"""Transport-only routes for the shared analysis tool protocol."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import ToolRequest
from patent_agent.application import SearchIndexService, ToolExecutionService
from retrieval.embedding import MULTILINGUAL_BETA_MODEL
from patent_agent.infrastructure import AppContainer
from patent_agent.infrastructure.observability import current_trace_id
from tools import tool_registry


router = APIRouter(prefix="/api", tags=["tools"])


@router.get("/tools")
def list_tools(container: AppContainer = Depends(get_container)):
    return {"tools": [{
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "methodology": tool.methodology,
        "evidence_level": tool.evidence_record.get("evidence_type", tool.evidence_level),
        "algorithm": tool.evidence_record,
        "cost_weight": tool.cost_weight,
        "returned_fields": tool.returned_fields,
        "definition": tool.definition.model_dump(mode="json"),
        "availability": tool.availability(container.store) if container.store else {
            "available": False, "reason": "尚未加载数据",
        },
    } for tool in tool_registry.list_tools()]}


@router.get("/search/status")
def search_status(container: AppContainer = Depends(get_container)):
    service = container.search_index_service or SearchIndexService()
    container.search_index_service = service
    return service.status(MULTILINGUAL_BETA_MODEL)


@router.post("/tools/{tool_name}")
async def run_tool(
    tool_name: str, req: ToolRequest = ToolRequest(),
    container: AppContainer = Depends(get_container),
):
    if not container.store or container.store.is_empty:
        raise HTTPException(400, "No patent data. Call /api/data/load first.")
    if len(container.active_generation_turns) >= container.settings.max_agent_concurrency:
        raise HTTPException(429, "已有分析任务正在运行，请等待完成后重试")
    try:
        tool = tool_registry.get_tool(tool_name)
    except KeyError:
        raise HTTPException(404, f"Unknown tool '{tool_name}'. Available: {tool_registry.get_all_names()}")
    try:
        async with container.tool_semaphore:
            service = container.tool_execution_service or ToolExecutionService()
            container.tool_execution_service = service
            result = await service.run_tool(tool, container.store, req.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Tool {tool_name} failed: {type(exc).__name__}") from exc

    if not hasattr(result, "model_dump"):
        return {"result_type": "patent_details", "data": [
            item.model_dump() if hasattr(item, "model_dump") else item for item in result
        ]}
    payload = result.model_dump()
    if not req.session_id:
        return payload
    if container.conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    repo = container.conversation_store
    fingerprint = container.store.dataset_fingerprint()
    await repo.ensure_session(req.session_id, fingerprint)
    turn_id = await repo.start_turn(
        req.session_id, "", origin="quick_tool",
        dataset_version_id=container.store.snapshot().version_id,
        trace_id=current_trace_id(),
    )
    execution_id = f"quick_{tool_name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    metadata = payload.get("result_metadata", {})
    await repo.record_execution(
        req.session_id, turn_id, execution_id, tool_name, req.params,
        "completed", payload,
        duration_ms=float(metadata.get("elapsed_ms", 0) or 0),
        algorithm_version=str(metadata.get("algorithm_version", "")),
        dataset_fingerprint=fingerprint,
        provenance=payload.get("provenance", {}), metrics=payload.get("metrics", {}),
    )
    await repo.finish_turn(
        req.session_id, turn_id, payload.get("summary") or f"{tool_name} 已完成。",
        metadata={"origin": "quick_tool", "execution_id": execution_id},
    )
    payload.setdefault("result_metadata", {}).update({
        "session_id": req.session_id, "turn_id": turn_id,
        "execution_id": execution_id, "origin": "quick_tool",
    })
    return payload
