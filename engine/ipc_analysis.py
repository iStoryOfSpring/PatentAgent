"""IPC 分类分析（对应书第2章）"""

import pandas as pd

from models.analysis_results import (
    IPCMatrixResult, IPCDistributionResult, IPCTrendResult,
)


def _expand_ipc_sections(df: pd.DataFrame) -> pd.DataFrame:
    """将 IPC 字段展开为 (year, section) 对"""
    rows = []
    for _, row in df.iterrows():
        year = row.get('year')
        ipc_str = row.get('ipc', '')
        if pd.isna(year) or not ipc_str:
            continue
        for code in str(ipc_str).split(';'):
            section = code.strip()[0] if code.strip() else ''
            if section and section.isalpha():
                rows.append({'year': int(year), 'section': section})
    if not rows:
        return pd.DataFrame(columns=['year', 'section'])
    return pd.DataFrame(rows)


def compute_ipc_year_matrix(df: pd.DataFrame) -> IPCMatrixResult:
    """年份 × IPC 部级（A–H）交叉分布矩阵"""
    expanded = _expand_ipc_sections(df)
    if expanded.empty:
        return IPCMatrixResult(
            result_type="ipc_matrix",
            years=[], sections=[], matrix=[],
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
    )


def compute_ipc_distribution(df: pd.DataFrame) -> IPCDistributionResult:
    """IPC 部级分布统计（全时段汇总）"""
    expanded = _expand_ipc_sections(df)
    if expanded.empty:
        return IPCDistributionResult(result_type="ipc_distribution", data=[])
    dist = expanded['section'].value_counts()
    data = [{"section": k, "count": int(v)} for k, v in dist.items()]
    return IPCDistributionResult(result_type="ipc_distribution", data=data)


def compute_ipc_trend(df: pd.DataFrame, section: str) -> IPCTrendResult:
    """单个 IPC 部的年度趋势"""
    expanded = _expand_ipc_sections(df)
    sub = expanded[expanded['section'] == section]
    if sub.empty:
        return IPCTrendResult(result_type="ipc_trend", data=[])
    yearly = sub.groupby('year').size().reset_index(name='count')
    data = [{"year": int(r['year']), "section": section, "count": int(r['count'])}
            for _, r in yearly.iterrows()]
    return IPCTrendResult(result_type="ipc_trend", data=data)
