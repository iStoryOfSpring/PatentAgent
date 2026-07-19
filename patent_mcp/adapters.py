"""Schema and result conversion between PatentAgent internal types and MCP protocol types.

Three key functions:
  1. tool_to_mcp_tool()     — PatentAgent Tool → mcp.types.Tool
  2. result_to_mcp_content() — AnalysisResult → list[ContentBlock]
  3. mcp_args_to_params()   — MCP arguments dict → type-coerced **params
"""

import json
import logging
import numbers
from typing import Any

from models.analysis_results import AnalysisResult

logger = logging.getLogger("patentagent.mcp.adapters")

# ── try importing mcp types; fail gracefully with clear error ──
try:
    from mcp.types import (
        Tool as MCPTool,
        TextContent,
        EmbeddedResource,
        TextResourceContents,
    )
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    MCPTool = None  # type: ignore
    TextContent = None  # type: ignore
    EmbeddedResource = None  # type: ignore
    TextResourceContents = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════
# 1. Tool → MCP Tool schema
# ═══════════════════════════════════════════════════════════════════

def tool_to_mcp_tool(tool) -> MCPTool:
    """Convert a PatentAgent Tool to an MCP Tool with full JSON Schema inputSchema.

    The existing Tool.parameters dict is a JSON Schema properties object
    (keys=param names, values=property definitions). MCP inputSchema needs
    a complete JSON Schema with type: "object" wrapper.
    """
    if not HAS_MCP:
        raise ImportError("mcp package not installed. Run: pip install mcp")

    evidence = tool.evidence_record
    return MCPTool(
        name=tool.name,
        description=(
            f"{tool.description}\n方法: {tool.methodology}\n"
            f"算法: {evidence.get('algorithm_id')} v{evidence.get('version')}\n"
            f"证据等级: {evidence.get('evidence_type')}\n"
            f"禁止结论: {', '.join(evidence.get('prohibited_claims', [])) or '无'}"
        ),
        inputSchema={
            "type": "object",
            "properties": tool.parameters,
            "required": [
                k for k, v in tool.parameters.items()
                if isinstance(v, dict) and v.get("required", False)
            ],
        },
    )


# ═══════════════════════════════════════════════════════════════════
# 2. AnalysisResult → MCP Content
# ═══════════════════════════════════════════════════════════════════

def result_to_mcp_content(result: Any, max_items: int = 50) -> list:
    """Convert an AnalysisResult (or list[FullPatent]) to MCP content blocks.

    Returns at least one TextContent with structured JSON.
    If chart_html is present, adds an EmbeddedResource with MIME text/html.
    """
    if not HAS_MCP:
        raise ImportError("mcp package not installed. Run: pip install mcp")

    blocks: list = []

    # Special case: ReadPatentDetailsTool returns list[FullPatent] not AnalysisResult
    if isinstance(result, list):
        text = _serialize_list(result, max_items)
        blocks.append(TextContent(type="text", text=text))
        return blocks

    # Normal case: AnalysisResult
    if isinstance(result, AnalysisResult):
        text = _analysis_result_to_text(result, max_items)
        blocks.append(TextContent(type="text", text=text))

        # Attach chart as embedded HTML resource
        chart_html = getattr(result, "chart_html", None)
        if chart_html and isinstance(chart_html, str) and chart_html.strip():
            try:
                blocks.append(EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri="chart://result",
                        mimeType="text/html",
                        text=chart_html,
                    ),
                ))
            except Exception as exc:
                logger.warning("Failed to embed chart HTML: %s", exc)

        return blocks

    # Fallback: unknown type
    return [TextContent(type="text", text=json.dumps(str(result), ensure_ascii=False))]


def _analysis_result_to_text(result: AnalysisResult, max_items: int) -> str:
    """Serialize an AnalysisResult to pretty JSON, truncating large lists/dicts."""
    try:
        # 图表作为独立 HTML resource 返回，避免 HTML 挤占结构化证据预算。
        data = result.model_dump(exclude={"chart_html"})
    except Exception:
        data = {"result_type": getattr(result, "result_type", "unknown")}

    truncated = _truncate_large_values(data, max_items)
    return json.dumps(truncated, ensure_ascii=False, indent=2, default=str)


def _serialize_list(items: list, max_items: int) -> str:
    """Serialize a list (e.g. list[FullPatent]) to JSON."""
    truncated = items[:max_items]
    converted = []
    for item in truncated:
        try:
            converted.append(item.model_dump())
        except AttributeError:
            converted.append(str(item))
    result = truncated
    if len(items) > max_items:
        note = {
            "_truncated": True,
            "_total": len(items),
            "_shown": max_items,
            "items": converted,
        }
        return json.dumps(note, ensure_ascii=False, indent=2, default=str)
    return json.dumps(converted, ensure_ascii=False, indent=2, default=str)


def _truncate_large_values(obj: Any, max_items: int) -> Any:
    """Recursively truncate lists and dicts to max_items entries."""
    if isinstance(obj, dict):
        if len(obj) > max_items:
            keys_to_keep = list(obj.keys())[:max_items]
            result = {k: _truncate_large_values(obj[k], max_items) for k in keys_to_keep}
            result["_truncated"] = True
            result["_total_keys"] = len(obj)
            return result
        return {k: _truncate_large_values(v, max_items) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > max_items:
            truncated = [_truncate_large_values(item, max_items) for item in obj[:max_items]]
            return {
                "_truncated": True,
                "_total_items": len(obj),
                "_shown": max_items,
                "items": truncated,
            }
        return [_truncate_large_values(item, max_items) for item in obj]
    if isinstance(obj, numbers.Number):
        return obj
    return obj


# ═══════════════════════════════════════════════════════════════════
# 3. MCP arguments → tool params (type coercion)
# ═══════════════════════════════════════════════════════════════════

def coerce_args(tool, arguments: dict) -> dict:
    """Coerce MCP client arguments to the types expected by tool.execute().

    MCP clients may send numbers as strings (e.g. year_start: "2020").
    This looks at the tool's parameter JSON Schema and coerces types.
    """
    coerced: dict = {}
    for key, raw_value in arguments.items():
        param_schema = tool.parameters.get(key, {})
        expected_type = param_schema.get("type", "string") if isinstance(param_schema, dict) else "string"

        try:
            coerced[key] = _coerce_value(raw_value, expected_type)
        except (ValueError, TypeError):
            logger.warning(
                "Cannot coerce parameter %s=%r to %s, passing as-is",
                key, raw_value, expected_type,
            )
            coerced[key] = raw_value

    return coerced


def _coerce_value(value: Any, target_type: str) -> Any:
    if target_type == "integer":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            return int(value)
    if target_type == "number":
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
    if target_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            import re
            return [v.strip() for v in re.split(r'[,;]', value) if v.strip()]
        return [value]
    if target_type == "string":
        return str(value)
    return value
