"""Tool: stable lexical retrieval plus an explicit multilingual beta mode."""

import html
import json
import time
from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import PatentSearchResult, PatentDetailsResult
from weakref import WeakKeyDictionary


class SearchTool(Tool):
    name = "search_patents"
    description = (
        "使用标题与摘要的 TF-IDF 词项相似度检索相关专利，"
        "支持按年份、IPC分类、申请人过滤；不等同于语义嵌入或查全检索。"
    )
    parameters = {
        "query": {
            "type": "string",
            "description": "自然语言检索描述，如'固态电池电解质材料'",
            "required": True,
        },
        "top_k": {
            "type": "integer",
            "description": "返回结果数量。默认 20。",
        },
        "year_start": {
            "type": "integer",
            "description": "起始年份过滤",
        },
        "year_end": {
            "type": "integer",
            "description": "结束年份过滤",
        },
        "ipc_filter": {
            "type": "array", "items": {"type": "string"},
            "description": "IPC 小类/主组过滤，如 H01M",
        },
        "applicant_filter": {
            "type": "string", "description": "申请人名称关键词过滤",
        },
        "retrieval_mode": {
            "type": "string",
            "enum": ["lexical", "multilingual_hybrid_beta"],
            "description": "默认 lexical；显式选择 multilingual_hybrid_beta 才会加载本地多语言模型。",
        },
    }
    required_fields = ("title", "abstract", "patent_number")
    methodology = "标题与摘要的 TF-IDF 混合检索；结果是相关性筛查，不等同于查全检索。"
    evidence_level = "engineering_approximation"

    async def execute(self, storage: PatentDataStore,
                      query: str = "",
                      top_k: int = 20,
                      year_start: int = None,
                      year_end: int = None,
                      ipc_filter: list[str] = None,
                      applicant_filter: str = None,
                      retrieval_mode: str = "lexical") -> PatentSearchResult:
        """Run the stable lexical baseline or explicitly selected beta."""
        year_range = None
        if year_start or year_end:
            year_range = (year_start or 1900, year_end or 2100)
        search_args = dict(
            query=query, top_k=top_k, year_range=year_range,
            ipc_filter=ipc_filter, applicant_filter=applicant_filter,
        )
        warnings: list[str] = []
        started = time.perf_counter()
        mode_used = retrieval_mode
        if retrieval_mode == "multilingual_hybrid_beta":
            try:
                lexical_searcher = _get_searcher(storage, "lexical")
                semantic_searcher = _get_searcher(storage, "multilingual_vector_beta")
                lexical = lexical_searcher.hybrid_search(**{
                    **search_args, "top_k": min(top_k * 3, 100),
                })
                semantic = semantic_searcher.hybrid_search(**{
                    **search_args, "top_k": min(top_k * 3, 100),
                })
                from retrieval.ranking import reciprocal_rank_fusion
                results = reciprocal_rank_fusion([lexical, semantic], top_k)
                warnings.append(
                    "多语言向量检索为 Beta：结果使用词法与 MiniLM 向量排名融合，"
                    "尚未经过专利专家查全率验证。"
                )
            except Exception as exc:
                results = _get_searcher(storage, "lexical").hybrid_search(**search_args)
                mode_used = "lexical"
                warnings.append(
                    "多语言向量检索 Beta 不可用，已明确回退到词法检索："
                    f"{type(exc).__name__}。请确认标准依赖已安装且首次模型下载可访问后重试。"
                )
        else:
            results = _get_searcher(storage, "lexical").hybrid_search(**search_args)
        query_time = round((time.perf_counter() - started) * 1000, 1)

        patents = [
            {
                "patent_number": r.patent_number,
                "title": r.title[:100],
                "abstract": r.abstract[:200],
                "applicants": ", ".join(r.applicants[:3]),
                "year": r.year,
                "relevance_score": r.relevance_score,
            }
            for r in results
        ]

        total_hits = len(patents)
        result = PatentSearchResult(
            result_type="patent_search",
            patents=patents,
            total_hits=total_hits,
            query_embedding_time_ms=query_time,
            warnings=warnings,
            result_metadata={
                "retrieval_mode_requested": retrieval_mode,
                "retrieval_mode_used": mode_used,
                "beta_fallback": retrieval_mode != mode_used,
                "embedding_model": (
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                    if mode_used == "multilingual_hybrid_beta" else ""
                ),
                "index": (
                    getattr(semantic_searcher, "index_metadata", {})
                    if mode_used == "multilingual_hybrid_beta" else {}
                ),
            },
        )

        # 搜索结果直接展示为列表（不需要图表）
        lines = [
            '<div style="background:#1a1a2e;color:#e0e0e0;padding:16px;'
            'border-radius:8px;font-family:monospace;line-height:1.6">',
            f'<b>检索结果: {total_hits} 件</b>',
            '<hr style="border-color:#333">',
        ]
        for i, p in enumerate(patents, 1):
            score_str = f" [{p.get('relevance_score', 0):.2f}]" if p.get('relevance_score') else ""
            lines.append(
                f'<b>{i}. {html.escape(str(p["patent_number"]))}</b>{score_str}<br>'
                f'{html.escape(str(p["title"][:120]))}<br>'
                f'<small>{html.escape(str(p.get("applicants", "")))}</small><br>'
            )
        lines.append('</div>')
        result.chart_html = '<br>'.join(lines)
        return result


class ReadPatentDetailsTool(Tool):
    name = "read_patent_details"
    description = (
        "读取指定专利在当前数据源中可用的结构化记录与 Derwent 摘要。"
        "仅当数据源实际提供时才展示权利要求、说明书或法律状态。"
        "仅在检索后需要深入了解某几篇专利时使用，单次最多查询 5 篇。"
    )
    requires_confirmation = True
    parameters = {
        "patent_numbers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要获取详情的专利号列表，最多 5 个",
            "maxItems": 5,
            "required": True,
        },
    }
    required_fields = ("patent_number",)
    optional_fields = ("claims_json", "description", "legal_status")
    methodology = "按公开号精确读取当前数据源已有字段；缺失全文和法律状态时不会推断。"

    async def execute(self, storage: PatentDataStore,
                      patent_numbers: list[str] = None) -> PatentDetailsResult:
        """从 DataFrame 按 patent_number 批量查询，返回 list[FullPatent]。

        Phase 4 使用 DataFrame 过渡，Phase 5+ 迁移到 SQLite PatentRepository。
        """
        from models.patent import FullPatent
        patent_numbers = (patent_numbers or [])[:5]
        if not patent_numbers:
            return PatentDetailsResult(patents=[], warnings=["未提供专利号。"])
        df = storage.get_all()
        if df.empty or 'patent_number' not in df.columns:
            return PatentDetailsResult(patents=[], warnings=["数据集中没有公开号字段。"])
        matched = df[df['patent_number'].isin(patent_numbers)]

        results = []
        for _, row in matched.iterrows():
            claims = []
            raw_claims = row.get("claims_json", "")
            if isinstance(raw_claims, str) and raw_claims.lstrip().startswith("["):
                try:
                    from models.patent import Claim
                    claims = [Claim.model_validate(item) for item in json.loads(raw_claims)]
                except (ValueError, TypeError):
                    claims = []
            fp = FullPatent(
                patent_number=str(row.get("patent_number", "")),
                normalized_patent_number=str(row.get("normalized_patent_number", "")),
                application_number=str(row.get("application_number", "")),
                source_record_id=str(row.get("source_record_id", "")),
                publication_numbers=_split_str(row.get("publication_numbers", "")),
                title=str(row.get("title", "")),
                abstract=str(row.get("abstract", "")),
                applicants=_split_str(row.get("applicants", "")),
                inventors=_split_str(row.get("inventors", "")),
                ipc_codes=_split_str(row.get("ipc", "")),
                cpc_codes=_split_str(row.get("cpc_codes", "")),
                publication_date=str(row.get("publication_date", row.get("date", ""))),
                priority_date=str(row.get("priority_date", "")),
                priority_numbers=_split_str(row.get("priority_numbers", "")),
                claims=claims,
                description=str(row.get("description", "") or ""),
                forward_citations=_split_str(row.get("forward_citations", "")),
                backward_citations=_split_str(
                    row.get("backward_citations", row.get("cited_refs", ""))
                ),
                non_patent_references=_split_lines(row.get("non_patent_references", "")),
                family_members=_split_str(row.get("family_members", "")),
                family_details=_split_str(row.get("family_details", "")),
                legal_status=str(row.get("legal_status", "") or ""),
                legal_status_as_of=str(row.get("legal_status_as_of", "") or ""),
                jurisdiction=str(row.get("jurisdiction", "") or ""),
                kind_code=str(row.get("kind_code", "") or ""),
                data_as_of=str(row.get("data_as_of", "") or ""),
                source_file="",
                imported_at="",
            )
            results.append(fp)
        payload = [item.model_dump() for item in results]
        warnings = []
        if not storage.has_field("claims_json"):
            warnings.append("当前数据源不含权利要求全文。")
        if not storage.has_field("legal_status"):
            warnings.append("当前数据源不含法律状态。")
        return PatentDetailsResult(patents=payload, warnings=warnings)


def _split_str(val) -> list[str]:
    if not val or not isinstance(val, str):
        return []
    return [s.strip() for s in val.split(';') if s.strip()]


def _split_lines(val) -> list[str]:
    if not val or not isinstance(val, str):
        return []
    return [s.strip() for s in val.splitlines() if s.strip()]


# ── 全局 searcher 缓存 ──
_searcher_cache: WeakKeyDictionary = WeakKeyDictionary()


def _get_searcher(storage: PatentDataStore, mode: str = "lexical"):
    """获取或创建 PatentSearcher（按 dataset 缓存）"""
    cached = _searcher_cache.setdefault(storage, {})
    if mode in cached:
        return cached[mode]

    from retrieval.search import PatentSearcher
    from retrieval.vector_store import create_vector_store

    backend = "tfidf" if mode == "lexical" else "sentence_transformers"
    vector_store = create_vector_store(
        persist_dir="./data/chroma_db",
        embedding_backend=backend,
        prefer_chromadb=False,  # exact lexical ranking; no persistent ANN state
    )
    searcher = PatentSearcher(
        vector_store=vector_store,
        patent_store=storage,
    )

    # Build or restore the explicit Beta index. The local model itself is
    # downloaded by sentence-transformers on first use.
    df = storage.get_all()
    restored = False
    index_dir = None
    if mode == "multilingual_vector_beta":
        from patent_agent.application import SearchIndexService
        from retrieval.embedding import MULTILINGUAL_BETA_MODEL
        cache = SearchIndexService()
        index_dir = cache.directory(storage.dataset_fingerprint(), MULTILINGUAL_BETA_MODEL)
        restored = vector_store.load_index(index_dir)
    if restored:
        searcher.index_metadata = {
            "cache_hit": True,
            "record_count": vector_store.count(),
            "index_version": "multilingual-rrf-v1",
            "cache_key": index_dir.name,
        }
    elif df.empty or 'title' not in df.columns:
        searcher.build_from_patents([])  # 空索引
    else:
        patents = [_row_to_pseudo_patent(row) for _, row in df.iterrows()]
        searcher.build_from_patents(patents)
        if index_dir is not None:
            size = vector_store.save_index(index_dir)
            searcher.index_metadata = {
                "cache_hit": False,
                "record_count": vector_store.count(),
                "index_size_bytes": size,
                "index_version": "multilingual-rrf-v1",
                "cache_key": index_dir.name,
            }

    cached[mode] = searcher
    return searcher


def _row_to_pseudo_patent(row) -> "FullPatent":
    """DataFrame row → FullPatent-like object for embedding.

    Explicitly converts all fields to plain Python types to avoid
    numpy array truth-value errors from Parquet deserialization.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        patent_number=str(row.get("patent_number", "")),
        title=str(row.get("title", "")),
        abstract=str(row.get("abstract", "")),
        claims=[],
        publication_date=str(row.get("publication_date", row.get("date", ""))),
        ipc_codes=list(_safe_list(row.get("ipc", ""))),
        backward_citations=list(_safe_list(
            row.get("backward_citations", row.get("cited_refs", ""))
        )),
        family_members=list(_safe_list(row.get("family_members", ""))),
        publication_numbers=list(_safe_list(row.get("publication_numbers", ""))),
        priority_numbers=list(_safe_list(row.get("priority_numbers", ""))),
        forward_citations=list(_safe_list(row.get("forward_citations", ""))),
    )


def _safe_list(val) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [c.strip() for c in val.split(';') if c.strip()]
    # numpy array or Python list from parquet
    if hasattr(val, 'tolist'):
        return [str(x).strip() for x in val.tolist() if str(x).strip()]
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]
    return []


# 注册
tool_registry.register(SearchTool())
tool_registry.register(ReadPatentDetailsTool())
