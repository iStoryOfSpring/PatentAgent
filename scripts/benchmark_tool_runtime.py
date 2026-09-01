#!/usr/bin/env python3
"""Repeatable PA-016 runtime baseline for large patent datasets.

The default exercises 100k records. Use --records for a quick smoke run. The
JSON report is intentionally machine-readable so releases can compare it with
an earlier artifact instead of relying on an anecdotal timing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import resource
import subprocess
import time

import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(min(4, os.cpu_count() or 1)))

from storage.datastore import PatentDataStore
from tools import tool_registry


def _node_version() -> str:
    try:
        return subprocess.run(
            ["node", "--version"], check=True, capture_output=True, text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    return round(value / (1024 * 1024) if platform.system() == "Darwin" else value / 1024, 2)


def _dataset(size: int) -> PatentDataStore:
    topics = (
        "solid electrolyte battery thermal safety",
        "robot optical sensor control system",
        "wireless communication antenna coding",
        "solar cell semiconductor efficiency",
    )
    records = []
    for index in range(size):
        topic = topics[index % len(topics)]
        year = 2000 + index % 25
        records.append({
            "patent_number": f"US{index:09d}A1",
            "publication_date": f"{year}-01-{index % 28 + 1:02d}",
            "date": f"{year}-01-{index % 28 + 1:02d}",
            "year": year,
            "title": f"{topic} apparatus {index % 97}",
            "abstract": (
                f"NOVELTY {topic}; USE industrial energy application; "
                f"ADVANTAGE improved reliability group {index % 31}"
            ),
            "ipc": ("H01M" if index % 2 == 0 else "G01D") + ";H02J",
            "applicants": f"Entity {index % 200}",
            "family_id": f"F{index // 3}",
        })
    store = PatentDataStore(pd.DataFrame.from_records(records))
    store._adapter_name = "synthetic_benchmark"
    return store


async def _timed(name: str, awaitable) -> dict:
    started = time.perf_counter()
    before = _peak_rss_mb()
    result = await awaitable
    return {
        "name": name,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "peak_rss_mb": _peak_rss_mb(),
        "peak_rss_delta_mb": round(max(0, _peak_rss_mb() - before), 2),
        "result_type": getattr(result, "result_type", type(result).__name__),
    }


async def _run(size: int) -> list[dict]:
    store = _dataset(size)
    results = []
    results.append(await _timed(
        "lexical_search",
        tool_registry.get_tool("search_patents").run(
            store, query="solid electrolyte", top_k=20,
        ),
    ))
    results.append(await _timed(
        "clustering",
        tool_registry.get_tool("analyze_clustering").run(
            store, n_clusters=4,
        ),
    ))
    results.append(await _timed(
        "technology_effect_matrix",
        tool_registry.get_tool("analyze_tech_matrix").run(store, top_n=20),
    ))
    results.append(await _timed(
        "four_tool_concurrency",
        asyncio.gather(*(
            tool_registry.get_tool("analyze_patent_trend").run(
                store, chart_type="yearly",
            ) for _ in range(4)
        )),
    ))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if args.records < 100:
        parser.error("--records must be at least 100")
    started = time.perf_counter()
    results = asyncio.run(_run(args.records))
    report = {
        "schema_version": 1,
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
            "node_version": _node_version(),
        },
        "record_count": args.records,
        "benchmarks": results,
        "total_elapsed_seconds": round(time.perf_counter() - started, 4),
        "final_peak_rss_mb": _peak_rss_mb(),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
