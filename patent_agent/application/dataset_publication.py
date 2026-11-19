"""Publish a local immutable dataset and reconcile interrupted single-process uploads."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


def _destination(root, dataset_id, version_id):
    if not all(part and Path(part).name == part and part not in {".", ".."} for part in (dataset_id, version_id)):
        raise ValueError("invalid_publication_identity")
    base = Path(root).resolve()
    destination = base / ".patentagent" / "datasets" / dataset_id / version_id / "source"
    if destination.resolve() != destination:
        raise ValueError("unsafe_publication_path")
    return destination


async def _complete(db, ident, dataset_id, version, count, metrics):
    metrics.update(progress=100, stage="completed", dataset_id=dataset_id,
                   dataset_version_id=version, record_count=count)
    cursor = await db.execute(
        "UPDATE imports SET status='completed',dataset_version_id=?,metrics_json=?,updated_at=? "
        "WHERE id=? AND status IN ('queued','parsing')",
        (version, json.dumps(metrics, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), ident),
    )
    if cursor.rowcount != 1:
        raise ValueError("import_is_not_pending")


async def publish_dataset(container, store, source_root, dataset_id, name, import_id=""):
    repo = container.conversation_store
    snapshot = store.snapshot().model_dump(mode="json")
    version = snapshot["version_id"]
    destination = _destination(container.settings.data_root, dataset_id, version)
    metrics = {}
    if import_id:
        current = await repo.get_import(import_id)
        metrics = dict(current["metrics"])
        report = store._import_report
        metrics.update(publishing_version=version, dataset_id=dataset_id,
                       file_detections=report.get("file_detections", []), warnings=report.get("warnings", []),
                       application_evidence_count=report.get("application_evidence_count", 0))
        # Durable intent identifies a moved directory even if the transaction is interrupted.
        await repo.update_import(import_id, metrics_json=metrics)

    moved = False
    async with aiosqlite.connect(repo.db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("BEGIN IMMEDIATE")
        try:
            rows = await db.execute_fetchall("SELECT dataset_id,content_hash FROM dataset_versions WHERE id=?", (version,))
            if rows:
                dataset_id, content_hash = rows[0]
                if content_hash != snapshot["content_hash"]:
                    raise ValueError("dataset_identity_conflict")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError("dataset_destination_conflict")
                source_root.rename(destination)
                moved = True
                store._source_dir = str(destination)
                store._dataset_id_override = dataset_id
                store._version_id_override = version
                await repo.write_dataset_snapshot(db, {
                    **store.snapshot().model_dump(mode="json"), "name": name,
                    "storage_path": str(destination), "source_root": str(destination),
                    "import_id": import_id, "import_report": store._import_report,
                })
            if import_id:
                metrics["deduplicated"] = bool(rows)
                await _complete(db, import_id, dataset_id, version, snapshot["record_count"], metrics)
            await db.commit()
        except Exception:
            await db.rollback()
            if moved:
                destination.rename(source_root)
            raise

    if moved:
        if container.dataset_runtime:
            container.dataset_runtime.register(store)
        container.store = store
    return version, dataset_id, bool(rows)


def _verify_source(container, record):
    source = _destination(container.settings.data_root, record["dataset_id"], record["id"])
    if str(source) != record["storage_path"] or not source.is_dir():
        raise ValueError("invalid_version_source")
    adapter = record["adapter"]
    if adapter not in {"wos_dii", "google_patents_jsonl", "uspto_grant_xml", "uspto_file_wrapper_json", "canonical_jsonl"}:
        adapter = "auto"
    snapshot = container.dataset_service.load(str(source), adapter).snapshot()
    if (snapshot.content_hash, snapshot.version_id, snapshot.fingerprint_scheme) != (
        record["content_hash"], record["id"], record["fingerprint_scheme"],
    ):
        raise ValueError("invalid_version_identity")


async def recover_imports(container):
    """Reconcile only pending imports before serving requests; preserve conflicting files."""
    repo = container.conversation_store
    async with aiosqlite.connect(repo.db_path) as db:
        db.row_factory = aiosqlite.Row
        jobs = await db.execute_fetchall("SELECT * FROM imports WHERE status IN ('queued','parsing')")
        for job in jobs:
            metrics = json.loads(job["metrics_json"] or "{}")
            candidates = await db.execute_fetchall(
                "SELECT * FROM dataset_versions WHERE import_id=? OR id=?",
                (job["id"], job["dataset_version_id"] or ""),
            )
            conflict = bool(candidates or job["dataset_version_id"])
            try:
                if len(candidates) == 1:
                    record = candidates[0]
                    expected = metrics.get("publishing_version") or job["dataset_version_id"]
                    if expected and expected != record["id"]:
                        raise ValueError("conflicting_version_identity")
                    await asyncio.to_thread(_verify_source, container, record)
                    await _complete(db, job["id"], record["dataset_id"], record["id"], record["record_count"], metrics)
                    continue
                if metrics.get("publishing_version"):
                    path = _destination(container.settings.data_root, metrics["dataset_id"], metrics["publishing_version"])
                    conflict = conflict or path.exists()
                elif metrics.get("dataset_id"):
                    # Legacy tasks lack an intent receipt. A missing staging directory plus a
                    # published-looking directory is ambiguous; never adopt or remove it.
                    parent = _destination(container.settings.data_root, metrics["dataset_id"], "probe").parents[1]
                    conflict = conflict or (parent.is_dir() and not Path(job["source_path"]).exists())
            except Exception:
                # A corrupt or unreadable historical source must not block startup.
                conflict = True
            category = "import_recovery_conflict" if conflict else "import_interrupted"
            message = "导入记录与已保存版本不一致，请核查后重新上传" if conflict else "导入因服务重启中断，请重新上传"
            metrics.update(progress=100, stage="failed")
            await db.execute(
                "UPDATE imports SET status='failed',error_category=?,error=?,metrics_json=?,updated_at=? WHERE id=?",
                (category, message, json.dumps(metrics, ensure_ascii=False),
                 datetime.now(timezone.utc).isoformat(), job["id"]),
            )
        await db.commit()
