"""MCP Server: registers all PatentAgent tools as MCP tools.

Uses the low-level mcp.server.Server class for full control over tool
listing and execution. Supports stdio transport (Claude Code, VS Code)
and HTTP transport (remote clients).
"""

import json
import logging
import sys

from mcp.server import Server  # noqa: E402 — this is the MCP SDK, not our package
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Prompt,
    PromptArgument,
    PromptMessage,
)

from tools.base import tool_registry
from patent_mcp.adapters import tool_to_mcp_tool, result_to_mcp_content, coerce_args
from patent_mcp.data_loader import MCPDataStoreManager

# ── Logging: MCP uses stdout for transport, so ALL logs go to stderr ──
logger = logging.getLogger("patentagent.mcp")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
))
logger.addHandler(handler)
logger.propagate = False


# ═══════════════════════════════════════════════════════════════════
#  Server factory
# ═══════════════════════════════════════════════════════════════════

def create_server(config):
    """Build and wire up the MCP Server with all PatentAgent tool handlers."""
    store_manager = MCPDataStoreManager(config)
    server = Server(
        name="patent-agent",
        version="3.0.0",
        instructions=(
            "PatentAgent exposes its runtime patent-analysis tool registry over MCP. "
            "data (Web of Science / Derwent format). Load patent data by setting "
            "MCP_INPUT_DIR to the directory containing .txt patent export files. "
            "Each analysis tool performs statistical computation and returns "
            "structured results. Charts are returned as embedded HTML resources "
            "where applicable."
        ),
    )

    # ── Trigger tool registration via side-effect imports ──
    _ensure_tools_imported()

    # ═════════════════════════════════════════════════════════════
    #  tools/list
    # ═════════════════════════════════════════════════════════════
    @server.list_tools()
    async def handle_list_tools():
        tools = [tool_to_mcp_tool(t) for t in tool_registry.list_tools()]
        logger.info("tools/list: returning %d tools", len(tools))
        return tools

    # ═════════════════════════════════════════════════════════════
    #  tools/call
    # ═════════════════════════════════════════════════════════════
    @server.call_tool(validate_input=False)
    async def handle_call_tool(name: str, arguments: dict):
        logger.info("tools/call: name=%s args=%s", name, json.dumps(arguments, ensure_ascii=False))

        # Resolve tool
        try:
            tool = tool_registry.get_tool(name)
        except KeyError:
            available = tool_registry.get_all_names()
            return [TextContent(
                type="text",
                text=(
                    f"Unknown tool: '{name}'.\n\n"
                    f"Available tools:\n  " + "\n  ".join(available)
                ),
            )]

        # Load data
        try:
            store = await store_manager.get_store()
        except Exception as exc:
            logger.error("Failed to load data store: %s", exc)
            return [TextContent(
                type="text",
                text=f"Error: Cannot load patent data. {exc}\n"
                     f"Check that MCP_INPUT_DIR points to a directory with .txt patent files.",
            )]

        # Coerce argument types
        params = coerce_args(tool, arguments)

        # Execute tool
        try:
            result = await tool.run(store, **params)
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc, exc_info=True)
            return [TextContent(
                type="text",
                text=f"Error executing '{name}': {exc}",
            )]

        # Convert result to MCP content
        return result_to_mcp_content(result, config.max_items_in_result)

    # ═════════════════════════════════════════════════════════════
    #  prompts/list (common analysis templates)
    # ═════════════════════════════════════════════════════════════
    @server.list_prompts()
    async def handle_list_prompts():
        return [
            Prompt(
                name="patent_overview",
                description="Get a comprehensive overview of the patent dataset",
                arguments=[
                    PromptArgument(
                        name="aspect",
                        description="Which aspect to focus on",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="technology_trend",
                description="Analyze technology trends over a time period",
                arguments=[
                    PromptArgument(
                        name="years",
                        description="Year range, e.g. '2018-2025'",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="competitor_analysis",
                description="Analyze competitive landscape by applicant",
                arguments=[
                    PromptArgument(
                        name="applicants",
                        description="Applicant names separated by comma",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="innovation_gaps",
                description="Review low-co-occurrence candidates in the Derwent abstract proxy matrix",
                arguments=[],
            ),
            Prompt(
                name="technology_hotspots",
                description="Identify technology hotspots using word clouds and burst terms",
                arguments=[],
            ),
        ]

    # ═════════════════════════════════════════════════════════════
    #  prompts/get
    # ═════════════════════════════════════════════════════════════
    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict | None):
        prompts_map = {
            "patent_overview": _build_overview_prompt,
            "technology_trend": _build_trend_prompt,
            "competitor_analysis": _build_competitor_prompt,
            "innovation_gaps": _build_gaps_prompt,
            "technology_hotspots": _build_hotspots_prompt,
        }
        builder = prompts_map.get(name)
        if not builder:
            raise ValueError(f"Unknown prompt: {name}")
        return builder(arguments or {})

    return server, store_manager


# ═══════════════════════════════════════════════════════════════════
#  Transport runners
# ═══════════════════════════════════════════════════════════════════

async def run_stdio(config):
    """Run the MCP server over stdio transport (for Claude Code, VS Code, etc.)."""
    server, store_manager = create_server(config)
    logger.info("Starting PatentAgent MCP server via stdio")

    async with stdio_server() as (read_stream, write_stream):
        init_opts = server.create_initialization_options()
        await server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=init_opts,
            raise_exceptions=False,
        )


async def run_http(config):
    """Run the MCP server over HTTP transport (for remote clients)."""
    from mcp.server.streamable_http import streamable_http_server

    server, store_manager = create_server(config)
    init_opts = server.create_initialization_options()

    logger.info(
        "Starting PatentAgent MCP server via HTTP on %s:%d",
        config.http_host, config.http_port,
    )

    app = streamable_http_server(server, init_opts)
    # Use uvicorn to serve the ASGI app
    import uvicorn
    uvicorn_config = uvicorn.Config(
        app,
        host=config.http_host,
        port=config.http_port,
        log_level=config.log_level.lower(),
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════

_tools_imported = False


def _ensure_tools_imported() -> None:
    """Import all tool modules to trigger tool_registry.register() calls."""
    global _tools_imported
    if _tools_imported:
        return
    # These imports trigger the register() calls at module level
    import tools.trend_tool        # noqa: F401
    import tools.lifecycle_tool    # noqa: F401
    import tools.ipc_tool          # noqa: F401
    import tools.nlp_tool          # noqa: F401
    import tools.network_tool      # noqa: F401
    import tools.country_tool      # noqa: F401
    import tools.roadmap_tool      # noqa: F401
    import tools.dataset_tool      # noqa: F401
    import tools.search_tool       # noqa: F401
    import tools.tech_matrix_tool  # noqa: F401
    import tools.clustering_tool   # noqa: F401
    import tools.valuation_tool    # noqa: F401
    _tools_imported = True


# ═══════════════════════════════════════════════════════════════════
#  Prompt builders
# ═══════════════════════════════════════════════════════════════════

def _build_overview_prompt(args: dict):
    aspect = args.get("aspect", "all")
    return {
        "messages": [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=(
                        f"I want a comprehensive overview of the patent dataset"
                        f"{' focused on ' + aspect if aspect != 'all' else ''}. "
                        f"Please:\n"
                        f"1. First call get_dataset_summary\n"
                        f"2. Then call analyze_patent_trend\n"
                        f"3. Then call analyze_ipc_distribution\n"
                        f"4. Then call generate_wordcloud\n"
                        f"5. Finally synthesize findings into a structured overview"
                    ),
                ),
            ),
        ],
    }


def _build_trend_prompt(args: dict):
    years = args.get("years", "")
    return {
        "messages": [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=(
                        f"I want to analyze technology trends"
                        f"{' for ' + years if years else ''}. "
                        f"Please:\n"
                        f"1. Call analyze_patent_trend with appropriate year filters\n"
                        f"2. Call analyze_lifecycle to understand technology maturity\n"
                        f"3. Call analyze_burst_terms to find emerging technologies\n"
                        f"4. Synthesize findings"
                    ),
                ),
            ),
        ],
    }


def _build_competitor_prompt(args: dict):
    applicants = args.get("applicants", "")
    return {
        "messages": [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=(
                        f"I want to analyze the competitive landscape"
                        f"{' for ' + applicants if applicants else ''}. "
                        f"Please:\n"
                        f"1. Call get_dataset_summary to understand the data\n"
                        f"2. Call analyze_patent_trend with applicant_filters\n"
                        f"3. Call analyze_ipc_distribution to see technology coverage\n"
                        f"4. Call analyze_co_network to map collaborations\n"
                        f"5. Call analyze_patent_valuation for top assignees\n"
                        f"6. Call analyze_tech_matrix to find their technology focus\n"
                        f"7. Synthesize into competitive analysis"
                    ),
                ),
            ),
        ],
    }


def _build_gaps_prompt(args: dict):
    _ = args
    return {
        "messages": [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=(
                        "I want to find innovation opportunities in the patent landscape. "
                        "Please:\n"
                        "1. Call analyze_tech_matrix to build the tech-effect matrix\n"
                        "2. Call analyze_clustering to identify technology themes\n"
                        "3. Cross-reference gaps from the matrix with emerging keywords\n"
                        "4. Recommend specific innovation directions based on the data"
                    ),
                ),
            ),
        ],
    }


def _build_hotspots_prompt(args: dict):
    _ = args
    return {
        "messages": [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=(
                        "I want to identify technology hotspots in the patent dataset. "
                        "Please:\n"
                        "1. Call generate_wordcloud to see high-frequency keywords\n"
                        "2. Call analyze_burst_terms to find rapidly emerging terms\n"
                        "3. Call analyze_yearly_keywords to track keyword evolution\n"
                        "4. Call analyze_ipc_distribution for technology area distribution\n"
                        "5. Synthesize findings into a hotspot report"
                    ),
                ),
            ),
        ],
    }
