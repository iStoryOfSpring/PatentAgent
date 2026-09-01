"""Trace context, request limits and secret-safe JSON request logging."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
from typing import Any
from uuid import uuid4

from starlette.responses import JSONResponse


trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
container_var: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "app_container", default=None,
)
_SAFE_TRACE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def current_trace_id() -> str:
    return trace_id_var.get() or f"trace_{uuid4().hex}"


def current_container() -> Any | None:
    return container_var.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "") or trace_id_var.get(),
        }
        for name in ("method", "path", "status_code", "elapsed_ms", "task_id", "turn_id"):
            value = getattr(record, name, None)
            if value not in (None, ""):
                payload[name] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Configure PatentAgent loggers without changing third-party logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("patentagent")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


class RequestGuardMiddleware:
    def __init__(
        self, app, max_request_bytes: int,
        streaming_path_limits: dict[str, int] | None = None,
    ):
        self.app = app
        self.max_request_bytes = max_request_bytes
        self.streaming_path_limits = streaming_path_limits or {}

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        path = scope.get("path", "")
        streaming_limit = self.streaming_path_limits.get(path)
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                too_large = int(raw_length) > (streaming_limit or self.max_request_bytes)
            except ValueError:
                too_large = True
            if too_large:
                await self._reject(scope, receive, send)
                return

        # Upload handlers consume UploadFile streams and enforce per-file and
        # aggregate byte limits. Do not buffer those bodies in middleware.
        if streaming_limit is not None:
            await self.app(scope, receive, send)
            return

        buffered: list[dict] = []
        body_size = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") == "http.disconnect":
                break
            body_size += len(message.get("body", b""))
            if body_size > self.max_request_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if buffered:
                return buffered.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope, receive, send) -> None:
        response = JSONResponse(
            {"detail": "请求体超过允许大小", "code": "request_too_large"},
            status_code=413,
        )
        await response(scope, receive, send)


class TraceMiddleware:
    def __init__(self, app, logger: logging.Logger | None = None):
        self.app = app
        self.logger = logger or logging.getLogger("patentagent.request")

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        requested = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        trace_id = requested if _SAFE_TRACE.fullmatch(requested) else f"trace_{uuid4().hex}"
        token = trace_id_var.set(trace_id)
        container = getattr(scope.get("app"), "state", None)
        container_token = container_var.set(getattr(container, "container", None))
        started = time.perf_counter()
        status_code = 500

        async def send_with_trace(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status", 500)
                headers_out = list(message.get("headers", []))
                headers_out.append((b"x-request-id", trace_id.encode("ascii")))
                message["headers"] = headers_out
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            self.logger.info(
                "request.completed",
                extra={
                    "trace_id": trace_id,
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status_code": status_code,
                    "elapsed_ms": elapsed,
                },
            )
            trace_id_var.reset(token)
            container_var.reset(container_token)
