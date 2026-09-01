"""Missing metadata remains missing and valuation ranks only comparable records."""

from types import SimpleNamespace

from engine.valuation import rank_patents_by_value


def _patent(number: str, *, family=None, backward=None, source="wos", year=2020):
    return SimpleNamespace(
        patent_number=number,
        title=number,
        publication_date=f"{year}-01-01" if year else "",
        ipc_codes=["H01M10/00"],
        family_members=family or [],
        backward_citations=backward or [],
        claims=[],
        source_format=source,
        source_availability={
            "publication_date": bool(year),
            "ipc": True,
            "family_members": family is not None,
            "backward_citations": backward is not None,
        },
    )


def test_missing_family_and_references_are_not_scored_as_zero():
    ranked = rank_patents_by_value([
        _patent("P-MISSING", family=None, backward=None),
        _patent("P-ZERO", family=[], backward=[]),
    ], weights={"family_size": 0.5, "cited_refs_count": 0.5})
    by_id = {item["patent_number"]: item for item in ranked}

    assert by_id["P-MISSING"]["family_size"] is None
    assert set(by_id["P-MISSING"]["missing_dimensions"]) == {
        "cited_refs_count", "family_size",
    }
    assert by_id["P-MISSING"]["available_weight_ratio"] == 0.0
    assert by_id["P-MISSING"]["score_interval"] == [0.0, 100.0]
    assert by_id["P-ZERO"]["family_size"] == 1
    assert by_id["P-ZERO"]["cited_refs_count"] == 0
    assert by_id["P-ZERO"]["available_weight_ratio"] == 1.0


def test_source_and_dimension_signature_define_comparability_group():
    ranked = rank_patents_by_value([
        _patent("W1", family=[], backward=[], source="wos"),
        _patent("W2", family=["EP2"], backward=["P1"], source="wos"),
        _patent("G1", family=[], backward=[], source="google_patents"),
    ], weights={"family_size": 0.5, "cited_refs_count": 0.5})
    by_id = {item["patent_number"]: item for item in ranked}

    assert by_id["W1"]["comparability_group"] == by_id["W2"]["comparability_group"]
    assert by_id["W1"]["comparable_within_group"] is True
    assert by_id["G1"]["comparability_group"] != by_id["W1"]["comparability_group"]
    assert by_id["G1"]["comparable_within_group"] is False
    assert by_id["W2"]["rank_scope"] == "comparability_group"
