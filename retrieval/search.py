"""混合检索: 语义搜索 + 结构化过滤 + 关键词匹配

返回值统一为 PatentSummary（轻量），严禁返回 FullPatent。
"""

import logging

from models.patent import PatentSummary
from storage.datastore import PatentDataStore
from retrieval.vector_store import create_vector_store, InMemoryVectorStore

logger = logging.getLogger(__name__)


class PatentSearcher:
    """语义搜索 + 结构化过滤 + 关键词匹配的混合检索。

    检索流程:
      1. 在 PatentDataStore 上解析年份、IPC、申请人结构化范围
      2. 将符合范围的专利号集合传给检索后端
      3. 仅在该集合内计算相关性并排序
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
        filters: dict = {}
        has_structured_scope = bool(year_range or ipc_filter or applicant_filter)
        if has_structured_scope and self._patent_store is not None:
            scoped = self._patent_store.query(
                year_start=year_range[0] if year_range else None,
                year_end=year_range[1] if year_range else None,
                ipc_filter=ipc_filter,
                applicant_filter=applicant_filter,
            )
            if scoped.empty or "patent_number" not in scoped.columns:
                return []
            allowed = sorted({
                str(value) for value in scoped["patent_number"].dropna()
                if str(value).strip()
            })
            if not allowed:
                return []
            filters["patent_number"] = {"$in": allowed}
        elif year_range:
            # A standalone vector store can still apply the scalar year range.
            filters["year"] = {"$gte": year_range[0], "$lte": year_range[1]}

        return self.vector_store.search(
            query, top_k=top_k, filters=filters or None,
        )

    def search_similar_patents(self, patent_id: str,
                               top_k: int = 10) -> list[PatentSummary]:
        """查找相似专利"""
        return self.vector_store.search_similar(patent_id, top_k)
