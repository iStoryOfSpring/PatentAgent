"""测试: engine/trend.py"""

import pandas as pd
import pytest

from engine.trend import (
    compute_monthly_trend, compute_yearly_trend, compute_growth_rate,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'year': [2020, 2020, 2020, 2021, 2021, 2022],
        'month': [1, 2, 3, 1, 2, 1],
        'date': ['2020-01-15', '2020-02-20', '2020-03-10',
                 '2021-01-05', '2021-02-18', '2022-01-22'],
    })


class TestMonthlyTrend:
    def test_normal(self, sample_df):
        result = compute_monthly_trend(sample_df)
        assert result.result_type == "monthly_trend"
        assert len(result.data) >= 1

    def test_empty(self):
        df = pd.DataFrame({'year': [], 'month': []})
        result = compute_monthly_trend(df)
        assert len(result.data) == 0


class TestYearlyTrend:
    def test_normal(self, sample_df):
        result = compute_yearly_trend(sample_df)
        assert result.result_type == "yearly_trend"
        years = [d["year"] for d in result.data]
        counts = [d["count"] for d in result.data]
        assert years == [2020, 2021, 2022]
        assert counts == [3, 2, 1]

    def test_empty(self):
        df = pd.DataFrame({'year': []})
        result = compute_yearly_trend(df)
        assert len(result.data) == 0


class TestGrowthRate:
    def test_normal(self, sample_df):
        result = compute_growth_rate(sample_df)
        assert result.result_type == "growth_rate"
        assert result.data[0]["growth_rate"] == 0.0  # 第一年无增长率
        assert result.data[1]["growth_rate"] < 0  # 2021 下降

    def test_single_year(self):
        df = pd.DataFrame({'year': [2020, 2020]})
        result = compute_growth_rate(df)
        assert len(result.data) == 1
        assert result.data[0]["growth_rate"] == 0.0

    def test_empty(self):
        df = pd.DataFrame({'year': []})
        result = compute_growth_rate(df)
        assert len(result.data) == 0


@pytest.mark.parametrize("cutoff",["","invalid","2026-99-99"])
def test_missing_source_cutoff_is_never_invented_from_observed_or_today(cutoff):
    from engine.trend import audit_publication_time_coverage
    frame=pd.DataFrame({"year":[2024,2024],"month":[1,3],"publication_date":["2024-01-01","2024-03-10"]})
    audit,warnings=audit_publication_time_coverage(frame,cutoff)
    assert audit["data_as_of"]==""
    assert audit["coverage_reference_date"]=="2024-03-10"
    assert audit["reference_basis"]=="observed_publication_max"
    assert audit["latest_year_missing_expected_months"]==[2]
    assert any("截止日期未知" in warning for warning in warnings)
    assert not any("截至" in warning for warning in warnings)


def test_cutoff_reference_without_dates_remains_unknown_and_real_cutoff_is_retained():
    from engine.trend import audit_publication_time_coverage
    frame=pd.DataFrame({"year":[2024],"month":[1]})
    unknown,warnings=audit_publication_time_coverage(frame)
    assert unknown["data_as_of"]==unknown["coverage_reference_date"]==""
    assert unknown["reference_basis"]=="unknown"
    provided,_=audit_publication_time_coverage(frame,"2024-03-31")
    assert provided["data_as_of"]==provided["coverage_reference_date"]=="2024-03-31"
    assert provided["reference_basis"]=="source_data_as_of"
