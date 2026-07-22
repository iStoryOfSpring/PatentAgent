"""Small use-case boundaries used by HTTP and MCP transports."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Callable

from engine.adapters.base import PatentAdapter
from engine.adapters.importer import PatentDatasetImporter
from patent_agent.domain import ImportReport, SourceFormat
from storage.datastore import PatentDataStore


class DatasetService:
    def __init__(self, loader: Callable[[str], Any]):
        self._loader = loader

    def load(self, input_dir: str):
        return self._loader(input_dir)


class DatasetImportService:
    """Import official files into the one DatasetView used by all tools."""

    def __init__(self, importer: PatentDatasetImporter | None = None):
        self._importer = importer or PatentDatasetImporter()

    def load(self, input_dir: str, source_format: SourceFormat = "auto") -> PatentDataStore:
        records, report, _manifest = self._importer.import_directory(input_dir, source_format)
        frame = PatentAdapter._patents_to_dataframe(records)
        store = PatentDataStore(source_dir=input_dir)
        if not frame.empty:
            store.load_dataframe(frame)
        store._adapter_name = (
            report.source_formats[0] if len(report.source_formats) == 1 else
            "multi_source" if report.source_formats else "unknown"
        )
        store._import_report = report.model_dump(mode="json")
        return store


class DatasetCatalog:
    def summary(self, store: PatentDataStore) -> dict[str, Any]:
        summary = store.get_summary()
        return {
            "total_patents": summary.total_patents,
            "year_range": list(summary.year_range),
            "ipc_sections": summary.ipc_sections,
            "top_applicants": [
                {"name": name, "count": count}
                for name, count in summary.top_applicants
            ],
            "dataset_snapshot": store.snapshot().model_dump(mode="json"),
            **store.audit(),
        }


class ToolExecutionService:
    async def run_tool(self, tool: Any, dataset: Any, params: dict[str, Any]):
        return await tool.run(dataset, **params)


class AnalysisService(ToolExecutionService):
    """Backward-compatible name for embedded callers."""


class ReportService:
    def __init__(self, generator_factory: Callable[[], Any]):
        self._generator_factory = generator_factory

    def export_html(self, title: str, messages: list[dict[str, Any]]) -> str:
        generator = self._generator_factory()
        for message in messages:
            if message.get("content"):
                generator.add_section(message.get("role", "assistant"), message["content"])
        return generator.generate_html(title=title)


class SearchIndexService:
    """Own deterministic, dataset-versioned local search-index paths."""

    INDEX_VERSION = "multilingual-rrf-v1"

    def __init__(self, cache_root: str | Path | None = None):
        default = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        self.cache_root = Path(cache_root or default / "patentagent" / "search_indexes")

    def key(self, dataset_hash: str, model_id: str) -> str:
        payload = json.dumps(
            [dataset_hash, model_id, self.INDEX_VERSION], separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def directory(self, dataset_hash: str, model_id: str) -> Path:
        return self.cache_root / self.key(dataset_hash, model_id)

    def status(self, model_id: str) -> dict[str, Any]:
        model_slug = "models--" + model_id.replace("/", "--")
        hf_root = Path(os.environ.get(
            "HF_HOME", Path.home() / ".cache" / "huggingface",
        ))
        model_root = hf_root / "hub" / model_slug
        snapshots = model_root / "snapshots"
        cached = snapshots.is_dir() and any(snapshots.iterdir())
        indexes = self.cache_root
        return {
            "model_id": model_id,
            "dependency_installed": importlib.util.find_spec("sentence_transformers") is not None,
            "model_cached": cached,
            "model_cache_directory": str(model_root),
            "index_cache_directory": str(indexes),
            "index_count": sum(1 for item in indexes.iterdir() if item.is_dir()) if indexes.is_dir() else 0,
            "download_size_mb": 471,
            "modes": ["lexical", "multilingual_hybrid_beta"],
        }
