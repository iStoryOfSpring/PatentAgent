"""Two-phase, fixed-source acquisition endpoints."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from patent_agent.api.dependencies import get_container
from patent_agent.application.acquisitions import AcquisitionRequest, AcquisitionService, sources

router=APIRouter(prefix="/api",tags=["acquisitions"])

def service(container):
    if container.conversation_store is None:raise HTTPException(503,"会话存储尚未初始化")
    if container.acquisition_service is None:container.acquisition_service=AcquisitionService(container)
    return container.acquisition_service

@router.get("/sources")
async def list_sources(container=Depends(get_container)):
    definitions=[s.model_dump() for s in sources()]
    if container.conversation_store is not None:
        import aiosqlite
        async with aiosqlite.connect(container.conversation_store.db_path) as db:
            rows=await db.execute_fetchall("SELECT state FROM acquisitions ORDER BY updated_at DESC LIMIT 1")
        if rows:
            for source in definitions:
                if source["id"]=="epo_ops":source["invocation_status"]=rows[0][0]
    return {"sources":definitions}

@router.post("/acquisitions",status_code=202)
async def create_acquisition(req:AcquisitionRequest,background_tasks:BackgroundTasks,container=Depends(get_container)):
    manager=service(container)
    try:job,start=await manager.prepare_or_confirm(req)
    except KeyError:raise HTTPException(404,"acquisition_not_found") from None
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
    if start:background_tasks.add_task(manager.run,job["id"])
    return {"acquisition":job}

@router.get("/acquisitions/{acquisition_id}")
async def get_acquisition(acquisition_id:str,container=Depends(get_container)):
    try:return {"acquisition":await service(container).get(acquisition_id)}
    except KeyError:raise HTTPException(404,"acquisition_not_found") from None

@router.post("/acquisitions/{acquisition_id}/cancel")
async def cancel_acquisition(acquisition_id:str,container=Depends(get_container)):
    try:return {"acquisition":await service(container).cancel(acquisition_id)}
    except KeyError:raise HTTPException(404,"acquisition_not_found") from None
    except ValueError as exc:raise HTTPException(409,str(exc)) from None
