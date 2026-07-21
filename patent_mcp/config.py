"""MCP server configuration — environment variables → typed dataclass."""

import os
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    input_dir: str = "./my_patents"
    store_cache_ttl: int = 300
    log_level: str = "INFO"
    http_port: int = 8000
    http_host: str = "127.0.0.1"
    auth_token: str = ""
    max_items_in_result: int = 50

    @classmethod
    def from_env(cls) -> "MCPServerConfig":
        return cls(
            input_dir=os.getenv("MCP_INPUT_DIR", "./my_patents"),
            store_cache_ttl=int(os.getenv("MCP_STORE_CACHE_TTL", "300")),
            log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
            http_port=int(os.getenv("MCP_HTTP_PORT", "8000")),
            http_host=os.getenv("MCP_HTTP_HOST", "127.0.0.1"),
            auth_token=os.getenv("MCP_AUTH_TOKEN", ""),
            max_items_in_result=int(os.getenv("MCP_MAX_ITEMS_IN_RESULT", "50")),
        )
