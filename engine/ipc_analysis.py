"""IPC 分类分析（对应书第2章）"""

import pandas as pd

from models.analysis_results import (
    IPCMatrixResult, IPCDistributionResult, IPCTrendResult,
)


VALID_IPC_SECTIONS = set("ABCDEFGH")


def _expand_ipc_sections(
    df: pd.DataFrame, count_mode: str = "assignment_count",
) -> tuple[pd.DataFrame, list[str]]:
    """将 IPC 字段展开为 (year, section) 对"""
    rows = []
    invalid_codes: list[str] = []
    for position, row in df.iterrows():
        year = row.get('year')
        ipc_str = row.get('ipc', '')
        if pd.isna(year) or not ipc_str:
            continue
        for code in str(ipc_str).split(';'):
            normalized = code.strip().upper()
            section = normalized[0] if normalized else ''
            if section in VALID_IPC_SECTIONS:
                family_id = str(row.get("family_id", "") or "").strip()
                patent_id = str(row.get("patent_number", "") or position)
                rows.append({
                    'year': int(year), 'section': section,
                    'patent_id': patent_id,
                    'family_key': family_id or f"patent:{patent_id}",
                })
            elif normalized:
                invalid_codes.append(normalized)
    if not rows:
        return pd.DataFrame(columns=['year', 'section', 'patent_id', 'family_key']), invalid_codes
    expanded = pd.DataFrame(rows)
    if count_mode == "unique_patents":
        expanded = expanded.drop_duplicates(["year", "section", "patent_id"])
    elif count_mode == "family_normalized":
        expanded = expanded.drop_duplicates(["year", "section", "family_key"])
    elif count_mode != "assignment_count":
        raise ValueError(f"未知 IPC 计数模式: {count_mode}")
    return expanded, invalid_codes


def compute_ipc_year_matrix(
    df: pd.DataFrame, count_mode: str = "assignment_count",
) -> IPCMatrixResult:
    """年份 × IPC 部级（A–H）交叉分布矩阵"""
    expanded, invalid_codes = _expand_ipc_sections(df, count_mode)
    if expanded.empty:
        return IPCMatrixResult(
            result_type="ipc_matrix",
            years=[], sections=[], matrix=[],
            result_metadata={
                "count_mode": count_mode,
                "metric_label": _metric_label(count_mode),
                "invalid_ipc_count": len(invalid_codes),
            },
        )
    pivot = expanded.pivot_table(
        index='year', columns='section',
        aggfunc='size', fill_value=0,
    )
    years_sorted = sorted(pivot.index.tolist())
    sections_sorted = sorted(pivot.columns.tolist())
    matrix = [[int(pivot.loc[y, s]) for s in sections_sorted] for y in years_sorted]
    return IPCMatrixResult(
        result_type="ipc_matrix",
        years=years_sorted,
        sections=sections_sorted,
        matrix=matrix,
        result_metadata={
            "count_mode": count_mode,
            "metric_label": _metric_label(count_mode),
            "valid_sections": list("ABCDEFGH"),
            "invalid_ipc_count": len(invalid_codes),
            "invalid_ipc_examples": sorted(set(invalid_codes))[:20],
        },
        warnings=(
            [f"发现 {len(invalid_codes)} 个非 A-H IPC 标注，已排除并写入数据质量元数据。"]
            if invalid_codes else []
        ),
    )


def compute_ipc_distribution(df: pd.DataFrame) -> IPCDistributionResult:
    """IPC 部级分布统计（全时段汇总）"""
    expanded, _ = _expand_ipc_sections(df)
    if expanded.empty:
        return IPCDistributionResult(result_type="ipc_distribution", data=[])
    dist = expanded['section'].value_counts()
    data = [{"section": k, "count": int(v)} for k, v in dist.items()]
    return IPCDistributionResult(result_type="ipc_distribution", data=data)


def compute_ipc_trend(df: pd.DataFrame, section: str) -> IPCTrendResult:
    """单个 IPC 部的年度趋势"""
    expanded, _ = _expand_ipc_sections(df)
    sub = expanded[expanded['section'] == section]
    if sub.empty:
        return IPCTrendResult(result_type="ipc_trend", data=[])
    yearly = sub.groupby('year').size().reset_index(name='count')
    data = [{"year": int(r['year']), "section": section, "count": int(r['count'])}
            for _, r in yearly.iterrows()]
    return IPCTrendResult(result_type="ipc_trend", data=data)


def _metric_label(count_mode: str) -> str:
    return {
        "assignment_count": "IPC 标注次数",
        "unique_patents": "含该 IPC 部级的去重专利数",
        "family_normalized": "含该 IPC 部级的去重同族数",
    }[count_mode]
