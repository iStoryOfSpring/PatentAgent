"""SQLite persistence for non-secret LLM provider profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

from models.provider_profile import ProviderProfileCreate
from storage.conversation_store import _now


class ProviderProfileStore:
    SCHEMA_VERSION = 1

    _MIGRATION_COLUMNS = {
        "schema_version": "INTEGER NOT NULL DEFAULT 1",
        "notes": "TEXT NOT NULL DEFAULT ''",
        "website_url": "TEXT NOT NULL DEFAULT ''",
        "base_url": "TEXT NOT NULL DEFAULT ''",
        "model": "TEXT NOT NULL DEFAULT ''",
        "selected": "INTEGER NOT NULL DEFAULT 0",
        "auth_mode": "TEXT NOT NULL DEFAULT 'bearer'",
        "auth_header_name": "TEXT NOT NULL DEFAULT 'Authorization'",
        "auth_prefix": "TEXT NOT NULL DEFAULT 'Bearer '",
        "timeout_seconds": "INTEGER NOT NULL DEFAULT 60",
        "max_retries": "INTEGER NOT NULL DEFAULT 2",
        "max_output_tokens": "INTEGER NOT NULL DEFAULT 8192",
        "temperature": "REAL",
        "reasoning_effort": "TEXT NOT NULL DEFAULT 'default'",
        "thinking_mode": "TEXT NOT NULL DEFAULT 'auto'",
        "model_discovery_path": "TEXT NOT NULL DEFAULT '/models'",
        "extra_headers_json": "TEXT NOT NULL DEFAULT '[]'",
        "extra_body_json": "TEXT NOT NULL DEFAULT '{}'",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_schema_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_profiles (
                    id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    website_url TEXT NOT NULL DEFAULT '',
                    base_url TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    selected INTEGER NOT NULL DEFAULT 0,
                    auth_mode TEXT NOT NULL DEFAULT 'bearer',
                    auth_header_name TEXT NOT NULL DEFAULT 'Authorization',
                    auth_prefix TEXT NOT NULL DEFAULT 'Bearer ',
                    timeout_seconds INTEGER NOT NULL DEFAULT 60,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    max_output_tokens INTEGER NOT NULL DEFAULT 8192,
                    temperature REAL,
                    reasoning_effort TEXT NOT NULL DEFAULT 'default',
                    thinking_mode TEXT NOT NULL DEFAULT 'auto',
                    model_discovery_path TEXT NOT NULL DEFAULT '/models',
                    extra_headers_json TEXT NOT NULL DEFAULT '[]',
                    extra_body_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            # Databases created by development builds can contain an earlier
            # subset of the profile columns.  Keep this migration independent
            # from PRAGMA user_version, which belongs to the conversation store
            # in the same SQLite file.
            columns = {
                row[1] for row in await db.execute_fetchall(
                    "PRAGMA table_info(provider_profiles)"
                )
            }
            for name, definition in self._MIGRATION_COLUMNS.items():
                if name not in columns:
                    await db.execute(
                        f"ALTER TABLE provider_profiles ADD COLUMN {name} {definition}"
                    )
            # Normalize accidental multi-selection before creating the partial
            # unique index. Keep the most recently updated profile selected.
            await db.execute(
                "UPDATE provider_profiles SET selected=0 WHERE selected=1 AND id NOT IN ("
                "SELECT id FROM provider_profiles WHERE selected=1 "
                "ORDER BY updated_at DESC,id LIMIT 1)"
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_selected "
                "ON provider_profiles(selected) WHERE selected=1"
            )
            await db.execute(
                "INSERT INTO provider_schema_meta(singleton,schema_version) VALUES(1,?) "
                "ON CONFLICT(singleton) DO UPDATE SET schema_version=excluded.schema_version",
                (self.SCHEMA_VERSION,),
            )
            # Repair values written by an early validator that accidentally
            # stripped the required space from the conventional Bearer prefix.
            await db.execute(
                "UPDATE provider_profiles SET auth_prefix='Bearer ' "
                "WHERE auth_mode='bearer' AND auth_header_name='Authorization' "
                "AND auth_prefix='Bearer'"
            )
            await db.commit()

    @staticmethod
    def _storage_payload(payload: dict[str, Any]) -> dict[str, Any]:
        clean = dict(payload)
        headers = []
        for header in clean.get("extra_headers", []) or []:
            item = header.model_dump() if hasattr(header, "model_dump") else dict(header)
            item.pop("credential_loaded", None)
            if item.get("sensitive"):
                item["value"] = ""
            headers.append(item)
        clean["extra_headers"] = headers
        return clean

    @staticmethod
    def _decode(row: aiosqlite.Row) -> dict[str, Any]:
        item = dict(row)
        item["selected"] = bool(item["selected"])
        item["extra_headers"] = json.loads(item.pop("extra_headers_json") or "[]")
        item["extra_body"] = json.loads(item.pop("extra_body_json") or "{}")
        return item

    async def list_profiles(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM provider_profiles ORDER BY selected DESC, updated_at DESC"
            )
        return [self._decode(row) for row in rows]

    async def get_profile(self, profile_id: str, required: bool = True) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM provider_profiles WHERE id=?", (profile_id,),
            )
            row = await cursor.fetchone()
        if row is None and required:
            raise KeyError(profile_id)
        return self._decode(row) if row else None

    async def selected_profile(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM provider_profiles WHERE selected=1 LIMIT 1"
            )
            row = await cursor.fetchone()
        return self._decode(row) if row else None

    async def create_profile(self, profile: ProviderProfileCreate) -> dict[str, Any]:
        data = self._storage_payload(profile.model_dump(exclude={"id"}))
        profile_id = profile.id or f"provider_{uuid4().hex}"
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            if data.get("selected"):
                await db.execute("UPDATE provider_profiles SET selected=0")
            await db.execute(
                """INSERT INTO provider_profiles (
                    id,schema_version,name,protocol,notes,website_url,base_url,model,selected,
                    auth_mode,auth_header_name,auth_prefix,timeout_seconds,max_retries,
                    max_output_tokens,temperature,reasoning_effort,thinking_mode,
                    model_discovery_path,extra_headers_json,extra_body_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    profile_id, self.SCHEMA_VERSION, data["name"], data["protocol"],
                    data["notes"], data["website_url"], data["base_url"], data["model"],
                    int(data["selected"]), data["auth_mode"], data["auth_header_name"],
                    data["auth_prefix"], data["timeout_seconds"], data["max_retries"],
                    data["max_output_tokens"], data["temperature"], data["reasoning_effort"],
                    data["thinking_mode"], data["model_discovery_path"],
                    json.dumps(data["extra_headers"], ensure_ascii=False),
                    json.dumps(data["extra_body"], ensure_ascii=False), now, now,
                ),
            )
            await db.commit()
        return await self.get_profile(profile_id)

    async def update_profile(self, profile_id: str, data: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_profile(profile_id)
        merged = {**current, **data}
        merged.pop("id", None)
        merged.pop("schema_version", None)
        merged.pop("created_at", None)
        merged.pop("updated_at", None)
        validated = ProviderProfileCreate.model_validate(merged)
        clean = self._storage_payload(validated.model_dump(exclude={"id"}))
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            if clean["selected"]:
                await db.execute("UPDATE provider_profiles SET selected=0 WHERE id<>?", (profile_id,))
            cursor = await db.execute(
                """UPDATE provider_profiles SET
                    name=?,protocol=?,notes=?,website_url=?,base_url=?,model=?,selected=?,
                    auth_mode=?,auth_header_name=?,auth_prefix=?,timeout_seconds=?,max_retries=?,
                    max_output_tokens=?,temperature=?,reasoning_effort=?,thinking_mode=?,
                    model_discovery_path=?,extra_headers_json=?,extra_body_json=?,updated_at=?
                    WHERE id=?""",
                (
                    clean["name"], clean["protocol"], clean["notes"], clean["website_url"],
                    clean["base_url"], clean["model"], int(clean["selected"]), clean["auth_mode"],
                    clean["auth_header_name"], clean["auth_prefix"], clean["timeout_seconds"],
                    clean["max_retries"], clean["max_output_tokens"], clean["temperature"],
                    clean["reasoning_effort"], clean["thinking_mode"], clean["model_discovery_path"],
                    json.dumps(clean["extra_headers"], ensure_ascii=False),
                    json.dumps(clean["extra_body"], ensure_ascii=False), now, profile_id,
                ),
            )
            await db.commit()
            if cursor.rowcount == 0:
                raise KeyError(profile_id)
        return await self.get_profile(profile_id)

    async def select_profile(self, profile_id: str) -> dict[str, Any]:
        await self.get_profile(profile_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE provider_profiles SET selected=0")
            await db.execute(
                "UPDATE provider_profiles SET selected=1,updated_at=? WHERE id=?",
                (_now(), profile_id),
            )
            await db.commit()
        return await self.get_profile(profile_id)

    async def delete_profile(self, profile_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM provider_profiles WHERE id=?", (profile_id,))
            await db.commit()
            if cursor.rowcount == 0:
                raise KeyError(profile_id)
