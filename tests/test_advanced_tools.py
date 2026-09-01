"""Contracts and scientific gates for NT-001 through NT-008."""

import asyncio
import json

import pandas as pd
import pytest

from storage.datastore import PatentDataStore
from tools import tool_registry


def _store() -> PatentDataStore:
    claims = json.dumps([
        {"number": 1, "text": "A battery comprising a cell; an electrolyte.", "is_independent": True, "depends_on": [], "language": "en"},
        {"number": 2, "text": "The battery of claim 1, wherein the electrolyte is solid.", "is_independent": False, "depends_on": [1], "language": "en"},
    ])
    frame = pd.DataFrame({
        "patent_number": ["US1A1", "EP2A1", "JP3A"],
        "publication_date": ["2022-01-01", "2023-02-01", "2024-03-01"],
        "date": ["2022-01-01", "2023-02-01", "2024-03-01"],
        "title": ["solid battery", "battery electrolyte", "robot sensor"],
        "abstract": ["solid electrolyte cell", "electrolyte battery", "optical robot sensor"],
        "applicants": ["Acme Inc.;Beta Ltd", "ACME", "Gamma"],
        "inventors": ["Li", "Li;Wang", "Tanaka"],
        "ipc": ["H01M;H02J", "H01M", "G01D"],
        "family_id": ["F1", "F1", "F3"],
        "family_members": ["EP1A1;JP1A", "US2A1", ""],
        "priority_numbers": ["CN100", "US200", "JP300"],
        "backward_citations": ["EP2A1;EXT9", "JP3A", ""],
        "forward_citations": ["EP2A1", "", ""],
        "grant_date": ["", "2025-01-01", ""],
        "legal_status": ["active", "active", "expired"],
        "legal_status_as_of": ["2026-01-01", "2026-01-01", "2026-01-01"],
        "jurisdiction": ["US", "EP", "JP"],
        "legal_events_json": ["[]", "[]", "[]"],
        "claims_json": [claims, claims, claims],
        "kind_code": ["A1", "A1", "A"],
    })
    return PatentDataStore(frame)


def test_entity_portfolio_and_concentration_use_normalized_entities():
    store = _store()
    portfolio = asyncio.run(tool_registry.get_tool("analyze_entity_portfolio").run(
        store, entity_type="applicant", metric="publications", top_n=10,
    ))
    acme = next(item for item in portfolio.data if item["canonical_name"] == "ACME")
    assert acme["record_count"] == 2
    assert set(acme["aliases"]) == {"ACME", "Acme Inc."}

    concentration = asyncio.run(tool_registry.get_tool("analyze_concentration").run(
        store, dimension="applicant", count_mode="publications", bootstrap_samples=20,
    ))
    metrics = concentration.data[0]
    assert 0 <= metrics["hhi"] <= 1
    assert metrics["cr3"] == 1
    assert metrics["hhi_bootstrap_95pct"] is not None


def test_citation_and_family_geography_keep_semantics_separate():
    store = _store()
    citation = asyncio.run(tool_registry.get_tool("analyze_citation_network").run(
        store, top_n=10,
    ))
    assert citation.result_metadata["internal_edge_count"] == 2
    assert citation.result_metadata["external_edge_count"] == 1

    geography = asyncio.run(tool_registry.get_tool("analyze_family_geography").run(store))
    dimensions = {item["dimension"]: item["values"] for item in geography.data}
    assert dimensions["first_publication_office"]
    assert dimensions["family_publication_offices"]
    assert dimensions["current_active_rights_jurisdictions"] == []
    assert geography.result_metadata["current_status_authoritative"] is False


def test_search_strategy_audit_reports_returned_sets_not_claimed_recall():
    result = asyncio.run(tool_registry.get_tool("audit_search_strategy").run(
        _store(), strategies=[
            {"name": "narrow", "query": "solid battery"},
            {"name": "broad", "query": "battery electrolyte"},
        ], known_patent_numbers=["US1A1"], top_k=3,
    ))
    assert len(result.data) == 2
    assert result.data[0]["total_hits_exact"] is False
    assert "expert_recall_benchmark_available" in result.result_metadata
    assert result.result_metadata["expert_recall_benchmark_available"] is False


def test_legal_status_gate_requires_authoritative_source_capability():
    store = _store()
    tool = tool_registry.get_tool("analyze_legal_status")
    assert tool.availability(store)["available"] is False
    store._import_report = {
        "source_capabilities": {"authority": {"current_legal_status": True}},
    }
    store._adapter_name = "authority"
    assert tool.availability(store)["available"] is True
    result = asyncio.run(tool.run(store))
    assert result.data[0]["status"] == "active"


def test_monitor_persists_versioned_baseline_and_deduplicates(monkeypatch, tmp_path):
    monkeypatch.setenv("PATENTAGENT_MONITOR_DB", str(tmp_path / "monitor.db"))
    tool = tool_registry.get_tool("monitor_patent_changes")
    params = {
        "strategy_id": "battery", "strategy_version": 1,
        "query": "battery", "top_k": 10, "update_baseline": True,
    }
    store = _store()
    store._adapter_name = "wos"
    first = asyncio.run(tool.run(store, **params))
    second = asyncio.run(tool.run(store, **params))
    assert first.result_metadata["baseline_existed"] is False
    assert second.result_metadata["baseline_existed"] is True
    assert second.data == []
    assert first.result_metadata["run_id"] == second.result_metadata["run_id"]
    assert first.result_metadata["should_notify"] is False
    assert second.result_metadata["should_notify"] is False


def test_claim_elements_are_explicitly_draft_and_reversible():
    result = asyncio.run(tool_registry.get_tool("analyze_claim_elements").run(
        _store(), patent_numbers=["US1A1"], product_features=["electrolyte"],
    ))
    assert result.result_metadata["draft"] is True
    assert result.result_metadata["human_review_required"] is True
    assert result.data[0]["claims"][0]["elements"]
    assert result.data[0]["claims"][0]["source_text_sha256"]
    assert any("不构成侵权" in warning for warning in result.warnings)


def test_entity_metric_fails_when_source_field_is_absent():
    with pytest.raises(ValueError, match="forward_citations"):
        asyncio.run(tool_registry.get_tool("analyze_entity_portfolio").run(
            PatentDataStore(pd.DataFrame({
                "patent_number": ["P1"], "applicants": ["A"],
            })), metric="citations",
        ))


def test_reviewed_parent_mapping_deduplicates_records():
    result = asyncio.run(tool_registry.get_tool("analyze_entity_portfolio").run(
        _store(), group_by_parent=True, reviewed_parent_map=[
            {"canonical_name": "ACME", "parent_name": "Battery Group", "reviewed": True},
            {"canonical_name": "BETA", "parent_name": "Battery Group", "reviewed": True},
        ],
    ))
    parent = next(item for item in result.data if item["canonical_name"] == "Battery Group")
    assert parent["record_count"] == 2
    assert result.result_metadata["parent_grouping_applied"] is True


def test_monitor_and_claim_tools_enforce_launch_gates():
    monitor = tool_registry.get_tool("monitor_patent_changes")
    assert monitor.availability(_store())["available"] is False

    store = _store()
    store.get_all().loc[:, "legal_status"] = ""
    claim_tool = tool_registry.get_tool("analyze_claim_elements")
    assert claim_tool.availability(store)["available"] is False
    assert any("法律状态" in item for item in claim_tool.availability(store)["gate_failures"])


def test_search_audit_exposes_label_feedback_without_claiming_recall():
    result = asyncio.run(tool_registry.get_tool("audit_search_strategy").run(
        _store(), strategies=[{"query": "battery"}],
        review_labels=[
            {"patent_number": "US1A1", "relevant": True},
            {"patent_number": "JP3A", "relevant": True},
        ], random_audit_sample_size=1, top_k=2,
    ))
    assert result.result_metadata["reviewed_label_count"] == 2
    assert result.result_metadata["expert_recall_benchmark_available"] is False
    assert isinstance(result.result_metadata["labeled_relevant_not_returned"], list)
