"""Validate algorithm evidence records and every registered implementation."""

from __future__ import annotations

from tools import tool_registry


def main() -> None:
    failures: list[str] = []
    seen_algorithms: set[tuple[str, str]] = set()
    for tool in tool_registry.list_tools():
        record = tool.evidence_record
        for key in ("algorithm_id", "version", "evidence_type", "formula"):
            if not record.get(key):
                failures.append(f"{tool.name}: missing {key}")
        for key in ("sources", "conditions", "prohibited_claims"):
            if not isinstance(record.get(key), list):
                failures.append(f"{tool.name}: {key} must be a list")
        implementations = {
            "default": {
                "algorithm_id": record.get("algorithm_id"),
                "version": record.get("version"),
            },
            **record.get("implementations", {}),
        }
        for mode, item in implementations.items():
            algorithm = (str(item.get("algorithm_id", "")), str(item.get("version", "")))
            if not all(algorithm):
                failures.append(f"{tool.name}.{mode}: incomplete algorithm identity")
            seen_algorithms.add(algorithm)
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"verified {len(tool_registry.get_all_names())} tools and "
        f"{len(seen_algorithms)} algorithm identities"
    )


if __name__ == "__main__":
    main()
