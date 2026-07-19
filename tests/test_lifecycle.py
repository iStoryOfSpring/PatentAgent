"""测试: engine/lifecycle.py"""

import pandas as pd
import pytest

from engine.lifecycle import (
    fit_logistic_curve, identify_lifecycle_stages, compute_maturity_index,
)


@pytest.fixture
def sample_yearly():
    """模拟一个完整的 S 形增长曲线"""
    return pd.DataFrame({
        'year': [2018, 2019, 2020, 2021, 2022],
        'count': [10, 30, 100, 200, 300],
    })


class TestFitLogisticCurve:
    def test_normal(self, sample_yearly):
        scurve = fit_logistic_curve(sample_yearly)
        assert scurve.result_type == "s_curve"
        assert len(scurve.years) == 5
        assert len(scurve.cumulative) == 5
        assert len(scurve.fitted) == 5
        # v1.4: 不再使用 Logistic 拟合，params 始终为 None
        assert scurve.params is None
        assert scurve.cumulative[-1] == sum(scurve.counts)  # 累计 = 申请量之和

    def test_insufficient_data(self):
        """少量数据点仍正常计算累计值"""
        yearly = pd.DataFrame({'year': [2020, 2021], 'count': [10, 20]})
        scurve = fit_logistic_curve(yearly)
        assert scurve.params is None
        assert scurve.cumulative[-1] == 30
        assert len(scurve.fitted) == 2

    def test_declining_trend(self):
        """下降趋势 — 累计值仍递增"""
        yearly = pd.DataFrame({
            'year': [2020, 2021, 2022],
            'count': [300, 200, 100],
        })
        scurve = fit_logistic_curve(yearly)
        assert len(scurve.cumulative) == 3
        assert scurve.cumulative[-1] == 600  # 300+200+100


class TestIdentifyStages:
    def test_normal(self, sample_yearly):
        scurve = fit_logistic_curve(sample_yearly)
        stages = identify_lifecycle_stages(scurve)
        assert len(stages) >= 1
        # v1.4: 阶段返回 (增长率标签, year, year) 格式
        for s in stages:
            assert '%' in s[0] or '+' in s[0]  # 包含增长率百分比
            assert s[1] <= s[2]

    def test_single_year(self):
        """单年数据"""
        yearly = pd.DataFrame({'year': [2020], 'count': [50]})
        scurve = fit_logistic_curve(yearly)
        assert scurve.params is None
        assert scurve.cumulative[-1] == 50


class TestMaturityIndex:
    def test_normal(self, sample_yearly):
        scurve = fit_logistic_curve(sample_yearly)
        maturity = compute_maturity_index(scurve)
        assert len(maturity) == 5
        assert 0.0 <= maturity[0] <= 1.0
        assert maturity[-1] == pytest.approx(1.0, abs=0.01)
