"""Strategic recommendation generator.

Translates cross-tool insights and analysis results into decision-oriented
recommendations with urgency, confidence, and actionable next steps.

Seven recommendation categories:
  R&D_INVESTMENT     — Where to invest R&D resources
  PATENT_FILING       — Where/when to file patent applications
  RISK_MITIGATION     — How to reduce infringement risk
  TALENT_ACQUISITION  — Which inventors/teams to watch or recruit
  LICENSING           — Which patents to license out
  PORTFOLIO_PRUNE     — Which patents to abandon
  PARTNERSHIP         — Which organizations to collaborate with
"""

import json
import logging
import os
from typing import Optional

from models.analysis_results import (
    AnalysisResult, CrossToolInsight, StrategicRecommendation,
    StrategyReport, SCurveResult, TechEffectMatrix,
    ValueIndicators, ClusteringResult, BurstTermResult,
    CoOccurrenceResult,
)

logger = logging.getLogger(__name__)

# Load strategy patterns at module level
_STRATEGY_PATTERNS: list[dict] = []


def _load_strategy_patterns() -> list[dict]:
    global _STRATEGY_PATTERNS
    if _STRATEGY_PATTERNS:
        return _STRATEGY_PATTERNS
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "knowledge", "strategy_patterns.json",
    )
    try:
        with open(path, "r") as f:
            _STRATEGY_PATTERNS = json.load(f)
    except FileNotFoundError:
        _STRATEGY_PATTERNS = []
    return _STRATEGY_PATTERNS


class StrategicAdvisor:
    """Generates strategic recommendations from analysis results."""

    def __init__(self, results: dict[str, AnalysisResult],
                 cross_tool_insights: list[CrossToolInsight],
                 chain_name: str = ""):
        self.results = results
        self.cross_insights = cross_tool_insights
        self.chain_name = chain_name
        self.recommendations: list[StrategicRecommendation] = []
        self.risk_factors: list[str] = []
        self.data_limitations: list[str] = []

    def generate(self) -> StrategyReport:
        """Run all recommendation generators and produce a StrategyReport."""
        self.recommendations = []
        self.risk_factors = []
        self.data_limitations = []

        self._recommend_rd_investment()
        self._recommend_patent_filing()
        self._recommend_portfolio_prune()
        self._recommend_licensing()
        self._recommend_risk_mitigation()
        self._recommend_talent()
        self._recommend_partnership()

        # Build executive summary from recommendations
        exec_parts = []
        if self.recommendations:
            top_recs = sorted(self.recommendations, key=lambda r: r.urgency, reverse=True)[:3]
            exec_parts.append("核心建议: " + "; ".join(
                f"[{r.category}] {r.recommendation[:80]}"
                for r in top_recs
            ))

        if self.risk_factors:
            exec_parts.append(f"风险提示: {len(self.risk_factors)} 项风险因素需关注")

        if self.data_limitations:
            exec_parts.append(f"数据限制: {len(self.data_limitations)} 项分析受数据可用性限制")

        # Build key findings from cross-tool insights
        key_findings = [ci.description for ci in self.cross_insights]

        # Build followup recommendations
        followups = self._suggest_followup_analyses()

        return StrategyReport(
            result_type="strategy_report",
            executive_summary="\n".join(exec_parts) if exec_parts else "分析完成",
            key_findings=key_findings,
            recommendations=self.recommendations,
            risk_factors=self.risk_factors,
            data_limitations=self.data_limitations,
            cross_tool_insights=self.cross_insights,
            followup_analyses=followups,
            chain_name=self.chain_name,
            tools_executed=sum(1 for r in self.results.values() if r is not None),
            tools_failed=0,
        )

    # ── Category-specific recommenders ──

    def _recommend_rd_investment(self):
        """R&D investment recommendations based on lifecycle + trend + gaps."""
        lifecycle = self.results.get("analyze_lifecycle")
        trend = self.results.get("analyze_patent_trend")
        matrix = self.results.get("analyze_tech_matrix")

        if not lifecycle and not trend:
            self.data_limitations.append("缺少趋势/生命周期数据，无法生成R&D投资建议")
            return

        # 只描述近期公开量信号，不从公开量曲线推断生命周期阶段。
        growth_signal = "未知"
        recent_growth = None
        if lifecycle and hasattr(lifecycle, 'counts') and lifecycle.counts:
            counts = lifecycle.counts
            if len(counts) >= 3:
                recent_growth = (counts[-1] - counts[-3]) / max(counts[-3], 1)
                if recent_growth > 0.3:
                    growth_signal = "近期公开量快速增长"
                elif recent_growth > 0.1:
                    growth_signal = "近期公开量增长"
                elif recent_growth > -0.1:
                    growth_signal = "近期公开量基本稳定"
                else:
                    growth_signal = "近期公开量下降"

        # Check for gaps in tech-effect matrix
        has_gaps = False
        gap_desc = ""
        if matrix:
            gaps = (getattr(matrix, 'gap_recommendations', []) or
                    getattr(matrix, '_gap_recommendations', []))
            if gaps:
                has_gaps = True
                top_gap = gaps[0]
                gap_desc = f"待复核低共现候选: {top_gap.get('function','?')} × {top_gap.get('effect','?')}"

        if recent_growth is not None and recent_growth > 0.1:
            self.recommendations.append(StrategicRecommendation(
                category="R&D_INVESTMENT",
                insight=f"{growth_signal}（两年窗口变化 {recent_growth:+.1%}）",
                recommendation=(
                    "建议结合市场、权利要求和竞争者数据评估是否增加研发投入。"
                    + (f" {gap_desc}" if has_gaps else "")
                ),
                urgency=4,
                confidence=3,
                supporting_tools=["analyze_lifecycle", "analyze_patent_trend"],
                alternative="如果研发资源有限，优先关注功效矩阵中的空白点方向",
                next_step="对Top 3空白点方向进行深度技术调研",
            ))
        elif recent_growth is not None and recent_growth >= -0.1:
            self.recommendations.append(StrategicRecommendation(
                category="R&D_INVESTMENT",
                insight=f"{growth_signal}（两年窗口变化 {recent_growth:+.1%}）",
                recommendation="建议选择性投入：聚焦高价值细分方向，或探索下一代替代技术",
                urgency=3,
                confidence=3,
                supporting_tools=["analyze_lifecycle"],
                alternative="关注突发词检测结果，寻找潜在的新兴替代技术",
                next_step="运行突发词检测和功效矩阵分析，寻找差异化方向",
            ))
        elif recent_growth is not None:
            self.recommendations.append(StrategicRecommendation(
                category="R&D_INVESTMENT",
                insight=f"{growth_signal}（两年窗口变化 {recent_growth:+.1%}）",
                recommendation="先核验尾年完整性、公开滞后与检索范围；在核验前不要直接减少投入，不能仅凭公开量下降作撤资判断",
                urgency=3,
                confidence=2,
                supporting_tools=["analyze_lifecycle"],
                alternative="评估可转让或许可的专利价值，通过运营回收研发成本",
                next_step="运行专利价值评估，筛选可许可专利",
            ))

    def _recommend_patent_filing(self):
        """Patent filing strategy based on IPC gaps and competitor coverage."""
        ipc = self.results.get("analyze_ipc_distribution")
        matrix = self.results.get("analyze_tech_matrix")

        if not ipc and not matrix:
            return

        gaps = []
        if matrix:
            gaps = (getattr(matrix, 'gap_recommendations', []) or
                    getattr(matrix, '_gap_recommendations', []))

        if gaps and len(gaps) >= 3:
            gap_strs = [
                f"{g['function']}×{g['effect']}"
                for g in gaps[:3]
            ]
            self.recommendations.append(StrategicRecommendation(
                category="PATENT_FILING",
                insight=f"功效矩阵发现 {len(gaps)} 个技术空白点",
                recommendation=(
                    f"建议优先在以下方向申请专利: {', '.join(gap_strs)}。"
                    f"这些方向目前专利密度低，是构建专利壁垒的窗口期"
                ),
                urgency=4,
                confidence=3,
                supporting_tools=["analyze_tech_matrix"],
                alternative="如海外布局意向，建议同步提交PCT申请",
                next_step="针对各空白方向，编写高质量专利申请文件",
            ))

    def _recommend_portfolio_prune(self):
        """Identify low-value patents for potential abandonment."""
        valuation = self.results.get("analyze_patent_valuation")

        if not valuation:
            return

        val_data = getattr(valuation, 'data', [])
        if not val_data:
            return

        # Count low-value patents (those without strong citation metrics)
        low_value_count = 0
        for p in val_data:
            if isinstance(p, dict):
                citation_count = p.get('citation_count', 0) or 0
                family_size = p.get('family_size', 0) or 0
                if citation_count <= 1 and family_size <= 2:
                    low_value_count += 1

        if low_value_count > 0:
            # Rough estimate: ~$500/year maintenance per patent family
            estimated_savings = low_value_count * 500
            self.recommendations.append(StrategicRecommendation(
                category="PORTFOLIO_PRUNE",
                insight=f"评估发现 {low_value_count} 件专利引证极少且同族规模小",
                recommendation=(
                    f"建议对 {low_value_count} 件低价值专利进行人工复核。"
                    f"若确认无战略价值，放弃维护可节省约 ${estimated_savings:,}/年"
                ),
                urgency=2,
                confidence=3,
                supporting_tools=["analyze_patent_valuation"],
                alternative="部分专利可能具有防御价值，建议法务团队介入最终判断",
                next_step="导出低价值专利清单，交由技术专家和法务团队复核",
            ))

    def _recommend_licensing(self):
        """Identify patents suitable for out-licensing."""
        valuation = self.results.get("analyze_patent_valuation")

        if not valuation:
            return

        val_data = getattr(valuation, 'data', [])
        if not val_data:
            return

        # High-value patents with large family → licensing candidates
        licensing_candidates = []
        for p in val_data[:10]:
            if isinstance(p, dict):
                score = p.get('score', 0) or 0
                family = p.get('family_size', 0) or 0
                if score > 60 and family >= 3:
                    pn = p.get('patent_number', '?')
                    licensing_candidates.append(pn)

        if licensing_candidates:
            self.recommendations.append(StrategicRecommendation(
                category="LICENSING",
                insight=(
                    f"{len(licensing_candidates)} 件专利具有高价值+大同族特征"
                ),
                recommendation=(
                    f"以下专利适合对外许可或交叉许可: "
                    f"{', '.join(licensing_candidates[:3])}。"
                    f"高价值+大同族意味着该技术在多个市场受保护，许可价值高"
                ),
                urgency=3,
                confidence=3,
                supporting_tools=["analyze_patent_valuation"],
                alternative="也可考虑专利转让，一次性回收研发成本",
                next_step="委托专利经纪人或许可平台评估市场价值",
            ))

    def _recommend_risk_mitigation(self):
        """FTO risk mitigation recommendations."""
        search = self.results.get("search_patents")
        if not search:
            return

        total_hits = getattr(search, 'total_hits', 0) or 0
        if total_hits == 0:
            return

        self.recommendations.append(StrategicRecommendation(
            category="RISK_MITIGATION",
            insight=f"TF-IDF 词项检索筛出 {total_hits} 件相关专利",
            recommendation=(
                f"建议对前 {min(total_hits, 10)} 件高相关专利进行深度分析，"
                f"逐一比对独立权利要求的必要技术特征，评估侵权风险等级"
            ),
            urgency=4,
            confidence=2,
            supporting_tools=["search_patents"],
            alternative=(
                "如果专利数量大，优先分析被引次数高且同族覆盖目标市场的专利"
            ),
            next_step="调用 read_patent_details 获取高风险专利的权利要求全文",
        ))

    def _recommend_talent(self):
        """Talent identification from inventor data."""
        network = self.results.get("analyze_co_network")

        if not network:
            return

        edges = getattr(network, 'edges', []) or []
        nodes = getattr(network, 'node_count', 0) or 0

        if nodes > 0 and edges:
            # Find the most connected node (hub)
            degree = {}
            for e in edges:
                src = e.get('source', '')
                tgt = e.get('target', '')
                degree[src] = degree.get(src, 0) + 1
                degree[tgt] = degree.get(tgt, 0) + 1
            if degree:
                top_node = max(degree, key=degree.get)
                self.recommendations.append(StrategicRecommendation(
                    category="TALENT_ACQUISITION",
                    insight=f"合作网络中 '{top_node}' 是核心节点（连接数 {degree[top_node]}）",
                    recommendation=(
                        f"'{top_node}' 在合作网络中处于枢纽位置，可能是核心研发团队或关键合作方。"
                        f"建议关注该节点的最新专利动向"
                    ),
                    urgency=2,
                    confidence=3,
                    supporting_tools=["analyze_co_network"],
                    alternative="如为核心人才，可考虑通过合作或招聘获取其技术能力",
                    next_step="通过专利发明人信息进一步核实该节点的具体身份",
                ))

    def _recommend_partnership(self):
        """Partnership recommendations from co-applicant network analysis."""
        network = self.results.get("analyze_co_network")

        if not network:
            return

        edges = getattr(network, 'edges', []) or []

        if edges:
            # Find cross-type collaborations (e.g., company + university)
            top_edge = sorted(edges, key=lambda e: e.get('weight', 0), reverse=True)
            if top_edge:
                e = top_edge[0]
                src = e.get('source', '')
                tgt = e.get('target', '')
                w = e.get('weight', 0)
                self.recommendations.append(StrategicRecommendation(
                    category="PARTNERSHIP",
                    insight=f"最强合作关系: {src} — {tgt}（联合申请 {w} 件）",
                    recommendation=(
                        f"'{src}' 与 '{tgt}' 合作紧密。"
                        f"建议评估是否可通过类似合作模式加速技术研发"
                    ),
                    urgency=2,
                    confidence=3,
                    supporting_tools=["analyze_co_network"],
                    alternative="关注其他潜在合作伙伴，扩展产学研网络",
                    next_step="深入分析该合作关系产出的专利质量和方向",
                ))

    def _suggest_followup_analyses(self) -> list[str]:
        """Suggest follow-up analyses based on what was covered vs. what's missing."""
        executed_tools = set(self.results.keys())
        all_dimensions = {
            "analyze_yearly_keywords": "逐年关键词对比，看技术热点的时间迁移",
            "analyze_tech_roadmap": "技术路线图，看核心技术的时间演进",
            "analyze_burst_terms": "突发词检测，识别快速兴起的新技术方向",
            "analyze_clustering": "专利聚类，发现数据中隐藏的技术主题",
        }

        followups = []
        for tool_name, desc in all_dimensions.items():
            if tool_name not in executed_tools:
                followups.append(desc)

        return followups[:3]  # Top 3 most important gaps
