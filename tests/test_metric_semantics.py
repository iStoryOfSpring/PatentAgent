"""Public labels and aggregation modes preserve their declared statistical meaning."""

import asyncio

import pandas as pd

from engine.ipc_analysis import compute_ipc_year_matrix
from engine.trend import audit_publication_time_coverage
from storage.datastore import PatentDataStore
from tools import tool_registry


def test_ipc_counts_assignments_patents_and_families_separately():
    frame = pd.DataFrame({
        "patent_number": ["P1", "P2", "P3"],
        "year": [2024, 2024, 2024],
        "ipc": ["H01M;H02J;H01M", "H01M", "Z99Z"],
        "family_id": ["F1", "F1", "F2"],
    })

    assignments = compute_ipc_year_matrix(frame, "assignment_count")
    patents = compute_ipc_year_matrix(frame, "unique_patents")
    families = compute_ipc_year_matrix(frame, "family_normalized")

    h_index = assignments.sections.index("H")
    assert assignments.matrix[0][h_index] == 4
    assert patents.matrix[0][h_index] == 2
    assert families.matrix[0][h_index] == 1
    assert assignments.result_metadata["metric_label"] == "IPC 标注次数"
    assert assignments.result_metadata["invalid_ipc_count"] == 1
    assert assignments.sections == ["H"]


def test_ipc_tool_reports_the_algorithm_mode_actually_used():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2"],
        "publication_date": ["2024-01-01", "2024-02-01"],
        "date": ["2024-01-01", "2024-02-01"],
        "ipc": ["H01M", "H02J"],
    }))
    result = asyncio.run(tool_registry.get_tool("analyze_ipc_distribution").run(
        store, count_mode="unique_patents",
    ))
    assert result.algorithm_execution.mode_used == "unique_patents"
    assert result.provenance.algorithm_id == "ipc_publication_matrix_unique_patents"


def test_ten_or_eleven_month_tail_is_still_a_partial_calendar_year():
    frame = pd.DataFrame({
        "year": [2023] * 12 + [2024] * 11,
        "month": list(range(1, 13)) + list(range(1, 12)),
        "publication_date": [
            *[f"2023-{month:02d}-01" for month in range(1, 13)],
            *[f"2024-{month:02d}-01" for month in range(1, 12)],
        ],
    })

    audit, warnings = audit_publication_time_coverage(frame, "2024-11-30")

    assert audit["latest_year_is_partial_calendar_year"] is True
    assert len(audit["latest_year_months_covered"]) == 11
    assert any("部分自然年" in warning for warning in warnings)
