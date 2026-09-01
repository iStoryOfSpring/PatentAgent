import asyncio
import hashlib
import sqlite3

import pytest

from storage.conversation_store import ConversationStore


def test_schema_v7_creates_remediation_tables_and_external_evidence_is_immutable(tmp_path):
    async def scenario():
        store = ConversationStore(tmp_path / "schema-v7.db")
        await store.initialize()
        excerpt = "Company A announced a standards contribution."
        record = {
            "evidence_id": "ext-1",
            "evidence_type": "standard",
            "title": "Standards contribution",
            "source_name": "Standards body",
            "source_uri": "https://example.invalid/source/1",
            "published_at": "2026-01-01",
            "observed_at": "2026-09-01T00:00:00Z",
            "entities": ["Company A", "Company A"],
            "text_excerpt": excerpt,
            "content_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
            "license_note": "test fixture",
        }
        created = await store.add_external_evidence(record)
        assert created["entities"] == ["Company A"]
        listed = await store.list_external_evidence("standard")
        assert listed[0]["content_hash"] == record["content_hash"]
        with pytest.raises(ValueError, match="不同 content_hash"):
            await store.add_external_evidence({**record, "content_hash": "0" * 64})
        session = await store.create_session("evidence")
        turn_id = await store.start_turn(session["id"], "run")
        await store.record_execution(
            session["id"], turn_id, "exec-1", "test_tool", {}, "completed",
            {"data": [{"year": 2024, "count": 12}]},
        )

    asyncio.run(scenario())
    with sqlite3.connect(tmp_path / "schema-v7.db") as db:
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "record_hashes", "entities", "entity_aliases", "patent_party_roles",
            "analysis_scopes", "evidence_values", "taxonomies", "taxonomy_labels",
            "record_annotations", "search_strategies", "search_strategy_versions",
            "monitor_runs", "monitor_events", "external_evidence",
        } <= tables
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
        values = dict(db.execute(
            "SELECT json_path,scalar_json FROM evidence_values WHERE execution_id='exec-1'"
        ))
        assert values["/data/0/count"] == "12"
