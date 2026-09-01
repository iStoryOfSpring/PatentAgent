"""Tool: 技术增长趋势分析（v1.4 重写）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import lifecycle
from models.analysis_results import SCurveResult


class LifecycleTool(Tool):
    name = "analyze_lifecycle"
    description = (
        "分析专利公开数量的增长趋势: 累计公开量 + 年同比增长率。"
        "适用于用户询问'趋势'、'增长'、'变化'等关键词。"
    )
    required_fields = ("publication_date",)
    methodology = "按公开日期统计累计量与同比变化；不把尾年缺失月份解释为生命周期衰退。"
    evidence_level = "descriptive_statistics"

    async def execute(self, storage: PatentDataStore) -> SCurveResult:
        df = storage.get_all()
        yearly = df.groupby('year').size().reset_index(name='count').sort_values('year')
        result = lifecycle.fit_logistic_curve(yearly)
        result.summary = "按公开日期统计年度公开量、累计公开量与同比变化；不输出生命周期阶段判定。"
        result.result_metadata["date_semantics"] = "publication_date"
        from engine.trend import audit_publication_time_coverage
        time_audit, warnings = audit_publication_time_coverage(
            df, storage.audit().get("data_as_of", ""),
        )
        result.result_metadata["time_coverage"] = time_audit
        result.warnings.extend(warnings)

        years = result.years
        counts = result.counts
        growth_rates = []
        for i in range(len(counts)):
            if i == 0:
                growth_rates.append(0.0)
            else:
                growth_rates.append(round(
                    (counts[i] - counts[i - 1]) / max(counts[i - 1], 1) * 100, 1
                ))
        year_span = max(0, years[-1] - years[0]) if years else 0
        cagr = (
            ((counts[-1] / counts[0]) ** (1 / year_span) - 1) * 100
            if year_span > 0 and counts[0] > 0 else None
        )
        result.result_metadata["cagr_pct"] = round(cagr, 2) if cagr is not None else None
        result.result_metadata["cagr_period_years"] = int(year_span)
        result.result_metadata["year_over_year_growth_pct"] = growth_rates
        return result


tool_registry.register(LifecycleTool())
