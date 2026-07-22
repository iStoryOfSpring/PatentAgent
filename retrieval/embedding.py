"""Text embedding providers used by explicitly selected retrieval modes."""

import os
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MULTILINGUAL_BETA_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ── 嵌入文本构建 ──
def build_embedding_text(patent) -> str:
    """按 Phase 4 嵌入策略拼接文本:
    1. title + abstract + first_independent_claim（默认）
    2. title + abstract（降级，claim 为空时）
    3. title only（极端降级）
    """
    title = patent.title or ""
    abstract = patent.abstract or ""

    # 尝试获取首项独立权利要求
    first_claim = ""
    if hasattr(patent, 'claims') and patent.claims:
        for c in patent.claims:
            if c.is_independent:
                first_claim = c.text[:1000]
                break

    if first_claim:
        return f"{title}\n{abstract}\n{first_claim}"
    elif abstract:
        return f"{title}\n{abstract}"
    else:
        return title


# ── Embedding Provider ──
class EmbeddingProvider:
    """文本向量化提供者"""

    def embed(self, texts: list[str]) -> np.ndarray:
        """批量文本 → 向量矩阵 (n_texts, dim)"""
        raise NotImplementedError


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI text-embedding-3-small"""

    def __init__(self, api_key: str = None, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var.")
        self.client = OpenAI(api_key=key)
        self.model = model

    def embed(self, texts: list[str]) -> np.ndarray:
        # OpenAI 单次最多 2048 条
        all_vectors = []
        batch_size = 500
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self.client.embeddings.create(
                model=self.model, input=batch,
            )
            vectors = [d.embedding for d in resp.data]
            all_vectors.extend(vectors)
        return np.array(all_vectors, dtype=np.float32)


class SentenceTransformerEmbedding(EmbeddingProvider):
    """本地 sentence-transformers 模型"""

    def __init__(self, model_name: str = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        self.model_name = model_name or MULTILINGUAL_BETA_MODEL
        self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(
            texts, show_progress_bar=False,
            convert_to_numpy=True, normalize_embeddings=True,
        )


class TFIDFEmbedding(EmbeddingProvider):
    """TF-IDF 降级方案 — 无需 API key，用于测试和开发"""

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=768, stop_words='english',
            ngram_range=(1, 2),
        )
        self._fitted = False

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            vectors = self.vectorizer.fit_transform(texts)
            self._fitted = True
        else:
            vectors = self.vectorizer.transform(texts)
        # 转为稠密矩阵并 L2 归一化
        dense = vectors.toarray().astype(np.float32)
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return dense / norms


# ── 工厂函数 ──
def create_embedding_provider(
    backend: str = "auto",
    openai_api_key: str = None,
    local_model: str = None,
) -> EmbeddingProvider:
    """创建 Embedding Provider。

    backend: "openai" | "sentence_transformers" | "tfidf" | "auto"
    auto: 依次尝试 OpenAI > sentence_transformers > TF-IDF
    """
    if backend == "openai":
        return OpenAIEmbedding(api_key=openai_api_key)
    elif backend == "sentence_transformers":
        return SentenceTransformerEmbedding(model_name=local_model)
    elif backend == "tfidf":
        return TFIDFEmbedding()
    elif backend == "auto":
        # 尝试 OpenAI
        if openai_api_key or os.getenv("OPENAI_API_KEY"):
            try:
                return OpenAIEmbedding(api_key=openai_api_key)
            except Exception:
                pass
        # 尝试本地 sentence-transformers
        try:
            return SentenceTransformerEmbedding(model_name=local_model)
        except Exception:
            pass
        # 降级 TF-IDF
        logger.info("使用 TF-IDF 降级方案（无需 API key）")
        return TFIDFEmbedding()
    else:
        raise ValueError(f"Unknown backend: {backend}")


# ── 便捷函数 ──
def embed_texts(texts: list[str],
                model: str = "text-embedding-3-small") -> np.ndarray:
    """批量文本向量化。

    Args:
        texts: 待向量化的文本列表
        model: OpenAI 模型名（仅 openai backend 生效），默认 text-embedding-3-small
    """
    provider = create_embedding_provider(
        backend="auto",
        openai_api_key=None,  # 从环境变量读取
    )
    # 如果用的是 OpenAI，设置模型
    if hasattr(provider, 'model') and model:
        provider.model = model
    return provider.embed(texts)


def embed_query(query: str,
                model: str = "text-embedding-3-small") -> np.ndarray:
    """单条查询向量化"""
    return embed_texts([query], model=model)[0]
