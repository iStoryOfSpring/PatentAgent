"""SSRF-resistant validation for model-service connection targets."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}


def _allowed_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_loopback or address.is_global


def validate_provider_url_syntax(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("请求地址缺少主机名")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if not _allowed_address(address):
        raise ValueError("请求地址不得指向私网、链路本地或特殊用途地址")
    return host


async def assert_safe_provider_target(value: str) -> None:
    """Resolve a provider host immediately before network access.

    Loopback remains available for local Ollama/vLLM. Every resolved address of
    any other hostname must be globally routable; mixed public/private DNS is
    rejected rather than selecting the public answer.
    """

    parsed = urlsplit(value)
    host = validate_provider_url_syntax(value)
    if host in _LOOPBACK_NAMES:
        return
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        answers = await asyncio.to_thread(
            socket.getaddrinfo, host, port, type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("模型服务主机无法解析") from exc
    addresses = {
        ipaddress.ip_address(answer[4][0])
        for answer in answers
    }
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("模型服务主机解析到了私网、链路本地或特殊用途地址")
