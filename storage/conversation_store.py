"""Persistent conversations and evidence snapshots for the web Agent.

The store deliberately excludes API keys and chart HTML.  Structured tool
payloads are the source of truth and can be rendered again by the frontend.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def execution_cache_key(
    dataset_fingerprint: str,
    tool_name: str,
    parameters: dict[str, Any],
    algorithm_version: str = "",
) -> str:
    canonical = json.dumps({
        "dataset": dataset_fingerprint,
        "tool": tool_name,
        "parameters": parameters,
        "algorithm_version": algorithm_version,
    }, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ConversationStore:
    """Small aiosqlite repository with explicit, versioned schema."""

    SCHEMA_VERSION = 4

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    dataset_fingerprint TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'idle',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    origin TEXT NOT NULL DEFAULT 'agent',
                    user_message TEXT NOT NULL DEFAULT '',
                    response_mode TEXT NOT NULL DEFAULT 'detailed',
                    status TEXT NOT NULL DEFAULT 'understanding',
                    intent_json TEXT NOT NULL DEFAULT '{}',
                    plan_json TEXT NOT NULL DEFAULT '{}',
                    final_text TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    pending_question_json TEXT NOT NULL DEFAULT '{}',
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    provider_profile_id TEXT NOT NULL DEFAULT '',
                    provider_name TEXT NOT NULL DEFAULT '',
                    provider_protocol TEXT NOT NULL DEFAULT '',
                    dataset_version_id TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    state_version INTEGER NOT NULL DEFAULT 0,
                    error_category TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    turn_id TEXT REFERENCES turns(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_executions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    tool_name TEXT NOT NULL,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    duration_ms REAL NOT NULL DEFAULT 0,
                    algorithm_version TEXT NOT NULL DEFAULT '',
                    cache_key TEXT NOT NULL DEFAULT '',
                    provider_tool_call_id TEXT NOT NULL DEFAULT '',
                    validation_json TEXT NOT NULL DEFAULT '{}',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL UNIQUE REFERENCES tool_executions(id) ON DELETE CASCADE,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    coverage_json TEXT NOT NULL DEFAULT '{}',
                    stale INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_root TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                    content_hash TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    adapter TEXT NOT NULL DEFAULT '',
                    record_count INTEGER NOT NULL DEFAULT 0,
                    field_coverage_json TEXT NOT NULL DEFAULT '{}',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    UNIQUE(dataset_id, content_hash)
                );
                CREATE TABLE IF NOT EXISTS imports (
                    id TEXT PRIMARY KEY,
                    dataset_version_id TEXT REFERENCES dataset_versions(id) ON DELETE SET NULL,
                    status TEXT NOT NULL,
                    source_path TEXT NOT NULL DEFAULT '',
                    error_category TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    decision TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
                    turn_id TEXT REFERENCES turns(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    format TEXT NOT NULL DEFAULT 'html',
                    content_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
                CREATE INDEX IF NOT EXISTS idx_exec_session ON tool_executions(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_exec_cache ON tool_executions(cache_key);
                CREATE INDEX IF NOT EXISTS idx_task_events_turn ON task_events(turn_id,id);
                """
            )
            # Idempotent migration for databases created before provider-aware
            # tool orchestration was introduced.
            turn_columns = {
                row[1] for row in await db.execute_fetchall("PRAGMA table_info(turns)")
            }
            if "provider" not in turn_columns:
                await db.execute("ALTER TABLE turns ADD COLUMN provider TEXT NOT NULL DEFAULT ''")
            if "model" not in turn_columns:
                await db.execute("ALTER TABLE turns ADD COLUMN model TEXT NOT NULL DEFAULT ''")
            if "provider_profile_id" not in turn_columns:
                await db.execute(
                    "ALTER TABLE turns ADD COLUMN provider_profile_id TEXT NOT NULL DEFAULT ''"
                )
            if "provider_name" not in turn_columns:
                await db.execute(
                    "ALTER TABLE turns ADD COLUMN provider_name TEXT NOT NULL DEFAULT ''"
                )
            if "provider_protocol" not in turn_columns:
                await db.execute(
                    "ALTER TABLE turns ADD COLUMN provider_protocol TEXT NOT NULL DEFAULT ''"
                )
            for column, ddl in {
                "dataset_version_id": "TEXT NOT NULL DEFAULT ''",
                "trace_id": "TEXT NOT NULL DEFAULT ''",
                "state_version": "INTEGER NOT NULL DEFAULT 0",
                "error_category": "TEXT NOT NULL DEFAULT ''",
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if column not in turn_columns:
                    await db.execute(f"ALTER TABLE turns ADD COLUMN {column} {ddl}")
            execution_columns = {
                row[1] for row in await db.execute_fetchall("PRAGMA table_info(tool_executions)")
            }
            if "provider_tool_call_id" not in execution_columns:
                await db.execute(
                    "ALTER TABLE tool_executions ADD COLUMN provider_tool_call_id TEXT NOT NULL DEFAULT ''"
                )
            if "validation_json" not in execution_columns:
                await db.execute(
                    "ALTER TABLE tool_executions ADD COLUMN validation_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "provenance_json" not in execution_columns:
                await db.execute(
                    "ALTER TABLE tool_executions ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "metrics_json" not in execution_columns:
                await db.execute(
                    "ALTER TABLE tool_executions ADD COLUMN metrics_json TEXT NOT NULL DEFAULT '{}'"
                )
            await db.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")
            await db.commit()

    async def create_session(
        self, name: str = "新会话", dataset_fingerprint: str = "",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = session_id or f"session_{uuid4().hex}"
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT OR IGNORE INTO sessions "
                "(id,name,dataset_fingerprint,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (session_id, name.strip() or "新会话", dataset_fingerprint,
                 "idle", now, now),
            )
            await db.commit()
        return await self.get_session(session_id)

    async def ensure_session(
        self, session_id: str, dataset_fingerprint: str,
        name: str = "新会话",
    ) -> dict[str, Any]:
        session = await self.get_session(session_id, required=False)
        if not session:
            return await self.create_session(name, dataset_fingerprint, session_id)
        if session["dataset_fingerprint"] != dataset_fingerprint:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA foreign_keys=ON")
                await db.execute(
                    "UPDATE evidence_snapshots SET stale=1 WHERE execution_id IN "
                    "(SELECT id FROM tool_executions WHERE session_id=?)",
                    (session_id,),
                )
                await db.execute(
                    "UPDATE sessions SET dataset_fingerprint=?,updated_at=? WHERE id=?",
                    (dataset_fingerprint, _now(), session_id),
                )
                await db.commit()
            session = await self.get_session(session_id)
            session["dataset_changed"] = True
        return session

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT s.*, (SELECT COUNT(*) FROM turns t WHERE t.session_id=s.id) AS turn_count "
                "FROM sessions s ORDER BY updated_at DESC"
            )
        return [dict(row) for row in rows]

    async def get_session(
        self, session_id: str, required: bool = True,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
            row = await cursor.fetchone()
        if row is None and required:
            raise KeyError(session_id)
        return dict(row) if row else None

    async def rename_session(self, session_id: str, name: str) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("会话名称不能为空")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE sessions SET name=?,updated_at=? WHERE id=?",
                (name.strip(), _now(), session_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                raise KeyError(session_id)
        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            cursor = await db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            await db.commit()
            if cursor.rowcount == 0:
                raise KeyError(session_id)

    async def start_turn(
        self, session_id: str, user_message: str,
        response_mode: str = "detailed", origin: str = "agent",
        turn_id: str | None = None, provider: str = "", model: str = "",
        provider_profile_id: str = "", provider_name: str = "",
        provider_protocol: str = "",
        dataset_version_id: str = "", trace_id: str = "",
    ) -> str:
        turn_id = turn_id or f"turn_{uuid4().hex}"
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT INTO turns (id,session_id,origin,user_message,response_mode,status,"
                "provider,model,provider_profile_id,provider_name,provider_protocol,"
                "dataset_version_id,trace_id,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (turn_id, session_id, origin, user_message, response_mode,
                 "created", provider, model, provider_profile_id,
                 provider_name, provider_protocol, dataset_version_id, trace_id,
                 now, now),
            )
            if user_message:
                await db.execute(
                    "INSERT INTO messages (session_id,turn_id,role,content,metadata_json,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (session_id, turn_id, "user", user_message, "{}", now),
                )
            await db.execute(
                "UPDATE sessions SET status=?,updated_at=? WHERE id=?",
                ("executing", now, session_id),
            )
            await db.commit()
        return turn_id

    async def update_turn(self, turn_id: str, **values: Any) -> None:
        columns = {
            "status", "intent_json", "plan_json", "final_text", "error",
            "pending_question_json", "provider", "model",
            "provider_profile_id", "provider_name", "provider_protocol",
            "dataset_version_id", "trace_id", "error_category",
            "cancel_requested",
        }
        clean = {key: value for key, value in values.items() if key in columns}
        if not clean:
            return
        for key in ("intent_json", "plan_json", "pending_question_json"):
            if key in clean and not isinstance(clean[key], str):
                clean[key] = _json(clean[key])
        clean["updated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in clean)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE turns SET {assignments},state_version=state_version+1 WHERE id=?",
                (*clean.values(), turn_id),
            )
            await db.commit()

    async def finish_turn(
        self, session_id: str, turn_id: str, final_text: str,
        status: str = "completed", error: str = "",
        metadata: dict[str, Any] | None = None,
        error_category: str = "",
    ) -> None:
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "UPDATE turns SET status=?,final_text=?,error=?,error_category=?,"
                "updated_at=?,state_version=state_version+1 WHERE id=?",
                (status, final_text, error,
                 error_category or ("system_failure" if error else ""), now, turn_id),
            )
            if final_text:
                await db.execute(
                    "DELETE FROM messages WHERE turn_id=? AND role='assistant'",
                    (turn_id,),
                )
                await db.execute(
                    "INSERT INTO messages (session_id,turn_id,role,content,metadata_json,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (session_id, turn_id, "assistant", final_text,
                     _json(metadata or {}), now),
                )
            await db.execute(
                "UPDATE sessions SET status=?,updated_at=? WHERE id=?",
                (status, now, session_id),
            )
            await db.commit()

    async def add_message(
        self, session_id: str, turn_id: str | None, role: str,
        content: str, metadata: dict[str, Any] | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (session_id,turn_id,role,content,metadata_json,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (session_id, turn_id, role, content, _json(metadata or {}), _now()),
            )
            await db.commit()

    async def record_execution(
        self, session_id: str, turn_id: str, execution_id: str,
        tool_name: str, parameters: dict[str, Any], status: str,
        result: dict[str, Any] | None, error: str = "",
        duration_ms: float = 0.0, algorithm_version: str = "",
        dataset_fingerprint: str = "", coverage: dict[str, Any] | None = None,
        provider_tool_call_id: str = "",
        validation: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        cache_key = execution_cache_key(
            dataset_fingerprint, tool_name, parameters, algorithm_version,
        )
        clean_result = dict(result or {})
        clean_result.pop("chart_html", None)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT OR REPLACE INTO tool_executions "
                "(id,session_id,turn_id,tool_name,parameters_json,status,error,duration_ms,"
                "algorithm_version,cache_key,provider_tool_call_id,validation_json,"
                "provenance_json,metrics_json,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (execution_id, session_id, turn_id, tool_name, _json(parameters),
                 status, error, duration_ms, algorithm_version, cache_key,
                 provider_tool_call_id, _json(validation or {}),
                 _json(provenance or {}), _json(metrics or {}), _now()),
            )
            await db.execute(
                "INSERT OR REPLACE INTO evidence_snapshots "
                "(execution_id,result_json,coverage_json,stale,created_at) VALUES (?,?,?,?,?)",
                (execution_id, _json(clean_result), _json(coverage or {}), 0, _now()),
            )
            await db.commit()
        return cache_key

    async def mark_inflight_interrupted(self) -> int:
        """Make process crashes explicit without replaying an LLM request."""
        inflight = (
            "created", "planning", "planned", "running", "executing",
            "validating", "synthesizing",
        )
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ",".join("?" for _ in inflight)
            cursor = await db.execute(
                f"UPDATE turns SET status='interrupted',error_category='system_failure',"
                f"updated_at=?,state_version=state_version+1 WHERE status IN ({placeholders})",
                (_now(), *inflight),
            )
            await db.execute(
                "UPDATE sessions SET status='interrupted',updated_at=? WHERE status IN "
                "('executing','running','planning','synthesizing')",
                (_now(),),
            )
            await db.commit()
            return cursor.rowcount

    async def request_cancel(self, turn_id: str) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE turns SET cancel_requested=1,updated_at=?,"
                "state_version=state_version+1 WHERE id=? AND status NOT IN "
                "('completed','failed','cancelled')",
                (_now(), turn_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                existing = await self.get_turn(turn_id)
                if not existing:
                    raise KeyError(turn_id)
        return await self.get_turn(turn_id)

    async def append_task_event(self, turn_id: str, payload: dict[str, Any]) -> int:
        clean = dict(payload)
        clean.pop("reasoning_content", None)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO task_events(turn_id,event_type,payload_json,created_at) "
                "VALUES(?,?,?,?)",
                (turn_id, str(clean.get("type", "event")), _json(clean), _now()),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_task_events(
        self, turn_id: str, after_id: int = 0, limit: int = 500,
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM task_events WHERE turn_id=? AND id>? "
                "ORDER BY id LIMIT ?",
                (turn_id, after_id, limit),
            )
        return [self._decode_row(row) for row in rows]

    async def list_dataset_versions(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT v.*,d.name,d.source_root FROM dataset_versions v "
                "JOIN datasets d ON d.id=v.dataset_id ORDER BY v.created_at DESC"
            )
        return [self._decode_row(row) for row in rows]

    async def upsert_dataset_snapshot(self, snapshot: dict[str, Any]) -> None:
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT INTO datasets(id,name,source_root,created_at,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name,source_root=excluded.source_root,updated_at=excluded.updated_at",
                (snapshot["dataset_id"], snapshot.get("name") or snapshot["dataset_id"],
                 (snapshot.get("sources") or [""])[0], now, now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO dataset_versions "
                "(id,dataset_id,content_hash,schema_version,adapter,record_count,"
                "field_coverage_json,sources_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (snapshot["version_id"], snapshot["dataset_id"], snapshot["content_hash"],
                 snapshot.get("schema_version", 1), snapshot.get("adapter", ""),
                 snapshot.get("record_count", 0), _json(snapshot.get("field_coverage", {})),
                 _json(snapshot.get("sources", [])), now),
            )
            await db.commit()

    async def record_approval(
        self, turn_id: str, decision: str, payload: dict[str, Any] | None = None,
    ) -> str:
        approval_id = f"approval_{uuid4().hex}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO approvals(id,turn_id,decision,payload_json,created_at) "
                "VALUES(?,?,?,?,?)",
                (approval_id, turn_id, decision, _json(payload or {}), _now()),
            )
            await db.commit()
        return approval_id

    async def save_report(
        self, title: str, content: str, session_id: str | None = None,
        turn_id: str | None = None, report_format: str = "html",
    ) -> str:
        report_id = f"report_{uuid4().hex}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT INTO reports(id,session_id,turn_id,title,format,content_text,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (report_id, session_id, turn_id, title, report_format, content, _now()),
            )
            await db.commit()
        return report_id

    async def get_session_detail(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            messages = await db.execute_fetchall(
                "SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)
            )
            turns = await db.execute_fetchall(
                "SELECT * FROM turns WHERE session_id=? ORDER BY created_at", (session_id,)
            )
            executions = await db.execute_fetchall(
                "SELECT e.*,s.result_json,s.coverage_json,s.stale FROM tool_executions e "
                "LEFT JOIN evidence_snapshots s ON s.execution_id=e.id "
                "WHERE e.session_id=? ORDER BY e.created_at", (session_id,)
            )
        return {
            "session": session,
            "messages": [self._decode_row(row) for row in messages],
            "turns": [self._decode_row(row) for row in turns],
            "tool_executions": [self._decode_row(row) for row in executions],
        }

    async def get_recent_messages(
        self, session_id: str, limit: int = 12,
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT role,content,turn_id,metadata_json,created_at FROM messages WHERE session_id=? "
                "ORDER BY id DESC LIMIT ?", (session_id, limit),
            )
        return [self._decode_row(row) for row in reversed(rows)]

    async def get_evidence(
        self, session_id: str, include_stale: bool = False, limit: int = 30,
    ) -> list[dict[str, Any]]:
        stale_clause = "" if include_stale else "AND s.stale=0"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT e.*,s.result_json,s.coverage_json,s.stale,t.final_text,t.user_message "
                "FROM tool_executions e JOIN evidence_snapshots s ON s.execution_id=e.id "
                "JOIN turns t ON t.id=e.turn_id WHERE e.session_id=? "
                f"{stale_clause} ORDER BY e.created_at DESC LIMIT ?",
                (session_id, limit),
            )
        return [self._decode_row(row) for row in rows]

    async def find_reusable(
        self, session_id: str, cache_key: str,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT e.*,s.result_json,s.coverage_json,s.stale FROM tool_executions e "
                "JOIN evidence_snapshots s ON s.execution_id=e.id "
                "WHERE e.session_id=? AND e.cache_key=? AND e.status='completed' AND s.stale=0 "
                "ORDER BY e.created_at DESC LIMIT 1",
                (session_id, cache_key),
            )
            row = await cursor.fetchone()
        return self._decode_row(row) if row else None

    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM turns WHERE id=?", (turn_id,))
            row = await cursor.fetchone()
        return self._decode_row(row) if row else None

    @staticmethod
    def _decode_row(row: aiosqlite.Row) -> dict[str, Any]:
        data = dict(row)
        for key in list(data):
            if key.endswith("_json"):
                target = key[:-5]
                try:
                    data[target] = json.loads(data.pop(key) or "{}")
                except (TypeError, ValueError):
                    data[target] = {}
        if "stale" in data:
            data["stale"] = bool(data["stale"])
        return data
