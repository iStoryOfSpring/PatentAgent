"""Registry-driven, file-first patent dataset importer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from engine.adapters.base import PatentAdapter
from engine.adapters.common import merge_patent_records
from engine.adapters.google_patents import GooglePatentsExportAdapter
from engine.adapters.uspto import USPTOFileWrapperJsonAdapter, USPTOGrantXmlAdapter
from engine.adapters.wos_adapter import WoSAdapter
from models.patent import PatentRecord
from patent_agent.domain import (
    FileDetection, ImportIssue, ImportManifest, ImportReport, SourceCapabilities, SourceFormat,
)


FORMAT_ADAPTERS: dict[str, type[PatentAdapter]] = {
    "wos_dii": WoSAdapter,
    "google_patents_jsonl": GooglePatentsExportAdapter,
    "uspto_grant_xml": USPTOGrantXmlAdapter,
    "uspto_file_wrapper_json": USPTOFileWrapperJsonAdapter,
}

SOURCE_CAPABILITIES: dict[str, SourceCapabilities] = {
    "wos": SourceCapabilities(
        classifications=True, citations=True, family=True,
    ),
    "google_patents": SourceCapabilities(
        multilingual_text=True, claims=True, description=True,
        classifications=True, citations=True, family=True,
    ),
    "uspto_grant": SourceCapabilities(
        claims=True, description=True, classifications=True, citations=True,
    ),
    "uspto_file_wrapper": SourceCapabilities(
        legal_events=True, prosecution_events=True,
    ),
}


class PatentDatasetImporter:
    def __init__(self, adapters: Iterable[PatentAdapter] | None = None):
        self.adapters = list(adapters or (
            WoSAdapter(), GooglePatentsExportAdapter(), USPTOGrantXmlAdapter(),
            USPTOFileWrapperJsonAdapter(),
        ))

    def import_directory(
        self, input_dir: str, source_format: SourceFormat = "auto",
    ) -> tuple[list[PatentRecord], ImportReport, ImportManifest | None]:
        root = Path(input_dir).resolve()
        if not root.is_dir():
            return [], ImportReport(warnings=[f"数据目录不存在: {root}"]), None
        manifest = self._load_manifest(root)
        file_specs = self._file_specs(root, manifest, source_format)
        report = ImportReport(files_seen=len(file_specs))
        parsed: list[PatentRecord] = []
        formats_seen: set[str] = set()
        for path, declared_format, expected_hash, detection_method in file_specs:
            if expected_hash:
                actual = _sha256(path)
                if actual.lower() != expected_hash.lower():
                    raise ValueError(f"导入文件校验失败: {path.name}")
            adapter, resolved_format = self._resolve_adapter(path, declared_format)
            if adapter is None:
                report.file_detections.append(FileDetection(
                    file=path.name, source_format="auto", method="unknown", matched=False,
                ))
                report.issues.append(ImportIssue(
                    file=path.name, code="unsupported_format", message="没有适配器可识别此文件",
                ))
                continue
            report.file_detections.append(FileDetection(
                file=path.name, source_format=resolved_format,
                method=detection_method, matched=True,
            ))
            formats_seen.add(resolved_format)
            try:
                records = adapter.parse_file(str(path))
                if manifest is not None:
                    self._apply_manifest_metadata(records, manifest)
                parsed.extend(records)
            except Exception as exc:
                report.records_failed += 1
                report.issues.append(ImportIssue(
                    file=path.name, code="parse_failed", message=str(exc),
                ))

        merged, duplicates, conflicts = merge_patent_records(parsed)
        report.source_formats = sorted(formats_seen)
        report.records_parsed = len(parsed)
        report.records_imported = len(merged)
        report.duplicates_merged = duplicates
        report.field_conflicts = conflicts
        report.field_coverage = _field_coverage(merged)
        report.language_distribution = _language_distribution(merged)
        adapters_seen = {
            record.provenance.source.adapter
            for record in parsed if record.provenance is not None
        }
        report.source_capabilities = {
            name: SOURCE_CAPABILITIES.get(name, SourceCapabilities())
            for name in sorted(adapters_seen)
        }
        if conflicts:
            report.warnings.append(f"跨来源合并发现 {conflicts} 个字段冲突；已保留来源和冲突值。")
        truncated = sum(
            item.truncated
            for record in merged
            for item in [*record.localized_titles, *record.localized_abstracts]
        )
        if truncated:
            report.warnings.append(f"有 {truncated} 个超大多语言文本字段已按安全上限截断。")
        if report.field_coverage.get("claims", 0) == 0:
            report.warnings.append("导入记录不含权利要求全文，不能据此形成 FTO 结论。")
        if not any(item.current_legal_status for item in report.source_capabilities.values()):
            report.warnings.append("数据源不提供实时法律状态；状态字段仅代表标注日期时的来源记录。")
        return merged, report, manifest

    @staticmethod
    def _apply_manifest_metadata(
        records: list[PatentRecord], manifest: ImportManifest,
    ) -> None:
        """Attach dataset-level source facts without overwriting record facts."""
        for record in records:
            if not record.data_as_of:
                record.data_as_of = manifest.data_as_of or manifest.retrieved_at
            if record.provenance is None:
                continue
            source = record.provenance.source
            if not source.source_name:
                source.source_name = manifest.source_name
            if not source.source_uri:
                source.source_uri = manifest.source_uri
            if not source.license_note:
                source.license_note = manifest.license_note

    @staticmethod
    def _load_manifest(root: Path) -> ImportManifest | None:
        path = root / "patentagent-import.json"
        if not path.is_file():
            return None
        return ImportManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def _file_specs(
        self, root: Path, manifest: ImportManifest | None, source_format: SourceFormat,
    ) -> list[tuple[Path, str, str, str]]:
        if manifest and manifest.files:
            specs = []
            for item in manifest.files:
                path = (root / item.path).resolve()
                try:
                    path.relative_to(root)
                except ValueError as exc:
                    raise ValueError(f"导入清单包含目录外路径: {item.path}") from exc
                if path.is_file():
                    chosen = source_format if source_format != "auto" else item.source_format
                    method = "user_selected" if source_format != "auto" else (
                        "manifest" if item.source_format != "auto" else "content_signature"
                    )
                    specs.append((path, chosen, item.sha256, method))
            return specs
        return [
            (
                path, source_format, "",
                "user_selected" if source_format != "auto" else "content_signature",
            ) for path in sorted(root.iterdir())
            if path.is_file() and not path.name.startswith(".")
            and path.name not in {"patentagent-import.json", "manifest.json"}
        ]

    def _resolve_adapter(self, path: Path, source_format: str) -> tuple[PatentAdapter | None, str]:
        if source_format != "auto":
            adapter_type = FORMAT_ADAPTERS.get(source_format)
            if adapter_type is None:
                return None, source_format
            # An explicit format is the recovery path for a valid vendor export
            # whose wrapper or extension differs from our content signature.
            # Parsing remains strict and reports a structured parse_failed issue.
            return adapter_type(), source_format
        matches: list[tuple[PatentAdapter, str]] = []
        for format_name, adapter_type in FORMAT_ADAPTERS.items():
            adapter = next((item for item in self.adapters if isinstance(item, adapter_type)), adapter_type())
            if adapter.detect(str(path)):
                matches.append((adapter, format_name))
        if len(matches) == 1:
            return matches[0]
        # Never guess when no signature or multiple signatures match. This is
        # safer than silently feeding a file to the first registered adapter.
        return None, "auto"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _field_coverage(records: list[PatentRecord]) -> dict[str, float]:
    if not records:
        return {}
    fields = (
        "patent_number", "application_number", "title", "abstract", "claims",
        "description", "ipc_codes", "cpc_codes", "backward_citations",
        "family_id", "family_members", "legal_events", "legal_status",
    )
    return {
        field: round(sum(bool(getattr(record, field)) for record in records) / len(records), 4)
        for field in fields
    }


def _language_distribution(records: list[PatentRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        language = record.language or "und"
        counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items()))
