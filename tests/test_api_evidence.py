import pandas as pd

import server
from storage.datastore import PatentDataStore
from tools import tool_registry


def _store():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["EP1"], "title": ["battery"],
        "abstract": ["solid electrolyte"], "applicants": ["A"],
        "inventors": ["I"], "ipc": ["H01M"],
        "publication_date": ["2020-01-01"], "date": ["2020-01-01"],
    }))
    store._adapter_name = "test"
    return store


def test_tools_api_exposes_single_source_algorithm_registry(monkeypatch):
    monkeypatch.setattr(server, "_store", _store())
    payload = server.list_tools()
    assert len(payload["tools"]) == len(tool_registry.get_all_names()) == 16
    for item in payload["tools"]:
        assert item["algorithm"]["algorithm_id"]
        assert item["algorithm"]["version"]
        assert "prohibited_claims" in item["algorithm"]
        assert "field_thresholds" in item["availability"]


def test_data_summary_separates_citation_scopes_and_batch_status(monkeypatch):
    store = _store()
    store._load_diagnostics = {
        "raw_records": 1, "parsed_unique_records": 1,
        "parse_failure_count": 0, "parse_rate": 1.0,
    }
    monkeypatch.setattr(server, "_store", store)
    payload = server.data_summary()
    assert payload["external_forward_citation_coverage"] == 0.0
    assert payload["internal_citation_network"]["scope"] == "internal_corpus_only"
    assert payload["batch_completeness"]["parse_failure_count"] == 0
    assert isinstance(payload["datasets"], list)
