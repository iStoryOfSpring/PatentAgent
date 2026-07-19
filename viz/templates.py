"""Pyecharts 统一主题与样式配置"""

from pyecharts import options as opts


# 生命周期阶段配色
STAGE_COLORS = {
    '萌芽期': '#87CEEB',
    '成长期': '#32CD32',
    '成熟期': '#FFA500',
    '衰退期': '#FF6B6B',
}

# 逐年关键词配色
YEARLY_COLORS = [
    '#00BFFF', '#FFD700', '#32CD32', '#FF6347', '#9370DB',
    '#FF69B4', '#20B2AA', '#FFA500', '#87CEEB', '#98FB98',
]

# IPC 热力图渐变
HEATMAP_COLORS = ["#F5F5F5", "#C6E48B", "#7BC96F", "#239A3B", "#196127"]


def get_dark_theme(width: str = "960px",
                   height: str = "520px") -> opts.InitOpts:
    """兼容旧函数名的浅色专业主题配置。"""
    return opts.InitOpts(theme="white", width=width, height=height,
                         bg_color="#ffffff")


def get_default_size() -> tuple[str, str]:
    """默认图表尺寸"""
    return ("960px", "520px")
