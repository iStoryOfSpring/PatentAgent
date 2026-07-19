"""Pyecharts 图表生成函数。

每个函数接收 AnalysisResult，返回 pyecharts 图表对象（不写文件）。
"""

from pyecharts import options as opts
from pyecharts.charts import (
    Line, Bar, Pie, Scatter, Timeline, HeatMap, WordCloud, Graph, Grid,
)
from pyecharts.commons.utils import JsCode

from viz.templates import (
    get_dark_theme, STAGE_COLORS, YEARLY_COLORS, HEATMAP_COLORS,
)


def plot_monthly_trend(result) -> Line:
    """月度公开趋势折线图（兼容旧客户端的 HTML 图表）。"""
    labels = [d["year_month"] for d in result.data]
    counts = [d["count"] for d in result.data]
    return (
        Line(init_opts=get_dark_theme())
        .add_xaxis(xaxis_data=labels)
        .add_yaxis(
            series_name="专利公开量",
            y_axis=counts,
            is_smooth=True,
            label_opts=opts.LabelOpts(is_show=len(labels) <= 12,
                                      color="#475569"),
            linestyle_opts=opts.LineStyleOpts(width=3, color="#2563EB"),
            areastyle_opts=opts.AreaStyleOpts(opacity=0.12, color="#2563EB"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="专利公开月度趋势", pos_left="center"),
            xaxis_opts=opts.AxisOpts(
                name="公开月份",
                axislabel_opts=opts.LabelOpts(interval=5 if len(labels) > 24 else 0),
            ),
            yaxis_opts=opts.AxisOpts(name="公开量（件）"),
            legend_opts=opts.LegendOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            datazoom_opts=(
                [opts.DataZoomOpts(type_="inside"), opts.DataZoomOpts(type_="slider")]
                if len(labels) > 24 else None
            ),
        )
    )


def plot_yearly_trend(result) -> Line:
    """年度公开趋势折线图"""
    labels = [str(d["year"]) for d in result.data]
    counts = [d["count"] for d in result.data]
    return (
        Line(init_opts=get_dark_theme())
        .add_xaxis(xaxis_data=labels)
        .add_yaxis(
            "年公开量", counts,
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=3, color="#00BFFF"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="年度专利公开趋势", pos_left="center"),
            xaxis_opts=opts.AxisOpts(name="年份"),
            yaxis_opts=opts.AxisOpts(name="公开量（件）"),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )


def plot_wordcloud(result, title: str = "专利关键词云") -> WordCloud:
    """词云"""
    word_pairs = [(d["word"], d["count"]) for d in result.data[:100]]
    return (
        WordCloud()
        .add("", word_pairs, word_size_range=[15, 80], shape="circle")
        .set_global_opts(title_opts=opts.TitleOpts(title=title, pos_left="center"))
    )


def plot_wordfreq_bar(result, title: str = "高频词 Top 20") -> Bar:
    """词频柱状图"""
    words = [d["word"] for d in result.data[:20]]
    counts = [d["count"] for d in result.data[:20]]
    return (
        Bar()
        .add_xaxis(words)
        .add_yaxis("出现频次", counts)
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title, pos_left="center"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-45)),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )


def plot_s_curve(scurve, stages: list) -> Grid:
    """S 曲线 + 生命周期阶段标注"""
    years = [str(y) for y in scurve.years]
    cum = scurve.cumulative
    fitted = scurve.fitted

    scatter = (
        Scatter(init_opts=get_dark_theme())
        .add_xaxis(years)
        .add_yaxis("实际累计量", cum, symbol_size=10,
                   label_opts=opts.LabelOpts(is_show=False))
    )

    line = (
        Line()
        .add_xaxis(years)
        .add_yaxis("S曲线拟合", fitted, is_smooth=True,
                   linestyle_opts=opts.LineStyleOpts(width=3, color="#FFD700"),
                   label_opts=opts.LabelOpts(is_show=False))
    )

    mark_areas = []
    for stage_name, sy, ey in stages:
        color = STAGE_COLORS.get(stage_name, '#888888')
        mark_areas.append(
            opts.MarkAreaItem(
                name=stage_name,
                x=(str(sy), str(ey)),
                itemstyle_opts=opts.ItemStyleOpts(color=color, opacity=0.15),
                label_opts=opts.LabelOpts(position='top', formatter=stage_name,
                                          color=color, font_weight='bold'),
            )
        )
    if mark_areas:
        line.set_series_opts(markarea_opts=opts.MarkAreaOpts(data=mark_areas))

    chart = scatter.overlap(line)
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="技术生命周期 S 曲线", pos_left="center"),
        xaxis_opts=opts.AxisOpts(name="年份", type_="category"),
        yaxis_opts=opts.AxisOpts(name="累计专利申请量"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="bottom"),
    )
    return chart


def plot_ipc_heatmap(result) -> HeatMap:
    """IPC 年分布热力图"""
    years = [str(y) for y in result.years]
    sections = result.sections
    heat_data = []
    for yi, y in enumerate(result.years):
        for si, s in enumerate(sections):
            val = result.matrix[yi][si]
            heat_data.append([str(y), s, val])
    max_val = max((v[2] for v in heat_data), default=1)

    return (
        HeatMap(init_opts=get_dark_theme())
        .add_xaxis(years)
        .add_yaxis("IPC 分类", sections, heat_data,
                   label_opts=opts.LabelOpts(is_show=True, position="inside",
                                              formatter="{c}", font_size=10))
        .set_global_opts(
            title_opts=opts.TitleOpts(title="IPC 分类年分布热力图", pos_left="center"),
            xaxis_opts=opts.AxisOpts(name="年份", type_="category",
                                     splitarea_opts=opts.SplitAreaOpts(is_show=True)),
            yaxis_opts=opts.AxisOpts(name="IPC 部", type_="category",
                                     splitarea_opts=opts.SplitAreaOpts(is_show=True)),
            visualmap_opts=opts.VisualMapOpts(
                min_=0, max_=max_val, range_color=HEATMAP_COLORS,
            ),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )


def plot_country_pie(result, year: int | None = None) -> Pie:
    """国家分布玫瑰图"""
    data_pair = [[d["country"], d["count"]] for d in result.data]
    title = f"{year}年 专利国家/地区分布" if year else "专利国家/地区分布"
    return (
        Pie()
        .add("", data_pair, radius=["30%", "70%"], rosetype="radius")
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title, pos_left="center"),
            legend_opts=opts.LegendOpts(orient="vertical", pos_top="15%", pos_left="2%"),
        )
        .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)"))
    )


def plot_yearly_keywords(result) -> Bar:
    """逐年关键词对比分组柱状图"""
    if not result.data:
        return Bar().set_global_opts(title_opts=opts.TitleOpts(title="无数据"))
    years = sorted(result.data.keys())
    all_keywords = set()
    for y in years:
        for word, _ in result.data[y]:
            all_keywords.add(word)
    all_keywords = sorted(all_keywords)[:15]

    bar = (
        Bar(init_opts=opts.InitOpts(theme="white", width="960px", height="520px", bg_color="#ffffff"))
        .add_xaxis(all_keywords)
    )
    for i, year in enumerate(years):
        wdict = {w: c for w, c in result.data[year]}
        vals = [wdict.get(w, 0) for w in all_keywords]
        bar.add_yaxis(
            str(year), vals,
            color=YEARLY_COLORS[i % len(YEARLY_COLORS)],
            label_opts=opts.LabelOpts(is_show=False),
        )
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="逐年关键词对比 (Top 15)", pos_left="center"),
        xaxis_opts=opts.AxisOpts(name="关键词", axislabel_opts=opts.LabelOpts(rotate=-45)),
        yaxis_opts=opts.AxisOpts(name="频次"),
        legend_opts=opts.LegendOpts(pos_top="bottom"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
    )
    return bar


def plot_burst_terms(result) -> Bar:
    """突发词横向柱状图"""
    if not result.data:
        return Bar().set_global_opts(title_opts=opts.TitleOpts(title="无突发词数据"))
    terms = [d["term"] for d in reversed(result.data)]
    scores = [d["burst"] for d in reversed(result.data)]
    return (
        Bar(init_opts=opts.InitOpts(theme="white", width="960px", height="600px", bg_color="#ffffff"))
        .add_xaxis(terms)
        .add_yaxis("突发强度", scores,
                   label_opts=opts.LabelOpts(position="right", formatter="{c}"),
                   itemstyle_opts=opts.ItemStyleOpts(color="#FF4500"))
        .reversal_axis()
        .set_global_opts(
            title_opts=opts.TitleOpts(title="技术突发词 Top 20", pos_left="center"),
            xaxis_opts=opts.AxisOpts(name="突发强度"),
            yaxis_opts=opts.AxisOpts(name="关键词", type_="category"),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )


def plot_bubble_chart(scurve, stages: list) -> Scatter:
    """技术成熟度气泡图"""
    years = scurve.years
    counts = scurve.counts
    fitted = scurve.fitted
    max_fitted = fitted[-1] if fitted[-1] > 0 else 1
    maturity = [f / max_fitted for f in fitted]

    year_stage = {}
    for stage_name, sy, ey in stages:
        for y in range(sy, ey + 1):
            year_stage[y] = stage_name

    plot_data = []
    for i, y in enumerate(years):
        stage = year_stage.get(int(y), '未知')
        color = STAGE_COLORS.get(stage, '#888888')
        plot_data.append([
            int(y),
            round(float(maturity[i]), 3),
            int(counts[i]),
            stage,
            color,
        ])

    return (
        Scatter(init_opts=get_dark_theme())
        .add_xaxis([d[0] for d in plot_data])
        .add_yaxis(
            "专利气泡",
            [d[1:] for d in plot_data],
            symbol_size=JsCode("function(val) { return Math.max(5, val[2] / 2); }"),
            label_opts=opts.LabelOpts(
                is_show=True,
                formatter=JsCode("function(p) { return p.value[0] + ': ' + p.data[3]; }"),
                position="top",
            ),
            itemstyle_opts=opts.ItemStyleOpts(
                color=JsCode("function(p) { return p.data[4]; }"),
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="技术成熟度气泡图", pos_left="center"),
            xaxis_opts=opts.AxisOpts(name="年份", type_="value"),
            yaxis_opts=opts.AxisOpts(name="技术成熟度", min_=0, max_=1,
                                     splitarea_opts=opts.SplitAreaOpts(is_show=True)),
            legend_opts=opts.LegendOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(
                formatter=JsCode(
                    "function(p) { return '年份: ' + p.value[0] + '<br/>成熟度: ' + p.value[1]"
                    " + '<br/>申请量: ' + p.data[2] + '<br/>阶段: ' + p.data[3]; }"
                ),
            ),
        )
    )


def plot_roadmap_timeline(result) -> Timeline:
    """技术路线图时间轴"""
    if not result.data:
        return Timeline(init_opts=get_dark_theme("1000px", "500px"))

    timeline = Timeline(init_opts=opts.InitOpts(theme="white", width="1100px", height="680px", bg_color="#ffffff"))
    for year in sorted(result.data.keys()):
        items = result.data[year]
        labels = [f"{it['patent_number']}: {it['title'][:60]}" for it in items][::-1]
        bar = (
            Bar()
            .add_xaxis(labels)
            .add_yaxis("核心专利", list(range(len(items), 0, -1)),
                       label_opts=opts.LabelOpts(is_show=True, position="right",
                                                  formatter="{b}", font_size=10),
                       itemstyle_opts=opts.ItemStyleOpts(color="#00BFFF"))
            .reversal_axis()
            .set_global_opts(
                title_opts=opts.TitleOpts(title=f"{year} 年核心技术专利"),
                xaxis_opts=opts.AxisOpts(is_show=False),
                legend_opts=opts.LegendOpts(is_show=False),
            )
        )
        timeline.add(bar, str(year))

    timeline.add_schema(is_auto_play=True, play_interval=2000, pos_left="center")
    return timeline


def plot_network(result) -> Graph:
    """申请人合作网络图"""
    if not result.edges:
        return Graph().set_global_opts(title_opts=opts.TitleOpts(title="无合作数据"))

    import networkx as nx
    G = nx.Graph()
    for e in result.edges:
        G.add_edge(e["source"], e["target"], weight=e["weight"])

    if G.number_of_nodes() > 50:
        top_nodes = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:50]
        top_set = {n for n, _ in top_nodes}
        G = G.subgraph(top_set).copy()

    degrees = dict(G.degree())
    max_deg = max(degrees.values()) if degrees else 1

    nodes_data = [
        {"name": n, "symbolSize": max(15, d / max_deg * 60), "category": 0}
        for n, d in degrees.items()
    ]
    links_data = [
        {"source": u, "target": v, "value": d.get("weight", 1)}
        for u, v, d in G.edges(data=True)
    ]

    return (
        Graph(init_opts=opts.InitOpts(theme="white", width="1100px", height="680px", bg_color="#ffffff"))
        .add(
            "", nodes_data, links_data,
            repulsion=2000, edge_length=[50, 300], gravity=0.1,
            is_draggable=True, is_roam=True, is_rotate_label=True,
            label_opts=opts.LabelOpts(is_show=True, position="right", font_size=11),
            edge_symbol=["none", "arrow"],
            linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.5, curve=0.1),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="申请人合作网络图", pos_left="center"),
            legend_opts=opts.LegendOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(
                formatter=JsCode(
                    "function(p) { return p.data.name + '<br/>合作数: ' + p.value; }"
                ),
            ),
        )
    )


def plot_clustering(result) -> Scatter:
    """聚类散点图（Phase 6 实现完整渲染）"""
    return (
        Scatter(init_opts=get_dark_theme())
        .set_global_opts(title_opts=opts.TitleOpts(title="专利聚类分析", pos_left="center"))
    )


def plot_tech_matrix(result) -> HeatMap:
    """技术功效矩阵热力图（Phase 6 实现完整渲染）"""
    return (
        HeatMap(init_opts=get_dark_theme())
        .set_global_opts(title_opts=opts.TitleOpts(title="技术功效矩阵", pos_left="center"))
    )
