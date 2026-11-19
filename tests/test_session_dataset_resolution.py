"""Session reads/execution never inherit another session's default dataset."""
import asyncio
from pathlib import Path
import httpx
import pytest
from models.patent import PatentRecord
from patent_agent.application import DatasetImportService,DatasetRuntimeManager
from storage.conversation_store import ConversationStore
import server

async def setup(tmp_path,monkeypatch):
    monkeypatch.setenv("PATENT_DATA_ROOT",str(tmp_path));monkeypatch.setenv("PATENTAGENT_SESSION_DB",str(tmp_path/"sessions.db"))
    app=server.create_app();container=app.state.container;repo=ConversationStore(tmp_path/"sessions.db");await repo.initialize();container.conversation_store=repo
    importer=DatasetImportService();container.dataset_service=importer;container.dataset_runtime=DatasetRuntimeManager(repo,importer,capacity=2)
    stores=[]
    for name,count in (("A",1),("B",2)):
        source=tmp_path/name;source.mkdir()
        records=[PatentRecord(patent_number=f"US{name}{i}A1",normalized_patent_number=f"US{name}{i}A1",title=name,abstract="cell",publication_date="2020-01-01") for i in range(count)]
        (source/"records.jsonl").write_text("".join(record.model_dump_json()+"\n" for record in records))
        value=importer.load(str(source));stores.append(value)
        await repo.upsert_dataset_snapshot({**value.snapshot().model_dump(),"storage_path":str(source)})
    a,b=stores;container.store=b
    await repo.create_session("bound",a.dataset_fingerprint(),"bound-A",a.snapshot().version_id)
    await repo.create_session("unbound",session_id="unbound")
    await repo.create_session("bad version",session_id="missing-version",dataset_version_id="version_missing")
    return app,container,a,b


def test_three_reads_and_post_use_bound_dataset_without_mutating_global(tmp_path,monkeypatch):
    async def scenario():
        app,container,a,b=await setup(tmp_path,monkeypatch)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
            detail=await client.get("/api/sessions/bound-A");assert detail.status_code==200
            assert container.store is b  # Session GET has no activation side effect.
            summary=await client.get("/api/data/summary",params={"session_id":"bound-A"})
            assert summary.status_code==200 and summary.json()["total_patents"]==1
            assert summary.json()["dataset_snapshot"]["version_id"]==a.snapshot().version_id
            tools=(await client.get("/api/tools",params={"session_id":"bound-A"})).json()["tools"]
            assert next(item for item in tools if item["name"]=="analyze_patent_trend")["availability"]["available"] is True
            capabilities=(await client.get("/api/capabilities",params={"session_id":"bound-A"})).json()["capabilities"]
            assert next(item for group in capabilities for item in group["tools"] if item["name"]=="analyze_patent_trend")["available"] is True
            executed=await client.post("/api/tools/get_dataset_summary",json={"session_id":"bound-A"})
            assert executed.status_code==200 and executed.json()["total_patents"]==1
            assert executed.json()["provenance"]["dataset_version_id"]==a.snapshot().version_id
            assert container.store is b
            # Default calls keep the legacy no-session dataset contract.
            assert (await client.get("/api/data/summary")).json()["total_patents"]==2
            assert (await client.post("/api/tools/get_dataset_summary",json={})).json()["total_patents"]==2
            assert (await client.get("/api/tools")).status_code==200
            assert (await client.get("/api/capabilities")).status_code==200
    asyncio.run(scenario())


def test_unbound_missing_and_missing_version_never_fall_back(tmp_path,monkeypatch):
    async def scenario():
        app,container,a,b=await setup(tmp_path,monkeypatch)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
            for path in ("/api/tools","/api/capabilities"):
                response=await client.get(path,params={"session_id":"unbound"});assert response.status_code==200
                entries=response.json().get("tools") or [item for group in response.json()["capabilities"] for item in group["tools"]]
                assert all(not item.get("availability",item).get("available") for item in entries)
                assert all("未绑定" in item.get("availability",item)["reason"] for item in entries)
            assert (await client.get("/api/data/summary",params={"session_id":"unbound"})).status_code==404
            assert (await client.post("/api/tools/get_dataset_summary",json={"session_id":"unbound"})).status_code==400
            for ident,status in (("absent",404),("missing-version",409)):
                for path in ("/api/tools","/api/capabilities","/api/data/summary"):
                    response=await client.get(path,params={"session_id":ident});assert response.status_code==status
                    if status==409:assert "requires_reimport" in response.text
                assert (await client.post("/api/tools/get_dataset_summary",json={"session_id":ident})).status_code==status
            assert await container.dataset_runtime.for_session("unbound",b) is None
            with pytest.raises(KeyError):await container.dataset_runtime.for_session("absent",b)
            assert await container.dataset_runtime.for_session(None,b) is b
            assert container.store is b
    asyncio.run(scenario())


def test_hash_conflict_and_missing_infrastructure_are_explicit(tmp_path,monkeypatch):
    async def scenario():
        app,container,a,b=await setup(tmp_path,monkeypatch)
        (Path(a._source_dir)/"records.jsonl").write_text(PatentRecord(patent_number="USCHANGEDA1",normalized_patent_number="USCHANGEDA1",title="changed",abstract="cell").model_dump_json())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
            for path in ("/api/tools","/api/capabilities","/api/data/summary"):
                response=await client.get(path,params={"session_id":"bound-A"});assert response.status_code==409
                assert "requires_reimport" in response.text and str(tmp_path) not in response.text
            assert (await client.post("/api/tools/get_dataset_summary",json={"session_id":"bound-A"})).status_code==409
            container.dataset_runtime=None
            for path in ("/api/tools","/api/capabilities","/api/data/summary"):
                assert (await client.get(path,params={"session_id":"bound-A"})).status_code==503
                assert (await client.get(path)).status_code==200
            assert (await client.post("/api/tools/get_dataset_summary",json={"session_id":"bound-A"})).status_code==503
            assert container.store is b
    asyncio.run(scenario())


@pytest.mark.parametrize("asgi_spec",["2.3","2.4"])
def test_agent_explicit_session_is_strict_and_default_new_session_still_works(tmp_path,monkeypatch,asgi_spec):
    class Agent:
        observed=[]
        async def stream_query(self,message,session,storage,*args,**kwargs):
            self.observed.append(storage.snapshot().version_id)
            yield {"type":"final","text":"done","final_status":"completed","turn_id":kwargs["turn_id"]}
            yield {"type":"done","session_id":session.id,"turn_id":kwargs["turn_id"],"final_status":"completed","answer_present":True}
    async def scenario():
        app,container,a,b=await setup(tmp_path,monkeypatch);agent=Agent();container.agent=agent
        async def spec23(scope,receive,send):
            scope={**scope,"asgi":{**scope.get("asgi",{}),"spec_version":asgi_spec}}
            await app(scope,receive,send)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=spec23),base_url="http://testserver") as client:
            for ident,status in (("unbound",400),("absent",404),("missing-version",409)):
                assert (await client.post("/api/agent/chat",json={"session_id":ident,"message":"test"})).status_code==status
            assert agent.observed==[]
            for ident in ("bound-A",None):
                body={"message":"test"}
                if ident is not None:body["session_id"]=ident
                response=await client.post("/api/agent/chat",json=body)
                assert response.status_code==200
                assert '"type": "text", "content": "done"' in response.text and '"type": "done"' in response.text
            assert agent.observed==[a.snapshot().version_id,b.snapshot().version_id]
            detail=await container.conversation_store.get_session_detail("bound-A")
            assert detail["turns"][0]["dataset_version_id"]==a.snapshot().version_id
            assert detail["turns"][0]["status"]=="completed"
            assert not container.active_generation_turns
            assert container.store is b
    asyncio.run(scenario())


def test_agent_http_disconnect_cleans_active_turns(tmp_path,monkeypatch):
    import json
    class WaitingAgent:
        async def stream_query(self,*args,**kwargs):
            await asyncio.Event().wait()
            if False:yield {}
    async def scenario():
        app,container,_,_=await setup(tmp_path,monkeypatch);container.agent=WaitingAgent()
        body=json.dumps({"session_id":"bound-A","message":"test disconnect"}).encode()
        disconnect=asyncio.Event();reads=0;body_sent=False
        async def receive():
            nonlocal reads
            reads+=1
            if reads==1:return {"type":"http.request","body":body,"more_body":False}
            await disconnect.wait()
            return {"type":"http.disconnect"}
        async def send(message):
            nonlocal body_sent
            if message["type"]=="http.response.body" and message.get("body"):
                body_sent=True
                assert container.active_generation_turns
                disconnect.set()
        scope={"type":"http","asgi":{"version":"3.0","spec_version":"2.3"},"http_version":"1.1","method":"POST","scheme":"http","path":"/api/agent/chat","raw_path":b"/api/agent/chat","query_string":b"","headers":[(b"host",b"testserver"),(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())],"client":("127.0.0.1",123),"server":("testserver",80)}
        await app(scope,receive,send)
        assert body_sent and not container.active_generation_turns
        assert reads==2
    asyncio.run(scenario())
