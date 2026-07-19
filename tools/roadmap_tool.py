"""Tool: 技术路线图"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import roadmap
from viz import charts
from models.analysis_results import RoadmapResult


class RoadmapTool(Tool):
    name = "analyze_tech_roadmap"
    description = (
        "生成按公开年度组织的技术主题时间轴和代表性专利；"
        "仅在内部引证充分时展示可验证的引证路径。"
        "适用于用户询问'技术路线'、'发展脉络'、'技术演进'、'路线图'等关键词。"
    )
    parameters = {
        "top_n_per_year": {
            "type": "integer",
            "description": "每年展示的专利数量。默认 3。",
        },
    }
    required_fields = ("publication_date", "title", "patent_number")
    optional_fields = ("backward_citations",)
    methodology = "按公开年度主题、代表性专利和数据可用的引证路径生成路线图。"
    evidence_level = "engineering_approximation"

    async def execute(self, storage: PatentDataStore,
                      top_n_per_year: int = 3) -> RoadmapResult:
        df = storage.get_columns([
            'year', 'date', 'publication_date', 'patent_number', 'title',
            'backward_citations', 'cited_refs',
        ])
        result = roadmap.compute_roadmap_data(df, top_n_per_year=top_n_per_year)
        if result.data:
            chart_obj = charts.plot_roadmap_timeline(result)
            result.chart_html = chart_obj.render_embed()
        return result


tool_registry.register(RoadmapTool())
