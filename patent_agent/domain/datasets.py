"""Versioned dataset contracts independent of a concrete dataframe backend."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalysisScope(BaseModel):
    """Normalized, transport-neutral population restriction for analysis tools."""

    year_start: int | None = None
    year_end: int | None = None
    ipc_prefixes: list[str] = Field(default_factory=list)
    applicant_names: list[str] = Field(default_factory=list)
    applicant_entity_ids: list[str] = Field(default_factory=list)
    inventor_names: list[str] = Field(default_factory=list)
    inventor_entity_ids: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    patent_numbers: list[str] = Field(default_factory=list)
    text_query: str | None = None
    family_deduplication: Literal["none", "simple", "inpadoc"] = "none"

    @field_validator(
        "ipc_prefixes", "applicant_names", "applicant_entity_ids",
        "inventor_names", "inventor_entity_ids", "jurisdictions",
        "patent_numbers", mode="before",
    )
    @classmethod
    def _normalize_lists(cls, value):
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        return sorted({str(item).strip() for item in items if str(item).strip()})

    @model_validator(mode="after")
    def _valid_range(self):
        if (
            self.year_start is not None and self.year_end is not None
            and self.year_start > self.year_end
        ):
            raise ValueError("scope.year_start 不能晚于 scope.year_end")
        return self

    def canonical(self) -> dict[str, Any]:
        return self.model_dump(exclude_defaults=True, exclude_none=True)


class DatasetSnapshot(BaseModel):
    """Immutable identity and quality summary for one loaded dataset version."""

    schema_version: int = 2
    dataset_id: str
    version_id: str
    content_hash: str
    fingerprint_scheme: str = "patent-content-v2"
    adapter: str
    sources: list[str] = Field(default_factory=list)
    record_count: int = 0
    field_coverage: dict[str, float] = Field(default_factory=dict)
    imported_at: str = ""


@runtime_checkable
class DatasetView(Protocol):
    """Logical data interface consumed by tools during the migration period."""

    @property
    def adapter_name(self) -> str: ...

    def dataset_fingerprint(self) -> str: ...

    def field_coverage(self, field_name: str) -> float: ...

    def audit(self) -> dict[str, Any]: ...

    def query(self, **filters: Any): ...

    def get_columns(self, columns: list[str]): ...

    def get_all(self): ...

    def snapshot(self) -> DatasetSnapshot: ...
