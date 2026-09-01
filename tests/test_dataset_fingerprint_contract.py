"""Dataset versions identify normalized analysis content, not only record IDs."""

import asyncio
import sqlite3

import pandas as pd

from storage.conversation_store import ConversationStore
from storage.datastore import PatentDataStore


def _frame():
    return pd.DataFrame({
        "patent_number": ["US1", "US2"],
        "source_record_id": ["r1", "r2"],
        "title": ["battery", "motor"],
        "abstract": ["solid electrolyte", "electric drive"],
        "publication_date": ["2020-01-01", "2021-01-01"],
        "date": ["2020-01-01", "2021-01-01"],
        "applicants": ["Beta;Acme", "Drive Corp"],
        "inventors": ["I1;I2", "I3"],
        "ipc": ["H01M;H02J", "H02K"],
        "backward_citations": ["US9;US8", ""],
    })


def test_fingerprint_changes_when_analysis_content_changes():
    original = _frame()
    changed = original.copy()
    changed.loc[0, "title"] = "completely changed content"
    assert (
        PatentDataStore(original).dataset_fingerprint()
        != PatentDataStore(changed).dataset_fingerprint()
    )


def test_fingerprint_changes_when_citations_change():
    original = _frame()
    changed = original.copy()
    changed.loc[0, "backward_citations"] = "US9;US7"
    assert (
        PatentDataStore(original).dataset_fingerprint()
        != PatentDataStore(changed).dataset_fingerprint()
    )


def test_fingerprint_is_row_and_multivalue_order_independent():
    original = _frame()
    reordered = original.iloc[::-1].reset_index(drop=True)
    reordered.loc[1, "applicants"] = "Acme;Beta"
    reordered.loc[1, "ipc"] = "H02J;H01M"
    reordered.loc[1, "backward_citations"] = "US8;US9"
    assert (
        PatentDataStore(original).dataset_fingerprint()
        == PatentDataStore(reordered).dataset_fingerprint()
    )


def test_snapshot_declares_content_fingerprint_scheme():
    snapshot = PatentDataStore(_frame()).snapshot()
    assert snapshot.schema_version == 2
    assert snapshot.fingerprint_scheme == "patent-content-v2"
    assert snapshot.version_id.endswith(snapshot.content_hash[:24])


def test_dataset_version_schema_migration_is_idempotent(tmp_path):
    async def scenario():
        db_path = tmp_path / "legacy.db"
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, source_root TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
            db.execute("CREATE TABLE dataset_versions (id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, content_hash TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, adapter TEXT NOT NULL DEFAULT '', record_count INTEGER NOT NULL DEFAULT 0, field_coverage_json TEXT NOT NULL DEFAULT '{}', sources_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)")
        repo = ConversationStore(db_path)
        await repo.initialize()
        await repo.initialize()
        with sqlite3.connect(db_path) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(dataset_versions)")}
            version = db.execute("PRAGMA user_version").fetchone()[0]
        assert "fingerprint_scheme" in columns
        assert version == ConversationStore.SCHEMA_VERSION

    asyncio.run(scenario())
