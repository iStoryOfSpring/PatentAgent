"""Adapter for JSONL exports from Google Patents Public Data."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from engine.adapters.base import PatentAdapter
from engine.adapters.common import iso_date, normalized_document_number, split_publication_number, stable_unique
from models.patent import (
    Citation, Classification, DataSource, FieldProvenance, LocalizedText,
    Party, PatentRecord, RecordProvenance,
)


MAX_LOCALIZED_TEXT_CHARS = 2_000_000


class GooglePatentsExportAdapter(PatentAdapter):
    name = "google_patents"
    display_name = "Google Patents Public Data JSONL"
    version = "1.0"

    def detect(self, filepath: str) -> bool:
        if not filepath.lower().endswith((".jsonl", ".ndjson")):
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                first = next((line for line in handle if line.strip()), "")
            payload = json.loads(first)
            return "publication_number" in payload and any(
                key in payload for key in (
                    "title_localized", "abstract_localized", "family_id", "cpc",
                )
            )
        except (OSError, ValueError):
            return False

    def parse_file(self, filepath: str) -> list[PatentRecord]:
        self._reset_parse_diagnostics()
        records: list[PatentRecord] = []
        with open(filepath, "r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                self.parse_diagnostics["expected"] += 1
                self.parse_diagnostics["detected"] += 1
                try:
                    payload = json.loads(line)
                    records.append(self._parse_row(payload, filepath, line_number))
                    self.parse_diagnostics["succeeded"] += 1
                except Exception as exc:
                    self._record_parse_issue(
                        filepath=filepath, record_id=f"line:{line_number}",
                        location=f"line:{line_number}", code="record_parse_failed",
                        message=f"{type(exc).__name__}: {exc}", sample=line,
                    )
        return records

    def _parse_row(self, row: dict[str, Any], filepath: str, line_number: int) -> PatentRecord:
        publication = str(row.get("publication_number") or "").strip()
        jurisdiction, _, kind_from_number = split_publication_number(publication)
        source_id = publication or str(row.get("application_number") or line_number)
        titles = _localized(row.get("title_localized") or row.get("title"))
        abstracts = _localized(row.get("abstract_localized") or row.get("abstract"))
        claims_text = _localized(row.get("claims_localized") or row.get("claims"))
        language = _preferred_language(titles, abstracts)
        title = _preferred_text(titles)
        abstract = _preferred_text(abstracts)
        claims = []
        if claims_text:
            from models.patent import Claim
            # Google exposes localized claim-text blobs rather than structural
            # dependency data. Do not invent dependent-claim relationships.
            claims = [Claim(
                number=1, text=item.text, is_independent=True,
                language=item.language, claim_id=f"localized_blob:{item.language}",
            ) for item in claims_text]

        ipc_codes, classifications = _classification_values(row.get("ipc"), "IPC")
        cpc_codes, cpc_records = _classification_values(row.get("cpc"), "CPC")
        citations = row.get("citation") or row.get("citations") or []
        backward = stable_unique(
            item.get("publication_number", "") if isinstance(item, dict) else item
            for item in citations
        )
        citation_records = [
            Citation(
                patent_number=number, citation_type="backward", cites=number,
                source_publication_number=publication,
                target_publication_number=number, source="google_patents",
            ) for number in backward
        ]
        raw_hash = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        provenance = RecordProvenance(
            source=DataSource(
                adapter=self.name, source_name="Google Patents Public Data",
                source_uri="https://console.cloud.google.com/marketplace/product/google_patents_public_datasets/google-patents-public-data",
                license_note="CC BY 4.0; verify export attribution in the import manifest.",
            ),
            source_record_id=source_id, source_file=os.path.basename(filepath), raw_record_hash=raw_hash,
        )
        field_provenance = [
            FieldProvenance(field_name=field, source=self.name, source_record_id=source_id,
                            source_path=f"line:{line_number}")
            for field, present in (
                ("title", titles), ("abstract", abstracts),
                ("publication_date", row.get("publication_date")),
                ("family_id", row.get("family_id")),
            ) if present
        ]
        applicant_names = _names(row.get("applicant"))
        assignee_names = _names(row.get("assignee"))
        current_holder_names = _names(
            row.get("current_assignee") or row.get("current_owner")
        )
        inventor_names = _names(row.get("inventor"))
        return PatentRecord(
            patent_number=publication,
            normalized_patent_number=normalized_document_number(publication),
            application_number=str(row.get("application_number") or ""),
            source_record_id=source_id,
            publication_numbers=[publication] if publication else [],
            title=title, abstract=abstract, language=language,
            localized_titles=titles, localized_abstracts=abstracts,
            applicants=applicant_names,
            inventors=inventor_names,
            ipc_codes=ipc_codes, cpc_codes=cpc_codes,
            classifications=[*classifications, *cpc_records],
            publication_date=iso_date(row.get("publication_date")),
            filing_date=iso_date(row.get("filing_date")),
            grant_date=iso_date(row.get("grant_date")),
            priority_date=iso_date(row.get("priority_date")),
            priority_numbers=stable_unique(
                item.get("publication_number") or item.get("application_number") or ""
                for item in (row.get("priority_claim") or []) if isinstance(item, dict)
            ),
            claims=claims,
            description=_preferred_text(_localized(
                row.get("description_localized") or row.get("description")
            )),
            backward_citations=backward,
            non_patent_references=stable_unique(
                item.get("npl_text", "") if isinstance(item, dict) else item
                for item in [
                    *(row.get("non_patent_citation") or []),
                    *(row.get("citation") or row.get("citations") or []),
                ]
            ),
            family_members=stable_unique(row.get("family_members") or []),
            family_id=str(row.get("family_id") or ""),
            jurisdiction=str(row.get("country_code") or jurisdiction),
            kind_code=str(row.get("kind_code") or kind_from_number),
            data_as_of=iso_date(row.get("data_as_of")),
            citation_records=citation_records, provenance=provenance,
            applicant_parties=[
                Party(name=name, role="applicant", source_role="applicant")
                for name in applicant_names
            ],
            assignee_parties=[
                Party(name=name, role="assignee", source_role="assignee")
                for name in assignee_names
            ],
            current_rights_holder_parties=[
                Party(name=name, role="current_rights_holder", source_role="current_assignee")
                for name in current_holder_names
            ],
            inventor_parties=[
                Party(name=name, role="inventor", source_role="inventor")
                for name in inventor_names
            ],
            field_provenance=field_provenance,
            source_file=os.path.basename(filepath),
        )


def _localized(value: Any) -> list[LocalizedText]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    result = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("value") or "").strip()
            language = str(item.get("language") or item.get("lang") or "und").lower()
            truncated = bool(item.get("truncated", False))
        else:
            text, language, truncated = str(item).strip(), "und", False
        if text:
            if len(text) > MAX_LOCALIZED_TEXT_CHARS:
                text = text[:MAX_LOCALIZED_TEXT_CHARS]
                truncated = True
            result.append(LocalizedText(language=language, text=text, truncated=truncated))
    return result


def _preferred_text(items: list[LocalizedText]) -> str:
    if not items:
        return ""
    for language in ("en", "zh", "und"):
        match = next((item.text for item in items if item.language.startswith(language)), None)
        if match:
            return match
    return items[0].text


def _preferred_language(*groups: list[LocalizedText]) -> str:
    for group in groups:
        if group:
            preferred = _preferred_text(group)
            return next((item.language for item in group if item.text == preferred), "und")
    return "und"


def _names(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return stable_unique(
        item.get("name", "") if isinstance(item, dict) else item for item in items
    )


def _classification_values(value: Any, scheme: str):
    items = value if isinstance(value, list) else ([value] if value else [])
    codes = stable_unique(item.get("code", "") if isinstance(item, dict) else item for item in items)
    return codes, [Classification(scheme=scheme, code=code) for code in codes]
