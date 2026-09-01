"""专利公开趋势分析（WoS PD 公开日期）"""

from collections import Counter
from datetime import date

import pandas as pd

from models.analysis_results import MonthlyTrendResult, YearlyTrendResult, GrowthRateResult


def audit_publication_time_coverage(
    df: pd.DataFrame, data_as_of: str = "",
) -> tuple[dict, list[str]]:
    """Separate partial tail years, historical gaps and publication lag warnings."""
    if df.empty or "year" not in df or "month" not in df:
        return {}, []
    valid = df.dropna(subset=["year", "month"]).copy()
    if valid.empty:
        return {}, []
    coverage = {
        int(year): sorted({int(month) for month in group["month"] if 1 <= int(month) <= 12})
        for year, group in valid.groupby("year")
    }
    latest_year = max(coverage)
    try:
        as_of = date.fromisoformat(str(data_as_of)[:10])
    except (TypeError, ValueError):
        max_date = pd.to_datetime(
            df.get("publication_date", df.get("date")), errors="coerce",
        ).max()
        as_of = max_date.date() if pd.notna(max_date) else date.today()
    expected_tail_months = (
        set(range(1, as_of.month + 1)) if latest_year == as_of.year
        else set(range(1, 13))
    )
    observed_tail = set(coverage[latest_year])
    calendar_year_partial = len(observed_tail) < 12
    missing_expected_tail = sorted(expected_tail_months - observed_tail)
    historical_gaps = {
        year: sorted(set(range(1, 13)) - set(months))
        for year, months in coverage.items()
        if year < latest_year and len(months) < 12
    }
    metadata = {
        "data_as_of": as_of.isoformat(),
        "latest_year": latest_year,
        "latest_year_months_covered": coverage[latest_year],
        "latest_year_is_partial_calendar_year": calendar_year_partial,
        "latest_year_missing_expected_months": missing_expected_tail,
        "historical_missing_months": historical_gaps,
        "publication_lag_possible": calendar_year_partial,
    }
    warnings = []
    if calendar_year_partial:
        warnings.append(
            f"尾年 {latest_year} 覆盖 {len(observed_tail)}/12 个月，属于部分自然年；"
            "不得把尾年下降解释为技术衰退。"
        )
    if missing_expected_tail:
        warnings.append(
            f"截至 {as_of.isoformat()}，尾年缺少预期月份 "
            + ",".join(map(str, missing_expected_tail))
            + "；可能存在批次收录缺口。"
        )
    if historical_gaps:
        warnings.append(
            f"{len(historical_gaps)} 个历史年份存在缺月，年度比较可能受批次缺口影响。"
        )
    if calendar_year_partial:
        warnings.append("专利公开存在法定与数据库收录滞后，近期公开量通常会低估最终水平。")
    return metadata, warnings


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
