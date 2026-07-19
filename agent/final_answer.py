"""Canonical, user-facing final-answer parsing and legacy JSON repair."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable


VALID_FOLLOWUP_KINDS = {"explain", "drilldown", "new_analysis", "method"}
CANONICAL_KEYS = {"answer_markdown", "evidence_refs", "followup_suggestions"}

FIELD_LABELS = {
    "answer": "核心结论",
    "conclusion": "核心结论",
    "summary": "核心结论",
    "details": "分维度分析",
    "findings": "关键发现",
    "key_findings": "关键发现",
    "key_points": "关键要点",
    "trend_summary": "趋势判断",
    "methodology": "方法说明",
    "limitations": "方法与数据限制",
    "warnings": "数据警告",
    "recommendations": "建议",
    "year": "年份",
    "stage": "阶段",
    "theme": "技术主题",
    "title": "标题",
    "name": "名称",
    "label": "名称",
    "representative_patents": "代表专利",
    "patents": "专利",
    "applicants": "申请人",
    "ipc": "IPC 分类",
    "ipc_codes": "IPC 分类",
}

ANSWER_ALIASES = ("answer_markdown", "answer", "conclusion", "summary")
FOLLOWUP_ALIASES = (
    "followup_suggestions", "follow_up_questions", "followup_questions",
)
EVIDENCE_ALIASES = ("evidence_refs", "evidence_references", "sources")
SECTION_ORDER = (
    "details", "findings", "key_findings", "key_points", "trend_summary",
    "methodology", "limitations", "warnings", "recommendations",
)


def _strip_code_fence(text: str) -> str:
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", candidate,
            flags=re.IGNORECASE,
        ).strip()
    return candidate


def parse_json_value(text: str) -> Any | None:
    candidate = _strip_code_fence(text)
    if not candidate or candidate[0] not in "[{":
        return None
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        return None


def _valid_suggestion(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if set(item) - {"text", "kind", "requires_new_tools", "evidence_ref"}:
        return False
    if not isinstance(item.get("text"), str) or not item["text"].strip():
        return False
    if item.get("kind") not in VALID_FOLLOWUP_KINDS:
        return False
    if not isinstance(item.get("requires_new_tools"), bool):
        return False
    return item.get("evidence_ref") is None or isinstance(item["evidence_ref"], str)


def parse_canonical_final_answer(text: str) -> dict | None:
    """Accept only the public FinalAnswerV1 contract without aliases."""
    data = parse_json_value(text)
    if not isinstance(data, dict) or set(data) != CANONICAL_KEYS:
        return None
    answer = data.get("answer_markdown")
    refs = data.get("evidence_refs")
    suggestions = data.get("followup_suggestions")
    if not isinstance(answer, str) or not answer.strip():
        return None
    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
        return None
    if (
        not isinstance(suggestions, list) or len(suggestions) > 3 or
        any(not _valid_suggestion(item) for item in suggestions)
    ):
        return None
    return {
        "answer_markdown": answer.strip(),
        "evidence_refs": refs,
        "followup_suggestions": suggestions,
    }


def _label(key: str) -> str:
    return FIELD_LABELS.get(key, key.replace("_", " ").strip().title())


def _scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).strip()


def _render_mapping(mapping: dict[str, Any], heading_level: int = 3) -> str:
    values = dict(mapping)
    heading = ""
    for identity in ("year", "stage", "title", "name", "label"):
        value = values.pop(identity, None)
        if value not in (None, ""):
            heading_text = f"{value} 年" if identity == "year" else _scalar(value)
            heading = f"{'#' * heading_level} {heading_text}"
            break

    lines = [heading] if heading else []
    for key, value in values.items():
        if value in (None, "", [], {}):
            continue
        label = _label(key)
        if isinstance(value, list):
            lines.append(f"**{label}：**")
            for item in value:
                if isinstance(item, dict):
                    rendered = _render_mapping(item, min(heading_level + 1, 6))
                    lines.append(rendered or "- —")
                else:
                    lines.append(f"- {_scalar(item)}")
        elif isinstance(value, dict):
            lines.append(f"**{label}：**")
            lines.append(_render_mapping(value, min(heading_level + 1, 6)))
        else:
            lines.append(f"**{label}：** {_scalar(value)}")
    return "\n\n".join(line for line in lines if line)


def _render_section(key: str, value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    heading = f"## {_label(key)}"
    if isinstance(value, str):
        return f"{heading}\n\n{value.strip()}"
    if isinstance(value, list):
        body: list[str] = []
        for item in value:
            if isinstance(item, dict):
                body.append(_render_mapping(item))
            else:
                body.append(f"- {_scalar(item)}")
        return f"{heading}\n\n" + "\n\n".join(filter(None, body))
    if isinstance(value, dict):
        return f"{heading}\n\n{_render_mapping(value)}"
    return f"{heading}\n\n{_scalar(value)}"


def _followup_kind(text: str) -> tuple[str, bool]:
    if any(word in text for word in ("限制", "可信", "影响", "为什么", "原因")):
        return "explain", False
    if any(word in text for word in ("方法", "算法", "口径", "如何计算")):
        return "method", False
    return "new_analysis", True


def _normalize_suggestions(data: dict[str, Any]) -> list[dict]:
    raw: Any = []
    for key in FOLLOWUP_ALIASES:
        if key in data:
            raw = data[key]
            break
    if not isinstance(raw, list):
        return []
    normalized: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            kind, needs_tools = _followup_kind(text)
            normalized.append({
                "text": text, "kind": kind,
                "requires_new_tools": needs_tools, "evidence_ref": None,
            })
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("question") or "").strip()
            if not text:
                continue
            default_kind, default_needs_tools = _followup_kind(text)
            kind = item.get("kind")
            if kind not in VALID_FOLLOWUP_KINDS:
                kind = default_kind
            needs_tools = item.get("requires_new_tools")
            if not isinstance(needs_tools, bool):
                needs_tools = default_needs_tools
            evidence_ref = item.get("evidence_ref")
            if not isinstance(evidence_ref, str):
                evidence_ref = None
            normalized.append({
                "text": text, "kind": kind,
                "requires_new_tools": needs_tools,
                "evidence_ref": evidence_ref,
            })
        if len(normalized) == 3:
            break
    return normalized


def _normalize_refs(data: dict[str, Any], evidence_tools: Iterable[str]) -> list[str]:
    for key in EVIDENCE_ALIASES:
        raw = data.get(key)
        if isinstance(raw, list):
            refs = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
            if refs:
                return refs
    return [f"[{name}]" for name in dict.fromkeys(evidence_tools) if name]


def _render_legacy_object(data: dict[str, Any]) -> str:
    answer_key = next(
        (key for key in ANSWER_ALIASES if isinstance(data.get(key), str) and data[key].strip()),
        None,
    )
    sections: list[str] = []
    if answer_key == "answer_markdown":
        sections.append(data[answer_key].strip())
    elif answer_key:
        sections.append(f"## 核心结论\n\n{data[answer_key].strip()}")

    consumed = set(ANSWER_ALIASES) | set(FOLLOWUP_ALIASES) | set(EVIDENCE_ALIASES)
    for key in SECTION_ORDER:
        if key in data:
            rendered = _render_section(key, data[key])
            if rendered:
                sections.append(rendered)
            consumed.add(key)

    # Preserve decision-relevant fields from unforeseen provider schemas without
    # leaking JSON syntax into the UI.
    for key, value in data.items():
        if key in consumed or value in (None, "", [], {}):
            continue
        rendered = _render_section(key, value)
        if rendered:
            sections.append(rendered)

    return "\n\n".join(sections).strip()


def normalize_final_answer(
    text: str, evidence_tools: Iterable[str] = (),
) -> tuple[dict | None, str]:
    """Return FinalAnswerV1 plus native/local_repair normalization mode."""
    native = parse_canonical_final_answer(text)
    if native is not None:
        return native, "native"
    value = parse_json_value(text)
    if isinstance(value, list):
        value = {"details": value}
    if not isinstance(value, dict):
        return None, ""
    markdown = _render_legacy_object(value)
    if not markdown:
        return None, ""
    return {
        "answer_markdown": markdown,
        "evidence_refs": _normalize_refs(value, evidence_tools),
        "followup_suggestions": _normalize_suggestions(value),
    }, "local_repair"


def user_facing_content(text: str) -> tuple[str, dict | None, str]:
    """Never return a JSON object as visible assistant prose."""
    normalized, mode = normalize_final_answer(text)
    if normalized is not None:
        return normalized["answer_markdown"], normalized, mode
    value = parse_json_value(text)
    if value is not None:
        return (
            "## 分析结果\n\n"
            "该轮模型返回了无法识别的结构化结果，请使用“仅重试总结”重新生成。",
            None,
            "fallback",
        )
    return (text or "").strip(), None, "native"
