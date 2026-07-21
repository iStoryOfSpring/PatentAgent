import asyncio
import sqlite3
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
    assert _profile(auth_prefix="Bearer ").auth_prefix == "Bearer "
    with pytest.raises(ValidationError, match="HTTP 客户端管理"):
        _profile(extra_headers=[ProviderHeader(name="Content-Length", value="9")])
    with pytest.raises(ValidationError, match="换行符"):
        ProviderCredentials(api_key="secret\r\ninjected")


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


def test_profile_store_migrates_an_early_partial_table_idempotently(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE provider_profiles ("
            "id TEXT PRIMARY KEY,name TEXT NOT NULL,protocol TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO provider_profiles(id,name,protocol) VALUES(?,?,?)",
            ("legacy", "Legacy", "openai_chat"),
        )

    async def scenario():
        store = ProviderProfileStore(db_path)
        await store.initialize()
        await store.initialize()
        restored = await store.get_profile("legacy")
        assert restored["timeout_seconds"] == 60
        assert restored["extra_body"] == {}
        with sqlite3.connect(db_path) as db:
            version = db.execute(
                "SELECT schema_version FROM provider_schema_meta WHERE singleton=1"
            ).fetchone()[0]
        assert version == ProviderProfileStore.SCHEMA_VERSION

    asyncio.run(scenario())


def test_public_profile_never_returns_sensitive_values(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server.app.state.container, "provider_store", store)
        server.app.state.container.credential_vault.clear()
        created = await server.create_llm_profile(_profile(
            extra_headers=[ProviderHeader(
                name="X-Private", value="SENSITIVE_HEADER_991", sensitive=True,
            )],
        ))
        assert created["extra_headers"][0]["value"] == ""
        profile_id = created["id"]
        server.app.state.container.credential_vault.set(profile_id, {
            "api_key": "API_SECRET_991",
            "sensitive_headers": {"X-Private": "SENSITIVE_HEADER_991"},
        })
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
        monkeypatch.setattr(server.app.state.container, "provider_store", store)
        server.app.state.container.credential_vault.clear()
        server.app.state.container.profiles_needing_reconnect.clear()
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
        assert server.app.state.container.agent.llm is fake
        assert result["profile"]["protocol"] == "deepseek_chat"

        active_agent = server.app.state.container.agent

        async def failed_probe(*_args):
            raise RuntimeError("authentication failed")

        monkeypatch.setattr(server, "_probe_profile", failed_probe)
        with pytest.raises(server.HTTPException) as caught:
            await server.activate_llm_profile(
                profile["id"], server.ProviderSecretRequest(api_key="wrong"),
            )
        assert caught.value.status_code == 502
        assert server.app.state.container.agent is active_agent

    asyncio.run(scenario())


def test_edit_connected_profile_disconnects_and_requires_reconnect(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server.app.state.container, "provider_store", store)
        profile = await store.create_profile(_profile(selected=True))

        class FakeClient:
            closed = False
            async def close(self):
                self.closed = True

        client = FakeClient()
        server.app.state.container.agent = type("Agent", (), {"llm": client})()
        server.app.state.container.connected_profile_id = profile["id"]
        server.app.state.container.connected_profile_snapshot = {
            "id": profile["id"], "name": profile["name"],
            "protocol": profile["protocol"], "model": profile["model"],
        }
        updated = await server.update_llm_profile(
            profile["id"], ProviderProfileUpdate(notes="changed"),
        )
        assert updated["needs_reconnect"] is True
        assert server.app.state.container.agent is None
        assert client.closed is True

    asyncio.run(scenario())


def test_selection_is_activation_only_and_selected_profile_can_be_deleted_after_disconnect(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server.app.state.container, "provider_store", store)
        server.app.state.container.active_generation_turns.clear()
        server.app.state.container.connected_profile_id = None
        server.app.state.container.agent = None
        created = await server.create_llm_profile(_profile(selected=True))
        assert created["selected"] is False
        selected = await store.create_profile(_profile(name="Selected", selected=True))
        result = await server.delete_llm_profile(selected["id"])
        assert result["status"] == "deleted"
        assert await store.selected_profile() is None

    asyncio.run(scenario())


def test_provider_mutation_is_blocked_while_answer_is_generating(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server.app.state.container, "provider_store", store)
        profile = await store.create_profile(_profile(selected=True))
        server.app.state.container.active_generation_turns.add("turn_in_progress")
        server.app.state.container.connected_profile_id = profile["id"]
        server.app.state.container.agent = object()
        try:
            with pytest.raises(server.HTTPException) as caught:
                await server.update_llm_profile(
                    profile["id"], ProviderProfileUpdate(notes="unsafe switch"),
                )
            assert caught.value.status_code == 409
            with pytest.raises(server.HTTPException) as caught:
                await server.disconnect_llm()
            assert caught.value.status_code == 409
        finally:
            server.app.state.container.active_generation_turns.clear()
            server.app.state.container.connected_profile_id = None
            server.app.state.container.agent = None

    asyncio.run(scenario())


def test_probe_failure_is_categorized_redacted_and_exposed_as_runtime_status(tmp_path, monkeypatch):
    async def scenario():
        store = ProviderProfileStore(tmp_path / "sessions.db")
        await store.initialize()
        monkeypatch.setattr(server.app.state.container, "provider_store", store)
        server.app.state.container.profile_probe_states.clear()
        profile = await store.create_profile(_profile())
        secret = "PROBE_SECRET_7281"

        async def failed_probe(*_args):
            raise RuntimeError(f"401 Authorization: Bearer {secret}")

        monkeypatch.setattr(server, "_probe_profile", failed_probe)
        with pytest.raises(server.HTTPException) as caught:
            await server.probe_llm_profile(
                profile["id"], server.ProviderSecretRequest(api_key=secret),
            )
        assert caught.value.status_code == 502
        assert secret not in str(caught.value.detail)
        assert caught.value.detail["category"] == "authentication"
        listed = await server.list_llm_profiles()
        public = listed["profiles"][0]
        assert public["probe_status"] == "failed"
        assert public["probe_error_category"] == "authentication"

    asyncio.run(scenario())
