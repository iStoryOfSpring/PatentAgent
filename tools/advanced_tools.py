"""Auditable portfolio, network, family, strategy, monitoring and claim tools."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

import numpy as np
import pandas as pd

from engine.entity_resolution import resolve_semicolon_names
from models.analysis_results import GenericAnalysisResult
from storage.datastore import PatentDataStore
from tools.base import Tool, tool_registry


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(";") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _year(value: Any) -> int | None:
    match = re.match(r"(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


def _office(value: Any) -> str:
    match = re.match(r"([A-Za-z]{2})", re.sub(r"[^A-Za-z0-9]", "", str(value or "")))
    return match.group(1).upper() if match else "UNKNOWN"


def _party_names(row: pd.Series, entity_type: str) -> list[tuple[str, str, str]]:
    """Return entity_id, canonical name and raw alias without inventing party roles."""
    if entity_type in {"applicant", "inventor"}:
        raw_field = "applicants" if entity_type == "applicant" else "inventors"
        resolved = resolve_semicolon_names(row.get(raw_field, ""), entity_type)
        return [(item.entity_id, item.canonical_name, item.original_name) for item in resolved]
    json_field = {
        "assignee": "assignee_parties_json",
        "owner": "current_rights_holder_parties_json",
    }[entity_type]
    try:
        parties = json.loads(str(row.get(json_field, "") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        parties = []
    names = [item.get("name", "") for item in parties if isinstance(item, dict)]
    resolved = resolve_semicolon_names(names, entity_type)
    return [(item.entity_id, item.canonical_name, item.original_name) for item in resolved]


class EntityPortfolioTool(Tool):
    name = "analyze_entity_portfolio"
    description = "按规范化申请人、受让人、当前权利人或发明人统计组合排名、年度公开趋势与 IPC 构成。"
    parameters = {
        "entity_type": {"type": "string", "enum": ["applicant", "assignee", "owner", "inventor"], "default": "applicant"},
        "metric": {"type": "string", "enum": ["publications", "families", "grants", "citations"], "default": "publications"},
        "top_n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        "group_by_parent": {"type": "boolean", "default": False},
        "reviewed_parent_map": {"type": "array", "maxItems": 500, "items": {"type": "object"}, "default": []},
    }
    required_fields = ("patent_number",)
    optional_fields = ("applicants", "inventors", "family_members", "forward_citations")
    methodology = "确定性名称规范化后的实体组合描述统计；不自动进行母子公司或并购历史归并。"

    async def execute(
        self, storage: PatentDataStore, entity_type="applicant",
        metric="publications", top_n=20, group_by_parent=False,
        reviewed_parent_map=[],
    ):
        role_field = {
            "applicant": "applicants", "inventor": "inventors",
            "assignee": "assignee_parties_json", "owner": "current_rights_holder_parties_json",
        }[entity_type]
        if storage.field_coverage(role_field) == 0:
            raise ValueError(f"当前数据没有可区分的 {entity_type} 角色字段")
        metric_field = {
            "families": "family_members", "grants": "grant_date",
            "citations": "forward_citations",
        }.get(metric)
        if metric_field and storage.field_coverage(metric_field) == 0:
            raise ValueError(f"指标 {metric} 需要来源字段 {metric_field}")
        df = storage.get_all()
        parent_map = {}
        for mapping in reviewed_parent_map or []:
            if not isinstance(mapping, dict) or mapping.get("reviewed") is not True:
                continue
            parent_name = str(mapping.get("parent_name", "") or "").strip()
            child = str(
                mapping.get("entity_id", "") or mapping.get("canonical_name", "") or ""
            ).strip()
            if parent_name and child:
                parent_map[child.casefold()] = parent_name
        rows: dict[str, dict] = {}
        unresolved = 0
        for _, record in df.iterrows():
            parties = _party_names(record, entity_type)
            if not parties:
                unresolved += 1
                continue
            family_key = str(record.get("family_id", "") or record.get("patent_number", ""))
            year = _year(record.get("publication_date", record.get("date")))
            ipc = sorted({code[:4].upper() for code in _values(record.get("ipc")) if len(code) >= 4})
            seen_record_entities = set()
            for entity_id, canonical, alias in parties:
                parent_name = (
                    parent_map.get(entity_id.casefold()) or
                    parent_map.get(canonical.casefold())
                ) if group_by_parent else None
                resolved_id = (
                    "parent:" + hashlib.sha256(parent_name.casefold().encode()).hexdigest()[:20]
                    if parent_name else entity_id
                )
                item = rows.setdefault(resolved_id, {
                    "entity_id": resolved_id,
                    "canonical_name": parent_name or canonical,
                    "aliases": set(), "record_ids": set(), "families": set(),
                    "grants": 0, "citations": 0, "yearly": Counter(), "ipc": Counter(),
                    "parent_group": parent_name,
                })
                item["aliases"].add(alias)
                if resolved_id in seen_record_entities:
                    continue
                seen_record_entities.add(resolved_id)
                item["record_ids"].add(str(record.get("patent_number", "")))
                item["families"].add(family_key)
                item["grants"] += bool(str(record.get("grant_date", "")).strip())
                item["citations"] += len(_values(record.get("forward_citations")))
                if year:
                    item["yearly"][year] += 1
                item["ipc"].update(ipc)
        metric_key = {"publications": "record_count", "families": "family_count", "grants": "grant_count", "citations": "forward_citation_count"}[metric]
        output = []
        for item in rows.values():
            rendered = {
                "entity_id": item["entity_id"], "canonical_name": item["canonical_name"],
                "aliases": sorted(item["aliases"]), "record_count": len(item["record_ids"]),
                "family_count": len(item["families"]), "grant_count": item["grants"],
                "forward_citation_count": item["citations"],
                "yearly_publications": [{"year": year, "count": count} for year, count in sorted(item["yearly"].items())],
                "top_ipc_subclasses": [{"ipc": code, "count": count} for code, count in item["ipc"].most_common(10)],
                "resolution_confidence": "high", "parent_group": item["parent_group"],
            }
            rendered["metric_value"] = rendered[metric_key]
            output.append(rendered)
        output.sort(key=lambda item: (-item["metric_value"], item["canonical_name"]))
        warnings = []
        if group_by_parent and not parent_map:
            warnings.append("未提供 reviewed=true 的母子公司映射，group_by_parent 未执行；结果保持法律实体粒度。")
        if metric == "citations":
            warnings.append("仅统计来源明确提供的外部前向被引字段；后向参考文献未被当作影响力。")
        return GenericAnalysisResult(
            result_type="entity_portfolio", data=output[:top_n], warnings=warnings,
            summary=f"按 {entity_type}/{metric} 输出 {min(top_n, len(output))} 个规范实体。",
            result_metadata={
                "entity_type": entity_type, "metric": metric,
                "parent_grouping_applied": bool(group_by_parent and parent_map),
                "reviewed_parent_mapping_count": len(parent_map),
                "entity_resolution_version": "deterministic-v1",
                "unresolved_record_count": unresolved, "low_confidence_mapping_count": 0,
                "analyzed_record_count": len(df),
            },
        )


def _concentration_metrics(weights: list[float]) -> dict[str, float]:
    values = np.array([value for value in weights if value > 0], dtype=float)
    if not len(values):
        return {"cr3": 0.0, "cr5": 0.0, "cr10": 0.0, "hhi": 0.0, "gini": 0.0, "shannon_entropy": 0.0, "effective_entities": 0.0}
    shares = np.sort(values / values.sum())[::-1]
    ascending = np.sort(values)
    n = len(values)
    gini = (2 * np.sum(np.arange(1, n + 1) * ascending) / (n * ascending.sum())) - (n + 1) / n
    entropy = -float(np.sum(shares * np.log(shares)))
    return {
        "cr3": round(float(shares[:3].sum()), 6), "cr5": round(float(shares[:5].sum()), 6),
        "cr10": round(float(shares[:10].sum()), 6), "hhi": round(float(np.sum(shares ** 2)), 6),
        "gini": round(float(max(0, gini)), 6), "shannon_entropy": round(entropy, 6),
        "effective_entities": round(float(math.exp(entropy)), 4),
    }


def _dimension_values(row: pd.Series, dimension: str) -> list[str]:
    if dimension == "applicant":
        return [item[1] for item in _party_names(row, "applicant")]
    if dimension == "ipc":
        return sorted({code[:4].upper() for code in _values(row.get("ipc")) if len(code) >= 4})
    return [_office(row.get("patent_number"))]


class ConcentrationTool(Tool):
    name = "analyze_concentration"
    description = "计算申请人、IPC 小类或主公开号首次公开局的 CRn、HHI、Gini 与 Shannon 有效主体数。"
    parameters = {
        "dimension": {"type": "string", "enum": ["applicant", "ipc", "publication_office"], "default": "applicant"},
        "count_mode": {"type": "string", "enum": ["publications", "families"], "default": "publications"},
        "bootstrap_samples": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 200},
    }
    required_fields = ("patent_number",)
    optional_fields = ("applicants", "ipc", "family_members")
    methodology = "多值维度按每件记录分数计数，报告 CR3/5/10、HHI、Gini、Shannon entropy 和 bootstrap HHI 稳定区间。"

    @staticmethod
    def _weights(df: pd.DataFrame, dimension: str) -> Counter:
        counts: Counter = Counter()
        for _, row in df.iterrows():
            values = _dimension_values(row, dimension)
            if not values:
                continue
            fractional = 1 / len(values)
            for value in values:
                counts[value] += fractional
        return counts

    async def execute(self, storage, dimension="applicant", count_mode="publications", bootstrap_samples=200):
        df = storage.get_all().copy()
        if count_mode == "families":
            keys = df.get("family_id", pd.Series("", index=df.index)).fillna("").astype(str)
            keys = keys.where(keys.str.strip().ne(""), df["patent_number"].astype(str))
            df = df.loc[~keys.duplicated(keep="first")]
        counts = self._weights(df, dimension)
        overall = _concentration_metrics(list(counts.values()))
        yearly = []
        for year, group in df.dropna(subset=["year"]).groupby("year"):
            metrics = _concentration_metrics(list(self._weights(group, dimension).values()))
            yearly_interval = None
            if bootstrap_samples and len(group) >= 2:
                rng = np.random.default_rng(42 + int(year))
                samples = []
                for _ in range(bootstrap_samples):
                    sampled = group.iloc[rng.integers(0, len(group), len(group))]
                    samples.append(_concentration_metrics(
                        list(self._weights(sampled, dimension).values())
                    )["hhi"])
                yearly_interval = [
                    round(float(np.quantile(samples, .025)), 6),
                    round(float(np.quantile(samples, .975)), 6),
                ]
            yearly.append({
                "year": int(year), "record_count": len(group), **metrics,
                "hhi_bootstrap_95pct": yearly_interval,
            })
        interval = None
        if bootstrap_samples and len(df) >= 2:
            rng = np.random.default_rng(42)
            hhi = []
            for _ in range(bootstrap_samples):
                sampled = df.iloc[rng.integers(0, len(df), len(df))]
                hhi.append(_concentration_metrics(list(self._weights(sampled, dimension).values()))["hhi"])
            interval = [round(float(np.quantile(hhi, .025)), 6), round(float(np.quantile(hhi, .975)), 6)]
        leaders = [{"entity": key, "fractional_count": round(value, 4)} for key, value in counts.most_common(20)]
        return GenericAnalysisResult(
            result_type="concentration", data=[{"scope": "overall", "record_count": len(df), **overall, "hhi_bootstrap_95pct": interval}],
            summary=f"{dimension} 集中度基于 {len(df)} 个{count_mode}计数单元。",
            result_metadata={
                "dimension": dimension, "count_mode": count_mode, "fractional_multi_assignment": True,
                "entity_resolution_version": "deterministic-v1", "bootstrap_samples": bootstrap_samples,
                "yearly_metrics": yearly, "leaders": leaders, "display_leader_limit": 20,
                "metrics_use_full_distribution": True,
                "formulas": {
                    "cr_n": "sum of n largest fractional shares",
                    "hhi": "sum(share_i^2)",
                    "gini": "2*sum(i*x_i)/(n*sum(x))-(n+1)/n",
                    "shannon_entropy": "-sum(share_i*ln(share_i))",
                    "effective_entities": "exp(shannon_entropy)",
                },
                "analyzed_record_count": len(df),
            },
            warnings=["集中度拐点仅是待解释现象；研发实力、市场份额和竞争行为需用非专利信息复核。"],
        )


class CitationNetworkTool(Tool):
    name = "analyze_citation_network"
    description = "区分数据集内部与外部引证边，描述关键节点、共引、文献耦合和引证年龄。"
    parameters = {"top_n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}
    required_fields = ("patent_number", "backward_citations")
    optional_fields = ("family_members", "applicants", "publication_date")
    methodology = "引用方向为 citing→cited；内部边参与网络统计，外部未解析边只报告覆盖，不把后向参考数量称为影响力。"

    async def execute(self, storage, top_n=20):
        import networkx as nx
        from engine.citation import build_citation_graph, compute_technology_cycle_time, find_key_patents
        from tools.search_tool import _row_to_pseudo_patent
        df = storage.get_all()
        patents = [_row_to_pseudo_patent(row) for _, row in df.iterrows()]
        graph = build_citation_graph(patents)
        known = set(df["patent_number"].astype(str))
        internal_edges = [(u, v) for u, v in graph.edges() if u in known and v in known]
        external_edges = [(u, v) for u, v in graph.edges() if v not in known]
        audit = storage.audit()["internal_citation_network"]
        internal_graph = graph.subgraph(known).copy()
        key_patents = find_key_patents(internal_graph, top_k=top_n)
        coupling: Counter = Counter()
        co_citation: Counter = Counter()
        refs_by_patent = {node: set(graph.successors(node)) for node in known if node in graph}
        cited_by: defaultdict[str, set] = defaultdict(set)
        for source, refs in refs_by_patent.items():
            for ref in refs:
                cited_by[ref].add(source)
        for patents_for_ref in cited_by.values():
            for left in sorted(patents_for_ref):
                for right in sorted(patents_for_ref):
                    if left < right:
                        coupling[(left, right)] += 1
        for source, refs in refs_by_patent.items():
            refs = sorted(refs)
            for i, left in enumerate(refs):
                for right in refs[i + 1:]:
                    co_citation[(left, right)] += 1
        path_allowed = audit["edge_resolution_rate"] >= .2 and len(internal_edges) >= 2
        row_by_number = {}
        for _, row in df.iterrows():
            row_by_number[str(row.get("patent_number", ""))] = row
        self_citations = 0
        by_applicant, by_office, by_ipc = Counter(), Counter(), Counter()
        citation_ages = []
        for citing, cited in internal_edges:
            source_row, target_row = row_by_number[citing], row_by_number[cited]
            source_entities = {item[0] for item in _party_names(source_row, "applicant")}
            target_entities = {item[0] for item in _party_names(target_row, "applicant")}
            if source_entities & target_entities:
                self_citations += 1
            by_applicant.update(item[1] for item in _party_names(source_row, "applicant"))
            by_office[_office(citing)] += 1
            by_ipc.update({code[:4].upper() for code in _values(source_row.get("ipc")) if len(code) >= 4})
            citing_year, cited_year = _year(source_row.get("publication_date")), _year(target_row.get("publication_date"))
            if citing_year and cited_year and citing_year >= cited_year:
                citation_ages.append(citing_year - cited_year)
        key_paths = []
        path_warning = ""
        if path_allowed and nx.is_directed_acyclic_graph(internal_graph):
            path = nx.algorithms.dag.dag_longest_path(internal_graph)
            if len(path) >= 2:
                key_paths.append({"method": "dag_longest_path", "patent_numbers": path})
        elif path_allowed:
            path_warning = "内部网络含环，未将任意破环结果包装为关键路径。"
        return GenericAnalysisResult(
            result_type="citation_network", data=key_patents,
            summary=f"解析 {len(internal_edges)} 条内部边和 {len(external_edges)} 条外部未闭合边。",
            result_metadata={
                "internal_edge_count": len(internal_edges), "external_edge_count": len(external_edges),
                "edge_resolution_rate": audit["edge_resolution_rate"],
                "node_participation_rate": round(sum(bool(refs) for refs in refs_by_patent.values()) / max(1, len(known)), 4),
                "family_collapse_enabled": True, "family_coverage": storage.field_coverage("family_members"),
                "technology_cycle_time_years_internal": round(compute_technology_cycle_time(graph.subgraph(known).copy()), 4),
                "bibliographic_coupling_pairs": [{"left": p[0], "right": p[1], "shared_references": n} for p, n in coupling.most_common(top_n)],
                "co_citation_pairs": [{"left": p[0], "right": p[1], "co_cited_count": n} for p, n in co_citation.most_common(top_n)],
                "self_citation_count": self_citations,
                "self_citation_rate_internal": round(self_citations / max(1, len(internal_edges)), 4),
                "citation_age_years": {
                    "count": len(citation_ages),
                    "median": round(float(np.median(citation_ages)), 4) if citation_ages else None,
                },
                "citation_distributions": {
                    "citing_applicants": [{"value": k, "count": v} for k, v in by_applicant.most_common(top_n)],
                    "citing_publication_offices": [{"value": k, "count": v} for k, v in by_office.most_common(top_n)],
                    "citing_ipc_subclasses": [{"value": k, "count": v} for k, v in by_ipc.most_common(top_n)],
                },
                "key_paths": key_paths,
                "key_path_conclusions_enabled": bool(key_paths), "analyzed_record_count": len(df),
            },
            warnings=([] if path_allowed else ["开放网络门禁未通过；关键节点仅作内部描述，不输出关键路径或影响力结论。"]) + ([path_warning] if path_warning else []),
        )


class FamilyGeographyTool(Tool):
    name = "analyze_family_geography"
    description = "分别统计优先权来源地、主公开号首次公开局、同族覆盖局、指定国与可用的当前有效地域。"
    parameters = {"top_n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30}}
    required_fields = ("patent_number",)
    optional_fields = ("priority_numbers", "family_members", "legal_status")
    methodology = "各地域口径分栏统计；PN 前缀只代表公开局，绝不代替市场覆盖或有效权利地域。"

    async def execute(self, storage, top_n=30):
        df = storage.get_all()
        priority, first, family, designated, active = Counter(), Counter(), Counter(), Counter(), Counter()
        for _, row in df.iterrows():
            priority.update({_office(value) for value in _values(row.get("priority_numbers"))})
            first[_office(row.get("patent_number"))] += 1
            family.update({_office(value) for value in _values(row.get("family_members"))})
            designated.update({_office(value) for value in _values(row.get("designated_states"))})
            if str(row.get("legal_status", "")).lower() in {"active", "granted", "patented case"}:
                jurisdiction = str(row.get("jurisdiction", "") or "").strip().upper()
                if jurisdiction:
                    active[jurisdiction] += 1
        capabilities = storage.audit().get("source_capabilities", {})
        current_status_authoritative = any(
            bool(item.get("current_legal_status")) for item in capabilities.values()
            if isinstance(item, dict)
        ) and storage.field_coverage("legal_status_as_of") >= .8 and storage.field_coverage("jurisdiction") >= .8
        def rendered(counter):
            return [{"office_or_jurisdiction": key, "count": value} for key, value in counter.most_common(top_n)]
        return GenericAnalysisResult(
            result_type="family_geography", data=[
                {"dimension": "priority_origin", "values": rendered(priority)},
                {"dimension": "first_publication_office", "values": rendered(first)},
                {"dimension": "family_publication_offices", "values": rendered(family)},
                {"dimension": "designated_states", "values": rendered(designated)},
                {"dimension": "current_active_rights_jurisdictions", "values": rendered(active) if current_status_authoritative else []},
            ],
            summary="地域布局按五种互不替代的来源口径分开报告。",
            result_metadata={
                "current_status_authoritative": current_status_authoritative,
                "legal_status_as_of_coverage": storage.field_coverage("legal_status_as_of"),
                "jurisdiction_coverage": storage.field_coverage("jurisdiction"),
                "analyzed_record_count": len(df),
            },
            warnings=["主公开号首次公开局和同族公开局不代表出口意向、市场吸引力或当前有效权利地域。"] + ([] if current_status_authoritative else ["来源不具备权威当前法律状态能力，未输出当前有效权利地域。"]),
        )


class SearchStrategyAuditTool(Tool):
    name = "audit_search_strategy"
    description = "比较版本化关键词/IPC/申请人检索策略的返回集、增量、独有记录、已知专利回查和滚雪球候选。"
    parameters = {
        "strategies": {"type": "array", "maxItems": 10, "items": {"type": "object"}, "required": True},
        "known_patent_numbers": {"type": "array", "maxItems": 100, "items": {"type": "string"}, "default": []},
        "review_labels": {"type": "array", "maxItems": 500, "items": {"type": "object"}, "default": []},
        "random_audit_sample_size": {"type": "integer", "minimum": 0, "maximum": 200, "default": 20},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
    }
    required_fields = ("patent_number", "title", "abstract")
    optional_fields = ("ipc", "family_members", "backward_citations")
    methodology = "在同一词法检索基线上对版本化策略做集合差异审计；已知专利回查率不是总体查全率。"

    async def execute(
        self, storage, strategies, known_patent_numbers=[], review_labels=[],
        random_audit_sample_size=20, top_k=200,
    ):
        from tools.search_tool import _get_searcher
        if not strategies or any(not isinstance(item, dict) or not str(item.get("query", "")).strip() for item in strategies):
            raise ValueError("每个 strategies 项必须包含非空 query")
        searcher = _get_searcher(storage, "lexical")
        known = {str(item) for item in (known_patent_numbers or [])}
        versions, previous = [], set()
        all_sets = []
        for index, strategy in enumerate(strategies, 1):
            query = str(strategy["query"]).strip()
            results = searcher.hybrid_search(
                query=query, top_k=top_k,
                ipc_filter=strategy.get("ipc_filter"),
                applicant_filter=strategy.get("applicant_filter"),
                year_range=tuple(strategy["year_range"]) if strategy.get("year_range") else None,
            )
            ids = [item.patent_number for item in results]
            hit_set = set(ids)
            version_payload = {key: strategy[key] for key in sorted(strategy)}
            versions.append({
                "version": index, "name": strategy.get("name", f"v{index}"),
                "strategy_hash": hashlib.sha256(json.dumps(version_payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                "query": query, "returned_count": len(ids), "total_hits_exact": False,
                "incremental_records": sorted(hit_set - previous),
                "removed_records": sorted(previous - hit_set),
                "known_patents_found": sorted(known & hit_set),
                "known_patent_recovery_ratio": round(len(known & hit_set) / len(known), 4) if known else None,
            })
            all_sets.append(hit_set)
            previous = hit_set
        for index, version in enumerate(versions):
            others = set().union(*(all_sets[:index] + all_sets[index + 1:])) if len(all_sets) > 1 else set()
            version["unique_records"] = sorted(all_sets[index] - others)
        returned_union = set().union(*all_sets)
        labels = {
            str(item.get("patent_number", "")): bool(item.get("relevant"))
            for item in (review_labels or []) if isinstance(item, dict)
            and str(item.get("patent_number", "")).strip()
        }
        reviewed_returned = {key: value for key, value in labels.items() if key in returned_union}
        labeled_missed_relevant = sorted(
            key for key, relevant in labels.items()
            if relevant and key not in returned_union
        )
        all_numbers = sorted(set(storage.get_all()["patent_number"].astype(str)) - returned_union)
        rng = np.random.default_rng(42)
        if random_audit_sample_size and all_numbers:
            positions = rng.choice(
                len(all_numbers), size=min(random_audit_sample_size, len(all_numbers)),
                replace=False,
            )
            random_audit_candidates = sorted(all_numbers[int(index)] for index in positions)
        else:
            random_audit_candidates = []
        frame = storage.get_all().set_index("patent_number", drop=False)
        snowball = set()
        for patent_number in set().union(*all_sets):
            if patent_number in frame.index:
                row = frame.loc[patent_number]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                snowball.update(_values(row.get("family_members")))
                snowball.update(_values(row.get("backward_citations", row.get("cited_refs"))))
        return GenericAnalysisResult(
            result_type="search_strategy_audit", data=versions,
            summary=f"比较 {len(versions)} 个检索策略版本；命中数均为返回集数量，不是确切全库命中数。",
            result_metadata={
                "known_patent_count": len(known), "snowball_candidates": sorted(snowball)[:500],
                "reviewed_label_count": len(labels),
                "reviewed_returned_precision": (
                    round(sum(reviewed_returned.values()) / len(reviewed_returned), 4)
                    if reviewed_returned else None
                ),
                "labeled_relevant_not_returned": labeled_missed_relevant,
                "random_nonreturned_audit_candidates": random_audit_candidates,
                "expert_recall_benchmark_available": False, "analyzed_record_count": len(storage.get_all()),
            },
            warnings=["已知专利回查率不能表述为查全率；随机漏检审计仍需专家标签样本。"],
        )


class LegalStatusTool(Tool):
    name = "analyze_legal_status"
    description = "在权威来源能力门禁通过后，分开统计当前法律状态与年度法律事件。"
    parameters = {"top_n": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30}}
    required_fields = ("legal_status",)
    optional_fields = ("legal_events",)
    methodology = "当前状态与历史事件分开统计，并保留司法辖区、来源和 as_of；不构成有效性或 FTO 法律意见。"
    deterministic = False

    def _dataset_gate_failures(self, storage):
        failures = super()._dataset_gate_failures(storage)
        capabilities = storage.audit().get("source_capabilities", {})
        if not any(bool(item.get("current_legal_status")) for item in capabilities.values() if isinstance(item, dict)):
            failures.append("来源未声明 current_legal_status 权威能力")
        if storage.field_coverage("legal_status_as_of") < .8:
            failures.append("至少 80% 状态记录需要 legal_status_as_of")
        if storage.field_coverage("jurisdiction") < .8:
            failures.append("至少 80% 状态记录需要明确司法辖区")
        if not storage.adapter_name or storage.adapter_name == "unknown":
            failures.append("法律状态需要可识别的数据来源")
        return failures

    async def execute(self, storage, top_n=30):
        df = storage.get_all()
        statuses = df["legal_status"].fillna("").astype(str).str.strip().replace("", "unknown").value_counts()
        events = Counter()
        upcoming_candidates = []
        jurisdictions = Counter()
        stale = 0
        now = datetime.now(timezone.utc)
        now_year = now.year
        for _, row in df.iterrows():
            jurisdiction = str(row.get("jurisdiction", "") or "unknown").strip().upper()
            jurisdictions[jurisdiction] += 1
            as_of_year = _year(row.get("legal_status_as_of"))
            if not as_of_year or now_year - as_of_year > 1:
                stale += 1
            try:
                items = json.loads(str(row.get("legal_events_json", "") or "[]"))
            except (ValueError, TypeError, json.JSONDecodeError):
                items = []
            for item in items:
                if isinstance(item, dict):
                    events[(_year(item.get("event_date")), str(item.get("event_code", "unknown")))] += 1
                    text = f"{item.get('event_code', '')} {item.get('description', '')}".casefold()
                    date_text = str(item.get("event_date", "") or "")
                    try:
                        event_date = datetime.fromisoformat(date_text[:10]).replace(tzinfo=timezone.utc)
                    except ValueError:
                        event_date = None
                    if event_date and now <= event_date <= now + timedelta(days=366) and any(
                        token in text for token in ("fee", "annuity", "renew", "expire", "年费", "届满")
                    ):
                        upcoming_candidates.append({
                            "patent_number": str(row.get("patent_number", "")),
                            "jurisdiction": jurisdiction,
                            "event_code": str(item.get("event_code", "")),
                            "event_date": date_text,
                        })
        return GenericAnalysisResult(
            result_type="legal_status", data=[{"status": key, "count": int(value)} for key, value in statuses.head(top_n).items()],
            summary=f"统计 {len(df)} 件记录的来源时点法律状态。",
            result_metadata={
                "yearly_events": [{"year": year, "event_code": code, "count": count} for (year, code), count in sorted(events.items(), key=lambda item: str(item[0]))],
                "upcoming_fee_or_expiry_event_candidates": upcoming_candidates,
                "jurisdiction_composition": [{"jurisdiction": key, "count": value} for key, value in jurisdictions.most_common()],
                "stale_record_count": stale, "analyzed_record_count": len(df),
            },
            warnings=["法律状态仅代表来源 as_of 时点；跨局状态不可直接比较，不构成可实施、无侵权或权利有效意见。"],
        )


class PatentMonitorTool(Tool):
    name = "monitor_patent_changes"
    description = "保存版本化词法检索基线，并审计新公开、移除记录以及同族、引证、法律事件和申请人字段变化。"
    parameters = {
        "strategy_id": {"type": "string", "required": True},
        "strategy_version": {"type": "integer", "minimum": 1, "required": True},
        "query": {"type": "string", "required": True},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 500},
        "update_baseline": {"type": "boolean", "default": True},
        "notification_policy": {
            "type": "string", "enum": ["all_changes", "threshold"],
            "default": "all_changes",
        },
        "minimum_event_count": {
            "type": "integer", "minimum": 1, "maximum": 1000, "default": 1,
        },
    }
    required_fields = ("patent_number", "title", "abstract")
    optional_fields = (
        "family_members", "backward_citations", "forward_citations",
        "legal_events", "applicants",
    )
    methodology = "比较持久化策略基线与当前内容版本；预警只表示数据变化，不表示侵权风险。"
    deterministic = False
    requires_confirmation = True

    def _dataset_gate_failures(self, storage):
        failures = super()._dataset_gate_failures(storage)
        if not storage.adapter_name or storage.adapter_name == "unknown":
            failures.append("持续监测必须使用可识别、可重复导入的外部数据源")
        return failures

    async def execute(
        self, storage, strategy_id, strategy_version, query, top_k=500,
        update_baseline=True, notification_policy="all_changes",
        minimum_event_count=1,
    ):
        from tools.search_tool import _get_searcher
        results = _get_searcher(storage, "lexical").hybrid_search(query=query, top_k=top_k)
        frame = storage.get_all().set_index("patent_number", drop=False)
        snapshot = {}
        for item in results:
            row = frame.loc[item.patent_number]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            fields = {
                key: str(row.get(key, "") or "") for key in (
                    "family_members", "backward_citations", "forward_citations",
                    "legal_events_json", "applicants",
                )
            }
            snapshot[item.patent_number] = {
                "record_hash": hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest(),
                "fields": fields,
            }
        db_path = Path(os.getenv("PATENTAGENT_MONITOR_DB", ".patentagent/monitoring.db")).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS monitor_baselines (strategy_id TEXT, strategy_version INTEGER, query TEXT, dataset_hash TEXT, snapshot_json TEXT, updated_at TEXT, PRIMARY KEY(strategy_id,strategy_version))")
            db.execute("CREATE TABLE IF NOT EXISTS monitor_runs (run_id TEXT PRIMARY KEY, strategy_id TEXT, strategy_version INTEGER, dataset_hash TEXT, event_count INTEGER, created_at TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS monitor_events (event_id TEXT PRIMARY KEY, run_id TEXT, strategy_id TEXT, strategy_version INTEGER, event_type TEXT, patent_number TEXT, created_at TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS monitor_audit_log (audit_id TEXT PRIMARY KEY, run_id TEXT, action TEXT, details_json TEXT, created_at TEXT)")
            row = db.execute("SELECT snapshot_json FROM monitor_baselines WHERE strategy_id=? AND strategy_version=?", (strategy_id, strategy_version)).fetchone()
            baseline = json.loads(row[0]) if row else {}
            events = []
            for patent_number in sorted(set(snapshot) - set(baseline)):
                events.append({"event_type": "new_publication", "patent_number": patent_number})
            for patent_number in sorted(set(baseline) - set(snapshot)):
                events.append({"event_type": "no_longer_returned", "patent_number": patent_number})
            for patent_number in sorted(set(snapshot) & set(baseline)):
                for field, event_type in (
                    ("family_members", "family_changed"), ("backward_citations", "citation_changed"),
                    ("forward_citations", "forward_citation_changed"),
                    ("legal_events_json", "legal_event_changed"), ("applicants", "applicant_changed"),
                ):
                    if snapshot[patent_number]["fields"][field] != baseline[patent_number]["fields"].get(field, ""):
                        events.append({"event_type": event_type, "patent_number": patent_number})
            now = datetime.now(timezone.utc).isoformat()
            run_id = hashlib.sha256(f"{strategy_id}\0{strategy_version}\0{storage.dataset_fingerprint()}".encode()).hexdigest()
            db.execute("INSERT OR IGNORE INTO monitor_runs VALUES (?,?,?,?,?,?)", (run_id, strategy_id, strategy_version, storage.dataset_fingerprint(), len(events), now))
            persisted_events = []
            for event in events:
                event_id = hashlib.sha256(
                    f"{run_id}\0{event['event_type']}\0{event['patent_number']}".encode()
                ).hexdigest()
                cursor = db.execute(
                    "INSERT OR IGNORE INTO monitor_events VALUES (?,?,?,?,?,?,?)",
                    (event_id, run_id, strategy_id, strategy_version,
                     event["event_type"], event["patent_number"], now),
                )
                if cursor.rowcount:
                    persisted_events.append({**event, "event_id": event_id})
            if update_baseline:
                db.execute("INSERT OR REPLACE INTO monitor_baselines VALUES (?,?,?,?,?,?)", (strategy_id, strategy_version, query, storage.dataset_fingerprint(), json.dumps(snapshot, ensure_ascii=False, sort_keys=True), now))
            should_notify = bool(baseline) and (
                len(persisted_events) > 0 if notification_policy == "all_changes"
                else len(persisted_events) >= minimum_event_count
            )
            audit_details = {
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "baseline_existed": bool(baseline),
                "baseline_updated": update_baseline,
                "notification_policy": notification_policy,
                "minimum_event_count": minimum_event_count,
                "should_notify": should_notify,
            }
            audit_id = hashlib.sha256(f"{run_id}\0execution_completed".encode()).hexdigest()
            db.execute(
                "INSERT OR IGNORE INTO monitor_audit_log VALUES (?,?,?,?,?)",
                (audit_id, run_id, "execution_completed",
                 json.dumps(audit_details, ensure_ascii=False, sort_keys=True), now),
            )
            db.commit()
        return GenericAnalysisResult(
            result_type="patent_monitor", data=persisted_events,
            summary=f"策略 {strategy_id} v{strategy_version} 检测到 {len(persisted_events)} 个新增去重数据变化事件。",
            result_metadata={
                "strategy_id": strategy_id, "strategy_version": strategy_version,
                "strategy_hash": hashlib.sha256(query.encode()).hexdigest(),
                "baseline_existed": bool(baseline), "baseline_updated": update_baseline,
                "dataset_content_hash": storage.dataset_fingerprint(), "run_id": run_id,
                "returned_count": len(snapshot), "analyzed_record_count": len(storage.get_all()),
                "notification_policy": notification_policy,
                "minimum_event_count": minimum_event_count,
                "should_notify": should_notify,
                "audit_log_id": audit_id,
            },
            warnings=["预警仅表示数据变化或规则命中，不表示已经发生侵权风险。"],
        )


def _claim_items(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(str(value or "[]"))
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


class ClaimElementsTool(Tool):
    name = "analyze_claim_elements"
    description = "生成权利要求依赖树、规则化要素拆分和产品特征词面映射草稿，供专利专业人员复核。"
    parameters = {
        "patent_numbers": {"type": "array", "maxItems": 20, "items": {"type": "string"}, "default": []},
        "product_features": {"type": "array", "maxItems": 100, "items": {"type": "string"}, "default": []},
    }
    required_fields = ("claims_json",)
    optional_fields = ("legal_status", "kind_code")
    methodology = "按来源 claim number/dependency 构树，以标点和连接词进行可逆规则拆分；产品映射仅为词面草稿。"
    requires_confirmation = True

    def _dataset_gate_failures(self, storage):
        failures = super()._dataset_gate_failures(storage)
        df = storage.get_all()
        if storage.field_coverage("legal_status") < .8:
            failures.append("至少 80% 记录需要可识别的授权/申请法律状态")
        version_recognized = 0
        structured_claims = 0
        claim_count = 0
        for _, row in df.iterrows():
            kind = str(row.get("kind_code", "") or "").strip()
            publication = str(row.get("patent_number", "") or "").strip()
            if kind or re.search(r"[A-Z]\d?$", publication, flags=re.I):
                version_recognized += 1
            for claim in _claim_items(row.get("claims_json")):
                claim_count += 1
                language = str(claim.get("language", "") or "").strip().lower()
                if (
                    str(claim.get("number", "")).isdigit()
                    and language not in {"", "und", "unknown"}
                    and isinstance(claim.get("is_independent"), bool)
                    and isinstance(claim.get("depends_on"), list)
                ):
                    structured_claims += 1
        total = max(len(df), 1)
        if version_recognized / total < .8:
            failures.append("至少 80% 记录需要可识别的公开/授权版本")
        if claim_count == 0 or structured_claims / claim_count < .8:
            failures.append("至少 80% 权利要求需要编号、语言、独立性和依赖关系结构")
        return failures

    async def execute(self, storage, patent_numbers=[], product_features=[]):
        df = storage.get_all()
        wanted = {str(item) for item in (patent_numbers or [])}
        if wanted:
            df = df[df["patent_number"].astype(str).isin(wanted)]
        output = []
        for _, row in df.iterrows():
            claims = _claim_items(row.get("claims_json"))
            rendered = []
            for position, claim in enumerate(claims, 1):
                number = int(claim.get("number") or position)
                text = str(claim.get("text", "")).strip()
                parts = [part.strip() for part in re.split(r"[;；]|(?<=。)|\bwherein\b|其中", text, flags=re.I) if part.strip()]
                mappings = []
                for feature in product_features or []:
                    matched = [index + 1 for index, part in enumerate(parts) if str(feature).casefold() in part.casefold()]
                    mappings.append({"feature": str(feature), "matched_element_numbers": matched, "match_method": "literal_substring"})
                rendered.append({
                    "claim_number": number, "is_independent": bool(claim.get("is_independent", not claim.get("depends_on"))),
                    "depends_on": [int(item) for item in claim.get("depends_on", []) if str(item).isdigit()],
                    "language": claim.get("language", "und"),
                    "elements": [{"element_number": index + 1, "text": part} for index, part in enumerate(parts)],
                    "product_feature_mapping_draft": mappings,
                    "source_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "source_evidence_path": (
                        f"record://{row.get('patent_number', '')}/claims_json/"
                        f"claim/{number}"
                    ),
                })
            output.append({
                "patent_number": str(row.get("patent_number", "")),
                "kind_code": str(row.get("kind_code", "") or ""),
                "legal_status": str(row.get("legal_status", "") or ""),
                "claims": rendered,
            })
        version_differences = []
        grouped: defaultdict[str, list[dict]] = defaultdict(list)
        for _, row in df.iterrows():
            group_key = str(
                row.get("application_number", "") or
                row.get("family_id", "") or ""
            ).strip()
            if not group_key:
                continue
            claim_hashes = [
                hashlib.sha256(str(item.get("text", "")).encode()).hexdigest()
                for item in _claim_items(row.get("claims_json"))
            ]
            grouped[group_key].append({
                "patent_number": str(row.get("patent_number", "")),
                "kind_code": str(row.get("kind_code", "") or ""),
                "claim_hashes": claim_hashes,
            })
        for group_key, versions in sorted(grouped.items()):
            ordered = sorted(versions, key=lambda item: (item["kind_code"], item["patent_number"]))
            for left, right in zip(ordered, ordered[1:]):
                left_hashes, right_hashes = set(left["claim_hashes"]), set(right["claim_hashes"])
                version_differences.append({
                    "version_group": group_key,
                    "from_patent_number": left["patent_number"],
                    "to_patent_number": right["patent_number"],
                    "removed_claim_hashes": sorted(left_hashes - right_hashes),
                    "added_claim_hashes": sorted(right_hashes - left_hashes),
                    "comparison_method": "exact_claim_text_sha256",
                })
        return GenericAnalysisResult(
            result_type="claim_elements", data=output,
            summary=f"为 {len(output)} 件专利生成可逆的权利要求要素拆分草稿。",
            result_metadata={
                "draft": True, "human_review_required": True,
                "mapping_method": "literal_substring", "analyzed_record_count": len(df),
                "version_differences": version_differences,
            },
            warnings=["本结果是人工复核草稿，不构成侵权、等同、无效或 FTO 结论；必须由专利专业人员审阅。"],
        )


for _tool in (
    EntityPortfolioTool(), ConcentrationTool(), CitationNetworkTool(),
    FamilyGeographyTool(), SearchStrategyAuditTool(), LegalStatusTool(),
    PatentMonitorTool(), ClaimElementsTool(),
):
    tool_registry.register(_tool)
