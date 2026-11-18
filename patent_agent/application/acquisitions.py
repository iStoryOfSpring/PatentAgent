"""Bounded, confirmed acquisition of public EPO OPS bibliographic records."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import logging
import re
from contextvars import ContextVar
import os
from pathlib import Path
import secrets
import shutil
import socket
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

import aiosqlite
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from models.patent import (PatentRecord, LocalizedText, Party, Classification, DataSource, RecordProvenance, FieldProvenance)
from engine.adapters.common import iso_date, normalized_document_number, stable_unique
from patent_agent.application.services import DatasetImportService

OPS_HOST = "ops.epo.org"
OPS_ROOT = "https://ops.epo.org/3.2/rest-services"
TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
QUOTA_HEADERS = ("X-IndividualQuotaPerHour-Used", "X-RegisteredQuotaPerWeek-Used", "X-Rejection-Reason", "X-Throttling-Control")
_acquisition_logging = ContextVar("acquisition_logging", default=False)

class _AcquisitionLogFilter(logging.Filter):
    def filter(self, record):
        # httpcore DEBUG can include Authorization headers; httpx INFO includes CQL.
        # Suppress the entire untrusted transport record inside the acquisition context.
        return not _acquisition_logging.get()

for _logger_name in ("httpx", "httpcore", "httpcore.http11", "httpcore.http2", "httpcore.connection", "httpcore.proxy"):
    logging.getLogger(_logger_name).addFilter(_AcquisitionLogFilter())

def safe_quota_headers(headers):
    result = {}
    for key in QUOTA_HEADERS[:2]:
        value = headers.get(key, "")
        if re.fullmatch(r"[0-9]{1,15}", value):result[key]=int(value)
    throttle=headers.get("X-Throttling-Control", "").lower()
    colors=[value for value in ("green", "yellow", "red", "black") if re.search(r"\b"+value+r"\b",throttle)]
    if colors:result["throttle_state"]=colors[-1]
    if headers.get("X-Rejection-Reason"):result["rejection_category"]="provider_rejected"
    return result


class SourceDefinition(BaseModel):
    id: str
    name: str
    documentation_url: str
    documentation_verified: bool = True
    authorization_status: str = "not_configured"
    invocation_status: str = "not_called"
    enabled: bool = False
    capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

class AcquisitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = "epo_ops"
    query: str = Field(min_length=1,max_length=4096)
    limit: int = Field(default=100,ge=1,le=1000)
    name: str = Field(default="EPO OPS",min_length=1,max_length=120)
    dataset_id: str = ""
    confirmation_token: str | None = Field(default=None,max_length=256)
    acquisition_id: str | None = None

    @field_validator("query")
    @classmethod
    def query_text(cls,value):
        value = " ".join(value.split())
        if not value or "://" in value or any(ord(c)<32 for c in value):
            raise ValueError("query must be CQL text, not a URL")
        return value

    @field_validator("source_id")
    @classmethod
    def source(cls,value):
        if value != "epo_ops": raise ValueError("Only epo_ops acquisition is implemented")
        return value

    @field_validator("dataset_id")
    @classmethod
    def dataset(cls,value):
        import re
        if value and not re.fullmatch(r"dataset_[A-Za-z0-9_-]{6,80}",value): raise ValueError("Invalid dataset_id")
        return value

    def canonical(self):
        return self.model_dump(exclude={"confirmation_token","acquisition_id"})

def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def sources():
    credentials = bool(os.getenv("EPO_OPS_CONSUMER_KEY") and os.getenv("EPO_OPS_CONSUMER_SECRET"))
    return [
        SourceDefinition(id="cnipa",name="CNIPA",documentation_url="https://www.cnipa.gov.cn/jact/front/mailpubdetail.do?sysid=12&transactId=496965",capabilities=["official_export"],limitations=["官方导出；注册 IPDPS 不代表已确认公众 REST"]),
        SourceDefinition(id="epo_ops",name="EPO OPS",documentation_url="https://www.epo.org/en/searching-for-patents/data/web-services/ops",enabled=True,authorization_status="configured_unverified" if credentials else "credentials_required",capabilities=["bibliographic","abstract","classifications","family_id"],limitations=["免费 4GB/week；搜索最多可访问 2000 条，本应用单任务最多 1000 条", "claims/description/full family/legal: not_fetched", "仅后端环境凭据；真实账号调用尚未验证"]),
        SourceDefinition(id="google_patents",name="Google Patents Public Data",documentation_url="https://github.com/google/patents-public-data",capabilities=["public_export"],limitations=["BigQuery/公开数据导出；无已实现在线采集"]),
        SourceDefinition(id="uspto",name="USPTO",documentation_url="https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20",capabilities=["official_export"],limitations=["PatentsView 迁移 ODP；不复用旧接口假设"]),
        SourceDefinition(id="zhihuiya",name="智慧芽",documentation_url="https://open.zhihuiya.com/devportal/api-reference/patent-search/task",authorization_status="disabled",capabilities=["commercial_optional"],limitations=["商业可选，默认禁用；Bearer 操作级鉴权"]),
        SourceDefinition(id="lens",name="Lens",documentation_url="https://support.lens.org/knowledge-base/lens-patent-and-scholar-api/",authorization_status="disabled",capabilities=["commercial_optional"],limitations=["14 天试用，长期付费，默认禁用"]),
        SourceDefinition(id="wipo",name="WIPO",documentation_url="https://www.wipo.int/en/web/patentscope/data/index",capabilities=["paid_pct_data"],limitations=["PCT 付费 SOAP/SFTP；非免费全球 REST"]),
    ]

class AcquisitionError(Exception): pass

class OPSClient:
    """Fixed-host client. Credentials/token never enter persisted state or errors."""
    def __init__(self, key, secret, *, transport=None):
        self.key,self.secret=key,secret
        self.transport=transport
        self.started=time.monotonic()
        self.business_requests=0
        self.bytes_received=0
        self.quota={}
        self.response_hashes=[]
        self.token=""
        self.token_deadline=0.0

    async def __aenter__(self):
        # Explicit DNS check; httpx redirects/proxy environment are disabled.
        self.pinned_ip = None
        if self.transport is None:
            addresses=await asyncio.to_thread(socket.getaddrinfo,OPS_HOST,443,type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise AcquisitionError("OPS host resolution rejected")
            self.pinned_ip=addresses[0][4][0]
        self.log_context=_acquisition_logging.set(True)
        self.client=httpx.AsyncClient(timeout=httpx.Timeout(30,connect=10),follow_redirects=False,trust_env=False,transport=self.transport)
        return self

    async def __aexit__(self,*args):
        try:await self.client.aclose()
        finally:_acquisition_logging.reset(self.log_context)

    async def _request(self,method,url,*,token=False,**kwargs):
        if url != TOKEN_URL and not url.startswith(OPS_ROOT+"/"):
            raise AcquisitionError("OPS URL rejected")
        maximum=65536 if token else 10*1024*1024
        for attempt in range(3):
            if time.monotonic()-self.started>180: raise AcquisitionError("task_time_budget_exhausted")
            if not token:
                self.business_requests+=1
                if self.business_requests>20:raise AcquisitionError("request_budget_exhausted")
            headers=dict(kwargs.get("headers", {}));headers["Accept-Encoding"]="identity"
            target=url
            options={**kwargs,"headers":headers}
            if self.pinned_ip:
                address="["+self.pinned_ip+"]" if ":" in self.pinned_ip else self.pinned_ip
                target=url.replace("https://"+OPS_HOST,"https://"+address,1)
                headers["Host"]=OPS_HOST
                options["extensions"]={"sni_hostname":OPS_HOST}
            async with self.client.stream(method,target,**options) as response:
                self.quota.update(safe_quota_headers(response.headers))
                rejection=response.headers.get("X-Rejection-Reason","")
                throttle=response.headers.get("X-Throttling-Control","").lower()
                if rejection or "black" in throttle or "red" in throttle or self.quota.get("X-RegisteredQuotaPerWeek-Used",0)>=4*1024**3:
                    raise AcquisitionError("quota_exhausted")
                if response.status_code in (429,503):
                    if attempt==2: raise AcquisitionError("quota_or_service_unavailable")
                    delay=min(2**attempt,4)
                    await asyncio.sleep(delay)
                    continue
                if response.status_code != 200:
                    raise AcquisitionError("credentials_rejected" if response.status_code in (401,403) else f"ops_http_{response.status_code}")
                if response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
                    raise AcquisitionError("compressed_response_rejected")
                body=bytearray()
                async for chunk in response.aiter_raw(chunk_size=65536):
                    if len(body)+len(chunk)>maximum or self.bytes_received+len(chunk)>20*1024*1024:
                        raise AcquisitionError("response_byte_budget_exhausted")
                    body.extend(chunk);self.bytes_received+=len(chunk)
                    if time.monotonic()-self.started>180: raise AcquisitionError("task_time_budget_exhausted")
                self.response_hashes.append(hashlib.sha256(body).hexdigest())
                return bytes(body)
        raise AcquisitionError("retry_budget_exhausted")

    async def authenticate(self):
        if self.token and time.monotonic()<self.token_deadline: return
        raw=await self._request("POST",TOKEN_URL,token=True,auth=httpx.BasicAuth(self.key,self.secret),data={"grant_type":"client_credentials"},headers={"Accept":"application/json"})
        try:
            obj=json.loads(raw);self.token=str(obj["access_token"]);expires=float(obj["expires_in"])
            if not self.token or not 0<expires<=86400: raise ValueError()
            self.token_deadline=time.monotonic()+max(0,expires-15)
        except (ValueError,KeyError,TypeError): raise AcquisitionError("invalid_token_response") from None

    async def search_page(self,query,start,end):
        await self.authenticate()
        raw=await self._request("GET",OPS_ROOT+"/published-data/search/biblio",params={"q":query},headers={"Authorization":"Bearer "+self.token,"X-OPS-Range":f"{start}-{end}","Accept":"application/xml"})
        return parse_ops_xml(raw)

def local(element): return element.tag.rsplit("}",1)[-1]
def children(element,name): return [n for n in element.iter() if local(n)==name]
def text(element): return " ".join("".join(element.itertext()).split()) if element is not None else ""
def first(element,name): return next(iter(children(element,name)),None)
def docid(element):
    ids=children(element,"document-id") if element is not None else []
    node=next((n for n in ids if n.attrib.get("document-id-type")=="docdb"),ids[0] if ids else None)
    if node is None:return "",""
    return "".join(text(first(node,k)) for k in ("country","doc-number","kind")),iso_date(text(first(node,"date")))

def parse_ops_xml(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper(): raise AcquisitionError("unsafe_xml")
    try: root=ET.fromstring(raw)
    except ET.ParseError: raise AcquisitionError("invalid_ops_xml") from None
    search=first(root,"biblio-search")
    if search is None: raise AcquisitionError("missing_search_metadata")
    try: total=int(search.attrib["total-result-count"])
    except (ValueError,KeyError): raise AcquisitionError("missing_result_count") from None
    if total<0: raise AcquisitionError("invalid_result_count")
    records=[]
    for doc in children(root,"exchange-document"):
        country=doc.attrib.get("country","");number=doc.attrib.get("doc-number","");kind=doc.attrib.get("kind","")
        if not country or not number or not kind: raise AcquisitionError("missing_publication_identity")
        publication=country+number+kind
        titles=[LocalizedText(language=n.attrib.get("lang","und"),text=text(n)) for n in children(doc,"invention-title") if text(n)]
        abstracts=[LocalizedText(language=n.attrib.get("lang","und"),text=text(n)) for n in children(doc,"abstract") if text(n)]
        def names(role):
            nodes=children(doc,role)
            preferred=[n for n in nodes if n.attrib.get("data-format")=="epodoc"] or nodes
            return stable_unique(text(first(n,"name")) or text(n) for n in preferred)
        applicants,inventors=names("applicant"),names("inventor")
        _,pub_date=docid(first(doc,"publication-reference"));app,filing=docid(first(doc,"application-reference"))
        priorities=[docid(n) for n in children(doc,"priority-claim")]
        ipc=[];cpc=[]
        for node in children(doc,"classification-ipcr"):
            value=text(first(node,"text"))
            if value: ipc.append("".join(value.split()))
        for node in children(doc,"patent-classification"):
            scheme=first(node,"classification-scheme")
            scheme_name=(scheme.attrib.get("scheme","") if scheme is not None else "").upper()
            if scheme_name not in ("CPCI","CPC"):continue
            parts={k:text(first(node,k)) for k in ("section","class","subclass","main-group","subgroup")}
            if all(parts.values()):cpc.append(parts["section"]+parts["class"]+parts["subclass"]+parts["main-group"]+"/"+parts["subgroup"])
        provenance=RecordProvenance(source=DataSource(adapter="epo_ops",source_name="EPO OPS",source_uri=OPS_ROOT+"/published-data/search/biblio",license_note="EPO OPS conditions; free quota 4GB/week; retain attribution and provenance"),source_record_id=publication,raw_record_hash=hashlib.sha256(ET.tostring(doc)).hexdigest())
        records.append(PatentRecord(patent_number=publication,normalized_patent_number=normalized_document_number(publication),publication_numbers=[publication],application_number=app,title=titles[0].text if titles else "",abstract=abstracts[0].text if abstracts else "",language=titles[0].language if titles else "und",localized_titles=titles,localized_abstracts=abstracts,applicants=applicants,inventors=inventors,applicant_parties=[Party(name=n,role="applicant",source="epo_ops") for n in applicants],inventor_parties=[Party(name=n,role="inventor",source="epo_ops") for n in inventors],publication_date=pub_date,filing_date=filing,priority_date=min([d for _,d in priorities if d],default=""),priority_numbers=[n for n,_ in priorities if n],ipc_codes=stable_unique(ipc),cpc_codes=stable_unique(cpc),classifications=[Classification(scheme="IPC",code=c) for c in stable_unique(ipc)]+[Classification(scheme="CPC",code=c) for c in stable_unique(cpc)],family_id=doc.attrib.get("family-id",""),jurisdiction=country,kind_code=kind,claims_structure_status="not_fetched",provenance=provenance,field_provenance=[FieldProvenance(field_name=f,source="epo_ops",source_record_id=publication) for f in ("title","abstract","publication_date","application_number","classifications")]))
    if total>0 and not records:raise AcquisitionError("empty_page_for_nonempty_result")
    return total,records

async def publish_dataset(container,store,source_root,dataset_id,name,import_id=""):
    """One version registration path shared by uploads and acquisitions."""
    repo=container.conversation_store
    version=store.snapshot().version_id
    existing=await repo.get_dataset_version(version)
    if existing:return existing["id"],existing["dataset_id"],True
    destination=(container.settings.data_root/".patentagent"/"datasets"/dataset_id/version/"source").resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():raise ValueError("dataset_destination_conflict")
    source_root.rename(destination)
    store._source_dir=str(destination);store._dataset_id_override=dataset_id;store._version_id_override=version
    try:
        await repo.upsert_dataset_snapshot({**store.snapshot().model_dump(mode="json"),"name":name,"storage_path":str(destination),"source_root":str(destination),"import_id":import_id,"import_report":store._import_report})
    except BaseException:
        # This exact directory was created by this publication; never remove siblings.
        shutil.rmtree(destination)
        raise
    if container.dataset_runtime:container.dataset_runtime.register(store)
    container.store=store
    return version,dataset_id,False

class AcquisitionService:
    def __init__(self,container,client_factory=OPSClient):
        self.container=container;self.client_factory=client_factory
        self._semaphore=asyncio.Semaphore(1)
    @property
    def db(self):return self.container.conversation_store.db_path

    async def get(self,ident):
        async with aiosqlite.connect(self.db) as db:
            db.row_factory=aiosqlite.Row
            cursor=await db.execute("SELECT id,state,request_json,result_json,expires_at,created_at,updated_at,cancel_requested FROM acquisitions WHERE id=?",(ident,))
            row=await cursor.fetchone()
        if row is None:raise KeyError(ident)
        obj=dict(row);obj["request"]=json.loads(obj.pop("request_json"));obj.update(json.loads(obj.pop("result_json")))
        return obj

    async def prepare_or_confirm(self,req):
        canonical=json.dumps(req.canonical(),sort_keys=True,ensure_ascii=False,separators=(",",":"));request_hash=digest(canonical)
        if not req.confirmation_token:
            token=secrets.token_urlsafe(32);ident="acq_"+uuid4().hex;created=now();expiry=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
            async with aiosqlite.connect(self.db) as db:
                await db.execute("INSERT INTO acquisitions(id,state,request_hash,token_hash,expires_at,request_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",(ident,"awaiting_confirmation",request_hash,digest(token),expiry,canonical,created,created));await db.commit()
            return {**await self.get(ident),"confirmation_token":token,"outbound_host":OPS_HOST,"budget":{"records":req.limit,"pages":10,"business_requests":20,"seconds":180,"response_bytes":10*1024*1024}},False
        if not req.acquisition_id:raise ValueError("acquisition_id_required")
        async with aiosqlite.connect(self.db) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor=await db.execute("SELECT state,request_hash,token_hash,expires_at FROM acquisitions WHERE id=?",(req.acquisition_id,));row=await cursor.fetchone()
            if row is None:raise KeyError(req.acquisition_id)
            if row[1]!=request_hash or not secrets.compare_digest(row[2],digest(req.confirmation_token)):raise ValueError("confirmation_mismatch")
            if row[0]!="awaiting_confirmation":return await self.get(req.acquisition_id),False
            if row[3]<now():raise ValueError("confirmation_expired")
            state="queued" if os.getenv("EPO_OPS_CONSUMER_KEY") and os.getenv("EPO_OPS_CONSUMER_SECRET") else "credentials_required"
            await db.execute("UPDATE acquisitions SET state=?,updated_at=? WHERE id=?",(state,now(),req.acquisition_id));await db.commit()
        return await self.get(req.acquisition_id),state=="queued"

    async def update(self,ident,state,result):
        async with aiosqlite.connect(self.db) as db:
            await db.execute("UPDATE acquisitions SET state=?,result_json=?,updated_at=? WHERE id=? AND state NOT IN ('cancelled','interrupted')",(state,json.dumps(result,ensure_ascii=False),now(),ident));await db.commit()

    async def cancel(self,ident):
        job=await self.get(ident)
        if job["state"]=="publishing":raise ValueError("publication_committing")
        async with aiosqlite.connect(self.db) as db:
            await db.execute("UPDATE acquisitions SET cancel_requested=1,state='cancelled',updated_at=? WHERE id=? AND state IN ('awaiting_confirmation','queued','running')",(now(),ident));await db.commit()
        return await self.get(ident)

    async def run(self,ident):
        async with self._semaphore:
            await self._run(ident)

    async def _run(self,ident):
        job=await self.get(ident)
        if job["state"]!="queued" or job["cancel_requested"]:return
        req=job["request"];records=[];pages=0;total=None;observed=now()
        metrics={"pages":0,"record_count":0,"matched_set_complete":False,"field_status":{"bibliographic":"fetched","abstract":"source_dependent","classifications":"source_dependent","family_id":"source_dependent","claims":"not_fetched","description":"not_fetched","family":"not_fetched","legal":"not_fetched"},"observed_at":observed}
        stage=self.container.settings.data_root/".patentagent"/"acquisitions"/ident
        try:
            await self.update(ident,"running",metrics)
            async with asyncio.timeout(180):
                async with self.client_factory(os.environ["EPO_OPS_CONSUMER_KEY"],os.environ["EPO_OPS_CONSUMER_SECRET"]) as client:
                    for start in range(1,req["limit"]+1,100):
                        if (await self.get(ident))["cancel_requested"]:await self.update(ident,"cancelled",metrics);return
                        count,page=await client.search_page(req["query"],start,min(start+99,req["limit"]))
                        if total is not None and count!=total:raise AcquisitionError("result_count_changed_during_acquisition")
                        total=count;records.extend(page);pages+=1
                        if len({r.normalized_patent_number for r in records})!=len(records):raise AcquisitionError("duplicate_publications_across_pages")
                        metrics.update({"pages":pages,"record_count":len(records),"total_matched":total,"quota_headers":client.quota,"response_hashes":client.response_hashes})
                        await self.update(ident,"running",metrics)
                        if len(records)>=total:break
                    metrics.update({"business_requests":client.business_requests,"response_bytes":client.bytes_received})
            complete=total is not None and len(records)==total
            metrics["matched_set_complete"]=complete
            if not complete:await self.update(ident,"partial",{**metrics,"error":"matched_set_incomplete: increase explicit budget or narrow CQL query"});return
            if (await self.get(ident))["cancel_requested"]:await self.update(ident,"cancelled",metrics);return
            if not records:await self.update(ident,"completed",metrics);return
            source=stage/"source";source.mkdir(parents=True,exist_ok=False)
            path=source/"records.jsonl"
            for record in records:record.provenance.imported_at=observed
            path.write_text("".join(r.model_dump_json()+"\n" for r in records),encoding="utf-8")
            dataset_id=req["dataset_id"] or "dataset_"+uuid4().hex
            manifest={"schema_version":1,"dataset_id":dataset_id,"source_name":"EPO OPS","source_uri":OPS_ROOT+"/published-data/search/biblio","retrieved_at":observed,"data_as_of":"","license_note":"EPO OPS terms; limited bibliographic scope", "files":[{"path":path.name,"source_format":"canonical_jsonl","sha256":hashlib.sha256(path.read_bytes()).hexdigest()}]}
            (source/"patentagent-import.json").write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf-8")
            store=await asyncio.to_thread((self.container.dataset_service or DatasetImportService()).load,str(source),"canonical_jsonl")
            if store._import_report.get("records_failed"):raise AcquisitionError("canonical_replay_failed")
            store._import_report.update({"matched_set_complete":True,"acquisition":metrics})
            async with aiosqlite.connect(self.db) as db:
                claimed=await db.execute("UPDATE acquisitions SET state='publishing',updated_at=? WHERE id=? AND state='running' AND cancel_requested=0",(now(),ident))
                await db.commit()
                if not claimed.rowcount:return
            version,dataset_id,dedup=await publish_dataset(self.container,store,source,dataset_id,req["name"])
            await self.update(ident,"completed",{**metrics,"dataset_version_id":version,"dataset_id":dataset_id,"deduplicated":dedup})
        except asyncio.CancelledError:
            await self.update(ident,"interrupted",metrics);raise
        except Exception as exc:
            # Never serialize provider exceptions or URLs containing a query/token.
            category=str(exc) if isinstance(exc,AcquisitionError) else "acquisition_failed:"+type(exc).__name__
            await self.update(ident,"partial" if records else "failed",{**metrics,"error":category})
        finally:
            if stage.exists():shutil.rmtree(stage)
