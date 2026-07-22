"""Opt-in retrieval stress harness (not part of normal CI).

Example: python -m scripts.benchmark_retrieval --records 100000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
import time

import pandas as pd

from storage.datastore import PatentDataStore
from tools.search_tool import SearchTool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=100_000)
    args = parser.parse_args()
    started = time.perf_counter()
    rows = [{
        "patent_number": f"US{i:08d}A1",
        "title": f"industrial robot battery carbon capture system {i % 97}",
        "abstract": f"synthetic performance record group {i % 31}",
        "date": f"{2010 + i % 15}-01-01", "ipc": "H01M;B25J",
        "applicants": f"Applicant {i % 101}",
    } for i in range(args.records)]
    store = PatentDataStore(pd.DataFrame(rows))
    load_seconds = time.perf_counter() - started
    query_started = time.perf_counter()
    result = asyncio.run(SearchTool().execute(
        store, query="solid battery industrial robot", top_k=20,
        retrieval_mode="lexical",
    ))
    query_seconds = time.perf_counter() - query_started
    print(json.dumps({
        "records": args.records,
        "mode": "lexical",
        "dataframe_seconds": round(load_seconds, 3),
        "first_query_seconds": round(query_seconds, 3),
        "reported_query_ms": result.query_embedding_time_ms,
        "peak_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "limitations": [
            "Synthetic stress data measures engineering capacity, not retrieval quality.",
            "Run semantic Beta separately after installing the semantic extra.",
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
