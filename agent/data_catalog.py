"""Data Catalog: 预计算所有分析维度的轻量摘要，供 Agent 按需选取。

工作流程:
  1. 数据加载后调用 build_catalog() 预计算全部摘要
  2. Agent 收到用户问题后，将 catalog 作为 "数据菜单" 喂给 LLM
  3. LLM 选择需要的维度（data_keys），只加载选中数据
  4. 基于选中数据生成结论

优点: 减少上下文消耗，回答更精准，避免 LLM 猜测数据。
"""

import json
from typing import Optional
from dataclasses import dataclass, field

import pandas as pd

from engine.preprocessing import prepare_patent_df
from engine import trend, lifecycle, nlp, ipc_analysis, country_analysis
from engine import network_analysis, roadmap, clustering, valuation, tech_matrix


@dataclass
class DataCatalog:
    """预计算的数据目录。

    每个字段是一个轻量 JSON-serializable 摘要，包含足够信息让 LLM 判断
    是否需要该维度数据。
    """
    # 元信息
    total_patents: int = 0
    year_range: tuple[int, int] = (0, 0)
    top_ipc_sections: list[str] = field(default_factory=list)
    top_applicants: list[dict] = field(default_factory=list)

    # 各维度摘要（只有关键指标，不含全量数据）
    trend_summary: dict = field(default_factory=dict)
    lifecycle_summary: dict = field(default_factory=dict)
    ipc_summary: dict = field(default_factory=dict)
    word_freq_summary: dict = field(default_factory=dict)
    burst_summary: dict = field(default_factory=dict)
    country_summary: dict = field(default_factory=dict)
    network_summary: dict = field(default_factory=dict)
    clustering_summary: dict = field(default_factory=dict)
    valuation_summary: dict = field(default_factory=dict)
    tech_matrix_summary: dict = field(default_factory=dict)
    roadmap_summary: dict = field(default_factory=dict)

    # 全量数据（按需加载，不在 catalog 中传递）
    _full_data_cache: dict = field(default_factory=dict)

    def to_menu(self) -> str:
        """生成供 LLM 浏览的 '数据菜单'。

        Returns:
            人类可读 + LLM 可解析的数据维度描述
        """
        menu = [
            "# 可用数据维度 (Data Catalog)",
            "",
            f"## 数据集概况",
            f"- 专利总量: {self.total_patents:,}",
            f"- 时间跨度: {self.year_range[0]} – {self.year_range[1]}",
            f"- 主要 IPC: {', '.join(self.top_ipc_sections[:5]) if self.top_ipc_sections else 'N/A'}",
            f"- Top 申请人: {', '.join(a['name'] for a in self.top_applicants[:3]) if self.top_applicants else 'N/A'}",
            "",
            "## 可用的数据维度",
            "",
        ]

        dimensions = self._list_dimensions()
        for i, dim in enumerate(dimensions, 1):
            menu.append(f"### {i}. {dim['key']}")
            menu.append(f"描述: {dim['description']}")
            menu.append(f"内容: {dim['preview']}")
            menu.append("")

        menu.append("## 使用说明")
        menu.append(
            "请用户提出分析需求后，从上述维度中选择你需要的 data_keys。"
            "返回 JSON: {{\"selected_keys\": [\"dim_key1\", \"dim_key2\"], "
            "\"reasoning\": \"为什么选择这些维度\"}}"
        )
        return "\n".join(menu)

    def _list_dimensions(self) -> list[dict]:
        dims = []
        if self.trend_summary:
            dims.append({
                "key": "trend",
                "description": "专利申请的月度/年度趋势数据（申请量随时间变化）",
                "preview": json.dumps(self.trend_summary, ensure_ascii=False)[:300],
            })
        if self.lifecycle_summary:
            dims.append({
                "key": "lifecycle",
                "description": "累计公开量与年度增长方向（不自动划分生命周期阶段）",
                "preview": json.dumps(self.lifecycle_summary, ensure_ascii=False)[:300],
            })
        if self.ipc_summary:
            dims.append({
                "key": "ipc",
                "description": "IPC 分类分布（哪些技术领域专利最多）",
                "preview": json.dumps(self.ipc_summary, ensure_ascii=False)[:300],
            })
        if self.word_freq_summary:
            dims.append({
                "key": "word_freq",
                "description": "标题/摘要中的高频技术关键词及其频次",
                "preview": json.dumps(self.word_freq_summary, ensure_ascii=False)[:300],
            })
        if self.burst_summary:
            dims.append({
                "key": "burst_terms",
                "description": "技术突发词（近期快速增长的新兴技术方向）",
                "preview": json.dumps(self.burst_summary, ensure_ascii=False)[:300],
            })
        if self.country_summary:
            dims.append({
                "key": "country",
                "description": "专利申请的国家/地区分布",
                "preview": json.dumps(self.country_summary, ensure_ascii=False)[:200],
            })
        if self.network_summary:
            dims.append({
                "key": "network",
                "description": "申请人合作网络（联合申请情况）",
                "preview": json.dumps(self.network_summary, ensure_ascii=False)[:200],
            })
        if self.clustering_summary:
            dims.append({
                "key": "clustering",
                "description": "专利文本聚类分析（自动发现的技术主题群组）",
                "preview": json.dumps(self.clustering_summary, ensure_ascii=False)[:300],
            })
        if self.valuation_summary:
            dims.append({
                "key": "valuation",
                "description": "专利价值评估排名（Top 高价值专利）",
                "preview": json.dumps(self.valuation_summary, ensure_ascii=False)[:300],
            })
        if self.tech_matrix_summary:
            dims.append({
                "key": "tech_matrix",
                "description": "技术功效矩阵分析（热点 × 空白点 × 创新方向推荐）",
                "preview": json.dumps(self.tech_matrix_summary, ensure_ascii=False)[:300],
            })
        if self.roadmap_summary:
            dims.append({
                "key": "roadmap",
                "description": "技术路线图（每年核心技术专利时间轴）",
                "preview": json.dumps(self.roadmap_summary, ensure_ascii=False)[:200],
            })
        return dims

    def get_full_data(self, key: str) -> dict:
        """按需获取某个维度的完整数据（LLM 选中后才调用）。"""
        return self._full_data_cache.get(key, {})


def build_catalog(df: pd.DataFrame, nlp_texts: list[str] = None,
                  max_patents: int = 2000) -> DataCatalog:
    """从 DataFrame 构建完整 DataCatalog。

    对所有维度做轻量预计算，存入 catalog。
    完整数据缓存在 _full_data_cache 中，仅当 LLM 选中后才暴露。
    """
    cat = DataCatalog()

    # 预处理
    df = prepare_patent_df(df)
    if nlp_texts is None:
        nlp_texts = (df['title'].fillna('') + ' ' + df['abstract'].fillna('')).tolist()

    # ── 元信息 ──
    cat.total_patents = len(df)
    years = df['year'].dropna()
    cat.year_range = (
        (int(years.min()), int(years.max()))
        if not years.empty else (0, 0)
    )
    cat.top_ipc_sections = _safe_ipc_sections(df)
    cat.top_applicants = _safe_top_applicants(df)

    # ── 趋势 ──
    try:
        tr = trend.compute_yearly_trend(df)
        cat.trend_summary = {
            "years": [d["year"] for d in tr.data],
            "counts": [d["count"] for d in tr.data],
            "total": sum(d["count"] for d in tr.data),
        }
        cat._full_data_cache["trend"] = {
            "data": tr.data,
        }
    except Exception:
        pass

    # ── 生命周期 ──
    try:
        yearly = df.groupby('year').size().reset_index(name='count').sort_values('year')
        if len(yearly) >= 3:
            sc = lifecycle.fit_logistic_curve(yearly)
            stages = lifecycle.identify_lifecycle_stages(sc)
            cat.lifecycle_summary = {
                "stages": [{"stage": s[0], "from": s[1], "to": s[2]} for s in stages],
                "latest_year_count": sc.counts[-1] if sc.counts else 0,
                "total_cumulative": sc.cumulative[-1] if sc.cumulative else 0,
            }
            cat._full_data_cache["lifecycle"] = {
                "stages": stages,
                "years": sc.years,
                "counts": sc.counts,
                "cumulative": sc.cumulative,
            }
    except Exception:
        pass

    # ── IPC ──
    try:
        ipc_dist = ipc_analysis.compute_ipc_distribution(df)
        cat.ipc_summary = {
            "top_sections": [
                {"section": d["section"], "count": d["count"]}
                for d in ipc_dist.data[:8]
            ],
        }
        cat._full_data_cache["ipc"] = {"data": ipc_dist.data}
    except Exception:
        pass

    # ── 词频 ──
    try:
        wf = nlp.compute_word_frequency(nlp_texts)
        cat.word_freq_summary = {
            "top_words": wf.data[:15],
            "total_unique": len(wf.data),
        }
        # full_data 裁到 Top 30，避免 JSON 过大被截断
        cat._full_data_cache["word_freq"] = {"data": wf.data[:30]}
    except Exception:
        pass

    # ── 突发词 ──
    try:
        yearly_texts = {}
        for _, row in df.iterrows():
            yr = row.get('year')
            if not hasattr(yr, 'item') and yr is not None:
                pass
            if yr is None or (isinstance(yr, float) and yr != yr):
                continue
            yr_int = int(yr)
            title = str(row.get('title', ''))
            ab = str(row.get('abstract', ''))
            yearly_texts.setdefault(yr_int, '')
            yearly_texts[yr_int] += f' {title} {ab}'
        bt = nlp.compute_burst_terms(yearly_texts, top_n=15)
        if bt.data:
            cat.burst_summary = {
                "top_burst": bt.data[:10],
            }
            cat._full_data_cache["burst_terms"] = {"data": bt.data}
    except Exception:
        pass

    # ── 国家分布 ──
    try:
        cd = country_analysis.compute_country_distribution(df)
        cat.country_summary = {
            "top_countries": cd.data[:10],
        }
        cat._full_data_cache["country"] = {"data": cd.data}
    except Exception:
        pass

    # ── 合作网络 ──
    try:
        co = network_analysis.compute_co_occurrence(df)
        cat.network_summary = {
            "node_count": co.node_count,
            "edge_count": co.edge_count,
            "has_data": co.edge_count > 0,
        }
        cat._full_data_cache["network"] = {"edges": co.edges}
    except Exception:
        pass

    # ── 聚类 ──
    try:
        sample = nlp_texts[:min(len(nlp_texts), max_patents)]
        cr = clustering.run_clustering_pipeline(sample, n_clusters=5)
        if cr.cluster_keywords:
            cat.clustering_summary = {
                "n_clusters": len(cr.cluster_keywords),
                "keywords_per_cluster": {
                    str(k): v[:8] for k, v in cr.cluster_keywords.items()
                },
            }
            cat._full_data_cache["clustering"] = {
                "cluster_keywords": cr.cluster_keywords,
                "patents_per_cluster": cr.patents_per_cluster,
            }
    except Exception:
        pass

    # ── 价值评估 ──
    try:
        from tools.search_tool import _row_to_pseudo_patent
        sample_patents = [_row_to_pseudo_patent(row)
                          for _, row in df.head(min(len(df), max_patents)).iterrows()]
        ranked = valuation.rank_patents_by_value(sample_patents)
        if ranked:
            cat.valuation_summary = {
                "top_patents": ranked[:10],
            }
            cat._full_data_cache["valuation"] = {"ranked": ranked[:20]}
    except Exception:
        pass

    # ── 技术功效矩阵 ──
    try:
        from tools.search_tool import _row_to_pseudo_patent
        sample_patents = [_row_to_pseudo_patent(row)
                          for _, row in df.head(min(len(df), max_patents)).iterrows()]
        tm = tech_matrix.build_tech_effect_matrix_results(sample_patents, top_n=30)
        gaps = tech_matrix.find_gap_recommendations(sample_patents, top_n=120, top_gaps=10)
        if tm.functions and tm.effects:
            import numpy as np
            m = np.array(tm.matrix)
            cat.tech_matrix_summary = {
                "functions": tm.functions[:10],
                "effects": tm.effects[:10],
                "total_combinations": m.shape[0] * m.shape[1] if m.size > 0 else 0,
                "max_co_occurrence": int(m.max()) if m.size > 0 else 0,
                "zero_count": int((m == 0).sum()) if m.size > 0 else 0,
                "top_gaps": [
                    {"function": g["function"], "effect": g["effect"],
                     "patent_count": g["patent_count"]}
                    for g in gaps[:5]
                ],
            }
            cat._full_data_cache["tech_matrix"] = {
                "functions": tm.functions,
                "effects": tm.effects,
                "matrix": tm.matrix,
                "gap_recommendations": gaps,
            }
    except Exception:
        pass

    # ── 路线图 ──
    try:
        rm = roadmap.compute_roadmap_data(df, top_n_per_year=3)
        if rm.data:
            cat.roadmap_summary = {
                "years": sorted(rm.data.keys()),
                "has_data": True,
            }
            cat._full_data_cache["roadmap"] = {"data": rm.data}
    except Exception:
        pass

    return cat


def _safe_ipc_sections(df: pd.DataFrame) -> list[str]:
    sections = set()
    for codes in df.get('ipc', pd.Series(dtype=str)).dropna():
        for code in str(codes).split(';'):
            s = code.strip()[:1]
            if s and s.isalpha():
                sections.add(s)
    return sorted(sections)


def _safe_top_applicants(df: pd.DataFrame, top_n: int = 5) -> list[dict]:
    counts = {}
    for apps in df.get('applicants', pd.Series(dtype=str)).dropna():
        for a in str(apps).split(';'):
            a = a.strip()
            if a:
                counts[a] = counts.get(a, 0) + 1
    sorted_apps = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"name": name, "count": cnt} for name, cnt in sorted_apps]
