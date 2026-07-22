"""Produce the transparent proxy validation payload for committed samples."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from patent_agent.application import DatasetImportService
from patent_agent.application.retrieval_validation import evaluate_rankings
from tools.search_tool import SearchTool


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "official_formats"
QUERIES = {
    "solid_state_battery": "solid state battery electrolyte",
    "carbon_capture": "carbon capture membrane",
    "industrial_robotics": "industrial robot calibration",
}


async def main() -> None:
    store = DatasetImportService().load(str(FIXTURE), "auto")
    rankings = {}
    for query_id, text in QUERIES.items():
        result = await SearchTool().execute(store, query=text, top_k=20)
        rankings[query_id] = [
            item["patent_number"].replace("-", "") for item in result.patents
        ]
    labels = json.loads((FIXTURE / "proxy_qrels.json").read_text(encoding="utf-8"))
    metrics = evaluate_rankings(rankings, labels["queries"])
    print(json.dumps({
        "dataset": store.audit(),
        "rankings": rankings,
        "metrics": asdict(metrics),
        "proxy_label_source": labels["proxy_label_source"],
        "limitations": labels["limitations"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
