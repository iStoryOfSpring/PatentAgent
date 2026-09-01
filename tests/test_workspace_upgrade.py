import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from patent_agent.api.routes.datasets import router as datasets_router
from patent_agent.api.routes.reports import router as reports_router
from patent_agent.api.routes.sessions import router as sessions_router
from patent_agent.api.routes.tools import router as tools_router
from patent_agent.application import DatasetImportService, DatasetRuntimeManager, ReportService
from patent_agent.infrastructure import AppContainer, AppSettings
from reporting import ReportGenerator
from storage.conversation_store import ConversationStore


def _app(tmp_path: Path) -> tuple[FastAPI, AppContainer]:
    settings = AppSettings(
        project_root=tmp_path,
        data_root=tmp_path / "data",
        input_dir=str(tmp_path / "data"),
        session_db=tmp_path / "sessions.db",
        cors_origins=("http://localhost:5173",),
        max_upload_file_bytes=2 * 1024 * 1024,
        max_upload_total_bytes=4 * 1024 * 1024,
    )
    settings.data_root.mkdir(parents=True)
    container = AppContainer(settings)
    container.conversation_store = ConversationStore(settings.session_db)
    asyncio.run(container.conversation_store.initialize())
    container.dataset_service = DatasetImportService()
    container.dataset_runtime = DatasetRuntimeManager(
        container.conversation_store, container.dataset_service,
    )
    container.report_service = ReportService(ReportGenerator)
    app = FastAPI()
    app.state.container = container
    app.include_router(datasets_router)
    app.include_router(sessions_router)
    app.include_router(tools_router)
    app.include_router(reports_router)
    return app, container


def test_upload_library_session_binding_and_capabilities(tmp_path):
    app, container = _app(tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "official_formats" / "google_patents_sample.jsonl"
    with TestClient(app) as client, fixture.open("rb") as handle:
        response = client.post(
            "/api/datasets/imports",
            data={"name": "演示数据", "source_format": "google_patents_jsonl"},
            files={"files": (fixture.name, handle, "application/json")},
        )
        assert response.status_code == 202
        import_id = response.json()["import_id"]
        imported = client.get(f"/api/imports/{import_id}").json()["import"]
        assert imported["status"] == "completed"
        assert imported["metrics"]["record_count"] > 0

        datasets = client.get("/api/datasets").json()["datasets"]
        assert datasets[0]["name"] == "演示数据"
        version_id = imported["dataset_version_id"]
        session = client.post(
            "/api/sessions",
            json={"name": "绑定会话", "dataset_version_id": version_id},
        ).json()
        assert session["dataset_version_id"] == version_id

        groups = client.get("/api/capabilities").json()["capabilities"]
        assert len(groups) == 9
        assert {group["id"] for group in groups} == {
            "patent_search", "technology_landscape", "technology_topics",
            "competition", "technology_roadmap", "value_opportunity",
            "citation_family", "search_monitor", "legal_claims",
        }
    assert container.store is not None


def test_explicit_rebind_stales_evidence_and_persistent_report(tmp_path):
    app, container = _app(tmp_path)
    repo = container.conversation_store

    async def seed():
        session = await repo.create_session(
            "报告会话", "fingerprint-a", dataset_version_id="version-a",
        )
        turn = await repo.start_turn(
            session["id"], "分析趋势", dataset_version_id="version-a",
        )
        await repo.record_execution(
            session["id"], turn, "exec-a", "analyze_patent_trend", {},
            "completed", {"summary": "公开量上升", "methodology": "年度计数"},
            dataset_fingerprint="fingerprint-a",
        )
        await repo.finish_turn(session["id"], turn, "总体呈上升趋势。")
        _, stale_count = await repo.bind_session_dataset(
            session["id"], "version-b", "fingerprint-b",
        )
        return session["id"], stale_count

    session_id, stale_count = asyncio.run(seed())
    assert stale_count == 1
    assert asyncio.run(repo.get_evidence(session_id)) == []

    with TestClient(app) as client:
        created = client.post(
            "/api/reports",
            json={"session_id": session_id, "title": "导师演示报告"},
        )
        assert created.status_code == 200
        report_id = created.json()["report"]["id"]
        html = client.get(f"/api/reports/{report_id}")
        assert html.status_code == 200
        assert "导师演示报告" in html.text
        assert "总体呈上升趋势" in html.text
        assert "analyze_patent_trend" in html.text
