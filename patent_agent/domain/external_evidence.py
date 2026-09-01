"""Traceable non-patent evidence records; never synthesized from model memory."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ExternalEvidenceRecord(BaseModel):
    evidence_id: str
    evidence_type: str
    title: str
    source_name: str
    source_uri: str
    published_at: str | None = None
    observed_at: str
    entities: list[str] = Field(default_factory=list)
    text_excerpt: str
    content_hash: str
    license_note: str = ""

    @field_validator("evidence_id", "evidence_type", "title", "source_name", "observed_at", "content_hash")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("外部证据标识、类型、标题、来源、观测时间和内容哈希不能为空")
        return str(value).strip()

    @field_validator("entities", mode="before")
    @classmethod
    def _normalized_entities(cls, value):
        return sorted({str(item).strip() for item in (value or []) if str(item).strip()})
