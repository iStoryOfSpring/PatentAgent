"""Tool 基类与注册表"""

from abc import ABC, abstractmethod
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from typing import Any

from models.analysis_results import AnalysisResult
from patent_agent.domain import (
    AlgorithmExecution, AnalysisScope, ExecutionMetrics, ToolDefinition,
    ToolExecutionEnvelope, ToolProvenance,
)
from storage.datastore import PatentDataStore
from tools.evidence import evidence_for


_VISUALIZATION_DEFAULTS: dict[str, dict[str, Any]] = {
    "monthly_trend": {"kind": "line", "width": 960, "height": 520},
    "yearly_trend": {"kind": "line", "width": 960, "height": 520},
    "s_curve": {"kind": "combo", "width": 960, "height": 520},
    "ipc_matrix": {"kind": "heatmap", "width": 960, "height": 520},
    "word_freq": {"kind": "tabs", "width": 960, "height": 520},
    "burst_terms": {"kind": "bar", "width": 960, "height": 600},
    "yearly_keywords": {"kind": "heatmap", "width": 960, "height": 620},
    "co_occurrence": {"kind": "network", "width": 1100, "height": 680},
    "country_distribution": {"kind": "donut", "width": 960, "height": 520},
    "roadmap": {"kind": "timeline", "width": 1100, "height": 680},
    "dataset_summary": {"kind": "kpi_table", "width": 960, "height": 520},
    "patent_search": {"kind": "cards", "width": 960, "height": 520},
    "patent_details": {"kind": "accordion", "width": 960, "height": 520},
    "tech_effect_matrix": {"kind": "matrix", "width": 1100, "height": 680},
    "clustering": {"kind": "bar_cards", "width": 960, "height": 520},
    "value_indicators": {"kind": "bar_table", "width": 960, "height": 600},
    "competitor_evolution": {"kind": "multi_line", "width": 960, "height": 520},
}

_TOOL_COST_WEIGHTS: dict[str, int] = {
    "get_dataset_summary": 1,
    "analyze_patent_trend": 1,
    "analyze_lifecycle": 1,
    "analyze_ipc_distribution": 1,
    "generate_wordcloud": 2,
    "analyze_burst_terms": 3,
    "analyze_yearly_keywords": 2,
    "analyze_co_network": 2,
    "analyze_country_distribution": 1,
    "analyze_tech_roadmap": 2,
    "search_patents": 1,
    "read_patent_details": 1,
    "analyze_tech_matrix": 3,
    "analyze_clustering": 3,
    "analyze_patent_valuation": 3,
    "analyze_competitor_evolution": 2,
    "analyze_entity_portfolio": 2,
    "analyze_concentration": 3,
    "analyze_citation_network": 3,
    "analyze_family_geography": 2,
    "audit_search_strategy": 3,
    "analyze_legal_status": 2,
    "monitor_patent_changes": 3,
    "analyze_claim_elements": 3,
}

_TOOL_RESULT_FIELDS: dict[str, list[str]] = {
    "get_dataset_summary": ["total_patents", "year_range", "top_applicants", "field_coverage"],
    "analyze_patent_trend": ["data(year_month/year,count)", "summary", "warnings"],
    "analyze_lifecycle": ["years", "counts", "cumulative", "fitted", "params"],
    "analyze_ipc_distribution": ["years", "sections", "matrix"],
    "generate_wordcloud": ["data(word,count)"],
    "analyze_burst_terms": ["data(term,growth_score,recent_support)"],
    "analyze_yearly_keywords": ["data(year -> terms)"],
    "analyze_co_network": ["edges(source,target,weight)", "node_count", "edge_count"],
    "analyze_country_distribution": ["data(country,count)", "family_availability"],
    "analyze_tech_roadmap": ["data(year -> representative patents and annual themes)", "route_nodes", "route_edges", "main_paths", "citation_route_gate"],
    "search_patents": ["patents", "total_hits", "relevance_score"],
    "read_patent_details": ["patents", "available_source_fields"],
    "analyze_tech_matrix": ["functions", "effects", "matrix", "gap_recommendations"],
    "analyze_clustering": ["cluster_titles", "cluster_keywords", "patents_per_cluster", "silhouette_score"],
    "analyze_patent_valuation": ["data", "score_label", "coverage"],
    "analyze_competitor_evolution": ["evolution", "entropy", "dominant_share", "cosine_shift"],
    "analyze_entity_portfolio": ["data", "aliases", "yearly_publications", "top_ipc_subclasses"],
    "analyze_concentration": ["data", "yearly_metrics", "leaders", "hhi_bootstrap_95pct"],
    "analyze_citation_network": ["data", "internal_edge_count", "external_edge_count", "coupling_pairs"],
    "analyze_family_geography": ["data(priority,first_publication,family,designated,active_rights)"],
    "audit_search_strategy": ["data", "incremental_records", "unique_records", "known_patent_recovery_ratio"],
    "analyze_legal_status": ["data", "yearly_events", "stale_record_count"],
    "monitor_patent_changes": ["data", "strategy_hash", "run_id", "baseline_updated"],
    "analyze_claim_elements": ["data", "claim_tree", "elements", "product_feature_mapping_draft"],
}

_ANALYSIS_SCOPE_SCHEMA = AnalysisScope.model_json_schema()
_CPU_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="patentagent-cpu",
)


def _run_execute_callable(execute, storage, params):
    """Run synchronous-style async tool code in a worker-thread event loop."""
    return asyncio.run(execute(storage, **params))


class Tool(ABC):
    """所有 Tool 的基类"""
    name: str = ""
    description: str = ""
    requires_confirmation: bool = False
    parameters: dict[str, Any] = {}
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    methodology: str = ""
    evidence_level: str = "engineering_heuristic"
    allow_empty: bool = False
    deterministic: bool = True
    supports_scope: bool = True
    cpu_bound: bool = True
    max_execution_seconds: float = 120.0
    max_input_records: int = 1_000_000
    memory_budget_mb: int = 1024

    @property
    def effective_parameters(self) -> dict[str, Any]:
        parameters = dict(self.parameters)
        if self.supports_scope:
            parameters["scope"] = {
                **_ANALYSIS_SCOPE_SCHEMA,
                "description": (
                    "统一分析范围；年份、IPC、主体、地域、专利号和文本条件在工具执行前应用。"
                ),
            }
        return parameters

    @property
    def cost_weight(self) -> int:
        return _TOOL_COST_WEIGHTS.get(self.name, 2)

    @property
    def returned_fields(self) -> list[str]:
        return _TOOL_RESULT_FIELDS.get(self.name, ["structured_result"])

    @property
    def evidence_record(self) -> dict[str, Any]:
        return evidence_for(self.name)

    @property
    def definition(self) -> ToolDefinition:
        record = self.evidence_record
        return ToolDefinition(
            name=self.name,
            version=str(record.get("version", "")),
            description=self.description,
            input_schema={
                "type": "object",
                "properties": self.effective_parameters,
                "required": [
                    name for name, schema in self.effective_parameters.items()
                    if schema.get("required", False)
                ],
            },
            output_schema={
                "type": "object",
                "required": ["result_type", "summary", "provenance", "metrics"],
                "x-returned-fields": self.returned_fields,
            },
            required_fields=set(self.required_fields),
            optional_fields=set(self.optional_fields),
            estimated_cost=self.cost_weight,
            deterministic=self.deterministic,
        )

    def availability(self, storage: PatentDataStore) -> dict[str, Any]:
        record = self.evidence_record
        thresholds = record.get("fields", {})
        coverage = {
            f: storage.field_coverage(f)
            for f in set((*self.required_fields, *self.optional_fields, *thresholds.keys()))
        }
        missing = [
            field for field, threshold in thresholds.items()
            if coverage.get(field, 0.0) < float(threshold)
        ]
        gate_failures = self._dataset_gate_failures(storage)
        return {
            "available": not missing and not gate_failures and (
                self.allow_empty or not storage.is_empty
            ),
            "missing_required_fields": missing,
            "field_coverage": coverage,
            "field_thresholds": thresholds,
            "gate_failures": gate_failures,
            "reason": (
                "数据集为空" if storage.is_empty and not self.allow_empty else
                f"字段覆盖不足: {', '.join(missing)}" if missing else
                "；".join(gate_failures)
            ),
            "evidence_level": record.get("evidence_type", self.evidence_level),
            "algorithm_id": record.get("algorithm_id"),
            "algorithm_version": record.get("version"),
        }

    def _dataset_gate_failures(self, storage: PatentDataStore) -> list[str]:
        failures: list[str] = []
        df = storage.get_all()
        if self.name == "analyze_clustering":
            title = df.get('title')
            abstract = df.get('abstract')
            if title is None or abstract is None:
                return ["聚类至少需要 100 条有效文本"]
            valid = ((title.fillna('').astype(str).str.len() +
                      abstract.fillna('').astype(str).str.len()) > 10).sum()
            if int(valid) < 100:
                failures.append("聚类至少需要 100 条有效文本")
        elif self.name == "analyze_co_network":
            collab = storage.audit()["collaboration_coverage"]
            if collab["multi_applicant_patents"] < 30 or collab["multi_applicant_rate"] < 0.01:
                failures.append("合作网络至少需要 30 件多申请人专利且占比不低于 1%")
        elif self.name == "analyze_burst_terms":
            years = df.get('year')
            if years is None:
                return ["近期增长词至少需要 5 个各含 50 件记录的完整年度"]
            counts = years.dropna().astype(int).value_counts()
            complete = counts[counts >= 50]
            if len(complete) < 5:
                failures.append("近期增长词至少需要 5 个各含 50 件记录的完整年度")
        return failures

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """在 Tool 入口统一校验，避免空查询和非法范围进入 Engine。"""
        effective = self.effective_parameters
        unknown = sorted(set(params) - set(effective))
        if unknown:
            raise ValueError(f"未知参数: {', '.join(unknown)}")
        clean = {k: v for k, v in params.items() if k in effective}
        for name, schema in effective.items():
            value = clean.get(name)
            if schema.get("required") and (
                value is None or value == "" or value == []
            ):
                raise ValueError(f"参数 {name} 不能为空")
            if value is None:
                continue
            if name == "scope":
                clean[name] = AnalysisScope.model_validate(value).canonical()
                continue
            if "enum" in schema and value not in schema["enum"]:
                raise ValueError(f"参数 {name} 必须是 {schema['enum']} 之一")
            if schema.get("type") == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"参数 {name} 必须是整数")
                if "minimum" in schema and value < schema["minimum"]:
                    raise ValueError(f"参数 {name} 不能小于 {schema['minimum']}")
                if "maximum" in schema and value > schema["maximum"]:
                    raise ValueError(f"参数 {name} 不能大于 {schema['maximum']}")
            if schema.get("type") == "array" and "maxItems" in schema:
                if len(value) > schema["maxItems"]:
                    raise ValueError(f"参数 {name} 最多包含 {schema['maxItems']} 项")
        if clean.get("year_start") and clean.get("year_end"):
            if clean["year_start"] > clean["year_end"]:
                raise ValueError("year_start 不能晚于 year_end")
        return clean

    async def run(self, storage: PatentDataStore, **params):
        """统一执行入口：参数校验、能力门禁、结果质量和追踪元数据。"""
        clean = self.validate_params(params)
        scope = AnalysisScope.model_validate(clean.get("scope", {}))
        execution_storage = (
            storage.filtered_by_scope(scope) if self.supports_scope and scope.canonical()
            else storage
        )
        capability = self.availability(execution_storage)
        if not capability["available"]:
            raise ValueError(capability["reason"] or "当前数据无法执行该工具")
        input_records = len(execution_storage.get_all())
        if input_records > self.max_input_records:
            raise ValueError(
                f"工具 {self.name} 输入 {input_records:,} 件，超过上限 "
                f"{self.max_input_records:,} 件；请先使用 scope 缩小范围。"
            )
        estimated_input_mb = round(
            float(execution_storage.get_all().memory_usage(deep=True).sum()) /
            (1024 * 1024), 2,
        )
        if estimated_input_mb > self.memory_budget_mb:
            raise ValueError(
                f"工具 {self.name} 输入数据约 {estimated_input_mb:g} MiB，超过内存预算 "
                f"{self.memory_budget_mb:g} MiB；请先使用 scope 缩小范围。"
            )
        started = time.perf_counter()
        execute_params = {key: value for key, value in clean.items() if key != "scope"}
        try:
            async with asyncio.timeout(self.max_execution_seconds):
                if self.cpu_bound:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        _CPU_EXECUTOR, _run_execute_callable,
                        self.execute, execution_storage, execute_params,
                    )
                else:
                    result = await self.execute(execution_storage, **execute_params)
        except TimeoutError as exc:
            raise TimeoutError(
                f"工具 {self.name} 超过最大执行时间 {self.max_execution_seconds:g} 秒"
            ) from exc
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        if isinstance(result, AnalysisResult):
            default_algorithm = AlgorithmExecution(
                algorithm_id=str(self.evidence_record.get("algorithm_id", "")),
                algorithm_version=str(self.evidence_record.get("version", "")),
                parameters=execute_params,
            )
            algorithm = result.algorithm_execution or default_algorithm
            allowed = {(
                str(self.evidence_record.get("algorithm_id", "")),
                str(self.evidence_record.get("version", "")),
            )}
            for implementation in self.evidence_record.get("implementations", {}).values():
                allowed.add((
                    str(implementation.get("algorithm_id", "")),
                    str(implementation.get("version", "")),
                ))
            if (algorithm.algorithm_id, algorithm.algorithm_version) not in allowed:
                raise ValueError(
                    f"工具 {self.name} 返回了未登记算法 "
                    f"{algorithm.algorithm_id}/{algorithm.algorithm_version}"
                )
            result.algorithm_execution = algorithm
            audit = execution_storage.audit()
            snapshot = storage.snapshot()
            family_deduplicated_count = len(execution_storage.get_all())
            scope_record_count = (
                execution_storage._scope_record_count_before_family_dedup
                if execution_storage._scope_record_count_before_family_dedup is not None
                else family_deduplicated_count
            )
            required_coverage = [
                capability["field_coverage"].get(field, 0.0)
                for field in self.required_fields
            ]
            minimum = min(required_coverage) if required_coverage else 1.0
            quality_level = "high" if minimum >= 0.9 else (
                "medium" if minimum >= 0.5 else "low"
            )
            result.methodology = result.methodology or self.methodology
            result.data_quality = {
                **audit,
                "tool_field_coverage": capability["field_coverage"],
                "quality_level": quality_level,
                **result.data_quality,
            }
            result.evidence_level = self.evidence_record.get(
                "evidence_type", self.evidence_level,
            )
            result.source_capabilities = audit.get("source_capabilities", {})
            result.unsupported_conclusions = audit.get("unsupported_conclusions", [])
            result.data_as_of = audit.get("data_as_of", "")
            result.result_metadata = {
                "tool_name": self.name,
                "parameters": clean,
                "scope": scope.canonical(),
                "population_before_scope": snapshot.record_count,
                "population_after_scope": scope_record_count,
                "population_after_family_deduplication": family_deduplicated_count,
                "elapsed_ms": elapsed_ms,
                "evidence_level": self.evidence_record.get("evidence_type", self.evidence_level),
                "algorithm_id": algorithm.algorithm_id,
                "algorithm_version": algorithm.algorithm_version,
                "algorithm_execution": algorithm.model_dump(mode="json"),
                "evidence_sources": self.evidence_record.get("sources", []),
                "prohibited_claims": self.evidence_record.get("prohibited_claims", []),
                "confidence": quality_level,
                "source_capabilities": result.source_capabilities,
                "unsupported_conclusions": result.unsupported_conclusions,
                "data_as_of": result.data_as_of,
                "runtime_limits": {
                    "cpu_offloaded": self.cpu_bound,
                    "max_execution_seconds": self.max_execution_seconds,
                    "max_input_records": self.max_input_records,
                    "memory_budget_mb": self.memory_budget_mb,
                    "estimated_input_mb": estimated_input_mb,
                    "cancellation_checkpoints": ["before_execute", "after_execute"],
                },
                **result.result_metadata,
            }
            analyzed_count = int(result.result_metadata.get(
                "sample_size", result.result_metadata.get(
                    "analyzed_record_count", scope_record_count,
                ),
            ))
            sampled = analyzed_count < family_deduplicated_count
            result.provenance = ToolProvenance(
                dataset_id=snapshot.dataset_id,
                dataset_version_id=snapshot.version_id,
                dataset_content_hash=snapshot.content_hash,
                adapter=snapshot.adapter,
                input_record_count=snapshot.record_count,
                scope_record_count=scope_record_count,
                family_deduplicated_record_count=family_deduplicated_count,
                analyzed_record_count=analyzed_count,
                sampled=sampled,
                sample_size=analyzed_count if sampled else None,
                sampling_method=str(result.result_metadata.get(
                    "sampling_method", "tool_declared" if sampled else "none",
                )),
                field_coverage=capability["field_coverage"],
                algorithm_id=algorithm.algorithm_id,
                algorithm_version=algorithm.algorithm_version,
                parameters=clean,
                scope=scope.canonical(),
            )
            result.metrics = ExecutionMetrics(elapsed_ms=elapsed_ms)
            visual = _VISUALIZATION_DEFAULTS.get(result.result_type)
            if visual and "visualization" not in result.result_metadata:
                result.result_metadata["visualization"] = {
                    **visual, "default_mode": "natural",
                }
            for warning in audit.get("warning_records", []):
                affected = warning.get("affected_tools", [])
                if (self.name == "get_dataset_summary" or self.name in affected):
                    message = warning.get("message", "")
                    if message and message not in result.warnings:
                        result.warnings.append(message)
            if not result.summary:
                result.summary = self._default_summary(result)
        elif isinstance(result, (list, tuple)):
            # 深读工具历史上返回 FullPatent 列表；保留类型但仍由调用端记录参数。
            return result
        return result

    def envelope(self, result: AnalysisResult) -> ToolExecutionEnvelope:
        """Build the transport-neutral envelope after a successful run."""
        if result.provenance is None:
            raise ValueError(f"工具 {self.name} 缺少 provenance")
        return ToolExecutionEnvelope(
            tool=self.definition,
            result=result.model_dump(mode="json"),
            evidence=[{"source": item} for item in self.evidence_record.get("sources", [])],
            warnings=result.warnings,
            provenance=result.provenance,
            metrics=result.metrics,
        )

    @staticmethod
    def _default_summary(result: AnalysisResult) -> str:
        data = result.model_dump(exclude={"chart_html"})
        for key in ("data", "patents", "nodes", "edges", "years"):
            value = data.get(key)
            if isinstance(value, (list, dict)):
                return f"{result.result_type} 已生成，共 {len(value)} 项结构化结果。"
        return f"{result.result_type} 分析已完成。"

    @abstractmethod
    async def execute(self, storage: PatentDataStore,
                      **params) -> AnalysisResult:
        """执行分析。

        Args:
            storage: 专利数据访问接口
            **params: 用户/Agent 指定的参数

        Returns:
            结构化 AnalysisResult；浏览器可视化由受信任的前端渲染器生成。
        """
        ...

    def to_schema(self, storage: PatentDataStore | None = None) -> dict:
        """生成 Claude/OpenAI function calling 兼容的 JSON Schema"""
        schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.effective_parameters,
                "required": [
                    k for k, v in self.effective_parameters.items()
                    if v.get("required", False)
                ],
            },
        }
        if storage is not None:
            schema["availability"] = self.availability(storage)
        schema["methodology"] = self.methodology
        schema["evidence_level"] = self.evidence_record.get("evidence_type", self.evidence_level)
        schema["algorithm"] = self.evidence_record
        schema["cost_weight"] = self.cost_weight
        schema["definition"] = self.definition.model_dump(mode="json")
        return schema

    def to_llm_schema(self, storage: PatentDataStore) -> dict:
        """Return the single-source capability definition shown to an LLM."""
        capability = self.availability(storage)
        record = self.evidence_record
        returned_fields = self.returned_fields
        limitations = record.get("prohibited_claims", [])
        coverage = capability.get("field_coverage", {})
        availability = (
            "当前可执行" if capability["available"] else
            f"当前不可执行：{capability.get('reason') or '字段门槛不满足'}"
        )
        description = "\n".join(filter(None, [
            self.description.strip(),
            f"何时使用：用户的问题直接需要该工具返回的结构化指标时。",
            f"不适用：{'；'.join(limitations) if limitations else '不要用于超出方法声明的结论'}。",
            f"算法：{record.get('algorithm_id', '未登记')} {record.get('version', '')}；"
            f"证据等级：{record.get('evidence_type', self.evidence_level)}。",
            f"公式/口径：{record.get('formula', self.methodology)}。",
            f"适用条件：{'；'.join(record.get('conditions', [])) if isinstance(record.get('conditions'), list) else record.get('conditions', '')}。",
            f"字段覆盖：{json_safe_compact(coverage)}。{availability}。",
            f"返回字段：{'、'.join(returned_fields)}，以及 summary、methodology、"
            f"data_quality、warnings、result_metadata、prohibited_claims/coverage_manifest。",
            f"证据来源：{json_safe_compact(record.get('sources', []))}。",
            f"预计成本权重：{self.cost_weight}/3。",
        ]))
        return {
            "name": self.name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": self.effective_parameters,
                "required": [
                    name for name, item in self.effective_parameters.items()
                    if item.get("required", False)
                ],
                "additionalProperties": False,
            },
            "availability": capability,
            "cost_weight": self.cost_weight,
            "returned_fields": returned_fields,
        }


class ToolRegistry:
    """Tool 注册表（单例）"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' 已注册")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' 未注册")
        return self._tools[name]

    def get_all_schemas(self, storage: PatentDataStore | None = None,
                        for_llm: bool = False) -> list[dict]:
        """获取所有 Tool 的 JSON Schema（供 LLM function calling）"""
        if for_llm:
            if storage is None:
                raise ValueError("LLM 能力目录需要当前数据存储")
            return [t.to_llm_schema(storage) for t in self._tools.values()]
        return [t.to_schema(storage) for t in self._tools.values()]

    def get_all_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())


# 全局注册表实例
tool_registry = ToolRegistry()


def json_safe_compact(value: Any) -> str:
    """Small dependency-free rendering used inside tool descriptions."""
    import json
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
