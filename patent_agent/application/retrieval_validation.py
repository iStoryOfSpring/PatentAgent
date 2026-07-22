"""Transparent proxy-label retrieval metrics.

These helpers deliberately know nothing about a retrieval implementation.  A
validation report must name the public proxy that created each relevance set;
the resulting numbers are engineering evidence, not expert novelty-search
validation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_10: float
    recall_at_20: float
    ndcg_at_10: float
    mrr: float
    query_count: int


def evaluate_rankings(
    rankings: Mapping[str, Sequence[str]],
    relevance: Mapping[str, Mapping[str, int]],
) -> RetrievalMetrics:
    """Evaluate deterministic rankings against graded public proxy labels."""
    query_ids = sorted(set(rankings) & set(relevance))
    if not query_ids:
        return RetrievalMetrics(0.0, 0.0, 0.0, 0.0, 0)
    recall10: list[float] = []
    recall20: list[float] = []
    ndcg10: list[float] = []
    reciprocal_ranks: list[float] = []
    for query_id in query_ids:
        ranking = list(dict.fromkeys(rankings[query_id]))
        labels = {key: int(value) for key, value in relevance[query_id].items() if value > 0}
        relevant = set(labels)
        denominator = max(len(relevant), 1)
        recall10.append(len(relevant.intersection(ranking[:10])) / denominator)
        recall20.append(len(relevant.intersection(ranking[:20])) / denominator)
        dcg = sum(
            (2 ** labels.get(document, 0) - 1) / math.log2(rank + 1)
            for rank, document in enumerate(ranking[:10], 1)
        )
        ideal = sorted(labels.values(), reverse=True)[:10]
        idcg = sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal, 1))
        ndcg10.append(dcg / idcg if idcg else 0.0)
        first = next((rank for rank, document in enumerate(ranking, 1) if document in relevant), None)
        reciprocal_ranks.append(1.0 / first if first else 0.0)
    mean = lambda values: round(sum(values) / len(values), 6)
    return RetrievalMetrics(
        recall_at_10=mean(recall10),
        recall_at_20=mean(recall20),
        ndcg_at_10=mean(ndcg10),
        mrr=mean(reciprocal_ranks),
        query_count=len(query_ids),
    )
