"""Report export route backed by the report application service."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from html import escape

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import CreateReportRequest, ExportRequest
from patent_agent.application import ReportService
from patent_agent.infrastructure import AppContainer
from reporting import ReportGenerator


router = APIRouter(prefix="/api", tags=["reports"])


def _structured_preview(result: dict) -> str | None:
    """Render a small, escaped table from persisted structured tool output."""
    rows = None
    for key in ("data", "top_patents", "items", "results", "yearly_data"):
        candidate = result.get(key)
        if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
            rows = candidate[:12]
            break
    if not rows:
        return None
    columns = list(dict.fromkeys(
        key for row in rows for key in row.keys()
        if not isinstance(row.get(key), (dict, list))
    ))[:8]
    if not columns:
        return None
    header = "".join(f"<th>{escape(str(column))}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(
            f"<td>{escape(str(row.get(column, '')))}</td>" for column in columns
        ) + "</tr>" for row in rows
    )
    return (
        '<div class="structured-preview"><table><thead><tr>' + header +
        "</tr></thead><tbody>" + body + "</tbody></table></div>"
    )


@router.post("/report/export")
async def report_export(req: ExportRequest, container: AppContainer = Depends(get_container)):
    service = container.report_service or ReportService(ReportGenerator)
    container.report_service = service
    html = service.export_html(req.title, req.messages)
    report_id = ""
    if container.conversation_store is not None:
        try:
            report_id = await container.conversation_store.save_report(
                req.title, html, req.session_id, req.turn_id,
            )
        except Exception as exc:
            raise HTTPException(422, f"报告记录保存失败: {type(exc).__name__}") from exc
    return HTMLResponse(content=html, headers={"X-Report-ID": report_id} if report_id else None)


def _repo(container: AppContainer):
    if container.conversation_store is None:
        raise HTTPException(503, "会话存储尚未初始化")
    return container.conversation_store


@router.post("/reports")
async def create_report(
    req: CreateReportRequest, container: AppContainer = Depends(get_container),
):
    repo = _repo(container)
    try:
        detail = await repo.get_session_detail(req.session_id)
    except KeyError as exc:
        raise HTTPException(404, "会话不存在") from exc
    session = detail["session"]
    version = None
    if session.get("dataset_version_id"):
        version = await repo.get_dataset_version(session["dataset_version_id"])
    generator = ReportGenerator()
    dataset_name = version.get("name") if version else "未绑定数据集"
    dataset_meta = [
        f"会话 ID: {req.session_id}",
        f"数据集: {dataset_name}",
        f"数据版本: {session.get('dataset_version_id') or '未记录'}",
    ]
    if version:
        dataset_meta.extend([
            f"记录数: {version.get('record_count', 0)}",
            f"数据适配器: {version.get('adapter', 'unknown')}",
            f"内容哈希: {version.get('content_hash', '')}",
        ])
    generator.add_section("报告与数据范围", "\n".join(dataset_meta))

    selected_turns = [
        turn for turn in detail.get("turns", [])
        if not req.turn_id or turn.get("id") == req.turn_id
    ]
    if req.turn_id and not selected_turns:
        raise HTTPException(404, "会话中不存在指定轮次")
    executions = detail.get("tool_executions", [])
    for turn in selected_turns:
        if turn.get("user_message"):
            generator.add_section("用户问题", turn["user_message"])
        if turn.get("final_text"):
            generator.add_section("Agent 综合结论", turn["final_text"])
        for execution in executions:
            if execution.get("turn_id") != turn.get("id"):
                continue
            result = execution.get("result") or {}
            lines = [
                f"状态: {execution.get('status', '')}",
                f"参数: {execution.get('parameters', {})}",
                f"耗时: {execution.get('duration_ms', 0)} ms",
            ]
            if result.get("summary"):
                lines.append(f"摘要: {result['summary']}")
            if result.get("methodology"):
                lines.append(f"方法: {result['methodology']}")
            warnings = result.get("warnings") or []
            if warnings:
                lines.append("警告: " + "；".join(str(item) for item in warnings))
            provenance = execution.get("provenance") or result.get("provenance") or {}
            if provenance:
                lines.append(f"证据追踪: {provenance}")
            generator.add_section(
                f"工具证据 · {execution.get('tool_name', 'unknown')}",
                "\n".join(lines),
                _structured_preview(result),
            )
    html = generator.generate_html(req.title)
    report_id = await repo.save_report(
        req.title, html, req.session_id, req.turn_id,
    )
    return {
        "report": {
            "id": report_id, "session_id": req.session_id,
            "turn_id": req.turn_id, "title": req.title, "format": "html",
            "download_url": f"/api/reports/{report_id}",
        }
    }


@router.get("/reports")
async def list_reports(container: AppContainer = Depends(get_container)):
    return {"reports": await _repo(container).list_reports()}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, container: AppContainer = Depends(get_container)):
    report = await _repo(container).get_report(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    return HTMLResponse(
        content=report["content_text"],
        headers={"Content-Disposition": f'inline; filename="{report_id}.html"'},
    )
