import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

import server
from models.provider_profile import (
    ProviderCredentials, ProviderHeader, ProviderProfileCreate,
    ProviderProfileUpdate,
)
from storage.provider_store import ProviderProfileStore


def _profile(**overrides):
    values = {
        "name": "Campus Gateway",
        "protocol": "openai_chat",
        "website_url": "https://example.edu/provider",
        "base_url": "https://llm.example.edu/v1/",
        "model": "campus-tool-model",
        "auth_mode": "bearer",
        "extra_headers": [],
    }
    values.update(overrides)
    return ProviderProfileCreate(**values)


def test_provider_profile_validates_urls_and_reserved_body_fields():
    assert _profile().base_url == "https://llm.example.edu/v1"
    assert _profile(base_url="http://localhost:11434/v1", auth_mode="none").base_url.startswith("http://")
    with pytest.raises(ValidationError, match="远程请求地址必须使用 HTTPS"):
        _profile(base_url="http://llm.example.edu/v1")
    with pytest.raises(ValidationError, match="用户名或密码"):
        _profile(base_url="https://user:secret@llm.example.edu/v1")
    with pytest.raises(ValidationError, match="保留字段"):
        _profile(extra_body={"messages": []})
    with pytest.raises(ValidationError, match="Thinking mode"):
        _profile(thinking_mode="enabled")


def test_profile_store_crud_migration_and_secret_bytes(tmp_path):
    async def scenario():
        db_path = tmp_path / "sessions.db"
        store = ProviderProfileStore(db_path)
        await store.initialize()
        await store.initialize()
        created = await store.create_profile(_profile(
            selected=True,
            extra_headers=[ProviderHeader(
                name="X-Campus-Secret", value="DO_NOT_PERSIST_7281", sensitive=True,
            )],
        ))
        assert created["selected"] is True
        assert created["extra_headers"][0]["value"] == ""
        updated = await store.update_profile(created["id"], {
            "name": "Renamed Gateway", "timeout_seconds": 90,
        })
        assert updated["name"] == "Renamed Gateway"
        assert updated["timeout_seconds"] == 90
        reopened = ProviderProfileStore(db_path)
        await reopened.initialize()
        restored = await reopened.get_profile(created["id"])
        assert restored["name"] == "Renamed Gateway"
        for path in tmp_path.iterdir():
            if path.is_file():
                assert b"DO_NOT_PERSIST_7281" not in path.read_bytes()

    asyncio.run(scenario())


def test_public_profile_never_returns_sensitive_values(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server, "_provider_store", store)
        server._credential_vault.clear()
        created = await server.create_llm_profile(_profile(
            extra_headers=[ProviderHeader(
                name="X-Private", value="SENSITIVE_HEADER_991", sensitive=True,
            )],
        ))
        assert created["extra_headers"][0]["value"] == ""
        profile_id = created["id"]
        server._credential_vault[profile_id] = {
            "api_key": "API_SECRET_991",
            "sensitive_headers": {"X-Private": "SENSITIVE_HEADER_991"},
        }
        listed = await server.list_llm_profiles()
        encoded = str(listed)
        assert "API_SECRET_991" not in encoded
        assert "SENSITIVE_HEADER_991" not in encoded
        public = listed["profiles"][0]
        assert public["credential_loaded"] is True
        assert public["extra_headers"][0]["credential_loaded"] is True

    asyncio.run(scenario())


def test_activation_uses_protocol_not_display_name_and_failure_preserves_agent(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server, "_provider_store", store)
        server._credential_vault.clear()
        server._profiles_needing_reconnect.clear()
        profile = await store.create_profile(_profile(
            name="任意中文品牌名", protocol="deepseek_chat",
            base_url="https://api.deepseek.com/v1", model="deepseek-v4-flash",
        ))

        class FakeClient:
            closed = False
            async def close(self):
                self.closed = True

        fake = FakeClient()

        async def successful_probe(actual, credentials):
            assert actual["name"] == "任意中文品牌名"
            assert actual["protocol"] == "deepseek_chat"
            assert credentials.api_key == "runtime-only"
            return fake, {
                "model": actual["model"], "latency_ms": 12,
                "tool_roundtrip": True, "structured_output": True,
                "stages": {"text": {"status": "passed"}},
            }, {"api_key": credentials.api_key, "sensitive_headers": {}}

        monkeypatch.setattr(server, "_probe_profile", successful_probe)
        result = await server.activate_llm_profile(
            profile["id"], server.ProviderSecretRequest(api_key="runtime-only"),
        )
        assert result["status"] == "connected"
        assert server._agent.llm is fake
        assert result["profile"]["protocol"] == "deepseek_chat"

        active_agent = server._agent

        async def failed_probe(*_args):
            raise RuntimeError("authentication failed")

        monkeypatch.setattr(server, "_probe_profile", failed_probe)
        with pytest.raises(server.HTTPException) as caught:
            await server.activate_llm_profile(
                profile["id"], server.ProviderSecretRequest(api_key="wrong"),
            )
        assert caught.value.status_code == 502
        assert server._agent is active_agent

    asyncio.run(scenario())


def test_edit_connected_profile_disconnects_and_requires_reconnect(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server, "_provider_store", store)
        profile = await store.create_profile(_profile(selected=True))

        class FakeClient:
            closed = False
            async def close(self):
                self.closed = True

        client = FakeClient()
        server._agent = type("Agent", (), {"llm": client})()
        server._connected_profile_id = profile["id"]
        server._connected_profile_snapshot = {
            "id": profile["id"], "name": profile["name"],
            "protocol": profile["protocol"], "model": profile["model"],
        }
        updated = await server.update_llm_profile(
            profile["id"], ProviderProfileUpdate(notes="changed"),
        )
        assert updated["needs_reconnect"] is True
        assert server._agent is None
        assert client.closed is True

    asyncio.run(scenario())

