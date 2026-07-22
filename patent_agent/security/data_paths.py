"""Local dataset path boundary used by HTTP and startup loading."""

from pathlib import Path


def validate_input_dir(input_dir: str, allowed_root: Path) -> str:
    candidate = Path(input_dir).expanduser().resolve()
    allowed = allowed_root.expanduser().resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"数据目录必须位于允许目录内: {allowed}") from exc
    return str(candidate)


def dataset_inventory(root: Path) -> list[dict]:
    import json

    inventory = []
    if not root.is_dir():
        return inventory
    for name in ("patentagent-import.json", "manifest.json"):
        for path in sorted(root.rglob(name)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = {"status": "invalid_manifest"}
            inventory.append({
                "dataset_id": payload.get("dataset_id", path.parent.name),
                "status": payload.get("status", "ready" if name == "patentagent-import.json" else "unknown"),
                "path": str(path.parent.relative_to(root)),
                "retrieved_records": payload.get("retrieved_records", 0),
                "query": payload.get("query", ""),
                "schema_version": payload.get("schema_version", 0),
            })
    unique = {}
    for item in inventory:
        unique[(item["dataset_id"], item["path"])] = item
    return list(unique.values())
