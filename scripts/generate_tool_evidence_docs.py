#!/usr/bin/env python3
"""Generate the human-readable tool evidence matrix from the JSON registry."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "knowledge" / "tool_evidence.json"
TARGET = ROOT / "docs" / "tool-evidence-matrix.md"


def cell(value) -> str:
    if isinstance(value, dict):
        value = "; ".join(f"{k}>={v:.0%}" for k, v in value.items()) or "—"
    elif isinstance(value, list):
        value = "; ".join(str(item) for item in value) or "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


registry = json.loads(SOURCE.read_text(encoding="utf-8"))
tool_count = len(registry["tools"])
lines = [
    f"# {tool_count} 工具算法证据矩阵",
    "",
    f"> 由 `knowledge/tool_evidence.json` 自动生成；登记版本 `{registry['registry_version']}`。请勿手工维护本表。",
    "",
    "| 工具 | algorithm_id / 版本 | 证据等级 | 公式或实现 | 字段门槛 | 来源 | 禁止结论 |",
    "|---|---|---|---|---|---|---|",
]
for name, record in registry["tools"].items():
    lines.append(
        "| " + " | ".join([
            f"`{name}`",
            f"`{record['algorithm_id']}` / `{record['version']}`",
            f"`{record['evidence_type']}`",
            cell(record["formula"]),
            cell(record.get("fields", {})),
            cell(record.get("sources", [])),
            cell(record.get("prohibited_claims", [])),
        ]) + " |"
    )
lines += [
    "",
    "证据等级说明：`descriptive_statistic` 为直接描述统计；`paper_adapted` 只表示部分公式有论文依据且偏差已声明；`engineering_screening` 为工程代理。只有完成原数据/手算复现和适用条件核验后才能使用 `paper_exact`，当前登记表没有任何工具达到该等级。",
]
TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
