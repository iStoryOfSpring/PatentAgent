#!/usr/bin/env python3
"""MCP HTTP server entry point for PatentAgent.

Usage:
    python mcp_http_server.py [--port PORT] [--host HOST]

Environment:
    MCP_INPUT_DIR: patent data directory (default ./my_patents)
    MCP_HTTP_PORT: HTTP port (default 8000)
    MCP_HTTP_HOST: HTTP host (default 127.0.0.1)
    MCP_LOG_LEVEL: logging level (default INFO)
"""

import argparse
import asyncio
import os
import sys

_package_root = os.path.dirname(os.path.abspath(__file__))
if _package_root not in sys.path:
    sys.path.insert(0, _package_root)

from patent_mcp.config import MCPServerConfig
from patent_mcp.server import run_http
from patent_mcp.server import logger as server_logger


def main():
    parser = argparse.ArgumentParser(description="PatentAgent MCP HTTP Server")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default: 8000)")
    parser.add_argument("--host", default=None, help="HTTP host (default: 127.0.0.1)")
    args = parser.parse_args()

    config = MCPServerConfig.from_env()
    if args.port is not None:
        config.http_port = args.port
    if args.host is not None:
        config.http_host = args.host

    server_logger.setLevel(config.log_level.upper())
    asyncio.run(run_http(config))


if __name__ == "__main__":
    main()
