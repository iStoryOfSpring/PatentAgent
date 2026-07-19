"""Tool: 竞争对手 IPC 画像演化分析。"""

import json
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
        },
    }
    required_fields = ("publication_date", "applicants", "ipc")
    methodology = "IPC 小类/主组年度画像的熵、主导份额与相邻年份余弦距离；不是 PatentMiner DICT/PBC/HBC。"
    evidence_level = "engineering_heuristic"

    async def execute(self, storage: PatentDataStore,
                      top_n: int = 10) -> CompetitorEvolutionResult:
        from engine.competitor_evolution import compute_competitor_evolution

        df = storage.get_columns(['year', 'applicants', 'ipc'])
        data = compute_competitor_evolution(df, top_n_applicants=top_n)

        result = CompetitorEvolutionResult(
            result_type="competitor_evolution",
            data=data,
        )

        # Build HTML display
        evo = data.get('evolution', [])
        html = [
            '<div style="background:#1a1a2e;color:#e0e0e0;padding:20px;border-radius:8px;'
            'font-family:monospace;font-size:12px;overflow-x:auto">',
            '<h3 style="color:#FFD700;margin-top:0">竞争对手技术演化分析</h3>',
            f'<p style="color:#888">{data.get("cross_insights", "")}</p>',
            '<table style="width:100%;border-collapse:collapse">',
            '<tr style="background:#333;color:#FFD700"><th>申请人</th><th>专利数</th>'
            '<th>技术演化总结</th><th>最新核心IPC</th></tr>',
        ]
        for e in evo:
            top_ipc_now = e.get('top_ipc', [[]])[-1] if e.get('top_ipc') else []
            html.append(
                f'<tr style="border-bottom:1px solid #333">'
                f'<td style="padding:8px;font-weight:bold">{e["applicant"]}</td>'
                f'<td style="padding:8px">{e["total_patents"]:,}</td>'
                f'<td style="padding:8px;color:#aaa">{e["trend_summary"][:120]}</td>'
                f'<td style="padding:8px;color:#4f8">{", ".join(top_ipc_now[:5])}</td>'
                f'</tr>'
            )
        html.append('</table>')
        html.append(
            '<p style="color:#888;font-size:10px;margin-top:12px">'
            '指标说明: dominant IPC share = 核心领域集中度 | '
            'IPC entropy = 技术多元化程度 | '
            'IPC profile cosine shift = 相邻年份画像变化。该工具不是 Tang DICT。</p></div>'
        )
        result.chart_html = '\n'.join(html)
        return result


tool_registry.register(CompetitorEvolutionTool())
