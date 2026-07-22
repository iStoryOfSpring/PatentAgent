"""HTTP request models shared by route modules."""

from pydantic import BaseModel, Field

from models.provider_profile import ProviderCredentials
from patent_agent.domain import SourceFormat


class LoadRequest(BaseModel):
    input_dir: str = "./my_patents"
    source_format: SourceFormat = "auto"


class ToolRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    session_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    response_mode: str = "detailed"
    reply_to_turn_id: str | None = None


class SessionCreateRequest(BaseModel):
    name: str = "新会话"


class SessionRenameRequest(BaseModel):
    name: str


class ResynthesizeRequest(BaseModel):
    response_mode: str = "detailed"


class ExportRequest(BaseModel):
    messages: list[dict]
    title: str = "PatentAgent Report"
    session_id: str | None = None
    turn_id: str | None = None


class LLMConfigRequest(BaseModel):
    provider: str = "Claude"
    api_key: str = ""
    base_url: str = ""
    model: str | None = None


class ProviderSecretRequest(ProviderCredentials):
    pass
