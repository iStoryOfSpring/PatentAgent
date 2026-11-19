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
        as_of = None
    reference = as_of
    reference_basis = "source_data_as_of" if as_of is not None else "unknown"
    if reference is None:
        dates = pd.to_datetime(df.get("publication_date", df.get("date", pd.Series(dtype=str))), errors="coerce")
        max_date = dates.max()
        if pd.notna(max_date):
            reference = max_date.date()
            reference_basis = "observed_publication_max"
    expected_tail_months = (
        set(range(1, reference.month + 1)) if reference is not None and latest_year == reference.year
        else set(range(1, 13)) if reference is not None else set()
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
        "data_as_of": as_of.isoformat() if as_of is not None else "",
        "coverage_reference_date": reference.isoformat() if reference is not None else "",
        "reference_basis": reference_basis,
        "latest_year": latest_year,
        "latest_year_months_covered": coverage[latest_year],
        "latest_year_is_partial_calendar_year": calendar_year_partial,
        "latest_year_missing_expected_months": missing_expected_tail,
        "historical_missing_months": historical_gaps,
        "publication_lag_possible": calendar_year_partial,
    }
    warnings = []
    if as_of is None:
        warnings.append("来源数据截止日期未知；最大公开日期仅用作观测月份参考，不代表来源更新时点。")
    if calendar_year_partial:
        warnings.append(
            f"尾年 {latest_year} 覆盖 {len(observed_tail)}/12 个月，属于部分自然年；"
            "不得把尾年下降解释为技术衰退。"
        )
    if missing_expected_tail:
        warnings.append(
            (f"截至 {as_of.isoformat()}，尾年缺少预期月份 " if as_of is not None else "按观测公开日期参考月份，尾年缺少月份 ")
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


def select_trend_population(storage, *, date_basis="publication", count_unit="publications", year_start=None, year_end=None, ipc_filter=None, applicant_filter=None, chart_type="monthly", **_):
    """Return counted units and their exact publication members, using real IDs."""
    from engine.adapters.common import normalized_application_number
    import hashlib
    import json
    column={"publication":"publication_date","filing":"filing_date","priority":"priority_date","grant":"grant_date"}[date_basis]
    df=storage.query(ipc_filter=ipc_filter,applicant_filter=applicant_filter).copy()
    df["_basis_date"]=pd.to_datetime(df.get(column,pd.Series(index=df.index,dtype=str)),errors="coerce")
    missing_dates=int(df["_basis_date"].isna().sum())
    id_column={"publications":"patent_number","applications":"application_number","families":"family_id"}[count_unit]
    ids=df.get(id_column,pd.Series("",index=df.index)).fillna("").astype(str).str.strip()
    if count_unit=="applications":ids=ids.map(normalized_application_number)
    missing_ids=int(ids.eq("").sum());df["_unit_id"]=ids
    df=df[ids.ne("")]
    units=[];membership={}
    for ident,group in df.groupby("_unit_id",sort=True):
        valid=group["_basis_date"].dropna()
        if valid.empty:continue
        selected=valid.min();year=int(selected.year)
        if year_start is not None and year<year_start or year_end is not None and year>year_end:continue
        bin_id=f"{year}-{selected.month:02d}" if chart_type=="monthly" else str(year)
        numbers=sorted(set(group["patent_number"].astype(str)))
        membership.setdefault(bin_id,[]).append({"unit_id":str(ident),"date":selected.date().isoformat(),"publication_numbers":numbers})
        units.append({"year":year,"month":int(selected.month),"publication_date":selected.date().isoformat()})
    descriptors={key:{"unit_count":len(value),"membership_sha256":hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()} for key,value in membership.items()}
    return pd.DataFrame(units,columns=["year","month","publication_date"]),membership,{"date_basis":date_basis,"count_unit":count_unit,"date_semantics":column,"missing_date_records":missing_dates,"missing_identity_records":missing_ids,"excluded_missing_unit_or_date":True,"evidence_bins":descriptors,"evidence_selector_version":"trend-units-v1"}
