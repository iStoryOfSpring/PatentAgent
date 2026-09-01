"""Tool: 国家/地区分布分析"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import country_analysis
from models.analysis_results import CountryDistResult


class CountryTool(Tool):
    name = "analyze_country_distribution"
    description = (
        "分析主公开号所属的首个公开局分布。该指标不等同于同族市场覆盖。"
        "适用于用户询问'公开局分布'、'地域分布'等关键词。"
    )
    required_fields = ("patent_number",)
    optional_fields = ("family_members",)
    methodology = "按 PN 主公开号前缀统计首个公开局；另有同族数据时才可讨论市场覆盖。"
    evidence_level = "descriptive_statistics"

    async def execute(self, storage: PatentDataStore) -> CountryDistResult:
        df = storage.get_all()
        result = country_analysis.compute_country_distribution(df)
        result.summary = f"主公开号首次公开局分布包含 {len(result.data)} 个局；该分布不是同族市场覆盖。"
        result.result_metadata["geography_semantics"] = "first_publication_office"
        if not storage.has_field("family_members"):
            result.warnings.append("同族成员不可用，无法分析市场覆盖国家。")
        return result


tool_registry.register(CountryTool())
