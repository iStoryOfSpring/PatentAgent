"""Contracts for file-first, traceable patent imports."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SourceFormat = Literal[
    "auto", "wos_dii", "google_patents_jsonl", "uspto_grant_xml",
    "uspto_file_wrapper_json",
]


class ImportFile(BaseModel):
    path: str
    source_format: SourceFormat = "auto"
    sha256: str = ""


class ImportManifest(BaseModel):
    schema_version: int = 1
    dataset_id: str = ""
    source_name: str = ""
    source_uri: str = ""
    retrieved_at: str = ""
    data_as_of: str = ""
    license_note: str = ""
    files: list[ImportFile] = Field(default_factory=list)


class SourceCapabilities(BaseModel):
    bibliographic: bool = True
    multilingual_text: bool = False
    claims: bool = False
    description: bool = False
    classifications: bool = False
    citations: bool = False
    family: bool = False
    legal_events: bool = False
    prosecution_events: bool = False
    current_legal_status: bool = False


class ImportIssue(BaseModel):
    file: str = ""
    record_id: str = ""
    code: str
    message: str


class FileDetection(BaseModel):
    file: str
    source_format: SourceFormat
    method: Literal["manifest", "user_selected", "content_signature", "unknown"]
    matched: bool


class ImportReport(BaseModel):
    schema_version: int = 1
    source_formats: list[str] = Field(default_factory=list)
    files_seen: int = 0
    records_parsed: int = 0
    records_imported: int = 0
    records_failed: int = 0
    duplicates_merged: int = 0
    field_conflicts: int = 0
    field_coverage: dict[str, float] = Field(default_factory=dict)
    language_distribution: dict[str, int] = Field(default_factory=dict)
    source_capabilities: dict[str, SourceCapabilities] = Field(default_factory=dict)
    file_detections: list[FileDetection] = Field(default_factory=list)
    issues: list[ImportIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
