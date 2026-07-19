"""Tool: 数据集概况查询"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import AnalysisResult
from pydantic import Field


class DatasetSummaryResult(AnalysisResult):
    """数据集概况结果，包含结构化数据字段供 LLM 提取"""
    total_patents: int = 0
    year_start: int = 0
    year_end: int = 0
    ipc_sections: list[str] = Field(default_factory=list)
    top_applicants: list[dict] = Field(default_factory=list)


class DatasetSummaryTool(Tool):
    name = "get_dataset_summary"
    description = (
        "获取当前专利数据集的概况信息，包括专利总量、时间跨度、IPC分类范围、"
        "主要申请人排名和字段质量。仅在用户询问数据概览、数据质量、"
        "样本范围，或当前问题确实需要核对数据边界时使用；"
        "不要为每个分析自动调用。"
    )
    methodology = "数据集记录数、公开日期范围、IPC 与申请人字段的描述性汇总。"
    evidence_level = "descriptive_statistics"
    allow_empty = True

    async def execute(self, storage: PatentDataStore) -> DatasetSummaryResult:
        summary = storage.get_summary()
        top_apps = [{"name": name, "count": count}
                    for name, count in summary.top_applicants]

        result = DatasetSummaryResult(
            result_type="dataset_summary",
            total_patents=summary.total_patents,
            year_start=summary.year_range[0],
            year_end=summary.year_range[1],
            ipc_sections=summary.ipc_sections,
            top_applicants=top_apps,
        )

        lines = [
            f"**专利总量**: {summary.total_patents:,} 件",
            f"**时间跨度**: {summary.year_range[0]} – {summary.year_range[1]}",
            f"**IPC 部级分类**: {', '.join(summary.ipc_sections)}",
            "",
            "**主要申请人 (Top 10)**:",
        ]
        for i, (name, count) in enumerate(summary.top_applicants, 1):
            lines.append(f"  {i}. {name}: {count:,} 件")

        result.chart_html = (
            '<div style="background:#1a1a2e;color:#e0e0e0;padding:20px;'
            'border-radius:8px;font-family:monospace;line-height:1.8">'
            + '<br>'.join(lines).replace('\n', '<br>') +
            '</div>'
        )
        return result


tool_registry.register(DatasetSummaryTool())
