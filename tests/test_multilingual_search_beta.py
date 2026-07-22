"""The semantic path is explicit, deterministic and never a silent fallback."""

import asyncio
from types import SimpleNamespace

import numpy as np

from models.patent import PatentSummary
from patent_agent.application import SearchIndexService
from storage.datastore import PatentDataStore
from tools.search_tool import SearchTool
from retrieval.vector_store import InMemoryVectorStore


class _Searcher:
    def __init__(self, ids):
        self.ids = ids

    def hybrid_search(self, **_kwargs):
        return [
            PatentSummary(
                patent_number=patent_id, title=patent_id, abstract="",
                applicants=[], relevance_score=1 / rank,
            ) for rank, patent_id in enumerate(self.ids, 1)
        ]


def _store():
    import pandas as pd
    frame = pd.DataFrame([
        {"patent_number": "A", "title": "solid battery", "abstract": "electrolyte", "date": "2020-01-01", "ipc": "H01M", "applicants": "A"},
        {"patent_number": "B", "title": "固态电池", "abstract": "电解质", "date": "2021-01-01", "ipc": "H01M", "applicants": "B"},
    ])
    store = PatentDataStore(frame)
    store._adapter_name = "test"
    return store


def test_default_mode_remains_lexical(monkeypatch):
    monkeypatch.setattr("tools.search_tool._get_searcher", lambda _store, mode="lexical": _Searcher(["A", "B"]))
    result = asyncio.run(SearchTool().execute(_store(), query="battery", top_k=2))
    assert [item["patent_number"] for item in result.patents] == ["A", "B"]
    assert result.result_metadata["retrieval_mode_used"] == "lexical"
    assert not result.result_metadata["beta_fallback"]


def test_beta_fuses_lexical_and_multilingual_rankings(monkeypatch):
    def searcher(_store, mode="lexical"):
        return _Searcher(["A", "B"] if mode == "lexical" else ["B", "A"])

    monkeypatch.setattr("tools.search_tool._get_searcher", searcher)
    result = asyncio.run(SearchTool().execute(
        _store(), query="固态电池", top_k=2,
        retrieval_mode="multilingual_hybrid_beta",
    ))
    assert {item["patent_number"] for item in result.patents} == {"A", "B"}
    assert result.result_metadata["retrieval_mode_used"] == "multilingual_hybrid_beta"
    assert result.result_metadata["embedding_model"].endswith("MiniLM-L12-v2")
    assert any("Beta" in warning for warning in result.warnings)


def test_beta_failure_is_visible_and_uses_lexical_results(monkeypatch):
    def searcher(_store, mode="lexical"):
        if mode != "lexical":
            raise ImportError("sentence-transformers missing")
        return _Searcher(["A"])

    monkeypatch.setattr("tools.search_tool._get_searcher", searcher)
    result = asyncio.run(SearchTool().execute(
        _store(), query="battery", top_k=1,
        retrieval_mode="multilingual_hybrid_beta",
    ))
    assert result.result_metadata["retrieval_mode_requested"] == "multilingual_hybrid_beta"
    assert result.result_metadata["retrieval_mode_used"] == "lexical"
    assert result.result_metadata["beta_fallback"]
    assert "明确回退" in result.warnings[0]


def test_vector_index_cache_round_trip_without_pickle(tmp_path):
    class Embedder:
        def embed(self, texts):
            return np.array([[len(text), 1.0] for text in texts], dtype=np.float32)

    patent = SimpleNamespace(
        patent_number="US1B2", title="battery", abstract="solid electrolyte",
        claims=[], publication_date="2020-01-01", ipc_codes=["H01M"],
    )
    first = InMemoryVectorStore(embedder=Embedder())
    first.build_index([patent])
    assert first.save_index(tmp_path) > 0
    second = InMemoryVectorStore(embedder=Embedder())
    assert second.load_index(tmp_path)
    assert second.search("battery", top_k=1)[0].patent_number == "US1B2"


def test_search_status_reports_runtime_model_and_index_cache(tmp_path, monkeypatch):
    hf_home = tmp_path / "huggingface"
    model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    snapshot = hf_home / "hub" / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    index_root = tmp_path / "indexes"
    (index_root / "one").mkdir(parents=True)
    monkeypatch.setenv("HF_HOME", str(hf_home))
    monkeypatch.setattr("patent_agent.application.services.importlib.util.find_spec", lambda _name: object())

    status = SearchIndexService(index_root).status(model)

    assert status["dependency_installed"]
    assert status["model_cached"]
    assert status["index_count"] == 1
    assert status["download_size_mb"] == 471
