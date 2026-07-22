"""End-to-end reproducibility contract over the committed synthetic dataset."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from engine.adapters.wos_adapter import WoSAdapter
from models.analysis_results import AnalysisResult
from storage.datastore import PatentDataStore
from tools import tool_registry
from scripts.generate_tool_goldens import canonical, fingerprint


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wos_golden"
PARAMETERS = {
    "analyze_patent_trend": {"chart_type": "yearly"},
    "analyze_lifecycle": {},
    "analyze_ipc_distribution": {},
    "generate_wordcloud": {"text_source": "title"},
    "analyze_burst_terms": {},
    "analyze_yearly_keywords": {"text_source": "title"},
    "analyze_co_network": {},
    "analyze_country_distribution": {},
    "analyze_tech_roadmap": {"top_n_per_year": 2},
    "get_dataset_summary": {},
    "search_patents": {"query": "solid electrolyte battery", "top_k": 5},
    "read_patent_details": {"patent_numbers": ["EP2019000000-A1"]},
    "analyze_tech_matrix": {"top_n": 10},
    "analyze_clustering": {"n_clusters": 6},
    "analyze_patent_valuation": {"top_n": 10, "citation_mode": "screening"},
    "analyze_competitor_evolution": {"top_n": 5},
}


def assert_golden_projection(actual, expected, path: str = "result") -> None:
    """Compare stable structure exactly and numeric metrics with CI-safe tolerance."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), path
        for key in expected:
            assert_golden_projection(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            assert_golden_projection(
                actual_item, expected_item, f"{path}[{index}]",
            )
        return
    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-6, abs=1e-6), path
        return
    assert actual == expected, path


@pytest.fixture(scope="module")
def golden_store() -> PatentDataStore:
    frame = WoSAdapter().batch_parse(str(FIXTURE_DIR))
    store = PatentDataStore(source_dir=str(FIXTURE_DIR))
    store.load_dataframe(frame)
    store._adapter_name = "wos_derwent"
    return store


def test_committed_wos_fixture_matches_golden_dataset_contract(golden_store):
    expected = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
    summary = golden_store.get_summary()
    audit = golden_store.audit()
    assert summary.total_patents == expected["record_count"]
    assert list(summary.year_range) == expected["year_range"]
    assert golden_store.get_all()["source_record_id"].nunique() == expected["unique_source_records"]
    assert audit["field_coverage"]["publication_date"] == expected["publication_date_coverage"]
    assert audit["field_coverage"]["ipc"] == expected["ipc_coverage"]
    assert audit["collaboration_coverage"]["multi_applicant_patents"] == expected["collaboration_patents"]
    assert audit["collaboration_coverage"]["multi_applicant_rate"] == expected["collaboration_rate"]
    assert audit["internal_citation_network"]["total_edges"] == expected["citation_edges"]


@pytest.mark.parametrize("tool_name", sorted(PARAMETERS))
def test_all_sixteen_tools_emit_traceable_contract(tool_name, golden_store):
    tool = tool_registry.get_tool(tool_name)
    assert tool.availability(golden_store)["available"], tool.availability(golden_store)
    result = asyncio.run(tool.run(golden_store, **PARAMETERS[tool_name]))
    assert isinstance(result, AnalysisResult)
    assert result.provenance is not None
    assert result.provenance.dataset_content_hash == golden_store.dataset_fingerprint()
    assert result.provenance.input_record_count == 300
    assert result.provenance.algorithm_id
    assert result.provenance.algorithm_version
    assert result.metrics.elapsed_ms >= 0
    assert result.evidence_level
    assert isinstance(result.source_capabilities, dict)
    assert isinstance(result.unsupported_conclusions, list)
    assert isinstance(result.data_as_of, str)
    envelope = tool.envelope(result)
    assert envelope.error is None
    assert envelope.tool.name == tool_name
    goldens = json.loads(
        (FIXTURE_DIR / "tool_goldens.json").read_text(encoding="utf-8")
    )["tools"]
    assert result.result_type == goldens[tool_name]["result_type"]
    payload = result.model_dump(mode="json")
    if fingerprint(payload) != goldens[tool_name]["sha256"]:
        assert_golden_projection(canonical(payload), goldens[tool_name]["projection"])


def test_key_algorithm_outputs_are_stable(golden_store):
    trend = asyncio.run(tool_registry.get_tool("analyze_patent_trend").run(
        golden_store, chart_type="yearly",
    ))
    assert trend.data == [
        {"year": year, "count": 50} for year in range(2019, 2025)
    ]

    first = asyncio.run(tool_registry.get_tool("analyze_clustering").run(
        golden_store, n_clusters=6,
    ))
    second = asyncio.run(tool_registry.get_tool("analyze_clustering").run(
        golden_store, n_clusters=6,
    ))
    assert first.labels == second.labels
    assert first.cluster_titles == second.cluster_titles
    assert first.silhouette_score == pytest.approx(second.silhouette_score, abs=1e-9)
