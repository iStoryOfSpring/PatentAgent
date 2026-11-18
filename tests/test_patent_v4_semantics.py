"""Regression evidence for document/application separation and unknown claim structure."""
import asyncio
import json
from pathlib import Path
import pytest
from models.patent import PatentRecord, LocalizedText, DataSource, RecordProvenance
from engine.adapters.base import PatentAdapter
from engine.adapters.common import merge_patent_records
from engine.adapters.google_patents import GooglePatentsExportAdapter
from engine.adapters.canonical import CanonicalJsonlAdapter
from engine.adapters.importer import PatentDatasetImporter
from patent_agent.application.services import DatasetImportService
from patent_agent.application.dataset_runtime import DatasetRuntimeManager
from storage.conversation_store import ConversationStore
from storage.datastore import PatentDataStore
from tools import tool_registry

def record(number="US100A1", **kw):
    return PatentRecord(patent_number=number, normalized_patent_number=number, title="battery", abstract="cell", application_number="US12345678", publication_date="2020-01-01", **kw)

def store(records):
    value=PatentDataStore(PatentAdapter._patents_to_dataframe(records));value._adapter_name="canonical_jsonl";return value

def test_publication_versions_never_collapse_on_application():
    merged,duplicates,_=merge_patent_records([record(),record("US100B2"),record()])
    assert {r.patent_number for r in merged}=={"US100A1","US100B2"}
    assert duplicates==1

def test_google_claim_blob_is_raw_unknown_and_roundtrips_in_details(tmp_path):
    path=tmp_path/"google.jsonl"
    path.write_text(json.dumps({"publication_number":"US100A1","application_number":"US12345678","title_localized":[{"language":"en","text":"battery"}],"claims_localized":[{"language":"zh","text":"1. 一种电池。2. 根据权利要求1所述的电池。"}]}))
    imported=DatasetImportService().load(str(tmp_path))
    details=asyncio.run(tool_registry.get_tool("read_patent_details").run(imported,patent_numbers=["US100A1"]))
    patent=details.patents[0]
    assert patent["claims"]==[]
    assert patent["claims_structure_status"]=="unknown"
    assert patent["raw_claims"][0]["text"].startswith("1. 一种电池")
    assert not tool_registry.get_tool("analyze_claim_elements").availability(imported)["available"]

def test_canonical_replay_rejects_old_schema_and_identity_mismatch(tmp_path):
    path=tmp_path/"records.jsonl"
    payload=record().model_dump()
    payload["schema_version"]=3
    path.write_text(json.dumps(payload))
    adapter=CanonicalJsonlAdapter()
    assert adapter.parse_file(str(path))==[]
    payload["schema_version"]=4;payload["normalized_patent_number"]="US999B2"
    path.write_text(json.dumps(payload))
    assert adapter.parse_file(str(path))==[]
    assert adapter.parse_diagnostics["failed"]==1

def test_application_only_evidence_kept_without_fabricated_publication(tmp_path):
    wrapper={"applicationMetaData":{"applicationNumberText":"16/123456","patentNumber":"1234567","inventionTitle":"Application title","applicationStatusDescriptionText":"Pending","applicationStatusDate":"2025-01-01"},"eventDataBag":[{"eventCode":"X","eventDate":"2024-01-01"}]}
    (tmp_path/"wrapper.json").write_text(json.dumps(wrapper))
    records,report,_=PatentDatasetImporter().import_directory(str(tmp_path))
    assert records==[]
    assert report.records_imported==0
    assert report.application_evidence[0]["patent_number"]==""
    assert report.application_evidence[0]["legal_events"][0]["event_code"]=="X"
    first=DatasetImportService().load(str(tmp_path)).dataset_fingerprint()
    wrapper["eventDataBag"][0]["eventCode"]="Y"
    (tmp_path/"wrapper.json").write_text(json.dumps(wrapper))
    assert DatasetImportService().load(str(tmp_path)).dataset_fingerprint()!=first

def test_symlink_enumeration_and_manifest_cannot_escape(tmp_path):
    inside=tmp_path/"inside";inside.mkdir();outside=tmp_path/"outside.json";outside.write_text('{}')
    (inside/"escape.json").symlink_to(outside)
    with pytest.raises(ValueError,match="越界"):PatentDatasetImporter().import_directory(str(inside))
    (inside/"escape.json").unlink();(inside/"patentagent-import.json").symlink_to(outside)
    with pytest.raises(ValueError,match="越界"):PatentDatasetImporter().import_directory(str(inside))

def test_fingerprint_recursively_ignores_observation_time_and_list_order():
    a=record(raw_claims=[LocalizedText(language="en",text="one")],applicants=["Beta","Acme"],provenance=RecordProvenance(source=DataSource(adapter="epo_ops"),imported_at="2025-01-01"))
    b=a.model_copy(deep=True);b.provenance.imported_at="2026-01-01";b.imported_at="2026";b.applicants.reverse()
    first,second=store([a]),store([b])
    first._import_report={"application_evidence":[a.model_dump()]};second._import_report={"application_evidence":[b.model_dump()]}
    assert first.dataset_fingerprint()==second.dataset_fingerprint()
    b.raw_claims[0].text="changed"
    assert first.dataset_fingerprint()!=store([b]).dataset_fingerprint()

def test_runtime_reload_verifies_hash_and_preserves_completeness(tmp_path):
    async def scenario():
        source=tmp_path/"source";source.mkdir();path=source/"records.jsonl";path.write_text(record().model_dump_json()+"\n")
        importer=DatasetImportService();loaded=importer.load(str(source));repo=ConversationStore(tmp_path/"db.sqlite");await repo.initialize()
        snapshot={**loaded.snapshot().model_dump(),"storage_path":str(source),"import_report":{**loaded._import_report,"matched_set_complete":False,"acquisition":{"pages":1}}}
        await repo.upsert_dataset_snapshot(snapshot)
        restored=await DatasetRuntimeManager(repo,importer).get(snapshot["version_id"])
        assert restored._import_report["matched_set_complete"] is False
        assert restored._import_report["acquisition"]["pages"]==1
        path.write_text(record("US100B2").model_dump_json()+"\n")
        with pytest.raises(ValueError,match="requires_reimport"):await DatasetRuntimeManager(repo,importer).get(snapshot["version_id"])
    asyncio.run(scenario())


def test_real_legal_as_of_changes_identity_while_observation_does_not():
    first=record(legal_status="active",legal_status_as_of="2025-01-01")
    later=first.model_copy(update={"legal_status_as_of":"2026-01-01"})
    assert store([first]).dataset_fingerprint()!=store([later]).dataset_fingerprint()


def test_newer_legal_assertion_wins_with_both_sources_and_dates_retained():
    old=record(legal_status="active",legal_status_as_of="2020-01-01",jurisdiction="US",provenance=RecordProvenance(source=DataSource(adapter="uspto_grant")))
    new=record(legal_status="expired",legal_status_as_of="2026-01-01",jurisdiction="US",provenance=RecordProvenance(source=DataSource(adapter="google_patents")))
    merged,_,_=merge_patent_records([old,new])
    assert merged[0].legal_status=="expired" and merged[0].legal_status_as_of=="2026-01-01"
    assertions={(item.source,item.as_of,item.value) for item in merged[0].field_provenance if item.field_name=="legal_status"}
    assert ("uspto_grant","2020-01-01","active") in assertions
    assert ("google_patents","2026-01-01","expired") in assertions
    assert merged[0].field_conflicts[-1].rejected_value=="active"


def test_empty_json_fields_do_not_report_record_coverage():
    value=store([record()])
    assert value.field_coverage("legal_events")==0
    assert value.field_coverage("multilingual_text")==0


def test_application_only_upload_persists_replayable_version_with_zero_publications(tmp_path,monkeypatch):
    import server
    from httpx import AsyncClient,ASGITransport
    monkeypatch.setenv("PATENT_DATA_ROOT",str(tmp_path/"data"));monkeypatch.setenv("MCP_INPUT_DIR",str(tmp_path/"data"));monkeypatch.setenv("PATENTAGENT_SESSION_DB",str(tmp_path/"sessions.sqlite"))
    wrapper={"applicationMetaData":{"applicationNumberText":"16/123456","inventionTitle":"Application title"},"eventDataBag":[{"eventCode":"UNMATCHED","eventDate":"2024-01-01"}]}
    async def scenario():
        app=server.create_app()
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver") as client:
                uploaded=await client.post("/api/datasets/imports",data={"name":"application evidence","source_format":"uspto_file_wrapper_json"},files={"files":("wrapper.json",json.dumps(wrapper).encode(),"application/json")})
                assert uploaded.status_code==202,uploaded.text
                status=(await client.get("/api/imports/"+uploaded.json()["import_id"])).json()["import"]
                assert status["status"]=="completed",status
                summary=await client.get("/api/data/summary")
                assert summary.status_code==200 and summary.json()["total_patents"]==0
                assert summary.json()["application_evidence_count"]==1
                assert summary.json()["import_report"]["application_evidence_count"]==1
                assert all(not item["availability"]["available"] for item in (await client.get("/api/tools")).json()["tools"] if item["name"] != "get_dataset_summary")
                runtime=app.state.container.dataset_runtime;runtime._stores.clear()
                reloaded=await runtime.get(status["dataset_version_id"])
                assert reloaded.snapshot().record_count==0
                assert reloaded._import_report["application_evidence"][0]["legal_events"][0]["event_code"]=="UNMATCHED"
                assert reloaded._import_report["application_evidence_count"]==1
                failed=await client.post("/api/datasets/imports",data={"name":"empty","source_format":"uspto_file_wrapper_json"},files={"files":("empty.json",b"[]","application/json")})
                empty_status=(await client.get("/api/imports/"+failed.json()["import_id"])).json()["import"]
                assert empty_status["status"]=="failed"
    asyncio.run(scenario())


def test_explicit_bilingual_expansion_and_independent_cpc_filter_are_auditable():
    a=record(cpc_codes=["H01M10/052"])
    b=record("US200A1",cpc_codes=["B64U10/00"])
    value=store([a,b]);tool=tool_registry.get_tool("search_patents")
    plain=asyncio.run(tool.run(value,query="电池"))
    assert plain.result_metadata["original_query"]==plain.result_metadata["expanded_query"]=="电池"
    assert plain.result_metadata["expansion_terms"]==[]
    expanded=asyncio.run(tool.run(value,query="电池",synonym_expansion=True,cpc_filter=["H01M"]))
    assert expanded.result_metadata["expansion_terms"]==["battery"]
    assert expanded.result_metadata["synonym_dictionary_version"]=="zh-en-v1"
    assert expanded.result_metadata["retrieval_mode_used"]=="lexical"
    assert [p["patent_number"] for p in expanded.patents]==["US100A1"]
