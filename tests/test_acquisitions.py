"""Synthetic public-contract tests; no provider account or external network used."""
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from patent_agent.application.acquisitions import (AcquisitionService,AcquisitionRequest,AcquisitionError,OPSClient,TOKEN_URL,OPS_ROOT,parse_ops_xml,safe_quota_headers,publish_dataset)
from patent_agent.application.services import DatasetImportService
from patent_agent.application.dataset_runtime import DatasetRuntimeManager
from patent_agent.infrastructure import AppContainer,AppSettings
from storage.conversation_store import ConversationStore

XML=b'''<ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns:ex="http://www.epo.org/exchange"><ops:biblio-search total-result-count="1"><ex:exchange-documents><ex:exchange-document country="EP" doc-number="1000000" kind="A1" family-id="F1"><ex:bibliographic-data><ex:publication-reference><ex:document-id document-id-type="docdb"><ex:country>EP</ex:country><ex:doc-number>1000000</ex:doc-number><ex:kind>A1</ex:kind><ex:date>20200101</ex:date></ex:document-id></ex:publication-reference><ex:application-reference><ex:document-id document-id-type="docdb"><ex:country>EP</ex:country><ex:doc-number>99999</ex:doc-number><ex:kind>A</ex:kind><ex:date>20190101</ex:date></ex:document-id></ex:application-reference><ex:invention-title lang="en">Battery cell</ex:invention-title><ex:parties><ex:applicants><ex:applicant data-format="epodoc"><ex:applicant-name><ex:name>ACME</ex:name></ex:applicant-name></ex:applicant></ex:applicants></ex:parties><ex:classifications-ipcr><ex:classification-ipcr><ex:text>H01M 10/052</ex:text></ex:classification-ipcr></ex:classifications-ipcr><ex:patent-classifications><ex:patent-classification><ex:classification-scheme scheme="CPCI"/><ex:section>H</ex:section><ex:class>01</ex:class><ex:subclass>M</ex:subclass><ex:main-group>10</ex:main-group><ex:subgroup>052</ex:subgroup></ex:patent-classification></ex:patent-classifications></ex:bibliographic-data><ex:abstract lang="en"><ex:p>A solid electrolyte.</ex:p></ex:abstract></ex:exchange-document></ex:exchange-documents></ops:biblio-search></ops:world-patent-data>'''

async def container(tmp_path):
    settings=AppSettings(project_root=tmp_path,data_root=tmp_path/"data",input_dir=str(tmp_path/"data"),session_db=tmp_path/"db.sqlite",cors_origins=())
    value=AppContainer(settings);value.conversation_store=ConversationStore(settings.session_db);await value.conversation_store.initialize()
    value.dataset_service=DatasetImportService();value.dataset_runtime=DatasetRuntimeManager(value.conversation_store,value.dataset_service)
    return value

class FakeOPS:
    calls=0
    total=1
    gate=None
    active=0
    maximum=0
    def __init__(self,*args):self.quota={};self.response_hashes=["safe-hash"];self.business_requests=0;self.bytes_received=1
    async def __aenter__(self):
        type(self).active+=1;type(self).maximum=max(type(self).maximum,type(self).active);return self
    async def __aexit__(self,*args):type(self).active-=1
    async def search_page(self,query,start,end):
        type(self).calls+=1;self.business_requests+=1
        if type(self).gate:await type(self).gate.wait()
        _,records=parse_ops_xml(XML)
        return type(self).total,records

async def confirmed(service,**kwargs):
    req=AcquisitionRequest(query='ti="battery"',**kwargs)
    prepared,_=await service.prepare_or_confirm(req)
    confirmed_req=req.model_copy(update={"acquisition_id":prepared["id"],"confirmation_token":prepared["confirmation_token"]})
    job,start=await service.prepare_or_confirm(confirmed_req)
    return prepared,job,start,confirmed_req

@pytest.fixture(autouse=True)
def reset_fake():
    FakeOPS.calls=0;FakeOPS.total=1;FakeOPS.gate=None;FakeOPS.active=0;FakeOPS.maximum=0


def test_prepare_never_calls_provider_and_token_not_readable(tmp_path,monkeypatch):
    monkeypatch.delenv("EPO_OPS_CONSUMER_KEY",raising=False);monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET",raising=False)
    async def scenario():
        service=AcquisitionService(await container(tmp_path),FakeOPS)
        prepared,job,start,req=await confirmed(service)
        assert FakeOPS.calls==0 and start is False
        assert prepared["state"]=="awaiting_confirmation" and prepared["outbound_host"]=="ops.epo.org"
        assert job["state"]=="credentials_required"
        assert "confirmation_token" not in await service.get(job["id"])
        assert prepared["confirmation_token"] not in json.dumps(job)
        again,start=await service.prepare_or_confirm(req)
        assert again["id"]==job["id"] and not start
    asyncio.run(scenario())


def test_confirmation_bound_to_request_and_expiry(tmp_path,monkeypatch):
    async def scenario():
        service=AcquisitionService(await container(tmp_path),FakeOPS)
        initial,_=await service.prepare_or_confirm(AcquisitionRequest(query="battery"))
        req=AcquisitionRequest(query="different",acquisition_id=initial["id"],confirmation_token=initial["confirmation_token"])
        with pytest.raises(ValueError,match="mismatch"):await service.prepare_or_confirm(req)
        import aiosqlite
        async with aiosqlite.connect(service.db) as db:
            await db.execute("UPDATE acquisitions SET expires_at='2000-01-01' WHERE id=?",(initial["id"],));await db.commit()
        with pytest.raises(ValueError,match="expired"):await service.prepare_or_confirm(req.model_copy(update={"query":"battery"}))
    asyncio.run(scenario())


def test_complete_publishes_replayable_version_but_partial_does_not(tmp_path,monkeypatch):
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY","synthetic-key");monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET","synthetic-secret")
    async def scenario():
        value=await container(tmp_path);service=AcquisitionService(value,FakeOPS)
        _,job,start,req=await confirmed(service)
        assert start
        await service.run(job["id"])
        finished=await service.get(job["id"])
        assert finished["state"]=="completed" and finished["matched_set_complete"] is True
        assert finished["field_status"]["claims"]=="not_fetched"
        versions=await value.conversation_store.list_dataset_versions();assert len(versions)==1
        reloaded=await DatasetRuntimeManager(value.conversation_store,value.dataset_service).get(finished["dataset_version_id"])
        assert reloaded.get_all().iloc[0]["cpc_codes"]=="H01M10/052"
        assert reloaded._import_report["acquisition"]["response_hashes"]==["safe-hash"]
        again,start=await service.prepare_or_confirm(req);assert not start
        assert FakeOPS.calls==1
        FakeOPS.total=1001
        _,partial,_,_=await confirmed(service,limit=1)
        await service.run(partial["id"])
        assert (await service.get(partial["id"]))["state"]=="partial"
        assert len(await value.conversation_store.list_dataset_versions())==1
    asyncio.run(scenario())


def test_cancel_and_concurrency_restart_are_explicit(tmp_path,monkeypatch):
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY","key");monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET","secret")
    async def scenario():
        value=await container(tmp_path);service=AcquisitionService(value,FakeOPS);FakeOPS.gate=asyncio.Event()
        _,one,_,_=await confirmed(service);_,two,_,_=await confirmed(service)
        first=asyncio.create_task(service.run(one["id"]));second=asyncio.create_task(service.run(two["id"]))
        for _ in range(20):
            if FakeOPS.calls:break
            await asyncio.sleep(.01)
        await service.cancel(one["id"]);FakeOPS.gate.set();await asyncio.gather(first,second)
        assert FakeOPS.maximum==1
        assert (await service.get(one["id"]))["state"]=="cancelled"
        assert (await service.get(two["id"]))["state"]=="completed"
        _,three,_,_=await confirmed(service)
        await value.conversation_store.mark_inflight_interrupted()
        assert (await service.get(three["id"]))["state"]=="interrupted"
    asyncio.run(scenario())


def test_xml_entities_and_missing_publication_are_rejected():
    with pytest.raises(AcquisitionError,match="unsafe_xml"):parse_ops_xml(b'<!DOCTYPE x [<!ENTITY y "z">]>'+XML)
    with pytest.raises(AcquisitionError,match="identity"):parse_ops_xml(XML.replace(b'kind="A1"',b''))
    count,records=parse_ops_xml(XML)
    assert count==1 and records[0].family_id=="F1" and records[0].claims==[]
    assert records[0].applicants==["ACME"] and records[0].claims_structure_status=="not_fetched"

class BytesStream(httpx.AsyncByteStream):
    def __init__(self,body):self.body=body
    async def __aiter__(self):yield self.body


def test_ops_fixed_endpoint_auth_budget_logging_and_quota(tmp_path,monkeypatch,caplog):
    key,secret,token,query="SYNTHETIC_KEY_X","SYNTHETIC_SECRET_X","SYNTHETIC_TOKEN_X","SYNTHETIC_CQL_X"
    calls=[]
    def handler(request):
        calls.append(request)
        logging.getLogger("httpcore.http11").debug("headers=%r",request.headers)
        if request.url.path.endswith("accesstoken"):
            assert request.content==b"grant_type=client_credentials"
            return httpx.Response(200,stream=BytesStream(json.dumps({"access_token":token,"expires_in":3600}).encode()))
        assert str(request.url).startswith(OPS_ROOT+"/published-data/search/biblio")
        assert request.headers["X-OPS-Range"]=="1-100"
        return httpx.Response(200,stream=BytesStream(XML),headers={"X-Throttling-Control":"yellow arbitrary-sensitive-text","X-IndividualQuotaPerHour-Used":"99","X-RegisteredQuotaPerWeek-Used":"untrusted-sensitive-text"})
    async def scenario():
        async with OPSClient(key,secret,transport=httpx.MockTransport(handler)) as client:
            assert (await client.search_page(query,1,100))[0]==1
            assert client.quota=={"X-IndividualQuotaPerHour-Used":99,"throttle_state":"yellow"}
    with caplog.at_level(logging.DEBUG):asyncio.run(scenario())
    assert len(calls)==2
    for sensitive in [key,secret,token,query,"arbitrary-sensitive-text",__import__("base64").b64encode((key+":"+secret).encode()).decode()]:assert sensitive not in caplog.text
    assert safe_quota_headers({"X-Rejection-Reason":"secret","X-RegisteredQuotaPerWeek-Used":"9999999999999999999999"})=={"rejection_category":"provider_rejected"}


def test_actual_retries_do_not_exceed_task_request_budget(monkeypatch):
    sent=[]
    async def no_sleep(_):pass
    monkeypatch.setattr(asyncio,"sleep",no_sleep)
    def handler(request):sent.append(request);return httpx.Response(503,stream=BytesStream(b""))
    async def scenario():
        async with OPSClient("key","secret",transport=httpx.MockTransport(handler)) as client:
            for _ in range(20):
                try:await client._request("GET",OPS_ROOT+"/published-data/search/biblio")
                except AcquisitionError:pass
    asyncio.run(scenario());assert len(sent)==20


def test_compressed_or_oversize_token_response_rejected():
    async def scenario():
        for body,headers,message in [(b"x",{"Content-Encoding":"gzip"},"compressed"),(b"x"*65537,{},"byte_budget")]:
            async with OPSClient("key","secret",transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=BytesStream(body),headers=headers))) as client:
                with pytest.raises(AcquisitionError,match=message):await client.authenticate()
    asyncio.run(scenario())


def test_dns_is_pinned_and_private_targets_rejected(monkeypatch):
    import socket
    seen=[]
    monkeypatch.setattr(socket,"getaddrinfo",lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,"",("93.184.216.34",443))])
    class Client:
        def __init__(self,**kwargs):assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        def stream(self,method,url,**kwargs):
            seen.append((url,kwargs))
            class Context:
                async def __aenter__(self):return httpx.Response(200,stream=BytesStream(b"{}"))
                async def __aexit__(self,*a):pass
            return Context()
        async def aclose(self):pass
    monkeypatch.setattr(httpx,"AsyncClient",Client)
    async def scenario():
        async with OPSClient("key","secret") as client:await client._request("POST",TOKEN_URL,token=True)
        assert seen[0][0].startswith("https://93.184.216.34/")
        assert seen[0][1]["headers"]["Host"]=="ops.epo.org" and seen[0][1]["extensions"]["sni_hostname"]=="ops.epo.org"
        monkeypatch.setattr(socket,"getaddrinfo",lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",443))])
        with pytest.raises(AcquisitionError,match="resolution"):
            async with OPSClient("key","secret"):pass
    asyncio.run(scenario())


def test_cancel_while_canonical_replay_is_running_cannot_publish(tmp_path,monkeypatch):
    import threading
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY","key");monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET","secret")
    async def scenario():
        value=await container(tmp_path);service=AcquisitionService(value,FakeOPS)
        started=threading.Event();release=threading.Event();original=value.dataset_service.load
        def blocked_load(*args):
            started.set()
            assert release.wait(5)
            return original(*args)
        monkeypatch.setattr(value.dataset_service,"load",blocked_load)
        _,job,_,_=await confirmed(service)
        task=asyncio.create_task(service.run(job["id"]))
        for _ in range(100):
            if started.is_set():break
            await asyncio.sleep(.01)
        assert started.is_set()
        await service.cancel(job["id"]);release.set();await task
        assert (await service.get(job["id"]))["state"]=="cancelled"
        assert await value.conversation_store.list_dataset_versions()==[]
        assert not (value.settings.data_root/".patentagent"/"datasets").exists()
    asyncio.run(scenario())


def test_failed_database_publication_removes_only_its_created_directory(tmp_path,monkeypatch):
    async def scenario():
        value=await container(tmp_path);source=tmp_path/"staged";source.mkdir()
        _,records=parse_ops_xml(XML)
        (source/"records.jsonl").write_text(records[0].model_dump_json()+"\n")
        store=value.dataset_service.load(str(source),"canonical_jsonl")
        sibling=value.settings.data_root/".patentagent"/"datasets"/"dataset_preserved";sibling.mkdir(parents=True);(sibling/"keep").write_text("unrelated")
        async def fail(*_):raise RuntimeError("synthetic database failure")
        monkeypatch.setattr(value.conversation_store,"write_dataset_snapshot",fail)
        with pytest.raises(RuntimeError):await publish_dataset(value,store,source,"dataset_synthetic","test")
        assert (sibling/"keep").read_text()=="unrelated"
        assert not (value.settings.data_root/".patentagent"/"datasets"/"dataset_synthetic"/store.snapshot().version_id/"source").exists()
        assert value.store is None
    asyncio.run(scenario())


def test_acquisition_rest_confirmation_sources_status_and_token_redaction(tmp_path,monkeypatch):
    import server
    monkeypatch.delenv("EPO_OPS_CONSUMER_KEY",raising=False);monkeypatch.delenv("EPO_OPS_CONSUMER_SECRET",raising=False)
    async def scenario():
        app=server.create_app();value=await container(tmp_path);app.state.container=value
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://testserver") as client:
            source=(await client.get("/api/sources")).json()["sources"]
            assert len(source)==7 and sum(item["enabled"] for item in source)==1
            body={"query":"ti=battery","limit":100,"source_id":"epo_ops"}
            prepared=(await client.post("/api/acquisitions",json=body)).json()["acquisition"]
            assert prepared["state"]=="awaiting_confirmation"
            get=await client.get("/api/acquisitions/"+prepared["id"])
            assert prepared["confirmation_token"] not in get.text
            confirmed_response=await client.post("/api/acquisitions",json={**body,"acquisition_id":prepared["id"],"confirmation_token":prepared["confirmation_token"]})
            assert confirmed_response.status_code==202
            assert confirmed_response.json()["acquisition"]["state"]=="credentials_required"
            statuses=(await client.get("/api/sources")).json()["sources"]
            assert next(item for item in statuses if item["id"]=="epo_ops")["invocation_status"]=="credentials_required"
    asyncio.run(scenario())


def test_reacquiring_identical_content_at_different_times_deduplicates(tmp_path,monkeypatch):
    import patent_agent.application.acquisitions as module
    monkeypatch.setenv("EPO_OPS_CONSUMER_KEY","key");monkeypatch.setenv("EPO_OPS_CONSUMER_SECRET","secret")
    async def scenario():
        value=await container(tmp_path);service=AcquisitionService(value,FakeOPS)
        _,one,_,_=await confirmed(service)
        monkeypatch.setattr(module,"now",lambda:"2026-10-15T01:00:00+00:00")
        await service.run(one["id"])
        first=await service.get(one["id"])
        assert first["state"]=="completed"
        _,two,_,_=await confirmed(service)
        monkeypatch.setattr(module,"now",lambda:"2026-10-15T02:00:00+00:00")
        await service.run(two["id"])
        second=await service.get(two["id"])
        assert second["state"]=="completed" and second["deduplicated"] is True
        assert first["dataset_version_id"]==second["dataset_version_id"]
        assert len(await value.conversation_store.list_dataset_versions())==1
        assert value.store.get_all()["data_as_of"].tolist()==[""]
    asyncio.run(scenario())
