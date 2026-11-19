import asyncio
from pathlib import Path
import shutil

import pytest

from patent_agent.application.dataset_publication import publish_dataset, recover_imports
from tests.test_acquisitions import container


async def staged(app, ident):
    root = app.settings.data_root / ".patentagent" / "uploads" / ident / "source"
    root.mkdir(parents=True)
    fixture = Path(__file__).resolve().parents[1] / "samples" / "offline" / "trend.jsonl"
    shutil.copyfile(fixture, root / "trend.jsonl")
    dataset = f"dataset_{ident}"
    await app.conversation_store.create_import(ident, str(root), {"dataset_id": dataset})
    store = app.dataset_service.load(str(root), "google_patents_jsonl")
    return store, root, dataset


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["queued", "parsing"])
async def test_pending_without_publication_fails_idempotently(tmp_path, state):
    app = await container(tmp_path)
    _, source, _ = await staged(app, "job")
    repo = app.conversation_store
    await repo.update_import("job", status=state)
    await recover_imports(app)
    first = await repo.get_import("job")
    assert (first["status"], first["error_category"]) == ("failed", "import_interrupted")
    await recover_imports(app)
    assert first == await repo.get_import("job")
    assert (source / "trend.jsonl").is_file()
    assert await repo.list_dataset_versions() == []


@pytest.mark.asyncio
async def test_move_before_commit_is_conflict_and_source_is_retained(tmp_path):
    app = await container(tmp_path)
    store, source, dataset = await staged(app, "job")
    version = store.snapshot().version_id
    repo = app.conversation_store
    await repo.update_import("job", status="parsing", metrics_json={"dataset_id":dataset,"publishing_version":version})
    target = app.settings.data_root / ".patentagent" / "datasets" / dataset / version / "source"
    target.parent.mkdir(parents=True)
    source.rename(target)
    await recover_imports(app)
    assert (await repo.get_import("job"))["error_category"] == "import_recovery_conflict"
    assert (target / "trend.jsonl").is_file() and not source.exists()
    assert await repo.list_dataset_versions() == []


@pytest.mark.asyncio
async def test_concurrent_upload_dedup_and_legacy_recovery(tmp_path):
    app = await container(tmp_path)
    repo = app.conversation_store

    async def upload(ident):
        store, source, dataset = await staged(app, ident)
        return await publish_dataset(app, store, source, dataset, ident, ident)

    results = await asyncio.gather(upload("first"), upload("second"))
    assert results[0][:2] == results[1][:2]
    assert sorted(item[2] for item in results) == [False, True]
    version, dataset = results[0][:2]
    versions = await repo.list_dataset_versions()
    assert len(versions) == 1
    record = versions[0]
    source = Path(record["storage_path"])
    assert (source / "trend.jsonl").is_file()
    assert len(list((app.settings.data_root / ".patentagent" / "datasets").glob("*/*/source"))) == 1
    original = record["import_id"]
    for ident in ("first", "second"):
        job = await repo.get_import(ident)
        assert (job["status"], job["dataset_version_id"], job["metrics"]["dataset_id"]) == ("completed", version, dataset)
    before = await repo.get_import(original)
    await recover_imports(app)
    assert before == await repo.get_import(original)

    # An older binary could register a version separately from completing its import.
    await repo.update_import(original, status="parsing", dataset_version_id="")
    await recover_imports(app)
    assert (await repo.get_import(original))["status"] == "completed"
    (source / "trend.jsonl").write_text("")
    await repo.update_import(original, status="parsing")
    await recover_imports(app)
    assert (await repo.get_import(original))["error_category"] == "import_recovery_conflict"
    assert source.is_dir() and len(await repo.list_dataset_versions()) == 1
