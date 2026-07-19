"""Adaptive planner with closed-loop FSM and intermediate review.

Upgrades the existing linear IDLE→...→DONE state machine to support:
  - INTERMEDIATE_REVIEW: assess findings after each tool, decide next action
  - REPLAN: dynamically insert/remove/skip steps based on data
  - SKIP: skip downstream steps when prerequisite data is missing
  - EARLY_CONCLUSION: stop early when findings are sufficient
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from models.session import ToolExecution

logger = logging.getLogger(__name__)


class ReviewDecision(Enum):
    CONTINUE = auto()            # Proceed as planned
    REPLAN_INSERT = auto()       # Insert new steps before continuing
    REPLAN_SKIP = auto()         # Skip some remaining steps
    EARLY_CONCLUSION = auto()    # Stop early, synthesize now
    DATA_GAP = auto()            # Data missing, skip dependent steps
    INSIGHT_TRIGGERED = auto()   # Interesting finding, add related analysis


@dataclass
class ReviewResult:
    decision: ReviewDecision
    reason: str = ""
    new_steps: list[dict] = field(default_factory=list)   # steps to insert
    skip_steps: list[str] = field(default_factory=list)    # tool names to skip


class AdaptivePlanner:
    """Wraps the execution loop with intermediate review checkpoints.

    After each tool execution, evaluates whether the plan should adapt:
      - New insights may trigger additional analysis (REPLAN_INSERT)
      - Missing data may invalidate downstream steps (REPLAN_SKIP / DATA_GAP)
      - Sufficient findings may allow early conclusion (EARLY_CONCLUSION)
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.review_history: list[ReviewResult] = []

    async def review_intermediate(
        self,
        current_step: dict,
        execution: ToolExecution,
        remaining_steps: list[dict],
        all_executions: list[ToolExecution],
    ) -> ReviewResult:
        """After executing one step, assess whether to adapt the plan.

        Uses rule-based heuristics in combination with optional LLM reasoning.
        Falls back to CONTINUE when neither can make a confident decision.
        """
        # ── Rule-based checks first (fast, no LLM cost) ──

        # Check 1: Did the tool fail?
        if execution.status == "failed":
            error = execution.error or ""
            if "year" in error or "column" in error.lower():
                return ReviewResult(
                    decision=ReviewDecision.DATA_GAP,
                    reason=f"数据缺少必要字段: {error[:100]}",
                )
            return ReviewResult(
                decision=ReviewDecision.CONTINUE,
                reason=f"工具 {execution.tool_name} 执行失败，但继续后续步骤",
            )

        # Check 2: Empty result — skip downstream steps that depend on this one
        if execution.result is None:
            dependent_steps = [
                s for s in remaining_steps
                if s.get("params", {}).get("_depends_on") == current_step.get("tool", "")
            ]
            if dependent_steps:
                return ReviewResult(
                    decision=ReviewDecision.REPLAN_SKIP,
                    reason=f"工具 {execution.tool_name} 无结果，跳过相关步骤",
                    skip_steps=[s.get("tool", "") for s in dependent_steps],
                )
            return ReviewResult(decision=ReviewDecision.CONTINUE)

        # Check 3: Data-driven triggers
        result = execution.result
        rt = getattr(result, 'result_type', '')

        # If clustering returned distinct clusters with clear themes → add tech_matrix
        if rt == "clustering":
            cluster_kw = getattr(result, 'cluster_keywords', {})
            if len(cluster_kw) >= 2:
                already_planned = {s.get("tool", "") for s in remaining_steps}
                if "analyze_tech_matrix" not in already_planned:
                    return ReviewResult(
                        decision=ReviewDecision.INSIGHT_TRIGGERED,
                        reason="聚类分析发现了明确的技术主题群组，建议追加功效矩阵分析以发现各主题的空白点",
                        new_steps=[{
                            "step": "追加",
                            "tool": "analyze_tech_matrix",
                            "params": {},
                            "reason": "基于聚类发现的多个技术主题，分析各主题的功效矩阵空白点",
                        }],
                    )

        # If burst terms found → add yearly keywords for temporal tracking
        if rt == "burst_terms":
            burst_data = getattr(result, 'data', [])
            if isinstance(burst_data, list) and len(burst_data) >= 3:
                already_planned = {s.get("tool", "") for s in remaining_steps}
                if "analyze_yearly_keywords" not in already_planned:
                    return ReviewResult(
                        decision=ReviewDecision.INSIGHT_TRIGGERED,
                        reason="突发词检测发现多个快速增长的关键词，建议追加逐年关键词分析以追踪热点迁移轨迹",
                        new_steps=[{
                            "step": "追加",
                            "tool": "analyze_yearly_keywords",
                            "params": {},
                            "reason": "突发词增长信号需要逐年数据验证一致性",
                        }],
                    )

        # If trend shows strong growth → ensure lifecycle is in the plan
        if rt in ("monthly_trend", "yearly_trend"):
            trend_data = getattr(result, 'data', [])
            if isinstance(trend_data, list) and len(trend_data) >= 3:
                counts = [d.get('count', 0) for d in trend_data[-3:]]
                if len(counts) >= 3 and counts[-1] > counts[-3] * 1.3:
                    already_planned = {s.get("tool", "") for s in remaining_steps}
                    if "analyze_lifecycle" not in already_planned:
                        return ReviewResult(
                            decision=ReviewDecision.INSIGHT_TRIGGERED,
                            reason="趋势显示30%以上增长，建议追加累计公开量与同比分析验证一致性",
                            new_steps=[{
                                "step": "追加",
                                "tool": "analyze_lifecycle",
                                "params": {},
                                "reason": "快速增长趋势需要累计量与同比序列验证一致性",
                            }],
                        )

        # Check 4: Enough data collected → early conclusion
        if len(all_executions) >= 4 and not remaining_steps:
            completed = sum(1 for e in all_executions if e.status == "completed")
            if completed >= 3:
                return ReviewResult(
                    decision=ReviewDecision.EARLY_CONCLUSION,
                    reason=f"已成功执行 {completed} 个分析步骤，数据充分，可以综合结论",
                )

        # ── Default: continue as planned ──
        return ReviewResult(decision=ReviewDecision.CONTINUE)

    def apply_review(self, review: ReviewResult,
                     remaining_steps: list[dict]) -> list[dict]:
        """Apply the review decision to modify the remaining plan steps."""
        if review.decision == ReviewDecision.REPLAN_SKIP:
            skip_names = set(review.skip_steps)
            return [s for s in remaining_steps if s.get("tool", "") not in skip_names]

        if review.decision in (
            ReviewDecision.REPLAN_INSERT, ReviewDecision.INSIGHT_TRIGGERED,
        ):
            return review.new_steps + remaining_steps

        if review.decision == ReviewDecision.EARLY_CONCLUSION:
            return []  # Empty → trigger synthesis

        return remaining_steps  # CONTINUE, DATA_GAP, INSIGHT_TRIGGERED
