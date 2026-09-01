"""Tool: 专利公开趋势分析"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import trend
from models.analysis_results import MonthlyTrendResult


class TrendTool(Tool):
    name = "analyze_patent_trend"
    description = (
        "分析专利公开时间趋势，生成月度或年度公开量统计数据及可视化图表。"
        "适用于用户询问'趋势'、'增长'、'变化'、'申请量'等关键词。"
    )
    parameters = {
        "chart_type": {
            "type": "string",
            "enum": ["monthly", "yearly"],
            "description": "图表类型: monthly=月度趋势, yearly=年度趋势。默认 monthly。",
            "default": "monthly",
        },
        "year_start": {
            "type": "integer",
            "description": "起始年份，不填则从最早年份开始",
        },
        "year_end": {
            "type": "integer",
            "description": "结束年份，不填则到最晚年",
        },
        "ipc_filter": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IPC分类号过滤，如['H01M', 'H02J']",
        },
        "applicant_filter": {
            "type": "string",
            "description": "申请人名称关键词过滤",
        },
    }
    required_fields = ("publication_date",)
    optional_fields = ("ipc", "applicants")
    methodology = "按 WoS PD 公开日期聚合；尾年月份不完整时不解释为技术衰退。"
    evidence_level = "descriptive_statistics"

    async def execute(self, storage: PatentDataStore,
                      chart_type: str = "monthly",
                      year_start: int = None,
                      year_end: int = None,
                      ipc_filter: list[str] = None,
                      applicant_filter: str = None) -> MonthlyTrendResult:
        df = storage.query(year_start=year_start, year_end=year_end,
                           ipc_filter=ipc_filter,
                           applicant_filter=applicant_filter)
        if chart_type == "yearly":
            result = trend.compute_yearly_trend(df)
        else:
            result = trend.compute_monthly_trend(df)
        result.summary = (
            f"按专利公开日期生成 {chart_type} 趋势，共 {len(result.data)} 个时间点，"
            f"筛选后 {len(df):,} 件记录。"
        )
        result.result_metadata.update({
            "population_after_filters": len(df),
            "date_semantics": "publication_date",
        })
        time_audit, warnings = trend.audit_publication_time_coverage(
            df, storage.audit().get("data_as_of", ""),
        )
        result.result_metadata["time_coverage"] = time_audit
        result.warnings.extend(warnings)
        return result


tool_registry.register(TrendTool())
