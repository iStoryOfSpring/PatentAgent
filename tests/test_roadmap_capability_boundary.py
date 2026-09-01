import asyncio

import pandas as pd

from storage.datastore import PatentDataStore
from tools.roadmap_tool import RoadmapTool


def test_public_roadmap_tool_declares_timeline_boundary():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2"],
        "title": ["solid battery", "solid electrolyte"],
        "abstract": ["battery", "electrolyte"],
        "publication_date": ["2023-01-01", "2024-01-01"],
        "date": ["2023-01-01", "2024-01-01"],
        "ipc": ["H01M", "H01M"],
        "applicants": ["A", "A"],
        "backward_citations": ["P0", "P1"],
    }))
    result = asyncio.run(RoadmapTool().run(store, top_n_per_year=1))
    assert result.result_metadata["capability_name"] == "annual_theme_timeline"
    assert result.result_metadata["citation_paths_generated"] is False
    assert any("门禁未通过" in warning for warning in result.warnings)
    assert "待复核路线" in result.methodology


def test_roadmap_emits_only_source_backed_time_respecting_family_path():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2", "P3"],
        "title": ["cell", "electrolyte", "battery pack"],
        "abstract": ["a", "b", "c"],
        "publication_date": ["2020-01-01", "2021-01-01", "2022-01-01"],
        "priority_date": ["2019-01-01", "2020-01-01", "2021-01-01"],
        "date": ["2020-01-01", "2021-01-01", "2022-01-01"],
        "ipc": ["H01M", "H01M", "H02J"],
        "applicants": ["A", "B", "C"],
        "family_id": ["F1", "F2", "F3"],
        "family_members": ["P1", "P2", "P3"],
        "backward_citations": ["", "P1", "P2"],
    }))
    result = asyncio.run(RoadmapTool().run(store, top_n_per_year=1))
    assert result.result_metadata["capability_name"] == "family_citation_route_draft"
    assert result.result_metadata["citation_paths_generated"] is True
    edges = result.result_metadata["route_edges"]
    assert [(edge["source_family_id"], edge["target_family_id"]) for edge in edges] == [
        ("F1", "F2"), ("F2", "F3"),
    ]
    assert all(edge["evidence"] for edge in edges)
