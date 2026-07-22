"""Explicitly regenerate the 16-tool golden fingerprints.

Run only for a reviewed algorithm/contract change:
    uv run python scripts/generate_tool_goldens.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from engine.adapters.wos_adapter import WoSAdapter
from storage.datastore import PatentDataStore
from tools import tool_registry


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "wos_golden"
PARAMETERS = {
    "analyze_patent_trend": {"chart_type": "yearly"},
    "analyze_lifecycle": {},
    "analyze_ipc_distribution": {},
    "generate_wordcloud": {"text_source": "title"},
    "analyze_burst_terms": {},
    "analyze_yearly_keywords": {"text_source": "title"},
    "analyze_co_network": {},
    "analyze_country_distribution": {},
    "analyze_tech_roadmap": {"top_n_per_year": 2},
    "get_dataset_summary": {},
    "search_patents": {"query": "solid electrolyte battery", "top_k": 5},
    "read_patent_details": {"patent_numbers": ["EP2019000000-A1"]},
    "analyze_tech_matrix": {"top_n": 10},
    "analyze_clustering": {"n_clusters": 6},
    "analyze_patent_valuation": {"top_n": 10, "citation_mode": "screening"},
    "analyze_competitor_evolution": {"top_n": 5},
}
# dataset_id is a local installation identity derived from the source directory.
# The portable content identity is dataset_content_hash, which the regression
# test validates separately before comparing the golden projection.
VOLATILE_KEYS = {
    "chart_html", "elapsed_ms", "query_embedding_time_ms", "imported_at", "dataset_id",
}


def canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: canonical(item) for key, item in sorted(value.items())
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, float):
        return round(value, 8)
    return value


def fingerprint(value: Any) -> str:
    payload = json.dumps(
        canonical(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def main() -> None:
    frame = WoSAdapter().batch_parse(str(FIXTURE_DIR))
    store = PatentDataStore(source_dir=str(FIXTURE_DIR))
    store.load_dataframe(frame)
    store._adapter_name = "wos_derwent"
    goldens = {"schema_version": 1, "tools": {}}
    for name in sorted(PARAMETERS):
        result = await tool_registry.get_tool(name).run(store, **PARAMETERS[name])
        payload = result.model_dump(mode="json")
        goldens["tools"][name] = {
            "result_type": result.result_type,
            "sha256": fingerprint(payload),
            "projection": canonical(payload),
        }
    destination = FIXTURE_DIR / "tool_goldens.json"
    destination.write_text(
        json.dumps(goldens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"updated {destination}")


if __name__ == "__main__":
    asyncio.run(main())
