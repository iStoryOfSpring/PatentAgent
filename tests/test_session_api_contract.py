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
        monkeypatch.setattr(server, "_conversation_store", repo)
        monkeypatch.setattr(server, "_store", _store())
        monkeypatch.setattr(server, "_agent", _BrokenAfterStepAgent())

        response = await server.agent_chat(ChatRequest(
            message="test", session_id="contract-session",
        ))
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        events = [
            json.loads(block.removeprefix("data: "))
            for block in "".join(chunks).strip().split("\n\n") if block
        ]
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
        monkeypatch.setattr(server, "_conversation_store", repo)
        monkeypatch.setattr(server, "_store", _store())
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
        monkeypatch.setattr(server, "_conversation_store", repo)
        monkeypatch.setattr(server, "_store", _store())
        monkeypatch.setattr(server, "_agent", _RawJsonFinalAgent())

        response = await server.agent_chat(ChatRequest(
            message="最近三年", session_id="raw-session",
        ))
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        events = [
            json.loads(block.removeprefix("data: "))
            for block in "".join(chunks).strip().split("\n\n") if block
        ]
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
        monkeypatch.setattr(server, "_conversation_store", repo)
        monkeypatch.setattr(server, "_store", _store())
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
