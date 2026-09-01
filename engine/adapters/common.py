"""Shared normalization and merge policy for patent source adapters."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable

from models.patent import FieldConflict, FieldProvenance, PatentRecord


_DOC_NUMBER = re.compile(r"[^A-Z0-9]")
_PUBLICATION = re.compile(r"^(?P<country>[A-Z]{2})(?P<number>[0-9A-Z]+?)(?P<kind>[A-Z][0-9]?)?$")


def normalized_document_number(value: Any) -> str:
    """Return a stable compact ST.16/DOCDB-style identifier.

    The original source value is always retained separately.  This function is
    intentionally conservative: it strips presentation punctuation but never
    guesses a missing country or kind code.
    """
    return _DOC_NUMBER.sub("", str(value or "").upper())


def normalized_application_number(value: Any) -> str:
    normalized = normalized_document_number(value)
    if not normalized.startswith("US"):
        return normalized
    body = normalized[2:]
    if body.endswith("A"):
        body = body[:-1]
    # Google DOCDB exports encode US applications as filing-year + series/serial,
    # while USPTO wrappers commonly use the series/serial form (16/629,734).
    if len(body) == 12 and body[:4].isdigit() and body[4:].isdigit():
        body = body[4:]
    return "US" + body


def split_publication_number(value: Any) -> tuple[str, str, str]:
    normalized = normalized_document_number(value)
    match = _PUBLICATION.match(normalized)
    if not match:
        return "", normalized, ""
    return match.group("country"), match.group("number"), match.group("kind") or ""


def iso_date(value: Any) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) == 6:
        return f"{digits[:4]}-{digits[4:6]}"
    if len(digits) == 4:
        return digits
    return str(value or "").strip()


def stable_unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = normalized_document_number(text) if any(c.isdigit() for c in text) else text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def record_merge_key(record: PatentRecord) -> str:
    application = normalized_application_number(record.application_number)
    publication = record.normalized_patent_number or normalized_document_number(record.patent_number)
    return f"application:{application}" if application else f"publication:{publication}"


_SOURCE_PRIORITY = {
    # Full-text/bibliographic records are the canonical display record.  File
    # wrapper metadata is merged in for dated prosecution/legal events.
    "uspto_grant": 40,
    "google_patents": 30,
    "uspto_file_wrapper": 20,
    "wos": 10,
}


def _source_name(record: PatentRecord) -> str:
    return record.provenance.source.adapter if record.provenance else "unknown"


def merge_patent_records(records: Iterable[PatentRecord]) -> tuple[list[PatentRecord], int, int]:
    """Merge exact application/publication duplicates with field provenance.

    This is not a family collapse.  Only records sharing a normalized
    application number (preferred) or publication number are combined.
    """
    grouped: dict[str, list[PatentRecord]] = {}
    for record in records:
        grouped.setdefault(record_merge_key(record), []).append(record)

    merged: list[PatentRecord] = []
    duplicate_count = 0
    conflict_count = 0
    for key in sorted(grouped):
        candidates = sorted(
            grouped[key], key=lambda item: (-_SOURCE_PRIORITY.get(_source_name(item), 0), _source_name(item)),
        )
        target = deepcopy(candidates[0])
        for source in candidates[1:]:
            duplicate_count += 1
            before = len(target.field_conflicts)
            _merge_into(target, source)
            conflict_count += len(target.field_conflicts) - before
        merged.append(target)
    return merged, duplicate_count, conflict_count


def _merge_into(target: PatentRecord, source: PatentRecord) -> None:
    source_name = _source_name(source)
    target_name = _source_name(target)
    scalar_fields = (
        "application_number", "title", "abstract", "language", "publication_date",
        "filing_date", "grant_date", "priority_date", "description", "family_id",
        "legal_status", "legal_status_as_of", "jurisdiction", "kind_code", "data_as_of",
    )
    for field in scalar_fields:
        current = getattr(target, field)
        incoming = getattr(source, field)
        if not current and incoming:
            setattr(target, field, incoming)
            target.field_provenance.append(FieldProvenance(
                field_name=field, source=source_name,
                source_record_id=source.source_record_id,
            ))
        elif current and incoming and str(current).strip() != str(incoming).strip():
            target.field_conflicts.append(FieldConflict(
                field_name=field, kept_value=str(current), rejected_value=str(incoming),
                kept_source=target_name, rejected_source=source_name,
            ))

    list_fields = (
        "publication_numbers", "applicants", "inventors", "ipc_codes", "cpc_codes",
        "priority_numbers", "forward_citations", "backward_citations",
        "non_patent_references", "family_members", "family_details",
    )
    for field in list_fields:
        setattr(target, field, stable_unique([*getattr(target, field), *getattr(source, field)]))

    keyed_lists = (
        ("localized_titles", lambda item: (item.language, item.text)),
        ("localized_abstracts", lambda item: (item.language, item.text)),
        ("claims", lambda item: (item.language, item.number, item.text)),
        ("legal_events", lambda item: (item.event_date, item.event_code, item.description)),
        ("classifications", lambda item: (item.scheme, item.code)),
        ("citation_records", lambda item: (
            item.source_publication_number, item.target_publication_number, item.citation_type,
        )),
        ("applicant_parties", lambda item: (item.name, item.role, item.source_role)),
        ("assignee_parties", lambda item: (item.name, item.role, item.source_role)),
        ("current_rights_holder_parties", lambda item: (item.name, item.role, item.source_role)),
        ("inventor_parties", lambda item: (item.name, item.role, item.source_role)),
    )
    for field, identity in keyed_lists:
        current = list(getattr(target, field))
        seen = {identity(item) for item in current}
        for item in getattr(source, field):
            if identity(item) not in seen:
                current.append(item)
                seen.add(identity(item))
        setattr(target, field, current)
    target.field_provenance.extend(source.field_provenance)
