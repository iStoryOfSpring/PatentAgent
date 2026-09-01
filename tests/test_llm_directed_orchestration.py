import asyncio
import json

import pandas as pd

from agent.llm import ChatResponse
from agent.orchestrator import PatentAgentOrchestrator
from models.session import Session
from storage.datastore import PatentDataStore
from tools.base import ToolRegistry
from tools.trend_tool import TrendTool


class _ToolSelectingLLM:
    def __init__(self):
        self.planning_calls = 0
        self.roundtrips = 0

    async def chat(self, messages, tools=None, **_kwargs):
        if tools:
            self.planning_calls += 1
            names = {item["name"] for item in tools}
            assert "analyze_patent_trend" in names
            return ChatResponse(
                tool_calls=[{
                    "id": "provider-call-1", "name": "analyze_patent_trend",
                    "arguments": {"chart_type": "yearly"}, "parse_error": "",
                }],
                raw_assistant_message={
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "provider-call-1", "type": "function",
                        "function": {
                            "name": "analyze_patent_trend",
                            "arguments": '{"chart_type":"yearly"}',
                        },
                    }],
                },
            )
        raise AssertionError("Unexpected free-form LLM call")

    async def continue_with_tool_results(
        self, _messages, _assistant, tool_results, _tools,
        _instruction, response_schema=None, **_kwargs,
    ):
        self.roundtrips += 1
        assert response_schema["properties"]["answer_markdown"]
        assert len(tool_results) == 1
        payload = tool_results[0]["payload"]
        assert payload["tool_name"] == "analyze_patent_trend"
        assert "yearly" in payload["summary"]
        summary_ref = payload["evidence_uri_root"] + "summary"
        return ChatResponse(json.dumps({
            "answer_markdown": "仅回答年度公开趋势。数据限制：只表示公开量。",
            "evidence_refs": [summary_ref],
            "followup_suggestions": [{
                "text": "2021 年公开量变化由哪些申请人贡献？",
                "kind": "new_analysis", "requires_new_tools": True,
                "evidence_ref": summary_ref,
            }],
        }, ensure_ascii=False))


class _SchemaDriftingLLM(_ToolSelectingLLM):
    async def continue_with_tool_results(
        self, _messages, _assistant, tool_results, _tools,
        instruction, response_schema=None, **_kwargs,
    ):
        self.roundtrips += 1
        assert response_schema["properties"]["answer_markdown"]
        if self.roundtrips == 2:
            assert "Previous invalid output" in instruction
            assert '"answer_markdown"' in instruction
        return ChatResponse(json.dumps({
            "answer": "年度公开量总体上升。",
            "details": [{"year": 2021, "theme": "公开量达到阶段高点"}],
            "trend_summary": "2021 年为观察区间内的高点。",
            "methodology": "基于公开日期年度计数。",
            "limitations": ["公开量不等于申请量。"],
            "follow_up_questions": ["2021 年的变化由哪些申请人贡献？"],
        }, ensure_ascii=False))


def test_normal_flow_executes_only_llm_selected_tool_and_roundtrips_result():
    async def scenario():
        registry = ToolRegistry()
        registry.register(TrendTool())
        llm = _ToolSelectingLLM()
        orchestrator = PatentAgentOrchestrator(llm, registry, {})
        store = PatentDataStore(pd.DataFrame({
            "patent_number": ["CN1", "CN2"],
            "title": ["a", "b"], "abstract": ["a", "b"],
            "publication_date": ["2020-01-01", "2021-01-01"],
            "ipc": ["H01M", "H01M"], "applicants": ["A", "B"],
        }))
        session = Session(
            id="s", name="test", created_at=pd.Timestamp.now().to_pydatetime(),
            dataset_id="d",
        )
        events = [event async for event in orchestrator.stream_query(
            "只分析年度专利公开趋势", session, store, turn_id="turn-1",
        )]
        steps = [event for event in events if event["type"] == "step"]
        assert [event["tool"] for event in steps] == ["analyze_patent_trend"]
        plan = next(event for event in events if event["type"] == "plan")
        assert plan["decision_source"] == "llm"
        assert plan["cost_weight"] == 1
        assert llm.planning_calls == 1
        assert llm.roundtrips == 1
        final = next(event for event in events if event["type"] == "final")
        assert "年度公开趋势" in final["text"]
        assert final["followup_questions"] == ["2021 年公开量变化由哪些申请人贡献？"]

    asyncio.run(scenario())


def test_schema_drift_is_locally_repaired_instead_of_returning_raw_json():
    async def scenario():
        registry = ToolRegistry()
        registry.register(TrendTool())
        llm = _SchemaDriftingLLM()
        orchestrator = PatentAgentOrchestrator(llm, registry, {})
        store = PatentDataStore(pd.DataFrame({
            "patent_number": ["CN1", "CN2"],
            "title": ["a", "b"], "abstract": ["a", "b"],
            "publication_date": ["2020-01-01", "2021-01-01"],
            "ipc": ["H01M", "H01M"], "applicants": ["A", "B"],
        }))
        session = Session(
            id="s", name="test", created_at=pd.Timestamp.now().to_pydatetime(),
            dataset_id="d",
        )
        events = [event async for event in orchestrator.stream_query(
            "分析年度公开趋势", session, store, turn_id="turn-drift",
        )]
        final = next(event for event in events if event["type"] == "final")
        done = next(event for event in events if event["type"] == "done")
        assert llm.roundtrips == 2
        assert final["text"].startswith("## 结构化降级总结")
        assert "### 数据限制" in final["text"]
        assert '"answer"' not in final["text"]
        assert final["normalization_mode"] == "fallback"
        assert done["answer_format"] == "markdown"
        assert done["normalization_mode"] == "fallback"

    asyncio.run(scenario())


def test_followup_similarity_filter_does_not_repeat_previous_suggestion():
    previous = [{
        "role": "assistant", "content": "report",
        "metadata": {"followup_suggestions": [{
            "text": "2021 年公开量变化由哪些申请人贡献？",
        }]},
    }]
    filtered = PatentAgentOrchestrator._filter_followup_suggestions([
        {"text": "2021年公开量变化由哪些申请人贡献？"},
        {"text": "H01M 的年度占比是否持续上升？"},
    ], "继续分析", previous)
    assert [item["text"] for item in filtered] == ["H01M 的年度占比是否持续上升？"]
