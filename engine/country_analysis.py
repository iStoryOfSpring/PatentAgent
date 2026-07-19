"""国家/地区分布分析"""

import pandas as pd

from models.analysis_results import CountryDistResult, CountryTrendResult


def compute_country_distribution(df: pd.DataFrame) -> CountryDistResult:
    """专利申请国家/地区分布（全时段汇总）"""
    if 'country' not in df.columns:
        return CountryDistResult(result_type="country_distribution", data=[])
    counts = df['country'].value_counts()
    data = [{"country": k, "count": int(v)} for k, v in counts.items()]
    return CountryDistResult(result_type="country_distribution", data=data)


def compute_country_distribution_by_year(df: pd.DataFrame) -> dict[int, list[dict]]:
    """每年单独的国家分布"""
    result = {}
    for year_val in sorted(df['year'].dropna().unique()):
        year_int = int(year_val)
        df_year = df[df['year'] == year_int]
        counts = df_year['country'].value_counts()
        result[year_int] = [
            {"country": k, "count": int(v)}
            for k, v in counts.items()
        ]
    return result


def compute_country_trend(df: pd.DataFrame) -> CountryTrendResult:
    """各国家年度趋势"""
    rows = []
    for year_val in sorted(df['year'].dropna().unique()):
        year_int = int(year_val)
        df_year = df[df['year'] == year_int]
        for country, count in df_year['country'].value_counts().items():
            rows.append({"year": year_int, "country": country, "count": int(count)})
    return CountryTrendResult(result_type="country_trend", data=rows)
