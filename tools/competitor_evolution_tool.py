"""Tool: 竞争对手 IPC 画像演化分析。"""

from pydantic import Field

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import AnalysisResult


class CompetitorEvolutionResult(AnalysisResult):
    result_type: str = "competitor_evolution"
    data: dict = Field(default_factory=dict)


class CompetitorEvolutionTool(Tool):
    name = "analyze_competitor_evolution"
    description = (
        "追踪主要申请人的技术重心转移：分析每家公司的技术多元化程度"
        "（IPC entropy）、核心领域集中度（dominant IPC share）、画像变化"
        "（IPC profile cosine shift），以及每年 Top IPC 小类/主组变化。"
        "适用于'竞争对手动向'、'技术布局变化'、'研发战略转移'等分析。"
    )
    parameters = {
        "top_n": {
            "type": "integer",
            "description": "分析前N个申请人，默认10",
            "default": 10,
            "minimum": 1,
            "maximum": 50,
        },
    }
    required_fields = ("publication_date", "applicants", "ipc")
    methodology = "IPC 小类/主组年度画像的熵、主导份额与相邻年份余弦距离；不是 PatentMiner DICT/PBC/HBC。"
    evidence_level = "engineering_heuristic"

    async def execute(self, storage: PatentDataStore,
                      top_n: int = 10) -> CompetitorEvolutionResult:
        from engine.competitor_evolution import compute_competitor_evolution

        df = storage.get_columns(['year', 'applicants', 'applicant_canonical_names', 'ipc'])
        if 'applicant_canonical_names' in df.columns:
            df = df.assign(applicants=df['applicant_canonical_names'])
        data = compute_competitor_evolution(df, top_n_applicants=top_n)

        result = CompetitorEvolutionResult(
            result_type="competitor_evolution",
            data=data,
        )

        return result


tool_registry.register(CompetitorEvolutionTool())
