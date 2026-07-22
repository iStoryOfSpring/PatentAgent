"""Dataset import, quality summary and version routes."""

from fastapi import APIRouter, Depends, HTTPException

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import LoadRequest
from patent_agent.application import DatasetCatalog, DatasetImportService
from patent_agent.infrastructure import AppContainer
from patent_agent.infrastructure.observability import current_trace_id
from patent_agent.security import dataset_inventory, validate_input_dir
from storage.dataset_manifest import inspect_dii_batches


router = APIRouter(prefix="/api", tags=["datasets"])


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
        container.store.snapshot().model_dump(mode="json"),
    )
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
