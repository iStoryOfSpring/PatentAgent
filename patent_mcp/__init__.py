"""patent_mcp/ — MCP (Model Context Protocol) server for PatentAgent.

Exposes all 15 PatentAgent analysis tools as MCP tools, accessible by
MCP-compatible clients such as Claude Code, VS Code, and Cursor.

Transport modes:
  - stdio:  python mcp_server.py
  - HTTP:   python mcp_http_server.py

Environment variables:
  MCP_INPUT_DIR         — patent data directory (default: ./my_patents)
  MCP_STORE_CACHE_TTL   — seconds before re-reading from disk (default: 300)
  MCP_LOG_LEVEL         — logging level (default: INFO)
  MCP_HTTP_PORT         — HTTP server port (default: 8000)
  MCP_HTTP_HOST         — HTTP server host (default: 127.0.0.1)
  MCP_MAX_ITEMS_IN_RESULT — max items in JSON result (default: 50)
"""

from patent_mcp.config import MCPServerConfig
from patent_mcp.data_loader import MCPDataStoreManager
from patent_mcp.adapters import tool_to_mcp_tool, result_to_mcp_content, coerce_args
from patent_mcp.server import create_server, run_stdio, run_http

__all__ = [
    "MCPServerConfig",
    "MCPDataStoreManager",
    "tool_to_mcp_tool",
    "result_to_mcp_content",
    "coerce_args",
    "create_server",
    "run_stdio",
    "run_http",
]
