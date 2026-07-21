import asyncio
from datetime import datetime

import pytest

from agent.llm import ChatResponse, LLMClient, LLMProvider
from agent.orchestrator import AnalysisPlan, IntentAnalysis, PatentAgentOrchestrator
from models.analysis_results import GenericAnalysisResult
from models.session import Session, ToolExecution
from storage.conversation_store import ConversationStore, execution_cache_key
from storage.datastore import PatentDataStore
from tools.base import ToolRegistry


def test_conversation_store_survives_reopen_and_excludes_chart_html(tmp_path):
    async def scenario():
        db_path = tmp_path / "sessions.db"
        store = ConversationStore(db_path)
        await store.initialize()
        session = await store.create_session("审查", "dataset-a")
        turn_id = await store.start_turn(session["id"], "分析趋势")
        await store.record_execution(
            session["id"], turn_id, "exec-1", "analyze_patent_trend", {},
            "completed", {
                "result_type": "monthly_trend",
                "summary": "趋势完成",
                "chart_html": "<script>should-not-persist</script>",
            }, dataset_fingerprint="dataset-a",
        )
        await store.finish_turn(session["id"], turn_id, "完整总结")

        reopened = ConversationStore(db_path)
        await reopened.initialize()
        detail = await reopened.get_session_detail(session["id"])
        assert detail["messages"][-1]["content"] == "完整总结"
        assert detail["tool_executions"][0]["result"]["summary"] == "趋势完成"
        assert "chart_html" not in detail["tool_executions"][0]["result"]
        assert b"should-not-persist" not in db_path.read_bytes()

    asyncio.run(scenario())


def test_dataset_change_marks_previous_evidence_stale(tmp_path):
    async def scenario():
        store = ConversationStore(tmp_path / "sessions.db")
        await store.initialize()
        session = await store.create_session("测试", "dataset-a")
        turn_id = await store.start_turn(session["id"], "总览")
        await store.record_execution(
            session["id"], turn_id, "exec-1", "get_dataset_summary", {},
            "completed", {"result_type": "dataset_summary", "summary": "旧数据"},
            dataset_fingerprint="dataset-a",
        )
        await store.ensure_session(session["id"], "dataset-b")
        assert await store.get_evidence(session["id"]) == []
        stale = await store.get_evidence(session["id"], include_stale=True)
        assert stale[0]["stale"] is True

    asyncio.run(scenario())


def test_execution_cache_key_is_parameter_order_independent():
    first = execution_cache_key("d", "tool", {"b": 2, "a": 1}, "1")
    second = execution_cache_key("d", "tool", {"a": 1, "b": 2}, "1")
    assert first == second


class _FailingLLM:
    async def chat(self, *_args, **_kwargs):
        raise RuntimeError("provider unavailable")


class _FailingSynthesisOrchestrator(PatentAgentOrchestrator):
    async def _understand_intent(self, message, history=None):
        return IntentAnalysis(goal=message, analysis_type="general")

    async def _plan_analysis(self, intent, storage, user_message=""):
        return AnalysisPlan(steps=[], chain_id="")

    async def _execute_plan(self, plan, storage, reuse_lookup=None, on_execution=None):
        execution = ToolExecution(
            id="exec-1", tool_name="synthetic_tool", parameters={},
            status="completed", result=GenericAnalysisResult(
                result_type="synthetic", summary="唯一事实 42",
                warnings=["样本有限"],
            ),
        )
        if on_execution:
            await on_execution(execution)
        return [execution]

    async def _synthesize(self, plan, executions, response_mode="detailed"):
        raise RuntimeError("synthesis crashed")


def test_stream_always_finishes_with_fallback_after_synthesis_failure():
    async def scenario():
        orchestrator = _FailingSynthesisOrchestrator(
            _FailingLLM(), ToolRegistry(), {},
        )
        orchestrator.enable_strategic_mode = False
        session = Session(
            id="s", name="test", created_at=datetime.now(), dataset_id="d",
        )
        events = [event async for event in orchestrator.stream_query(
            "执行分析", session, PatentDataStore(), turn_id="turn-1",
        )]
        done = [event for event in events if event["type"] == "done"]
        final = [event for event in events if event["type"] == "final"]
        assert len(done) == 1
        assert done[0]["answer_present"] is True
        assert done[0]["final_status"] == "partial"
        assert "唯一事实 42" in final[0]["text"]
        assert "数据限制" in final[0]["text"]

    asyncio.run(scenario())


class _ApprovalOrchestrator(_FailingSynthesisOrchestrator):
    async def _plan_analysis(self, intent, storage, user_message=""):
        return AnalysisPlan(steps=[], chain_id="", requires_confirmation=True)

    async def _execute_plan(self, plan, storage, reuse_lookup=None, on_execution=None):
        return []

    async def _synthesize(self, plan, executions, response_mode="detailed"):
        return "审批后完成。"


def test_persisted_approval_bypasses_repeated_budget_prompt():
    async def scenario():
        orchestrator = _ApprovalOrchestrator(_FailingLLM(), ToolRegistry(), {})
        orchestrator.enable_strategic_mode = False
        session = Session(id="s", name="test", created_at=datetime.now(), dataset_id="d")
        events = [event async for event in orchestrator.stream_query(
            "执行完整分析", session, PatentDataStore(), turn_id="approved-turn",
            approval_granted=True,
        )]
        plan = next(event for event in events if event["type"] == "plan")
        assert plan["requires_confirmation"] is False
        assert not [event for event in events if event["type"] == "clarification"]
        assert next(event for event in events if event["type"] == "done")["final_status"] == "completed"

    asyncio.run(scenario())


class _HistoryLLM:
    async def chat(self, messages, **_kwargs):
        assert "历史工具证据" in messages[0]["content"]
        return ChatResponse("峰值来自已保存数据。[历史轮次:analyze_patent_trend:data]")


def test_explanatory_followup_reuses_history_without_tool_steps():
    async def scenario():
        orchestrator = PatentAgentOrchestrator(_HistoryLLM(), ToolRegistry(), {})
        session = Session(
            id="s", name="test", created_at=datetime.now(), dataset_id="d",
        )
        evidence = [{
            "id": "old-exec", "turn_id": "old-turn",
            "tool_name": "analyze_patent_trend",
            "result": {"result_type": "monthly_trend", "summary": "峰值 42"},
        }]
        events = [event async for event in orchestrator.stream_query(
            "为什么这个图有峰值？", session, PatentDataStore(),
            historical_evidence=evidence, turn_id="turn-2",
        )]
        assert not [event for event in events if event["type"] == "step"]
        done = next(event for event in events if event["type"] == "done")
        assert done["reused_execution_ids"] == ["old-exec"]
        assert done["new_execution_ids"] == []

    asyncio.run(scenario())


def test_llm_client_rejects_empty_provider_response():
    async def scenario():
        client = object.__new__(LLMClient)
        client.provider = LLMProvider.OPENAI
        client.max_retries = 0

        async def empty(*_args, **_kwargs):
            return ChatResponse("")

        client._openai_chat = empty
        with pytest.raises(RuntimeError, match="LLM_PROVIDER_ERROR"):
            await client.chat([{"role": "user", "content": "hello"}])

    asyncio.run(scenario())
