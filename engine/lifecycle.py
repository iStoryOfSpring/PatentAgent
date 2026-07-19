"""技术增长趋势分析 — 累计申请量 + 年增长率

v1.4 重构: 原来的 Logistic S 曲线拟合在 5 年数据上无统计意义
（3 参数模型，2 自由度，任意数据都能"拟合"）。
替换为诚实的数据展示: 累计量 + 年同比增长率。
"""

import numpy as np

from models.analysis_results import SCurveResult


def fit_logistic_curve(yearly_df: 'pd.DataFrame') -> SCurveResult:
    """计算累计申请量和年增长率。

    不再使用 Logistic 拟合——数据量不足时无统计意义。
    返回原始累计值作为 fitted（向后兼容，图表只展示实际数据）。

    Returns:
        SCurveResult(years, counts, cumulative, fitted, params=None)
    """
    yearly = yearly_df.sort_values('year')
    years = yearly['year'].values.astype(int)
    counts = yearly['count'].values.astype(int)
    cumulative = np.cumsum(counts)

    return SCurveResult(
        result_type="s_curve",
        years=years.tolist(),
        counts=counts.tolist(),
        cumulative=cumulative.tolist(),
        fitted=cumulative.astype(float).tolist(),
        params=None,   # v1.4: 不再使用 Logistic 拟合
    )


def identify_lifecycle_stages(scurve: SCurveResult) -> list[tuple[str, int, int]]:
    """计算年增长率并标注趋势方向。

    v1.4: 不再输出虚构的"萌芽/成长/成熟/衰退"标签。
    改为基于实际年增长率的方向判断。

    Returns:
        [(direction, year, growth_rate), ...] 逐年趋势
    """
    years = np.array(scurve.years)
    counts = np.array(scurve.counts)
    result = []
    for i in range(len(years)):
        if i == 0:
            growth = 0.0
        else:
            growth = round((counts[i] - counts[i - 1]) / max(counts[i - 1], 1), 3)
        result.append((f"{years[i]}年: {growth:+.1%}", int(years[i]), int(years[i])))
    return result


def compute_maturity_index(scurve: SCurveResult) -> 'np.ndarray':
    """归一化累计比例 (0~1)"""
    fitted = np.array(scurve.fitted)
    max_val = fitted[-1] if fitted[-1] > 0 else 1
    return fitted / max_val
