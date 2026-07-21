"""Versioned dataset contracts independent of a concrete dataframe backend."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class DatasetSnapshot(BaseModel):
    """Immutable identity and quality summary for one loaded dataset version."""

    schema_version: int = 1
    dataset_id: str
    version_id: str
    content_hash: str
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
