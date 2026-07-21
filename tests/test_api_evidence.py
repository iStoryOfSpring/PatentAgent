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
    monkeypatch.setattr(server.app.state.container, "store", _store())
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
    monkeypatch.setattr(server.app.state.container, "store", store)
    payload = server.data_summary()
    assert payload["external_forward_citation_coverage"] == 0.0
    assert payload["internal_citation_network"]["scope"] == "internal_corpus_only"
    assert payload["batch_completeness"]["parse_failure_count"] == 0
    assert isinstance(payload["datasets"], list)


def test_report_export_remains_available_after_ui_removal():
    import asyncio
    response = asyncio.run(server.report_export(server.ExportRequest(
        title="迁移验证报告",
        messages=[
            {"role": "user", "content": "分析问题"},
            {"role": "assistant", "content": "分析结论"},
        ],
    )))

    body = response.body.decode("utf-8")
    assert response.media_type == "text/html"
    assert "<title>迁移验证报告</title>" in body
    assert "分析问题" in body
    assert "分析结论" in body


def test_report_export_escapes_untrusted_title_and_messages():
    import asyncio
    response = asyncio.run(server.report_export(server.ExportRequest(
        title='<script>alert("title")</script>',
        messages=[{"role": '<img src=x onerror=alert(1)>',
                   "content": '<script>alert("message")</script>'}],
    )))

    body = response.body.decode("utf-8")
    assert "<script>" not in body
    assert "<img src=x" not in body
    assert "&lt;script&gt;" in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body
