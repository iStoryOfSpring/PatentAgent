"""PatentDataStore singleton with lazy loading and TTL-based cache for MCP server.

Wraps PatentMiner + PatentDataStore. The first tool call triggers data loading
from disk. Subsequent calls within store_cache_ttl use the cached store.

CRITICAL: PatentMiner.batch_process() prints progress to stdout. Since MCP
stdio transport uses stdout for JSON-RPC, we must temporarily redirect stdout
to stderr during data loading to avoid corrupting the transport.
"""

import asyncio
import contextlib
import io
import logging
import os
import sys
import time

from storage.datastore import PatentDataStore

logger = logging.getLogger("patentagent.mcp.data_loader")


class MCPDataStoreManager:
    def __init__(self, config):
        self._config = config
        self._store: PatentDataStore | None = None
        self._loaded_at: float | None = None

    async def get_store(self) -> PatentDataStore:
        now = time.monotonic()
        if self._store is not None and self._loaded_at is not None:
            if now - self._loaded_at < self._config.store_cache_ttl:
                return self._store
            logger.info("Store cache TTL expired, reloading from disk")

        self._store = await self._load_from_disk(self._config.input_dir)
        self._loaded_at = time.monotonic()
        return self._store

    def invalidate(self) -> None:
        logger.info("Store cache invalidated")
        self._store = None
        self._loaded_at = None

    async def _load_from_disk(self, input_dir: str) -> PatentDataStore:
        logger.info("Loading patent data from: %s", input_dir)

        if not os.path.isdir(input_dir):
            logger.warning("Input directory does not exist: %s", input_dir)
            return PatentDataStore()

        # REST 与 MCP 共用同一 WoSAdapter、缓存版本和 DataFrame 契约。
        from engine.adapters.wos_adapter import WoSAdapter
        adapter = WoSAdapter()

        # batch_process() prints progress to stdout. In MCP stdio mode,
        # stdout is the JSON-RPC transport — print() output would corrupt
        # the protocol stream. Redirect stdout to stderr while loading.
        try:
            with _redirect_stdout_to_stderr():
                df = await asyncio.to_thread(adapter.batch_parse, input_dir)
        except Exception as exc:
            logger.error("Failed to load patent data: %s", exc)
            return PatentDataStore()

        if df is None or df.empty:
            logger.warning("No patent data found in %s", input_dir)
            return PatentDataStore()

        store = PatentDataStore()
        store.load_dataframe(df)
        store._adapter_name = adapter.name
        logger.info("Loaded %d patents from %s", len(df), input_dir)
        return store


@contextlib.contextmanager
def _redirect_stdout_to_stderr():
    """Temporarily redirect sys.stdout to sys.stderr.

    Used to prevent PatentMiner.batch_process() print() calls from
    corrupting the MCP stdio JSON-RPC transport.
    """
    old_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr
        yield
    finally:
        sys.stdout = old_stdout
