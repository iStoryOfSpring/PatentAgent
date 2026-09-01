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


def _scalar_evidence_values(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Flatten JSON leaves to the same escaped paths accepted by evidence://."""
    if isinstance(value, dict):
        output = []
        for key, item in value.items():
            segment = str(key).replace("~", "~0").replace("/", "~1")
            output.extend(_scalar_evidence_values(item, f"{path}/{segment}"))
        return output
    if isinstance(value, list):
        output = []
        for index, item in enumerate(value):
            output.extend(_scalar_evidence_values(item, f"{path}/{index}"))
        return output
    return [(path or "/", _json(value))]


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

    SCHEMA_VERSION = 7

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
                    dataset_version_id TEXT NOT NULL DEFAULT '',
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
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                    content_hash TEXT NOT NULL,
                    fingerprint_scheme TEXT NOT NULL DEFAULT 'legacy-identity-v1',
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    adapter TEXT NOT NULL DEFAULT '',
                    record_count INTEGER NOT NULL DEFAULT 0,
                    field_coverage_json TEXT NOT NULL DEFAULT '{}',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    storage_path TEXT NOT NULL DEFAULT '',
                    import_id TEXT NOT NULL DEFAULT '',
                    import_report_json TEXT NOT NULL DEFAULT '{}',
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
                CREATE TABLE IF NOT EXISTS record_hashes (
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
                    patent_number TEXT NOT NULL,
                    record_content_hash TEXT NOT NULL,
                    PRIMARY KEY(dataset_version_id,patent_number)
                );
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL DEFAULT '',
                    parent_entity_id TEXT REFERENCES entities(id) ON DELETE SET NULL,
                    valid_from TEXT, valid_to TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    alias TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'und',
                    source TEXT NOT NULL DEFAULT '', confidence REAL,
                    resolution_method TEXT NOT NULL DEFAULT '',
                    review_status TEXT NOT NULL DEFAULT 'unreviewed',
                    UNIQUE(entity_id,alias,source)
                );
                CREATE TABLE IF NOT EXISTS patent_party_roles (
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
                    patent_number TEXT NOT NULL,
                    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
                    observed_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(dataset_version_id,patent_number,entity_id,role,source)
                );
                CREATE TABLE IF NOT EXISTS analysis_scopes (
                    scope_hash TEXT PRIMARY KEY,
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
                    canonical_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_values (
                    execution_id TEXT NOT NULL REFERENCES tool_executions(id) ON DELETE CASCADE,
                    json_path TEXT NOT NULL,
                    scalar_json TEXT NOT NULL,
                    PRIMARY KEY(execution_id,json_path)
                );
                CREATE TABLE IF NOT EXISTS taxonomies (
                    id TEXT NOT NULL, version TEXT NOT NULL,
                    name TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '',
                    creator TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    PRIMARY KEY(id,version)
                );
                CREATE TABLE IF NOT EXISTS taxonomy_labels (
                    taxonomy_id TEXT NOT NULL, taxonomy_version TEXT NOT NULL,
                    label_id TEXT NOT NULL, label_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    PRIMARY KEY(taxonomy_id,taxonomy_version,label_id),
                    FOREIGN KEY(taxonomy_id,taxonomy_version) REFERENCES taxonomies(id,version) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS record_annotations (
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
                    patent_number TEXT NOT NULL,
                    taxonomy_id TEXT NOT NULL, taxonomy_version TEXT NOT NULL,
                    label_id TEXT NOT NULL, source TEXT NOT NULL,
                    reviewer TEXT NOT NULL DEFAULT '', review_status TEXT NOT NULL DEFAULT 'unreviewed',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(dataset_version_id,patent_number,taxonomy_id,taxonomy_version,label_id,source)
                );
                CREATE TABLE IF NOT EXISTS search_strategies (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_strategy_versions (
                    strategy_id TEXT NOT NULL REFERENCES search_strategies(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, strategy_hash TEXT NOT NULL,
                    query_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(strategy_id,version), UNIQUE(strategy_hash)
                );
                CREATE TABLE IF NOT EXISTS monitor_runs (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL, strategy_version INTEGER NOT NULL,
                    dataset_version_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS monitor_events (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES monitor_runs(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL, patent_number TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS external_evidence (
                    evidence_id TEXT PRIMARY KEY, evidence_type TEXT NOT NULL,
                    title TEXT NOT NULL, source_name TEXT NOT NULL,
                    source_uri TEXT NOT NULL, published_at TEXT,
                    observed_at TEXT NOT NULL, entities_json TEXT NOT NULL DEFAULT '[]',
                    text_excerpt TEXT NOT NULL, content_hash TEXT NOT NULL,
                    license_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
                CREATE INDEX IF NOT EXISTS idx_exec_session ON tool_executions(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_exec_cache ON tool_executions(cache_key);
                CREATE INDEX IF NOT EXISTS idx_task_events_turn ON task_events(turn_id,id);
                CREATE INDEX IF NOT EXISTS idx_external_evidence_type_time ON external_evidence(evidence_type,published_at);
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
            session_columns = {
                row[1] for row in await db.execute_fetchall("PRAGMA table_info(sessions)")
            }
            if "dataset_version_id" not in session_columns:
                await db.execute(
                    "ALTER TABLE sessions ADD COLUMN dataset_version_id TEXT NOT NULL DEFAULT ''"
                )
            dataset_columns = {
                row[1] for row in await db.execute_fetchall("PRAGMA table_info(datasets)")
            }
            if "status" not in dataset_columns:
                await db.execute(
                    "ALTER TABLE datasets ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'"
                )
            version_columns = {
                row[1] for row in await db.execute_fetchall("PRAGMA table_info(dataset_versions)")
            }
            for column, ddl in {
                "storage_path": "TEXT NOT NULL DEFAULT ''",
                "import_id": "TEXT NOT NULL DEFAULT ''",
                "import_report_json": "TEXT NOT NULL DEFAULT '{}'",
                "fingerprint_scheme": "TEXT NOT NULL DEFAULT 'legacy-identity-v1'",
            }.items():
                if column not in version_columns:
                    await db.execute(f"ALTER TABLE dataset_versions ADD COLUMN {column} {ddl}")
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
            await db.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_dataset_version
                ON sessions(dataset_version_id);
                CREATE INDEX IF NOT EXISTS idx_dataset_versions_dataset
                ON dataset_versions(dataset_id,created_at);
                CREATE INDEX IF NOT EXISTS idx_imports_status
                ON imports(status,updated_at);
                CREATE INDEX IF NOT EXISTS idx_reports_session
                ON reports(session_id,created_at);
                """
            )
            await db.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")
            await db.execute("PRAGMA optimize")
            await db.commit()

    async def create_session(
        self, name: str = "新会话", dataset_fingerprint: str = "",
        session_id: str | None = None, dataset_version_id: str = "",
    ) -> dict[str, Any]:
        session_id = session_id or f"session_{uuid4().hex}"
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT OR IGNORE INTO sessions "
                "(id,name,dataset_fingerprint,dataset_version_id,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (session_id, name.strip() or "新会话", dataset_fingerprint,
                 dataset_version_id, "idle", now, now),
            )
            await db.commit()
        return await self.get_session(session_id)

    async def ensure_session(
        self, session_id: str, dataset_fingerprint: str,
        name: str = "新会话", dataset_version_id: str = "",
    ) -> dict[str, Any]:
        session = await self.get_session(session_id, required=False)
        if not session:
            return await self.create_session(
                name, dataset_fingerprint, session_id, dataset_version_id,
            )
        # Existing sessions keep their explicit binding. Legacy rows are filled
        # once, without invalidating evidence merely because the session was read.
        if not session.get("dataset_version_id") and dataset_version_id:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE sessions SET dataset_fingerprint=?,dataset_version_id=?,updated_at=? "
                    "WHERE id=?",
                    (dataset_fingerprint, dataset_version_id, _now(), session_id),
                )
                await db.commit()
            session = await self.get_session(session_id)
        elif (
            not session.get("dataset_version_id") and not dataset_version_id and
            session.get("dataset_fingerprint") != dataset_fingerprint
        ):
            # Backward-compatible behavior for embedded callers that do not
            # know version IDs. HTTP session reads no longer call this method.
            async with aiosqlite.connect(self.db_path) as db:
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

    async def bind_session_dataset(
        self, session_id: str, dataset_version_id: str, dataset_fingerprint: str,
    ) -> tuple[dict[str, Any], int]:
        session = await self.get_session(session_id)
        if session.get("dataset_version_id") == dataset_version_id:
            return session, 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            cursor = await db.execute(
                "UPDATE evidence_snapshots SET stale=1 WHERE stale=0 AND execution_id IN "
                "(SELECT id FROM tool_executions WHERE session_id=?)",
                (session_id,),
            )
            await db.execute(
                "UPDATE sessions SET dataset_fingerprint=?,dataset_version_id=?,updated_at=? "
                "WHERE id=?",
                (dataset_fingerprint, dataset_version_id, _now(), session_id),
            )
            await db.commit()
            stale_count = max(cursor.rowcount, 0)
        return await self.get_session(session_id), stale_count

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
                 "queued", provider, model, provider_profile_id,
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
            await db.execute(
                "DELETE FROM evidence_values WHERE execution_id=?", (execution_id,),
            )
            await db.executemany(
                "INSERT INTO evidence_values(execution_id,json_path,scalar_json) VALUES (?,?,?)",
                [
                    (execution_id, path, scalar)
                    for path, scalar in _scalar_evidence_values(clean_result)
                ],
            )
            dataset_version_id = str((provenance or {}).get("dataset_version_id", ""))
            scope = parameters.get("scope") if isinstance(parameters, dict) else None
            if dataset_version_id and isinstance(scope, dict):
                exists = await db.execute_fetchall(
                    "SELECT 1 FROM dataset_versions WHERE id=?", (dataset_version_id,),
                )
                if exists:
                    canonical_scope = json.dumps(
                        scope, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), default=str,
                    )
                    scope_hash = hashlib.sha256(
                        f"{dataset_version_id}\0{canonical_scope}".encode()
                    ).hexdigest()
                    await db.execute(
                        "INSERT OR IGNORE INTO analysis_scopes VALUES (?,?,?,?)",
                        (scope_hash, dataset_version_id, canonical_scope, _now()),
                    )
            await db.commit()
        return cache_key

    async def mark_inflight_interrupted(self) -> int:
        """Make process crashes explicit without replaying an LLM request."""
        inflight = (
            "created", "queued", "planning", "planned", "running", "executing",
            "validating", "synthesizing", "cancelling",
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
                "UPDATE turns SET cancel_requested=1,status='cancelling',updated_at=?,"
                "state_version=state_version+1 WHERE id=? AND status NOT IN "
                "('completed','partial','failed','cancelled','interrupted')",
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
                "SELECT v.*,d.name,d.source_root,d.status AS dataset_status FROM dataset_versions v "
                "JOIN datasets d ON d.id=v.dataset_id ORDER BY v.created_at DESC"
            )
        return [self._decode_row(row) for row in rows]

    async def get_dataset_version(self, version_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT v.*,d.name,d.source_root,d.status AS dataset_status "
                "FROM dataset_versions v JOIN datasets d ON d.id=v.dataset_id WHERE v.id=?",
                (version_id,),
            )
            row = await cursor.fetchone()
        return self._decode_row(row) if row else None

    async def upsert_dataset_snapshot(self, snapshot: dict[str, Any]) -> None:
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(
                "INSERT INTO datasets(id,name,source_root,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name,source_root=excluded.source_root,status=excluded.status,"
                "updated_at=excluded.updated_at",
                (snapshot["dataset_id"], snapshot.get("name") or snapshot["dataset_id"],
                 snapshot.get("source_root") or (snapshot.get("sources") or [""])[0],
                 snapshot.get("status", "ready"), now, now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO dataset_versions "
                "(id,dataset_id,content_hash,fingerprint_scheme,schema_version,adapter,record_count,"
                "field_coverage_json,sources_json,storage_path,import_id,import_report_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (snapshot["version_id"], snapshot["dataset_id"], snapshot["content_hash"],
                 snapshot.get("fingerprint_scheme", "legacy-identity-v1"),
                 snapshot.get("schema_version", 1), snapshot.get("adapter", ""),
                 snapshot.get("record_count", 0), _json(snapshot.get("field_coverage", {})),
                 _json(snapshot.get("sources", [])), snapshot.get("storage_path", ""),
                 snapshot.get("import_id", ""), _json(snapshot.get("import_report", {})), now),
            )
            await db.commit()

    async def update_dataset(self, dataset_id: str, **values: Any) -> dict[str, Any]:
        allowed = {"name", "status"}
        clean = {key: value for key, value in values.items() if key in allowed}
        if not clean:
            raise ValueError("没有可更新的数据集字段")
        if "status" in clean and clean["status"] not in {"ready", "archived"}:
            raise ValueError("status 必须是 ready 或 archived")
        if "name" in clean and not str(clean["name"]).strip():
            raise ValueError("数据集名称不能为空")
        clean["updated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in clean)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE datasets SET {assignments} WHERE id=?",
                (*clean.values(), dataset_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                raise KeyError(dataset_id)
            db.row_factory = aiosqlite.Row
            result = await db.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,))
            row = await result.fetchone()
        return dict(row)

    async def create_import(
        self, import_id: str, source_path: str, metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO imports(id,status,source_path,metrics_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (import_id, "queued", source_path, _json(metrics or {}), now, now),
            )
            await db.commit()
        return await self.get_import(import_id)

    async def update_import(self, import_id: str, **values: Any) -> dict[str, Any]:
        allowed = {"status", "dataset_version_id", "error_category", "error", "metrics_json"}
        clean = {key: value for key, value in values.items() if key in allowed}
        if "metrics_json" in clean and not isinstance(clean["metrics_json"], str):
            clean["metrics_json"] = _json(clean["metrics_json"])
        clean["updated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in clean)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE imports SET {assignments} WHERE id=?", (*clean.values(), import_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                raise KeyError(import_id)
        return await self.get_import(import_id)

    async def get_import(self, import_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM imports WHERE id=?", (import_id,))
            row = await cursor.fetchone()
        return self._decode_row(row) if row else None

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

    async def list_reports(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id,session_id,turn_id,title,format,created_at FROM reports "
                "ORDER BY created_at DESC"
            )
        return [dict(row) for row in rows]

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM reports WHERE id=?", (report_id,))
            row = await cursor.fetchone()
        return dict(row) if row else None

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

    async def add_external_evidence(self, record) -> dict[str, Any]:
        """Persist immutable, source-attributed non-patent evidence."""
        from patent_agent.domain import ExternalEvidenceRecord

        item = ExternalEvidenceRecord.model_validate(record)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            existing = await db.execute_fetchall(
                "SELECT * FROM external_evidence WHERE evidence_id=?",
                (item.evidence_id,),
            )
            if existing:
                current = self._decode_row(existing[0])
                if current.get("content_hash") != item.content_hash:
                    raise ValueError("同一 evidence_id 已绑定不同 content_hash")
                return current
            created_at = _now()
            await db.execute(
                "INSERT INTO external_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.evidence_id, item.evidence_type, item.title,
                    item.source_name, item.source_uri, item.published_at,
                    item.observed_at, _json(item.entities), item.text_excerpt,
                    item.content_hash, item.license_note, created_at,
                ),
            )
            await db.commit()
        return {**item.model_dump(mode="json"), "created_at": created_at}

    async def list_external_evidence(
        self, evidence_type: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        clause = "WHERE evidence_type=?" if evidence_type else ""
        params = (evidence_type, limit) if evidence_type else (limit,)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                f"SELECT * FROM external_evidence {clause} "
                "ORDER BY observed_at DESC,evidence_id LIMIT ?",
                params,
            )
        return [self._decode_row(row) for row in rows]

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
