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
