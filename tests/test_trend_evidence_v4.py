import asyncio
import pandas as pd
import pytest
from httpx import AsyncClient,ASGITransport
from tools import tool_registry
from storage.datastore import PatentDataStore
from storage.conversation_store import ConversationStore
from patent_agent.application import DatasetImportService,DatasetRuntimeManager
from engine.trend import select_trend_population
import server

def population():
    frame=pd.DataFrame({"patent_number":["US1A1","US1B2","EP2A1","CN3A1"],"title":["battery"]*4,"abstract":["cell"]*4,"publication_date":["2020-01-01","2024-01-01","2021-02-01","2022-01-01"],"filing_date":["2018-03-01","2018-03-01","2019-04-01","2017-01-01"],"priority_date":["2017-01-01","2017-01-01","2017-02-01", ""],"grant_date":["","2024-01-01","", ""],"application_number":["US11111111","US11111111","EP222A", ""],"family_id":["F1","F1","F1", ""],"applicants":["Acme"]*4})
    value=PatentDataStore(frame);value._adapter_name="synthetic";value._dataset_id_override="dataset_synthetic";value._version_id_override="version_synthetic";return value


def test_trend_date_unit_and_year_scope_match_selected_axis():
    value=population();tool=tool_registry.get_tool("analyze_patent_trend")
    default=asyncio.run(tool.run(value,chart_type="yearly"))
    assert sum(row["count"] for row in default.data)==4
    filing=asyncio.run(tool.run(value,chart_type="yearly",date_basis="filing",count_unit="applications",scope={"year_start":2018,"year_end":2018}))
    assert filing.data==[{"year":2018,"count":1}]
    assert filing.result_metadata["missing_identity_records"]==1
    family=asyncio.run(tool.run(value,chart_type="yearly",date_basis="priority",count_unit="families"))
    assert family.data==[{"year":2017,"count":1}]
    grant=asyncio.run(tool.run(value,chart_type="yearly",date_basis="grant"))
    assert grant.data==[{"year":2024,"count":1}] and grant.result_metadata["missing_date_records"]==3
    assert "not" not in str(default.data)


def test_persisted_evidence_resolves_only_counted_bin_and_rejects_stale(tmp_path):
    async def scenario():
        app=server.create_app();container=app.state.container;repo=ConversationStore(tmp_path/"db.sqlite");await repo.initialize();container.conversation_store=repo
        value=population();container.store=value;container.dataset_runtime=DatasetRuntimeManager(repo,DatasetImportService());container.dataset_runtime.register(value)
        await repo.upsert_dataset_snapshot(value.snapshot().model_dump())
        params={"chart_type":"yearly","date_basis":"filing","count_unit":"applications"}
        result=await tool_registry.get_tool("analyze_patent_trend").run(value,**params)
        await repo.ensure_session("s",value.dataset_fingerprint(),dataset_version_id=value.snapshot().version_id)
        turn=await repo.start_turn("s","trend",dataset_version_id=value.snapshot().version_id)
        await repo.record_execution("s",turn,"execution1","analyze_patent_trend",params,"completed",result.model_dump(),provenance=result.provenance.model_dump())
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver") as client:
            response=await client.get("/api/executions/execution1/records?bin=2018&limit=1")
            assert response.status_code==200,response.text
            page=response.json();assert page["total_units"]==1
            assert page["groups"][0]["publication_numbers"]==["US1A1","US1B2"]
            assert all(m["dataset_version_id"]=="version_synthetic" for m in page["groups"][0]["members"])
            assert (await client.get("/api/executions/execution1/records?bin=2024")).status_code==422
            assert (await client.get("/api/executions/execution1/records?bin=2018&limit=101")).status_code==422
            value.get_all().loc[0,"title"]="changed after execution"
            assert (await client.get("/api/executions/execution1/records?bin=2018")).status_code==409
    asyncio.run(scenario())


def test_local_boundary_uses_peer_and_host_not_forwarded_headers():
    async def scenario():
        app=server.create_app()
        async with AsyncClient(transport=ASGITransport(app=app,client=("198.51.100.2",123)),base_url="http://127.0.0.1") as client:
            assert (await client.get("/api/sources",headers={"X-Forwarded-For":"127.0.0.1"})).status_code==403
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://attacker.example") as client:
            assert (await client.get("/api/sources")).status_code==403
    asyncio.run(scenario())


def test_full_epo_trend_keeps_unknown_source_cutoff_separate_from_observation():
    from tests.test_acquisitions import XML
    from patent_agent.application.acquisitions import parse_ops_xml
    from engine.adapters.base import PatentAdapter
    _,records=parse_ops_xml(XML)
    value=PatentDataStore(PatentAdapter._patents_to_dataframe(records));value._adapter_name="canonical_jsonl"
    result=asyncio.run(tool_registry.get_tool("analyze_patent_trend").run(value,chart_type="yearly"))
    assert result.data_as_of==""
    coverage=result.result_metadata["time_coverage"]
    assert coverage["data_as_of"]=="" and coverage["reference_basis"]=="observed_publication_max"
    assert coverage["coverage_reference_date"]=="2020-01-01"
    assert any("截止日期未知" in warning for warning in result.warnings)


@pytest.mark.parametrize("tool_name,old_version,new_version",[("analyze_patent_trend","3.0","3.0.1"),("analyze_lifecycle","2.0","2.0.1")])
def test_cutoff_patch_registry_invalidates_new_reuse_without_rewriting_history(tmp_path,tool_name,old_version,new_version):
    from storage.conversation_store import execution_cache_key
    from tools.evidence import load_evidence_registry
    async def scenario():
        repo=ConversationStore(tmp_path/"cache.sqlite");await repo.initialize()
        value=population();fingerprint=value.dataset_fingerprint();params={}
        await repo.create_session("cache",fingerprint,"cache-session")
        turn=await repo.start_turn("cache-session","old trend")
        old_result={"result_type":"yearly_trend","summary":"old saved result","result_metadata":{"algorithm_version":old_version,"time_coverage":{"data_as_of":"2024-01-01"}}}
        old_key=await repo.record_execution("cache-session",turn,"old-execution",tool_name,params,"completed",old_result,algorithm_version=old_version,dataset_fingerprint=fingerprint)
        tool=tool_registry.get_tool(tool_name)
        assert tool.evidence_record["version"]==tool.definition.version==new_version
        assert load_evidence_registry()["registry_version"]=="2026.10.16"
        new_key=execution_cache_key(fingerprint,tool_name,params,tool.evidence_record["version"])
        assert old_key!=new_key and await repo.find_reusable("cache-session",new_key) is None
        assert (await repo.find_reusable("cache-session",old_key))["id"]=="old-execution"
        assert (await repo.get_execution_evidence("old-execution"))["result"]==old_result
    asyncio.run(scenario())


@pytest.mark.parametrize("tool_name",["analyze_patent_trend","analyze_lifecycle","get_dataset_summary"])
@pytest.mark.parametrize("raw_cutoff,expected",[("",""),("invalid",""),("2026-99-99",""),("2026-01-02","2026-01-02"),("2026-01-02T12:30:00Z","2026-01-02")])
def test_all_tool_run_cutoffs_are_consistent_and_preserve_raw_source(tool_name,raw_cutoff,expected):
    value=population()
    value.get_all()["month"]=pd.to_datetime(value.get_all()["publication_date"]).dt.month
    value.get_all()["year"]=pd.to_datetime(value.get_all()["publication_date"]).dt.year
    value.get_all()["data_as_of"]=raw_cutoff
    result=asyncio.run(tool_registry.get_tool(tool_name).run(value))
    assert result.data_as_of==expected
    assert result.result_metadata["data_as_of"]==expected
    if "time_coverage" in result.result_metadata:
        assert result.result_metadata["time_coverage"]["data_as_of"]==expected
    assert value.get_all()["data_as_of"].tolist()==[raw_cutoff]*4
    assert value.audit()["data_as_of"]==raw_cutoff
