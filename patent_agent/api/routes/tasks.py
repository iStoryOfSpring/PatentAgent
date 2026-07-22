"""Task status, replay, cancellation and evidence-only resume routes."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import ResynthesizeRequest
from patent_agent.application.tasks import TaskNotFoundError, TaskService, TaskStateError
from patent_agent.infrastructure import AppContainer
from patent_agent.infrastructure.observability import current_trace_id


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _service(container: AppContainer) -> TaskService:
    if container.task_service is None:
        raise HTTPException(503, "任务服务尚未初始化")
    return container.task_service


@router.get("/{turn_id}")
async def get_task(turn_id: str, container: AppContainer = Depends(get_container)):
    try:
        task = await _service(container).get(turn_id)
    except TaskNotFoundError as exc:
        raise HTTPException(404, "任务不存在") from exc
    return {"task": task, "trace_id": current_trace_id()}


@router.get("/{turn_id}/events")
async def get_task_events(
    turn_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    container: AppContainer = Depends(get_container),
):
    service = _service(container)
    try:
        await service.get(turn_id)
        after_id = max(0, int(last_event_id or 0))
    except TaskNotFoundError as exc:
        raise HTTPException(404, "任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(422, "Last-Event-ID 必须是整数") from exc

    async def replay():
        cursor = after_id
        while True:
            for stored in await service.events_after(turn_id, cursor):
                cursor = int(stored["id"])
                yield _sse(stored.get("payload", {}), cursor)
            current = await service.get(turn_id)
            if current.get("status") in service.TERMINAL:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        replay(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{turn_id}/cancel")
async def cancel_task(turn_id: str, container: AppContainer = Depends(get_container)):
    try:
        task = await _service(container).cancel(turn_id)
    except TaskNotFoundError as exc:
        raise HTTPException(404, "任务不存在") from exc
    return {"task": task, "trace_id": current_trace_id()}


@router.post("/{turn_id}/resume")
async def resume_task(
    turn_id: str, request: ResynthesizeRequest = ResynthesizeRequest(),
    container: AppContainer = Depends(get_container),
):
    try:
        return await _service(container).resume(turn_id, request)
    except TaskNotFoundError as exc:
        raise HTTPException(404, "任务不存在") from exc
    except TaskStateError as exc:
        raise HTTPException(409, str(exc)) from exc


def _sse(data: dict, event_id: int) -> str:
    payload = dict(data)
    payload.setdefault("trace_id", current_trace_id())
    return f"id: {event_id}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
