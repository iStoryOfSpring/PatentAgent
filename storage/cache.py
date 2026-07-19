"""AnalysisCache — 分析结果缓存，避免重复计算"""

from models.analysis_results import AnalysisResult


class AnalysisCache:
    """Pydantic 模型自动支持 JSON 序列化。

    失效策略:
      - PatentRepository 每次数据变更后自动调用 invalidate(dataset_id)
      - 默认数据集级别失效（任一专利增减 → 清空该数据集所有缓存）
      - 支持按 result_type 粒度选择性失效
    """

    def __init__(self, cache_dir: str = "./data/cache"): ...

    def get(self, cache_key: str) -> AnalysisResult | None: ...

    def set(self, cache_key: str, result: AnalysisResult, ttl: int = 3600): ...

    def invalidate(self, dataset_id: str, result_type: str = None): ...

    def clear_all(self): ...
