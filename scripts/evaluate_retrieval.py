"""Evaluate saved rankings against an explicitly documented proxy label set.

Usage:
  python -m scripts.evaluate_retrieval rankings.json proxy_qrels.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from patent_agent.application.retrieval_validation import evaluate_rankings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rankings", type=Path)
    parser.add_argument("relevance", type=Path)
    args = parser.parse_args()
    rankings = json.loads(args.rankings.read_text(encoding="utf-8"))
    relevance_payload = json.loads(args.relevance.read_text(encoding="utf-8"))
    if not relevance_payload.get("proxy_label_source"):
        raise SystemExit("relevance file must document proxy_label_source")
    metrics = evaluate_rankings(rankings, relevance_payload.get("queries", {}))
    print(json.dumps({
        "metrics": asdict(metrics),
        "proxy_label_source": relevance_payload["proxy_label_source"],
        "limitations": relevance_payload.get("limitations", []),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
