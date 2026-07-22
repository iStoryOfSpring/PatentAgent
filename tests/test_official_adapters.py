"""Official-format adapters, merge policy and import capability reporting."""

from pathlib import Path
import asyncio
import shutil

import pytest
from httpx import ASGITransport, AsyncClient

from engine.adapters.common import normalized_application_number, normalized_document_number
from engine.adapters.google_patents import GooglePatentsExportAdapter
from engine.adapters.google_patents import MAX_LOCALIZED_TEXT_CHARS, _localized
from engine.adapters.importer import PatentDatasetImporter
from engine.adapters.uspto import USPTOFileWrapperJsonAdapter, USPTOGrantXmlAdapter
from patent_agent.application import DatasetImportService
import server


FIXTURE = Path(__file__).parent / "fixtures" / "official_formats"
WOS_FIXTURE = Path(__file__).parent / "fixtures" / "wos_golden" / "synthetic_wos.txt"


def test_number_normalization_preserves_raw_semantics_but_joins_uspto_forms():
    assert normalized_document_number("US-11,325,075-B2") == "US11325075B2"
    assert normalized_application_number("US-201816629734-A") == "US16629734"
    assert normalized_application_number("US16/629,734") == "US16629734"


def test_google_public_data_export_maps_multilingual_and_capability_fields():
    records = GooglePatentsExportAdapter().parse_file(str(FIXTURE / "google_patents_sample.jsonl"))
    assert len(records) == 3
    carbon = next(item for item in records if item.normalized_patent_number == "US11325075B2")
    assert carbon.title == "Carbon capture membrane"
    assert {item.language for item in carbon.localized_titles} == {"en", "zh"}
    assert carbon.family_id == "64433682"
    assert carbon.ipc_codes == ["B01D71/68"]
    assert carbon.backward_citations == ["US-7650331-B1"]
    assert carbon.provenance.source.adapter == "google_patents"


def test_uspto_grant_and_file_wrapper_map_claims_and_dated_events():
    grant = USPTOGrantXmlAdapter().parse_file(str(FIXTURE / "uspto_grant_sample.xml"))[0]
    wrapper = USPTOFileWrapperJsonAdapter().parse_file(
        str(FIXTURE / "uspto_file_wrapper_sample.json")
    )[0]
    assert grant.normalized_patent_number == "US11325075B2"
    assert len(grant.claims) == 2
    assert grant.claims[0].is_independent
    assert grant.claims[1].depends_on == [1]
    assert wrapper.legal_status == "Patented Case"
    assert wrapper.legal_status_as_of == "2022-05-10"
    assert [item.event_code for item in wrapper.legal_events] == ["PGM", "NOA"]


def test_registry_import_merges_exact_application_and_keeps_field_provenance():
    records, report, manifest = PatentDatasetImporter().import_directory(str(FIXTURE))
    assert manifest is not None
    assert report.records_parsed == 5
    assert report.records_imported == 3
    assert report.duplicates_merged == 2
    carbon = next(item for item in records if item.normalized_patent_number == "US11325075B2")
    assert len(carbon.claims) == 2
    assert len(carbon.legal_events) == 2
    assert carbon.family_id == "64433682"
    assert {item.source for item in carbon.field_provenance} >= {
        "google_patents", "uspto_file_wrapper",
    }
    assert set(report.source_capabilities) == {
        "google_patents", "uspto_file_wrapper", "uspto_grant",
    }
    assert carbon.data_as_of == "2026-07-22"
    assert carbon.provenance.source.license_note
    assert {item.method for item in report.file_detections} == {"manifest"}
    assert all(item.matched for item in report.file_detections)


def test_auto_detection_recognizes_every_supported_official_fixture_without_manifest(tmp_path):
    for name in (
        "google_patents_sample.jsonl",
        "uspto_grant_sample.xml",
        "uspto_file_wrapper_sample.json",
    ):
        shutil.copy2(FIXTURE / name, tmp_path / name)

    records, report, manifest = PatentDatasetImporter().import_directory(str(tmp_path), "auto")

    assert manifest is None
    assert report.records_parsed == 5
    assert report.records_imported == 3
    assert set(report.source_formats) == {
        "google_patents_jsonl", "uspto_grant_xml", "uspto_file_wrapper_json",
    }
    assert len(report.file_detections) == 3
    assert {item.method for item in report.file_detections} == {"content_signature"}
    assert all(item.matched for item in report.file_detections)
    assert not report.issues


def test_auto_detection_recognizes_wos_tagged_text_without_manifest(tmp_path):
    shutil.copy2(WOS_FIXTURE, tmp_path / "export.txt")

    records, report, manifest = PatentDatasetImporter().import_directory(str(tmp_path), "auto")

    assert manifest is None
    assert len(records) == 300
    assert report.source_formats == ["wos_dii"]
    assert report.file_detections[0].method == "content_signature"
    assert report.file_detections[0].matched


def test_auto_detection_refuses_to_guess_unknown_content_and_manual_format_is_fallback(tmp_path):
    unknown = tmp_path / "unknown.json"
    unknown.write_text('{"unrelated": true}', encoding="utf-8")

    records, report, _ = PatentDatasetImporter().import_directory(str(tmp_path), "auto")
    assert records == []
    assert report.file_detections[0].method == "unknown"
    assert not report.file_detections[0].matched
    assert report.issues[0].code == "unsupported_format"

    # Explicit selection bypasses signature matching, then fails at the parser
    # with an honest format-specific error rather than being silently guessed.
    _, forced, _ = PatentDatasetImporter().import_directory(
        str(tmp_path), "uspto_file_wrapper_json",
    )
    assert forced.file_detections[0].method == "user_selected"
    assert forced.file_detections[0].matched


def test_dataset_view_exposes_import_report_and_full_claim_payload():
    store = DatasetImportService().load(str(FIXTURE), "auto")
    audit = store.audit()
    assert audit["import_report"]["records_imported"] == 3
    assert audit["source_capabilities"]["google_patents"]["multilingual_text"]
    assert "正式 FTO 意见" in audit["unsupported_conclusions"]
    assert "实时有效性判断" in audit["unsupported_conclusions"]
    assert store.field_coverage("claims_json") == pytest.approx(1.0, abs=0.0001)
    claim_json = store.get_all().loc[
        store.get_all()["normalized_patent_number"].eq("US11325075B2"), "claims_json"
    ].iloc[0]
    assert "polymeric" in claim_json


def test_manifest_rejects_paths_outside_dataset(tmp_path):
    (tmp_path / "patentagent-import.json").write_text(
        '{"files":[{"path":"../escape.jsonl","source_format":"google_patents_jsonl"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="目录外路径"):
        PatentDatasetImporter().import_directory(str(tmp_path))


def test_malformed_inputs_and_oversized_text_are_bounded(tmp_path):
    malformed_json = tmp_path / "broken.jsonl"
    malformed_json.write_text('{"publication_number":', encoding="utf-8")
    with pytest.raises(ValueError):
        GooglePatentsExportAdapter().parse_file(str(malformed_json))

    malformed_xml = tmp_path / "broken.xml"
    malformed_xml.write_text("<us-patent-grant><broken>", encoding="utf-8")
    with pytest.raises(Exception):
        USPTOGrantXmlAdapter().parse_file(str(malformed_xml))

    localized = _localized({"language": "en", "text": "x" * (MAX_LOCALIZED_TEXT_CHARS + 1)})
    assert len(localized[0].text) == MAX_LOCALIZED_TEXT_CHARS
    assert localized[0].truncated


def test_data_load_api_accepts_source_format_and_returns_import_report(tmp_path, monkeypatch):
    monkeypatch.setenv("PATENT_DATA_ROOT", str(FIXTURE.parent))
    monkeypatch.setenv("MCP_INPUT_DIR", str(FIXTURE))
    monkeypatch.setenv("PATENTAGENT_SESSION_DB", str(tmp_path / "api.db"))
    application = server.create_app()

    async def scenario():
        async with application.router.lifespan_context(application):
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://test",
            ) as client:
                loaded = await client.post("/api/data/load", json={
                    "input_dir": str(FIXTURE), "source_format": "auto",
                })
                status = await client.get("/api/search/status")
                return loaded, status

    response, status_response = asyncio.run(scenario())
    assert response.status_code == 200
    payload = response.json()
    assert payload["import_report"]["records_imported"] == 3
    assert payload["source_capabilities"]["uspto_grant"]["claims"]
    assert status_response.status_code == 200
    assert status_response.json()["model_id"].endswith("MiniLM-L12-v2")
    assert isinstance(status_response.json()["dependency_installed"], bool)
