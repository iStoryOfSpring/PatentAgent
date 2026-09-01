"""Dataset import, quality summary and version routes."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import DatasetUpdateRequest, LoadRequest
from patent_agent.application import DatasetCatalog, DatasetImportService
from patent_agent.infrastructure import AppContainer
from patent_agent.infrastructure.observability import current_trace_id
from patent_agent.security import dataset_inventory, validate_input_dir
from storage.dataset_manifest import inspect_dii_batches


router = APIRouter(prefix="/api", tags=["datasets"])

_ALLOWED_EXTENSIONS = {".txt", ".jsonl", ".json", ".xml"}
_SOURCE_FORMATS = {
    "auto", "wos_dii", "google_patents_jsonl", "uspto_grant_xml",
    "uspto_file_wrapper_json",
}
_SAFE_DATASET_ID = re.compile(r"^dataset_[A-Za-z0-9_-]{6,80}$")


def _repo(container: AppContainer):
    if container.conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    return container.conversation_store


@router.post("/data/load")
async def data_load(req: LoadRequest, container: AppContainer = Depends(get_container)):
    try:
        input_dir = validate_input_dir(req.input_dir, container.settings.data_root)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    service = container.dataset_service or DatasetImportService()
    container.dataset_service = service
    try:
        container.store = service.load(input_dir, req.source_format)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    container.store._load_diagnostics = inspect_dii_batches(
        input_dir, len(container.store.get_all()),
    )
    await _repo(container).upsert_dataset_snapshot(
        {
            **container.store.snapshot().model_dump(mode="json"),
            "storage_path": input_dir,
            "source_root": input_dir,
        },
    )
    if container.dataset_runtime:
        container.dataset_runtime.register(container.store)
    return {
        **DatasetCatalog().summary(container.store),
        "datasets": dataset_inventory(container.settings.data_root),
        "trace_id": current_trace_id(),
    }


@router.get("/data/summary")
def data_summary(container: AppContainer = Depends(get_container)):
    if not container.store or container.store.is_empty:
        raise HTTPException(404, "No patent data loaded. POST /api/data/load first.")
    return {
        **DatasetCatalog().summary(container.store),
        "datasets": dataset_inventory(container.settings.data_root),
        "trace_id": current_trace_id(),
    }


@router.get("/datasets")
async def list_datasets(container: AppContainer = Depends(get_container)):
    versions = await _repo(container).list_dataset_versions()
    grouped: dict[str, dict] = {}
    for version in versions:
        dataset = grouped.setdefault(version["dataset_id"], {
            "id": version["dataset_id"],
            "name": version.get("name") or version["dataset_id"],
            "source_root": version.get("source_root", ""),
            "latest_version": version,
            "version_count": 0,
            "status": version.get("dataset_status", "ready"),
        })
        dataset["version_count"] += 1
    return {"datasets": list(grouped.values()), "trace_id": current_trace_id()}


@router.get("/datasets/{dataset_id}/versions")
async def list_dataset_versions(dataset_id: str, container: AppContainer = Depends(get_container)):
    versions = [
        item for item in await _repo(container).list_dataset_versions()
        if item["dataset_id"] == dataset_id
    ]
    if not versions:
        raise HTTPException(404, "数据集不存在")
    return {"dataset_id": dataset_id, "versions": versions, "trace_id": current_trace_id()}


@router.patch("/datasets/{dataset_id}")
async def update_dataset(
    dataset_id: str, req: DatasetUpdateRequest,
    container: AppContainer = Depends(get_container),
):
    try:
        dataset = await _repo(container).update_dataset(
            dataset_id, **req.model_dump(exclude_none=True),
        )
    except KeyError as exc:
        raise HTTPException(404, "数据集不存在") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"dataset": dataset, "trace_id": current_trace_id()}


@router.post("/datasets/imports", status_code=202)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    name: str = Form("新数据集"),
    source_format: str = Form("auto"),
    dataset_id: str = Form(""),
    container: AppContainer = Depends(get_container),
):
    if not files:
        raise HTTPException(422, "请至少选择一个文件")
    if source_format not in _SOURCE_FORMATS:
        raise HTTPException(422, "不支持的数据源格式")
    if dataset_id and not _SAFE_DATASET_ID.fullmatch(dataset_id):
        raise HTTPException(422, "dataset_id 格式无效")
    import_id = f"import_{uuid4().hex}"
    selected_dataset_id = dataset_id or f"dataset_{uuid4().hex}"
    stage_root = (
        container.settings.data_root / ".patentagent" / "uploads" / import_id
    ).resolve()
    source_root = stage_root / "source"
    source_root.mkdir(parents=True, exist_ok=False)
    total = 0
    staged_names: list[str] = []
    try:
        for upload in files:
            filename = Path(upload.filename or "").name
            if not filename or filename != upload.filename:
                raise ValueError("文件名包含非法路径")
            if Path(filename).suffix.lower() not in _ALLOWED_EXTENSIONS:
                raise ValueError(f"不支持的文件扩展名: {filename}")
            target = source_root / filename
            if target.exists():
                raise ValueError(f"文件名重复: {filename}")
            file_size = 0
            with target.open("xb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    file_size += len(chunk)
                    total += len(chunk)
                    if file_size > container.settings.max_upload_file_bytes:
                        raise ValueError(f"文件超过单文件大小限制: {filename}")
                    if total > container.settings.max_upload_total_bytes:
                        raise ValueError("上传文件总量超过限制")
                    handle.write(chunk)
            staged_names.append(filename)
    except (OSError, ValueError) as exc:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise HTTPException(422, str(exc)) from exc
    finally:
        for upload in files:
            await upload.close()

    repo = _repo(container)
    await repo.create_import(import_id, str(source_root), {
        "dataset_id": selected_dataset_id,
        "name": name.strip() or "新数据集",
        "source_format": source_format,
        "files": staged_names,
        "bytes_received": total,
        "progress": 0,
    })
    background_tasks.add_task(
        _process_upload, container, import_id, selected_dataset_id,
        name.strip() or "新数据集", source_format, stage_root, source_root,
    )
    return {
        "import_id": import_id, "status": "queued",
        "dataset_id": selected_dataset_id, "files": staged_names,
        "trace_id": current_trace_id(),
    }


@router.get("/imports/{import_id}")
async def get_import(import_id: str, container: AppContainer = Depends(get_container)):
    record = await _repo(container).get_import(import_id)
    if not record:
        raise HTTPException(404, "导入任务不存在")
    return {"import": record, "trace_id": current_trace_id()}


async def _process_upload(
    container: AppContainer, import_id: str, dataset_id: str, name: str,
    source_format: str, stage_root: Path, source_root: Path,
) -> None:
    repo = _repo(container)
    try:
        current = await repo.get_import(import_id) or {}
        metrics = dict(current.get("metrics") or {})
        metrics.update({"progress": 20, "stage": "parsing"})
        await repo.update_import(import_id, status="parsing", metrics_json=metrics)
        service = container.dataset_service or DatasetImportService()
        container.dataset_service = service
        store = await asyncio.to_thread(service.load, str(source_root), source_format)
        if store.is_empty:
            report = store.audit().get("import_report", {})
            issues = report.get("issues", [])
            detail = issues[0].get("message") if issues else "没有解析出专利记录"
            raise ValueError(detail)
        content_version_id = store.snapshot().version_id
        existing = await repo.get_dataset_version(content_version_id)
        if existing:
            shutil.rmtree(stage_root, ignore_errors=True)
            metrics.update({
                "progress": 100, "stage": "completed", "deduplicated": True,
                "dataset_id": existing["dataset_id"],
                "dataset_version_id": existing["id"],
                "record_count": existing.get("record_count", 0),
            })
            await repo.update_import(
                import_id, status="completed", dataset_version_id=existing["id"],
                metrics_json=metrics,
            )
            return

        final_source = (
            container.settings.data_root / ".patentagent" / "datasets" /
            dataset_id / content_version_id / "source"
        ).resolve()
        final_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_root), str(final_source))
        shutil.rmtree(stage_root, ignore_errors=True)
        store._source_dir = str(final_source)
        store._dataset_id_override = dataset_id
        store._version_id_override = content_version_id
        snapshot = store.snapshot().model_dump(mode="json")
        import_report = store.audit().get("import_report", {})
        await repo.upsert_dataset_snapshot({
            **snapshot,
            "name": name,
            "source_root": str(final_source),
            "storage_path": str(final_source),
            "import_id": import_id,
            "import_report": import_report,
        })
        metrics.update({
            "progress": 100, "stage": "completed", "deduplicated": False,
            "dataset_id": dataset_id, "dataset_version_id": content_version_id,
            "record_count": snapshot["record_count"],
            "file_detections": import_report.get("file_detections", []),
            "warnings": import_report.get("warnings", []),
        })
        await repo.update_import(
            import_id, status="completed", dataset_version_id=content_version_id,
            metrics_json=metrics,
        )
        if container.dataset_runtime:
            container.dataset_runtime.register(store)
        container.store = store
    except Exception as exc:
        shutil.rmtree(stage_root, ignore_errors=True)
        try:
            await repo.update_import(
                import_id, status="failed", error_category="import_failed",
                error=str(exc)[:500], metrics_json={"progress": 100, "stage": "failed"},
            )
        except Exception:
            pass
