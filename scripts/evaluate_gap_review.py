"""Offline synthetic holdout. Labels are loaded only after search returns."""
import asyncio
import json
from pathlib import Path
from patent_agent.application.services import DatasetImportService
from tools import tool_registry

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "review_holdout"


async def evaluate():
    store = DatasetImportService().load(str(ROOT / "source"), "google_patents_jsonl")
    result = await tool_registry.get_tool("search_gap_counterevidence").run(store,
        technology="near infrared", effect="sorting", ipc_prefixes=["B07C"], example_limit=25)
    labels = json.loads((ROOT / "labels.json").read_text())["relevance"]
    known = {k for k,v in labels.items() if v}
    seen=set()
    report=[]
    for stage in result.data:
        assert not stage["truncated"]
        found={r["publication"] for r in stage["candidates"]}
        added=found-seen
        seen.update(found)
        tp=len(seen & known)
        report.append(dict(stage=stage["stage"], recovered=tp, known_relevant=len(known),
                           candidates=len(seen), false_positives=len(seen)-tp, precision=tp/len(seen) if seen else None,
                           recall=tp/len(known), additional_reviews=len(added)))
    return report


if __name__=="__main__":
    print(json.dumps(asyncio.run(evaluate()), indent=2))
