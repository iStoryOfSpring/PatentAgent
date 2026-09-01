"""Deterministic, reversible party-name normalization.

This module only collapses formatting and common corporate suffix variants.
Fuzzy matches, parent-company links and merger history require explicit reviewed
aliases and are intentionally outside the automatic path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata


_ENGLISH_SUFFIXES = {
    "co", "company", "corp", "corporation", "inc", "incorporated",
    "ltd", "limited", "llc", "plc", "gmbh", "ag", "sa", "spa", "bv",
}
_CHINESE_SUFFIXES = (
    "股份有限公司", "集团有限公司", "有限责任公司", "有限公司", "集团",
)


@dataclass(frozen=True)
class ResolvedEntity:
    entity_id: str
    canonical_name: str
    normalized_key: str
    original_name: str
    resolution_method: str = "deterministic_format_normalization"
    confidence: str = "high"
    review_required: bool = False


def normalize_entity_key(name: str) -> str:
    value = unicodedata.normalize("NFKC", str(name or "")).strip()
    for suffix in _CHINESE_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            value = value[:-len(suffix)].strip()
            break
    value = re.sub(r"[\.,，。·•'\"`´()（）\[\]{}]", " ", value)
    value = re.sub(r"[-_/\\]+", " ", value)
    tokens = [token for token in re.split(r"\s+", value) if token]
    while len(tokens) > 1 and tokens[-1].casefold() in _ENGLISH_SUFFIXES:
        tokens.pop()
    return " ".join(tokens).casefold().strip()


def resolve_entity(name: str, entity_type: str = "organization") -> ResolvedEntity | None:
    original = str(name or "").strip()
    key = normalize_entity_key(original)
    if not key:
        return None
    entity_id = "entity_" + hashlib.sha256(
        f"{entity_type}\0{key}".encode("utf-8")
    ).hexdigest()[:24]
    canonical = key.upper() if key.isascii() else key
    return ResolvedEntity(
        entity_id=entity_id,
        canonical_name=canonical,
        normalized_key=key,
        original_name=original,
    )


def resolve_semicolon_names(value, entity_type: str) -> list[ResolvedEntity]:
    if value is None:
        return []
    if isinstance(value, str):
        names = value.split(";")
    elif isinstance(value, (list, tuple, set)):
        names = value
    else:
        names = [value]
    resolved: dict[str, ResolvedEntity] = {}
    for name in names:
        entity = resolve_entity(str(name), entity_type=entity_type)
        if entity is not None:
            resolved.setdefault(entity.entity_id, entity)
    return sorted(resolved.values(), key=lambda item: item.entity_id)
