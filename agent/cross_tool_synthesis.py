"""Cross-tool correlation engine.

Takes results from multiple independent tool executions and discovers
insights that no single tool could reveal alone. Feeds into the
strategic recommendation generator.

Key correlation methods:
  correlate_trend_ipc       — Which IPC sections are driving growth?
  correlate_clusters_value  — Where do high-value patents cluster?
  correlate_matrix_burst    — Do emerging keywords match blank spots?
  detect_anomalies          — Contradictory signals across tools?
  rank_opportunities        — Prioritised innovation directions
  competitive_positioning   — Applicant-level tech advantage map
"""

import logging
from typing import Any

from models.analysis_results import (
    AnalysisResult, CrossToolInsight,
    YearlyTrendResult, MonthlyTrendResult,
    IPCMatrixResult, IPCDistributionResult,
    WordFreqResult, BurstTermResult,
    ClusteringResult, TechEffectMatrix,
    ValueIndicators, SCurveResult,
    CoOccurrenceResult, CountryDistResult,
)

logger = logging.getLogger(__name__)


class CrossToolAnalyzer:
    """Discovers cross-tool insights by correlating independent analysis results."""

    def __init__(self):
        self.insights: list[CrossToolInsight] = []

    def analyze(self, results: dict[str, AnalysisResult]) -> list[CrossToolInsight]:
        """Run all available correlation methods on the result set."""
        self.insights = []

        # Trend + IPC: growth driver analysis
        self._correlate_trend_ipc(results)

        # Trend + Lifecycle: validate and enrich stage assessment
        self._correlate_trend_lifecycle(results)

        # Clustering + Valuation: high-value cluster identification
        self._correlate_clusters_value(results)

        # Tech Matrix + Burst Terms: emerging opportunities
        self._correlate_matrix_burst(results)

        # Anomaly detection: contradictory signals
        self._detect_anomalies(results)

        # Opportunity ranking
        self._rank_opportunities(results)

        return self.insights

    # ── Individual correlation methods ──

    def _correlate_trend_ipc(self, results: dict[str, Any]):
        """Which IPC sections are driving the overall patent growth trend?"""
        trend = results.get("analyze_patent_trend")
        ipc = results.get("analyze_ipc_distribution")

        if not trend or not ipc:
            return

        # Extract trend direction
        trend_data = getattr(trend, 'data', [])
        if isinstance(trend_data, list) and len(trend_data) >= 2:
            first_count = trend_data[0].get('count', 0) if isinstance(trend_data[0], dict) else 0
            last_count = trend_data[-1].get('count', 0) if isinstance(trend_data[-1], dict) else 0
            if first_count > 0:
                growth_pct = round((last_count - first_count) / first_count * 100, 1)
            else:
                growth_pct = 0.0
        else:
            growth_pct = 0.0

        # Extract top IPC sections from matrix
        sections = []
        if hasattr(ipc, 'matrix') and hasattr(ipc, 'sections'):
            m = ipc.matrix
            if m and ipc.sections and len(m) > 0 and len(m[0]) > 0:
                # Sum each section across all years
                for i, section in enumerate(ipc.sections):
                    total = sum(row[i] for row in m if i < len(row))
                    sections.append((section, total))
                sections.sort(key=lambda x: x[1], reverse=True)

        direction = "上升" if growth_pct > 0 else "下降"
        top_sections = [s[0] for s in sections[:3]]

        if top_sections and growth_pct != 0:
            self.insights.append(CrossToolInsight(
                insight_type="trend_vs_ipc",
                description=(
                    f"专利公开量{'{:.1f}%'.format(abs(growth_pct))}{direction}。"
                    f"增长主要由 {', '.join(top_sections)} 部驱动"
                ),
                source_tools=["analyze_patent_trend", "analyze_ipc_distribution"],
                confidence=min(abs(growth_pct) / 50, 1.0),
            ))

    def _correlate_trend_lifecycle(self, results: dict[str, Any]):
        """Validate lifecycle stage against trend direction."""
        trend = results.get("analyze_patent_trend")
        lifecycle = results.get("analyze_lifecycle")

        if not trend or not lifecycle:
            return

        # Get trend data
        trend_data = getattr(trend, 'data', [])
        years_data = [d.get('year', 0) for d in trend_data] if isinstance(trend_data, list) and trend_data else []

        # Get lifecycle years
        lc_years = getattr(lifecycle, 'years', [])

        # Check if trend years match lifecycle years for data consistency
        if years_data and lc_years:
            overlap = set(years_data) & set(lc_years)
            if not overlap:
                self.insights.append(CrossToolInsight(
                    insight_type="trend_vs_lifecycle",
                    description="趋势分析和生命周期分析的年份范围不匹配，可能使用不同的数据切片",
                    source_tools=["analyze_patent_trend", "analyze_lifecycle"],
                    confidence=0.8,
                ))

    def _correlate_clusters_value(self, results: dict[str, Any]):
        """Which technology clusters contain the highest-value patents?"""
        clustering = results.get("analyze_clustering")
        valuation = results.get("analyze_patent_valuation")

        if not clustering or not valuation:
            return

        cluster_kw = getattr(clustering, 'cluster_keywords', {})
        val_data = getattr(valuation, 'data', [])

        if not cluster_kw or not val_data:
            return

        # Summarize: which clusters exist and how many patents each
        patents_per = getattr(clustering, 'patents_per_cluster', {})
        cluster_summary = []
        for cid, kws in sorted(cluster_kw.items()):
            count = patents_per.get(int(cid), 0)
            top_kw = ', '.join(kws[:3]) if kws else '未知'
            cluster_summary.append(f"簇{cid}({count}件): {top_kw}")

        top_patents = val_data[:3] if val_data else []
        if cluster_summary and top_patents:
            self.insights.append(CrossToolInsight(
                insight_type="cluster_vs_value",
                description=(
                    f"专利文本自动聚类为 {len(cluster_summary)} 个技术主题: "
                    + "; ".join(cluster_summary[:4])
                ),
                source_tools=["analyze_clustering", "analyze_patent_valuation"],
                confidence=0.7,
            ))

    def _correlate_matrix_burst(self, results: dict[str, Any]):
        """Do emerging keywords (burst terms) overlap with tech-effect matrix gaps?"""
        matrix = results.get("analyze_tech_matrix")
        burst = results.get("analyze_burst_terms")

        if not matrix or not burst:
            return

        m_functions = set(getattr(matrix, 'functions', []))
        m_effects = set(getattr(matrix, 'effects', []))
        burst_terms = []
        burst_data = getattr(burst, 'data', [])
        if isinstance(burst_data, list):
            burst_terms = [t.get('term', '') for t in burst_data[:5]]

        # Check overlap between burst terms and matrix dimensions
        overlap_f = m_functions & set(burst_terms)
        overlap_e = m_effects & set(burst_terms)

        if overlap_f or overlap_e:
            self.insights.append(CrossToolInsight(
                insight_type="matrix_vs_burst",
                description=(
                    f"突发增长关键词 {', '.join(overlap_f | overlap_e)} "
                    f"同时出现在代理功效矩阵中；这是近期增长与段落共现的交叉信号，需逐件复核"
                ),
                source_tools=["analyze_tech_matrix", "analyze_burst_terms"],
                confidence=0.75,
            ))
        elif burst_terms:
            self.insights.append(CrossToolInsight(
                insight_type="matrix_vs_burst",
                description=(
                    f"突发增长关键词 ({', '.join(burst_terms[:3])}) 不在功效矩阵Top维度中，"
                    f"可能来自口径差异，建议扩大关键词池并抽查原始专利"
                ),
                source_tools=["analyze_tech_matrix", "analyze_burst_terms"],
                confidence=0.5,
            ))

    def _detect_anomalies(self, results: dict[str, Any]):
        """Detect contradictory or surprising signals across tools."""
        trend = results.get("analyze_patent_trend")
        lifecycle = results.get("analyze_lifecycle")

        # Trend up but lifecycle shows decline → anomaly
        if trend and lifecycle:
            trend_data = getattr(trend, 'data', [])
            if isinstance(trend_data, list) and len(trend_data) >= 2:
                recent = [d.get('count', 0) for d in trend_data[-2:]]
                if len(recent) == 2 and recent[1] < recent[0] * 0.9:
                    # Recent decline
                    self.insights.append(CrossToolInsight(
                        insight_type="anomaly_trend_decline",
                        description="近期专利公开量出现下降信号，需先核验尾年完整性、公开滞后与检索范围",
                        source_tools=["analyze_patent_trend"],
                        confidence=0.6,
                    ))

        # High value but no citation data → data limitation
        valuation = results.get("analyze_patent_valuation")
        if valuation:
            val_data = getattr(valuation, 'data', [])
            if not val_data:
                self.insights.append(CrossToolInsight(
                    insight_type="anomaly_no_valuation",
                    description="价值评估未产生结果——引证数据可能缺失（WoS Derwent不含前引数据）",
                    source_tools=["analyze_patent_valuation"],
                    confidence=0.9,
                ))

    def _rank_opportunities(self, results: dict[str, Any]):
        """Rank innovation opportunities by combining gap data with trend signals."""
        matrix = results.get("analyze_tech_matrix")
        burst = results.get("analyze_burst_terms")
        trend = results.get("analyze_patent_trend")

        if not matrix:
            return

        # Extract gaps from tech matrix
        gaps = (getattr(matrix, 'gap_recommendations', []) or
                getattr(matrix, '_gap_recommendations', []))
        if not gaps:
            # Try to derive from matrix data
            functions = getattr(matrix, 'functions', [])
            effects = getattr(matrix, 'effects', [])
            mat = getattr(matrix, 'matrix', [])
            if functions and effects and mat:
                gaps = _extract_gaps_from_matrix(functions, effects, mat)

        if gaps:
            gap_descriptions = []
            for g in gaps[:5]:
                fn = g.get('function', '?')
                ef = g.get('effect', '?')
                cnt = g.get('patent_count', '?')
                gap_descriptions.append(f"{fn}+{ef}({cnt}件)")

            self.insights.append(CrossToolInsight(
                insight_type="opportunity_ranking",
                description=(
                    f"低共现复核候选（不等同于蓝海或创新空白）: "
                    + "; ".join(gap_descriptions)
                ),
                source_tools=["analyze_tech_matrix", "analyze_burst_terms"],
                confidence=0.65,
            ))

    def _competitive_positioning(self, results: dict[str, Any]):
        """Map competitive positions: which company leads in which technology area."""
        ipc = results.get("analyze_ipc_distribution")
        network = results.get("analyze_co_network")

        if not ipc:
            return

        # This is a simplification — full competitive positioning requires
        # per-applicant IPC data, which the current tools don't produce separately.
        # We signal this as a data limitation rather than producing poor analysis.
        if ipc and not network:
            self.insights.append(CrossToolInsight(
                insight_type="competitive_positioning_partial",
                description=(
                    "IPC分布已就绪但缺少申请人级数据对比。"
                    "建议使用 applicant_filter 参数对每个主要申请人单独运行趋势分析，以获取完整的竞争定位对比。"
                ),
                source_tools=["analyze_ipc_distribution"],
                confidence=0.3,
            ))


def _extract_gaps_from_matrix(functions: list[str], effects: list[str],
                              matrix: list[list[int]]) -> list[dict]:
    """Extract low-density cells from a tech-effect matrix."""
    if not matrix or not matrix[0]:
        return []
    gaps = []
    for fi, fn in enumerate(functions):
        for ei, ef in enumerate(effects):
            if fi < len(matrix) and ei < len(matrix[fi]):
                count = matrix[fi][ei]
                gaps.append({"function": fn, "effect": ef, "patent_count": count})
    gaps.sort(key=lambda x: x["patent_count"])
    return gaps[:10]
