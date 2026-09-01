"""Structured search scope must be applied before relevance truncation."""

from types import SimpleNamespace

import numpy as np
import pandas as pd

from retrieval.search import PatentSearcher
from retrieval.vector_store import InMemoryVectorStore
from storage.datastore import PatentDataStore


class _KeywordEmbedder:
    def embed(self, texts):
        return np.array([
            [str(text).lower().count("battery"), str(text).lower().count("motor")]
            for text in texts
        ], dtype=np.float32)


def _patent(number, title, year, applicant, ipc):
    return SimpleNamespace(
        patent_number=number,
        title=title,
        abstract=title,
        claims=[],
        publication_date=f"{year}-01-01",
        applicants=[applicant],
        ipc_codes=[ipc],
    )


def _searcher():
    patents = [
        _patent("OLD-1", "battery battery battery", 2020, "Acme (R&D)", "H01M"),
        _patent("NEW-1", "battery", 2024, "Beta Corp", "H01M"),
        _patent("MOTOR-1", "motor", 2024, "Acme (R&D)", "H02K"),
    ]
    frame = pd.DataFrame({
        "patent_number": [p.patent_number for p in patents],
        "title": [p.title for p in patents],
        "abstract": [p.abstract for p in patents],
        "publication_date": [p.publication_date for p in patents],
        "date": [p.publication_date for p in patents],
        "applicants": [";".join(p.applicants) for p in patents],
        "inventors": ["I1", "I2", "I3"],
        "ipc": [";".join(p.ipc_codes) for p in patents],
    })
    store = PatentDataStore(frame)
    vector_store = InMemoryVectorStore(embedder=_KeywordEmbedder())
    vector_store.build_index(patents)
    return PatentSearcher(vector_store=vector_store, patent_store=store)


def test_inmemory_search_applies_year_filter_before_top_k():
    results = _searcher().hybrid_search(
        "battery", top_k=1, year_range=(2024, 2024),
    )
    assert [item.patent_number for item in results] == ["NEW-1"]


def test_inmemory_search_preserves_and_filters_applicants():
    results = _searcher().hybrid_search(
        "battery", top_k=10, applicant_filter="Beta",
    )
    assert [item.patent_number for item in results] == ["NEW-1"]
    assert results[0].applicants == ["Beta Corp"]


def test_applicant_filter_is_literal_not_regex():
    results = _searcher().hybrid_search(
        "battery", top_k=10, applicant_filter="Acme (R&D)",
    )
    assert {item.patent_number for item in results} == {"OLD-1", "MOTOR-1"}


def test_ipc_filter_happens_before_top_k():
    results = _searcher().hybrid_search(
        "motor", top_k=1, ipc_filter=["H01M"],
    )
    assert [item.patent_number for item in results] == ["NEW-1"]


def test_empty_structured_scope_returns_no_results():
    assert _searcher().hybrid_search(
        "battery", top_k=10, applicant_filter="Missing Entity",
    ) == []
