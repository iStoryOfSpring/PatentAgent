"""Strong tool definition and execution-envelope contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .tasks import ErrorInfo


class ToolDefinition(BaseModel):
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_fields: set[str] = Field(default_factory=set)
    optional_fields: set[str] = Field(default_factory=set)
    estimated_cost: int = 1
    deterministic: bool = True


class ToolProvenance(BaseModel):
    dataset_id: str
    dataset_version_id: str
    dataset_content_hash: str
    adapter: str
    input_record_count: int
    analyzed_record_count: int
    sampled: bool = False
    sample_size: int | None = None
    sampling_method: str = "none"
    field_coverage: dict[str, float] = Field(default_factory=dict)
    algorithm_id: str = ""
    algorithm_version: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecutionMetrics(BaseModel):
    elapsed_ms: float = 0
    cache_hit: bool = False
    retry_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None


class ToolExecutionEnvelope(BaseModel):
    tool: ToolDefinition
    result: dict[str, Any] | list[Any] | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: ToolProvenance
    metrics: ExecutionMetrics
    error: ErrorInfo | None = None
