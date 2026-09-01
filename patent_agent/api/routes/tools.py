"""Transport-only routes for the shared analysis tool protocol."""

import asyncio
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

CAPABILITY_GROUPS = [
    {
        "id": "patent_search", "name": "专利检索", "icon": "search",
        "description": "从当前语料中筛选相关专利并读取可用字段。",
        "tool_names": ["search_patents", "read_patent_details"],
        "prompts": ["检索与柔性传感器相关的专利", "列出最相关的 10 件专利并说明依据"],
    },
    {
        "id": "technology_landscape", "name": "数据与技术态势", "icon": "chart",
        "description": "分析公开趋势、IPC 构成、增长阶段和首个公开局分布。",
        "tool_names": ["get_dataset_summary", "analyze_patent_trend", "analyze_lifecycle", "analyze_ipc_distribution", "analyze_country_distribution"],
        "prompts": ["概括这个数据集的技术态势", "分析近五年的专利公开趋势"],
    },
    {
        "id": "technology_topics", "name": "技术热点与主题", "icon": "sparkles",
        "description": "识别高频技术词、近期增长词、年度变化和文本主题。",
        "tool_names": ["generate_wordcloud", "analyze_burst_terms", "analyze_yearly_keywords", "analyze_clustering"],
        "prompts": ["当前有哪些主要技术主题", "找出最近快速增长的技术词"],
    },
    {
        "id": "competition", "name": "竞争格局", "icon": "network",
        "description": "观察申请人合作关系和主要竞争者 IPC 布局变化。",
        "tool_names": ["analyze_co_network", "analyze_competitor_evolution", "analyze_entity_portfolio", "analyze_concentration"],
        "prompts": ["分析主要申请人的竞争格局", "哪些申请人的技术布局变化最大"],
    },
    {
        "id": "technology_roadmap", "name": "技术路线", "icon": "route",
        "description": "默认按年度梳理代表性主题；同族、优先权和引证覆盖门禁通过后附待复核路线。",
        "tool_names": ["analyze_tech_roadmap", "analyze_patent_trend"],
        "prompts": ["梳理该领域的技术演进路线", "按年份总结关键技术变化"],
    },
    {
        "id": "value_opportunity", "name": "价值与机会筛查", "icon": "target",
        "description": "进行数据集内相对价值筛查和代理功效矩阵分析。",
        "tool_names": ["analyze_patent_valuation", "analyze_tech_matrix"],
        "prompts": ["筛选值得进一步人工复核的专利", "分析技术手段与用途效果的低共现组合"],
    },
    {
        "id": "citation_family", "name": "引证与同族", "icon": "network",
        "description": "在来源覆盖门禁下分析内部/外部引证网络和分口径地域布局。",
        "tool_names": ["analyze_citation_network", "analyze_family_geography"],
        "prompts": ["分析内部与外部引证网络覆盖", "区分优先权地、首次公开局和同族覆盖局"],
    },
    {
        "id": "search_monitor", "name": "检索审计与监测", "icon": "search",
        "description": "比较检索策略版本并保存内容指纹化变化基线。",
        "tool_names": ["audit_search_strategy", "monitor_patent_changes"],
        "prompts": ["比较两版检索策略的独有命中", "保存当前检索结果作为监测基线"],
    },
    {
        "id": "legal_claims", "name": "法律状态与权利要求辅助", "icon": "shield",
        "description": "仅在权威状态或权利要求全文门禁通过时提供结构化人工复核草稿。",
        "tool_names": ["analyze_legal_status", "analyze_claim_elements"],
        "prompts": ["统计来源时点法律状态构成", "生成权利要求依赖树和要素拆分草稿"],
    },
]


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


@router.get("/capabilities")
def list_capabilities(container: AppContainer = Depends(get_container)):
    tools = {tool.name: tool for tool in tool_registry.list_tools()}
    groups = []
    for definition in CAPABILITY_GROUPS:
        statuses = []
        for name in definition["tool_names"]:
            tool = tools[name]
            availability = tool.availability(container.store) if container.store else {
                "available": False, "reason": "尚未加载数据",
            }
            statuses.append({"name": name, **availability})
        available_count = sum(bool(item.get("available")) for item in statuses)
        state = "available" if available_count == len(statuses) else (
            "partial" if available_count else "unavailable"
        )
        groups.append({
            **definition, "availability": state,
            "available_tool_count": available_count,
            "tool_count": len(statuses), "tools": statuses,
        })
    return {"capabilities": groups}


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
    dataset = container.store
    if req.session_id and container.dataset_runtime:
        try:
            dataset = await container.dataset_runtime.for_session(req.session_id, dataset)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, f"会话绑定的数据集不可用: {exc}") from exc
    if not dataset or dataset.is_empty:
        raise HTTPException(400, "No patent data. Call /api/data/load first.")
    if len(container.active_generation_turns) >= container.settings.max_agent_concurrency:
        raise HTTPException(429, "已有分析任务正在运行，请等待完成后重试")
    try:
        tool = tool_registry.get_tool(tool_name)
    except KeyError:
        raise HTTPException(404, f"Unknown tool '{tool_name}'. Available: {tool_registry.get_all_names()}")
    try:
        async with asyncio.timeout(container.settings.max_tool_queue_wait_seconds):
            await container.tool_semaphore.acquire()
    except TimeoutError as exc:
        raise HTTPException(429, "工具队列等待超时，请缩小分析范围或稍后重试") from exc
    try:
        service = container.tool_execution_service or ToolExecutionService()
        container.tool_execution_service = service
        result = await service.run_tool(tool, dataset, req.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Tool {tool_name} failed: {type(exc).__name__}") from exc
    finally:
        container.tool_semaphore.release()

    if not hasattr(result, "model_dump"):
        return {"result_type": "patent_details", "data": [
            item.model_dump() if hasattr(item, "model_dump") else item for item in result
        ]}
    payload = result.model_dump(exclude={"chart_html"})
    if not req.session_id:
        return payload
    if container.conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    repo = container.conversation_store
    fingerprint = dataset.dataset_fingerprint()
    await repo.ensure_session(
        req.session_id, fingerprint,
        dataset_version_id=dataset.snapshot().version_id,
    )
    turn_id = await repo.start_turn(
        req.session_id, "", origin="quick_tool",
        dataset_version_id=dataset.snapshot().version_id,
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
