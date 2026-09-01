"""Provider profile, credential and activation use cases."""

from __future__ import annotations

import re
import time
from datetime import datetime

import httpx

from agent.llm import LLMClient, LLMProvider
from agent.orchestrator import PatentAgentOrchestrator, build_default_knowledge
from models.provider_profile import (
    ProviderCredentials, ProviderProfile, ProviderProfileCreate,
    ProviderProfileUpdate,
)
from patent_agent.infrastructure import AppContainer
from patent_agent.security import assert_safe_provider_target
from tools import tool_registry


PROTOCOL_MAP = {
    "openai_chat": LLMProvider.OPENAI,
    "anthropic_messages": LLMProvider.CLAUDE,
    "deepseek_chat": LLMProvider.DEEPSEEK,
}


class ProviderBusyError(RuntimeError):
    pass


class ProviderInUseError(RuntimeError):
    pass


class ProviderService:
    def __init__(self, container: AppContainer):
        self.container = container

    @property
    def repository(self):
        if self.container.provider_store is None:
            raise RuntimeError("供应商配置存储尚未初始化")
        return self.container.provider_store

    def public_profile(self, profile: dict | None) -> dict | None:
        if not profile:
            return None
        profile_id = profile["id"]
        vault = self.container.credential_vault.get(profile_id, {})
        loaded_headers = {name.lower() for name in vault.get("sensitive_headers", {})}
        public_headers = []
        for raw in profile.get("extra_headers", []):
            header = dict(raw)
            if header.get("sensitive"):
                header["value"] = ""
                header["credential_loaded"] = header.get("name", "").lower() in loaded_headers
            else:
                header["credential_loaded"] = False
            public_headers.append(header)
        item = dict(profile)
        probe_state = self.container.profile_probe_states.get(profile_id, {})
        item.update({
            "extra_headers": public_headers,
            "credential_loaded": item.get("auth_mode") == "none" or bool(vault.get("api_key")),
            "connected": profile_id == self.container.connected_profile_id and self.container.agent is not None,
            "needs_reconnect": profile_id in self.container.profiles_needing_reconnect,
            "probe_status": probe_state.get("status", "not_tested"),
            "probe_error_category": probe_state.get("error_category", ""),
            "last_probe_at": probe_state.get("at", ""),
        })
        return ProviderProfile.model_validate(item).model_dump()

    @staticmethod
    def redacted_error(exc: Exception, secrets: list[str] | None = None) -> str:
        text = str(exc)
        for secret in secrets or []:
            if secret:
                text = text.replace(secret, "[redacted]")
        text = re.sub(
            r"(?i)(api[-_ ]?key|authorization|x-api-key)\s*[:=]\s*[^\s,}]+",
            r"\1=[redacted]", text,
        )
        return f"{type(exc).__name__}: {text[:500]}"

    @staticmethod
    def error_category(exc: Exception) -> str:
        text = str(exc).lower()
        if any(token in text for token in ("401", "403", "unauthor", "forbidden", "api key", "authentication")):
            return "authentication"
        if any(token in text for token in ("404", "model_not_found", "unknown model", "does not exist")):
            return "model"
        if any(token in text for token in (
            "connect", "dns", "name or service", "无法解析", "timeout",
            "timed out", "ssl", "certificate",
        )):
            return "address"
        if any(token in text for token in ("tool", "structured", "schema", "capabil")):
            return "capability"
        if any(token in text for token in ("400", "422", "protocol", "invalid request", "unsupported")):
            return "protocol"
        return "provider"

    def record_probe_state(self, profile_id: str, status: str, **values) -> None:
        self.container.profile_probe_states[profile_id] = {
            "status": status, "at": datetime.now().astimezone().isoformat(), **values,
        }

    def ensure_mutation_allowed(self) -> None:
        if self.container.active_generation_turns:
            raise ProviderBusyError(
                "Agent 正在生成回答，完成或取消当前轮次后才能切换、编辑、删除或断开供应商"
            )

    def merged_credentials(self, profile: dict, supplied: ProviderCredentials | None) -> dict:
        cached = dict(self.container.credential_vault.get(profile["id"], {}))
        configured_names = {
            header["name"].lower(): header["name"]
            for header in profile.get("extra_headers", []) if header.get("sensitive")
        }
        cached_headers = {
            configured_names.get(name.lower(), name): value
            for name, value in cached.get("sensitive_headers", {}).items()
            if name.lower() in configured_names
        }
        if supplied:
            if supplied.api_key:
                cached["api_key"] = supplied.api_key
            cached_headers.update({
                configured_names.get(name.lower(), name): value
                for name, value in supplied.sensitive_headers.items()
                if value and name.lower() in configured_names
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

    @staticmethod
    def request_headers(profile: dict, credentials: dict) -> tuple[dict[str, str], str]:
        headers: dict[str, str] = {}
        secret_headers = credentials.get("sensitive_headers", {})
        for header in profile.get("extra_headers", []):
            value = secret_headers.get(header["name"], "") if header.get("sensitive") else header.get("value", "")
            if value:
                headers[header["name"]] = value
        key = credentials.get("api_key", "")
        auth_mode = profile["auth_mode"]
        sdk_key = key
        if auth_mode == "bearer":
            name, prefix = profile.get("auth_header_name") or "Authorization", profile.get("auth_prefix", "Bearer ")
            headers.setdefault(name, f"{prefix}{key}")
            if name.lower() != "authorization" or prefix != "Bearer ":
                sdk_key = "patentagent-custom-auth"
        elif auth_mode == "x_api_key":
            headers.setdefault(profile.get("auth_header_name") or "x-api-key", key)
            if profile["protocol"] != "anthropic_messages":
                sdk_key = "patentagent-custom-auth"
        elif auth_mode == "custom_header":
            headers[profile["auth_header_name"]] = f"{profile.get('auth_prefix', '')}{key}"
            sdk_key = "patentagent-custom-auth"
        elif auth_mode == "none":
            sdk_key = "patentagent-no-auth"
        return headers, sdk_key

    def build_client(self, profile: dict, credentials: dict) -> LLMClient:
        if not profile.get("base_url") or not profile.get("model"):
            raise ValueError("请求地址和模型 ID 不能为空")
        headers, sdk_key = self.request_headers(profile, credentials)
        return LLMClient(
            provider=PROTOCOL_MAP[profile["protocol"]], api_key=sdk_key,
            base_url=profile["base_url"], model=profile["model"],
            max_retries=profile["max_retries"], timeout_seconds=profile["timeout_seconds"],
            max_output_tokens=profile["max_output_tokens"], temperature=profile.get("temperature"),
            reasoning_effort=profile["reasoning_effort"], thinking_mode=profile["thinking_mode"],
            extra_headers=headers, extra_body=profile.get("extra_body", {}),
        )

    async def close_current(self) -> None:
        client = getattr(self.container.agent, "llm", None) if self.container.agent else None
        self.container.agent = None
        self.container.connected_profile_id = None
        self.container.connected_profile_snapshot = None
        self.container.llm_capabilities = {}
        if client and hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                pass

    async def probe_profile(self, profile: dict, supplied: ProviderCredentials):
        credentials = self.merged_credentials(profile, supplied)
        await assert_safe_provider_target(profile["base_url"])
        client = self.build_client(profile, credentials)
        try:
            probe = await client.probe_detailed()
        except Exception:
            await client.close()
            raise
        return client, probe, credentials

    async def list_profiles(self):
        return {"profiles": [self.public_profile(item) for item in await self.repository.list_profiles()]}

    async def create_profile(self, req: ProviderProfileCreate):
        profile = await self.repository.create_profile(req.model_copy(update={"selected": False}))
        return self.public_profile(profile)

    async def update_profile(self, profile_id: str, req: ProviderProfileUpdate):
        current = await self.repository.get_profile(profile_id)
        if (current.get("selected") or profile_id == self.container.connected_profile_id) and self.container.active_generation_turns:
            self.ensure_mutation_allowed()
        changes = req.model_dump(exclude_unset=True)
        changes.pop("selected", None)
        changed = any(current.get(key) != value for key, value in changes.items())
        profile = await self.repository.update_profile(profile_id, changes)
        if changed and current.get("selected"):
            self.container.profiles_needing_reconnect.add(profile_id)
            self.container.profile_probe_states.pop(profile_id, None)
        if changed and profile_id == self.container.connected_profile_id:
            await self.close_current()
        return self.public_profile(profile)

    async def delete_profile(self, profile_id: str):
        profile = await self.repository.get_profile(profile_id)
        if profile_id == self.container.connected_profile_id or (profile.get("selected") and self.container.agent is not None):
            if self.container.active_generation_turns:
                self.ensure_mutation_allowed()
            raise ProviderInUseError("当前已连接配置不能删除；请先断开连接")
        await self.repository.delete_profile(profile_id)
        self.container.credential_vault.pop(profile_id, None)
        self.container.profiles_needing_reconnect.discard(profile_id)
        self.container.profile_probe_states.pop(profile_id, None)
        return {"status": "deleted", "profile_id": profile_id}

    async def probe(self, profile_id: str, supplied: ProviderCredentials):
        profile = await self.repository.get_profile(profile_id)
        client, probe, credentials = await self.probe_profile(profile, supplied)
        self.container.credential_vault.set(profile_id, credentials)
        await client.close()
        self.record_probe_state(
            profile_id, "passed", latency_ms=probe.get("latency_ms", 0),
            stages=probe.get("stages", {}),
        )
        return {
            "status": "passed", "profile": self.public_profile(profile),
            "model": profile["model"], "latency_ms": probe["latency_ms"],
            "capabilities": probe, "stages": probe["stages"],
        }

    async def discover_models(self, profile_id: str, supplied: ProviderCredentials):
        profile = await self.repository.get_profile(profile_id)
        if not profile.get("base_url"):
            raise ValueError("请求地址不能为空")
        await assert_safe_provider_target(profile["base_url"])
        credentials = self.merged_credentials(profile, supplied)
        headers, _ = self.request_headers(profile, credentials)
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
        self.container.credential_vault.set(profile_id, credentials)
        return {
            "models": models,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "manual_entry_allowed": True,
        }

    async def activate(self, profile_id: str, supplied: ProviderCredentials):
        self.ensure_mutation_allowed()
        profile = await self.repository.get_profile(profile_id)
        new_client, probe, credentials = await self.probe_profile(profile, supplied)
        if not probe.get("tool_roundtrip") or not probe.get("structured_output"):
            await new_client.close()
            raise RuntimeError("模型可聊天，但未通过 PatentAgent 工具与结构化输出能力门禁")
        old_agent = self.container.agent
        new_agent = PatentAgentOrchestrator(
            llm_client=new_client, tool_registry=tool_registry,
            knowledge_base=build_default_knowledge(),
            tool_semaphore=self.container.tool_semaphore,
            queue_wait_timeout=self.container.settings.max_tool_queue_wait_seconds,
        )
        try:
            await self.repository.select_profile(profile_id)
        except Exception:
            await new_client.close()
            raise
        self.container.agent = new_agent
        self.container.credential_vault.set(profile_id, credentials)
        self.container.connected_profile_id = profile_id
        self.container.llm_capabilities = probe
        self.container.profiles_needing_reconnect.discard(profile_id)
        self.record_probe_state(
            profile_id, "passed", latency_ms=probe.get("latency_ms", 0),
            stages=probe.get("stages", {}),
        )
        selected = await self.repository.get_profile(profile_id)
        self.container.connected_profile_snapshot = {
            "id": profile_id, "name": selected["name"],
            "protocol": selected["protocol"], "model": selected["model"],
        }
        if old_agent and getattr(old_agent, "llm", None) is not new_client:
            try:
                await old_agent.llm.close()
            except Exception:
                pass
        return {
            "status": "connected", "profile": self.public_profile(selected),
            "capabilities": probe,
        }

    async def disconnect(self):
        self.ensure_mutation_allowed()
        await self.close_current()
        return {"status": "disconnected"}

    async def configure_legacy(self, provider: str, api_key: str, base_url: str = "", model: str | None = None):
        self.ensure_mutation_allowed()
        if not api_key:
            raise ValueError("API key required.")
        defaults = {
            "Claude": ("anthropic_messages", "https://api.anthropic.com", LLMProvider.CLAUDE, "x_api_key", "x-api-key", ""),
            "OpenAI": ("openai_chat", "https://api.openai.com/v1", LLMProvider.OPENAI, "bearer", "Authorization", "Bearer "),
            "DeepSeek": ("deepseek_chat", "https://api.deepseek.com/v1", LLMProvider.DEEPSEEK, "bearer", "Authorization", "Bearer "),
        }
        if provider not in defaults:
            raise ValueError(f"Unknown provider '{provider}'. Use: Claude, OpenAI, DeepSeek")
        protocol, default_url, llm_provider, auth_mode, header_name, prefix = defaults[provider]
        temporary = ProviderProfileCreate(
            id="legacy", name=provider, protocol=protocol,
            base_url=base_url or default_url,
            model=model or LLMClient.DEFAULT_MODELS[llm_provider],
            auth_mode=auth_mode, auth_header_name=header_name, auth_prefix=prefix,
        ).model_dump()
        await assert_safe_provider_target(temporary["base_url"])
        candidate = self.build_client(temporary, {"api_key": api_key, "sensitive_headers": {}})
        try:
            probe = await candidate.probe_detailed()
            old_agent = self.container.agent
            self.container.agent = PatentAgentOrchestrator(
                llm_client=candidate, tool_registry=tool_registry,
                knowledge_base=build_default_knowledge(),
                tool_semaphore=self.container.tool_semaphore,
                queue_wait_timeout=self.container.settings.max_tool_queue_wait_seconds,
            )
            self.container.connected_profile_id = None
            self.container.connected_profile_snapshot = {
                "id": "legacy", "name": provider, "protocol": protocol,
                "model": probe["model"],
            }
            self.container.llm_capabilities = probe
            if old_agent and getattr(old_agent, "llm", None) is not candidate:
                try:
                    await old_agent.llm.close()
                except Exception:
                    pass
            return {
                "status": "ok", "provider": provider, "model": probe["model"],
                "probe": "passed", "tool_roundtrip": probe.get("tool_roundtrip", False),
                "structured_output": probe.get("structured_output", False),
            }
        except Exception:
            if getattr(self.container.agent, "llm", None) is not candidate:
                await candidate.close()
            raise
