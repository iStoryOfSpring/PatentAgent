"""Bounded runtime loading for versioned local patent datasets."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from patent_agent.application.services import DatasetImportService
from storage.datastore import PatentDataStore


class DatasetRuntimeManager:
    """Resolve a session's immutable dataset version with a small LRU cache."""

    def __init__(self, repository: Any, importer: DatasetImportService, capacity: int = 1):
        self.repository = repository
        self.importer = importer
        self.capacity = max(1, capacity)
        self._stores: OrderedDict[str, PatentDataStore] = OrderedDict()

    def register(self, store: PatentDataStore) -> PatentDataStore:
        version_id = store.snapshot().version_id
        self._stores[version_id] = store
        self._stores.move_to_end(version_id)
        while len(self._stores) > self.capacity:
            self._stores.popitem(last=False)
        return store

    async def get(self, version_id: str) -> PatentDataStore:
        if version_id in self._stores:
            store = self._stores[version_id]
            self._stores.move_to_end(version_id)
            return store
        record = await self.repository.get_dataset_version(version_id)
        if not record:
            raise KeyError(version_id)
        source = record.get("storage_path") or record.get("source_root")
        if not source:
            sources = record.get("sources") or []
            source = sources[0] if sources else ""
        if not source:
            raise ValueError("数据集版本没有可读取的存储路径")
        adapter = record.get("adapter") or "auto"
        if adapter not in {
            "auto", "wos_dii", "google_patents_jsonl", "uspto_grant_xml",
            "uspto_file_wrapper_json",
        }:
            adapter = "auto"
        store = self.importer.load(source, adapter)
        store._dataset_id_override = record["dataset_id"]
        store._version_id_override = record["id"]
        return self.register(store)

    async def for_session(
        self, session_id: str | None, fallback: PatentDataStore | None,
    ) -> PatentDataStore | None:
        if not session_id:
            return fallback
        session = await self.repository.get_session(session_id, required=False)
        if not session or not session.get("dataset_version_id"):
            return fallback
        return await self.get(session["dataset_version_id"])
