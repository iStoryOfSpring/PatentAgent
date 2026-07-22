"""Persistent conversation CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import SessionCreateRequest, SessionRenameRequest
from patent_agent.application import ConversationService
from patent_agent.infrastructure import AppContainer


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _service(container: AppContainer) -> ConversationService:
    if container.conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    if (
        container.conversation_service is None or
        container.conversation_service.repository is not container.conversation_store
    ):
        container.conversation_service = ConversationService(container.conversation_store)
    return container.conversation_service


def _fingerprint(container: AppContainer) -> str:
    return container.store.dataset_fingerprint() if container.store else "empty"


@router.post("")
async def create_session(req: SessionCreateRequest = SessionCreateRequest(), container: AppContainer = Depends(get_container)):
    return await _service(container).create(req.name, _fingerprint(container))


@router.get("")
async def list_sessions(container: AppContainer = Depends(get_container)):
    return {"sessions": await _service(container).list()}


@router.get("/{session_id}")
async def get_session(session_id: str, container: AppContainer = Depends(get_container)):
    try:
        return await _service(container).get(session_id, _fingerprint(container))
    except KeyError as exc:
        raise HTTPException(404, "会话不存在") from exc


@router.patch("/{session_id}")
async def rename_session(session_id: str, req: SessionRenameRequest, container: AppContainer = Depends(get_container)):
    try:
        return await _service(container).rename(session_id, req.name)
    except KeyError as exc:
        raise HTTPException(404, "会话不存在") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/{session_id}")
async def delete_session(session_id: str, container: AppContainer = Depends(get_container)):
    try:
        await _service(container).delete(session_id)
    except KeyError as exc:
        raise HTTPException(404, "会话不存在") from exc
    container.sessions.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}
