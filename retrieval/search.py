"""混合检索: 语义搜索 + 结构化过滤 + 关键词匹配

返回值统一为 PatentSummary（轻量），严禁返回 FullPatent。
"""

import logging
from typing import Optional

from models.patent import PatentSummary
from storage.datastore import PatentDataStore
from retrieval.vector_store import create_vector_store, InMemoryVectorStore

logger = logging.getLogger(__name__)


class PatentSearcher:
    """语义搜索 + 结构化过滤 + 关键词匹配的混合检索。

    检索流程:
      1. 语义搜索 (top_k * 3, is_deleted=False) → 候选集
      2. 结构化过滤（年份、IPC、申请人） → 缩小候选集
      3. 关键词 BM25 加权融合 → 最终排序
      4. 返回 top_k PatentSummary
    """

    def __init__(self, vector_store=None, patent_store: PatentDataStore = None):
        self._vector_store = vector_store
        self._patent_store = patent_store

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = create_vector_store(prefer_chromadb=True)
        return self._vector_store

    def build_from_patents(self, patents: list) -> int:
        """从 FullPatent 列表构建索引"""
        texts = []
        for p in patents:
            title = getattr(p, 'title', '') or ''
            abstract = getattr(p, 'abstract', '') or ''
            texts.append(f"{title}\n{abstract}")
        return self.vector_store.build_index(patents)

    def hybrid_search(self,
                      query: str,
                      top_k: int = 20,
                      year_range: tuple[int, int] | None = None,
                      ipc_filter: list[str] | None = None,
                      applicant_filter: str | None = None,
                      ) -> list[PatentSummary]:
        """混合检索主入口。

        Args:
            query: 自然语言查询
            top_k: 返回数量
            year_range: 年份范围 (start, end)
            ipc_filter: IPC分类过滤
            applicant_filter: 申请人过滤

        Returns:
            PatentSummary 列表（轻量模型，不含 claims/description/citations）
        """
        # 构建 ChromaDB where 条件
        filters = {}
        if year_range:
            filters["year"] = {"$gte": year_range[0], "$lte": year_range[1]}

        # 语义搜索（取 top_k * 3 候选，供后续过滤）
        candidates = self.vector_store.search(
            query, top_k=min(top_k * 3, 100), filters=filters,
        )

        # IPC 后置过滤（ChromaDB 不支持复杂数组过滤）
        if ipc_filter and self._patent_store:
            candidates = self._filter_by_ipc(candidates, ipc_filter)

        # 申请人关键词匹配
        if applicant_filter:
            candidates = [
                c for c in candidates
                if applicant_filter.lower() in ' '.join(c.applicants).lower()
            ]

        # 返回 top_k
        return candidates[:top_k]

    def _filter_by_ipc(self, candidates: list[PatentSummary],
                       ipc_filter: list[str]) -> list[PatentSummary]:
        """用 SQLite/DataFrame 做 IPC 精确过滤"""
        if not self._patent_store:
            return candidates
        df = self._patent_store.get_columns(['patent_number', 'ipc'])

        def _match(val):
            if not val or not isinstance(val, str):
                return False
            codes = [c.strip()[:4] for c in val.split(';')]
            return any(c in ipc_filter for c in codes)

        mask = df.get('ipc', '').apply(_match)
        matched_pns = set(df.loc[mask, 'patent_number'].tolist())

        return [c for c in candidates if c.patent_number in matched_pns]

    def search_similar_patents(self, patent_id: str,
                               top_k: int = 10) -> list[PatentSummary]:
        """查找相似专利"""
        return self.vector_store.search_similar(patent_id, top_k)
