import asyncio
import json

import pandas as pd

import server
from server import ChatRequest, ToolRequest
from storage.conversation_store import ConversationStore
from storage.datastore import PatentDataStore


def _store():
    return PatentDataStore(pd.DataFrame({
        "patent_number": ["US1"],
        "title": ["Example"],
        "abstract": ["Example patent abstract"],
        "year": [2024],
        "month": [1],
        "country": ["US"],
        "ipc": ["H01M"],
        "applicants": ["Example Corp"],
    }))


def _decode_sse(chunks: list[str]) -> list[dict]:
    events = []
    for block in "".join(chunks).strip().split("\n\n"):
        data_line = next(
            (line for line in block.splitlines() if line.startswith("data: ")),
            "",
        )
        if data_line:
            events.append(json.loads(data_line[6:]))
    return events


def test_sse_text_chunking_preserves_markdown_exactly():
    text = "## 核心结论\n\n最近三年 技术路线 逐步演进。\n\n## 数据限制\n\n- 引证不足"
    assert "".join(server._chunk_text(text, 3)) == text


class _BrokenAfterStepAgent:
    async def stream_query(self, *_args, **kwargs):
        turn_id = kwargs["turn_id"]
        yield {"type": "intent", "goal": "test", "analysis_type": "general", "turn_id": turn_id}
        yield {"type": "plan", "steps": [], "chain_id": "", "turn_id": turn_id}
        yield {
            "type": "step", "tool": "synthetic", "status": "completed",
            "duration_ms": 1, "parameters": {}, "chart_html": None,
            "result": {"result_type": "synthetic", "summary": "已完成事实 7",
                       "methodology": "test", "data_quality": {}, "warnings": [],
                       "result_metadata": {"algorithm_version": "1"}},
            "summary": "已完成事实 7", "methodology": "test",
            "data_quality": {}, "warnings": [], "error": None,
            "execution_id": "exec-contract", "origin": "agent",
            "reused_from_execution_id": None, "turn_id": turn_id,
        }
        raise RuntimeError("post-tool synthesis failure")


class _RawJsonFinalAgent:
    async def stream_query(self, *_args, **kwargs):
        turn_id = kwargs["turn_id"]
        raw = json.dumps({
            "answer": "最近三年技术路线逐步演进。",
            "details": [{"year": 2022, "theme": "碳封存"}],
            "methodology": "年度主题统计。",
            "limitations": ["引证覆盖不足。"],
            "follow_up_questions": ["是否查看代表专利？"],
        }, ensure_ascii=False)
        yield {
            "type": "final", "text": raw, "turn_id": turn_id,
            "final_status": "completed", "followup_questions": [],
            "followup_suggestions": [], "evidence_refs": [],
        }
        yield {
            "type": "done", "session_id": "raw-session", "turn_id": turn_id,
            "final_status": "completed", "answer_present": True,
            "result_coverage": [], "coverage_complete": True,
            "new_execution_ids": [], "reused_execution_ids": [],
        }


def test_server_stream_converts_post_tool_failure_to_text_and_done(tmp_path, monkeypatch):
    async def scenario():
        repo = ConversationStore(tmp_path / "sessions.db")
        await repo.initialize()
        monkeypatch.setattr(server.app.state.container, "conversation_store", repo)
        monkeypatch.setattr(server.app.state.container, "store", _store())
        monkeypatch.setattr(server.app.state.container, "agent", _BrokenAfterStepAgent())

        response = await server.agent_chat(ChatRequest(
            message="test", session_id="contract-session",
        ))
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        events = _decode_sse(chunks)
        assert len([event for event in events if event["type"] == "done"]) == 1
        assert any(event["type"] == "text" and "已完成事实 7" in event["content"] for event in events)
        done = next(event for event in events if event["type"] == "done")
        assert done["answer_present"] is True
        assert done["final_status"] == "partial"

    asyncio.run(scenario())


def test_quick_tool_result_is_attached_to_session_without_chart_html(tmp_path, monkeypatch):
    async def scenario():
        repo = ConversationStore(tmp_path / "sessions.db")
        await repo.initialize()
        monkeypatch.setattr(server.app.state.container, "conversation_store", repo)
        monkeypatch.setattr(server.app.state.container, "store", _store())
        await repo.create_session("quick", server._dataset_fingerprint(), "quick-session")
        payload = await server.run_tool(
            "get_dataset_summary",
            ToolRequest(params={}, session_id="quick-session"),
        )
        assert payload["result_metadata"]["origin"] == "quick_tool"
        detail = await repo.get_session_detail("quick-session")
        assert detail["turns"][0]["origin"] == "quick_tool"
        result = detail["tool_executions"][0]["result"]
        assert result["result_type"] == "dataset_summary"
        assert "chart_html" not in result

    asyncio.run(scenario())


def test_sse_boundary_never_streams_raw_json_and_preserves_followups(tmp_path, monkeypatch):
    async def scenario():
        repo = ConversationStore(tmp_path / "sessions.db")
        await repo.initialize()
        monkeypatch.setattr(server.app.state.container, "conversation_store", repo)
        monkeypatch.setattr(server.app.state.container, "store", _store())
        monkeypatch.setattr(server.app.state.container, "agent", _RawJsonFinalAgent())

        response = await server.agent_chat(ChatRequest(
            message="最近三年", session_id="raw-session",
        ))
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        events = _decode_sse(chunks)
        visible = "".join(
            event["content"] for event in events if event["type"] == "text"
        )
        assert "## 核心结论" in visible
        assert '"answer"' not in visible
        done = next(event for event in events if event["type"] == "done")
        assert done["answer_present"] is True
        assert done["answer_format"] == "markdown"
        assert done["normalization_mode"] == "local_repair"
        assert done["followup_questions"] == ["是否查看代表专利？"]

    asyncio.run(scenario())


def test_history_json_is_repaired_for_display_without_rewriting_database(tmp_path, monkeypatch):
    async def scenario():
        repo = ConversationStore(tmp_path / "sessions.db")
        await repo.initialize()
        monkeypatch.setattr(server.app.state.container, "conversation_store", repo)
        monkeypatch.setattr(server.app.state.container, "store", _store())
        session = await repo.create_session("legacy", server._dataset_fingerprint(), "legacy")
        turn_id = await repo.start_turn(session["id"], "最近三年")
        raw = json.dumps({
            "answer": "历史结论。",
            "limitations": ["历史限制。"],
            "follow_up_questions": ["继续分析吗？"],
        }, ensure_ascii=False)
        await repo.finish_turn(session["id"], turn_id, raw, metadata={
            "followup_questions": ["旧的兜底追问"],
            "followup_suggestions": [{
                "text": "旧的兜底追问", "kind": "explain",
                "requires_new_tools": False, "evidence_ref": None,
            }],
        })

        detail = await server.get_session(session["id"])
        assert detail["messages"][-1]["content"].startswith("## 核心结论")
        assert detail["messages"][-1]["metadata"]["followup_questions"] == ["继续分析吗？"]
        stored = await repo.get_session_detail(session["id"])
        assert stored["messages"][-1]["content"] == raw
        assert stored["messages"][-1]["metadata"]["followup_questions"] == ["旧的兜底追问"]

    asyncio.run(scenario())


def test_dataset_and_task_apis_replay_stable_events_and_cancel(tmp_path, monkeypatch):
    async def scenario():
        repo = ConversationStore(tmp_path / "tasks.db")
        await repo.initialize()
        store = _store()
        monkeypatch.setattr(server.app.state.container, "conversation_store", repo)
        monkeypatch.setattr(server.app.state.container, "store", store)
        await repo.upsert_dataset_snapshot(store.snapshot().model_dump(mode="json"))

        datasets = await server.list_datasets()
        assert datasets["datasets"][0]["latest_version"]["content_hash"] == store.dataset_fingerprint()
        versions = await server.list_dataset_versions(store.snapshot().dataset_id)
        assert versions["versions"][0]["id"] == store.snapshot().version_id

        session = await repo.create_session("task", store.dataset_fingerprint())
        turn_id = await repo.start_turn(session["id"], "执行", trace_id="trace-task")
        event_id = await repo.append_task_event(turn_id, {"type": "plan", "steps": []})
        await repo.finish_turn(session["id"], turn_id, "完成", "completed")
        task = await server.get_task(turn_id)
        assert task["task"]["trace_id"] == "trace-task"

        replay = await server.get_task_events(turn_id, last_event_id="0")
        chunks = []
        async for chunk in replay.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        wire = "".join(chunks)
        assert f"id: {event_id}" in wire
        assert '"type": "plan"' in wire

        cancellable = await repo.start_turn(session["id"], "取消")
        cancelled = await server.cancel_task(cancellable)
        assert cancelled["task"]["cancel_requested"] == 1

    asyncio.run(scenario())
