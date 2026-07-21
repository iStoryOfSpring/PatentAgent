"""Agent 编排器 — 有限状态机 + 工具编排 + 战略推理

v2.0: 集成了跨工具关联推理、自适应规划和战略建议生成
"""

import json
import asyncio
import time
import logging
import re
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from agent.llm import LLMClient, ChatResponse
from agent.pipeline import (
    AnswerSynthesizer, ExecutionPolicy, IntentParser, Planner,
    ResultValidator, ToolExecutor,
)
from agent.final_answer import (
    normalize_final_answer,
    parse_canonical_final_answer,
)
from agent.prompts import (
    SYSTEM_PROMPT, PLANNING_PROMPT, SYNTHESIS_PROMPT,
    INTENT_UNDERSTANDING_PROMPT, DATA_SELECTION_PROMPT,
    STRATEGY_SYNTHESIS_PROMPT,
)
from models.session import Session, ToolExecution
from models.analysis_results import AnalysisResult, GenericAnalysisResult, StrategyReport
from storage.datastore import PatentDataStore
from tools.base import ToolRegistry

logger = logging.getLogger(__name__)


def _safe_text_chunks(value: str, chunk_size: int) -> list[str]:
    """Split large evidence without cutting an identifier/string token."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    chunks: list[str] = []
    start = 0
    token_char = lambda char: char.isalnum() or char in "_-.:/"
    while start < len(value):
        end = min(start + chunk_size, len(value))
        if end < len(value) and token_char(value[end - 1]) and token_char(value[end]):
            boundary = end
            while boundary > start and token_char(value[boundary - 1]):
                boundary -= 1
            if boundary > start:
                end = boundary
            else:
                boundary = end
                while boundary < len(value) and token_char(value[boundary]):
                    boundary += 1
                end = boundary
        chunks.append(value[start:end])
        start = end
    return chunks or [""]


class AgentState(Enum):
    IDLE = auto()
    UNDERSTANDING = auto()
    PLANNING = auto()
    WAITING_APPROVAL = auto()
    EXECUTING = auto()
    INTERMEDIATE_REVIEW = auto()   # v2.0: 每步执行后评估是否调整计划
    REPLAN = auto()               # v2.0: 动态重规划
    EXECUTION_ERROR = auto()
    SYNTHESIZING = auto()
    DONE = auto()


@dataclass
class IntentAnalysis:
    """意图分析结果"""
    goal: str = ""
    tech_field: Optional[str] = None
    applicants: list[str] = field(default_factory=list)
    ipc_codes: list[str] = field(default_factory=list)
    time_range: Optional[tuple[int, int]] = None
    analysis_type: str = ""


@dataclass
class AnalysisPlan:
    """分析计划"""
    steps: list[dict] = field(default_factory=list)
    estimated_tokens: int = 0
    requires_confirmation: bool = False
    chain_id: str = ""  # v2.0: which analysis chain was selected
    decision_source: str = "llm"
    decision_type: str = "analysis"  # analysis | reuse | clarify | direct
    tool_calls: list[dict] = field(default_factory=list)
    reused_evidence: list[dict] = field(default_factory=list)
    validation_status: str = "valid"
    cost_weight: int = 0
    planner_response: ChatResponse | None = None
    planner_messages: list[dict] = field(default_factory=list)
    direct_answer: str = ""
    clarification: dict | None = None
    final_response_metadata: dict = field(default_factory=dict)


class AgentResponse:
    """Agent 最终响应"""
    def __init__(self, text: str = "", charts: list[str] = None,
                 plan: dict = None, tool_executions: list = None,
                 needs_approval: bool = False, session_status: str = "completed",
                 strategy_report: StrategyReport = None):
        self.text = text
        self.charts = charts or []
        self.plan = plan or {}
        self.tool_executions = tool_executions or []
        self.needs_approval = needs_approval
        self.session_status = session_status
        self.strategy_report = strategy_report  # v2.0: strategic recommendations


class PatentAgentOrchestrator:
    """专利分析 Agent 编排器"""

    def __init__(self,
                 llm_client: LLMClient,
                 tool_registry: ToolRegistry,
                 knowledge_base: dict = None):
        self.llm = llm_client
        self.tools = tool_registry
        self.knowledge = knowledge_base or {}
        self.state = AgentState.IDLE
        self.max_retries = 3
        self.enable_strategic_mode = True  # v2.0: enable cross-tool reasoning
        self.intent_parser = IntentParser()
        self.execution_policy = ExecutionPolicy()
        self.planner = Planner(self._select_tools_with_llm)
        self.tool_executor = ToolExecutor()
        self.result_validator = ResultValidator()
        self.answer_synthesizer = AnswerSynthesizer(self.result_validator)

    # ── 主入口 ──
    async def process_query(self,
                            user_message: str,
                            session: Session,
                            storage: PatentDataStore,
                            response_mode: str = "detailed") -> AgentResponse:
        """Non-streaming facade over the same LLM-directed workflow as SSE."""
        final_text = ""
        final_status = "failed"
        plan_payload: dict[str, Any] = {}
        async for event in self.stream_query(
            user_message, session, storage, response_mode=response_mode,
        ):
            if event["type"] == "plan":
                plan_payload = event
            elif event["type"] == "final":
                final_text = event.get("text", "")
                final_status = event.get("final_status", "completed")
        return AgentResponse(
            text=final_text,
            charts=[
                execution.result.chart_html for execution in session.tool_executions
                if execution.result and execution.result.chart_html
            ],
            plan=plan_payload,
            tool_executions=session.tool_executions,
            needs_approval=final_status == "awaiting_clarification",
            session_status=final_status,
        )

    async def stream_query(self, user_message: str, session: Session,
                           storage: PatentDataStore,
                           response_mode: str = "detailed",
                           historical_evidence: list[dict] | None = None,
                           turn_id: str | None = None,
                           reuse_lookup: Callable[[str, dict, str], Awaitable[ToolExecution | None]] | None = None,
                           approval_granted: bool = False):
        """LLM chooses tools; local code validates/executes; LLM answers round two."""
        turn_id = turn_id or f"turn_{uuid4().hex}"
        historical_evidence = historical_evidence or []
        prior_messages = list(session.messages)
        session.messages.append({
            "role": "user", "content": user_message,
            "created_at": datetime.now().isoformat(),
        })
        session.tool_executions = []
        legacy_mode = False
        try:
            planner_context = self.intent_parser.context(
                user_message, prior_messages, storage, historical_evidence,
            )
            plan = await self.planner.plan(planner_context)
        except Exception:
            # Preserve extension/test subclasses which intentionally override the
            # old planning hooks; production instances never enter fixed chains.
            if type(self)._plan_analysis is PatentAgentOrchestrator._plan_analysis:
                raise
            legacy_mode = True
            intent = await self._understand_intent(user_message, prior_messages)
            plan = await self._plan_analysis(intent, storage, user_message)
            plan.decision_source = "legacy_extension"
            plan.decision_type = "analysis"

        if approval_granted:
            # The approval was already validated and persisted by the
            # application layer. Do not ask the same budget question again.
            plan.requires_confirmation = False

        yield {
            "type": "intent", "goal": user_message,
            "analysis_type": plan.decision_type, "turn_id": turn_id,
        }
        yield {
            "type": "plan", "steps": plan.steps, "chain_id": "",
            "turn_id": turn_id, "decision_source": plan.decision_source,
            "tool_calls": plan.tool_calls,
            "reused_evidence": [item.get("id") for item in plan.reused_evidence],
            "validation_status": plan.validation_status,
            "cost_weight": plan.cost_weight,
            "requires_confirmation": plan.requires_confirmation,
            "provider": getattr(plan.planner_response, "provider", ""),
            "model": getattr(plan.planner_response, "model", ""),
            "request_id": getattr(plan.planner_response, "request_id", ""),
            "usage": getattr(plan.planner_response, "usage", {}),
            "finish_reason": getattr(plan.planner_response, "finish_reason", ""),
        }

        if plan.requires_confirmation:
            question = (
                f"模型选择了 {len(plan.steps)} 个分析工具，总成本权重 "
                f"{plan.cost_weight}，超过自动执行上限（4 个工具/权重 6）。"
                "请回复“确认执行”，或说明希望保留的分析维度。"
            )
            async for event in self._clarification_events(
                session, turn_id, question, ["execution_budget"],
            ):
                yield event
            return

        if plan.decision_type == "clarify":
            clarification = plan.clarification or {}
            async for event in self._clarification_events(
                session, turn_id,
                clarification.get("question", "请补充执行分析所需的关键条件。"),
                clarification.get("missing_fields", []),
                clarification.get("defaults", []),
            ):
                yield event
            return

        if plan.decision_type == "direct":
            text = plan.direct_answer.strip()
            if not text:
                text = "请说明希望分析的专利问题或需要了解的方法。"
            reused_ids = [
                item.get("id") for item in plan.reused_evidence if item.get("id")
            ]
            suggestions = self._filter_followup_suggestions(
                [], user_message, prior_messages,
            )
            session.messages.append({
                "role": "assistant", "content": text,
                "metadata": {"followup_suggestions": suggestions},
                "created_at": datetime.now().isoformat(),
            })
            final_event = self._final_event(text, turn_id, "completed", suggestions)
            final_event["llm_response"] = self._chat_response_metadata(plan.planner_response)
            yield final_event
            yield self._done_event(
                session.id, turn_id, "completed", [], [], reused_ids,
                suggestions,
            )
            return

        executions: list[ToolExecution] = []
        if plan.decision_type == "reuse":
            executions = self._restore_evidence_executions(plan.reused_evidence)
            for execution in executions:
                yield self._execution_event(execution, turn_id)
        else:
            execution_queue: asyncio.Queue[ToolExecution] = asyncio.Queue()

            async def on_execution(execution: ToolExecution) -> None:
                await execution_queue.put(execution)

            # Normal production flow deliberately bypasses adaptive rule expansion.
            execution_task = asyncio.create_task(self.tool_executor.execute(
                plan, storage, modern=self._execute_llm_plan,
                legacy=self._execute_plan, legacy_mode=legacy_mode,
                reuse_lookup=reuse_lookup, on_execution=on_execution,
            ))
            yielded_execution_ids: set[str] = set()
            try:
                while not execution_task.done() or not execution_queue.empty():
                    try:
                        execution = await asyncio.wait_for(
                            execution_queue.get(), timeout=0.1,
                        )
                    except asyncio.TimeoutError:
                        continue
                    yielded_execution_ids.add(execution.id)
                    yield self._execution_event(execution, turn_id)
                    if execution.status == "failed":
                        yield {
                            "type": "error", "tool": execution.tool_name,
                            "message": execution.error, "recoverable": True,
                            "turn_id": turn_id,
                        }
                executions = await execution_task
            except BaseException:
                if not execution_task.done():
                    execution_task.cancel()
                    await asyncio.gather(execution_task, return_exceptions=True)
                raise
            for execution in executions:
                if execution.id in yielded_execution_ids:
                    continue
                yield self._execution_event(execution, turn_id)

        session.tool_executions = executions
        yield {"type": "synthesis", "status": "started", "turn_id": turn_id}
        final_status = (
            "partial" if any(item.status not in {"completed"} for item in executions)
            else "completed"
        )
        try:
            self.answer_synthesizer.assert_validated(executions)
            if legacy_mode:
                text = await self._synthesize(plan, executions, response_mode)
                suggestions = []
                evidence_refs = []
            else:
                text, evidence_refs, suggestions = await self._synthesize_tool_roundtrip(
                    user_message, plan, executions, prior_messages,
                    response_mode,
                )
            if not text.strip():
                raise RuntimeError("综合模型返回空文本")
        except Exception as exc:
            logger.exception("Final synthesis failed after tools completed")
            text = self._deterministic_fallback(executions, str(exc))
            suggestions = self._fallback_followups(executions, user_message)
            evidence_refs = []
            final_status = "partial"
            plan.final_response_metadata = {
                **plan.final_response_metadata,
                "answer_format": "markdown",
                "normalization_mode": "fallback",
            }
            yield {"type": "synthesis", "status": "fallback", "turn_id": turn_id}

        suggestions = self._filter_followup_suggestions(
            suggestions, user_message, prior_messages,
        )
        session.status = final_status
        session.messages.append({
            "role": "assistant", "content": text,
            "metadata": {
                "followup_suggestions": suggestions,
                "evidence_refs": evidence_refs,
                "answer_format": "markdown",
                "normalization_mode": plan.final_response_metadata.get(
                    "normalization_mode", "native",
                ),
            },
            "created_at": datetime.now().isoformat(),
        })
        coverage = self._coverage_manifest(executions)
        final_event = self._final_event(
            text, turn_id, final_status, suggestions, evidence_refs,
            plan.final_response_metadata.get("normalization_mode", "native"),
        )
        final_event["llm_response"] = plan.final_response_metadata
        yield final_event
        new_ids = [item.id for item in executions if not item.reused_from_execution_id]
        reused_ids = [
            item.reused_from_execution_id or item.id for item in executions
            if item.origin == "reused" or item.reused_from_execution_id
        ]
        yield self._done_event(
            session.id, turn_id, final_status, coverage, new_ids,
            reused_ids, suggestions,
            plan.final_response_metadata.get("normalization_mode", "native"),
        )

    @staticmethod
    def _control_tool_schemas() -> list[dict]:
        """Internal orchestration controls; these never appear in the sidebar."""
        return [
            {
                "name": "reuse_session_evidence",
                "description": (
                    "Use saved evidence from this session when it already answers the current "
                    "question. Do not call an analysis tool again. Return the exact execution IDs "
                    "to reuse and explain why they are relevant."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "execution_ids": {
                            "type": "array", "items": {"type": "string"},
                            "description": "Existing execution IDs from the evidence index.",
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["execution_ids", "reason"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "request_clarification",
                "description": (
                    "Pause before analysis only when a missing condition would materially change "
                    "the tool, parameters, or conclusion. Ask at most three related fields."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "missing_fields": {
                            "type": "array", "items": {"type": "string"},
                        },
                        "defaults": {
                            "type": "array", "items": {"type": "string"},
                        },
                    },
                    "required": ["question", "missing_fields"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "respond_without_analysis_tool",
                "description": (
                    "Use for help, method explanations, capability questions, or other requests "
                    "that require no patent dataset computation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                    "required": ["reason"],
                    "additionalProperties": False,
                },
            },
        ]

    async def _select_tools_with_llm(
        self, user_message: str, history: list[dict], storage: PatentDataStore,
        historical_evidence: list[dict], allow_over_budget: bool = False,
    ) -> AnalysisPlan:
        """One model call performs intent understanding and real tool selection."""
        catalog = self.tools.get_all_schemas(storage, for_llm=True)
        callable_tools = [
            {key: item[key] for key in ("name", "description", "parameters")}
            for item in catalog if item["availability"]["available"]
        ]
        all_tools = callable_tools + self._control_tool_schemas()
        capability_lines = []
        for item in catalog:
            capability_lines.append(
                f"- {item['name']} | available={item['availability']['available']} | "
                f"cost={item['cost_weight']} | {item['description']}"
            )
        evidence_index = [
            {
                "execution_id": item.get("id"),
                "turn_id": item.get("turn_id"),
                "tool": item.get("tool_name"),
                "parameters": item.get("parameters", {}),
                "summary": (item.get("result") or {}).get("summary", ""),
                "question": item.get("user_message", ""),
            }
            for item in historical_evidence[:20]
        ]
        dataset = storage.get_summary()
        audit = storage.audit()
        system = (
            "You are PatentAgent's tool-selection controller. Analyze the user's original "
            "request and choose only the minimum necessary tools using actual function calls. "
            "There is no keyword strategy chain and no default landscape report. Never add a "
            "tool merely because it could be interesting. A narrow question usually needs one "
            "tool; a genuinely multi-dimensional question may need several. The local automatic "
            "limit is four analysis tools and total cost weight six. Put every user filter "
            "(year, applicant, IPC, query, patent number) into the selected tool arguments; do "
            "not guess missing required arguments. If saved evidence is sufficient, call "
            "reuse_session_evidence. If a material condition is missing, call "
            "request_clarification. For method/help questions call "
            "respond_without_analysis_tool or answer directly. Never mix control tools with "
            "analysis tools in one plan. Do not claim FTO safety, financial value, blue ocean, "
            "lifecycle stage, external forward citations, or paper-exact algorithms unless the "
            "tool description explicitly permits it.\n\n"
            f"Dataset: total={dataset.total_patents}; years={dataset.year_range}; "
            f"audit={json.dumps(audit, ensure_ascii=False, default=str)}\n\n"
            "Dynamic capability catalog:\n" + "\n".join(capability_lines) +
            "\n\n历史工具证据 index:\n" +
            json.dumps(evidence_index, ensure_ascii=False, default=str)
        )
        recent = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in history[-10:]
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        base_messages = [
            {"role": "system", "content": system}, *recent,
            {"role": "user", "content": user_message},
        ]
        repair = ""
        response: ChatResponse | None = None
        for attempt in range(2):
            messages = list(base_messages)
            if repair:
                messages.append({
                    "role": "user",
                    "content": "The previous tool plan was invalid. Repair it once: " + repair,
                })
            response = await self.llm.chat(
                messages, tools=all_tools, tool_choice="auto", max_tokens=4096,
            )
            calls = response.tool_calls
            if not calls:
                reused = historical_evidence if historical_evidence else []
                return AnalysisPlan(
                    decision_type="direct", direct_answer=response.text,
                    reused_evidence=reused, planner_response=response,
                    planner_messages=messages, validation_status="valid_no_tool",
                )
            control_names = {item["name"] for item in self._control_tool_schemas()}
            control = [call for call in calls if call.get("name") in control_names]
            analysis = [call for call in calls if call.get("name") not in control_names]
            if control and analysis:
                repair = "Control tools and analysis tools cannot be mixed. Choose one path."
                continue
            if any(call.get("parse_error") for call in calls):
                repair = "One or more tool arguments were invalid JSON. Return schema-valid JSON."
                continue
            call_ids = [str(call.get("id", "")) for call in calls]
            if any(not call_id for call_id in call_ids) or len(set(call_ids)) != len(call_ids):
                repair = "Every tool call needs a unique non-empty provider call ID."
                continue
            if any(not isinstance(call.get("arguments"), dict) for call in calls):
                repair = "Every tool argument payload must be a JSON object."
                continue
            if control:
                if len(control) != 1:
                    repair = "Choose exactly one control tool."
                    continue
                call = control[0]
                args = {key: value for key, value in call.get("arguments", {}).items()
                        if value is not None}
                if call["name"] == "request_clarification":
                    if (
                        not isinstance(args.get("question"), str) or
                        not isinstance(args.get("missing_fields"), list) or
                        not args["missing_fields"] or len(args["missing_fields"]) > 3
                    ):
                        repair = "Clarification needs a question and missing_fields."
                        continue
                    return AnalysisPlan(
                        decision_type="clarify", tool_calls=calls,
                        planner_response=response, planner_messages=messages,
                        clarification=args,
                    )
                if call["name"] == "reuse_session_evidence":
                    if not isinstance(args.get("execution_ids"), list) or not isinstance(args.get("reason"), str):
                        repair = "Evidence reuse needs execution_ids and a reason."
                        continue
                    requested = set(args.get("execution_ids") or [])
                    known = {item.get("id") for item in historical_evidence}
                    if not requested or not requested.issubset(known):
                        repair = "reuse_session_evidence must contain existing IDs from the index."
                        continue
                    selected = [
                        item for item in historical_evidence if item.get("id") in requested
                    ]
                    return AnalysisPlan(
                        decision_type="reuse", tool_calls=calls,
                        reused_evidence=selected, planner_response=response,
                        planner_messages=messages,
                    )
                if not isinstance(args.get("reason"), str) or not args["reason"].strip():
                    repair = "respond_without_analysis_tool needs a non-empty reason."
                    continue
                return AnalysisPlan(
                    decision_type="respond", tool_calls=calls,
                    planner_response=response, planner_messages=messages,
                )

            steps: list[dict] = []
            seen: set[str] = set()
            cost = 0
            validation_errors: list[str] = []
            for index, call in enumerate(analysis, 1):
                name = call.get("name", "")
                try:
                    tool = self.tools.get_tool(name)
                except KeyError:
                    validation_errors.append(f"unknown tool {name}")
                    continue
                capability = tool.availability(storage)
                if not capability["available"]:
                    validation_errors.append(f"{name} unavailable: {capability['reason']}")
                    continue
                args = {
                    key: value for key, value in (call.get("arguments") or {}).items()
                    if value is not None
                }
                try:
                    args = tool.validate_params(args)
                except ValueError as exc:
                    validation_errors.append(f"{name}: {exc}")
                    continue
                signature = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
                if signature in seen:
                    continue
                seen.add(signature)
                cost += tool.cost_weight
                steps.append({
                    "step": index, "tool": name, "params": args,
                    "reason": "LLM tool call", "tool_call_id": call.get("id", ""),
                    "cost_weight": tool.cost_weight,
                })
            if validation_errors:
                repair = "; ".join(validation_errors)
                continue
            if not steps:
                repair = "The plan contained no executable analysis tool."
                continue
            needs_confirmation = self.execution_policy.requires_confirmation(
                len(steps), cost, approved=allow_over_budget,
            )
            return AnalysisPlan(
                steps=steps, tool_calls=calls, cost_weight=cost,
                requires_confirmation=needs_confirmation,
                planner_response=response, planner_messages=messages,
                validation_status="valid",
            )
        raise RuntimeError(f"LLM_TOOL_PLAN_INVALID: {repair or 'unknown error'}")

    async def _clarification_events(
        self, session: Session, turn_id: str, question: str,
        missing_fields: list[str], defaults: list[str] | None = None,
    ):
        session.status = "awaiting_clarification"
        suggestion = {
            "text": "按默认条件继续", "kind": "clarification_default",
            "requires_new_tools": False, "evidence_ref": None,
        }
        yield {
            "type": "clarification", "turn_id": turn_id,
            "question": question, "missing_fields": missing_fields,
            "defaults": defaults or [], "allow_defaults": True,
        }
        yield self._final_event(
            question, turn_id, "awaiting_clarification", [suggestion], [],
        )
        yield self._done_event(
            session.id, turn_id, "awaiting_clarification", [], [], [], [suggestion],
        )

    @staticmethod
    def _restore_evidence_executions(evidence: list[dict]) -> list[ToolExecution]:
        restored = []
        for item in evidence:
            payload = item.get("result") or {}
            payload.setdefault("result_type", "historical_evidence")
            restored.append(ToolExecution(
                id=f"reuse_{item.get('id')}",
                tool_name=item.get("tool_name", "historical_evidence"),
                parameters=item.get("parameters", {}), status="completed",
                result=GenericAnalysisResult.model_validate(payload),
                origin="reused", reused_from_execution_id=item.get("id"),
            ))
        return restored

    @staticmethod
    def _final_output_schema() -> dict:
        return {
            "type": "object",
            "properties": {
                "answer_markdown": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "followup_suggestions": {
                    "type": "array", "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "kind": {
                                "type": "string",
                                "enum": ["explain", "drilldown", "new_analysis", "method"],
                            },
                            "requires_new_tools": {"type": "boolean"},
                            "evidence_ref": {"type": ["string", "null"]},
                        },
                        "required": [
                            "text", "kind", "requires_new_tools", "evidence_ref",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["answer_markdown", "evidence_refs", "followup_suggestions"],
            "additionalProperties": False,
        }

    async def _execution_payload_for_llm(self, execution: ToolExecution) -> dict:
        base = {
            "status": execution.status,
            "tool_name": execution.tool_name,
            "parameters": execution.parameters,
        }
        if not execution.result:
            return {**base, "error": execution.error or execution.status}
        payload = execution.result.model_dump(exclude={"chart_html"})
        metadata = payload.get("result_metadata", {})
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        coverage = {
            "fields_read": sorted(payload), "source_chars": len(raw),
            "chunked": len(raw) > 36000, "omitted": False,
        }
        if len(raw) <= 36000:
            analysis_payload: Any = payload
        else:
            chunks = _safe_text_chunks(raw, 12000)
            extracted = []
            for index, chunk in enumerate(chunks, 1):
                response = await self.llm.chat([{
                    "role": "user",
                    "content": (
                        "Read this complete tool-result chunk and extract every decision-relevant "
                        "fact, number, method, warning and limitation. Do not create conclusions. "
                        f"Tool={execution.tool_name}; chunk={index}/{len(chunks)}\n{chunk}"
                    ),
                }], max_tokens=4096)
                extracted.append({"chunk": index, "evidence": response.text})
            analysis_payload = {"chunk_evidence": extracted}
            coverage["chunks"] = len(chunks)
        return {
            **base,
            "summary": payload.get("summary", ""),
            "analysis_payload": analysis_payload,
            "methodology": payload.get("methodology", ""),
            "data_quality": payload.get("data_quality", {}),
            "warnings": payload.get("warnings", []),
            "result_metadata": metadata,
            "prohibited_claims": metadata.get("prohibited_claims", []),
            "coverage_manifest": coverage,
        }

    async def _synthesize_tool_roundtrip(
        self, user_message: str, plan: AnalysisPlan,
        executions: list[ToolExecution], history: list[dict], response_mode: str,
    ) -> tuple[str, list[str], list[dict]]:
        """Feed local results back to the selecting model using its native protocol."""
        payloads = [
            await self._execution_payload_for_llm(execution)
            for execution in executions
        ]
        by_call = {
            execution.provider_tool_call_id: payload
            for execution, payload in zip(executions, payloads)
            if execution.provider_tool_call_id
        }
        tool_results: list[dict] = []
        for call in plan.tool_calls:
            name = call.get("name")
            if name == "reuse_session_evidence":
                payload = {"status": "completed", "reused_evidence": payloads}
            elif name == "respond_without_analysis_tool":
                payload = {"status": "completed", "instruction": "Answer without dataset tools."}
            else:
                payload = by_call.get(call.get("id"))
                if payload is None:
                    candidate = next(
                        (item for item in payloads if item["tool_name"] == name), None,
                    )
                    payload = candidate or {
                        "status": "error", "tool_name": name,
                        "error": "No matching local execution result",
                    }
            tool_results.append({
                "tool_call_id": call.get("id", ""), "payload": payload,
                "is_error": payload.get("status") not in {"completed", "ok"},
            })

        previous_suggestions = self._previous_suggestion_texts(history)
        final_instruction = (
            "Now produce the final answer for the user's original question. This is the answer "
            "phase: do not call any more tools. Return JSON matching the requested schema. "
            f"Original question: {user_message}\nResponse mode: {response_mode}. "
            "Answer the specific question directly; do not turn it into a generic landscape "
            "report. Use only current or explicitly reused evidence. Put source references after "
            "important facts. Explain relevant methodology and limitations, and obey every "
            "prohibited_claim. Put every user-visible conclusion, detail, methodology and "
            "limitation inside answer_markdown as natural Markdown; never return report sections "
            "as extra JSON fields. In detailed mode organize the report as core conclusion, "
            "dimension-specific analysis, trend assessment, and methodology/data limitations. "
            "In concise mode keep the direct conclusion, key evidence, and necessary limitations. "
            "Generate zero to three concrete follow-up questions based on this "
            "turn's actual findings. They must differ from previous questions and already answered "
            f"topics. Previous suggestions: {json.dumps(previous_suggestions, ensure_ascii=False)}. "
            "If fewer than three useful questions exist, return fewer; never use filler."
        )
        schema = self._final_output_schema()
        response: ChatResponse
        if (
            plan.planner_response and plan.planner_response.raw_assistant_message and
            hasattr(self.llm, "continue_with_tool_results")
        ):
            response = await self.llm.continue_with_tool_results(
                plan.planner_messages, plan.planner_response, tool_results,
                self._tools_used_for_roundtrip(plan),
                final_instruction, response_schema=schema,
            )
        else:
            # Compatibility for local/fake clients without raw provider messages.
            response = await self.llm.chat([{
                "role": "user",
                "content": final_instruction + "\nTOOL RESULTS:\n" +
                           json.dumps(payloads, ensure_ascii=False, default=str),
            }], response_schema=schema)
        initial_response = response
        parsed = self._parse_final_output(response.text)
        missing = self._final_output_missing(parsed, executions, response_mode)
        if response.finish_reason.lower() in {"length", "max_tokens"}:
            missing.append("response was truncated")
        if missing and hasattr(self.llm, "continue_with_tool_results") and plan.planner_response:
            retry_instruction = (
                final_instruction + "\nRepair the invalid previous final output. Return JSON only. "
                f"Missing requirements: {', '.join(missing)}.\n"
                "The exact required JSON Schema is:\n"
                f"{json.dumps(schema, ensure_ascii=False)}\n"
                "Previous invalid output follows; preserve its useful facts while correcting "
                "the envelope and moving all report sections into answer_markdown:\n"
                f"{response.text}"
            )
            response = await self.llm.continue_with_tool_results(
                plan.planner_messages, plan.planner_response, tool_results,
                self._tools_used_for_roundtrip(plan), retry_instruction,
                response_schema=schema,
            )
            parsed = self._parse_final_output(response.text)
            missing = self._final_output_missing(parsed, executions, response_mode)
            if response.finish_reason.lower() in {"length", "max_tokens"}:
                missing.append("response was truncated")

        normalization_mode = "native" if response is initial_response else "llm_repair"
        if parsed is None or missing:
            tool_names = [item.tool_name for item in executions]
            for candidate in (response, initial_response):
                normalized, mode = normalize_final_answer(candidate.text, tool_names)
                candidate_missing = self._final_output_missing(
                    normalized, executions, response_mode,
                )
                if normalized is not None and not candidate_missing:
                    parsed = normalized
                    response = candidate
                    missing = []
                    normalization_mode = mode
                    break
        if missing:
            raise RuntimeError("FINAL_OUTPUT_INCOMPLETE: " + ", ".join(missing))
        if parsed is None:
            raise RuntimeError("FINAL_OUTPUT_INCOMPLETE: valid user-facing response")
        plan.final_response_metadata = {
            **self._chat_response_metadata(response),
            "answer_format": "markdown",
            "normalization_mode": normalization_mode,
        }
        return (
            parsed["answer_markdown"].strip(),
            parsed.get("evidence_refs", []),
            parsed.get("followup_suggestions", []),
        )

    async def resynthesize_from_evidence(
        self, user_message: str, executions: list[ToolExecution],
        response_mode: str = "detailed", history: list[dict] | None = None,
    ) -> tuple[str, list[str], list[dict], str]:
        """Retry only the answer phase without rerunning or faking tool calls."""
        payloads = [
            await self._execution_payload_for_llm(execution)
            for execution in executions
        ]
        prompt = (
            "You are retrying only the final synthesis of an existing patent-analysis turn. "
            "Do not call tools. Return JSON matching the supplied schema with answer_markdown, "
            "evidence_refs and zero to three non-repeating followup_suggestions. Directly answer "
            "the original question, cite each completed tool, explain relevant limitations, and "
            "obey prohibited_claims.\n"
            f"Original question: {user_message}\nMode: {response_mode}\n"
            f"Previous suggestions: {json.dumps(self._previous_suggestion_texts(history or []), ensure_ascii=False)}\n"
            f"Evidence: {json.dumps(payloads, ensure_ascii=False, default=str)}"
        )
        response = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            response_schema=self._final_output_schema(),
        )
        initial_response = response
        normalization_mode = "native"
        parsed = self._parse_final_output(response.text)
        missing = self._final_output_missing(parsed, executions, response_mode)
        if missing:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt +
                  "\nRepair missing requirements: " + ", ".join(missing) +
                  "\nPrevious invalid output:\n" + response.text +
                  "\nExact JSON Schema:\n" +
                  json.dumps(self._final_output_schema(), ensure_ascii=False)}],
                response_schema=self._final_output_schema(),
            )
            parsed = self._parse_final_output(response.text)
            missing = self._final_output_missing(parsed, executions, response_mode)
            if parsed is not None and not missing:
                normalization_mode = "llm_repair"
        if parsed is None or missing:
            tool_names = [item.tool_name for item in executions]
            for candidate in (response, initial_response):
                normalized, _mode = normalize_final_answer(candidate.text, tool_names)
                candidate_missing = self._final_output_missing(
                    normalized, executions, response_mode,
                )
                if normalized is not None and not candidate_missing:
                    parsed = normalized
                    missing = []
                    normalization_mode = "local_repair"
                    break
        if parsed is None or missing:
            raise RuntimeError("RESYNTHESIS_INCOMPLETE: " + ", ".join(missing))
        suggestions = self._filter_followup_suggestions(
            parsed["followup_suggestions"], user_message, history or [],
        )
        return (
            parsed["answer_markdown"], parsed["evidence_refs"], suggestions,
            normalization_mode,
        )

    def _tools_used_for_roundtrip(self, plan: AnalysisPlan) -> list[dict]:
        # Recreate the exact definitions from registry/control schemas. Availability
        # metadata is intentionally excluded from provider requests.
        controls = {item["name"]: item for item in self._control_tool_schemas()}
        used = []
        for call in plan.tool_calls:
            name = call.get("name")
            if name in controls:
                used.append(controls[name])
                continue
            try:
                schema = self.tools.get_tool(name).to_schema()
            except KeyError:
                continue
            used.append({key: schema[key] for key in ("name", "description", "parameters")})
        return used

    @staticmethod
    def _parse_final_output(text: str) -> dict | None:
        return parse_canonical_final_answer(text)

    @staticmethod
    def _final_output_missing(
        parsed: dict | None, executions: list[ToolExecution], response_mode: str,
    ) -> list[str]:
        if parsed is None:
            return ["valid structured JSON"]
        answer = parsed.get("answer_markdown", "")
        refs = " ".join(parsed.get("evidence_refs", []))
        missing = []
        for execution in executions:
            if execution.tool_name not in answer + refs:
                missing.append(f"source reference for {execution.tool_name}")
        if response_mode == "detailed" and not any(word in answer for word in ("限制", "局限", "limitation")):
            missing.append("data/method limitations")
        return missing

    @staticmethod
    def _previous_suggestion_texts(history: list[dict]) -> list[str]:
        texts: list[str] = []
        for item in history:
            metadata = item.get("metadata") or {}
            for suggestion in metadata.get("followup_suggestions", []):
                if isinstance(suggestion, str):
                    texts.append(suggestion)
                elif isinstance(suggestion, dict) and suggestion.get("text"):
                    texts.append(suggestion["text"])
        return texts[-12:]

    @classmethod
    def _filter_followup_suggestions(
        cls, suggestions: list, current_question: str, history: list[dict],
    ) -> list[dict]:
        prior = [current_question]
        prior.extend(item.get("content", "") for item in history if item.get("content"))
        prior.extend(cls._previous_suggestion_texts(history))
        accepted: list[dict] = []
        for raw in suggestions or []:
            item = {"text": raw} if isinstance(raw, str) else dict(raw)
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            if any(cls._question_similarity(text, old) >= 0.72 for old in [*prior, *[x["text"] for x in accepted]]):
                continue
            item.setdefault("kind", "drilldown")
            item.setdefault("requires_new_tools", False)
            item.setdefault("evidence_ref", None)
            accepted.append(item)
            if len(accepted) == 3:
                break
        return accepted

    @staticmethod
    def _question_similarity(left: str, right: str) -> float:
        normalize = lambda value: re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())
        a, b = normalize(left), normalize(right)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        grams = lambda value: {value[i:i + 2] for i in range(max(1, len(value) - 1))}
        ga, gb = grams(a), grams(b)
        return len(ga & gb) / max(1, len(ga | gb))

    @staticmethod
    def _fallback_followups(
        executions: list[ToolExecution], user_question: str,
    ) -> list[dict]:
        """Evidence-specific fallback only; never pad with fixed generic questions."""
        suggestions: list[dict] = []
        for execution in executions:
            if not execution.result:
                continue
            payload = execution.result.model_dump(exclude={"chart_html"})
            data = payload.get("data")
            if execution.tool_name == "analyze_patent_trend" and isinstance(data, list) and data:
                peak = max(data, key=lambda item: item.get("count", 0))
                period = peak.get("year_month") or peak.get("year")
                suggestions.append({
                    "text": f"{period} 的公开量高点由哪些主题或申请人贡献？",
                    "kind": "new_analysis", "requires_new_tools": True,
                    "evidence_ref": f"[{execution.tool_name}:data]",
                })
            elif execution.tool_name == "analyze_ipc_distribution":
                labels = payload.get("sections") or []
                if labels:
                    suggestions.append({
                        "text": f"占比最高的 {labels[0]} 在各年如何变化？",
                        "kind": "drilldown", "requires_new_tools": False,
                        "evidence_ref": f"[{execution.tool_name}:sections]",
                    })
            warnings = payload.get("warnings") or []
            if warnings:
                topic = str(warnings[0])[:38]
                suggestions.append({
                    "text": f"“{topic}”会如何影响本轮结论的可信度？",
                    "kind": "explain", "requires_new_tools": False,
                    "evidence_ref": f"[{execution.tool_name}:warnings]",
                })
            if len(suggestions) >= 3:
                break
        return suggestions[:3]

    @staticmethod
    def _final_event(
        text: str, turn_id: str, status: str, suggestions: list[dict],
        evidence_refs: list[str] | None = None,
        normalization_mode: str = "native",
    ) -> dict:
        return {
            "type": "final", "text": text, "strategy": None,
            "turn_id": turn_id, "final_status": status,
            "answer_format": "markdown",
            "normalization_mode": normalization_mode,
            "evidence_refs": evidence_refs or [],
            "followup_suggestions": suggestions,
            "followup_questions": [item["text"] for item in suggestions],
        }

    @staticmethod
    def _chat_response_metadata(response: ChatResponse | None) -> dict:
        if response is None:
            return {}
        return {
            "provider": response.provider,
            "model": response.model,
            "request_id": response.request_id,
            "usage": response.usage,
            "finish_reason": response.finish_reason,
        }

    @staticmethod
    def _done_event(
        session_id: str, turn_id: str, status: str, coverage: list[dict],
        new_ids: list[str], reused_ids: list[str], suggestions: list[dict],
        normalization_mode: str = "native",
    ) -> dict:
        return {
            "type": "done", "session_id": session_id, "turn_id": turn_id,
            "final_status": status, "answer_present": status != "failed",
            "answer_format": "markdown",
            "normalization_mode": normalization_mode,
            "result_coverage": coverage,
            "coverage_complete": all(not item.get("omitted", False) for item in coverage),
            "new_execution_ids": new_ids, "reused_execution_ids": reused_ids,
            "followup_suggestions": suggestions,
            "followup_questions": [item["text"] for item in suggestions],
        }

    async def query_with_catalog(self,
                                  user_message: str,
                                  catalog: "DataCatalog") -> str:
        """基于 DataCatalog 的问答: LLM 先选数据维度，再基于选中数据回答。

        不做工具调用，直接从预计算目录中取数据。上下文更小，回答更精准。
        """
        # 1. 展示数据菜单，让 LLM 选择需要的维度
        menu = catalog.to_menu()
        selection_prompt = DATA_SELECTION_PROMPT.format(
            user_query=user_message,
            data_menu=menu,
        )
        sel_resp = await self.llm.chat([{"role": "user", "content": selection_prompt}])

        # 2. 解析选中的维度
        selected_keys = []
        try:
            text = sel_resp.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            sel_data = json.loads(text)
            selected_keys = sel_data.get("selected_keys", [])
        except (json.JSONDecodeError, KeyError):
            selected_keys = ["trend", "word_freq", "ipc"]  # 兜底: 选最常用的

        # 3. 加载选中的完整数据（始终附加数据集概况）
        data_sections = []
        # 元信息始终附带
        meta = (
            f"## dataset_overview\n"
            f"专利总量: {catalog.total_patents:,}\n"
            f"时间跨度: {catalog.year_range[0]} – {catalog.year_range[1]}\n"
            f"主要 IPC: {', '.join(catalog.top_ipc_sections[:8])}\n"
        )
        if catalog.top_applicants:
            meta += f"Top 申请人: {', '.join(a['name'] for a in catalog.top_applicants[:5])}\n"
        data_sections.append(meta)

        for key in selected_keys:
            full_data = catalog.get_full_data(key)
            if full_data:
                j = json.dumps(full_data, ensure_ascii=False, indent=2)
                data_sections.append(
                    f"## {key}\n```json\n{j}\n```"
                )

        if not data_sections:
            return "未找到相关数据，请尝试更具体的问题。"

        # 4. 基于选中数据生成答案
        data_text = "\n\n".join(data_sections)
        answer_prompt = (
            "你是专利分析专家。以下是从专利数据集中提取的真实分析数据。"
            "请严格基于这些数据回答用户问题。禁止编造任何未在数据中出现的信息。\n\n"
            f"用户问题: {user_message}\n\n"
            f"分析数据:\n{data_text}\n\n"
            "如果是'总览'类问题，请从多个维度给出全景式的摘要。"
            "请用中文给出简洁、专业的分析结论。引用具体数字。"
        )
        answer_resp = await self.llm.chat([{"role": "user", "content": answer_prompt}])
        return answer_resp.text or "分析完成，请查看数据。"

    async def resume_with_approval(self,
                                   session: Session,
                                   storage: PatentDataStore,
                                   decision: str = "APPROVED",
                                   modifications: dict = None) -> AgentResponse:
        """
        用户确认后从 session 恢复 Plan 并继续执行。
        decision: APPROVED / REJECTED / MODIFIED
        """
        if decision == "REJECTED":
            session.status = "completed"
            return AgentResponse(
                text="已取消分析。请重新描述您的需求，我会调整分析方案。",
                session_status="completed",
            )

        if not session.pending_plan:
            return AgentResponse(
                text="无法找到待确认的分析计划，请重新提问。",
                session_status="completed",
            )

        # 恢复 Plan
        plan_data = session.pending_plan["plan"]
        plan = AnalysisPlan(
            steps=plan_data["steps"],
            estimated_tokens=plan_data.get("estimated_tokens", 0),
            requires_confirmation=False,
        )

        # MODIFIED: 合并用户修改
        if decision == "MODIFIED" and modifications:
            plan = await self._modify_plan(plan, modifications)

        session.status = "executing"
        return await self._execute_and_synthesize(plan, session, storage)

    async def _execute_and_synthesize(self,
                                       plan: AnalysisPlan,
                                       session: Session,
                                       storage: PatentDataStore,
                                       response_mode: str = "detailed") -> AgentResponse:
        """执行计划 + 综合结论。v2.0: 支持自适应规划和跨工具关联推理。"""
        self.state = AgentState.EXECUTING
        session.tool_executions = []

        # v2.0: Adaptive execution with intermediate review
        if self.enable_strategic_mode and plan.chain_id:
            executions = await self._execute_with_adaptive_review(plan, storage)
        else:
            executions = await self._execute_plan(plan, storage)

        session.tool_executions = executions

        # 5. SYNTHESIZING
        self.state = AgentState.SYNTHESIZING

        # v2.0: If strategic mode, use cross-tool synthesis + recommendation engine
        if self.enable_strategic_mode and plan.chain_id:
            synthesis, strategy_report = await self._strategic_synthesize(
                plan, executions, response_mode=response_mode,
            )
        else:
            synthesis = await self._synthesize(
                plan, executions, response_mode=response_mode,
            )
            strategy_report = None

        # 6. DONE
        self.state = AgentState.DONE
        session.status = "completed"
        session.messages.extend([
            {"role": "assistant", "content": synthesis,
             "created_at": datetime.now().isoformat()},
        ])

        charts_html = [
            e.result.chart_html for e in executions
            if e.result and e.result.chart_html
        ]
        return AgentResponse(
            text=synthesis,
            charts=charts_html,
            plan={"steps": plan.steps, "chain": plan.chain_id},
            tool_executions=executions,
            session_status="completed",
            strategy_report=strategy_report,
        )

    # ── 意图理解 ──
    async def _understand_intent(self, message: str,
                                 history: list[dict] | None = None) -> IntentAnalysis:
        """用 LLM 理解用户意图，提取关键实体"""
        summary = self.knowledge.get("methodology_summary", "")
        tools_desc = "\n".join(
            f"- {t.name}: {t.description[:120]}"
            for t in self.tools.list_tools()
        )
        recent_history = "\n".join(
            f"{m.get('role')}: {m.get('content', '')[:1000]}"
            for m in (history or [])[-6:]
        )
        prompt = INTENT_UNDERSTANDING_PROMPT.format(
            user_message=message,
            methodology_summary=summary[:2000],
            available_tools=tools_desc,
        )
        if recent_history:
            prompt += f"\n\n同一会话最近上下文（用于理解追问）:\n{recent_history}"
        response = await self.llm.chat([
            {"role": "user", "content": prompt},
        ])
        try:
            data = json.loads(response.text)
            return IntentAnalysis(
                goal=data.get("goal", ""),
                tech_field=data.get("tech_field"),
                applicants=data.get("applicants", []),
                ipc_codes=data.get("ipc_codes", []),
                time_range=tuple(data["time_range"]) if data.get("time_range") else None,
                analysis_type=data.get("analysis_type", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return IntentAnalysis(goal=message, analysis_type="general")

    # ── 分析计划 ──
    async def _plan_analysis(self, intent: IntentAnalysis,
                             storage: PatentDataStore,
                             user_message: str = "") -> AnalysisPlan:
        """制定分析计划。v2.0: 优先使用战略分析链(Strategy Chain)。"""
        ds = storage.get_summary()
        dataset_info = (
            f"专利总量: {ds.total_patents}, "
            f"时间跨度: {ds.year_range[0]}-{ds.year_range[1]}, "
            f"IPC 分类: {', '.join(ds.ipc_sections)}"
        )

        # v2.0: Try strategy chain selection first
        if self.enable_strategic_mode:
            from agent.strategy_chains import select_chain
            chain = select_chain(
                intent.goal, intent.analysis_type, user_message,
            )
            if chain:
                steps = []
                for i, cs in enumerate(chain.steps, 1):
                    params = self._merge_intent_params(
                        cs.tool_name, cs.params.copy(), intent,
                    )
                    steps.append({
                        "step": i,
                        "tool": cs.tool_name,
                        "params": params,
                        "reason": cs.reason,
                        "_triggers_strategy": cs.triggers_strategy,
                        "_optional": cs.optional,
                        "_condition": cs.condition,
                        "_depends_on": cs.depends_on,
                    })
                logger.info("Using strategy chain: %s (%d steps)", chain.chain_id, len(steps))
                return AnalysisPlan(
                    steps=steps,
                    estimated_tokens=len(steps) * 800,
                    chain_id=chain.chain_id,
                )

        # Fallback: LLM-based planning (original behavior)
        tools_desc = json.dumps(self.tools.get_all_schemas(), ensure_ascii=False)

        prompt = PLANNING_PROMPT.format(
            user_intent=json.dumps({
                "goal": intent.goal,
                "tech_field": intent.tech_field,
                "applicants": intent.applicants,
                "time_range": list(intent.time_range) if intent.time_range else None,
                "analysis_type": intent.analysis_type,
            }, ensure_ascii=False),
            available_tools=tools_desc,
            dataset_summary=dataset_info,
        )

        response = await self.llm.chat([
            {"role": "user", "content": prompt},
        ])

        try:
            data = json.loads(response.text)
            steps = data.get("plan", [])
            estimated_tokens = data.get("estimated_tokens", 0)
            needs_confirm = data.get("requires_confirmation", False)

            for step in steps:
                tool_name = step.get("tool", "")
                try:
                    tool = self.tools.get_tool(tool_name)
                    step["params"] = self._merge_intent_params(
                        tool_name, step.get("params", {}), intent,
                    )
                    if tool.requires_confirmation:
                        needs_confirm = True
                except KeyError:
                    pass

            return AnalysisPlan(
                steps=steps,
                estimated_tokens=estimated_tokens,
                requires_confirmation=needs_confirm,
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            fallback_steps = [
                    {"step": 1, "tool": "get_dataset_summary",
                     "params": {}, "reason": "了解数据概况"},
                    {"step": 2, "tool": "analyze_patent_trend",
                     "params": {}, "reason": "查看趋势"},
                ]
            for step in fallback_steps:
                step["params"] = self._merge_intent_params(
                    step["tool"], step["params"], intent,
                )
            return AnalysisPlan(
                steps=fallback_steps,
                estimated_tokens=500,
                requires_confirmation=False,
            )

    async def _modify_plan(self, plan: AnalysisPlan,
                           modifications: dict) -> AnalysisPlan:
        """合并用户修改"""
        if modifications.get("remove_steps"):
            remove_ids = set(modifications["remove_steps"])
            plan.steps = [s for s in plan.steps
                          if s.get("step") not in remove_ids]
        if modifications.get("add_steps"):
            plan.steps.extend(modifications["add_steps"])
        if modifications.get("override_params"):
            for step_id, params in modifications["override_params"].items():
                for s in plan.steps:
                    if s.get("step") == step_id:
                        s["params"] = params
        return plan

    def _should_confirm(self, plan: AnalysisPlan) -> bool:
        """判断是否需要用户确认"""
        if plan.estimated_tokens > 50000:
            return True
        return False

    # ── 执行计划 ──
    async def _execute_llm_plan(
        self, plan: AnalysisPlan, storage: PatentDataStore,
        reuse_lookup: Callable[[str, dict, str], Awaitable[ToolExecution | None]] | None = None,
        on_execution: Callable[[ToolExecution], Awaitable[None]] | None = None,
    ) -> list[ToolExecution]:
        """Run independent model-selected, read-only tools concurrently."""
        semaphore = asyncio.Semaphore(4)

        async def run_step(step: dict) -> ToolExecution:
            async with semaphore:
                execution = await self._execute_with_retry(
                    step["tool"], dict(step.get("params", {})), storage,
                    reuse_lookup=reuse_lookup, on_execution=None,
                )
                execution.provider_tool_call_id = step.get("tool_call_id")
                if on_execution:
                    await on_execution(execution)
                return execution

        return list(await asyncio.gather(*(run_step(step) for step in plan.steps)))

    async def _execute_plan(
        self, plan: AnalysisPlan, storage: PatentDataStore,
        reuse_lookup: Callable[[str, dict, str], Awaitable[ToolExecution | None]] | None = None,
        on_execution: Callable[[ToolExecution], Awaitable[None]] | None = None,
    ) -> list[ToolExecution]:
        """按顺序执行 Tool，每步带重试"""
        executions = []
        for step in plan.steps:
            tool_name = step.get("tool", "")
            params = dict(step.get("params", {}))
            dependency = step.get("_depends_on") or step.get("depends_on")
            prior = next((e for e in reversed(executions)
                          if e.tool_name == dependency), None) if dependency else None
            if dependency and (prior is None or prior.status != "completed"):
                executions.append(self._skipped_execution(
                    tool_name, params, f"依赖步骤 {dependency} 未成功完成",
                ))
                continue
            condition = step.get("_condition") or step.get("condition")
            if condition and not self._condition_met(condition, prior):
                executions.append(self._skipped_execution(
                    tool_name, params, f"条件 {condition} 不满足",
                ))
                continue
            if tool_name == "read_patent_details" and prior and prior.result:
                params["patent_numbers"] = [
                    p.get("patent_number")
                    for p in getattr(prior.result, "patents", [])[:5]
                    if p.get("patent_number")
                ]

            try:
                tool = self.tools.get_tool(tool_name)
            except KeyError:
                executions.append(ToolExecution(
                    id=f"err_{tool_name}",
                    tool_name=tool_name,
                    parameters=params,
                    status="failed",
                    error=f"未知工具: {tool_name}",
                ))
                continue

            execution = await self._execute_with_retry(
                tool_name, params, storage, reuse_lookup=reuse_lookup,
                on_execution=on_execution,
            )
            execution.provider_tool_call_id = step.get("tool_call_id")
            executions.append(execution)

        return executions

    async def _execute_with_retry(
        self, tool_name: str, params: dict, storage: PatentDataStore,
        reuse_lookup: Callable[[str, dict, str], Awaitable[ToolExecution | None]] | None = None,
        on_execution: Callable[[ToolExecution], Awaitable[None]] | None = None,
    ) -> ToolExecution:
        """带反思重试的 Tool 执行，失败时进入 EXECUTION_ERROR 状态"""
        tool = self.tools.get_tool(tool_name)
        started = time.time()

        if reuse_lookup is not None:
            algorithm_version = str(tool.evidence_record.get("version", ""))
            reusable = await reuse_lookup(tool_name, params, algorithm_version)
            if reusable is not None:
                if on_execution:
                    await on_execution(reusable)
                return reusable

        # Only pass params that exist in the tool's parameter schema
        valid_keys = set(tool.parameters.keys())
        filters = params.get("__filters", {})
        effective_storage = storage.filtered(**filters) if filters else storage
        for attempt in range(self.max_retries + 1):
            try:
                # 每次重试都重新过滤并校验 LLM 修正后的参数。
                filtered = {k: v for k, v in params.items() if k in valid_keys}
                result: AnalysisResult = await tool.run(effective_storage, **filtered)
                execution = ToolExecution(
                    id=f"{tool_name}_{uuid4().hex}",
                    tool_name=tool_name,
                    parameters=params,
                    status="completed",
                    result=result,
                    started_at=started,
                    completed_at=time.time(),
                    duration_ms=(time.time() - started) * 1000,
                    retry_count=attempt,
                )
                if on_execution:
                    await on_execution(execution)
                return execution
            except Exception as e:
                error_msg = str(e)
                self.state = AgentState.EXECUTION_ERROR

                if attempt < self.max_retries:
                    # 尝试让 LLM 修正参数（RETRYABLE 路径）
                    retry_params = await self._suggest_retry_params(
                        tool_name, params, error_msg,
                    )
                    if retry_params and retry_params != params:
                        params = {**retry_params, "__filters": filters} if filters else retry_params
                        continue

                # 致命错误（FATAL 路径）或超过 max_retries
                execution = ToolExecution(
                    id=f"{tool_name}_{uuid4().hex}",
                    tool_name=tool_name,
                    parameters=params,
                    status="failed",
                    error=error_msg,
                    started_at=started,
                    completed_at=time.time(),
                    duration_ms=(time.time() - started) * 1000,
                    retry_count=attempt,
                )
                if on_execution:
                    await on_execution(execution)
                return execution

    async def _suggest_retry_params(self, tool_name: str,
                                    params: dict, error: str) -> dict | None:
        """LLM 建议修正参数"""
        prompt = (
            f"工具 '{tool_name}' 执行失败。\n"
            f"原始参数: {json.dumps(params, ensure_ascii=False)}\n"
            f"错误信息: {error}\n\n"
            f"请判断是否可以通过修改参数来重试。如果可以，返回修正后的 JSON 参数。"
            f"如果无法修复，返回 null。\n"
            f"只返回 JSON，不要其他内容。"
        )
        try:
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            if data and isinstance(data, dict) and "null" not in str(data).lower():
                return data
        except Exception:
            pass
        return None

    # ── v2.0: Adaptive execution with intermediate review ──
    async def _execute_with_adaptive_review(
        self, plan: AnalysisPlan, storage: PatentDataStore,
        reuse_lookup: Callable[[str, dict, str], Awaitable[ToolExecution | None]] | None = None,
        on_execution: Callable[[ToolExecution], Awaitable[None]] | None = None,
    ) -> list[ToolExecution]:
        """Execute plan steps with adaptive review after each step."""
        from agent.adaptive_planner import AdaptivePlanner, ReviewDecision

        planner = AdaptivePlanner(llm_client=self.llm)
        remaining = list(plan.steps)
        executions = []

        while remaining:
            step = remaining.pop(0)
            tool_name = step.get("tool", "")

            dependency = step.get("_depends_on")
            prior = next((e for e in reversed(executions)
                          if e.tool_name == dependency), None) if dependency else None
            if dependency and (prior is None or prior.status != "completed"):
                executions.append(self._skipped_execution(
                    tool_name, step.get("params", {}),
                    f"依赖步骤 {dependency} 未成功完成",
                ))
                continue

            params = dict(step.get("params", {}))
            if tool_name == "read_patent_details" and prior and prior.result:
                patents = getattr(prior.result, "patents", [])
                params["patent_numbers"] = [
                    p.get("patent_number") for p in patents[:5]
                    if p.get("patent_number")
                ]

            if step.get("_condition") and not self._condition_met(
                step["_condition"], prior,
            ):
                executions.append(self._skipped_execution(
                    tool_name, params, f"条件 {step['_condition']} 不满足",
                ))
                continue

            try:
                tool = self.tools.get_tool(tool_name)
            except KeyError:
                executions.append(ToolExecution(
                    id=f"err_{tool_name}",
                    tool_name=tool_name,
                    parameters=step.get("params", {}),
                    status="failed",
                    error=f"未知工具: {tool_name}",
                ))
                continue

            capability = tool.availability(storage)
            if not capability["available"] and step.get("_optional"):
                executions.append(self._skipped_execution(
                    tool_name, params, capability["reason"],
                ))
                continue

            if plan.chain_id == "fto_risk" and tool_name == "read_patent_details":
                if not (storage.has_field("claims_json") and storage.has_field("legal_status")):
                    executions.append(self._skipped_execution(
                        tool_name, params,
                        "WoS 缺少权利要求与法律状态，仅能进行初步相关专利筛查",
                    ))
                    continue

            execution = await self._execute_with_retry(
                tool_name, params, storage, reuse_lookup=reuse_lookup,
                on_execution=on_execution,
            )
            executions.append(execution)

            # Intermediate review: adapt plan based on this step's result
            self.state = AgentState.INTERMEDIATE_REVIEW
            review = await planner.review_intermediate(
                step, execution, remaining, executions,
            )

            if review.decision in (ReviewDecision.REPLAN_INSERT, ReviewDecision.INSIGHT_TRIGGERED):
                self.state = AgentState.REPLAN
                logger.info("Replan: %s — %s", review.decision.name, review.reason)
                remaining = planner.apply_review(review, remaining)
            elif review.decision == ReviewDecision.EARLY_CONCLUSION:
                logger.info("Early conclusion: %s", review.reason)
                break
            elif review.decision == ReviewDecision.REPLAN_SKIP:
                logger.info("Skipping steps: %s", review.skip_steps)
                remaining = planner.apply_review(review, remaining)

        return executions

    # ── v2.0: Strategic synthesis with cross-tool correlation ──
    async def _strategic_synthesize(
        self, plan: AnalysisPlan, executions: list[ToolExecution],
        response_mode: str = "detailed",
    ) -> tuple[str, StrategyReport]:
        """Cross-tool synthesis + strategic recommendation generation."""
        from agent.cross_tool_synthesis import CrossToolAnalyzer
        from agent.recommendation_engine import StrategicAdvisor

        # Collect successful results into a dict keyed by tool name.
        results: dict[str, AnalysisResult] = {}
        for e in executions:
            if e.status == "completed" and e.result is not None:
                results[e.tool_name] = e.result

        try:
            analyzer = CrossToolAnalyzer()
            cross_insights = analyzer.analyze(results)
        except Exception:
            logger.exception("Cross-tool rule analysis failed")
            cross_insights = []

        try:
            advisor = StrategicAdvisor(
                results=results,
                cross_tool_insights=cross_insights,
                chain_name=plan.chain_id,
            )
            strategy_report = advisor.generate()
        except Exception:
            logger.exception("Strategic rule report failed")
            strategy_report = StrategyReport(
                chain_name=plan.chain_id,
                tools_executed=len(results),
                tools_failed=sum(e.status == "failed" for e in executions),
                data_limitations=["规则战略报告生成失败，已改用工具证据综合。"],
            )

        # Step 3: Build synthesis text from strategy report
        text_parts = []
        if strategy_report.executive_summary:
            text_parts.append(f"## 战略分析结论\n\n{strategy_report.executive_summary}")

        if strategy_report.key_findings:
            text_parts.append("\n### 关键发现\n")
            for f in strategy_report.key_findings:
                text_parts.append(f"- {f}")

        if strategy_report.recommendations:
            text_parts.append("\n### 策略建议\n")
            for r in strategy_report.recommendations:
                urgency_bar = "█" * r.urgency + "░" * (5 - r.urgency)
                text_parts.append(
                    f"**[{r.category}]** 紧迫度: {urgency_bar}\n"
                    f"> {r.insight}\n\n"
                    f"建议: {r.recommendation}\n"
                )
                if r.next_step:
                    text_parts.append(f"下一步: {r.next_step}\n")

        if strategy_report.risk_factors:
            text_parts.append("\n### 风险因素\n")
            for risk in strategy_report.risk_factors:
                text_parts.append(f"- ⚠️ {risk}")

        if strategy_report.data_limitations:
            text_parts.append("\n### 数据限制\n")
            for limit in strategy_report.data_limitations:
                text_parts.append(f"- 📊 {limit}")

        if strategy_report.followup_analyses:
            text_parts.append("\n### 建议后续分析\n")
            for fa in strategy_report.followup_analyses:
                text_parts.append(f"- → {fa}")

        candidate_text = "\n".join(text_parts)
        evidence_context, coverage = await self._build_evidence_context(executions)
        prompt = self._report_prompt(
            plan, evidence_context, coverage, response_mode,
            candidate_text=candidate_text,
        )
        synthesis_text = await self._call_report_llm(
            prompt, executions, response_mode, candidate_text,
        )
        return synthesis_text, strategy_report

    # ── 综合结论（原始版本，非战略模式时使用） ──
    async def _synthesize(self, plan: AnalysisPlan,
                          executions: list[ToolExecution],
                          response_mode: str = "detailed") -> str:
        """汇总所有 Tool 结果，用 LLM 生成综合结论。

        注意: 必须将实际分析数据摘要传给 LLM，否则 LLM 无法基于真实数据
        写结论，会凭空编造（hallucination）。
        """
        evidence_context, coverage = await self._build_evidence_context(executions)
        prompt = self._report_prompt(
            plan, evidence_context, coverage, response_mode,
        )

        return await self._call_report_llm(
            prompt, executions, response_mode,
            self._deterministic_fallback(executions),
        )

    async def _call_report_llm(
        self, prompt: str, executions: list[ToolExecution],
        response_mode: str, candidate_text: str = "",
    ) -> str:
        """Generate, validate and once repair a final report."""
        response = await self.llm.chat([{"role": "user", "content": prompt}])
        text = response.text.strip()
        if response.finish_reason.lower() in {"length", "max_tokens"}:
            continuation = await self.llm.chat([{
                "role": "user",
                "content": (
                    "以下专利分析报告因长度被截断。请从中断处继续，禁止重复已有段落，"
                    "并确保补全数据限制与后续分析。\n\n已有文本:\n" + text
                ),
            }])
            text = f"{text}\n{continuation.text.strip()}".strip()

        missing = self._report_missing_requirements(text, executions, response_mode)
        if missing:
            repair_prompt = (
                "修复下面的专利分析报告。保留已有事实，只补齐缺失部分，不得编造。"
                f"\n缺失要求: {', '.join(missing)}\n"
                f"原报告:\n{text or candidate_text}\n\n原始任务与证据:\n{prompt}"
            )
            repaired = await self.llm.chat([
                {"role": "user", "content": repair_prompt}
            ])
            text = repaired.text.strip()
            missing = self._report_missing_requirements(text, executions, response_mode)
        if not text or missing:
            candidate = candidate_text.strip()
            if candidate and not self._report_missing_requirements(
                candidate, executions, response_mode,
            ):
                return candidate
            return self._deterministic_fallback(executions)
        return text

    @staticmethod
    def _report_missing_requirements(
        text: str, executions: list[ToolExecution], response_mode: str,
    ) -> list[str]:
        if not text.strip():
            return ["非空核心结论"]
        missing: list[str] = []
        if response_mode == "detailed" and "限制" not in text:
            missing.append("数据限制")
        completed = [e.tool_name for e in executions if e.status == "completed"]
        if response_mode == "detailed" and completed:
            cited = sum(tool in text for tool in completed)
            if cited == 0 and "[" not in text:
                missing.append("工具字段来源标注")
        return missing

    @staticmethod
    def _deterministic_fallback(
        executions: list[ToolExecution], error: str = "",
    ) -> str:
        lines = [
            "## 结构化降级总结",
            "",
            "LLM 综合失败，以下内容直接来自已经完成的工具结果。",
        ]
        if error:
            lines.append(f"综合失败原因：{error}")
        completed = 0
        limitations: list[str] = []
        for execution in executions:
            if execution.status == "completed" and execution.result:
                completed += 1
                summary = execution.result.summary or f"{execution.tool_name} 已完成。"
                lines.extend(["", f"### {execution.tool_name}", summary])
                for warning in execution.result.warnings:
                    limitations.append(f"[{execution.tool_name}] {warning}")
            else:
                limitations.append(
                    f"[{execution.tool_name}] {execution.error or execution.status}"
                )
        if completed == 0:
            lines.extend(["", "没有工具成功返回可综合的结构化结果。"])
        lines.extend(["", "### 数据限制"])
        lines.extend(f"- {item}" for item in (limitations or ["未发现额外工具警告。"]))
        lines.extend(["", "### 后续分析", "- 可在不重新运行工具的情况下重试生成总结。"])
        return "\n".join(lines)

    def _merge_intent_params(self, tool_name: str, params: dict,
                             intent: IntentAnalysis) -> dict:
        """把用户条件传给所有声明了相应参数的工具。"""
        tool = self.tools.get_tool(tool_name)
        keys = set(tool.parameters)
        if intent.time_range:
            if "year_start" in keys:
                params.setdefault("year_start", intent.time_range[0])
            if "year_end" in keys:
                params.setdefault("year_end", intent.time_range[1])
        if intent.applicants and "applicant_filter" in keys:
            params.setdefault("applicant_filter", intent.applicants[0])
        if "query" in keys:
            query = intent.tech_field or intent.goal
            if query:
                params.setdefault("query", query)
        filters = {}
        if intent.time_range:
            filters.update({
                "year_start": intent.time_range[0],
                "year_end": intent.time_range[1],
            })
        if intent.applicants:
            filters["applicant_filter"] = intent.applicants[0]
        if intent.ipc_codes:
            filters["ipc_filter"] = intent.ipc_codes
        if intent.tech_field:
            filters["text_query"] = intent.tech_field
        if filters:
            params["__filters"] = filters
        return params

    @staticmethod
    def _condition_met(condition: str, prior: ToolExecution | None) -> bool:
        if condition == "search_returned_high_risk":
            return bool(prior and prior.result and
                        getattr(prior.result, "total_hits", 0) > 0)
        return bool(prior and prior.status == "completed")

    @staticmethod
    def _skipped_execution(tool_name: str, params: dict,
                           reason: str) -> ToolExecution:
        return ToolExecution(
            id=f"{tool_name}_skipped_{uuid4().hex}",
            tool_name=tool_name, parameters=params, status="skipped",
            error=reason, started_at=datetime.now(), completed_at=datetime.now(),
        )

    async def _build_evidence_context(
        self, executions: list[ToolExecution], chunk_size: int = 12000,
    ) -> tuple[str, list[dict]]:
        """完整读取无 HTML 的分析载荷；大结果逐块提证后再综合。"""
        sections: list[str] = []
        coverage: list[dict] = []
        for execution in executions:
            if not execution.result:
                sections.append(json.dumps({
                    "tool": execution.tool_name, "status": execution.status,
                    "error": execution.error,
                }, ensure_ascii=False))
                coverage.append({
                    "tool": execution.tool_name, "status": execution.status,
                    "fields_read": [], "chunks": 0, "omitted": False,
                })
                continue
            payload = execution.result.model_dump(exclude={"chart_html"})
            raw = json.dumps(payload, ensure_ascii=False, default=str)
            chunks = _safe_text_chunks(raw, chunk_size) or ["{}"]
            field_names = sorted(payload.keys())
            if len(raw) <= chunk_size * 3:
                sections.append(
                    f"## TOOL {execution.tool_name} FULL_PAYLOAD\n{raw}"
                )
            else:
                extracted = []
                for index, chunk in enumerate(chunks, 1):
                    chunk_prompt = (
                        "你是证据提取器。完整阅读下面工具结果分块，逐项保留所有决策相关事实、"
                        "数字、警告、方法和限制；不要生成最终建议。\n"
                        f"工具: {execution.tool_name}; 分块: {index}/{len(chunks)}\n{chunk}"
                    )
                    try:
                        response = await self.llm.chat([
                            {"role": "user", "content": chunk_prompt}
                        ])
                        extracted.append(response.text)
                    except Exception as exc:
                        extracted.append(f"分块提取失败: {exc}; 原始分块: {chunk}")
                sections.append(
                    f"## TOOL {execution.tool_name} CHUNK_EVIDENCE\n" +
                    "\n".join(extracted)
                )
            coverage.append({
                "tool": execution.tool_name,
                "status": execution.status,
                "fields_read": field_names,
                "chunks": len(chunks),
                "omitted": False,
                "source_chars": len(raw),
            })
        return "\n\n".join(sections), coverage

    @staticmethod
    def _execution_event(execution: ToolExecution, turn_id: str) -> dict:
        result_payload = (
            execution.result.model_dump(exclude={"chart_html"})
            if execution.result else None
        )
        return {
            "type": "step", "tool": execution.tool_name,
            "status": execution.status,
            "duration_ms": round(execution.duration_ms),
            "parameters": execution.parameters,
            "chart_html": execution.result.chart_html if execution.result else None,
            "result": result_payload,
            "summary": execution.result.summary if execution.result else "",
            "methodology": execution.result.methodology if execution.result else "",
            "data_quality": execution.result.data_quality if execution.result else {},
            "warnings": execution.result.warnings if execution.result else [],
            "error": execution.error,
            "execution_id": execution.id,
            "origin": execution.origin,
            "reused_from_execution_id": execution.reused_from_execution_id,
            "provider_tool_call_id": execution.provider_tool_call_id,
            "turn_id": turn_id,
        }

    @staticmethod
    def _coverage_manifest(executions: list[ToolExecution],
                           chunk_size: int = 12000) -> list[dict]:
        manifest = []
        for execution in executions:
            if not execution.result:
                manifest.append({
                    "tool": execution.tool_name, "status": execution.status,
                    "fields_read": [], "chunks": 0, "omitted": False,
                })
                continue
            payload = execution.result.model_dump(exclude={"chart_html"})
            size = len(json.dumps(payload, ensure_ascii=False, default=str))
            manifest.append({
                "tool": execution.tool_name, "status": execution.status,
                "fields_read": sorted(payload),
                "chunks": max(1, (size + chunk_size - 1) // chunk_size),
                "omitted": False, "source_chars": size,
            })
        return manifest

    @staticmethod
    def _report_prompt(plan: AnalysisPlan, evidence_context: str,
                       coverage: list[dict], response_mode: str,
                       candidate_text: str = "") -> str:
        if response_mode == "concise":
            structure = "只输出：核心结论、关键数字、数据限制。控制在约 500 字。"
        else:
            structure = (
                "固定包含：核心结论、关键数字、分维度分析、方法说明、数据限制、"
                "建议和后续分析。详细解释结论依据，不要为了简短省略重要证据。"
            )
        return (
            "你是专利分析专家。以下 evidence 是工具结果的完整语义载荷或逐块证据提取。"
            "必须完整阅读，禁止编造；事实后用 [工具名:字段/指标] 标注来源。\n"
            f"分析计划:\n{json.dumps(plan.steps, ensure_ascii=False)}\n"
            f"候选规则洞察（仅供复核，不可替代证据）:\n{candidate_text}\n"
            f"结果覆盖清单:\n{json.dumps(coverage, ensure_ascii=False, indent=2)}\n"
            f"写作模式: {response_mode}. {structure}\n"
            "FTO、有效性和财务价值不得写成正式法律或估值结论。\n\n"
            "不得把公开量写成申请量；不得把近期增长分数称为 Kleinberg Burst；"
            "不得把低共现称为蓝海；不得把 TF-IDF 称为语义嵌入；"
            "不得把 IPC entropy/cosine shift 称为 PatentMiner DICT；"
            "不得仅凭公开增长判断生命周期或技术衰退。\n\n"
            f"EVIDENCE:\n{evidence_context}"
        )

    def _extract_result_summary(self, result) -> dict:
        """从 AnalysisResult 中提取实际数据摘要，供 LLM 写结论。

        只提取统计摘要和代表性样本，不传递全量 raw data。
        """
        rt = getattr(result, 'result_type', 'unknown')
        summary = {"result_type": rt}

        # ── 趋势数据 ──
        if rt in ("monthly_trend", "yearly_trend", "growth_rate"):
            if hasattr(result, 'data') and isinstance(result.data, list) and result.data:
                # 提取首/尾/极值点
                first = result.data[0]
                last = result.data[-1]
                sample = []
                if len(result.data) <= 12:
                    sample = result.data
                else:
                    sample = result.data[:3] + result.data[-3:]
                summary["first"] = first
                summary["last"] = last
                summary["sample"] = sample

        # ── S曲线 ──
        elif rt == "s_curve":
            if hasattr(result, 'years') and result.years:
                summary["year_range"] = f"{min(result.years)}-{max(result.years)}"
                summary["total_cumulative"] = result.cumulative[-1] if result.cumulative else 0
                summary["latest_year_count"] = result.counts[-1] if result.counts else 0
                # 只计算增长信号，不自动映射生命周期阶段。
                if hasattr(result, 'counts') and len(result.counts) >= 2:
                    first_c = result.counts[0]
                    last_c = result.counts[-1]
                    if first_c > 0:
                        n = len(result.counts) - 1
                        cagr = round(((last_c / first_c) ** (1 / max(n, 1)) - 1) * 100, 1)
                        summary["cagr_pct"] = cagr
                        summary["growth_signal"] = (
                            "增长" if cagr > 5 else
                            "基本稳定" if cagr > -5 else "下降，需核验尾年完整性"
                        )

        # ── 词频 ──
        elif rt == "word_freq":
            if hasattr(result, 'data') and isinstance(result.data, list):
                summary["top_words"] = result.data[:15]

        # ── 逐年关键词 ──
        elif rt == "yearly_keywords":
            if hasattr(result, 'data') and isinstance(result.data, dict):
                years = sorted(result.data.keys())
                summary["years"] = years
                # 每年取 top 5
                yearly_sample = {}
                for y in years[-3:]:
                    yearly_sample[str(y)] = result.data[y][:5]
                summary["recent_years"] = yearly_sample

        # ── 突发词 ──
        elif rt == "burst_terms":
            if hasattr(result, 'data') and isinstance(result.data, list):
                summary["top_burst"] = result.data[:10]
                # Add interpreted strength descriptions
                interpreted = []
                for t in result.data[:6]:
                    burst = t.get("burst", 0)
                    desc = "急速上升" if burst > 3 else ("显著增长" if burst > 2 else "稳步增长")
                    interpreted.append(f"{t.get('term','?')}({desc}, burst={burst})")
                summary["burst_interpreted"] = interpreted

        # ── IPC ──
        elif rt == "ipc_matrix":
            if hasattr(result, 'sections') and result.sections:
                summary["sections"] = result.sections
                summary["years"] = result.years[:5] if len(result.years) > 5 else result.years
                # Pre-compute growth per section
                if hasattr(result, 'matrix') and result.matrix and len(result.matrix) >= 2:
                    growths = {}
                    m = result.matrix
                    for si, sec in enumerate(result.sections):
                        if si < len(m[0]):
                            first_val = m[0][si]
                            last_val = m[-1][si]
                            if first_val > 0:
                                pct = round((last_val - first_val) / first_val * 100)
                                growths[sec] = pct
                    growing = sorted(growths.items(), key=lambda x: -x[1])
                    summary["growth_by_section"] = [f"{s}: {p:+d}%" for s, p in growing[:5]]

        elif rt == "ipc_distribution":
            if hasattr(result, 'data') and isinstance(result.data, list):
                summary["top_sections"] = result.data[:8]

        # ── 国家分布 ──
        elif rt == "country_distribution":
            if hasattr(result, 'data') and isinstance(result.data, list):
                total = sum(d.get("count", 0) for d in result.data)
                summary["total_countries"] = len(result.data)
                summary["total_patent_count"] = total
                # Top countries with percentages
                top_with_pct = []
                for d in result.data[:8]:
                    pct = round(d.get("count", 0) / max(total, 1) * 100, 1)
                    top_with_pct.append(f"{d.get('country','?')} {pct}% ({d.get('count',0)}件)")
                summary["top_countries_pct"] = top_with_pct
                # Concentration
                top1 = result.data[0].get("count", 0) if result.data else 0
                top3 = sum(d.get("count", 0) for d in result.data[:3])
                summary["top1_share"] = f"{round(top1 / max(total, 1) * 100, 1)}%"
                summary["top3_share"] = f"{round(top3 / max(total, 1) * 100, 1)}%"

        # ── 合作网络 ──
        elif rt == "co_occurrence":
            summary["node_count"] = getattr(result, 'node_count', 0)
            summary["edge_count"] = getattr(result, 'edge_count', 0)
            if hasattr(result, 'edges') and isinstance(result.edges, list):
                summary["top_edges"] = sorted(
                    result.edges, key=lambda x: x.get("weight", 0), reverse=True,
                )[:10]

        # ── 路线图 ──
        elif rt == "roadmap":
            if hasattr(result, 'data') and isinstance(result.data, dict):
                summary["years"] = sorted(result.data.keys())
                # 最近一年专利
                if summary["years"]:
                    latest = str(max(int(y) for y in summary["years"]))
                    patents = result.data.get(int(latest), [])[:3]
                    summary[f"sample_{latest}"] = patents

        # ── 数据集概况 ──
        elif rt == "dataset_summary":
            if hasattr(result, 'total_patents'):
                summary["total_patents"] = result.total_patents
            if hasattr(result, 'year_start'):
                summary["year_range"] = f"{result.year_start} - {result.year_end}"
            if hasattr(result, 'ipc_sections'):
                summary["ipc_sections"] = result.ipc_sections
            if hasattr(result, 'top_applicants'):
                summary["top_applicants"] = result.top_applicants[:10]

        # ── 聚类 ──
        elif rt == "clustering":
            summary["n_clusters"] = len(getattr(result, 'cluster_keywords', {}))
            kw = getattr(result, 'cluster_keywords', {})
            counts = getattr(result, 'patents_per_cluster', {})
            # Find largest cluster
            if counts:
                largest = max(counts.items(), key=lambda x: x[1])
                largest_kw = ', '.join(kw.get(int(largest[0]), [])[:5])
                summary["largest_cluster"] = f"簇{largest[0]} ({largest[1]}件): {largest_kw}"
                # All clusters as readable strings
                cluster_list = []
                for cid in sorted(kw.keys()):
                    kws = ', '.join(kw[cid][:5])
                    cnt = counts.get(int(cid), 0)
                    cluster_list.append(f"簇{cid}({cnt}件): {kws}")
                summary["cluster_summary"] = cluster_list
            else:
                summary["keywords_per_cluster"] = kw

        # ── 价值评估 ──
        elif rt == "value_indicators":
            if hasattr(result, 'data') and isinstance(result.data, list):
                summary["top_patents"] = result.data[:10]

        # ── 功效矩阵 ──
        elif rt == "tech_effect_matrix":
            functions = getattr(result, 'functions', [])[:15]
            effects = getattr(result, 'effects', [])[:10]
            summary["function_count"] = len(functions)
            summary["effect_count"] = len(effects)
            summary["function_preview"] = functions[:8]
            summary["effect_preview"] = effects[:8]
            if hasattr(result, 'matrix') and result.matrix:
                import numpy as np
                m = np.array(result.matrix)
                if m.size > 0:
                    # Find hottest combos
                    flat_indices = np.argsort(m.flatten())[::-1][:5]
                    hottest = []
                    rows, cols = m.shape
                    for idx in flat_indices:
                        r, c = int(idx) // cols, int(idx) % cols
                        if r < len(functions) and c < len(effects):
                            hottest.append(f"{functions[r]}×{effects[c]}: {int(m[r, c])}件")
                    summary["hottest_combos"] = hottest
                    # Find coldest
                    cold_indices = np.argsort(m.flatten())[:5]
                    coldest = []
                    for idx in cold_indices:
                        r, c = int(idx) // cols, int(idx) % cols
                        if r < len(functions) and c < len(effects):
                            coldest.append(f"{functions[r]}×{effects[c]}: {int(m[r, c])}件")
                    summary["coldest_combos"] = coldest
            # 空白点推荐
            gaps = getattr(result, 'gap_recommendations', [])
            if gaps:
                summary["top_gaps"] = [
                    f"{g['function']}×{g['effect']}({g['patent_count']}件)"
                    for g in gaps[:5]
                ]

        # ── 检索结果 ──
        elif rt == "patent_search":
            summary["total_hits"] = getattr(result, 'total_hits', 0)
            if hasattr(result, 'patents') and isinstance(result.patents, list):
                summary["top_results"] = result.patents[:10]

        return summary

    # ── 辅助 ──
    def _format_plan_summary(self, plan: AnalysisPlan) -> str:
        """格式化分析计划为可读文本"""
        lines = ["## 分析计划", ""]
        for s in plan.steps:
            tool = s.get("tool", "?")
            reason = s.get("reason", "")
            params = s.get("params", {})
            lines.append(f"**{s.get('step', '?')}.** `{tool}`")
            if reason:
                lines.append(f"  > {reason}")
            if params:
                lines.append(f"  参数: {json.dumps(params, ensure_ascii=False)}")
            lines.append("")
        if plan.estimated_tokens:
            lines.append(f"预估 Token: {plan.estimated_tokens:,}")
        lines.append("")
        lines.append("请点击「确认执行」开始分析，或「修改计划」调整步骤。")
        return "\n".join(lines)


    async def execute_complex(self, user_message: str,
                              session=None) -> "AgentResponse":
        """委托给 MultiAgentOrchestrator 进行多 Agent 协作分析。

        用于复杂查询，由 Search Agent + Analysis Agent 并行工作，
        再由 Report Agent 汇总。
        """
        from agent.multi_agent import MultiAgentOrchestrator

        multi = MultiAgentOrchestrator(
            llm_client=self.llm,
            tool_registry=self.tools,
        )
        report = await multi.execute_complex_analysis(
            user_query=user_message,
            session=session,
        )

        report_text = report.get("summary", "")
        return AgentResponse(text=report_text, plan={})


def build_default_knowledge() -> dict:
    """只从机器可读的工具算法证据登记表加载 AI 方法知识。"""
    knowledge = {}
    try:
        from tools.evidence import load_evidence_registry
        knowledge["tool_evidence_registry"] = load_evidence_registry()
        knowledge["methodology_summary"] = json.dumps(
            knowledge["tool_evidence_registry"], ensure_ascii=False,
        )
    except (OSError, ValueError):
        knowledge["tool_evidence_registry"] = {}
        knowledge["methodology_summary"] = "工具算法证据登记表未加载。"
    return knowledge
