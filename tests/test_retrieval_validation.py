from patent_agent.application.retrieval_validation import evaluate_rankings


def test_proxy_metrics_are_deterministic_and_graded():
    metrics = evaluate_rankings(
        {"q1": ["B", "A", "X"], "q2": ["Z", "C"]},
        {"q1": {"A": 2, "B": 1}, "q2": {"C": 1}},
    )
    assert metrics.query_count == 2
    assert metrics.recall_at_10 == 1.0
    assert metrics.recall_at_20 == 1.0
    assert metrics.mrr == 0.75
    assert 0 < metrics.ndcg_at_10 < 1


def test_empty_proxy_set_is_explicit():
    assert evaluate_rankings({}, {}).query_count == 0
