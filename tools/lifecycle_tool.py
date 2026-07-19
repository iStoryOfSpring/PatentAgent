"""Tool: 技术增长趋势分析（v1.4 重写）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import lifecycle
from viz import charts
from models.analysis_results import SCurveResult


class LifecycleTool(Tool):
    name = "analyze_lifecycle"
    description = (
        "分析专利公开数量的增长趋势: 累计公开量 + 年同比增长率。"
        "适用于用户询问'趋势'、'增长'、'变化'等关键词。"
    )
    required_fields = ("publication_date",)
    methodology = "按公开日期统计累计量与同比变化；不把尾年缺失月份解释为生命周期衰退。"
    evidence_level = "descriptive_statistics"

    async def execute(self, storage: PatentDataStore) -> SCurveResult:
        df = storage.get_all()
        yearly = df.groupby('year').size().reset_index(name='count').sort_values('year')
        result = lifecycle.fit_logistic_curve(yearly)
        result.summary = "按公开日期统计年度公开量、累计公开量与同比变化；不输出生命周期阶段判定。"
        result.result_metadata["date_semantics"] = "publication_date"
        if not df.empty and "month" in df:
            max_year = int(df["year"].dropna().max())
            months = df.loc[df["year"] == max_year, "month"].dropna().nunique()
            result.result_metadata["latest_year_months_covered"] = int(months)
            if months < 10:
                result.warnings.append(
                    f"尾年 {max_year} 仅覆盖 {months} 个月，不应把下降解释为技术衰退。"
                )

        # 构建双面板 HTML: 累计量 + 增长率
        years = result.years
        counts = result.counts
        cumulative = result.cumulative

        # 增长率计算
        growth_rates = []
        for i in range(len(counts)):
            if i == 0:
                growth_rates.append(0.0)
            else:
                growth_rates.append(round(
                    (counts[i] - counts[i - 1]) / max(counts[i - 1], 1) * 100, 1
                ))

        # 构建简洁的 HTML 面板
        rows = [
            '<div style="display:flex;flex-wrap:wrap;gap:24px">',
            # ── 左侧: 累计申请量 ──
            '<div style="flex:1;min-width:400px;background:#1a1a2e;border-radius:8px;padding:20px">',
            '<h3 style="color:#FFD700;margin-top:0">累计专利公开量</h3>',
            '<table style="width:100%;border-collapse:collapse;font-size:14px">',
            '<tr style="color:#888"><th style="text-align:left;padding:6px">年份</th>'
            '<th style="text-align:right;padding:6px">年申请量</th>'
            '<th style="text-align:right;padding:6px">累计量</th>'
            '<th style="text-align:right;padding:6px">增长率</th></tr>',
        ]
        for i in range(len(years)):
            g_color = "#4f4" if growth_rates[i] > 0 else ("#f44" if growth_rates[i] < 0 else "#888")
            g_sign = "+" if growth_rates[i] > 0 else ""
            rows.append(
                f'<tr style="border-bottom:1px solid #333">'
                f'<td style="padding:8px 6px;color:#e0e0e0">{years[i]}</td>'
                f'<td style="padding:8px 6px;text-align:right;color:#e0e0e0">{counts[i]:,}</td>'
                f'<td style="padding:8px 6px;text-align:right;color:#FFD700;font-weight:bold">{cumulative[i]:,}</td>'
                f'<td style="padding:8px 6px;text-align:right;color:{g_color}">{g_sign}{growth_rates[i]}%</td>'
                f'</tr>'
            )
        rows.append('</table>')

        # 趋势总结
        total = cumulative[-1]
        avg_growth = sum(g for g in growth_rates[1:] if growth_rates[1:]) / max(len(growth_rates[1:]), 1)
        trend_word = "快速增长" if avg_growth > 10 else ("平稳增长" if avg_growth > 0 else "下降")
        rows.append(
            f'<p style="color:#888;margin-top:16px;font-size:13px">'
            f'{len(years)} 年累计 {total:,} 件，年均增长率 {avg_growth:+.1f}%，'
            f'整体呈<b style="color:#FFD700">{trend_word}</b>趋势</p>'
        )
        rows.append('</div>')

        # ── 右侧: 折线图 ──
        chart = charts.plot_yearly_trend(_make_trend_result(years, counts))
        rows.append(
            f'<div style="flex:1;min-width:400px;background:#1a1a2e;border-radius:8px;padding:10px">'
            f'<h3 style="color:#FFD700;padding:10px 10px 0;margin:0">年度公开趋势</h3>'
            f'{chart.render_embed()}'
            f'</div>'
        )
        rows.append('</div>')

        result.chart_html = '\n'.join(rows)
        return result


def _make_trend_result(years, counts):
    """构造 YearlyTrendResult 兼容对象"""
    from types import SimpleNamespace
    data = [{"year": int(y), "count": int(c)} for y, c in zip(years, counts)]
    return SimpleNamespace(data=data, result_type="yearly_trend")


tool_registry.register(LifecycleTool())
