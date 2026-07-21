"""Stable domain contracts shared by REST, Agent and MCP transports."""

from .datasets import DatasetSnapshot, DatasetView
from .tasks import ErrorCategory, ErrorInfo, TaskState
from .tools import ExecutionMetrics, ToolDefinition, ToolExecutionEnvelope, ToolProvenance

__all__ = [
    "DatasetSnapshot", "DatasetView", "ErrorCategory", "ErrorInfo",
    "ExecutionMetrics", "TaskState", "ToolDefinition",
    "ToolExecutionEnvelope", "ToolProvenance",
]
