"""Tool: IPC 分类分析"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import ipc_analysis
from models.analysis_results import IPCMatrixResult
from patent_agent.domain import AlgorithmExecution


class IPCTool(Tool):
    name = "analyze_ipc_distribution"
    description = (
        "分析专利的 IPC 分类分布情况，生成年份×IPC 部级（A-H）热力图，"
        "可选择 IPC 标注次数、去重专利数或同族归一化计数。"
        "适用于用户询问'技术构成'、'IPC分布'、'技术领域'等关键词。"
    )
    parameters = {
        "count_mode": {
            "type": "string",
            "enum": ["assignment_count", "unique_patents", "family_normalized"],
            "description": "IPC 计数口径；默认统计全部 IPC 标注次数。",
            "default": "assignment_count",
        },
    }
    required_fields = ("publication_date", "ipc")
    methodology = "按公开年份与 IPC 分类聚合的描述性统计。"
    evidence_level = "descriptive_statistics"

    async def execute(
        self, storage: PatentDataStore, count_mode: str = "assignment_count",
    ) -> IPCMatrixResult:
        df = storage.get_all()
        result = ipc_analysis.compute_ipc_year_matrix(df, count_mode)
        result.algorithm_execution = AlgorithmExecution(
            algorithm_id=f"ipc_publication_matrix_{count_mode}",
            algorithm_version="2.1",
            mode_requested=count_mode,
            mode_used=count_mode,
            parameters={"count_mode": count_mode},
        )
        return result


tool_registry.register(IPCTool())
