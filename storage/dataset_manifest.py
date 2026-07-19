"""DII batch diagnostics shared by API and audit tooling."""

from pathlib import Path
import re
from typing import Any


def inspect_dii_batches(input_dir: str, parsed_records: int) -> dict[str, Any]:
    directory = Path(input_dir)
    files = sorted(directory.glob("*.txt")) if directory.is_dir() else []
    raw_records = 0
    record_ids: list[str] = []
    batches = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        ids = re.findall(r"^UT\s+(.+)$", text, flags=re.MULTILINE)
        # ER is the authoritative record terminator in WoS/DII plain text.
        records = len(re.findall(r"^ER\s*$", text, flags=re.MULTILINE))
        raw_records += records
        record_ids.extend(ids)
        batches.append({"name": path.name, "raw_records": records, "ut_records": len(ids)})
    unique_ids = len(set(record_ids))
    expected_unique = unique_ids or raw_records
    failures = max(expected_unique - parsed_records, 0)
    return {
        "source_files": len(files),
        "batches": batches,
        "raw_records": raw_records,
        "raw_ut_records": len(record_ids),
        "unique_ut_records": unique_ids,
        "duplicate_ut_records": max(len(record_ids) - unique_ids, 0),
        "parsed_unique_records": parsed_records,
        "parse_failure_count": failures,
        "parse_rate": round(parsed_records / expected_unique, 6) if expected_unique else 0.0,
        "batch_overlap_detected": len(record_ids) != unique_ids,
    }
