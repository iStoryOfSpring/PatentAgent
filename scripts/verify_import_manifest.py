"""Verify file hashes in a patentagent-import.json without downloading data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    manifest = json.loads((root / "patentagent-import.json").read_text(encoding="utf-8"))
    failures = []
    for item in manifest.get("files", []):
        path = (root / item["path"]).resolve()
        if root not in path.parents or not path.is_file():
            failures.append(f"missing/outside root: {item['path']}")
            continue
        if not item.get("sha256"):
            failures.append(f"missing hash: {item['path']}")
            continue
        actual = digest(path)
        if actual.lower() != item.get("sha256", "").lower():
            failures.append(f"hash mismatch: {item['path']}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"verified {len(manifest.get('files', []))} files")


if __name__ == "__main__":
    main()
