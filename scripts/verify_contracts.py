"""Fail CI when tool schemas drift from executable Python contracts."""

from __future__ import annotations

import inspect

from tools import tool_registry


def main() -> None:
    failures: list[str] = []
    for tool in tool_registry.list_tools():
        signature = inspect.signature(tool.execute)
        executable = {
            name: parameter for name, parameter in signature.parameters.items()
            if name != "storage" and parameter.kind not in {
                inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL,
            }
        }
        declared = tool.parameters
        missing_in_schema = sorted(set(executable) - set(declared))
        missing_in_code = sorted(set(declared) - set(executable))
        if missing_in_schema:
            failures.append(f"{tool.name}: execute-only params {missing_in_schema}")
        if missing_in_code:
            failures.append(f"{tool.name}: schema-only params {missing_in_code}")
        for name, schema in declared.items():
            if "default" not in schema or name not in executable:
                continue
            actual = executable[name].default
            if actual is inspect.Parameter.empty or actual != schema["default"]:
                failures.append(
                    f"{tool.name}.{name}: schema default={schema['default']!r}, "
                    f"execute default={actual!r}"
                )
        exposed = tool.definition.input_schema.get("properties", {})
        if tool.supports_scope and "scope" not in exposed:
            failures.append(f"{tool.name}: scope missing from ToolDefinition")
        if not tool.supports_scope and "scope" in exposed:
            failures.append(f"{tool.name}: unsupported scope exposed")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"verified {len(tool_registry.get_all_names())} tool contracts")


if __name__ == "__main__":
    main()
