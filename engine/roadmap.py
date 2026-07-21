"""技术路线图分析（对应书第10章）

Engine 层:
  - compute_roadmap_data: 轻量版（每年 Top N 专利）
  - build_technology_roadmap: 完整版（引证 + 功效矩阵 + 价值 + 时间）

Phase 6 重写，综合 4 个维度构建技术路线图。
"""

from models.analysis_results import RoadmapResult
import pandas as pd


def compute_roadmap_data(df: 'pd.DataFrame',
                         top_n_per_year: int = 3) -> RoadmapResult:
    """每年 Top N 专利数据（轻量版，向后兼容 Phase 1）。"""
    df = df.copy()
    if 'date' in df.columns:
        df['year'] = pd.to_datetime(df['date'], errors='coerce').dt.year

    years = sorted(df['year'].dropna().unique())
    data: dict[int, list[dict]] = {}

    from engine.preprocessing import tokenize_text, filter_stopwords
    for year_val in years:
        year_int = int(year_val)
        df_year = df[df['year'] == year_int].copy()
        if df_year.empty:
            continue
        # 代表性 = 标题术语对当年主题的覆盖 + 可用的引证连接数。
        terms = []
        for title in df_year['title'].fillna(''):
            terms.extend(set(filter_stopwords(tokenize_text(str(title), min_len=3))))
        from collections import Counter
        theme_counts = Counter(terms)
        themes = [
            term for term, _ in sorted(
                theme_counts.items(), key=lambda item: (-item[1], item[0]),
            )[:5]
        ]
        def score(row):
            title_terms = set(filter_stopwords(tokenize_text(str(row.get('title', '')), min_len=3)))
            theme_score = sum(theme_counts[t] for t in title_terms if t in themes)
            refs = str(row.get('backward_citations', row.get('cited_refs', '')))
            return theme_score + len([x for x in refs.split(';') if x.strip()])
        df_year['_representative_score'] = df_year.apply(score, axis=1)
        df_year = df_year.sort_values('_representative_score', ascending=False).head(top_n_per_year)
        data[year_int] = [
            {"patent_number": str(r.get('patent_number', '')),
             "title": str(r.get('title', ''))[:120],
             "annual_themes": themes,
             "representative_score": int(r.get('_representative_score', 0))}
            for _, r in df_year.iterrows()
        ]

    return RoadmapResult(result_type="roadmap", data=data)


def build_technology_roadmap(
    patents: list,
    citation_graph=None,
    tech_functions: list = None,
    tech_effects: list = None,
    time_window: int = 5,
) -> dict:
    """完整技术路线图（Phase 6）。

    综合考虑:
      1. 专利引证关系 — 技术演进路径
      2. 技术功效矩阵 — 关键技术节点
      3. 专利价值评分 — 重点专利识别
      4. 时间维度 — 技术代际更替

    Returns:
        {
            "timeline": {year: [patent_summary, ...]},
            "key_nodes": [...],        # 技术路线关键节点
            "evolution_paths": [...],   # 演进路径
            "tech_generations": [...],  # 技术代际
            "summary": str,            # 路线图摘要
        }
    """
    from engine.valuation import rank_patents_by_value
    from engine.tech_matrix import build_tech_effect_matrix_results, find_density_hotspots
    from engine.citation import build_citation_graph, find_key_patents

    years = set()
    for p in patents:
        pub = getattr(p, 'publication_date', '') or ''
        if pub and len(pub) >= 4:
            try:
                years.add(int(pub[:4]))
            except ValueError:
                pass
    sorted_years = sorted(years)

    # 1. 时间线: 每年高价值专利
    ranked = rank_patents_by_value(patents) if patents else []
    ranked_by_pn = {r['patent_number']: r for r in ranked}

    timeline = {}
    for y in sorted_years:
        window_patents = []
        for p in patents:
            pub = getattr(p, 'publication_date', '') or ''
            if pub and len(pub) >= 4:
                try:
                    if int(pub[:4]) == y:
                        pn = getattr(p, 'patent_number', '')
                        score = ranked_by_pn.get(pn, {}).get('score', 0)
                        window_patents.append({
                            "patent_number": pn,
                            "title": getattr(p, 'title', '')[:100],
                            "score": score,
                        })
                except ValueError:
                    pass
        if window_patents:
            window_patents.sort(key=lambda x: x['score'], reverse=True)
            timeline[y] = window_patents[:5]

    # 2. 关键技术节点: Top 10 高价值专利
    key_nodes = [r for r in ranked[:10]]

    # 3. 演进路径: 引证关系（如果有引证数据）
    evolution_paths = []
    if citation_graph is not None and citation_graph.number_of_edges() > 0:
        key_patents_list = find_key_patents(citation_graph, top_k=5)
        for kp in key_patents_list[:3]:
            refs = list(citation_graph.successors(kp['patent_number']))
            cited_by = list(citation_graph.predecessors(kp['patent_number']))
            if refs or cited_by:
                evolution_paths.append({
                    "patent": kp['patent_number'],
                    "cites": refs[:5],
                    "cited_by": cited_by[:5],
                })

    # 4. 技术代际: 按时间窗口划分
    tech_generations = []
    if sorted_years:
        for i in range(0, len(sorted_years), time_window):
            window = sorted_years[i:i + time_window]
            if window:
                gen_patents = [p for p in patents
                               if getattr(p, 'publication_date', '')[:4] in [str(y) for y in window]]
                if gen_patents:
                    tech_generations.append({
                        "period": f"{window[0]}-{window[-1]}",
                        "patent_count": len(gen_patents),
                    })

    return {
        "timeline": timeline,
        "key_nodes": key_nodes,
        "evolution_paths": evolution_paths,
        "tech_generations": tech_generations,
        "summary": f"技术路线图: {len(sorted_years)} 年, "
                   f"{len(key_nodes)} 个关键节点, "
                   f"{len(evolution_paths)} 条演进路径",
    }
