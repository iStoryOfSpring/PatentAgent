"""File adapters for official USPTO grant XML and Patent File Wrapper JSON."""

from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable

from engine.adapters.base import PatentAdapter
from engine.adapters.common import iso_date, normalized_document_number, stable_unique
from models.patent import (
    Claim, Classification, DataSource, FieldProvenance, LegalEvent,
    LocalizedText, Party, PatentRecord, RecordProvenance,
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _descendants(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (child for child in element.iter() if _local(child.tag) == name)


def _first(element: ET.Element, *names: str) -> ET.Element | None:
    wanted = set(names)
    return next((child for child in element.iter() if _local(child.tag) in wanted), None)


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _document_id(scope: ET.Element | None) -> tuple[str, str, str, str]:
    if scope is None:
        return "", "", "", ""
    country = _text(_first(scope, "country"))
    number = _text(_first(scope, "doc-number"))
    kind = _text(_first(scope, "kind"))
    date = _text(_first(scope, "date"))
    return country, number, kind, date


class USPTOGrantXmlAdapter(PatentAdapter):
    name = "uspto_grant"
    display_name = "USPTO Patent Grant Full Text XML"
    version = "1.0"

    def detect(self, filepath: str) -> bool:
        if not filepath.lower().endswith(".xml"):
            return False
        try:
            with open(filepath, "rb") as handle:
                head = handle.read(65536).lower()
            return b"us-patent-grant" in head or b"patent-grant" in head
        except OSError:
            return False

    def parse_file(self, filepath: str) -> list[PatentRecord]:
        self._reset_parse_diagnostics()
        with open(filepath, "rb") as handle:
            raw = handle.read()
        chunks = re.split(br"(?=<\?xml\s)", raw)
        records: list[PatentRecord] = []
        for index, chunk in enumerate(chunks, 1):
            if not chunk.strip():
                continue
            cleaned = re.sub(br"<!DOCTYPE[^>]*(?:\[[\s\S]*?\]\s*)?>", b"", chunk, count=1)
            try:
                root = ET.fromstring(cleaned)
            except ET.ParseError as exc:
                self.parse_diagnostics["expected"] += 1
                self.parse_diagnostics["detected"] += 1
                self._record_parse_issue(
                    filepath=filepath, record_id=f"document:{index}",
                    location=f"document:{index}", code="xml_record_truncated_or_invalid",
                    message=f"{type(exc).__name__}: {exc}", sample=chunk,
                )
                continue
            grant_nodes = [node for node in root.iter() if _local(node.tag) == "us-patent-grant"]
            if _local(root.tag) == "us-patent-grant":
                grant_nodes = [root]
            if not grant_nodes:
                self.parse_diagnostics["expected"] += 1
                self.parse_diagnostics["detected"] += 1
                self._record_parse_issue(
                    filepath=filepath, record_id=f"document:{index}",
                    location=f"document:{index}", code="xml_no_grant_record",
                    message="XML 文档中未发现 us-patent-grant 记录", sample=chunk,
                    outcome="skipped",
                )
                continue
            self.parse_diagnostics["expected"] += len(grant_nodes)
            self.parse_diagnostics["detected"] += len(grant_nodes)
            for grant_position, grant in enumerate(grant_nodes, 1):
                try:
                    records.append(self._parse_grant(grant, filepath, index, chunk))
                    self.parse_diagnostics["succeeded"] += 1
                except Exception as exc:
                    self._record_parse_issue(
                        filepath=filepath,
                        record_id=f"document:{index}:grant:{grant_position}",
                        location=f"document:{index}:grant:{grant_position}",
                        code="record_parse_failed",
                        message=f"{type(exc).__name__}: {exc}", sample=chunk,
                    )
        return records

    def _parse_grant(self, root: ET.Element, filepath: str, index: int, raw: bytes) -> PatentRecord:
        publication_ref = _first(root, "publication-reference")
        country, document_number, kind, publication_date = _document_id(publication_ref)
        publication = f"{country}{document_number}{kind}" if document_number else ""
        application_ref = _first(root, "application-reference")
        _, application_number, _, filing_date = _document_id(application_ref)
        title_node = _first(root, "invention-title")
        title = _text(title_node)
        language = str(title_node.attrib.get("lang", "en")).lower() if title_node is not None else "en"
        abstract = _text(_first(root, "abstract"))
        description = _text(_first(root, "description"))

        claims = []
        for position, node in enumerate(_descendants(root, "claim"), 1):
            number_raw = node.attrib.get("num") or re.sub(r"\D", "", node.attrib.get("id", ""))
            number = int(number_raw) if str(number_raw).isdigit() else position
            dependencies = []
            for reference in _descendants(node, "claim-ref"):
                ref_number = reference.attrib.get("num") or re.sub(r"\D", "", _text(reference))
                if str(ref_number).isdigit():
                    dependencies.append(int(ref_number))
            claims.append(Claim(
                number=number, text=_text(node), is_independent=not dependencies,
                depends_on=dependencies, language=language,
                claim_id=str(node.attrib.get("id", "")),
            ))

        ipc_codes = []
        classifications = []
        for classification in _descendants(root, "classification-ipcr"):
            code = "".join(_text(classification).split())
            if code:
                ipc_codes.append(code)
                classifications.append(Classification(scheme="IPC", code=code))
        cpc_codes = []
        for classification in _descendants(root, "classification-cpc-text"):
            code = "".join(_text(classification).split())
            if code:
                cpc_codes.append(code)
                classifications.append(Classification(scheme="CPC", code=code))

        applicants = [_text(node) for node in _descendants(root, "applicant")]
        assignees = [_text(node) for node in _descendants(root, "assignee")]
        inventors = [_text(node) for node in _descendants(root, "inventor")]
        backward = []
        for citation in _descendants(root, "patcit"):
            cited_country, cited_number, cited_kind, _ = _document_id(citation)
            if cited_number:
                backward.append(f"{cited_country}{cited_number}{cited_kind}")
        non_patent = [_text(node) for node in _descendants(root, "nplcit")]
        source_id = publication or application_number or f"record-{index}"
        provenance = RecordProvenance(
            source=DataSource(
                adapter=self.name, source_name="USPTO Open Data Portal",
                source_uri="https://data.uspto.gov/apis/bulk-data/search",
                license_note="Official USPTO bulk-data export; retain the acquisition manifest.",
            ), source_record_id=source_id, source_file=os.path.basename(filepath),
            raw_record_hash=hashlib.sha256(raw).hexdigest(),
        )
        applicant_names = stable_unique(applicants)
        assignee_names = stable_unique(assignees)
        inventor_names = stable_unique(inventors)
        return PatentRecord(
            patent_number=publication,
            normalized_patent_number=normalized_document_number(publication),
            application_number=f"US{application_number}" if application_number and not application_number.upper().startswith("US") else application_number,
            source_record_id=source_id, publication_numbers=[publication] if publication else [],
            title=title, abstract=abstract, language=language,
            localized_titles=[LocalizedText(language=language, text=title)] if title else [],
            localized_abstracts=[LocalizedText(language=language, text=abstract)] if abstract else [],
            applicants=applicant_names, inventors=inventor_names,
            ipc_codes=stable_unique(ipc_codes), cpc_codes=stable_unique(cpc_codes),
            classifications=classifications,
            publication_date=iso_date(publication_date), filing_date=iso_date(filing_date),
            grant_date=iso_date(publication_date), claims=claims, description=description,
            backward_citations=stable_unique(backward),
            non_patent_references=stable_unique(non_patent), jurisdiction=country or "US",
            kind_code=kind, source_file=os.path.basename(filepath), provenance=provenance,
            applicant_parties=[Party(name=name, role="applicant", source_role="applicant") for name in applicant_names],
            assignee_parties=[Party(name=name, role="assignee", source_role="assignee") for name in assignee_names],
            inventor_parties=[Party(name=name, role="inventor", source_role="inventor") for name in inventor_names],
            field_provenance=[
                FieldProvenance(field_name=field, source=self.name, source_record_id=source_id,
                                source_path=f"document:{index}")
                for field in ("title", "abstract", "claims", "description", "publication_date")
                if locals().get(field) or field in ("claims", "description") and (claims if field == "claims" else description)
            ],
        )


class USPTOFileWrapperJsonAdapter(PatentAdapter):
    name = "uspto_file_wrapper"
    display_name = "USPTO Patent File Wrapper JSON"
    version = "1.0"

    def detect(self, filepath: str) -> bool:
        if not filepath.lower().endswith(".json") or os.path.basename(filepath) == "patentagent-import.json":
            return False
        try:
            with open(filepath, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            probe = payload[0] if isinstance(payload, list) and payload else payload
            return _contains_any_key(
                probe, {"applicationmetadata", "eventdatabag", "applicationnumbertext"},
            )
        except (OSError, ValueError, TypeError):
            return False

    def parse_file(self, filepath: str) -> list[PatentRecord]:
        self._reset_parse_diagnostics()
        with open(filepath, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        rows = _unwrap_rows(payload)
        self.parse_diagnostics["expected"] = len(rows)
        self.parse_diagnostics["detected"] = len(rows)
        records = []
        for index, row in enumerate(rows, 1):
            try:
                records.append(self._parse_row(row, filepath, index))
                self.parse_diagnostics["succeeded"] += 1
            except Exception as exc:
                self._record_parse_issue(
                    filepath=filepath, record_id=f"record:{index}",
                    location=f"record:{index}", code="record_parse_failed",
                    message=f"{type(exc).__name__}: {exc}",
                    sample=json.dumps(row, ensure_ascii=False, sort_keys=True),
                )
        return records

    def _parse_row(self, row: dict[str, Any], filepath: str, index: int) -> PatentRecord:
        metadata = _dict_at(row, "applicationMetaData", "applicationMetadata", "metadata")
        application = _value(metadata, "applicationNumberText", "applicationNumber", "application_number")
        patent_number = _value(metadata, "patentNumber", "grantNumber", "publicationNumber")
        publication = normalized_document_number(
            patent_number if str(patent_number).upper().startswith("US") else f"US{patent_number}" if patent_number else ""
        )
        application_normalized = normalized_document_number(
            application if str(application).upper().startswith("US") else f"US{application}" if application else ""
        )
        source_id = publication or application_normalized or f"record-{index}"
        event_rows = _list_at(row, "eventDataBag", "events", "applicationEvents")
        events = []
        for event in event_rows:
            if not isinstance(event, dict):
                continue
            events.append(LegalEvent(
                event_code=str(_value(event, "eventCode", "code") or ""),
                description=str(_value(event, "eventDescriptionText", "eventDescription", "description") or ""),
                event_date=iso_date(_value(event, "eventDate", "date")),
                source=self.name, jurisdiction="US",
            ))
        status = str(_value(metadata, "applicationStatusDescriptionText", "applicationStatus", "status") or "")
        status_date = iso_date(_value(metadata, "applicationStatusDate", "statusDate"))
        title = str(_value(metadata, "inventionTitle", "title") or "")
        applicant_values = _list_at(metadata, "applicantBag", "applicants")
        applicants = stable_unique(
            _value(item, "applicantNameText", "name") if isinstance(item, dict) else item
            for item in applicant_values
        )
        raw_hash = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        provenance = RecordProvenance(
            source=DataSource(
                adapter=self.name, source_name="USPTO Patent File Wrapper",
                source_uri="https://data.uspto.gov/apis/patent-file-wrapper",
                license_note="Official USPTO export; retain acquisition date and endpoint version.",
            ), source_record_id=source_id, source_file=os.path.basename(filepath), raw_record_hash=raw_hash,
        )
        current_holder_values = _list_at(
            metadata, "currentRightsHolderBag", "currentAssigneeBag", "owners",
        )
        current_holders = stable_unique(
            _value(item, "name", "assigneeNameText", "ownerName")
            if isinstance(item, dict) else item
            for item in current_holder_values
        )
        return PatentRecord(
            patent_number=publication, normalized_patent_number=publication,
            application_number=application_normalized, source_record_id=source_id,
            publication_numbers=[publication] if publication else [], title=title, abstract="",
            localized_titles=[LocalizedText(language="en", text=title)] if title else [], language="en",
            applicants=applicants,
            applicant_parties=[Party(name=name, role="applicant", source_role="applicantBag") for name in applicants],
            current_rights_holder_parties=[
                Party(name=name, role="current_rights_holder", source_role="currentRightsHolderBag")
                for name in current_holders
            ],
            filing_date=iso_date(_value(metadata, "filingDate", "applicationFilingDate")),
            grant_date=iso_date(_value(metadata, "grantDate", "patentGrantDate")),
            legal_status=status, legal_status_as_of=status_date, legal_events=events,
            jurisdiction="US", data_as_of=status_date, provenance=provenance,
            source_file=os.path.basename(filepath),
            field_provenance=[
                FieldProvenance(field_name=field, source=self.name, source_record_id=source_id,
                                source_path=f"record:{index}")
                for field, present in (("legal_status", status), ("legal_events", events), ("filing_date", _value(metadata, "filingDate")))
                if present
            ],
        )


def _unwrap_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "data", "patentFileWrapperDataBag", "applications"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _unwrap_rows(value)
            if nested:
                return nested
    return [payload]


def _contains_any_key(payload: Any, wanted: set[str]) -> bool:
    """Inspect nested JSON keys without relying on serialization order/length."""
    stack = [payload]
    visited = 0
    while stack and visited < 100_000:
        current = stack.pop()
        visited += 1
        if isinstance(current, dict):
            if any(str(key).lower() in wanted for key in current):
                return True
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return False


def _dict_at(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _list_at(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, list):
                    return nested
    return []


def _value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", []):
            return value
    return ""
