"""Stable domain contracts shared by REST, Agent and MCP transports."""

from .datasets import AnalysisScope, DatasetSnapshot, DatasetView
from .external_evidence import ExternalEvidenceRecord
from .imports import (
    FileDetection, ImportFile, ImportIssue, ImportManifest, ImportReport, SourceCapabilities,
    SourceFormat,
)
from .tasks import ErrorCategory, ErrorInfo, TaskState
from .tools import AlgorithmExecution, ExecutionMetrics, ToolDefinition, ToolExecutionEnvelope, ToolProvenance

__all__ = [
    "AnalysisScope", "DatasetSnapshot", "DatasetView", "ExternalEvidenceRecord", "FileDetection", "ImportFile", "ImportIssue",
    "ImportManifest", "ImportReport", "SourceCapabilities", "SourceFormat",
    "ErrorCategory", "ErrorInfo",
    "AlgorithmExecution", "ExecutionMetrics", "TaskState", "ToolDefinition",
    "ToolExecutionEnvelope", "ToolProvenance",
]
