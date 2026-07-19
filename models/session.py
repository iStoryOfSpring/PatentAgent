"""Pydantic 数据模型: Session, ToolExecution"""

from datetime import datetime
from pydantic import BaseModel, Field, SerializeAsAny
from .analysis_results import AnalysisResult


class ToolExecution(BaseModel):
    id: str
    tool_name: str
    parameters: dict
    status: str = "pending"  # 'pending' | 'running' | 'completed' | 'failed'
    result: SerializeAsAny[AnalysisResult] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    retry_count: int = 0
    origin: str = "agent"
    reused_from_execution_id: str | None = None
    provider_tool_call_id: str | None = None


class Session(BaseModel):
    id: str
    name: str
    created_at: datetime
    dataset_id: str
    status: str = "idle"  # 'idle' | 'awaiting_approval' | 'executing' | 'completed' | 'cancelled'
    messages: list[dict] = Field(default_factory=list)
    tool_executions: list[ToolExecution] = Field(default_factory=list)
    analysis_reports: list[str] = Field(default_factory=list)
    pending_plan: dict | None = None
