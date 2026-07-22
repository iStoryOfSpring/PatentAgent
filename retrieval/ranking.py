"""Deterministic rank fusion helpers."""

from __future__ import annotations

from collections.abc import Iterable

from models.patent import PatentSummary


def reciprocal_rank_fusion(
    rankings: Iterable[list[PatentSummary]], top_k: int, constant: int = 60,
) -> list[PatentSummary]:
    """Fuse rankings without comparing incomparable lexical/vector scores."""
    scores: dict[str, float] = {}
    records: dict[str, PatentSummary] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item.patent_number] = scores.get(item.patent_number, 0.0) + 1.0 / (constant + rank)
            records.setdefault(item.patent_number, item)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))[:top_k]
    return [
        records[key].model_copy(update={"relevance_score": round(scores[key], 6)})
        for key in ordered
    ]
