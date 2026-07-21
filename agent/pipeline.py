"""Composable Agent pipeline responsibilities.

These classes intentionally have no FastAPI or persistence dependencies so
tests can replace planning, execution and validation independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from models.session import ToolExecution


@dataclass(frozen=True)
class PlannerContext:
    user_message: str
    history: list[dict]
    dataset: Any
    historical_evidence: list[dict]
    allow_over_budget: bool = False


class IntentParser:
    """Extract only deterministic control intent; the LLM still selects tools."""

    _APPROVAL_TOKENS = ("确认执行", "同意执行", "按计划执行")

    def context(
        self, user_message: str, history: list[dict], dataset: Any,
        historical_evidence: list[dict],
    ) -> PlannerContext:
        return PlannerContext(
            user_message=user_message,
            history=history,
            dataset=dataset,
            historical_evidence=historical_evidence,
            allow_over_budget=any(token in user_message for token in self._APPROVAL_TOKENS),
        )


class Planner:
    def __init__(self, select_tools: Callable[..., Awaitable[Any]]):
        self._select_tools = select_tools

    async def plan(self, context: PlannerContext):
        return await self._select_tools(
            context.user_message,
            context.history,
            context.dataset,
            context.historical_evidence,
            allow_over_budget=context.allow_over_budget,
        )


@dataclass(frozen=True)
class ExecutionPolicy:
    max_tools: int = 4
    max_cost_weight: int = 6

    def requires_confirmation(
        self, tool_count: int, cost_weight: int, approved: bool = False,
    ) -> bool:
        return not approved and (
            tool_count > self.max_tools or cost_weight > self.max_cost_weight
        )


class ToolExecutor:
    """Select the modern or explicit legacy executor without planning policy."""

    async def execute(
        self, plan: Any, dataset: Any, *, modern: Callable[..., Awaitable[list]],
        legacy: Callable[..., Awaitable[list]], legacy_mode: bool,
        reuse_lookup=None, on_execution=None,
    ) -> list[ToolExecution]:
        callback = legacy if legacy_mode else modern
        return await callback(
            plan, dataset, reuse_lookup=reuse_lookup, on_execution=on_execution,
        )


class ResultValidator:
    """Enforce that only validated, traceable results reach the synthesizer."""

    def validate(self, executions: list[ToolExecution]) -> list[str]:
        errors: list[str] = []
        for execution in executions:
            if execution.status != "completed":
                continue
            if execution.result is None:
                errors.append(f"{execution.tool_name}: completed without result")
                continue
            provenance = getattr(execution.result, "provenance", None)
            if provenance is None and execution.origin not in {"reused", "restored"}:
                errors.append(f"{execution.tool_name}: missing provenance")
        return errors


class AnswerSynthesizer:
    def __init__(self, validator: ResultValidator):
        self._validator = validator

    def assert_validated(self, executions: list[ToolExecution]) -> None:
        errors = self._validator.validate(executions)
        if errors:
            raise ValueError("RESULT_VALIDATION_FAILED: " + "; ".join(errors))
