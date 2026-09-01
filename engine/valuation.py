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
        availability = getattr(p, 'source_availability', {}) or {}
        # Family size includes the focal publication/family node itself.
        family_members = getattr(p, 'family_members', []) or []
        family = (
            1 + len(family_members)
            if availability.get("family_members", bool(family_members)) else None
        )
        claims = len(getattr(p, 'claims', []) or [])
        ipc_codes = getattr(p, 'ipc_codes', []) or []
        # Use IPC subclass breadth (for example H01M), not the overly coarse A-H section count.
        ipc_subclasses = {
            str(code).strip().upper()[:4]
            for code in ipc_codes
            if len(str(code).strip()) >= 4 and str(code).strip()[0].upper() in "ABCDEFGH"
        }
        ipc_breadth = len(ipc_subclasses) if ipc_subclasses else None
        backward = getattr(p, 'backward_citations', []) or []
        cited_refs_count = (
            len(backward)
            if availability.get("backward_citations", bool(backward)) else None
        )

        # 专利年龄
        pub_date = getattr(p, 'publication_date', '') or ''
        patent_age = None
        publication_year = None
        if pub_date and len(pub_date) >= 4:
            try:
                publication_year = int(pub_date[:4])
                patent_age = max(0, current_year - publication_year)
            except ValueError:
                pass

        # 三方专利
        family_pns = ' '.join(family_members)
        has_us = 'US' in family_pns or pn.startswith('US')
        has_ep = 'EP' in family_pns or pn.startswith('EP')
        has_jp = 'JP' in family_pns or pn.startswith('JP')
        is_triadic = (
            1 if (has_us and has_ep and has_jp) else 0
        ) if availability.get("family_members", bool(family_members)) else None

        # 引证网络指标
        ss = ss_scores.get(pn) if ss_scores else None
        ss_val = ss.get("shared_specialization") if ss is not None else None
        ro_val = ss.get("reachability_out_degree") if ss is not None else None
        bc_val = ss.get("bibliographical_coupling") if ss is not None else None
        primary_ipc = sorted(ipc_subclasses)[0] if ipc_subclasses else "unknown"

        data.append({
            "patent_number": pn,
            "title": getattr(p, 'title', '')[:100],
            "source_format": getattr(p, "source_format", "unknown") or "unknown",
            "publication_year": publication_year,
            "citation_normalization_group": f"{publication_year or 'unknown'}|{primary_ipc}",
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
    requested_weights = {
        key: float(weight) for key, weight in requested_weights.items()
        if key in frame.columns and float(weight) > 0
    }
    requested_total = sum(requested_weights.values()) or 1.0

    # Citation-network position is normalized within publication-year and IPC-subclass
    # observation groups. Other metadata dimensions are normalized within source strata.
    citation_dimensions = {
        "shared_specialization", "reachability_out_degree", "bibliographical_coupling",
    }
    for key in requested_weights:
        values = pd.to_numeric(frame[key], errors="coerce")
        grouping = (
            frame["citation_normalization_group"]
            if key in citation_dimensions else frame["source_format"]
        )
        percentile = values.groupby(grouping, dropna=False).rank(method="average", pct=True)
        if key == "patent_age":
            group_sizes = values.notna().groupby(grouping, dropna=False).transform("sum")
            percentile = 1.0 - percentile + (1.0 / group_sizes.clip(lower=1))
        frame[f"{key}_percentile"] = percentile.round(6)

    rows: list[dict] = []
    for _, row in frame.iterrows():
        dimensions = [
            key for key in requested_weights
            if pd.notna(row.get(key)) and pd.notna(row.get(f"{key}_percentile"))
        ]
        missing = sorted(set(requested_weights) - set(dimensions))
        available_weight = sum(requested_weights[key] for key in dimensions)
        available_ratio = available_weight / requested_total
        weighted_observed = sum(
            float(row[f"{key}_percentile"]) * requested_weights[key]
            for key in dimensions
        )
        score = 100 * weighted_observed / available_weight if available_weight else 0.0
        lower = 100 * weighted_observed / requested_total
        upper = lower + 100 * (1.0 - available_ratio)
        item = {
            key: (None if pd.isna(value) else value)
            for key, value in row.to_dict().items()
        }
        item.update({
            "score": round(score, 2),
            "score_interval": [round(lower, 2), round(min(100.0, upper), 2)],
            "available_weight_ratio": round(available_ratio, 4),
            "missing_dimensions": missing,
            "scoring_dimensions": sorted(dimensions),
            "confidence_level": (
                "high" if available_ratio >= 0.85
                else "medium" if available_ratio >= 0.6 else "low"
            ),
        })
        item["comparability_group"] = (
            f"{item.get('source_format', 'unknown')}|" + ",".join(sorted(dimensions))
        )
        rows.append(item)

    group_sizes: dict[str, int] = {}
    for item in rows:
        group = item["comparability_group"]
        group_sizes[group] = group_sizes.get(group, 0) + 1
    for item in rows:
        item["comparability_group_size"] = group_sizes[item["comparability_group"]]
        item["comparable_within_group"] = group_sizes[item["comparability_group"]] >= 2

    # A rank is only meaningful inside a group with the same source and dimensions.
    for group in sorted(group_sizes):
        members = [item for item in rows if item["comparability_group"] == group]
        members.sort(key=lambda item: (-item["score"], item["patent_number"]))
        for index, item in enumerate(members, start=1):
            item["rank"] = index
            item["rank_scope"] = "comparability_group"
    scored = sorted(
        rows,
        key=lambda item: (
            not item["comparable_within_group"],
            item["comparability_group"],
            item["rank"],
        ),
    )
    return scored


def compute_patent_strength_index(patent: dict) -> float:
    """单件专利强度指数"""
    return compute_patent_value_score(patent)
