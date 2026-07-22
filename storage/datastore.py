"""轻量级专利数据存储 (v2.2: 多数据源适配)"""

from dataclasses import dataclass, field
import hashlib
import json
import os
import re
from typing import Any, Optional

import pandas as pd

from engine.preprocessing import prepare_patent_df
from patent_agent.domain import DatasetSnapshot

# v2.2: Known field mapping — DataFrame columns → FullPatent field names
_FIELD_MAP = {
    "forward_citations": "forward_citations",
    "cpc_codes": "cpc_codes",
    "claims_json": "claims_json",
    "description": "description",
    "legal_status": "legal_status",
    "legal_events": "legal_events_json",
    "multilingual_text": "localized_titles_json",
}


@dataclass
class DatasetSummary:
    total_patents: int
    year_range: tuple[int, int]
    ipc_sections: list[str]
    top_applicants: list[tuple[str, int]]


class PatentDataStore:
    """DataFrame 包装器，提供统一的查询接口。

    v2.2: 支持多数据源。通过 has_field() 检测字段可用性，
    工具在缺失字段时自动降级。
    """

    def __init__(self, df: Optional[pd.DataFrame] = None, source_dir: str = ""):
        self._df = df if df is not None else pd.DataFrame()
        self._adapter_name: str = ""
        self._source_dir = source_dir
        self._load_diagnostics: dict[str, Any] = {}
        self._import_report: dict[str, Any] = {}
        self._cached_summary = None
        if not self._df.empty:
            self._ensure_columns()

    @property
    def adapter_name(self) -> str:
        return self._adapter_name

    def has_field(self, field_name: str) -> bool:
        """检测底层数据源是否提供至少一个实际非空值。"""
        col = _FIELD_MAP.get(field_name, field_name)
        return self.field_coverage(col) > 0

    @staticmethod
    def _has_value(value: Any) -> bool:
        """统一识别字符串、列表及标量中的有效值。"""
        if value is None:
            return False
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def field_coverage(self, field_name: str) -> float:
        """返回字段有效值覆盖率（0..1），不存在的字段为 0。"""
        col = _FIELD_MAP.get(field_name, field_name)
        if col not in self._df.columns or self._df.empty:
            return 0.0
        return round(float(self._df[col].map(self._has_value).mean()), 4)

    def audit(self) -> dict[str, Any]:
        """生成 API、工具能力门禁和报告共同使用的数据质量审计。"""
        fields = {
            name: self.field_coverage(name)
            for name in (
                "patent_number", "title", "abstract", "publication_date",
                "ipc", "applicants", "inventors", "backward_citations",
                "forward_citations", "family_members", "claims_json",
                "description", "legal_status",
                "source_record_id", "publication_numbers",
                "priority_numbers", "non_patent_references",
                "legal_events", "multilingual_text",
            )
        }
        network = self._citation_network_audit()
        collaboration = self._collaboration_audit()
        warning_records: list[dict[str, Any]] = []
        def warn(code: str, message: str, affected_tools: list[str]) -> None:
            warning_records.append({
                "code": code, "message": message,
                "affected_tools": affected_tools,
            })
        if fields["publication_date"] < 0.95:
            warn("publication_date_incomplete", "公开日期存在缺失，时间趋势与专利年龄指标会降级。", [
                "analyze_patent_trend", "analyze_lifecycle", "analyze_ipc_distribution",
                "analyze_burst_terms", "analyze_yearly_keywords", "analyze_tech_roadmap",
                "analyze_patent_valuation", "analyze_competitor_evolution",
            ])
        if fields["backward_citations"] == 0:
            warn("backward_citations_missing", "缺少专利后向引证，无法构建可靠的引证网络。", [
                "analyze_tech_roadmap", "analyze_patent_valuation",
            ])
        elif network["edge_resolution_rate"] < 0.2:
            warn("internal_citation_network_open", (
                f"内部引证边解析率仅 {network['edge_resolution_rate']:.1%}，"
                "当前语料不能视为闭合引证网络。"
            ), ["analyze_tech_roadmap", "analyze_patent_valuation"])
        if fields["forward_citations"] == 0:
            warn("external_forward_citations_missing", "当前加载数据中没有外部前向被引字段，不能直接计算外部前向被引次数。", [
                "analyze_patent_valuation",
            ])
        if fields["claims_json"] == 0 or fields["legal_status"] == 0:
            warn("fto_fields_missing", "当前加载数据缺少权利要求或法律状态，仅可进行初步相关专利筛查，不构成 FTO 法律意见。", [
                "search_patents", "read_patent_details",
            ])
        if fields["family_members"] < 0.5:
            warn("family_coverage_low", "同族覆盖低于 50%，三方专利和基于同族的价值指标退出正式评分。", [
                "analyze_patent_valuation",
            ])
        warnings = [item["message"] for item in warning_records]
        return {
            "adapter": self.adapter_name or "unknown",
            "total_patents": len(self._df),
            "field_coverage": fields,
            "date_completeness": fields["publication_date"],
            "citation_availability": max(
                fields["backward_citations"], fields["forward_citations"]),
            "external_forward_citation_coverage": fields["forward_citations"],
            "internal_citation_network": network,
            "family_availability": fields["family_members"],
            "claims_availability": fields["claims_json"],
            "collaboration_coverage": collaboration,
            "dataset_manifest": self._load_manifest(),
            "batch_completeness": self._load_diagnostics,
            "import_report": self._import_report,
            "source_capabilities": self._import_report.get("source_capabilities", {}),
            "data_as_of": self._data_as_of(),
            "unsupported_conclusions": self._unsupported_conclusions(
                fields, self._import_report.get("source_capabilities", {}),
            ),
            "warning_records": warning_records,
            "warnings": warnings,
        }

    def _data_as_of(self) -> str:
        if "data_as_of" not in self._df.columns or self._df.empty:
            return ""
        values = self._df["data_as_of"].dropna().astype(str)
        values = values[values.str.strip().ne("")]
        return max(values) if not values.empty else ""

    @staticmethod
    def _unsupported_conclusions(
        fields: dict[str, float], source_capabilities: dict | None = None,
    ) -> list[str]:
        unsupported = ["正式专利价值或交易价格结论"]
        if (
            fields.get("claims_json", 0) < 1.0 or
            fields.get("legal_status", 0) < 1.0
        ):
            unsupported.extend(["权利要求范围判断", "侵权比对", "正式 FTO 意见"])
        capabilities = source_capabilities or {}
        has_current_status = any(
            bool(item.get("current_legal_status"))
            for item in capabilities.values() if isinstance(item, dict)
        )
        if fields.get("legal_status", 0) < 1.0 or not has_current_status:
            unsupported.extend(["实时有效性判断", "当前权利状态判断"])
        if fields.get("external_forward_citations", fields.get("forward_citations", 0)) == 0:
            unsupported.append("基于完整外部前向引证的影响力结论")
        return unsupported

    @staticmethod
    def _split_values(value: Any) -> list[str]:
        if not PatentDataStore._has_value(value):
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in re.split(r'[;\n]+', str(value)) if item.strip()]

    @staticmethod
    def _citation_key(value: str) -> str:
        return re.sub(r'[^A-Z0-9]', '', str(value).upper())

    def _citation_network_audit(self) -> dict[str, Any]:
        if self._df.empty:
            return {"total_edges": 0, "resolved_internal_edges": 0,
                    "edge_resolution_rate": 0.0, "participating_node_rate": 0.0,
                    "office_composition": {}, "european_style_share": 0.0}
        aliases: dict[str, int] = {}
        for idx, row in self._df.iterrows():
            values = [row.get('patent_number', '')]
            for col in ('publication_numbers', 'family_members'):
                values.extend(self._split_values(row.get(col, '')))
            for value in values:
                key = self._citation_key(value)
                if key:
                    aliases[key] = idx
        total_edges = 0
        resolved = 0
        nodes: set[int] = set()
        for idx, value in self._df.get(
            'backward_citations', pd.Series('', index=self._df.index)
        ).items():
            for citation in self._split_values(value):
                total_edges += 1
                target = aliases.get(self._citation_key(citation))
                if target is not None and target != idx:
                    resolved += 1
                    nodes.update((idx, target))
        countries = self._df.get('country', pd.Series('Unknown', index=self._df.index))
        office_counts = countries.fillna('Unknown').astype(str).str.upper().value_counts()
        comparable = {'DE', 'EP', 'GB', 'WO'}
        comparable_count = sum(int(office_counts.get(code, 0)) for code in comparable)
        return {
            "total_edges": total_edges,
            "resolved_internal_edges": resolved,
            "edge_resolution_rate": round(resolved / total_edges, 4) if total_edges else 0.0,
            "participating_node_rate": round(len(nodes) / len(self._df), 4),
            "office_composition": {str(k): int(v) for k, v in office_counts.head(20).items()},
            "european_style_share": round(comparable_count / len(self._df), 4),
            "direction": "citing_patent_to_cited_patent",
            "scope": "internal_corpus_only",
        }

    def _collaboration_audit(self) -> dict[str, Any]:
        applicants = self._df.get('applicants', pd.Series('', index=self._df.index))
        multi = int(applicants.map(lambda value: len(self._split_values(value)) >= 2).sum())
        return {
            "multi_applicant_patents": multi,
            "multi_applicant_rate": round(multi / len(self._df), 4) if len(self._df) else 0.0,
        }

    def _load_manifest(self) -> dict[str, Any] | None:
        if not self._source_dir:
            return None
        path = os.path.join(self._source_dir, 'manifest.json')
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {"status": "invalid", "path": path}

    def _ensure_columns(self):
        """确保 year/month/country 列存在 (v2.1 Parquet修复)"""
        needs_prep = (
            'year' not in self._df.columns or
            'month' not in self._df.columns or
            'country' not in self._df.columns or
            self._df['year'].isna().all()
        )
        if needs_prep:
            self._df = prepare_patent_df(self._df)
        # Fallback: force month if still missing (Parquet edge case)
        if 'month' not in self._df.columns and 'date' in self._df.columns:
            import pandas as pd
            dates = pd.to_datetime(self._df['date'], errors='coerce')
            self._df['month'] = dates.dt.month.fillna(1).astype(int)

    def load_from_miner(self, miner) -> "PatentDataStore":
        """从 PatentMiner 批量加载"""
        df = miner.batch_process()
        if not df.empty:
            self._df = df
            self._ensure_columns()
            self._cached_summary = None
        return self

    def load_dataframe(self, df: pd.DataFrame) -> "PatentDataStore":
        """直接加载 DataFrame"""
        self._df = df.copy()
        self._ensure_columns()
        self._cached_summary = None

    # ── 查询 ──
    def query(self,
              year_start: Optional[int] = None,
              year_end: Optional[int] = None,
              ipc_filter: Optional[list[str]] = None,
              applicant_filter: Optional[str] = None,
              text_query: Optional[str] = None,
              ) -> pd.DataFrame:
        """统一查询接口，支持多条件过滤。

        v2.1: 不复制完整 DataFrame。链式 filter 返回视图/子集，仅在最终返回时复制。
        """
        df = self._df
        if 'year' not in df.columns:
            return df.copy()

        mask = pd.Series(True, index=df.index)
        if year_start is not None:
            mask &= df['year'] >= year_start
        if year_end is not None:
            mask &= df['year'] <= year_end

        if ipc_filter:
            def _match_ipc(val):
                if pd.isna(val):
                    return False
                codes = [c.strip()[:4] for c in str(val).split(';')]
                return any(c in ipc_filter for c in codes)
            mask &= df.get('ipc', pd.Series(dtype=str)).apply(_match_ipc)

        if applicant_filter:
            mask &= df.get('applicants', pd.Series(dtype=str)).str.contains(
                applicant_filter, case=False, na=False)

        if text_query:
            tokens = [
                token.lower() for token in str(text_query).split()
                if len(token.strip()) >= 3
            ]
            if tokens:
                haystack = (
                    df.get('title', pd.Series('', index=df.index)).fillna('').astype(str)
                    + ' ' +
                    df.get('abstract', pd.Series('', index=df.index)).fillna('').astype(str)
                ).str.lower()
                text_mask = pd.Series(False, index=df.index)
                for token in tokens:
                    text_mask |= haystack.str.contains(token, regex=False, na=False)
                mask &= text_mask

        # Only copy the filtered subset
        filtered = df.loc[mask]
        return filtered.copy() if not mask.all() else filtered

    def filtered(self, **filters) -> "PatentDataStore":
        """创建会话/计划范围内的隔离数据视图，不修改全局数据集。"""
        scoped = PatentDataStore(self.query(**filters))
        scoped._adapter_name = self._adapter_name
        scoped._source_dir = self._source_dir
        scoped._load_diagnostics = self._load_diagnostics
        scoped._import_report = self._import_report
        return scoped

    def get_columns(self, columns: list[str]) -> pd.DataFrame:
        """仅返回指定列的子集，减少内存占用。

        v2.1: 工具只请求需要的列，避免每次加载 300MB 全量 DataFrame。
        例如 TrendTool 只需 ['year', 'month', 'ipc', 'applicants']。
        """
        available = [c for c in columns if c in self._df.columns]
        # 工具经常会添加临时列；返回浅层隔离副本，避免污染共享数据集。
        return self._df.loc[:, available].copy()

    def get_all(self) -> pd.DataFrame:
        return self._df  # View, not copy. Callers that need a copy should do it themselves.

    def dataset_fingerprint(self) -> str:
        """Stable content identity used to invalidate conversational evidence."""
        if self._df.empty:
            return "empty"
        identity_column = (
            "source_record_id" if "source_record_id" in self._df.columns
            else "patent_number"
        )
        values = self._df.get(
            identity_column, pd.Series("", index=self._df.index)
        ).fillna("").astype(str).sort_values()
        digest = hashlib.sha256()
        digest.update((self.adapter_name or "unknown").encode("utf-8"))
        digest.update(str(len(self._df)).encode("ascii"))
        for value in values:
            digest.update(value.encode("utf-8", errors="ignore"))
            digest.update(b"\0")
        return digest.hexdigest()

    def snapshot(self) -> DatasetSnapshot:
        """Return the versioned logical identity consumed by tool provenance."""
        content_hash = self.dataset_fingerprint()
        dataset_key = hashlib.sha256(
            f"{self.adapter_name or 'unknown'}\0{self._source_dir}".encode(
                "utf-8", errors="ignore",
            )
        ).hexdigest()[:24]
        audit = self.audit()
        return DatasetSnapshot(
            dataset_id=f"dataset_{dataset_key}",
            version_id=f"version_{content_hash[:24]}",
            content_hash=content_hash,
            adapter=self.adapter_name or "unknown",
            sources=[self._source_dir] if self._source_dir else [],
            record_count=len(self._df),
            field_coverage=audit.get("field_coverage", {}),
        )

    # ── 元数据 ──
    def get_summary(self) -> DatasetSummary:
        """数据集概况。v2.1: 缓存结果避免重复扫描。"""
        if hasattr(self, '_cached_summary') and self._cached_summary is not None:
            return self._cached_summary

        df = self._df
        total = len(df)
        if total == 0 or 'year' not in df.columns:
            self._cached_summary = DatasetSummary(
                total_patents=0, year_range=(0, 0),
                ipc_sections=[], top_applicants=[],
            )
            return self._cached_summary
        years = df['year'].dropna()
        yr_range = (int(years.min()), int(years.max())) if not years.empty else (0, 0)

        ipc_sections = set()
        for codes in df.get('ipc', pd.Series(dtype=str)).dropna():
            for code in str(codes).split(';'):
                s = code.strip()[:1]
                if s and s.isalpha():
                    ipc_sections.add(s)

        applicants = df.get('applicants', pd.Series(dtype=str)).dropna()
        app_counts = {}
        for apps in applicants:
            for a in apps.split(';'):
                a = a.strip()
                if a:
                    app_counts[a] = app_counts.get(a, 0) + 1
        top = sorted(app_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        self._cached_summary = DatasetSummary(
            total_patents=total,
            year_range=yr_range,
            ipc_sections=sorted(ipc_sections),
            top_applicants=top,
        )
        return self._cached_summary

    def get_available_years(self) -> list[int]:
        years = self._df['year'].dropna().unique()
        return sorted(int(y) for y in years)

    def get_available_ipc_sections(self) -> list[str]:
        sections = set()
        for codes in self._df.get('ipc', pd.Series(dtype=str)).dropna():
            for code in str(codes).split(';'):
                s = code.strip()[:1]
                if s and s.isalpha():
                    sections.add(s)
        return sorted(sections)

    @property
    def is_empty(self) -> bool:
        return self._df.empty
