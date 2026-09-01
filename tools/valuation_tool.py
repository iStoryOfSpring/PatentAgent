"""Tool: 专利价值筛查（工程指标 + 受门禁约束的论文适配指标）"""

from tools.base import Tool, tool_registry
from storage.datastore import PatentDataStore
from models.analysis_results import ValueIndicators


class ValuationTool(Tool):
    name = "analyze_patent_valuation"
    description = (
        "对专利进行多维度价值筛查和排名，并报告日期、同族与引证覆盖率。"
        "适用于用户询问'价值'、'排名'、'核心专利'、'重要专利'等关键词。"
    )
    parameters = {
        "top_n": {
            "type": "integer",
            "description": "返回Top N高价值专利。默认 20。",
            "minimum": 1,
            "maximum": 100,
            "default": 20,
        },
        "citation_mode": {
            "type": "string",
            "enum": ["auto", "screening", "replication"],
            "description": "auto 自动按数据门禁选择；screening 不把 SS 纳入评分；replication 请求论文适配复现。",
            "default": "auto",
        },
    }
    required_fields = ("patent_number", "publication_date", "ipc")
    optional_fields = ("backward_citations", "family_members", "forward_citations")
    methodology = "数据集内稳健百分位价值筛查；引证充分时使用三阶段可达性与耦合指标，字段不足时明确降级。"
    evidence_level = "paper_informed_screening"

    async def execute(self, storage: PatentDataStore,
                      top_n: int = 20,
                      citation_mode: str = "auto") -> ValueIndicators:
        from engine.valuation import rank_patents_by_value, DEFAULT_WEIGHTS
        from engine.citation import build_citation_graph
        from tools.search_tool import _row_to_pseudo_patent

        df = storage.get_columns(['patent_number', 'publication_numbers', 'title', 'abstract',
                                   'publication_date', 'date', 'ipc', 'cited_refs',
                                   'backward_citations',
                                   'family_members', 'forward_citations', 'source_file'])
        patents = []
        for _, row in df.iterrows():
            patent = _row_to_pseudo_patent(row)
            patent.source_format = storage.adapter_name or "unknown"
            patent.source_availability = {
                "publication_date": _has_value(row.get("publication_date", row.get("date"))),
                "ipc": _has_value(row.get("ipc")),
                "backward_citations": _has_value(
                    row.get("backward_citations", row.get("cited_refs"))
                ),
                "family_members": _has_value(row.get("family_members")),
            }
            patents.append(patent)

        # 全量语料直接使用完整内部引证图，不对全体用随机子图评分。
        audit_full = storage.audit()
        audit = audit_full["field_coverage"]
        network = audit_full["internal_citation_network"]
        citation_coverage = audit.get("backward_citations", 0.0)
        family_coverage = audit.get("family_members", 0.0)
        replication_gates = {
            "family_coverage_at_least_50pct": family_coverage >= 0.5,
            "internal_edge_resolution_at_least_20pct": network["edge_resolution_rate"] >= 0.2,
            "european_style_share_at_least_80pct": network["european_style_share"] >= 0.8,
        }
        requested_replication = citation_mode == "replication"
        use_ss = citation_mode != "screening" and all(replication_gates.values())
        graph = build_citation_graph(patents)
        scoring_weights = dict(DEFAULT_WEIGHTS)
        if not use_ss:
            scoring_weights.pop("shared_specialization", None)
        if family_coverage < 0.5:
            scoring_weights.pop("is_triadic", None)
            scoring_weights.pop("family_size", None)
        ranked = rank_patents_by_value(
            patents, weights=scoring_weights,
            citation_graph=graph if use_ss else None,
        )
        applied_mode = "paper_adapted_replication" if use_ss else "engineering_screening"
        coverage = {
            "publication_date": audit.get("publication_date", 0.0),
            "family_members": audit.get("family_members", 0.0),
            "backward_citations": citation_coverage,
            "network_nodes": graph.number_of_nodes(),
            "network_edges": graph.number_of_edges(),
            "internal_edge_resolution_rate": network["edge_resolution_rate"],
            "european_style_share": network["european_style_share"],
        }
        result = ValueIndicators(
            result_type="value_indicators", data=ranked[:top_n], coverage=coverage,
            score_label="数据集内相对工程筛查分",
            result_metadata={
                "population_size": len(df), "sampled": False,
                "citation_method_mode": applied_mode,
                "requested_citation_mode": citation_mode,
                "replication_gates": replication_gates,
                "paper_exact": False,
                "ranking_scope": "within_source_and_available_dimension_group",
                "citation_normalization": "publication_year_by_ipc_subclass",
                "missing_values_treated_as_zero": False,
                "sensitivity_analysis": _ranking_sensitivity(
                    patents, scoring_weights, graph if use_ss else None, ranked, top_n,
                ),
            },
        )
        if not use_ss:
            result.warnings.append(
                "当前数据不满足论文复现门禁，SS/RO/BC 未进入价值筛查分；结果为工程筛查，不是财务估值。"
            )
        if requested_replication and not use_ss:
            failed = [name for name, passed in replication_gates.items() if not passed]
            result.warnings.append("论文适配复现请求已降级，未通过门禁: " + ", ".join(failed))
        low_confidence = sum(item["confidence_level"] == "low" for item in ranked)
        incomparable = sum(not item["comparable_within_group"] for item in ranked)
        if low_confidence:
            result.warnings.append(
                f"{low_confidence} 件记录可用评分权重低于 60%，请结合分数区间而非点估计解读。"
            )
        if incomparable:
            result.warnings.append(
                f"{incomparable} 件记录没有同来源、同维度的可比对象，不应与其他组直接混排。"
            )
        return result


tool_registry.register(ValuationTool())


def _ranking_sensitivity(patents, weights, graph, baseline, top_n: int) -> dict:
    """Report how much the top set moves under a ±20% one-factor perturbation."""
    from engine.valuation import rank_patents_by_value

    baseline_ids = [item["patent_number"] for item in baseline[:top_n]]
    baseline_set = set(baseline_ids)
    scenarios = []
    for dimension in sorted(weights):
        for factor in (0.8, 1.2):
            perturbed = dict(weights)
            perturbed[dimension] *= factor
            ranked = rank_patents_by_value(
                patents, weights=perturbed, citation_graph=graph,
            )
            candidate = [item["patent_number"] for item in ranked[:top_n]]
            overlap = len(baseline_set.intersection(candidate)) / max(1, len(baseline_set))
            scenarios.append({
                "dimension": dimension, "factor": factor,
                "top_n_overlap": round(overlap, 4),
            })
    return {
        "method": "one_factor_weight_perturbation",
        "perturbation": 0.2,
        "top_n": min(top_n, len(baseline_ids)),
        "minimum_top_n_overlap": min(
            (item["top_n_overlap"] for item in scenarios), default=1.0,
        ),
        "scenarios": scenarios,
        "missingness": {
            "records_with_missing_dimensions": sum(
                bool(item.get("missing_dimensions")) for item in baseline
            ),
            "minimum_available_weight_ratio": min(
                (item.get("available_weight_ratio", 0.0) for item in baseline),
                default=0.0,
            ),
            "maximum_score_interval_width": max(
                (
                    item.get("score_interval", [0.0, 100.0])[1]
                    - item.get("score_interval", [0.0, 100.0])[0]
                    for item in baseline
                ),
                default=0.0,
            ),
        },
        "interpretation": "衡量权重扰动下的排名稳定性，不是现实商业价值校准。",
    }


def _has_value(value) -> bool:
    """Treat blank/absent source cells as missing, never as a measured zero."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    try:
        import pandas as pd
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True
