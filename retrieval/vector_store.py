"""ChromaDB 向量存储管理

metadata 字段: patent_number, is_deleted=False, year, ipc_section, title, abstract
search() 默认 where={"is_deleted": False} 保证 Top-K 语义不被软删除截断
"""

import os
import logging
from typing import Optional

import numpy as np

from models.patent import FullPatent, PatentSummary
from retrieval.embedding import build_embedding_text, create_embedding_provider

logger = logging.getLogger(__name__)

# ChromaDB 是可选的
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    chromadb = None


class PatentVectorStore:
    """ChromaDB 专利向量索引。

    嵌入文本: title + abstract + first_independent_claim
    metadata: {patent_number, is_deleted, year, ipc_section, title, abstract}
    """

    COLLECTION_NAME = "patents"
    _instance = None

    def __init__(self, persist_dir: str = "./data/chroma_db",
                 embedding_backend: str = "auto"):
        if not HAS_CHROMADB:
            raise ImportError(
                "chromadb not installed. Run: pip install chromadb"
            )
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._embedder = create_embedding_provider(backend=embedding_backend)

        # 获取或创建 collection
        try:
            self._collection = self._client.get_collection(
                self.COLLECTION_NAME,
            )
        except Exception:
            self._collection = self._client.create_collection(
                self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        self._id_counter = 0

    # ── 索引构建 ──
    def build_index(self, patents: list[FullPatent]) -> int:
        """全量构建索引。先清空 collection，再批量插入。

        Returns: 索引的专利数量
        """
        if not patents:
            return 0

        # 删除旧 collection 并重建
        try:
            self._client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        self._collection = self._client.create_collection(
            self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        # 分批处理
        batch_size = 1000
        total = 0
        for i in range(0, len(patents), batch_size):
            batch = patents[i:i + batch_size]
            total += self.add_patents(batch)
        return total

    def add_patents(self, patents: list[FullPatent]) -> int:
        """批量添加专利到索引"""
        if not patents:
            return 0

        ids = []
        texts = []
        metadatas = []
        for p in patents:
            pid = p.patent_number
            ids.append(pid)
            texts.append(build_embedding_text(p))
            metadatas.append(self._build_metadata(p))

        # 生成 embeddings
        vectors = self._embedder.embed(texts)

        # 添加
        self._collection.add(
            ids=ids,
            embeddings=vectors.tolist(),
            metadatas=metadatas,
            documents=texts,
        )
        return len(patents)

    def _build_metadata(self, patent: FullPatent) -> dict:
        ipc_section = ""
        if patent.ipc_codes:
            first = patent.ipc_codes[0]
            ipc_section = first[0] if first and first[0].isalpha() else ""
        year = 0
        if patent.publication_date and len(patent.publication_date) >= 4:
            try:
                year = int(patent.publication_date[:4])
            except ValueError:
                pass
        return {
            "patent_number": patent.patent_number,
            "is_deleted": False,
            "year": year,
            "ipc_section": ipc_section,
            "title": patent.title[:200],
            "abstract": patent.abstract[:200],
        }

    # ── 检索 ──
    def search(self, query: str, top_k: int = 20,
               filters: dict = None) -> list[PatentSummary]:
        """语义搜索。

        Args:
            query: 自然语言查询
            top_k: 返回数量
            filters: ChromaDB where 条件（如 {"year": {"$gte": 2020}}）

        Returns:
            PatentSummary 列表（轻量，不含 claims/description/citations）
        """
        # 默认过滤软删除
        where = {"is_deleted": False}
        if filters:
            where.update(filters)

        query_vec = self._embedder.embed([query])[0]

        results = self._collection.query(
            query_embeddings=[query_vec.tolist()],
            n_results=top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )

        return self._to_patent_summaries(results)

    def search_similar(self, patent_id: str,
                       top_k: int = 10) -> list[PatentSummary]:
        """查询与指定专利相似的专利"""
        # 先获取目标专利的 embedding
        existing = self._collection.get(
            ids=[patent_id],
            include=["embeddings"],
        )
        if not existing["embeddings"]:
            return []

        query_vec = existing["embeddings"][0]
        results = self._collection.query(
            query_embeddings=[query_vec],
            n_results=top_k + 1,  # +1 因为第一个可能是自己
            where={"is_deleted": False},
            include=["metadatas", "documents", "distances"],
        )

        summaries = self._to_patent_summaries(results)
        # 排除自身
        return [s for s in summaries if s.patent_number != patent_id][:top_k]

    def _to_patent_summaries(self,
                             chroma_results: dict) -> list[PatentSummary]:
        """ChromaDB 结果 → PatentSummary 列表"""
        ids_list = chroma_results.get("ids", [[]])[0]
        metas_list = chroma_results.get("metadatas", [[]])[0]
        distances = chroma_results.get("distances", [[]])[0]

        summaries = []
        for i, pid in enumerate(ids_list):
            meta = metas_list[i] if i < len(metas_list) else {}
            dist = distances[i] if i < len(distances) else 0.0
            # cosine distance → similarity score (0-1)
            score = max(0.0, 1.0 - dist) if dist else 1.0

            ipc_sec = meta.get("ipc_section", "")
            summaries.append(PatentSummary(
                patent_number=pid,
                title=meta.get("title", "")[:200],
                abstract=meta.get("abstract", "")[:500],
                applicants=[],  # metadata 不存全量申请人
                year=meta.get("year"),
                ipc_sections=[ipc_sec] if ipc_sec else [],
                relevance_score=round(score, 4),
            ))
        return summaries

    # ── 删除 ──
    def mark_deleted(self, patent_numbers: list[str]):
        """软删除: 更新 metadata.is_deleted=True"""
        for pid in patent_numbers:
            try:
                self._collection.update(
                    ids=[pid],
                    metadatas=[{"is_deleted": True}],
                )
            except Exception:
                logger.warning(f"Failed to mark_deleted: {pid}")

    def delete_by_ids(self, patent_ids: list[str]):
        """物理删除 ChromaDB 记录"""
        if patent_ids:
            self._collection.delete(ids=patent_ids)

    def rebuild_index(self, patents: list[FullPatent]):
        """全量重建索引"""
        self.build_index(patents)

    # ── 元数据 ──
    def count(self) -> int:
        """索引中的记录数"""
        try:
            return self._collection.count()
        except Exception:
            return 0


# ── 简易内存向量存储（无需 ChromaDB 的降级方案） ──
class InMemoryVectorStore:
    """内存向量存储 — 用于 ChromaDB 不可用时的降级方案"""

    def __init__(self, embedder=None):
        self._embedder = embedder or create_embedding_provider(backend="tfidf")
        self._ids: list[str] = []
        self._vectors: np.ndarray = None
        self._metadatas: list[dict] = []
        self._documents: list[str] = []

    def build_index(self, patents: list[FullPatent]) -> int:
        self._ids = []
        self._metadatas = []
        self._documents = []
        self._vectors = None
        if not patents:
            return 0
        for p in patents:
            self._ids.append(p.patent_number)
            self._metadatas.append(self._build_metadata(p))
            self._documents.append(build_embedding_text(p))
        if self._documents:
            self._vectors = self._embedder.embed(self._documents)
        return len(self._ids)

    def _build_metadata(self, patent: FullPatent) -> dict:
        ipc_section = ""
        if patent.ipc_codes:
            first = patent.ipc_codes[0]
            ipc_section = first[0] if first and first[0].isalpha() else ""
        year = 0
        if patent.publication_date and len(patent.publication_date) >= 4:
            try:
                year = int(patent.publication_date[:4])
            except ValueError:
                pass
        return {
            "patent_number": patent.patent_number,
            "is_deleted": False,
            "year": year,
            "ipc_section": ipc_section,
            "title": patent.title[:200],
            "abstract": patent.abstract[:200],
        }

    def search(self, query, top_k=20, filters=None) -> list[PatentSummary]:
        if self._vectors is None or len(self._ids) == 0:
            return []
        q_vec = self._embedder.embed([query])[0]
        # cosine similarity
        norms_d = np.linalg.norm(self._vectors, axis=1)
        norm_q = np.linalg.norm(q_vec)
        denom = norms_d * norm_q
        denom[denom == 0] = 1.0
        scores = np.dot(self._vectors, q_vec) / denom

        # 过滤 is_deleted
        valid_idx = [
            i for i, m in enumerate(self._metadatas)
            if not m.get("is_deleted", False)
        ]
        valid_scores = [(i, scores[i]) for i in valid_idx]
        valid_scores.sort(key=lambda item: (-float(item[1]), self._ids[item[0]]))

        summaries = []
        for idx, score in valid_scores[:top_k]:
            meta = self._metadatas[idx]
            ipc_sec = meta.get("ipc_section", "")
            summaries.append(PatentSummary(
                patent_number=self._ids[idx],
                title=meta.get("title", "")[:200],
                abstract=meta.get("abstract", "")[:500],
                applicants=[],
                year=meta.get("year"),
                ipc_sections=[ipc_sec] if ipc_sec else [],
                relevance_score=round(float(score), 4),
            ))
        return summaries

    def search_similar(self, patent_id, top_k=10) -> list[PatentSummary]:
        if patent_id not in self._ids:
            return []
        idx = self._ids.index(patent_id)
        q_vec = self._vectors[idx]
        scores = np.dot(self._vectors, q_vec) / (
            np.linalg.norm(self._vectors, axis=1) * np.linalg.norm(q_vec) + 1e-8
        )
        scored = [(i, float(scores[i])) for i in range(len(self._ids))
                  if i != idx and not self._metadatas[i].get("is_deleted", False)]
        scored.sort(key=lambda item: (-float(item[1]), self._ids[item[0]]))

        summaries = []
        for i, score in scored[:top_k]:
            meta = self._metadatas[i]
            ipc_sec = meta.get("ipc_section", "")
            summaries.append(PatentSummary(
                patent_number=self._ids[i],
                title=meta.get("title", "")[:200],
                abstract=meta.get("abstract", "")[:500],
                applicants=[],
                year=meta.get("year"),
                ipc_sections=[ipc_sec] if ipc_sec else [],
                relevance_score=round(score, 4),
            ))
        return summaries

    def mark_deleted(self, patent_numbers: list[str]):
        for m in self._metadatas:
            if m["patent_number"] in patent_numbers:
                m["is_deleted"] = True

    def add_patents(self, patents: list[FullPatent]) -> int:
        if not patents:
            return 0
        new_texts = [build_embedding_text(p) for p in patents]
        new_vecs = self._embedder.embed(new_texts)
        for i, p in enumerate(patents):
            self._ids.append(p.patent_number)
            self._documents.append(new_texts[i])
            self._metadatas.append(self._build_metadata(p))
        if self._vectors is None:
            self._vectors = new_vecs
        else:
            self._vectors = np.vstack([self._vectors, new_vecs])
        return len(patents)

    def count(self) -> int:
        return len(self._ids)


def create_vector_store(persist_dir: str = "./data/chroma_db",
                        embedding_backend: str = "auto",
                        prefer_chromadb: bool = True):
    """工厂函数: 优先 ChromaDB，降级内存存储"""
    if prefer_chromadb and HAS_CHROMADB:
        try:
            return PatentVectorStore(
                persist_dir=persist_dir,
                embedding_backend=embedding_backend,
            )
        except Exception:
            pass
    logger.info("使用 InMemoryVectorStore（无需 ChromaDB）")
    embedder = create_embedding_provider(backend=embedding_backend)
    return InMemoryVectorStore(embedder=embedder)
