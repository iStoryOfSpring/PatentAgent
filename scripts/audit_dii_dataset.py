#!/usr/bin/env python3
"""Audit a licensed DII Plain Text export directory and update its manifest."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.adapters.wos_adapter import WoSAdapter  # noqa: E402
from storage.datastore import PatentDataStore  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_record_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r"^UT\s+(.+)$", text, flags=re.MULTILINE)


def audit(directory: Path) -> dict:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = sorted(directory.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"no DII .txt batches in {directory}")

    file_rows = []
    all_ids: list[str] = []
    for path in files:
        ids = raw_record_ids(path)
        all_ids.extend(ids)
        file_rows.append({
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "ut_records": len(ids),
        })

    adapter = WoSAdapter()
    frame = adapter.batch_parse(str(directory))
    store = PatentDataStore(frame, source_dir=str(directory))
    store._adapter_name = adapter.name
    duplicate_ids = len(all_ids) - len(set(all_ids))
    parsed = len(frame)
    core = store.audit()["field_coverage"] if parsed else {}
    raw_unique = len(set(all_ids))
    parse_rate = parsed / raw_unique if raw_unique else 0.0

    manifest.update({
        "status": "audited" if parse_rate >= 0.995 else "audit_failed",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "retrieved_records": len(all_ids),
        "unique_ut_records": raw_unique,
        "duplicate_ut_records": duplicate_ids,
        "parsed_unique_records": parsed,
        "parse_rate": round(parse_rate, 6),
        "field_coverage": core,
        "files": file_rows,
    })
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.directory.resolve())
    except (FileNotFoundError, ValueError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "audited" else 1


if __name__ == "__main__":
    raise SystemExit(main())
