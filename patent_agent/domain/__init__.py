"""Stable domain contracts shared by REST, Agent and MCP transports."""

from .datasets import DatasetSnapshot, DatasetView
from .imports import (
    FileDetection, ImportFile, ImportIssue, ImportManifest, ImportReport, SourceCapabilities,
    SourceFormat,
)
from .tasks import ErrorCategory, ErrorInfo, TaskState
from .tools import ExecutionMetrics, ToolDefinition, ToolExecutionEnvelope, ToolProvenance

__all__ = [
    "DatasetSnapshot", "DatasetView", "FileDetection", "ImportFile", "ImportIssue",
    "ImportManifest", "ImportReport", "SourceCapabilities", "SourceFormat",
    "ErrorCategory", "ErrorInfo",
    "ExecutionMetrics", "TaskState", "ToolDefinition",
    "ToolExecutionEnvelope", "ToolProvenance",
]
