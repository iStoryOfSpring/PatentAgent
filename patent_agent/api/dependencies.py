"""FastAPI dependency accessors for application-owned state."""

from fastapi import Request

from patent_agent.infrastructure import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


async def resolve_dataset(container: AppContainer, session_id: str | None = None):
    """Resolve an explicit session binding without mutating or falling back to global data."""
    from fastapi import HTTPException
    if session_id is None:
        return container.store
    if container.conversation_store is None or container.dataset_runtime is None:
        raise HTTPException(503, "会话或数据集运行时尚未初始化")
    session = await container.conversation_store.get_session(session_id, required=False)
    if session is None:
        raise HTTPException(404, "会话不存在")
    version_id = session.get("dataset_version_id")
    if not version_id:
        return None
    try:
        return await container.dataset_runtime.get(version_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, "requires_reimport: 会话绑定的数据集不可用，需要重新导入或显式绑定有效版本") from exc
