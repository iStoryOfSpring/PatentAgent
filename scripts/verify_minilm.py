"""Download/cache MiniLM and verify the real multilingual retrieval path.

This is intentionally separate from the fast test suite because the first run
downloads model weights. It exits non-zero if the Beta path silently falls back.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from patent_agent.application import DatasetImportService, SearchIndexService
from retrieval.embedding import MULTILINGUAL_BETA_MODEL
from tools.search_tool import SearchTool


async def _verify(dataset: Path, query: str) -> dict:
    store = DatasetImportService().load(str(dataset), "auto")
    result = await SearchTool().execute(
        store,
        query=query,
        top_k=3,
        retrieval_mode="multilingual_hybrid_beta",
    )
    metadata = result.result_metadata
    if metadata.get("retrieval_mode_used") != "multilingual_hybrid_beta":
        raise RuntimeError("MiniLM Beta fell back: " + " | ".join(result.warnings))
    status = SearchIndexService().status(MULTILINGUAL_BETA_MODEL)
    if not status["dependency_installed"] or not status["model_cached"]:
        raise RuntimeError(f"MiniLM runtime/cache status is incomplete: {status}")
    return {
        "query": query,
        "model": metadata.get("embedding_model"),
        "retrieval_mode_used": metadata.get("retrieval_mode_used"),
        "beta_fallback": metadata.get("beta_fallback"),
        "index": metadata.get("index"),
        "top_results": [
            {"patent_number": item["patent_number"], "title": item["title"]}
            for item in result.patents
        ],
        "runtime_status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/fixtures/official_formats"),
    )
    parser.add_argument("--query", default="二氧化碳捕集膜 carbon capture membrane")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_verify(args.dataset, args.query)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
