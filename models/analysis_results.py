"""Pydantic 数据模型: 所有 AnalysisResult 子类"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from patent_agent.domain import ExecutionMetrics, ToolProvenance


class AnalysisResult(BaseModel):
    """所有分析结果的基类"""
    result_type: str
    chart_html: str | None = None  # Tool 层调用 Viz 后填充
    summary: str = ""
    methodology: str = ""
    data_quality: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: ToolProvenance | None = None
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)


class GenericAnalysisResult(AnalysisResult):
    """Lossless representation for structured evidence restored from SQLite."""
    model_config = ConfigDict(extra="allow")


class MonthlyTrendResult(AnalysisResult):
    result_type: str = "monthly_trend"
    data: list[dict]  # [{"year_month": "2020-01", "count": 15}, ...]


class YearlyTrendResult(AnalysisResult):
    result_type: str = "yearly_trend"
    data: list[dict]  # [{"year": 2020, "count": 180}, ...]


class GrowthRateResult(AnalysisResult):
    result_type: str = "growth_rate"
    data: list[dict]  # [{"year": 2020, "count": 180, "growth_rate": 0.15}, ...]


class SCurveResult(AnalysisResult):
    result_type: str = "s_curve"
    years: list[int]
    counts: list[int]
    cumulative: list[int]
    fitted: list[float]
    params: list[float] | None = None  # [L, k, x0]


class WordFreqResult(AnalysisResult):
    result_type: str = "word_freq"
    data: list[dict]  # [{"word": "电池", "count": 45}, ...]


class YearlyKeywordsResult(AnalysisResult):
    result_type: str = "yearly_keywords"
    data: dict[int, list[list]]  # {2020: [["电池", 45], ...], ...}


class BurstTermResult(AnalysisResult):
    result_type: str = "burst_terms"
    data: list[dict]  # [{"term": "固态", "burst": 3.5, "early_freq": 12.0, "late_freq": 42.0}, ...]


class CoOccurrenceResult(AnalysisResult):
    result_type: str = "co_occurrence"
    edges: list[dict]  # [{"source": "华为", "target": "清华", "weight": 5}, ...]
    node_count: int = 0
    edge_count: int = 0


class IPCMatrixResult(AnalysisResult):
    result_type: str = "ipc_matrix"
    years: list[int]
    sections: list[str]
    matrix: list[list[int]]


class IPCDistributionResult(AnalysisResult):
    result_type: str = "ipc_distribution"
    data: list[dict]  # [{"section": "H01M", "count": 120}, ...]


class IPCTrendResult(AnalysisResult):
    result_type: str = "ipc_trend"
    data: list[dict]  # [{"year": 2020, "section": "H01M", "count": 15}, ...]


class CountryDistResult(AnalysisResult):
    result_type: str = "country_distribution"
    data: list[dict]  # [{"country": "CN", "count": 200}, ...]


class CountryTrendResult(AnalysisResult):
    result_type: str = "country_trend"
    data: list[dict]  # [{"year": 2020, "country": "CN", "count": 50}, ...]


class RoadmapResult(AnalysisResult):
    result_type: str = "roadmap"
    data: dict[int, list[dict]]  # {2020: [{"patent_number": "...", "title": "..."}, ...], ...}


class ClusteringResult(AnalysisResult):
    result_type: str = "clustering"
    labels: list[int]
    centroids: list[list[float]]
    cluster_keywords: dict[int, list[str]]
    patents_per_cluster: dict[int, int]
    cluster_titles: dict[int, str] = Field(default_factory=dict)
    silhouette_score: float | None = None


class TechEffectMatrix(AnalysisResult):
    result_type: str = "tech_effect_matrix"
    functions: list[str]
    effects: list[str]
    matrix: list[list[int]]
    gap_recommendations: list[dict] = Field(default_factory=list)


class ValueIndicators(AnalysisResult):
    result_type: str = "value_indicators"
    data: list[dict]  # [{"patent_number": "...", "citation_count": 12, ...}, ...]
    score_label: str = "价值筛查分"
    coverage: dict[str, float] = Field(default_factory=dict)


class PatentSearchResult(AnalysisResult):
    result_type: str = "patent_search"
    patents: list[dict]  # PatentSummary 列表
    total_hits: int
    query_embedding_time_ms: float = 0.0


class PatentDetailsResult(AnalysisResult):
    result_type: str = "patent_details"
    patents: list[dict] = Field(default_factory=list)


class NetworkResult(AnalysisResult):
    result_type: str = "network"
    nodes: list[dict]
    edges: list[dict]


# ═══════════════════════════════════════════════════════════════════
#  Phase 7: Strategic recommendation models
# ═══════════════════════════════════════════════════════════════════

class StrategicRecommendation(BaseModel):
    """A single strategic recommendation backed by data evidence."""
    category: str  # R&D_INVESTMENT / PATENT_FILING / RISK_MITIGATION /
                   # TALENT_ACQUISITION / LICENSING / PORTFOLIO_PRUNE / PARTNERSHIP
    insight: str           # data-backed factual observation
    recommendation: str    # specific actionable advice
    urgency: int = 3       # 1 (low) – 5 (critical)
    confidence: int = 3    # 1 (low) – 5 (high), based on data quality and completeness
    supporting_tools: list[str] = Field(default_factory=list)
    alternative: str = ""  # fallback option
    next_step: str = ""    # concrete next action


class CrossToolInsight(BaseModel):
    """An insight derived by correlating results from two or more tools."""
    insight_type: str      # e.g. "trend_vs_ipc", "cluster_vs_value", "gap_vs_burst"
    description: str       # human-readable insight
    source_tools: list[str]  # which tools contributed
    confidence: float = 0.0  # 0.0 – 1.0


class StrategyReport(AnalysisResult):
    """Decision-oriented analysis report with strategic recommendations."""
    result_type: str = "strategy_report"
    executive_summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[StrategicRecommendation] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    cross_tool_insights: list[CrossToolInsight] = Field(default_factory=list)
    followup_analyses: list[str] = Field(default_factory=list)
    chain_name: str = ""       # which analysis chain produced this report
    tools_executed: int = 0    # how many tools successfully ran
    tools_failed: int = 0      # how many tools failed
