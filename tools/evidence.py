"""Single source of truth for tool algorithm claims and evidence boundaries."""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def load_evidence_registry() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "knowledge" / "tool_evidence.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evidence_for(tool_name: str) -> dict[str, Any]:
    registry = load_evidence_registry()
    record = registry.get("tools", {}).get(tool_name)
    if not record:
        raise KeyError(f"工具 {tool_name} 未登记算法证据")
    return record

