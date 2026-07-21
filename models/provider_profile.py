"""Validated, non-secret configuration for an LLM provider profile."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from patent_agent.security.provider_urls import validate_provider_url_syntax


ProviderProtocol = Literal["openai_chat", "anthropic_messages", "deepseek_chat"]
AuthMode = Literal["bearer", "x_api_key", "custom_header", "none"]
ReasoningEffort = Literal["default", "low", "medium", "high", "max"]
ThinkingMode = Literal["auto", "enabled", "disabled"]
ProbeStatus = Literal["not_tested", "passed", "failed"]

RESERVED_EXTRA_BODY_FIELDS = {
    "model", "messages", "tools", "tool_choice", "response_format",
    "max_tokens", "max_completion_tokens", "stream",
}

FORBIDDEN_EXTRA_HEADER_NAMES = {
    "connection", "content-length", "content-type", "host",
    "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade",
}


def _validate_http_url(value: str, *, website: bool = False) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("必须是有效的 HTTP/HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("URL 不得包含用户名或密码")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("URL 端口无效") from exc
    if not website and (parsed.query or parsed.fragment):
        raise ValueError("请求地址不得包含 query 或 fragment")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if not website and parsed.scheme != "https" and parsed.hostname not in local_hosts:
        raise ValueError("远程请求地址必须使用 HTTPS；仅本机地址允许 HTTP")
    if not website:
        validate_provider_url_syntax(value)
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


class ProviderHeader(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(default="", max_length=4096)
    sensitive: bool = False
    credential_loaded: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ch in value for ch in "\r\n:"):
            raise ValueError("Header 名称无效")
        if value.lower() in FORBIDDEN_EXTRA_HEADER_NAMES:
            raise ValueError(f"Header {value} 由 HTTP 客户端管理，不能在 Extra Headers 中设置")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if any(ch in value for ch in "\r\n"):
            raise ValueError("Header 值不得包含换行符")
        return value


class ProviderProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: ProviderProtocol = "openai_chat"
    notes: str = Field(default="", max_length=1000)
    website_url: str = ""
    base_url: str = ""
    model: str = Field(default="", max_length=200)
    selected: bool = False

    auth_mode: AuthMode = "bearer"
    auth_header_name: str = Field(default="Authorization", max_length=128)
    auth_prefix: str = Field(default="Bearer ", max_length=64)

    timeout_seconds: int = Field(default=60, ge=5, le=300)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_output_tokens: int = Field(default=8192, ge=256, le=32768)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning_effort: ReasoningEffort = "default"
    thinking_mode: ThinkingMode = "auto"
    model_discovery_path: str = Field(default="/models", max_length=300)
    extra_headers: list[ProviderHeader] = Field(default_factory=list)
    extra_body: dict = Field(default_factory=dict)

    @field_validator("name", "notes", "model", "auth_header_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("auth_prefix")
    @classmethod
    def validate_auth_prefix(cls, value: str) -> str:
        if any(ch in value for ch in "\r\n"):
            raise ValueError("鉴权前缀不得包含换行符")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, value: str) -> str:
        return _validate_http_url(value, website=True)

    @field_validator("model_discovery_path")
    @classmethod
    def validate_discovery_path(cls, value: str) -> str:
        value = value.strip() or "/models"
        if "?" in value or "#" in value:
            raise ValueError("模型发现路径不得包含 query 或 fragment")
        if not value.startswith("/"):
            value = "/" + value
        return value

    @field_validator("extra_body")
    @classmethod
    def validate_extra_body(cls, value: dict) -> dict:
        conflicts = sorted(RESERVED_EXTRA_BODY_FIELDS.intersection(value))
        if conflicts:
            raise ValueError("Extra Body 不得覆盖保留字段: " + ", ".join(conflicts))
        return value

    @model_validator(mode="after")
    def validate_profile(self):
        if self.auth_mode == "custom_header" and not self.auth_header_name:
            raise ValueError("自定义鉴权必须填写 Header 名称")
        names = [header.name.lower() for header in self.extra_headers]
        if len(names) != len(set(names)):
            raise ValueError("Extra Headers 名称不得重复")
        if self.auth_mode != "none" and self.auth_header_name.lower() in names:
            raise ValueError("Extra Headers 不得重复设置鉴权 Header")
        if self.protocol != "deepseek_chat" and self.thinking_mode != "auto":
            raise ValueError("Thinking mode 仅适用于 DeepSeek 协议")
        return self


class ProviderProfileCreate(ProviderProfileBase):
    id: str | None = None


class ProviderProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    protocol: ProviderProtocol | None = None
    notes: str | None = Field(default=None, max_length=1000)
    website_url: str | None = None
    base_url: str | None = None
    model: str | None = Field(default=None, max_length=200)
    selected: bool | None = None
    auth_mode: AuthMode | None = None
    auth_header_name: str | None = Field(default=None, max_length=128)
    auth_prefix: str | None = Field(default=None, max_length=64)
    timeout_seconds: int | None = Field(default=None, ge=5, le=300)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    max_output_tokens: int | None = Field(default=None, ge=256, le=32768)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning_effort: ReasoningEffort | None = None
    thinking_mode: ThinkingMode | None = None
    model_discovery_path: str | None = Field(default=None, max_length=300)
    extra_headers: list[ProviderHeader] | None = None
    extra_body: dict | None = None


class ProviderProfile(ProviderProfileBase):
    id: str
    schema_version: int = 1
    credential_loaded: bool = False
    connected: bool = False
    needs_reconnect: bool = False
    probe_status: ProbeStatus = "not_tested"
    probe_error_category: str = ""
    last_probe_at: str = ""
    created_at: str = ""
    updated_at: str = ""


class ProviderCredentials(BaseModel):
    api_key: str = Field(default="", max_length=8192)
    sensitive_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if any(ch in value for ch in "\r\n"):
            raise ValueError("API Key 不得包含换行符")
        return value

    @field_validator("sensitive_headers")
    @classmethod
    def validate_sensitive_headers(cls, value: dict[str, str]) -> dict[str, str]:
        for key, secret in value.items():
            if not key.strip() or any(ch in key for ch in "\r\n:"):
                raise ValueError("敏感 Header 名称无效")
            if len(secret) > 8192:
                raise ValueError("敏感 Header 值过长")
            if any(ch in secret for ch in "\r\n"):
                raise ValueError("敏感 Header 值不得包含换行符")
        return {key.strip(): secret for key, secret in value.items()}
