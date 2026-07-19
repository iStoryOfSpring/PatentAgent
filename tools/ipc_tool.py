"""Tool: IPC 分类分析"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import ipc_analysis
from viz import charts
from models.analysis_results import IPCMatrixResult


class IPCTool(Tool):
    name = "analyze_ipc_distribution"
    description = (
        "分析专利的 IPC 分类分布情况，生成年份×IPC 部级（A-H）热力图，"
        "直观展示各技术领域的专利分布和变化趋势。"
        "适用于用户询问'技术构成'、'IPC分布'、'技术领域'等关键词。"
    )
    required_fields = ("publication_date", "ipc")
    methodology = "按公开年份与 IPC 分类聚合的描述性统计。"
    evidence_level = "descriptive_statistics"

    async def execute(self, storage: PatentDataStore) -> IPCMatrixResult:
        df = storage.get_all()
        result = ipc_analysis.compute_ipc_year_matrix(df)
        if result.sections:
            chart_obj = charts.plot_ipc_heatmap(result)
            result.chart_html = chart_obj.render_embed()
        return result


tool_registry.register(IPCTool())
