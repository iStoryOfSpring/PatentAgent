"""Persistent Agent-task use cases independent of FastAPI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class TaskNotFoundError(KeyError):
    pass


class TaskStateError(RuntimeError):
    pass


class TaskService:
    TERMINAL = {"completed", "partial", "failed", "cancelled", "interrupted"}
    RESUMABLE = {"interrupted", "partial", "failed"}

    def __init__(
        self, repository: Any,
        resynthesize: Callable[..., Awaitable[dict]] | None = None,
    ):
        self.repository = repository
        self._resynthesize = resynthesize

    async def get(self, turn_id: str) -> dict:
        task = await self.repository.get_turn(turn_id)
        if not task:
            raise TaskNotFoundError(turn_id)
        return task

    async def events_after(self, turn_id: str, cursor: int) -> list[dict]:
        await self.get(turn_id)
        return await self.repository.list_task_events(turn_id, cursor)

    async def cancel(self, turn_id: str) -> dict:
        try:
            return await self.repository.request_cancel(turn_id)
        except KeyError as exc:
            raise TaskNotFoundError(turn_id) from exc

    async def resume(self, turn_id: str, request: Any) -> dict:
        task = await self.get(turn_id)
        if task.get("status") not in self.RESUMABLE:
            raise TaskStateError("只有中断、部分完成或失败的任务可以恢复")
        if self._resynthesize is None:
            raise TaskStateError("任务恢复处理器尚未初始化")
        await self.repository.update_turn(turn_id, cancel_requested=0)
        return await self._resynthesize(task["session_id"], turn_id, request)
