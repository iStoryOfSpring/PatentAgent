"""Typed environment configuration with local-only defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    data_root: Path
    input_dir: str
    session_db: Path
    cors_origins: tuple[str, ...]
    max_request_bytes: int = 2 * 1024 * 1024
    max_upload_file_bytes: int = 256 * 1024 * 1024
    max_upload_total_bytes: int = 512 * 1024 * 1024
    dataset_cache_size: int = 1
    max_agent_concurrency: int = 1
    max_tool_concurrency: int = 4
    max_tool_queue_wait_seconds: float = 30.0

    @classmethod
    def from_env(cls, project_root: str | Path) -> "AppSettings":
        root = Path(project_root).resolve()
        data_root = Path(os.getenv("PATENT_DATA_ROOT", root / "my_patents")).expanduser().resolve()
        session_db = Path(os.getenv(
            "PATENTAGENT_SESSION_DB", root / ".patentagent" / "sessions.db",
        )).expanduser().resolve()
        origins = tuple(
            value.strip() for value in os.getenv(
                "PATENTAGENT_CORS_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(",") if value.strip()
        )
        return cls(
            project_root=root,
            data_root=data_root,
            input_dir=os.getenv("MCP_INPUT_DIR", "./my_patents"),
            session_db=session_db,
            cors_origins=origins,
            max_request_bytes=int(os.getenv("PATENTAGENT_MAX_REQUEST_BYTES", str(2 * 1024 * 1024))),
            max_upload_file_bytes=int(os.getenv(
                "PATENTAGENT_MAX_UPLOAD_FILE_BYTES", str(256 * 1024 * 1024),
            )),
            max_upload_total_bytes=int(os.getenv(
                "PATENTAGENT_MAX_UPLOAD_TOTAL_BYTES", str(512 * 1024 * 1024),
            )),
            dataset_cache_size=max(1, int(os.getenv("PATENTAGENT_DATASET_CACHE_SIZE", "1"))),
            max_agent_concurrency=max(1, int(os.getenv("PATENTAGENT_MAX_AGENT_CONCURRENCY", "1"))),
            max_tool_concurrency=max(1, int(os.getenv("PATENTAGENT_MAX_TOOL_CONCURRENCY", "4"))),
            max_tool_queue_wait_seconds=max(
                0.1, float(os.getenv("PATENTAGENT_MAX_TOOL_QUEUE_WAIT_SECONDS", "30")),
            ),
        )
