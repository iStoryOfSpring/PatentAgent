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

        from patent_agent.application.services import DatasetImportService
        try:
            with _redirect_stdout_to_stderr():
                return await asyncio.to_thread(DatasetImportService().load, input_dir, "auto")
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Failed to load patent data (%s)", type(exc).__name__)
            return PatentDataStore()


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
