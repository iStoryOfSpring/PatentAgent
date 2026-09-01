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
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from engine.parser import PatentMiner
from storage.datastore import PatentDataStore
from models.session import Session, ToolExecution
from models.analysis_results import GenericAnalysisResult
from tools import tool_registry
from tools.base import Tool
from agent.final_answer import user_facing_content
from agent.orchestrator import AnalysisPlan, PatentAgentOrchestrator, build_default_knowledge
from reporting import ReportGenerator
from storage.conversation_store import ConversationStore, execution_cache_key
from storage.provider_store import ProviderProfileStore
from models.provider_profile import (
    ProviderCredentials,
    ProviderProfileCreate,
    ProviderProfileUpdate,
)
from patent_agent.infrastructure import AppContainer, AppSettings
from patent_agent.infrastructure.observability import (
    RequestGuardMiddleware, TraceMiddleware, configure_json_logging,
    current_container, current_trace_id,
)
from patent_agent.security import validate_input_dir
from patent_agent.application import (
    AnalysisService, DatasetImportService, DatasetRuntimeManager, ProviderService, ReportService,
    SearchIndexService, TaskService,
    ToolExecutionService,
    normalize_evidence_history, normalize_history_messages,
    normalize_session_detail,
)
from patent_agent.api.schemas import (
    ChatRequest, ExportRequest, LLMConfigRequest, LoadRequest,
    ProviderSecretRequest, ResynthesizeRequest, SessionCreateRequest,
    SessionRenameRequest, ToolRequest,
)
from patent_agent.api.routes import (
    datasets_router, providers_router, reports_router, sessions_router,
    tasks_router, tools_router,
)
from patent_agent.api.routes.providers import (
    activate_llm_profile as _activate_llm_profile_route,
    agent_config as _agent_config_route,
    create_llm_profile as _create_llm_profile_route,
    delete_llm_profile as _delete_llm_profile_route,
    disconnect_llm as _disconnect_llm_route,
    discover_llm_models as _discover_llm_models_route,
    list_llm_profiles as _list_llm_profiles_route,
    probe_llm_profile as _probe_llm_profile_route,
    update_llm_profile as _update_llm_profile_route,
)
from patent_agent.api.routes.datasets import (
    data_summary as _data_summary_route,
    list_datasets as _list_datasets_route,
    list_dataset_versions as _list_dataset_versions_route,
)
from patent_agent.api.routes.reports import report_export as _report_export_route
from patent_agent.api.routes.sessions import get_session as _get_session_route
from patent_agent.api.routes.tools import (
    list_tools as _list_tools_route, run_tool as _run_tool_route,
)
from patent_agent.api.routes.tasks import (
    cancel_task as _cancel_task_route,
    get_task as _get_task_route,
    get_task_events as _get_task_events_route,
)

logger = logging.getLogger("patentagent.server")
configure_json_logging(getattr(
    logging, os.getenv("PATENTAGENT_LOG_LEVEL", "INFO").upper(), logging.INFO,
))

# ═══════════════════════════════════════════════════════════
#  App
# ═══════════════════════════════════════════════════════════

def _new_container() -> AppContainer:
    return AppContainer(AppSettings.from_env(_project_root))


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    runtime = fastapi_app.state.container
    runtime.dataset_service = runtime.dataset_service or DatasetImportService()
    runtime.analysis_service = runtime.analysis_service or AnalysisService()
    runtime.tool_execution_service = runtime.tool_execution_service or ToolExecutionService()
    runtime.report_service = runtime.report_service or ReportService(ReportGenerator)
    runtime.search_index_service = runtime.search_index_service or SearchIndexService()
    if runtime.agent is not None:
        await ProviderService(runtime).close_current()
    runtime.clear_ephemeral()
    input_dir = validate_input_dir(
        os.getenv("MCP_INPUT_DIR", "./my_patents"), runtime.settings.data_root,
    )
    runtime.store = runtime.dataset_service.load(input_dir, "auto")
    session_db = Path(os.getenv(
        "PATENTAGENT_SESSION_DB",
        os.path.join(_project_root, ".patentagent", "sessions.db"),
    )).expanduser().resolve()
    runtime.conversation_store = ConversationStore(session_db)
    await runtime.conversation_store.initialize()
    runtime.provider_store = ProviderProfileStore(session_db)
    await runtime.provider_store.initialize()
    runtime.provider_service = ProviderService(runtime)
    await runtime.conversation_store.upsert_dataset_snapshot(
        {
            **runtime.store.snapshot().model_dump(mode="json"),
            "storage_path": runtime.store._source_dir,
            "source_root": runtime.store._source_dir,
        },
    )
    runtime.dataset_runtime = DatasetRuntimeManager(
        runtime.conversation_store, runtime.dataset_service,
        runtime.settings.dataset_cache_size,
    )
    runtime.dataset_runtime.register(runtime.store)
    await runtime.conversation_store.mark_inflight_interrupted()
    runtime.task_service = TaskService(runtime.conversation_store, resynthesize_turn)
    try:
        yield
    finally:
        await ProviderService(runtime).close_current()
        runtime.clear_ephemeral()


app = FastAPI(
    title="PatentAgent API", version="3.1",
    description="可追溯的专利分析、流式 Agent 对话与报告导出",
    lifespan=lifespan,
)
app.state.container = _new_container()


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_, exc: RequestValidationError):
    """Return useful validation locations without echoing request values."""
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        messages.append(f"{location}: {error.get('msg', '参数无效')}")
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数校验失败: " + "; ".join(messages)},
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
app.add_middleware(
    RequestGuardMiddleware,
    max_request_bytes=app.state.container.settings.max_request_bytes,
    streaming_path_limits={
        "/api/datasets/imports": app.state.container.settings.max_upload_total_bytes,
    },
)
app.add_middleware(TraceMiddleware)
app.include_router(datasets_router)
app.include_router(tools_router)
app.include_router(sessions_router)
app.include_router(reports_router)
app.include_router(providers_router)
app.include_router(tasks_router)

# ═══════════════════════════════════════════════════════════
#  Application-owned state
# ═══════════════════════════════════════════════════════════

def _runtime() -> AppContainer:
    return current_container() or app.state.container


def _load_store(input_dir: str) -> PatentDataStore:
    """Compatibility loader routed through the registry-driven importer."""
    s = DatasetImportService().load(input_dir, "auto")
    from storage.dataset_manifest import inspect_dii_batches
    s._load_diagnostics = inspect_dii_batches(input_dir, len(s.get_all()))
    return s


def _dataset_fingerprint() -> str:
    return _runtime().store.dataset_fingerprint() if _runtime().store else "empty"


def _conversation_repo() -> ConversationStore:
    if _runtime().conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    return _runtime().conversation_store


def _provider_repo() -> ProviderProfileStore:
    if _runtime().provider_store is None:
        raise HTTPException(503, "供应商配置存储尚未初始化")
    return _runtime().provider_store


# Direct-call compatibility for embedded users and older unit tests.  HTTP
# routing lives in patent_agent.api.routes; these wrappers do not own logic.
def data_summary():
    return _data_summary_route(_runtime())


def list_tools():
    return _list_tools_route(_runtime())


async def run_tool(tool_name: str, req: ToolRequest = ToolRequest()):
    return await _run_tool_route(tool_name, req, _runtime())


async def list_datasets():
    return await _list_datasets_route(_runtime())


async def list_dataset_versions(dataset_id: str):
    return await _list_dataset_versions_route(dataset_id, _runtime())


async def get_session(session_id: str):
    return await _get_session_route(session_id, _runtime())


async def report_export(req: ExportRequest):
    return await _report_export_route(req, _runtime())


async def list_llm_profiles():
    return await _list_llm_profiles_route(_runtime())


async def create_llm_profile(req: ProviderProfileCreate):
    return await _create_llm_profile_route(req, _runtime())


async def update_llm_profile(profile_id: str, req: ProviderProfileUpdate):
    return await _update_llm_profile_route(profile_id, req, _runtime())


async def delete_llm_profile(profile_id: str):
    return await _delete_llm_profile_route(profile_id, _runtime())


async def probe_llm_profile(profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest()):
    service = ProviderService(_runtime())
    service.probe_profile = _probe_profile
    try:
        return await service.probe(profile_id, req)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except Exception as exc:
        category = service.error_category(exc)
        service.record_probe_state(profile_id, "failed", error_category=category, stages=getattr(exc, "stages", {}))
        raise HTTPException(502, {
            "message": "连接探测失败: " + service.redacted_error(exc, [req.api_key, *req.sensitive_headers.values()]),
            "category": category, "stages": getattr(exc, "stages", {}),
        }) from exc


async def discover_llm_models(profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest()):
    return await _discover_llm_models_route(profile_id, req, _runtime())


async def activate_llm_profile(profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest()):
    service = ProviderService(_runtime())
    service.probe_profile = _probe_profile
    try:
        return await service.activate(profile_id, req)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except Exception as exc:
        category = service.error_category(exc)
        service.record_probe_state(profile_id, "failed", error_category=category, stages=getattr(exc, "stages", {}))
        raise HTTPException(502, {
            "message": "无法激活供应商: " + service.redacted_error(exc, [req.api_key, *req.sensitive_headers.values()]),
            "category": category, "stages": getattr(exc, "stages", {}),
        }) from exc


async def disconnect_llm():
    return await _disconnect_llm_route(_runtime())


async def agent_config(req: LLMConfigRequest):
    return await _agent_config_route(req, _runtime())


def _ensure_task_service() -> None:
    runtime = _runtime()
    repo = _conversation_repo()
    if runtime.task_service is None or runtime.task_service.repository is not repo:
        runtime.task_service = TaskService(repo, resynthesize_turn)


async def get_task(turn_id: str):
    _ensure_task_service()
    return await _get_task_route(turn_id, _runtime())


async def get_task_events(turn_id: str, last_event_id: str | None = None):
    _ensure_task_service()
    return await _get_task_events_route(turn_id, last_event_id, _runtime())


async def cancel_task(turn_id: str):
    _ensure_task_service()
    return await _cancel_task_route(turn_id, _runtime())


# ═══════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    ds = _runtime().store.get_summary() if _runtime().store else None
    selected = await _provider_repo().selected_profile() if _runtime().provider_store else None
    return {
        "status": "ok",
        "patents_loaded": ds.total_patents if ds else 0,
        "year_range": list(ds.year_range) if ds and ds.year_range != (0, 0) else None,
        "tools": len(tool_registry.get_all_names()),
        "agent_configured": _runtime().agent is not None,
        "selected_profile": ProviderService(_runtime()).public_profile(selected) if selected else None,
        "connected_profile": _runtime().connected_profile_snapshot,
        "credential_loaded": bool(
            selected and (
                selected.get("auth_mode") == "none" or
                bool(_runtime().credential_vault.get(selected["id"], {}).get("api_key"))
            )
        ),
        "llm_capabilities": _runtime().llm_capabilities,
        "active_generations": len(_runtime().active_generation_turns),
        "trace_id": current_trace_id(),
        "dataset_snapshot": (
            _runtime().store.snapshot().model_dump(mode="json")
            if _runtime().store else None
        ),
    }

# Provider probing lives in ProviderService. This hook remains patchable for
# embedded callers and contract tests; HTTP routes use the same service.
async def _probe_profile(profile: dict, supplied: ProviderCredentials):
    return await ProviderService(_runtime()).probe_profile(profile, supplied)

# ═══════════════════════════════════════════════════════════
#  Agent Chat (SSE streaming)
# ═══════════════════════════════════════════════════════════

@app.post("/api/agent/chat")
async def agent_chat(req: ChatRequest):
    """Streaming agent chat via Server-Sent Events."""
    if not _runtime().agent:
        raise HTTPException(400, "Agent not configured. Call /api/agent/config first.")
    # Freeze the Agent/profile pair for the whole turn. Provider mutations are
    # rejected while the generator below is active.
    turn_agent = _runtime().agent
    turn_provider_snapshot = dict(_runtime().connected_profile_snapshot or {})

    if req.response_mode not in {"detailed", "concise"}:
        raise HTTPException(422, "response_mode 必须是 detailed 或 concise")
    repo = _conversation_repo()
    session_id = req.session_id or f"api_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    turn_store = _runtime().store
    if _runtime().dataset_runtime:
        try:
            turn_store = await _runtime().dataset_runtime.for_session(session_id, turn_store)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, f"会话绑定的数据集不可用: {exc}") from exc
    if not turn_store or turn_store.is_empty:
        raise HTTPException(400, "No patent data. Import or activate a dataset first.")
    turn_fingerprint = turn_store.dataset_fingerprint()
    turn_version_id = turn_store.snapshot().version_id
    persisted_session = await repo.ensure_session(
        session_id, turn_fingerprint, "API Chat", turn_version_id,
    )
    recent_messages = normalize_history_messages(
        await repo.get_recent_messages(session_id),
    )
    effective_message = req.message
    approval_granted = False
    if req.reply_to_turn_id:
        pending_turn = await repo.get_turn(req.reply_to_turn_id)
        if not pending_turn or pending_turn.get("session_id") != session_id:
            raise HTTPException(404, "待回复的澄清轮次不存在")
        pending_plan = pending_turn.get("plan", {})
        was_budget_approval = bool(pending_plan.get("requires_confirmation"))
        normalized_reply = req.message.strip().lower().replace(" ", "")
        approval_granted = was_budget_approval and normalized_reply in {
            "确认", "确认执行", "同意", "批准", "approved", "approve", "yes",
        }
        await repo.record_approval(
            req.reply_to_turn_id,
            "approved" if approval_granted else "modified",
            {"reply": req.message, "new_turn_id_pending": True},
        )
        effective_message = pending_turn.get("user_message", "") if approval_granted else (
            f"原始问题：{pending_turn.get('user_message', '')}\n"
            f"用户补充：{req.message}"
        )

    turn_id = await repo.start_turn(
        session_id, req.message, req.response_mode,
        provider=getattr(getattr(turn_agent, "llm", None), "provider", "").value
        if getattr(getattr(turn_agent, "llm", None), "provider", None) else "",
        model=str(getattr(getattr(turn_agent, "llm", None), "model", "") or ""),
        provider_profile_id=str(turn_provider_snapshot.get("id", "")),
        provider_name=str(turn_provider_snapshot.get("name", "")),
        provider_protocol=str(turn_provider_snapshot.get("protocol", "")),
        dataset_version_id=turn_version_id,
        trace_id=current_trace_id(),
    )
    session = Session(
        id=session_id,
        name=persisted_session.get("name", "API Chat"),
        created_at=datetime.fromisoformat(persisted_session["created_at"]),
        dataset_id=turn_fingerprint,
        messages=recent_messages,
    )
    _runtime().sessions[session_id] = session
    historical_evidence = normalize_evidence_history(
        await repo.get_evidence(session_id),
    )

    async def reuse_lookup(tool_name: str, params: dict, algorithm_version: str):
        key = execution_cache_key(
            turn_fingerprint, tool_name, params, algorithm_version,
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
        _runtime().active_generation_turns.add(turn_id)
        try:
            yield await _persist_sse(repo, turn_id, {
                "type": "task_status", "status": "queued", "turn_id": turn_id,
            })
            async for event in turn_agent.stream_query(
                effective_message, session, turn_store, req.response_mode,
                historical_evidence=historical_evidence,
                turn_id=turn_id,
                reuse_lookup=reuse_lookup,
                approval_granted=approval_granted,
            ):
                event.setdefault("turn_id", turn_id)
                event.setdefault("dataset_version_id", turn_version_id)
                current_task = await repo.get_turn(turn_id)
                if current_task and current_task.get("cancel_requested"):
                    raise asyncio.CancelledError
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
                        yield await _persist_sse(repo, turn_id, {"type": "text", "content": chunk})
                        await asyncio.sleep(0.01)
                    if event.get("strategy"):
                        yield await _persist_sse(repo, turn_id, {"type": "strategy", "report": event["strategy"]})
                elif event["type"] == "intent":
                    await repo.update_turn(turn_id, intent_json={
                        "goal": event.get("goal", ""),
                        "analysis_type": event.get("analysis_type", ""),
                    }, status="planning")
                    yield await _persist_sse(repo, turn_id, event)
                elif event["type"] == "plan":
                    next_state = (
                        "waiting_approval"
                        if event.get("requires_confirmation", False)
                        else "running"
                    )
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
                        }, status=next_state,
                    )
                    yield await _persist_sse(repo, turn_id, event)
                    if next_state == "running":
                        yield await _persist_sse(repo, turn_id, {
                            "type": "task_status", "status": "running",
                            "turn_id": turn_id,
                        })
                elif event["type"] == "clarification":
                    await repo.update_turn(
                        turn_id, status="awaiting_clarification",
                        pending_question_json=event,
                    )
                    yield await _persist_sse(repo, turn_id, event)
                elif event["type"] == "synthesis":
                    await repo.update_turn(turn_id, status="synthesizing")
                    yield await _persist_sse(repo, turn_id, event)
                elif event["type"] == "step":
                    result_payload = event.get("result") or {}
                    metadata = result_payload.get("result_metadata", {})
                    await repo.update_turn(
                        turn_id,
                        status="validating" if event.get("status") == "completed" else "running",
                    )
                    await repo.record_execution(
                        session_id, turn_id,
                        event.get("execution_id") or f"exec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        event.get("tool", ""), event.get("parameters", {}),
                        event.get("status", "failed"), result_payload,
                        error=event.get("error") or "",
                        duration_ms=float(event.get("duration_ms", 0) or 0),
                        algorithm_version=str(metadata.get("algorithm_version", "")),
                        dataset_fingerprint=turn_fingerprint,
                        coverage={
                            "fields_read": sorted(result_payload.keys()),
                            "omitted": False,
                        },
                        provider_tool_call_id=str(event.get("provider_tool_call_id") or ""),
                        validation={"status": "valid"},
                        provenance=result_payload.get("provenance", {}),
                        metrics=result_payload.get("metrics", {}),
                    )
                    if event.get("summary"):
                        step_summaries.append(
                            f"[{event.get('tool')}] {event.get('summary')}"
                        )
                    yield await _persist_sse(repo, turn_id, event)
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
                        yield await _persist_sse(repo, turn_id, {"type": "synthesis", "status": "fallback",
                                    "turn_id": turn_id})
                        yield await _persist_sse(repo, turn_id, {"type": "text", "content": final_text})
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
                    yield await _persist_sse(repo, turn_id, event)
                else:
                    yield await _persist_sse(repo, turn_id, event)
            if not terminal_sent:
                raise RuntimeError("SSE_STREAM_ENDED_WITHOUT_DONE")
        except asyncio.CancelledError:
            cancelled_task = await repo.get_turn(turn_id)
            cancellation_requested = bool(
                cancelled_task and cancelled_task.get("cancel_requested")
            )
            cancelled_text = (
                _server_fallback_summary(step_summaries, "用户取消了本轮分析")
                if step_summaries else "本轮分析已由用户取消。"
            )
            await repo.finish_turn(
                session_id, turn_id, cancelled_text, "cancelled", "用户取消",
                metadata={"cancelled": True},
            )
            if cancellation_requested:
                yield await _persist_sse(repo, turn_id, {
                    "type": "done", "session_id": session_id,
                    "turn_id": turn_id, "final_status": "cancelled",
                    "answer_present": bool(cancelled_text),
                    "coverage_complete": False,
                })
                return
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
            yield await _persist_sse(repo, turn_id, {"type": "error", "message": str(exc),
                        "recoverable": True, "turn_id": turn_id})
            if fallback:
                yield await _persist_sse(repo, turn_id, {"type": "text", "content": fallback})
            yield await _persist_sse(repo, turn_id, {
                "type": "done", "session_id": session_id,
                "turn_id": turn_id, "final_status": status,
                "answer_present": bool(fallback), "result_coverage": [],
                "coverage_complete": False, "new_execution_ids": [],
                "reused_execution_ids": [],
                "answer_format": "markdown", "normalization_mode": "fallback",
            })
        finally:
            _runtime().active_generation_turns.discard(turn_id)

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/sessions/{session_id}/turns/{turn_id}/resynthesize")
async def resynthesize_turn(
    session_id: str, turn_id: str,
    req: ResynthesizeRequest = ResynthesizeRequest(),
):
    if not _runtime().agent:
        raise HTTPException(400, "Agent not configured. Call /api/agent/config first.")
    if req.response_mode not in {"detailed", "concise"}:
        raise HTTPException(422, "response_mode 必须是 detailed 或 concise")
    resynthesis_agent = _runtime().agent
    repo = _conversation_repo()
    turn = await repo.get_turn(turn_id)
    if not turn or turn.get("session_id") != session_id:
        raise HTTPException(404, "轮次不存在")
    detail = normalize_session_detail(await repo.get_session_detail(session_id))
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
    generation_id = f"resynthesize:{turn_id}"
    _runtime().active_generation_turns.add(generation_id)
    try:
        try:
            text, evidence_refs, suggestions, normalization_mode = await resynthesis_agent.resynthesize_from_evidence(
                turn.get("user_message", ""), executions, req.response_mode,
                history=detail.get("messages", []),
            )
            status = "completed"
        except Exception as exc:
            text = resynthesis_agent._deterministic_fallback(executions, str(exc))
            evidence_refs = []
            suggestions = resynthesis_agent._filter_followup_suggestions(
                resynthesis_agent._fallback_followups(executions, turn.get("user_message", "")),
                turn.get("user_message", ""), detail.get("messages", []),
            )
            status = "partial"
            normalization_mode = "fallback"
    finally:
        _runtime().active_generation_turns.discard(generation_id)
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


async def _persist_sse(repo: ConversationStore, turn_id: str, data: dict) -> str:
    payload = dict(data)
    payload.setdefault("trace_id", current_trace_id())
    payload.setdefault("task_id", turn_id)
    event_id = await repo.append_task_event(turn_id, payload)
    return _sse(payload, event_id)


def _sse(data: dict, event_id: int | None = None) -> str:
    payload = dict(data)
    payload.setdefault("trace_id", current_trace_id())
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return prefix + f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


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
#  Main
# ═══════════════════════════════════════════════════════════

def create_app(container: AppContainer | None = None) -> FastAPI:
    """Create an isolated API application for tests or embedded use.

    Route functions resolve the container from the current ASGI scope, so a
    factory-created app does not share the singleton's mutable runtime state.
    """
    candidate = FastAPI(
        title="PatentAgent API", version="3.1",
        description="可追溯的专利分析、流式 Agent 对话与报告导出",
        lifespan=lifespan,
    )
    candidate.state.container = container or _new_container()
    candidate.add_exception_handler(RequestValidationError, safe_validation_error)
    candidate.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in os.getenv(
            "PATENTAGENT_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    candidate.add_middleware(
        RequestGuardMiddleware,
        max_request_bytes=candidate.state.container.settings.max_request_bytes,
    )
    candidate.add_middleware(TraceMiddleware)
    framework_paths = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    candidate.router.routes.extend(
        route for route in app.router.routes
        if getattr(route, "path", "") not in framework_paths
    )
    return candidate

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
