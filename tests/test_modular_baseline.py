import asyncio
import json
import logging
import sqlite3

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from patent_agent.infrastructure.observability import (
    JsonFormatter, RequestGuardMiddleware, TraceMiddleware,
)
from patent_agent.security.provider_urls import assert_safe_provider_target
from patent_mcp.config import MCPServerConfig
from patent_mcp.server import _BearerAuthMiddleware, _is_loopback_bind
from storage.conversation_store import ConversationStore
import server


def test_request_limit_and_trace_header_are_transport_level_guards():
    guarded = FastAPI()

    @guarded.post("/echo")
    async def echo():
        return {"ok": True}

    guarded.add_middleware(RequestGuardMiddleware, max_request_bytes=8)
    guarded.add_middleware(TraceMiddleware)
    async def scenario():
        async with AsyncClient(
            transport=ASGITransport(app=guarded), base_url="http://test",
        ) as client:
            accepted = await client.post(
                "/echo", content=b"12345678", headers={"X-Request-ID": "case-17"},
            )
            rejected = await client.post("/echo", content=b"123456789")
        return accepted, rejected

    accepted, rejected = asyncio.run(scenario())
    assert accepted.status_code == 200
    assert accepted.headers["x-request-id"] == "case-17"
    assert rejected.status_code == 413
    assert rejected.json()["code"] == "request_too_large"


def test_create_app_owns_an_isolated_container(tmp_path, monkeypatch):
    monkeypatch.setenv("PATENT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MCP_INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("PATENTAGENT_SESSION_DB", str(tmp_path / "isolated.db"))
    original_repo = server.app.state.container.conversation_store
    isolated = server.create_app()
    assert isolated.state.container is not server.app.state.container
    async def scenario():
        async with isolated.router.lifespan_context(isolated):
            async with AsyncClient(
                transport=ASGITransport(app=isolated), base_url="http://test",
            ) as client:
                return await client.get(
                    "/api/health", headers={"X-Request-ID": "factory-test"},
                )

    response = asyncio.run(scenario())
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "factory-test"
    assert isolated.state.container.conversation_store is not None
    assert server.app.state.container.conversation_store is original_repo


def test_json_formatter_has_stable_trace_fields_and_does_not_inspect_secrets():
    record = logging.LogRecord("patentagent.test", logging.INFO, __file__, 1, "complete", (), None)
    record.trace_id = "trace-fixed"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["trace_id"] == "trace-fixed"
    assert payload["message"] == "complete"
    assert "api_key" not in payload


def test_provider_dns_rejects_private_and_mixed_answers(monkeypatch):
    def private_answers(*_args, **_kwargs):
        return [(2, 1, 6, "", ("169.254.169.254", 443))]

    monkeypatch.setattr("patent_agent.security.provider_urls.socket.getaddrinfo", private_answers)
    with pytest.raises(ValueError, match="私网"):
        asyncio.run(assert_safe_provider_target("https://provider.example/v1"))

    def mixed_answers(*_args, **_kwargs):
        return [
            (2, 1, 6, "", ("8.8.8.8", 443)),
            (2, 1, 6, "", ("10.0.0.8", 443)),
        ]

    monkeypatch.setattr("patent_agent.security.provider_urls.socket.getaddrinfo", mixed_answers)
    with pytest.raises(ValueError, match="私网"):
        asyncio.run(assert_safe_provider_target("https://provider.example/v1"))
    asyncio.run(assert_safe_provider_target("http://127.0.0.1:11434/v1"))


def test_mcp_http_non_loopback_requires_auth_and_guard_rejects_missing_token():
    assert _is_loopback_bind("127.0.0.1")
    assert _is_loopback_bind("::1")
    assert not _is_loopback_bind("0.0.0.0")
    assert MCPServerConfig(http_host="0.0.0.0").auth_token == ""

    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    async def scenario():
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        guarded = _BearerAuthMiddleware(inner, "secret-token")
        await guarded({"type": "http", "headers": []}, receive, send)
        return messages

    messages = asyncio.run(scenario())
    assert messages[0]["status"] == 401
    assert called is False


def test_conversation_schema_is_idempotent_and_recovers_inflight_tasks(tmp_path):
    async def scenario():
        db_path = tmp_path / "tasks.db"
        store = ConversationStore(db_path)
        await store.initialize()
        await store.initialize()
        session = await store.create_session("recover", "fixture")
        turn_id = await store.start_turn(
            session["id"], "分析", dataset_version_id="version_fixture",
            trace_id="trace-recover",
        )
        await store.update_turn(turn_id, status="synthesizing")
        first_event = await store.append_task_event(turn_id, {"type": "plan", "reasoning_content": "secret"})
        await store.record_execution(
            session["id"], turn_id, "exec-1", "synthetic", {}, "completed",
            {"summary": "evidence"}, provenance={"dataset_version_id": "version_fixture"},
            metrics={"elapsed_ms": 3.5},
        )
        assert await store.mark_inflight_interrupted() == 1
        task = await store.get_turn(turn_id)
        assert task["status"] == "interrupted"
        assert task["dataset_version_id"] == "version_fixture"
        assert task["trace_id"] == "trace-recover"
        assert task["state_version"] >= 2
        events = await store.list_task_events(turn_id, first_event - 1)
        assert events[0]["payload"]["type"] == "plan"
        assert "reasoning_content" not in events[0]["payload"]
        detail = await store.get_session_detail(session["id"])
        assert detail["tool_executions"][0]["provenance"]["dataset_version_id"] == "version_fixture"
        assert detail["tool_executions"][0]["metrics"]["elapsed_ms"] == 3.5

        with sqlite3.connect(db_path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = db.execute("PRAGMA user_version").fetchone()[0]
        assert {"datasets", "dataset_versions", "imports", "approvals", "reports", "task_events"} <= tables
        assert version == ConversationStore.SCHEMA_VERSION

    asyncio.run(scenario())
