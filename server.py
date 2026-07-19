"""PatentAgent FastAPI Backend

Start:  uvicorn server:app --reload --port 8000
Docs:  http://localhost:8000/docs
"""

import json
import logging
import os
import sys
import asyncio
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
import httpx

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from engine.parser import PatentMiner
from storage.datastore import PatentDataStore
from models.session import Session, ToolExecution
from models.analysis_results import GenericAnalysisResult
from tools import tool_registry
from tools.base import Tool
from agent.llm import LLMClient, LLMProvider
from agent.final_answer import user_facing_content
from agent.orchestrator import AnalysisPlan, PatentAgentOrchestrator, build_default_knowledge
from ui.report import ReportGenerator
from storage.conversation_store import ConversationStore, execution_cache_key
from storage.provider_store import ProviderProfileStore
from models.provider_profile import (
    ProviderCredentials,
    ProviderProfile,
    ProviderProfileCreate,
    ProviderProfileUpdate,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  App
# ═══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(_: FastAPI):
    global _store, _conversation_store, _provider_store
    input_dir = _validate_input_dir(os.getenv("MCP_INPUT_DIR", "./my_patents"))
    _store = _load_store(input_dir)
    session_db = Path(os.getenv(
        "PATENTAGENT_SESSION_DB",
        os.path.join(_project_root, ".patentagent", "sessions.db"),
    )).expanduser().resolve()
    _conversation_store = ConversationStore(session_db)
    await _conversation_store.initialize()
    _provider_store = ProviderProfileStore(session_db)
    await _provider_store.initialize()
    yield


app = FastAPI(
    title="PatentAgent API", version="3.0",
    description="可追溯的专利分析、流式 Agent 对话与报告导出",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "PATENTAGENT_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
#  Global state
# ═══════════════════════════════════════════════════════════

_store: PatentDataStore = None
_agent: PatentAgentOrchestrator = None
_sessions: dict[str, Session] = {}
_conversation_store: ConversationStore | None = None
_provider_store: ProviderProfileStore | None = None
_credential_vault: dict[str, dict] = {}
_connected_profile_id: str | None = None
_connected_profile_snapshot: dict | None = None
_llm_capabilities: dict = {}
_profiles_needing_reconnect: set[str] = set()


def _normalize_history_messages(messages: list[dict]) -> list[dict]:
    """Repair legacy assistant JSON for display/context without rewriting SQLite."""
    normalized_messages: list[dict] = []
    for stored in messages:
        item = dict(stored)
        if item.get("role") == "assistant":
            visible, canonical, mode = user_facing_content(str(item.get("content", "")))
            item["content"] = visible
            if canonical is not None:
                metadata = dict(item.get("metadata") or {})
                metadata["answer_format"] = "markdown"
                metadata["normalization_mode"] = mode
                if canonical.get("followup_suggestions"):
                    # The stored suggestions may be an older deterministic
                    # fallback created only because this JSON was not parsed.
                    metadata["followup_suggestions"] = canonical["followup_suggestions"]
                    metadata["followup_questions"] = [
                        entry["text"] for entry in canonical["followup_suggestions"]
                    ]
                if canonical.get("evidence_refs"):
                    metadata.setdefault("evidence_refs", canonical["evidence_refs"])
                item["metadata"] = metadata
        normalized_messages.append(item)
    return normalized_messages


def _normalize_session_detail(detail: dict) -> dict:
    normalized = dict(detail)
    normalized["messages"] = _normalize_history_messages(detail.get("messages", []))
    turns = []
    for stored in detail.get("turns", []):
        turn = dict(stored)
        if turn.get("final_text"):
            turn["final_text"] = user_facing_content(str(turn["final_text"]))[0]
        turns.append(turn)
    normalized["turns"] = turns
    return normalized


def _normalize_evidence_history(evidence: list[dict]) -> list[dict]:
    normalized = []
    for stored in evidence:
        item = dict(stored)
        if item.get("final_text"):
            item["final_text"] = user_facing_content(str(item["final_text"]))[0]
        normalized.append(item)
    return normalized


def _allowed_data_root() -> Path:
    return Path(os.getenv(
        "PATENT_DATA_ROOT", os.path.join(_project_root, "my_patents")
    )).expanduser().resolve()


def _validate_input_dir(input_dir: str) -> str:
    candidate = Path(input_dir).expanduser().resolve()
    allowed = _allowed_data_root()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise HTTPException(
            403, f"数据目录必须位于允许目录内: {allowed}",
        ) from exc
    return str(candidate)


def _load_store(input_dir: str) -> PatentDataStore:
    """Load patent data using WoSAdapter (default)."""
    from engine.adapters.wos_adapter import WoSAdapter
    adapter = WoSAdapter()
    df = adapter.batch_parse(input_dir)
    s = PatentDataStore(source_dir=input_dir)
    if not df.empty:
        s.load_dataframe(df)
    s._adapter_name = adapter.name
    from storage.dataset_manifest import inspect_dii_batches
    s._load_diagnostics = inspect_dii_batches(input_dir, len(df))
    return s


def _dataset_inventory() -> list[dict]:
    """List manifest-backed datasets below the configured data root."""
    root = _allowed_data_root()
    inventory = []
    if not root.is_dir():
        return inventory
    for path in sorted(root.rglob("manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {"status": "invalid_manifest"}
        inventory.append({
            "dataset_id": payload.get("dataset_id", path.parent.name),
            "status": payload.get("status", "unknown"),
            "path": str(path.parent.relative_to(root)),
            "retrieved_records": payload.get("retrieved_records", 0),
            "query": payload.get("query", ""),
        })
    return inventory


def _dataset_fingerprint() -> str:
    return _store.dataset_fingerprint() if _store else "empty"


def _conversation_repo() -> ConversationStore:
    if _conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    return _conversation_store


def _provider_repo() -> ProviderProfileStore:
    if _provider_store is None:
        raise HTTPException(503, "供应商配置存储尚未初始化")
    return _provider_store


# ═══════════════════════════════════════════════════════════
#  Request models
# ═══════════════════════════════════════════════════════════

class LoadRequest(BaseModel):
    input_dir: str = "./my_patents"

class ToolRequest(BaseModel):
    params: dict = {}
    session_id: str | None = None

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    response_mode: str = "detailed"
    reply_to_turn_id: str | None = None

class SessionCreateRequest(BaseModel):
    name: str = "新会话"

class SessionRenameRequest(BaseModel):
    name: str

class ResynthesizeRequest(BaseModel):
    response_mode: str = "detailed"

class ExportRequest(BaseModel):
    messages: list[dict]
    title: str = "PatentAgent Report"

class LLMConfigRequest(BaseModel):
    provider: str = "Claude"       # Claude | OpenAI | DeepSeek
    api_key: str = ""
    base_url: str = ""
    model: str | None = None


class ProviderSecretRequest(ProviderCredentials):
    pass


# ═══════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    ds = _store.get_summary() if _store else None
    selected = await _provider_repo().selected_profile() if _provider_store else None
    return {
        "status": "ok",
        "patents_loaded": ds.total_patents if ds else 0,
        "year_range": list(ds.year_range) if ds and ds.year_range != (0, 0) else None,
        "tools": len(tool_registry.get_all_names()),
        "agent_configured": _agent is not None,
        "selected_profile": _public_profile(selected) if selected else None,
        "connected_profile": _connected_profile_snapshot,
        "credential_loaded": bool(
            _connected_profile_id and _connected_profile_id in _credential_vault
        ),
        "llm_capabilities": _llm_capabilities,
    }

# ═══════════════════════════════════════════════════════════
#  Data
# ═══════════════════════════════════════════════════════════

@app.post("/api/data/load")
def data_load(req: LoadRequest):
    global _store
    _store = _load_store(_validate_input_dir(req.input_dir))
    ds = _store.get_summary()
    return {
        "total_patents": ds.total_patents,
        "year_range": list(ds.year_range),
        "ipc_sections": ds.ipc_sections,
        "top_applicants": [{"name": n, "count": c} for n, c in ds.top_applicants],
        "datasets": _dataset_inventory(),
        **_store.audit(),
    }

@app.get("/api/data/summary")
def data_summary():
    if not _store or _store.is_empty:
        raise HTTPException(404, "No patent data loaded. POST /api/data/load first.")
    ds = _store.get_summary()
    return {
        "total_patents": ds.total_patents,
        "year_range": list(ds.year_range),
        "ipc_sections": ds.ipc_sections,
        "top_applicants": [{"name": n, "count": c} for n, c in ds.top_applicants[:10]],
        "datasets": _dataset_inventory(),
        **_store.audit(),
    }

# ═══════════════════════════════════════════════════════════
#  Tools
# ═══════════════════════════════════════════════════════════

@app.get("/api/tools")
def list_tools():
    """列出工具参数、当前数据能力、方法与证据等级。"""
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "methodology": t.methodology,
                "evidence_level": t.evidence_record.get("evidence_type", t.evidence_level),
                "algorithm": t.evidence_record,
                "cost_weight": t.cost_weight,
                "returned_fields": t.returned_fields,
                "availability": t.availability(_store) if _store else {
                    "available": False, "reason": "尚未加载数据",
                },
            }
            for t in tool_registry.list_tools()
        ]
    }

@app.post("/api/tools/{tool_name}")
async def run_tool(tool_name: str, req: ToolRequest = ToolRequest()):
    """Execute a single analysis tool."""
    if not _store or _store.is_empty:
        raise HTTPException(400, "No patent data. Call /api/data/load first.")

    try:
        tool = tool_registry.get_tool(tool_name)
    except KeyError:
        names = tool_registry.get_all_names()
        raise HTTPException(404, f"Unknown tool '{tool_name}'. Available: {names}")

    try:
        result = await tool.run(_store, **req.params)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Tool {tool_name} failed: {e}")

    if hasattr(result, "model_dump"):
        payload = result.model_dump()
        if req.session_id:
            repo = _conversation_repo()
            await repo.ensure_session(req.session_id, _dataset_fingerprint())
            turn_id = await repo.start_turn(
                req.session_id, "", origin="quick_tool",
            )
            execution_id = f"quick_{tool_name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            metadata = payload.get("result_metadata", {})
            await repo.record_execution(
                req.session_id, turn_id, execution_id, tool_name, req.params,
                "completed", payload,
                duration_ms=float(metadata.get("elapsed_ms", 0) or 0),
                algorithm_version=str(metadata.get("algorithm_version", "")),
                dataset_fingerprint=_dataset_fingerprint(),
            )
            await repo.finish_turn(
                req.session_id, turn_id,
                payload.get("summary") or f"{tool_name} 已完成。",
                metadata={"origin": "quick_tool", "execution_id": execution_id},
            )
            payload.setdefault("result_metadata", {}).update({
                "session_id": req.session_id,
                "turn_id": turn_id,
                "execution_id": execution_id,
                "origin": "quick_tool",
            })
        return payload
    return {"result_type": "patent_details", "data": [
        item.model_dump() if hasattr(item, "model_dump") else item
        for item in result
    ]}

# ═══════════════════════════════════════════════════════════
#  LLM Config
# ═══════════════════════════════════════════════════════════

_PROTOCOL_MAP = {
    "openai_chat": LLMProvider.OPENAI,
    "anthropic_messages": LLMProvider.CLAUDE,
    "deepseek_chat": LLMProvider.DEEPSEEK,
}


def _public_profile(profile: dict | None) -> dict | None:
    """Return a profile without ever exposing API keys or sensitive values."""
    if not profile:
        return None
    profile_id = profile["id"]
    vault = _credential_vault.get(profile_id, {})
    loaded_headers = set(vault.get("sensitive_headers", {}))
    public_headers = []
    for raw in profile.get("extra_headers", []):
        header = dict(raw)
        if header.get("sensitive"):
            header["value"] = ""
            header["credential_loaded"] = header.get("name") in loaded_headers
        else:
            header["credential_loaded"] = False
        public_headers.append(header)
    item = dict(profile)
    item.update({
        "extra_headers": public_headers,
        "credential_loaded": (
            item.get("auth_mode") == "none" or bool(vault.get("api_key"))
        ),
        "connected": profile_id == _connected_profile_id and _agent is not None,
        "needs_reconnect": profile_id in _profiles_needing_reconnect,
    })
    return ProviderProfile.model_validate(item).model_dump()


def _redacted_error(exc: Exception, secrets: list[str] | None = None) -> str:
    text = str(exc)
    for secret in secrets or []:
        if secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(
        r"(?i)(api[-_ ]?key|authorization|x-api-key)\s*[:=]\s*[^\s,}]+",
        r"\1=[redacted]", text,
    )
    return f"{type(exc).__name__}: {text[:500]}"


def _merged_credentials(
    profile: dict, supplied: ProviderCredentials | None,
) -> dict:
    cached = dict(_credential_vault.get(profile["id"], {}))
    cached_headers = dict(cached.get("sensitive_headers", {}))
    if supplied:
        if supplied.api_key:
            cached["api_key"] = supplied.api_key
        cached_headers.update({
            name: value for name, value in supplied.sensitive_headers.items() if value
        })
    cached["sensitive_headers"] = cached_headers
    if profile["auth_mode"] != "none" and not cached.get("api_key"):
        raise ValueError("该配置需要 API Key；凭证不会在重启后自动恢复")
    missing = [
        header["name"] for header in profile.get("extra_headers", [])
        if header.get("sensitive") and not cached_headers.get(header["name"])
    ]
    if missing:
        raise ValueError("缺少敏感 Header 值: " + ", ".join(missing))
    return cached


def _request_headers(profile: dict, credentials: dict) -> tuple[dict[str, str], str]:
    headers: dict[str, str] = {}
    secret_headers = credentials.get("sensitive_headers", {})
    for header in profile.get("extra_headers", []):
        value = secret_headers.get(header["name"], "") if header.get("sensitive") else header.get("value", "")
        if value:
            headers[header["name"]] = value
    key = credentials.get("api_key", "")
    auth_mode = profile["auth_mode"]
    sdk_key = key
    if auth_mode == "x_api_key":
        headers.setdefault(profile.get("auth_header_name") or "x-api-key", key)
        if profile["protocol"] != "anthropic_messages":
            sdk_key = "patentagent-custom-auth"
    elif auth_mode == "custom_header":
        headers[profile["auth_header_name"]] = f"{profile.get('auth_prefix', '')}{key}"
        sdk_key = "patentagent-custom-auth"
    elif auth_mode == "none":
        sdk_key = "patentagent-no-auth"
    return headers, sdk_key


def _build_llm_client(profile: dict, credentials: dict) -> LLMClient:
    if not profile.get("base_url"):
        raise ValueError("请求地址不能为空")
    if not profile.get("model"):
        raise ValueError("模型 ID 不能为空")
    headers, sdk_key = _request_headers(profile, credentials)
    return LLMClient(
        provider=_PROTOCOL_MAP[profile["protocol"]],
        api_key=sdk_key,
        base_url=profile["base_url"],
        model=profile["model"],
        max_retries=profile["max_retries"],
        timeout_seconds=profile["timeout_seconds"],
        max_output_tokens=profile["max_output_tokens"],
        temperature=profile.get("temperature"),
        reasoning_effort=profile["reasoning_effort"],
        thinking_mode=profile["thinking_mode"],
        extra_headers=headers,
        extra_body=profile.get("extra_body", {}),
    )


async def _close_current_agent() -> None:
    global _agent, _connected_profile_id, _connected_profile_snapshot, _llm_capabilities
    client = getattr(_agent, "llm", None) if _agent else None
    _agent = None
    _connected_profile_id = None
    _connected_profile_snapshot = None
    _llm_capabilities = {}
    if client and hasattr(client, "close"):
        try:
            await client.close()
        except Exception:
            logger.warning("Failed to close previous LLM client", exc_info=False)


async def _probe_profile(profile: dict, supplied: ProviderCredentials) -> tuple[LLMClient, dict, dict]:
    credentials = _merged_credentials(profile, supplied)
    client = _build_llm_client(profile, credentials)
    try:
        probe = await client.probe_detailed()
    except Exception:
        await client.close()
        raise
    return client, probe, credentials


@app.get("/api/llm/profiles")
async def list_llm_profiles():
    return {"profiles": [
        _public_profile(profile) for profile in await _provider_repo().list_profiles()
    ]}


@app.post("/api/llm/profiles")
async def create_llm_profile(req: ProviderProfileCreate):
    try:
        profile = await _provider_repo().create_profile(req)
    except Exception as exc:
        raise HTTPException(422, _redacted_error(exc))
    return _public_profile(profile)


@app.patch("/api/llm/profiles/{profile_id}")
async def update_llm_profile(profile_id: str, req: ProviderProfileUpdate):
    global _connected_profile_id
    try:
        profile = await _provider_repo().update_profile(
            profile_id, req.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(404, "供应商配置不存在")
    except Exception as exc:
        raise HTTPException(422, _redacted_error(exc))
    if profile_id == _connected_profile_id:
        _profiles_needing_reconnect.add(profile_id)
        await _close_current_agent()
    return _public_profile(profile)


@app.delete("/api/llm/profiles/{profile_id}")
async def delete_llm_profile(profile_id: str):
    try:
        profile = await _provider_repo().get_profile(profile_id)
    except KeyError:
        raise HTTPException(404, "供应商配置不存在")
    if profile.get("selected") or profile_id == _connected_profile_id:
        raise HTTPException(409, "当前配置不能删除；请先断开，并选择其他配置")
    await _provider_repo().delete_profile(profile_id)
    _credential_vault.pop(profile_id, None)
    _profiles_needing_reconnect.discard(profile_id)
    return {"status": "deleted", "profile_id": profile_id}


@app.post("/api/llm/profiles/{profile_id}/probe")
async def probe_llm_profile(profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest()):
    try:
        profile = await _provider_repo().get_profile(profile_id)
        client, probe, credentials = await _probe_profile(profile, req)
        _credential_vault[profile_id] = credentials
        await client.close()
        return {
            "status": "passed", "profile": _public_profile(profile),
            "model": profile["model"], "latency_ms": probe["latency_ms"],
            "capabilities": probe, "stages": probe["stages"],
        }
    except KeyError:
        raise HTTPException(404, "供应商配置不存在")
    except Exception as exc:
        secrets = [req.api_key, *req.sensitive_headers.values()]
        raise HTTPException(502, "连接探测失败: " + _redacted_error(exc, secrets))


@app.post("/api/llm/profiles/{profile_id}/models")
async def discover_llm_models(profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest()):
    try:
        profile = await _provider_repo().get_profile(profile_id)
        credentials = _merged_credentials(profile, req)
        headers, sdk_key = _request_headers(profile, credentials)
        if profile["auth_mode"] == "bearer":
            headers.setdefault("Authorization", f"Bearer {sdk_key}")
        elif profile["auth_mode"] == "x_api_key":
            headers.setdefault(profile.get("auth_header_name") or "x-api-key", credentials.get("api_key", ""))
        if profile["protocol"] == "anthropic_messages":
            headers.setdefault("anthropic-version", "2023-06-01")
        url = profile["base_url"].rstrip("/") + "/" + profile["model_discovery_path"].lstrip("/")
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=profile["timeout_seconds"], follow_redirects=False) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
        raw_models = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
        models = sorted({
            str(item.get("id") or item.get("name")) if isinstance(item, dict) else str(item)
            for item in raw_models if item
        })
        if not models:
            raise ValueError("模型端点未返回可识别的模型列表")
        _credential_vault[profile_id] = credentials
        return {
            "models": models,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "manual_entry_allowed": True,
        }
    except KeyError:
        raise HTTPException(404, "供应商配置不存在")
    except Exception as exc:
        secrets = [req.api_key, *req.sensitive_headers.values()]
        raise HTTPException(502, "获取模型失败，可继续手工填写模型 ID。" + _redacted_error(exc, secrets))


@app.post("/api/llm/profiles/{profile_id}/activate")
async def activate_llm_profile(profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest()):
    global _agent, _connected_profile_id, _connected_profile_snapshot, _llm_capabilities
    try:
        profile = await _provider_repo().get_profile(profile_id)
        new_client, probe, credentials = await _probe_profile(profile, req)
    except KeyError:
        raise HTTPException(404, "供应商配置不存在")
    except Exception as exc:
        secrets = [req.api_key, *req.sensitive_headers.values()]
        raise HTTPException(502, "无法激活供应商: " + _redacted_error(exc, secrets))

    old_agent = _agent
    _agent = PatentAgentOrchestrator(
        llm_client=new_client,
        tool_registry=tool_registry,
        knowledge_base=build_default_knowledge(),
    )
    await _provider_repo().select_profile(profile_id)
    _credential_vault[profile_id] = credentials
    _connected_profile_id = profile_id
    _llm_capabilities = probe
    _profiles_needing_reconnect.discard(profile_id)
    selected = await _provider_repo().get_profile(profile_id)
    _connected_profile_snapshot = {
        "id": profile_id, "name": selected["name"],
        "protocol": selected["protocol"], "model": selected["model"],
    }
    if old_agent and getattr(old_agent, "llm", None) is not new_client:
        try:
            await old_agent.llm.close()
        except Exception:
            logger.warning("Failed to close replaced LLM client", exc_info=False)
    return {
        "status": "connected", "profile": _public_profile(selected),
        "capabilities": probe,
    }


@app.post("/api/llm/disconnect")
async def disconnect_llm():
    await _close_current_agent()
    return {"status": "disconnected"}

@app.post("/api/agent/config")
async def agent_config(req: LLMConfigRequest):
    """Configure the LLM backend for agent chat."""
    global _agent, _connected_profile_id, _connected_profile_snapshot, _llm_capabilities
    if not req.api_key:
        raise HTTPException(400, "API key required.")

    pmap = {"Claude": LLMProvider.CLAUDE, "OpenAI": LLMProvider.OPENAI,
            "DeepSeek": LLMProvider.DEEPSEEK}
    if req.provider not in pmap:
        raise HTTPException(400, f"Unknown provider '{req.provider}'. Use: Claude, OpenAI, DeepSeek")

    try:
        client = LLMClient(provider=pmap[req.provider], api_key=req.api_key,
                           base_url=req.base_url or None, model=req.model or None)
        probe = await client.probe_detailed()
        old_agent = _agent
        _agent = PatentAgentOrchestrator(
            llm_client=client,
            tool_registry=tool_registry,
            knowledge_base=build_default_knowledge(),
        )
        _connected_profile_id = None
        _connected_profile_snapshot = {
            "id": "legacy", "name": req.provider,
            "protocol": {
                "Claude": "anthropic_messages", "OpenAI": "openai_chat",
                "DeepSeek": "deepseek_chat",
            }[req.provider],
            "model": probe["model"],
        }
        _llm_capabilities = probe
        if old_agent and getattr(old_agent, "llm", None) is not client:
            try:
                await old_agent.llm.close()
            except Exception:
                pass
        return {"status": "ok", "provider": req.provider,
                "model": probe["model"], "probe": "passed",
                "tool_roundtrip": probe.get("tool_roundtrip", False),
                "structured_output": probe.get("structured_output", False)}
    except Exception as e:
        raise HTTPException(500, f"Failed to create agent: {e}")

# ═══════════════════════════════════════════════════════════
#  Persistent conversations
# ═══════════════════════════════════════════════════════════

@app.post("/api/sessions")
async def create_session(req: SessionCreateRequest = SessionCreateRequest()):
    return await _conversation_repo().create_session(
        req.name, _dataset_fingerprint(),
    )


@app.get("/api/sessions")
async def list_sessions():
    return {"sessions": await _conversation_repo().list_sessions()}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    try:
        await _conversation_repo().ensure_session(
            session_id, _dataset_fingerprint(),
        )
        detail = await _conversation_repo().get_session_detail(session_id)
        return _normalize_session_detail(detail)
    except KeyError:
        raise HTTPException(404, "会话不存在")


@app.patch("/api/sessions/{session_id}")
async def rename_session(session_id: str, req: SessionRenameRequest):
    try:
        return await _conversation_repo().rename_session(session_id, req.name)
    except KeyError:
        raise HTTPException(404, "会话不存在")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        await _conversation_repo().delete_session(session_id)
    except KeyError:
        raise HTTPException(404, "会话不存在")
    _sessions.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}


# ═══════════════════════════════════════════════════════════
#  Agent Chat (SSE streaming)
# ═══════════════════════════════════════════════════════════

@app.post("/api/agent/chat")
async def agent_chat(req: ChatRequest):
    """Streaming agent chat via Server-Sent Events."""
    if not _agent:
        raise HTTPException(400, "Agent not configured. Call /api/agent/config first.")
    if not _store or _store.is_empty:
        raise HTTPException(400, "No patent data. Call /api/data/load first.")

    if req.response_mode not in {"detailed", "concise"}:
        raise HTTPException(422, "response_mode 必须是 detailed 或 concise")
    repo = _conversation_repo()
    session_id = req.session_id or f"api_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    persisted_session = await repo.ensure_session(
        session_id, _dataset_fingerprint(), "API Chat",
    )
    recent_messages = _normalize_history_messages(
        await repo.get_recent_messages(session_id),
    )
    effective_message = req.message
    if req.reply_to_turn_id:
        pending_turn = await repo.get_turn(req.reply_to_turn_id)
        if not pending_turn or pending_turn.get("session_id") != session_id:
            raise HTTPException(404, "待回复的澄清轮次不存在")
        effective_message = (
            f"原始问题：{pending_turn.get('user_message', '')}\n"
            f"用户补充：{req.message}"
        )

    turn_id = await repo.start_turn(
        session_id, req.message, req.response_mode,
        provider=getattr(getattr(_agent, "llm", None), "provider", "").value
        if getattr(getattr(_agent, "llm", None), "provider", None) else "",
        model=str(getattr(getattr(_agent, "llm", None), "model", "") or ""),
        provider_profile_id=str((_connected_profile_snapshot or {}).get("id", "")),
        provider_name=str((_connected_profile_snapshot or {}).get("name", "")),
        provider_protocol=str((_connected_profile_snapshot or {}).get("protocol", "")),
    )
    session = Session(
        id=session_id,
        name=persisted_session.get("name", "API Chat"),
        created_at=datetime.fromisoformat(persisted_session["created_at"]),
        dataset_id=_dataset_fingerprint(),
        messages=recent_messages,
    )
    _sessions[session_id] = session
    historical_evidence = _normalize_evidence_history(
        await repo.get_evidence(session_id),
    )

    async def reuse_lookup(tool_name: str, params: dict, algorithm_version: str):
        key = execution_cache_key(
            _dataset_fingerprint(), tool_name, params, algorithm_version,
        )
        found = await repo.find_reusable(session_id, key)
        if not found:
            return None
        result = GenericAnalysisResult.model_validate(found.get("result", {}))
        return ToolExecution(
            id=f"reuse_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            tool_name=tool_name,
            parameters=params,
            status="completed",
            result=result,
            duration_ms=0,
            origin="reused",
            reused_from_execution_id=found["id"],
        )

    async def event_stream() -> AsyncIterator[str]:
        final_text = ""
        final_status = "failed"
        terminal_sent = False
        step_summaries: list[str] = []
        final_metadata: dict = {}
        try:
            async for event in _agent.stream_query(
                effective_message, session, _store, req.response_mode,
                historical_evidence=historical_evidence,
                turn_id=turn_id,
                reuse_lookup=reuse_lookup,
            ):
                if event["type"] == "final":
                    raw_final_text = str(event.get("text", "") or "")
                    final_text, canonical, boundary_mode = user_facing_content(
                        raw_final_text,
                    )
                    final_status = event.get("final_status", "completed")
                    normalization_mode = event.get("normalization_mode", "native")
                    if boundary_mode != "native":
                        normalization_mode = boundary_mode
                    if boundary_mode == "fallback":
                        final_status = "partial"
                    suggestions = event.get("followup_suggestions", [])
                    questions = event.get("followup_questions", [])
                    evidence_refs = event.get("evidence_refs", [])
                    if canonical is not None:
                        suggestions = suggestions or canonical.get("followup_suggestions", [])
                        questions = questions or [item["text"] for item in suggestions]
                        evidence_refs = evidence_refs or canonical.get("evidence_refs", [])
                    final_metadata = {
                        "followup_questions": questions,
                        "followup_suggestions": suggestions,
                        "evidence_refs": evidence_refs,
                        "llm_response": event.get("llm_response", {}),
                        "answer_format": "markdown",
                        "normalization_mode": normalization_mode,
                    }
                    for chunk in _chunk_text(final_text, 12):
                        yield _sse({"type": "text", "content": chunk})
                        await asyncio.sleep(0.01)
                    if event.get("strategy"):
                        yield _sse({"type": "strategy", "report": event["strategy"]})
                elif event["type"] == "intent":
                    await repo.update_turn(turn_id, intent_json={
                        "goal": event.get("goal", ""),
                        "analysis_type": event.get("analysis_type", ""),
                    }, status="planning")
                    yield _sse(event)
                elif event["type"] == "plan":
                    await repo.update_turn(
                        turn_id, plan_json={
                            "steps": event.get("steps", []),
                            "chain_id": event.get("chain_id", ""),
                            "decision_source": event.get("decision_source", ""),
                            "tool_calls": event.get("tool_calls", []),
                            "reused_evidence": event.get("reused_evidence", []),
                            "validation_status": event.get("validation_status", ""),
                            "cost_weight": event.get("cost_weight", 0),
                            "requires_confirmation": event.get("requires_confirmation", False),
                            "provider": event.get("provider", ""),
                            "model": event.get("model", ""),
                            "request_id": event.get("request_id", ""),
                            "usage": event.get("usage", {}),
                            "finish_reason": event.get("finish_reason", ""),
                        }, status="executing",
                    )
                    yield _sse(event)
                elif event["type"] == "clarification":
                    await repo.update_turn(
                        turn_id, status="awaiting_clarification",
                        pending_question_json=event,
                    )
                    yield _sse(event)
                elif event["type"] == "synthesis":
                    await repo.update_turn(turn_id, status="synthesizing")
                    yield _sse(event)
                elif event["type"] == "step":
                    result_payload = event.get("result") or {}
                    metadata = result_payload.get("result_metadata", {})
                    await repo.record_execution(
                        session_id, turn_id,
                        event.get("execution_id") or f"exec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        event.get("tool", ""), event.get("parameters", {}),
                        event.get("status", "failed"), result_payload,
                        error=event.get("error") or "",
                        duration_ms=float(event.get("duration_ms", 0) or 0),
                        algorithm_version=str(metadata.get("algorithm_version", "")),
                        dataset_fingerprint=_dataset_fingerprint(),
                        coverage={
                            "fields_read": sorted(result_payload.keys()),
                            "omitted": False,
                        },
                        provider_tool_call_id=str(event.get("provider_tool_call_id") or ""),
                        validation={"status": "valid"},
                    )
                    if event.get("summary"):
                        step_summaries.append(
                            f"[{event.get('tool')}] {event.get('summary')}"
                        )
                    yield _sse(event)
                elif event["type"] == "done":
                    incoming_status = event.get("final_status", final_status)
                    if not (
                        final_metadata.get("normalization_mode") == "fallback" and
                        incoming_status == "completed"
                    ):
                        final_status = incoming_status
                    event["final_status"] = final_status
                    final_metadata.update({
                        "result_coverage": event.get("result_coverage", []),
                        "coverage_complete": event.get("coverage_complete", False),
                        "new_execution_ids": event.get("new_execution_ids", []),
                        "reused_execution_ids": event.get("reused_execution_ids", []),
                    })
                    if not final_text.strip() and final_status not in {"failed"}:
                        final_text = _server_fallback_summary(step_summaries)
                        yield _sse({"type": "synthesis", "status": "fallback",
                                    "turn_id": turn_id})
                        yield _sse({"type": "text", "content": final_text})
                        event["final_status"] = "partial"
                        event["answer_present"] = True
                        final_status = "partial"
                    event["followup_questions"] = final_metadata.get(
                        "followup_questions", []
                    )
                    event["followup_suggestions"] = final_metadata.get(
                        "followup_suggestions", []
                    )
                    event["answer_format"] = "markdown"
                    event["normalization_mode"] = final_metadata.get(
                        "normalization_mode", "native",
                    )
                    await repo.finish_turn(
                        session_id, turn_id, final_text, final_status,
                        metadata=final_metadata,
                    )
                    terminal_sent = True
                    yield _sse(event)
                else:
                    yield _sse(event)
            if not terminal_sent:
                raise RuntimeError("SSE_STREAM_ENDED_WITHOUT_DONE")
        except asyncio.CancelledError:
            cancelled_text = (
                _server_fallback_summary(step_summaries, "用户取消了本轮分析")
                if step_summaries else "本轮分析已由用户取消。"
            )
            await repo.finish_turn(
                session_id, turn_id, cancelled_text, "cancelled", "用户取消",
                metadata={"cancelled": True},
            )
            raise
        except Exception as exc:
            logger.exception("Agent stream failed for turn %s", turn_id)
            fallback = final_text.strip() or _server_fallback_summary(
                step_summaries, str(exc),
            )
            status = "partial" if step_summaries else "failed"
            await repo.finish_turn(
                session_id, turn_id, fallback, status, str(exc),
                metadata={"stream_failure": True},
            )
            yield _sse({"type": "error", "message": str(exc),
                        "recoverable": True, "turn_id": turn_id})
            if fallback:
                yield _sse({"type": "text", "content": fallback})
            yield _sse({
                "type": "done", "session_id": session_id,
                "turn_id": turn_id, "final_status": status,
                "answer_present": bool(fallback), "result_coverage": [],
                "coverage_complete": False, "new_execution_ids": [],
                "reused_execution_ids": [],
                "answer_format": "markdown", "normalization_mode": "fallback",
            })

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/sessions/{session_id}/turns/{turn_id}/resynthesize")
async def resynthesize_turn(
    session_id: str, turn_id: str,
    req: ResynthesizeRequest = ResynthesizeRequest(),
):
    if not _agent:
        raise HTTPException(400, "Agent not configured. Call /api/agent/config first.")
    if req.response_mode not in {"detailed", "concise"}:
        raise HTTPException(422, "response_mode 必须是 detailed 或 concise")
    repo = _conversation_repo()
    turn = await repo.get_turn(turn_id)
    if not turn or turn.get("session_id") != session_id:
        raise HTTPException(404, "轮次不存在")
    detail = _normalize_session_detail(await repo.get_session_detail(session_id))
    executions: list[ToolExecution] = []
    for item in detail["tool_executions"]:
        if item.get("turn_id") != turn_id:
            continue
        if item.get("stale"):
            raise HTTPException(409, "数据集已经变化，不能把历史证据重新综合为当前结论")
        payload = item.get("result") or {}
        result = GenericAnalysisResult.model_validate(payload) if payload else None
        executions.append(ToolExecution(
            id=item["id"], tool_name=item["tool_name"],
            parameters=item.get("parameters", {}), status=item["status"],
            result=result, error=item.get("error") or None,
            duration_ms=item.get("duration_ms", 0), origin="restored",
        ))
    if not executions:
        raise HTTPException(422, "该轮次没有可用于重新综合的工具结果")
    plan_payload = turn.get("plan", {})
    plan = AnalysisPlan(
        steps=plan_payload.get("steps", []),
        chain_id=plan_payload.get("chain_id", ""),
    )
    try:
        text, evidence_refs, suggestions, normalization_mode = await _agent.resynthesize_from_evidence(
            turn.get("user_message", ""), executions, req.response_mode,
            history=detail.get("messages", []),
        )
        status = "completed"
    except Exception as exc:
        text = _agent._deterministic_fallback(executions, str(exc))
        evidence_refs = []
        suggestions = _agent._filter_followup_suggestions(
            _agent._fallback_followups(executions, turn.get("user_message", "")),
            turn.get("user_message", ""), detail.get("messages", []),
        )
        status = "partial"
        normalization_mode = "fallback"
    text, canonical, boundary_mode = user_facing_content(text)
    if boundary_mode != "native":
        normalization_mode = boundary_mode
    if canonical is not None:
        suggestions = suggestions or canonical.get("followup_suggestions", [])
        evidence_refs = evidence_refs or canonical.get("evidence_refs", [])
    if normalization_mode == "fallback":
        status = "partial"
    await repo.finish_turn(
        session_id, turn_id, text, status,
        metadata={
            "resynthesized": True,
            "evidence_refs": evidence_refs,
            "followup_suggestions": suggestions,
            "followup_questions": [item["text"] for item in suggestions],
            "answer_format": "markdown",
            "normalization_mode": normalization_mode,
        },
    )
    return {
        "session_id": session_id, "turn_id": turn_id,
        "final_status": status, "answer_present": bool(text.strip()),
        "text": text, "evidence_refs": evidence_refs,
        "answer_format": "markdown", "normalization_mode": normalization_mode,
        "followup_suggestions": suggestions,
        "followup_questions": [item["text"] for item in suggestions],
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _chunk_text(text: str, words_per_chunk: int = 8) -> list[str]:
    """Split text for SSE while preserving Markdown whitespace exactly."""
    tokens = re.findall(r"\S+\s*", text)
    if not tokens:
        return [text]
    return [
        "".join(tokens[index:index + words_per_chunk])
        for index in range(0, len(tokens), words_per_chunk)
    ]


def _server_fallback_summary(summaries: list[str], error: str = "") -> str:
    lines = [
        "## 结构化降级总结", "",
        "最终综合未正常完成，以下内容来自已经返回的工具结果。",
    ]
    if error:
        lines.append(f"错误：{error}")
    lines.extend(f"- {item}" for item in summaries)
    if not summaries:
        lines.append("- 本轮没有可用的工具结果。")
    lines.extend(["", "### 数据限制", "- 本回复为异常降级结果，可使用“仅重试总结”恢复完整报告。"])
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  Report export
# ═══════════════════════════════════════════════════════════

@app.post("/api/report/export")
def report_export(req: ExportRequest):
    gen = ReportGenerator()
    for msg in req.messages:
        if msg.get("content"):
            gen.add_section(
                msg.get("role", "assistant"),
                msg["content"],
            )
    html = gen.generate_html(title=req.title)
    return HTMLResponse(content=html)


# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
