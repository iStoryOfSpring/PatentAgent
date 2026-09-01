"""Every applicable analysis tool receives one normalized population scope."""

import asyncio

import pandas as pd
import pytest

from models.analysis_results import AnalysisResult
from patent_agent.domain import AnalysisScope
from storage.datastore import PatentDataStore
from tools.base import Tool
from tools import tool_registry


class _CountTool(Tool):
    name = "scope_contract_test"
    description = "test"
    allow_empty = True

    @property
    def evidence_record(self):
        return {
            "algorithm_id": "scope_contract", "version": "1",
            "evidence_type": "descriptive_statistic", "fields": {},
            "sources": [], "conditions": [], "prohibited_claims": [],
        }

    async def execute(self, storage: PatentDataStore) -> AnalysisResult:
        return AnalysisResult(
            result_type="scope_contract",
            summary=str(len(storage.get_all())),
            result_metadata={"analyzed_record_count": len(storage.get_all())},
        )


def _store():
    return PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2", "P3"],
        "title": ["solid battery", "liquid battery", "electric motor"],
        "abstract": ["electrolyte", "electrolyte", "drive"],
        "publication_date": ["2020-01-01", "2024-01-01", "2024-01-01"],
        "date": ["2020-01-01", "2024-01-01", "2024-01-01"],
        "applicants": ["Acme", "Beta", "Acme"],
        "inventors": ["Li", "Wang", "Li"],
        "ipc": ["H01M", "H01M", "H02K"],
        "jurisdiction": ["US", "CN", "US"],
        "family_id": ["F1", "F1", ""],
        "priority_numbers": ["US100", "US100", "US300"],
    }))


def test_analysis_scope_normalizes_lists_and_rejects_reverse_years():
    scope = AnalysisScope(ipc_prefixes=["H01", "H01"], applicant_names=["Beta"])
    assert scope.ipc_prefixes == ["H01"]
    with pytest.raises(ValueError, match="不能晚于"):
        AnalysisScope(year_start=2024, year_end=2020)


def test_scope_combines_filters_before_tool_execution():
    tool = _CountTool()
    result = asyncio.run(tool.run(_store(), scope={
        "year_start": 2024,
        "ipc_prefixes": ["H01M"],
        "applicant_names": ["Beta"],
        "jurisdictions": ["CN"],
    }))
    assert result.summary == "1"
    assert result.provenance.input_record_count == 3
    assert result.provenance.scope_record_count == 1
    assert result.provenance.analyzed_record_count == 1
    assert not result.provenance.sampled
    assert result.result_metadata["population_after_scope"] == 1


def test_scope_schema_is_exposed_and_unknown_params_fail():
    tool = _CountTool()
    assert "scope" in tool.to_schema(_store())["parameters"]["properties"]
    with pytest.raises(ValueError, match="未知参数"):
        asyncio.run(tool.run(_store(), silently_dropped=True))


def test_entity_id_scope_uses_automatic_reversible_mapping():
    store = _store()
    acme_entity_id = store.get_all().loc[0, "applicant_entity_ids"]

    scoped = store.filtered_by_scope({"applicant_entity_ids": [acme_entity_id]}).get_all()

    assert scoped["patent_number"].tolist() == ["P1", "P3"]
    assert scoped["applicants"].tolist() == ["Acme", "Acme"]


def test_all_applicable_registered_tools_expose_scope():
    for tool in tool_registry.list_tools():
        properties = tool.to_schema(_store())["parameters"]["properties"]
        if tool.name == "get_dataset_summary":
            assert "scope" not in properties
        else:
            assert "scope" in properties, tool.name


def test_scope_family_deduplication_is_deterministic_and_audited():
    result = asyncio.run(_CountTool().run(
        _store(), scope={"family_deduplication": "simple"},
    ))
    assert result.summary == "2"
    assert result.provenance.scope_record_count == 3
    assert result.provenance.family_deduplicated_record_count == 2
    assert result.result_metadata["population_after_family_deduplication"] == 2

    with pytest.raises(ValueError, match="至少 80%"):
        asyncio.run(_CountTool().run(
            _store(), scope={"family_deduplication": "inpadoc"},
        ))
