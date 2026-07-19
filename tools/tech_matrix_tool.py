"""Tool: 技术功效矩阵分析（对应书第8-9章）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import TechEffectMatrix


class TechMatrixTool(Tool):
    name = "analyze_tech_matrix"
    description = (
        "从 Derwent 摘要标签构建代理技术功效矩阵，分析技术手段与用途/效果的共现；"
        "低共现仅列为需要逐件复核的候选，不直接解释为创新空白。"
        "适用于用户询问'技术热点'、'空白点'、'功效矩阵'、'创新方向'等关键词。"
    )
    parameters = {
        "top_n": {
            "type": "integer",
            "description": "保留的Top N关键词数量。默认 30。",
        },
    }
    required_fields = ("abstract",)
    methodology = "从 Derwent NOVELTY/详细描述代理技术手段，从 USE/ADVANTAGE 代理用途与效果；空白仅作复核候选。"
    evidence_level = "derwent_abstract_proxy"

    async def execute(self, storage: PatentDataStore,
                      top_n: int = 50) -> TechEffectMatrix:
        from engine import tech_matrix
        from tools.search_tool import _row_to_pseudo_patent

        # Sample up to 5000 patents for performance (NLP is O(n²) on keywords)
        df = storage.get_columns(['title', 'abstract', 'patent_number',
                                   'publication_date', 'ipc', 'cited_refs',
                                   'family_members', 'forward_citations'])
        n_sample = min(len(df), 5000)
        df_sample = df.sample(n=n_sample, random_state=42) if len(df) > n_sample else df
        patents = [_row_to_pseudo_patent(row) for _, row in df_sample.iterrows()]

        result = tech_matrix.build_tech_effect_matrix_results(patents, top_n=top_n)
        gap_recs = result.gap_recommendations
        result.result_metadata.update({
            "sample_size": n_sample, "population_size": len(df),
            "sampled": len(df) > n_sample,
        })
        if len(df) > n_sample:
            result.warnings.append(f"功效矩阵抽样 {n_sample:,}/{len(df):,} 件，使用固定随机种子。")

        if result.functions and result.effects:
            import numpy as np
            matrix = np.array(result.matrix)
            max_val = np.max(matrix) if matrix.size > 0 else 1

            # ── 左侧：热力图 ──
            heatmap_html = ['<div style="overflow-x:auto;min-width:400px">',
                            '<table style="border-collapse:collapse;font-size:10px">']
            heatmap_html.append('<tr><th></th>')
            for eff in result.effects[:10]:
                heatmap_html.append(
                    f'<th style="padding:4px;background:#333;color:#FFD700">{eff[:8]}</th>'
                )
            heatmap_html.append('</tr>')
            for i, func in enumerate(result.functions[:15]):
                heatmap_html.append('<tr>')
                heatmap_html.append(
                    f'<td style="padding:4px;background:#333;color:#FFD700">{func[:8]}</td>'
                )
                for j in range(min(10, len(result.effects))):
                    val = int(matrix[i, j]) if i < matrix.shape[0] and j < matrix.shape[1] else 0
                    intensity = min(val / max(max_val, 1), 1.0)
                    r = int(0 + intensity * 255)
                    g = int(100 + intensity * 100)
                    b = int(50)
                    heatmap_html.append(
                        f'<td style="padding:4px;text-align:center;'
                        f'background:rgb({r},{g},{b});color:white">{val}</td>'
                    )
                heatmap_html.append('</tr>')
            heatmap_html.append('</table></div>')

            # ── 右侧：空白点探照灯 ──
            gap_html = [
                '<div style="background:#1a1a2e;color:#e0e0e0;padding:16px;'
                'border-radius:8px;min-width:280px;font-size:13px">',
                '<h4 style="color:#FFD700;margin-top:0">空白点 Top 10 ',
                '<span style="font-size:11px;color:#888">（需人工复核的低共现候选）</span></h4>',
                '<table style="width:100%;border-collapse:collapse">',
                '<tr style="color:#888;font-size:11px">'
                '<th style="text-align:left;padding:4px">#</th>'
                '<th style="text-align:left;padding:4px">技术手段</th>'
                '<th style="text-align:left;padding:4px">技术效果</th>'
                '<th style="text-align:right;padding:4px">现有专利</th></tr>',
            ]
            for rank, g in enumerate(gap_recs, 1):
                color = "#FFD700" if g["patent_count"] == 0 else (
                    "#FFA500" if g["patent_count"] <= 3 else "#888"
                )
                cnt_color = "#4f4" if g["patent_count"] == 0 else "#aaa"
                gap_html.append(
                    f"<tr style='border-bottom:1px solid #333'>"
                    f"<td style='padding:6px 4px;color:#888'>{rank}</td>"
                    f"<td style='padding:6px 4px;color:{color}'>{g['function']}</td>"
                    f"<td style='padding:6px 4px;color:{color}'>{g['effect']}</td>"
                    f"<td style='padding:6px 4px;text-align:right;color:{cnt_color}'>"
                    f"{g['patent_count']}</td></tr>"
                )
            gap_html.append('</table>')
            gap_html.append(
                '<p style="color:#888;font-size:10px;margin-top:8px">'
                '低共现不等于蓝海，必须结合术语质量、相关专利和权利要求复核。</p></div>'
            )

            # ── 组合布局 ──
            result.chart_html = (
                '<div style="display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start">'
                + '\n'.join(heatmap_html)
                + '\n'.join(gap_html)
                + '</div>'
            )

        return result


tool_registry.register(TechMatrixTool())
