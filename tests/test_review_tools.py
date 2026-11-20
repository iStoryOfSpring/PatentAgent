import asyncio
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

import server
from patent_agent.application import DatasetImportService, DatasetRuntimeManager
from scripts.evaluate_gap_review import evaluate, ROOT
from storage.conversation_store import ConversationStore
from storage.datastore import PatentDataStore
from tools import tool_registry


def trend_store():
    # Published counts 1, 0, 2; application counts 1, 0, 1.
    return PatentDataStore(pd.DataFrame({
        "patent_number":["P1","P2","P3"], "publication_date":["2020-04-02","2022-01-02","2022-02-01"],
        "application_number":["US111", "US111","US222"], "filing_date":["2018-01-01","2018-01-01","2021-01-01"],
        "family_id":["", "", ""], "title":["alpha"]*3, "applicants":["A"]*3,
    }))


@pytest.mark.asyncio
async def test_trend_directions_evidence_missingness_and_cutoff():
    store = trend_store()
    tool = tool_registry.get_tool("audit_trend_robustness")
    result=await tool.run(store)
    assert result.years==[2020,2021,2022]
    publications, applications, families=result.data
    assert publications["annual_counts"]==[1,0,2] and not publications["sustained_growth"]
    assert applications["annual_counts"]==[1,0,1] and applications["direction"]=="flat"
    assert families["direction"]=="incomparable" and families["missing_ids"]==3
    assert all(text in result.summary for text in ("2020–2022", "公开文献数增长", "申请数持平", "专利族数（缺标识 3 件，仅统计标识已知记录）不可比", "方向存在分歧", "截止日期未知"))
    assert result.verdict=="divergent" and result.tail_coverage=="unknown"
    assert any(r.get("cross_year") and r["publication_numbers"]==["P1","P2"] for r in result.examples)
    assert {r["publication_numbers"][0] for r in result.examples if r.get("reason")=="missing_identity"}=={"P1","P2","P3"}
    one=await tool.run(store,date_basis="filing",scope={"year_start":2018,"year_end":2018})
    assert one.years==[2018] and one.data[0]["annual_counts"]==[2] and one.data[1]["annual_counts"]==[1]
    assert all(row["direction"]=="incomparable" for row in one.data)
    store._import_report["data_as_of"]="2022-02-01"
    from unittest.mock import patch
    with patch.object(store,"audit",return_value={**store.audit(),"data_as_of":"2022-02-01"}):
        partial=await tool.run(store,example_limit=1)
    assert partial.tail_coverage=="partial" and partial.examples_truncated


@pytest.mark.asyncio
async def test_gap_labels_snippets_class_leads_and_truncation():
    metrics=await evaluate()
    assert [(m["recovered"],m["false_positives"],m["additional_reviews"]) for m in metrics]==[(1,1,2),(4,1,3),(5,3,3)]
    store=DatasetImportService().load(str(ROOT/"source"),"google_patents_jsonl")
    tool=tool_registry.get_tool("search_gap_counterevidence")
    params=dict(technology="near infrared",effect="sorting",ipc_prefixes=["B07C"])
    result=await tool.run(store,**params)
    df=store.get_all().set_index("patent_number")
    assert all(text in result.summary for text in ("原词双轴命中 2 件", "扩展新增 3 件", "分类线索再新增 3 件", "3 件仅有单侧文本与分类支持"))
    assert result.missing_abstract==1 and result.unique_hits==8
    assert any(r["level"]=="single_axis_lead" and r["classifications"] for r in result.data[2]["candidates"])
    assert "DEMO-08-A1" not in {r["publication"] for stage in result.data for r in stage["candidates"]}
    for stage in result.data:
        candidates=stage["candidates"]
        assert len({r["publication"] for r in candidates})==len(candidates)
        assert stage["hits"]==stage["overlap"]+stage["new"]
        for candidate in candidates:
            for hit in candidate["technology_hits"]+candidate["effect_hits"]:
                original=df.loc[candidate["publication"],hit["field"]]
                assert original[hit["start"]:hit["end"]]==hit["snippet"]
    limited=await tool.run(store,**params,example_limit=1)
    assert limited.data[1]["truncated"] and limited.data[1]["candidates"][0]["new"]
    none=await tool.run(store,technology="nonexistent",effect="unheard")
    assert not none.has_expansions and none.unique_hits==0
    with pytest.raises(ValueError):
        await tool.run(store,technology="x"*101,effect="sorting")


@pytest.mark.asyncio
async def test_review_http_binds_scope_and_refuses_wrong_session_version_pair_hash(tmp_path):
    app=server.create_app()
    value=app.state.container
    repo=ConversationStore(tmp_path/"test.sqlite")
    await repo.initialize()
    value.conversation_store=repo
    store=DatasetImportService().load(str(ROOT/"source"),"google_patents_jsonl")
    value.store=store
    value.dataset_runtime=DatasetRuntimeManager(repo,DatasetImportService())
    value.dataset_runtime.register(store)
    snapshot=store.snapshot()
    await repo.upsert_dataset_snapshot(snapshot.model_dump())
    for ident in ("s","other"):
        await repo.ensure_session(ident,snapshot.content_hash,dataset_version_id=snapshot.version_id)
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver") as client:
        async def run(name,params,session="s",**source):
            return await client.post("/api/tools/"+name,json={"params":params,"session_id":session,**source})
        trend=await run("analyze_patent_trend",{"chart_type":"yearly","date_basis":"filing","scope":{"year_start":2018}})
        assert trend.status_code==200,trend.text
        meta=trend.json()["result_metadata"]
        proof={"source_execution_id":meta["execution_id"],"source_digest":meta["review_digest"]}
        # Older evidence snapshots did not store a review digest. Restore from the signed inputs.
        import aiosqlite, json
        async with aiosqlite.connect(repo.db_path) as db:
            row=(await db.execute_fetchall("SELECT result_json FROM evidence_snapshots WHERE execution_id=?", (proof["source_execution_id"],)))[0]
            old=json.loads(row[0])
            del old["result_metadata"]["review_digest"]
            await db.execute("UPDATE evidence_snapshots SET result_json=? WHERE execution_id=?", (json.dumps(old),proof["source_execution_id"]))
            await db.commit()
        history=await repo.get_session_detail("s")
        assert history["tool_executions"][0]["result"]["result_metadata"]["review_digest"]==proof["source_digest"]
        reviewed=await run("audit_trend_robustness",{},**proof)
        assert reviewed.status_code==200,reviewed.text
        result=reviewed.json()
        assert result["date_basis"]=="filing" and result["provenance"]["scope"]=={"year_start":2018}
        restored=await repo.get_execution_evidence(result["result_metadata"]["execution_id"])
        assert restored["result"]["result_metadata"]["review_source"]["sha256"]==proof["source_digest"]
        assert (await run("audit_trend_robustness",{},session="other",**proof)).status_code==409
        assert (await run("audit_trend_robustness",{"date_basis":"grant"},**proof)).status_code==409
        assert (await run("audit_trend_robustness",{},**{**proof,"source_digest":"0"*64})).status_code==409
        matrix=(await run("analyze_tech_matrix",{})).json()["result_metadata"]
        mp={"source_execution_id":matrix["execution_id"],"source_digest":matrix["review_digest"]}
        assert (await run("search_gap_counterevidence",{"technology":"unknown","effect":"unknown"},**mp)).status_code==409
        valid=await run("search_gap_counterevidence",{"technology":"textile","effect":"separator"},**mp)
        assert valid.status_code==200 and valid.json()["result_metadata"]["review_source"]["matrix_observed"]==0
        import aiosqlite
        async with aiosqlite.connect(repo.db_path) as db:
            await db.execute("UPDATE evidence_snapshots SET stale=1 WHERE execution_id=?", (proof["source_execution_id"],))
            await db.commit()
        assert (await run("audit_trend_robustness",{},**proof)).status_code==409
        store.get_all().loc[0,"title"]="changed"
        assert (await run("search_gap_counterevidence",{"technology":"textile","effect":"separator"},**mp)).status_code==409
