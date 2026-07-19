"""Tool: 合作网络与关联分析"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import network_analysis
from viz import charts
from models.analysis_results import CoOccurrenceResult


class NetworkTool(Tool):
    name = "analyze_co_network"
    description = (
        "分析申请人/专利权人之间的合作网络，生成交互式网络图。"
        "适用于用户询问'合作关系'、'合作网络'、'共同申请'、'产学研'等关键词。"
    )
    required_fields = ("applicants",)
    methodology = "同一专利的多申请人共现网络；不把名称相似自动视作同一主体。"
    evidence_level = "descriptive_network"

    async def execute(self, storage: PatentDataStore) -> CoOccurrenceResult:
        df = storage.get_all()
        result = network_analysis.compute_co_occurrence(df)

        if result.edges:
            chart_obj = charts.plot_network(result)
            result.chart_html = chart_obj.render_embed()
        else:
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
            result.chart_html = (
                '<div style="background:#1a1a2e;color:#e0e0e0;padding:30px;'
                'border-radius:8px;text-align:center;font-family:Arial,sans-serif">'
                '<h3 style="color:#FFD700">合作网络分析</h3>'
                f'<p style="font-size:18px">该数据集中 <b>{multi:,}</b> 件专利涉及多个申请人，'
                f'占比 <b>{pct:.1f}%</b></p>'
                '<p style="color:#888">合作申请比例过低，无法构建有意义的网络图</p>'
                '<p style="color:#666;font-size:13px">'
                '提示：WoS Derwent 数据通常以单一专利权人为主。<br>'
                '如需合作网络分析，建议使用包含产学研合作或公司间联合申请的数据集。</p>'
                '</div>'
            )

        return result


tool_registry.register(NetworkTool())
