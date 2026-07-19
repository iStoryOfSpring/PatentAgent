"""专利价值筛查（工程指标 + von Wartburg et al. 2005 论文适配指标）

Engine 层 — 纯计算:
  - 多维度加权评分
  - 专利排名
  - 共享专业化 (Shared Specialization) 引证先进程度

von Wartburg 的相关性来自特定领域 107 个专利族，不能外推为财务价值。
普通 DII 筛查模式由 Tool 层移除不满足门禁的同族/SS 维度。
"""

from models.analysis_results import ValueIndicators


# 默认权重 (v1.4 重新校准)
# citation_count 和 cited_refs_count 降权 → shared_specialization 占据核心权重
DEFAULT_WEIGHTS = {
    # SS 已由 RO + BC 构成，评分中不再重复加入两个组成项。
    "shared_specialization": 0.35,
    "family_size": 0.20,
    "ipc_breadth": 0.15,
    "patent_age": 0.10,
    "is_triadic": 0.10,
    "cited_refs_count": 0.10,
}


def compute_patent_value_indicators(patents: list,
                                     citation_graph=None,
                                     ss_scores: dict = None) -> ValueIndicators:
    """多维度价值指标计算。

    指标:
      - shared_specialization: 引证网络位置综合得分 (von Wartburg)
      - reachability_out_degree: 纵向技术深度
      - bibliographical_coupling: 横向技术共享度
      - family_size: 同族专利数量
      - ipc_breadth: IPC 分类广度
      - patent_age: 专利年龄
      - cited_refs_count: 引用的参考文献数量（仅作参考）
      - is_triadic: 是否三方专利
    """
    from datetime import datetime
    current_year = datetime.now().year

    data = []
    for p in patents:
        pn = getattr(p, 'patent_number', '')
        # Family size includes the focal publication/family node itself.
        family = 1 + len(getattr(p, 'family_members', []) or [])
        claims = len(getattr(p, 'claims', []) or [])
        ipc_codes = getattr(p, 'ipc_codes', []) or []
        ipc_sections = set(c[0] for c in ipc_codes if c and c[0].isalpha())
        ipc_breadth = len(ipc_sections)
        backward = getattr(p, 'backward_citations', []) or []
        cited_refs_count = len(backward)

        # 专利年龄
        pub_date = getattr(p, 'publication_date', '') or ''
        patent_age = 0
        if pub_date and len(pub_date) >= 4:
            try:
                patent_age = current_year - int(pub_date[:4])
            except ValueError:
                pass

        # 三方专利
        family_pns = ' '.join(getattr(p, 'family_members', []) or [])
        has_us = 'US' in family_pns or pn.startswith('US')
        has_ep = 'EP' in family_pns or pn.startswith('EP')
        has_jp = 'JP' in family_pns or pn.startswith('JP')
        is_triadic = 1 if (has_us and has_ep and has_jp) else 0

        # 引证网络指标
        ss = ss_scores.get(pn, {}) if ss_scores else {}
        ss_val = ss.get("shared_specialization", 0.0)
        ro_val = ss.get("reachability_out_degree", 0.0)
        bc_val = ss.get("bibliographical_coupling", 0.0)

        data.append({
            "patent_number": pn,
            "title": getattr(p, 'title', '')[:100],
            "shared_specialization": ss_val,
            "reachability_out_degree": ro_val,
            "bibliographical_coupling": bc_val,
            "family_size": family,
            "ipc_breadth": ipc_breadth,
            "patent_age": patent_age,
            "cited_refs_count": cited_refs_count,
            "claim_count": claims,          # WoS 不可用
            "citation_count": 0,            # WoS 不可用 (forward citations)
            "is_triadic": is_triadic,
        })

    return ValueIndicators(result_type="value_indicators", data=data)


def compute_patent_value_score(patent: dict,
                               weights: dict = None) -> float:
    """单件专利加权价值评分 (0-100)。

    v1.4: shared_specialization 已是对数变换值 (log(RO+1))，不需要额外归一化。
    将其按最大值比例缩放至 0-1 区间。
    """
    w = weights or DEFAULT_WEIGHTS
    score = 0.0
    for key, weight in w.items():
        val = patent.get(key, 0) or 0
        if key == "patent_age":
            val = 1.0 - max(0, min(val, 20)) / 20  # 越新越高
        elif key == "family_size":
            val = min(val, 50) / 50
        elif key == "ipc_breadth":
            val = min(val, 8) / 8
        elif key == "cited_refs_count":
            val = min(val, 100) / 100
        elif key in ("shared_specialization", "reachability_out_degree",
                      "bibliographical_coupling"):
            # 对数变换值，除以典型最大值做缩放
            val = min(val, 10.0) / 10.0
        elif key in ("is_triadic",):
            val = float(val)
        else:
            val = min(val, 100) / 100
        score += val * weight * 100
    return round(score, 2)


def rank_patents_by_value(patents: list,
                          weights: dict = None,
                          citation_graph=None) -> list[dict]:
    """加权评分排名。

    如果提供了 citation_graph，自动计算所有专利的 SS 得分并融入排名。
    """
    # 构建 SS 得分映射
    ss_scores = {}
    if citation_graph is not None:
        from engine.citation import compute_all_shared_specialization
        ss_scores = compute_all_shared_specialization(citation_graph)

    indicators = compute_patent_value_indicators(
        patents, citation_graph=citation_graph, ss_scores=ss_scores,
    )
    scored = indicators.data
    if not scored:
        return []
    import pandas as pd
    frame = pd.DataFrame(scored)
    requested_weights = weights or DEFAULT_WEIGHTS
    available = {}
    for key, weight in requested_weights.items():
        values = pd.to_numeric(frame.get(key), errors="coerce").fillna(0)
        # age 即使相同仍是可用字段；其他全零指标不参与并自动重分配。
        if key == "patent_age" or bool((values != 0).any()):
            available[key] = weight
    weight_total = sum(available.values()) or 1.0
    normalized_weights = {k: v / weight_total for k, v in available.items()}
    frame["score"] = 0.0
    for key, weight in normalized_weights.items():
        values = pd.to_numeric(frame[key], errors="coerce").fillna(0)
        percentile = values.rank(method="average", pct=True)
        if key == "patent_age":
            percentile = 1.0 - percentile + (1.0 / len(frame))
        frame[f"{key}_percentile"] = percentile.round(4)
        frame["score"] += percentile * weight * 100
    scored = frame.to_dict(orient="records")
    for item in scored:
        item["score"] = round(float(item["score"]), 2)
        item["scoring_dimensions"] = sorted(normalized_weights)
    scored.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(scored):
        item["rank"] = i + 1
    return scored


def compute_patent_strength_index(patent: dict) -> float:
    """单件专利强度指数"""
    return compute_patent_value_score(patent)
