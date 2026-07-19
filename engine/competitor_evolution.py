"""IPC profile competitor evolution heuristics.

These metrics are descriptive engineering heuristics, not Tang et al.'s
PatentMiner DICT/PBC/HBC algorithms.
"""

import math
import numpy as np


def compute_competitor_evolution(df, top_n_applicants: int = 10) -> dict:
    """分析主要申请人的技术重心转移轨迹。

    Args:
        df: DataFrame with 'year', 'applicants', 'ipc' columns
        top_n_applicants: 分析前 N 个申请人

    Returns:
        {
            "applicants": [...],
            "evolution": [
                {
                    "applicant": "CATL",
                    "years": [2018, 2019, ...],
                    "focus_depth": [0.45, 0.42, ...],
                    "focus_breadth": [1.2, 1.5, ...],
                    "shift_index": [0, 0.12, ...],
                    "top_ipc": [["H01M", "B60L"], ["H01M", "C01G"], ...],
                    "trend_summary": "从电池材料(H01M)向电动车(B60L)扩展, 技术多元化趋势明显"
                },
                ...
            ],
            "cross_insights": "总体趋势描述"
        }
    """
    # Parse applicants and IPC
    applicant_counts = {}
    ipc_yearly = {}  # applicant → {year → {ipc_section → count}}

    for _, row in df.iterrows():
        year = row.get('year')
        if year is None or (isinstance(year, float) and math.isnan(year)):
            continue
        year = int(year)
        apps = str(row.get('applicants', '')).split(';')
        ipc_str = str(row.get('ipc', ''))

        for app in apps:
            app = app.strip()
            if not app:
                continue
            applicant_counts[app] = applicant_counts.get(app, 0) + 1

            if app not in ipc_yearly:
                ipc_yearly[app] = {}
            if year not in ipc_yearly[app]:
                ipc_yearly[app][year] = {}

            # IPC subclass / main-group proxy (e.g. H01M, B60L). WoS strings
            # are not always normalized deeply enough for subgroup analysis.
            for code in ipc_str.split(';'):
                normalized = ''.join(code.strip().split()).upper()
                section = normalized[:4]
                if len(section) == 4 and section[0].isalpha():
                    ipc_yearly[app][year][section] = ipc_yearly[app][year].get(section, 0) + 1

    # Select top applicants
    top_apps = sorted(applicant_counts.items(), key=lambda x: -x[1])[:top_n_applicants]
    top_app_names = [a for a, _ in top_apps]

    evolution = []
    all_sections = set()
    for app in top_app_names:
        if app not in ipc_yearly:
            continue
        years = sorted(ipc_yearly[app].keys())
        if len(years) < 2:
            continue

        # Build IPC profiles per year
        for y in years:
            for s in ipc_yearly[app].get(y, {}):
                all_sections.add(s)

    section_list = sorted(all_sections)

    for app in top_app_names:
        if app not in ipc_yearly:
            continue
        years = sorted(ipc_yearly[app].keys())
        if len(years) < 2:
            continue

        # Build yearly IPC vectors
        vectors = []
        for y in years:
            vec = np.zeros(len(section_list))
            total = sum(ipc_yearly[app][y].values())
            for si, sec in enumerate(section_list):
                vec[si] = ipc_yearly[app][y].get(sec, 0) / max(total, 1)
            vectors.append(vec)

        # Compute metrics
        focus_depth = []   # max IPC share per year
        focus_breadth = []  # entropy per year
        shift_index = [0.0]  # cosine distance from previous year
        top_ipc_by_year = []

        for yi, vec in enumerate(vectors):
            # Focus Depth
            focus_depth.append(round(float(np.max(vec)), 3))
            # IPC entropy
            ent = 0.0
            for v in vec:
                if v > 0:
                    ent -= v * math.log(v)
            focus_breadth.append(round(ent, 3))
            # Top IPC sections
            top_idx = np.argsort(vec)[::-1][:3]
            top_ipc = [section_list[i] for i in top_idx if vec[i] > 0.01]
            top_ipc_by_year.append(top_ipc)
            # IPC profile cosine shift
            if yi > 0:
                prev = vectors[yi - 1]
                cosine = np.dot(prev, vec) / (np.linalg.norm(prev) * np.linalg.norm(vec) + 1e-9)
                shift_index.append(round(float(1.0 - cosine), 3))

        # Trend summary
        summary = _build_trend_summary(app, years, top_ipc_by_year, focus_depth, focus_breadth, shift_index)

        evolution.append({
            "applicant": app,
            "years": years,
            "dominant_ipc_share": focus_depth,
            "ipc_entropy": focus_breadth,
            "ipc_profile_cosine_shift": shift_index,
            "top_ipc": top_ipc_by_year,
            "trend_summary": summary,
            "total_patents": applicant_counts.get(app, 0),
        })

    return {
        "applicants": top_app_names,
        "evolution": evolution,
        "cross_insights": _build_cross_insights(evolution),
        "methodology": "IPC subclass profile cosine shift, IPC entropy, dominant IPC share",
        "evidence_level": "engineering_heuristic_not_DICT",
    }


def _build_trend_summary(app, years, top_ipc, focus_depth, focus_breadth, shift_index) -> str:
    first_ipc = set(top_ipc[0]) if top_ipc else set()
    last_ipc = set(top_ipc[-1]) if top_ipc else set()
    new_domains = last_ipc - first_ipc
    dropped = first_ipc - last_ipc

    depth_change = focus_depth[-1] - focus_depth[0]
    breadth_change = focus_breadth[-1] - focus_breadth[0]

    parts = [f"{app}: {years[0]}-{years[-1]}年"]
    if new_domains:
        parts.append(f"新进入 {', '.join(new_domains)} 领域")
    if dropped:
        parts.append(f"退出 {', '.join(dropped)} 领域")
    if breadth_change > 0.1:
        parts.append("技术多元化趋势")
    elif breadth_change < -0.1:
        parts.append("技术收窄聚焦趋势")
    if depth_change < -0.1:
        parts.append("核心领域集中度下降(分散化)")

    return "；".join(parts) if len(parts) > 1 else f"{app}: 技术布局稳定"


def _build_cross_insights(evolution: list) -> str:
    if not evolution:
        return "数据不足，无法生成交叉洞察。"
    insights = []
    # Most diversified
    most_diverse = max(evolution, key=lambda e: e['ipc_entropy'][-1] if e['ipc_entropy'] else 0)
    insights.append(f"技术最多元化: {most_diverse['applicant']} (IPC熵={most_diverse['ipc_entropy'][-1]})")
    # Most focused
    most_focused = max(evolution, key=lambda e: e['dominant_ipc_share'][-1] if e['dominant_ipc_share'] else 0)
    insights.append(f"技术最聚焦: {most_focused['applicant']} (主导IPC份额={most_focused['dominant_ipc_share'][-1]})")
    # Fastest shifting
    if len(evolution) > 0:
        max_shift = max(evolution, key=lambda e: sum(e['ipc_profile_cosine_shift']) if e['ipc_profile_cosine_shift'] else 0)
        insights.append(f"IPC画像变化最大: {max_shift['applicant']} (累计余弦距离={sum(max_shift['ipc_profile_cosine_shift']):.2f})")

    return "；".join(insights)
