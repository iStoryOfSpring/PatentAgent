#!/usr/bin/env python3
"""MCP stdio server entry point for PatentAgent.

Usage:
    python mcp_server.py
    # or when installed as a package:
    # mcp run mcp_server.py

Environment:
    MCP_INPUT_DIR: patent data directory (default ./my_patents)
    MCP_STORE_CACHE_TTL: cache TTL in seconds (default 300)
    MCP_LOG_LEVEL: logging level (default INFO)
    MCP_MAX_ITEMS_IN_RESULT: max items per result (default 50)
"""

import asyncio
import os
import sys

# Ensure the PatentAgent package root is on sys.path
_package_root = os.path.dirname(os.path.abspath(__file__))
if _package_root not in sys.path:
    sys.path.insert(0, _package_root)

from patent_mcp.config import MCPServerConfig
from patent_mcp.server import run_stdio
from patent_mcp.server import logger as server_logger


def main():
    config = MCPServerConfig.from_env()
    server_logger.setLevel(config.log_level.upper())
    asyncio.run(run_stdio(config))


if __name__ == "__main__":
    main()
