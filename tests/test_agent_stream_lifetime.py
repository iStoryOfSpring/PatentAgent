"""Actual Agent app HTTP lifetime under disconnects; no body_iterator shortcuts."""
import asyncio
import json
import httpx
import pytest
from starlette.requests import ClientDisconnect
import server
from tests.test_session_dataset_resolution import setup


def request_scope(body,spec="2.4"):
    return {"type":"http","asgi":{"version":"3.0","spec_version":spec},"http_version":"1.1","method":"POST","scheme":"http","path":"/api/agent/chat","raw_path":b"/api/agent/chat","query_string":b"","headers":[(b"host",b"testserver"),(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())],"client":("127.0.0.1",123),"server":("testserver",80)}

@pytest.mark.parametrize("break_at",[1,2])
def test_asgi24_actual_agent_closes_immediately_and_next_request_runs(tmp_path,monkeypatch,break_at):
    async def scenario():
        app,container,a,_=await setup(tmp_path,monkeypatch)
        monkeypatch.setattr(server.app.state.container,"active_generation_turns",{"global-sentinel"})
        closed=[]
        class WaitingAgent:
            async def stream_query(self,*args,**kwargs):
                try:
                    yield {"type":"intent","goal":"test","analysis_type":"general","turn_id":kwargs["turn_id"]}
                    await asyncio.Event().wait()
                finally:closed.append("inner")
        container.agent=WaitingAgent()
        body=json.dumps({"session_id":"bound-A","message":"disconnect"}).encode();reads=0;sent=0
        async def receive():
            nonlocal reads
            reads+=1;assert reads==1
            return {"type":"http.request","body":body,"more_body":False}
        async def send(message):
            nonlocal sent
            if message["type"]=="http.response.body" and message.get("body"):
                sent+=1
                if sent==break_at:
                    assert container.active_generation_turns
                    raise OSError("synthetic disconnected peer")
        with pytest.raises(ClientDisconnect):await app(request_scope(body),receive,send)
        assert not container.active_generation_turns  # Immediately, without GC or sleep.
        assert closed==(["inner"] if break_at==2 else [])
        assert server.app.state.container.active_generation_turns=={"global-sentinel"}
        detail=await container.conversation_store.get_session_detail("bound-A")
        assert detail["turns"][0]["status"]=="interrupted"
        assert detail["turns"][0]["dataset_version_id"]==a.snapshot().version_id
        class CompleteAgent:
            async def stream_query(self,*args,**kwargs):
                yield {"type":"final","text":"second request complete","final_status":"completed","turn_id":kwargs["turn_id"]}
                yield {"type":"done","session_id":"bound-A","turn_id":kwargs["turn_id"],"final_status":"completed","answer_present":True}
        container.agent=CompleteAgent()
        async def spec24(scope,receive,send):await app({**scope,"asgi":{"version":"3.0","spec_version":"2.4"}},receive,send)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=spec24),base_url="http://testserver") as client:
            response=await client.post("/api/agent/chat",json={"session_id":"bound-A","message":"next"})
            assert response.status_code==200 and '"type": "done"' in response.text
        assert not container.active_generation_turns
        statuses=[turn["status"] for turn in (await container.conversation_store.get_session_detail("bound-A"))["turns"]]
        assert statuses==["interrupted","completed"]
    asyncio.run(scenario())


def test_asgi23_disconnect_after_inner_entry_closes_both_and_persists_interrupted(tmp_path,monkeypatch):
    async def scenario():
        app,container,_,_=await setup(tmp_path,monkeypatch);closed=[]
        class Agent:
            async def stream_query(self,*args,**kwargs):
                try:
                    yield {"type":"intent","goal":"test","analysis_type":"general","turn_id":kwargs["turn_id"]}
                    await asyncio.Event().wait()
                finally:closed.append("inner")
        container.agent=Agent();body=json.dumps({"session_id":"bound-A","message":"disconnect"}).encode();disconnect=asyncio.Event();reads=0;sent=0
        async def receive():
            nonlocal reads
            reads+=1
            if reads==1:return {"type":"http.request","body":body,"more_body":False}
            await disconnect.wait();return {"type":"http.disconnect"}
        async def send(message):
            nonlocal sent
            if message["type"]=="http.response.body" and message.get("body"):
                sent+=1
                if sent==2:disconnect.set()
        await app(request_scope(body,"2.3"),receive,send)
        assert closed==["inner"] and not container.active_generation_turns
        assert (await container.conversation_store.get_session_detail("bound-A"))["turns"][0]["status"]=="interrupted"
    asyncio.run(scenario())


@pytest.mark.parametrize("saved_status",["completed","waiting_approval","awaiting_clarification","cancelled"])
def test_interrupted_cleanup_never_overwrites_terminal_or_approval_state(tmp_path,monkeypatch,saved_status):
    async def scenario():
        _,container,_,_=await setup(tmp_path,monkeypatch);repo=container.conversation_store
        turn=await repo.start_turn("bound-A","test")
        await repo.update_turn(turn,status=saved_status)
        assert await repo.interrupt_turn_if_running(turn) is False
        assert (await repo.get_turn(turn))["status"]==saved_status
    asyncio.run(scenario())


def test_cleanup_failures_do_not_replace_transport_exception_or_leak_active_slot(tmp_path,monkeypatch):
    async def scenario():
        app,container,_,_=await setup(tmp_path,monkeypatch)
        class Agent:
            async def stream_query(self,*args,**kwargs):
                try:
                    yield {"type":"intent","goal":"test","analysis_type":"general","turn_id":kwargs["turn_id"]}
                finally:raise RuntimeError("synthetic inner cleanup failure")
        async def fail(_):raise RuntimeError("synthetic persistence cleanup failure")
        monkeypatch.setattr(container.conversation_store,"interrupt_turn_if_running",fail)
        container.agent=Agent();body=json.dumps({"session_id":"bound-A","message":"disconnect"}).encode();sent=0
        async def receive():return {"type":"http.request","body":body,"more_body":False}
        async def send(message):
            nonlocal sent
            if message["type"]=="http.response.body" and message.get("body"):
                sent+=1
                if sent==2:raise OSError("original disconnect")
        with pytest.raises(ClientDisconnect):await app(request_scope(body),receive,send)
        assert not container.active_generation_turns
    asyncio.run(scenario())


@pytest.mark.parametrize("waiting_status",["waiting_approval","awaiting_clarification"])
def test_actual_transport_cleanup_preserves_saved_approval_state(tmp_path,monkeypatch,waiting_status):
    async def scenario():
        app,container,_,_=await setup(tmp_path,monkeypatch);closed=[]
        class Agent:
            async def stream_query(self,*args,**kwargs):
                try:
                    if waiting_status=="waiting_approval":
                        yield {"type":"plan","steps":[],"requires_confirmation":True,"turn_id":kwargs["turn_id"]}
                    else:
                        yield {"type":"clarification","question":"Confirm scope","turn_id":kwargs["turn_id"]}
                    await asyncio.Event().wait()
                finally:closed.append(True)
        container.agent=Agent();body=json.dumps({"session_id":"bound-A","message":"wait"}).encode();sent=0
        async def receive():return {"type":"http.request","body":body,"more_body":False}
        async def send(message):
            nonlocal sent
            if message["type"]=="http.response.body" and message.get("body"):
                sent+=1
                if sent==2:raise OSError("synthetic waiting client disconnect")
        with pytest.raises(ClientDisconnect):await app(request_scope(body),receive,send)
        assert closed==[True] and not container.active_generation_turns
        assert (await container.conversation_store.get_session_detail("bound-A"))["turns"][0]["status"]==waiting_status
    asyncio.run(scenario())


def test_actual_http_user_cancellation_keeps_cancelled_state_after_cleanup(tmp_path,monkeypatch):
    async def scenario():
        app,container,_,_=await setup(tmp_path,monkeypatch);closed=[]
        class Agent:
            async def stream_query(self,*args,**kwargs):
                try:
                    yield {"type":"intent","goal":"test","analysis_type":"general","turn_id":kwargs["turn_id"]}
                    yield {"type":"synthesis","status":"started","turn_id":kwargs["turn_id"]}
                finally:closed.append(True)
        container.agent=Agent();body=json.dumps({"session_id":"bound-A","message":"cancel"}).encode();events=[]
        async def receive():return {"type":"http.request","body":body,"more_body":False}
        async def send(message):
            if message["type"]=="http.response.body" and message.get("body"):
                decoded=message["body"].decode()
                event=json.loads(next(line[6:] for line in decoded.splitlines() if line.startswith("data: ")))
                events.append(event)
                if event["type"]=="intent":await container.conversation_store.request_cancel(event["turn_id"])
        await app(request_scope(body),receive,send)
        assert any(event["type"]=="done" and event["final_status"]=="cancelled" for event in events)
        assert closed==[True] and not container.active_generation_turns
        assert (await container.conversation_store.get_session_detail("bound-A"))["turns"][0]["status"]=="cancelled"
    asyncio.run(scenario())


def test_actual_first_body_user_cancel_and_send_error_converges_to_cancelled(tmp_path,monkeypatch):
    async def scenario():
        app,container,_,_=await setup(tmp_path,monkeypatch)
        class Agent:
            async def stream_query(self,*args,**kwargs):
                raise AssertionError("disconnect happened before inner Agent entry")
                if False:yield {}
        container.agent=Agent();body=json.dumps({"session_id":"bound-A","message":"cancel/disconnect race"}).encode()
        async def receive():return {"type":"http.request","body":body,"more_body":False}
        async def send(message):
            if message["type"]=="http.response.body" and message.get("body"):
                event=json.loads(next(line[6:] for line in message["body"].decode().splitlines() if line.startswith("data: ")))
                await container.conversation_store.request_cancel(event["turn_id"])
                raise OSError("synthetic simultaneous cancel and disconnected peer")
        with pytest.raises(ClientDisconnect):await app(request_scope(body),receive,send)
        assert not container.active_generation_turns
        detail=await container.conversation_store.get_session_detail("bound-A")
        assert detail["turns"][0]["status"]=="cancelled"
        assert detail["session"]["status"]=="cancelled"
    asyncio.run(scenario())
