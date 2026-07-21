"""Persistent task states and transport-neutral error categories."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    VALIDATING = "validating"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ErrorCategory(str, Enum):
    DATA_INSUFFICIENT = "data_insufficient"
    INPUT_VALIDATION = "input_validation"
    ALGORITHM = "algorithm_failure"
    PROVIDER = "provider_failure"
    SYNTHESIS = "synthesis_failure"
    SYSTEM = "system_failure"


class ErrorInfo(BaseModel):
    category: ErrorCategory
    code: str
    message: str
    recoverable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
