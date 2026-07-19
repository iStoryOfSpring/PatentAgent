"""专利公开趋势分析（WoS PD 公开日期）"""

from collections import Counter

import pandas as pd

from models.analysis_results import MonthlyTrendResult, YearlyTrendResult, GrowthRateResult


def compute_monthly_trend(df: pd.DataFrame) -> MonthlyTrendResult:
    """月度公开量趋势"""
    monthly = (
        df.groupby(['year', 'month']).size()
        .reset_index(name='count')
        .sort_values(['year', 'month'])
    )
    data = [
        {"year_month": f"{int(r['year'])}-{int(r['month']):02d}", "count": int(r['count'])}
        for _, r in monthly.iterrows()
    ]
    return MonthlyTrendResult(result_type="monthly_trend", data=data)


def compute_yearly_trend(df: pd.DataFrame) -> YearlyTrendResult:
    """年度公开量趋势"""
    yearly = df.groupby('year').size().reset_index(name='count').sort_values('year')
    data = [
        {"year": int(r['year']), "count": int(r['count'])}
        for _, r in yearly.iterrows()
    ]
    return YearlyTrendResult(result_type="yearly_trend", data=data)


def compute_growth_rate(df: pd.DataFrame) -> GrowthRateResult:
    """年增长率"""
    yearly = df.groupby('year').size().reset_index(name='count').sort_values('year')
    counts = yearly['count'].values
    data = []
    for i, (_, row) in enumerate(yearly.iterrows()):
        year = int(row['year'])
        count = int(row['count'])
        if i > 0 and counts[i-1] > 0:
            growth = round((count - counts[i-1]) / counts[i-1], 3)
        else:
            growth = 0.0
        data.append({"year": year, "count": count, "growth_rate": growth})
    return GrowthRateResult(result_type="growth_rate", data=data)


def compute_ipc_counts(df: pd.DataFrame) -> list[dict]:
    """IPC 辅助统计"""
    all_ipcs = []
    for codes in df['ipc'].dropna():
        all_ipcs.extend([code.strip()[:4] for code in codes.split(';')])
    ipc_ctr = Counter(all_ipcs)
    return [{"ipc": k, "count": v} for k, v in ipc_ctr.most_common()]
