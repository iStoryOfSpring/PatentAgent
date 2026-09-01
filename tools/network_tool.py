"""Tool: 合作网络与关联分析"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import network_analysis
from models.analysis_results import CoOccurrenceResult


class NetworkTool(Tool):
    name = "analyze_co_network"
    description = (
        "分析申请人/专利权人之间的合作网络，生成交互式网络图。"
        "适用于用户询问'合作关系'、'合作网络'、'共同申请'、'产学研'等关键词。"
    )
    required_fields = ("applicants",)
    methodology = "同一专利的多申请人共现网络；使用可逆的确定性格式/公司后缀规范化，不做模糊实体合并。"
    evidence_level = "descriptive_network"

    async def execute(self, storage: PatentDataStore) -> CoOccurrenceResult:
        df = storage.get_columns(['applicants', 'applicant_canonical_names'])
        if 'applicant_canonical_names' in df.columns:
            df = df.assign(applicants=df['applicant_canonical_names'])
        result = network_analysis.compute_co_occurrence(df)

        if not result.edges:
            # 统计单一/多申请人比例，给出有意义的提示
            multi = 0
            single = 0
            for apps in df['applicants'].dropna():
                if ';' in apps:
                    multi += 1
                else:
                    single += 1
            total = multi + single if (multi + single) > 0 else 1
            pct = multi / total * 100
            result.warnings.append(
                f"仅 {multi:,} 件（{pct:.1f}%）记录含多个申请人，合作网络证据不足。"
            )
        return result


tool_registry.register(NetworkTool())
