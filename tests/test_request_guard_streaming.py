"""Bounded receive tests expose replay bugs without an unbounded busy listener."""
import asyncio
from patent_agent.infrastructure.observability import RequestGuardMiddleware

SCOPE={"type":"http","headers":[(b"host",b"testserver")],"client":("127.0.0.1",1),"path":"/stream"}

def test_buffered_chunks_replayed_once_then_original_disconnect():
    async def scenario():
        events=[{"type":"http.request","body":b"first","more_body":True},{"type":"http.request","body":b"second","more_body":False},{"type":"http.disconnect"}]
        upstream_calls=0;delivered=[]
        async def receive():
            nonlocal upstream_calls
            upstream_calls+=1
            assert upstream_calls<=3
            return events[upstream_calls-1]
        async def app(scope,receive,send):
            assert upstream_calls==2
            delivered.append(await receive());delivered.append(await receive())
            assert upstream_calls==2
            delivered.append(await receive())
        await RequestGuardMiddleware(app,100)(SCOPE,receive,None)
        assert delivered==events and upstream_calls==3
    asyncio.run(scenario())

def test_exhausted_replay_really_awaits_upstream_and_is_cancellable():
    async def scenario():
        upstream_calls=0;blocked=asyncio.Event()
        async def receive():
            nonlocal upstream_calls
            upstream_calls+=1
            assert upstream_calls<=2
            if upstream_calls==1:return {"type":"http.request","body":b"body","more_body":False}
            await blocked.wait()
            raise AssertionError("unreleased upstream read")
        async def app(scope,receive,send):
            assert (await receive())["body"]==b"body"
            pending=asyncio.create_task(receive())
            await asyncio.sleep(0)
            assert upstream_calls==2
            assert not pending.done()  # Old implementation returns another empty body immediately.
            pending.cancel()
            result=await asyncio.gather(pending,return_exceptions=True)
            assert isinstance(result[0],asyncio.CancelledError)
        await RequestGuardMiddleware(app,100)(SCOPE,receive,None)
    asyncio.run(scenario())


def test_asgi24_send_error_reaches_streaming_disconnect_contract():
    from starlette.responses import StreamingResponse
    from starlette.requests import ClientDisconnect
    import pytest
    async def scenario():
        calls=0
        async def receive():
            nonlocal calls
            calls+=1
            assert calls==1
            return {"type":"http.request","body":b"request","more_body":False}
        async def chunks():yield b"event: data\n\n"
        async def app(scope,receive,send):await StreamingResponse(chunks(),media_type="text/event-stream")(scope,receive,send)
        async def send(message):
            if message["type"]=="http.response.body":raise OSError("synthetic disconnected peer")
        with pytest.raises(ClientDisconnect):
            await RequestGuardMiddleware(app,100)({**SCOPE,"asgi":{"version":"3.0","spec_version":"2.4"}},receive,send)
        assert calls==1  # ASGI 2.4 handles send errors; it must not launch a receive busy loop.
    asyncio.run(scenario())
