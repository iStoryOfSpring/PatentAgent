"""retrieval/ — 语义检索层（Phase 4）

向量化 → ChromaDB / InMemory 索引 → 混合检索
"""

from retrieval.embedding import (
    EmbeddingProvider, OpenAIEmbedding,
    SentenceTransformerEmbedding, TFIDFEmbedding,
    create_embedding_provider, build_embedding_text,
    embed_texts, embed_query,
)
from retrieval.vector_store import (
    PatentVectorStore, InMemoryVectorStore, create_vector_store,
)
from retrieval.search import PatentSearcher

__all__ = [
    "EmbeddingProvider", "OpenAIEmbedding",
    "SentenceTransformerEmbedding", "TFIDFEmbedding",
    "create_embedding_provider", "build_embedding_text",
    "embed_texts", "embed_query",
    "PatentVectorStore", "InMemoryVectorStore", "create_vector_store",
    "PatentSearcher",
]
