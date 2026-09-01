from types import SimpleNamespace

from engine.tech_matrix import find_gap_recommendations


def _patent(number: str, technology: str, effect: str):
    return SimpleNamespace(
        patent_number=number,
        abstract=f"NOVELTY - {technology}. USE - {effect}.",
    )


def test_gap_candidates_use_expected_frequency_not_arbitrary_zero_order():
    patents = [
        _patent(f"B{i}", "cathode electrode", "energy storage") for i in range(10)
    ] + [
        _patent(f"F{i}", "membrane filter", "water filtration") for i in range(10)
    ]
    candidates = find_gap_recommendations(patents, top_n=20, top_gaps=10)
    assert candidates
    assert all("expected_count" in item for item in candidates)
    assert all("pearson_residual" in item for item in candidates)
    assert candidates[0]["patent_count"] == 0
    assert candidates[0]["expected_count"] > 0
    assert candidates[0]["pearson_residual"] < 0
    assert candidates[0]["lift"] == 0
