import asyncio

import numpy as np
import pandas as pd

from engine.clustering import generate_cluster_title, _select_cluster_count
from engine.nlp import compute_burst_terms
from engine.parser import PatentMiner
from engine.adapters.wos_adapter import WoSAdapter
from engine.valuation import compute_patent_value_indicators
from engine.citation import (
    build_citation_graph, compute_bibliographical_coupling,
    compute_reachability_out_degree, compute_shared_specialization,
)
from agent.llm import ChatResponse
from agent.orchestrator import PatentAgentOrchestrator, IntentAnalysis
from models.analysis_results import WordFreqResult
from models.session import ToolExecution
from storage.datastore import PatentDataStore
from tools import tool_registry
from tools.search_tool import SearchTool


def test_wos_cp_is_citation_cr_is_not_and_no_self_loop(tmp_path):
    record = """PT P
PN US2020000001-A1; US1111111-B2
TI Example patent
AB NOVELTY - A separator. USE - filtration. ADVANTAGE - lower pressure.
AE EXAMPLE CO
AU DOE J
IP B01D-001/00
PD US2020000001-A1   02 Jan 2020
FD US1111111-B2 Previous Publ. Patent US2020000001
CP US2020000001-A1
   US9999999-B2
CR US2020000001-A1
   JOURNAL ARTICLE 2019
ER
"""
    path = tmp_path / "gold.txt"
    path.write_text(record, encoding="utf-8")
    row = PatentMiner(str(tmp_path)).parse_txt(str(path)).iloc[0]
    assert row.patent_number == "US2020000001-A1"
    assert row.cited_refs == "US9999999-B2"
    assert "US1111111-B2" in row.family_members
    assert row.publication_date == row.date == "2020-01-02"


def test_wos_keeps_ut_publication_priority_and_nonpatent_fields(tmp_path):
    record = """PT P
UT DIIDW:2024-ABC123
PN EP1234567-A1; WO2024123456-A1
TI Example
AB NOVELTY - separator. USE - filtration. ADVANTAGE - lower pressure.
PI EP202300001 01 Jan 2023
PD EP1234567-A1 02 Jan 2024
CR JOURNAL OF FILTERS 2020; STANDARD ISO 123
ER
"""
    path = tmp_path / "fields.txt"
    path.write_text(record, encoding="utf-8")
    row = PatentMiner(str(tmp_path)).parse_txt(str(path)).iloc[0]
    assert row.source_record_id == "DIIDW:2024-ABC123"
    assert row.publication_numbers == "EP1234567-A1;WO2024123456-A1"
    assert "EP202300001" in row.priority_numbers
    assert "JOURNAL OF FILTERS 2020" in row.non_patent_references


def test_adapter_deduplicates_overlapping_batches_by_ut(tmp_path):
    template = """FN Clarivate Analytics Web of Science
VR 1.0
ER

PT P
UT DIIDW:DUPLICATE-1
PN EP1234567-A1
TI Example {suffix}
AB Example abstract
AE EXAMPLE CO
IP H01M-001/00
PD EP1234567-A1 02 Jan 2024
ER
EF
"""
    (tmp_path / "batch1.txt").write_text(template.format(suffix="one"), encoding="utf-8")
    (tmp_path / "batch2.txt").write_text(template.format(suffix="two"), encoding="utf-8")
    frame = WoSAdapter().batch_parse(str(tmp_path))
    assert len(frame) == 1
    assert frame.iloc[0].source_record_id == "DIIDW:DUPLICATE-1"


def test_von_wartburg_adapted_formula_on_hand_network():
    import networkx as nx
    graph = nx.DiGraph()
    graph.add_edges_from([
        ("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"),
        ("E", "C"),
    ])
    assert compute_reachability_out_degree(graph, "A", max_depth=3) == 2.0
    assert round(compute_bibliographical_coupling(graph, "A"), 4) == 0.6667
    ss = compute_shared_specialization(graph, "A")
    assert ss["shared_specialization"] == 2.6667


def test_family_graph_collapses_publication_alias_and_removes_self_loop():
    from types import SimpleNamespace
    patents = [
        SimpleNamespace(
            patent_number="EP-1-A1", publication_numbers=["EP-1-A1", "WO-1-A1"],
            family_members=["US-1-A1"], backward_citations=["WO1A1"],
            title="family", publication_date="2020-01-01",
        )
    ]
    graph = build_citation_graph(patents)
    assert graph.number_of_nodes() == 1
    assert graph.number_of_edges() == 0


def test_cc05_requires_majority_and_prefers_cluster_specific_term():
    # 3 cluster docs out of 6; alpha appears in all cluster docs and no outside docs.
    all_vectors = np.array([
        [1, 1], [1, 1], [1, 0], [0, 1], [0, 1], [0, 0],
    ], dtype=float)
    title = generate_cluster_title(
        all_vectors[:3], ["alpha", "common"], 0,
        all_vectors=all_vectors, top_k=1,
    )
    assert title == "alpha"


def test_k_selection_reports_silhouette_and_stability():
    from scipy.sparse import csr_matrix
    vectors = csr_matrix(np.array([
        [1.0, 0.0], [0.9, 0.1], [1.0, 0.1],
        [0.0, 1.0], [0.1, 0.9], [0.1, 1.0],
    ]))
    selected, diagnostics = _select_cluster_count(vectors)
    assert selected == 2
    assert diagnostics["candidates"][0]["mean_cosine_silhouette"] > 0
    assert diagnostics["candidates"][0]["adjusted_rand_stability"] == 1.0


def test_recent_growth_filters_singleton_noise():
    yearly = {
        2019: ["battery cell"] * 5,
        2020: ["battery cell"] * 5,
        2021: ["battery cell"] * 5,
        2022: ["solid electrolyte"] * 6 + ["singletonnoise"],
    }
    result = compute_burst_terms(yearly, top_n=20, min_support=3)
    terms = {item["term"] for item in result.data}
    assert "singletonnoise" not in terms


def test_triadic_definition_is_us_ep_jp():
    class Patent:
        patent_number = "US1"
        title = "x"
        publication_date = "2020-01-01"
        family_members = ["EP1", "JP1"]
        ipc_codes = ["H01M"]
        backward_citations = []
        claims = []

    item = compute_patent_value_indicators([Patent()]).data[0]
    assert item["is_triadic"] == 1


def test_tool_contract_rejects_empty_search_query():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["US1"], "title": ["battery"],
        "abstract": ["cell"], "date": ["2020-01-01"],
    }))
    try:
        asyncio.run(SearchTool().run(store, query=""))
    except ValueError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("empty query should fail validation")


def test_tool_contract_exposes_non_breaking_visualization_hint():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["US1", "US2"],
        "title": ["battery", "cell"],
        "abstract": ["storage", "electrode"],
        "publication_date": ["2020-01-02", "2020-02-03"],
        "date": ["2020-01-02", "2020-02-03"],
        "ipc": ["H01M", "H01M"],
        "applicants": ["A", "B"],
    }))
    result = asyncio.run(
        tool_registry.get_tool("analyze_patent_trend").run(store),
    )
    assert result.result_metadata["visualization"] == {
        "kind": "line", "width": 960, "height": 520,
        "default_mode": "natural",
    }


def test_registry_covers_every_registered_tool_and_declares_boundaries():
    from tools.evidence import load_evidence_registry
    registry = load_evidence_registry()["tools"]
    assert set(registry) == set(tool_registry.get_all_names())
    for name, record in registry.items():
        assert record["algorithm_id"], name
        assert record["version"], name
        assert record["evidence_type"] in {
            "descriptive_statistic", "paper_exact", "paper_adapted",
            "engineering_screening",
        }
        assert isinstance(record["prohibited_claims"], list)


def test_audit_separates_external_forward_and_internal_network():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["EP1", "EP2"],
        "publication_numbers": ["EP1", "EP2"],
        "title": ["a", "b"], "abstract": ["x", "y"],
        "publication_date": ["2020-01-01", "2021-01-01"],
        "date": ["2020-01-01", "2021-01-01"],
        "ipc": ["H01M", "H01M"], "applicants": ["A", "B"],
        "backward_citations": ["EP2", ""],
        "forward_citations": ["", ""],
    }))
    audit = store.audit()
    assert audit["external_forward_citation_coverage"] == 0.0
    assert audit["internal_citation_network"]["resolved_internal_edges"] == 1
    assert audit["internal_citation_network"]["scope"] == "internal_corpus_only"


def test_quality_warnings_are_conditional_and_only_reach_affected_tools():
    base = {
        "patent_number": ["EP1", "EP2"], "title": ["a", "b"],
        "abstract": ["x", "y"],
        "publication_date": ["2020-01-01", "2021-01-01"],
        "date": ["2020-01-01", "2021-01-01"],
        "ipc": ["H01M", "H01M"], "applicants": ["A", "B"],
        "forward_citations": ["", ""], "claims_json": ["", ""],
        "legal_status": ["", ""],
    }
    store = PatentDataStore(pd.DataFrame(base))
    trend = asyncio.run(tool_registry.get_tool("analyze_patent_trend").run(store))
    assert not any("FTO" in warning or "前向被引" in warning for warning in trend.warnings)

    enriched = dict(base)
    enriched.update({
        "forward_citations": ["EP3", "EP4"],
        "claims_json": ["1. claim", "1. claim"],
        "legal_status": ["active", "active"],
    })
    audit = PatentDataStore(pd.DataFrame(enriched)).audit()
    codes = {item["code"] for item in audit["warning_records"]}
    assert "external_forward_citations_missing" not in codes
    assert "fto_fields_missing" not in codes


def test_cooperation_availability_enforces_evidence_gate():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": [f"EP{i}" for i in range(40)],
        "applicants": ["A;B"] * 29 + ["A"] * 11,
        "date": ["2020-01-01"] * 40,
    }))
    availability = tool_registry.get_tool("analyze_co_network").availability(store)
    assert availability["available"] is False
    assert "30 件" in availability["reason"]


def test_value_tool_downgrades_mixed_open_network_and_excludes_ss():
    rows = []
    for i in range(4):
        rows.append({
            "patent_number": f"US{i}", "publication_numbers": f"US{i}",
            "title": "battery", "abstract": "cell",
            "publication_date": f"202{i}-01-01", "date": f"202{i}-01-01",
            "ipc": "H01M", "applicants": "A",
            "backward_citations": "US0" if i else "",
            "family_members": "EP1;JP1" if i == 1 else "",
        })
    store = PatentDataStore(pd.DataFrame(rows))
    result = asyncio.run(tool_registry.get_tool("analyze_patent_valuation").run(
        store, top_n=4, citation_mode="replication",
    ))
    assert result.result_metadata["citation_method_mode"] == "engineering_screening"
    assert result.result_metadata["paper_exact"] is False
    assert "shared_specialization" not in result.data[0]["scoring_dimensions"]


def test_intent_filters_are_attached_to_every_chain_step():
    class NoopLLM:
        pass

    agent = PatentAgentOrchestrator(NoopLLM(), tool_registry)
    params = agent._merge_intent_params(
        "analyze_patent_trend", {"chart_type": "yearly"},
        IntentAnalysis(
            goal="battery trend", tech_field="solid battery",
            applicants=["ACME"], ipc_codes=["H01M"],
            time_range=(2020, 2022),
        ),
    )
    assert params["year_start"] == 2020
    assert params["applicant_filter"] == "ACME"
    assert params["__filters"] == {
        "year_start": 2020, "year_end": 2022,
        "applicant_filter": "ACME", "ipc_filter": ["H01M"],
        "text_query": "solid battery",
    }


def test_evidence_channel_reads_every_large_result_chunk():
    class RecordingLLM:
        def __init__(self):
            self.prompts = []

        async def chat(self, messages):
            self.prompts.append(messages[0]["content"])
            return ChatResponse(text="chunk read")

    llm = RecordingLLM()
    agent = PatentAgentOrchestrator(llm, tool_registry)
    data = [{"word": f"unique_{i}", "count": i} for i in range(80)]
    data[-1]["word"] = "FINAL_UNIQUE_MARKER"
    execution = ToolExecution(
        id="e1", tool_name="generate_wordcloud", parameters={},
        status="completed", result=WordFreqResult(data=data),
    )
    _, coverage = asyncio.run(
        agent._build_evidence_context([execution], chunk_size=100),
    )
    assert "FINAL_UNIQUE_MARKER" in "".join(llm.prompts)
    assert coverage[0]["chunks"] > 1
    assert coverage[0]["omitted"] is False
