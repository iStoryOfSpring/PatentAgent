"""Gated family-citation route with an annual-theme fallback."""

import re

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from engine import roadmap
from models.analysis_results import RoadmapResult
from patent_agent.domain import AlgorithmExecution


class RoadmapTool(Tool):
    name = "analyze_tech_roadmap"
    description = (
        "默认生成按公开年度组织的主题时间线；仅在同族、优先权时间和内部引证"
        "覆盖门禁通过时，附加可追溯的同族引证路线草稿。"
    )
    parameters = {
        "top_n_per_year": {
            "type": "integer",
            "description": "每年展示的专利数量。默认 3。",
            "default": 3,
            "minimum": 1,
            "maximum": 20,
        },
    }
    required_fields = ("publication_date", "title", "patent_number")
    optional_fields = ("backward_citations", "family_members", "priority_date")
    methodology = "低覆盖时按公开年度生成主题时间线；高覆盖时按来源同族归并、优先权时间和 citing→cited 证据生成待复核路线。"
    evidence_level = "engineering_approximation"

    async def execute(self, storage: PatentDataStore,
                      top_n_per_year: int = 3) -> RoadmapResult:
        df = storage.get_columns([
            'year', 'date', 'publication_date', 'patent_number', 'title',
            'backward_citations', 'cited_refs', 'family_id', 'family_members',
            'priority_date', 'ipc',
        ])
        result = roadmap.compute_roadmap_data(df, top_n_per_year=top_n_per_year)
        audit = storage.audit()["internal_citation_network"]
        route_gate = {
            "internal_edge_resolution_rate": audit["edge_resolution_rate"],
            "family_id_coverage": storage.field_coverage("family_id"),
            "priority_date_coverage": storage.field_coverage("priority_date"),
        }
        route_enabled = (
            route_gate["internal_edge_resolution_rate"] >= .2
            and route_gate["family_id_coverage"] >= .5
            and route_gate["priority_date_coverage"] >= .8
        )
        route = _family_citation_route(df) if route_enabled else {
            "nodes": [], "edges": [], "main_paths": [], "anomalous_edges": [],
        }
        result.result_metadata.update({
            "capability_name": (
                "family_citation_route_draft" if route_enabled
                else "annual_theme_timeline"
            ),
            "legacy_tool_name": self.name,
            "citation_route_gate": route_gate,
            "citation_paths_generated": bool(route["main_paths"]),
            "route_nodes": route["nodes"],
            "route_edges": route["edges"],
            "main_paths": route["main_paths"],
            "anomalous_edges": route["anomalous_edges"],
        })
        if route_enabled:
            result.warnings.append(
                "同族引证路线仅为来源边与时间约束生成的待复核草稿，不代表因果技术谱系。"
            )
            result.algorithm_execution = AlgorithmExecution(
                algorithm_id="family_citation_route_draft",
                algorithm_version="1.0",
                mode_requested="auto",
                mode_used="family_citation_route_draft",
                parameters={"top_n_per_year": top_n_per_year, **route_gate},
            )
        else:
            result.warnings.append(
                "同族、优先权时间或内部引证覆盖门禁未通过，仅生成年度主题时间线。"
            )
            result.algorithm_execution = AlgorithmExecution(
                algorithm_id="annual_theme_timeline", algorithm_version="2.2",
                mode_requested="auto", mode_used="annual_theme_timeline",
                fallback_reason="citation_route_gate_failed",
                parameters={"top_n_per_year": top_n_per_year, **route_gate},
            )
        return result


tool_registry.register(RoadmapTool())


def _split(value) -> list[str]:
    return [
        item.strip() for item in re.split(r"[;\n]+", str(value or ""))
        if item.strip()
    ]


def _family_citation_route(df):
    """Build only source-backed, time-respecting family edges."""
    import networkx as nx

    rows = {
        str(row.get("patent_number", "")): row for _, row in df.iterrows()
        if str(row.get("patent_number", "")).strip()
    }
    family_for = {
        patent_number: str(row.get("family_id", "") or patent_number)
        for patent_number, row in rows.items()
    }
    grouped: dict[str, list[tuple[str, object]]] = {}
    for patent_number, row in rows.items():
        grouped.setdefault(family_for[patent_number], []).append((patent_number, row))
    graph = nx.DiGraph()
    nodes = {}
    for family_id, members in grouped.items():
        ordered = sorted(members, key=lambda item: (
            str(item[1].get("priority_date", "") or "9999"), item[0],
        ))
        representative_number, representative = ordered[0]
        nodes[family_id] = {
            "family_id": family_id,
            "representative_patent_number": representative_number,
            "member_patent_numbers": sorted(item[0] for item in members),
            "priority_date": str(representative.get("priority_date", "") or ""),
            "technology_elements": sorted({
                code[:4].upper() for _, row in members
                for code in _split(row.get("ipc")) if len(code) >= 4
            }),
            "review_status": "unreviewed",
        }
        graph.add_node(family_id)
    edge_evidence: dict[tuple[str, str], list[dict]] = {}
    anomalies = []
    for citing_number, citing_row in rows.items():
        citing_family = family_for[citing_number]
        citing_date = str(citing_row.get("priority_date", "") or "")
        for cited_number in _split(
            citing_row.get("backward_citations", citing_row.get("cited_refs", ""))
        ):
            if cited_number not in rows:
                continue
            cited_family = family_for[cited_number]
            if cited_family == citing_family:
                continue
            cited_date = str(rows[cited_number].get("priority_date", "") or "")
            evidence = {
                "citing_patent_number": citing_number,
                "cited_patent_number": cited_number,
                "source_field": "backward_citations",
                "review_status": "unreviewed",
            }
            if citing_date and cited_date and cited_date > citing_date:
                anomalies.append({**evidence, "reason": "cited_priority_after_citing_priority"})
                continue
            # Route time runs from earlier cited family to later citing family.
            edge_evidence.setdefault((cited_family, citing_family), []).append(evidence)
            graph.add_edge(cited_family, citing_family)
    main_paths = []
    if graph.number_of_edges() and nx.is_directed_acyclic_graph(graph):
        path = nx.algorithms.dag.dag_longest_path(graph)
        if len(path) >= 2:
            main_paths.append({
                "method": "longest_time_respecting_family_citation_path",
                "family_ids": path,
                "review_status": "unreviewed",
            })
    edges = [{
        "source_family_id": source,
        "target_family_id": target,
        "evidence": evidence,
        "review_status": "unreviewed",
    } for (source, target), evidence in sorted(edge_evidence.items())]
    for family_id, node in nodes.items():
        node["incoming_edge_count"] = int(graph.in_degree(family_id))
        node["outgoing_edge_count"] = int(graph.out_degree(family_id))
    return {
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": edges, "main_paths": main_paths,
        "anomalous_edges": anomalies,
    }
