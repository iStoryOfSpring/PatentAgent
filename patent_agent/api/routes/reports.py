"""Report export route backed by the report application service."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import ExportRequest
from patent_agent.application import ReportService
from patent_agent.infrastructure import AppContainer
from reporting import ReportGenerator


router = APIRouter(prefix="/api/report", tags=["reports"])


@router.post("/export")
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
