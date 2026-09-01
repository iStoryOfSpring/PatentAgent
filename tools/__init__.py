"""tools/ — Tool 层，封装 Engine + LLM 增强 + Viz 渲染"""

from tools.base import Tool, ToolRegistry, tool_registry

# 所有 Tool 模块在此导入以触发注册
import tools.trend_tool       # noqa: E402, F401
import tools.lifecycle_tool   # noqa: E402, F401
import tools.ipc_tool         # noqa: E402, F401
import tools.nlp_tool         # noqa: E402, F401
import tools.network_tool     # noqa: E402, F401
import tools.country_tool     # noqa: E402, F401
import tools.roadmap_tool     # noqa: E402, F401
import tools.dataset_tool     # noqa: E402, F401
import tools.search_tool      # noqa: E402, F401  # Phase 4
import tools.tech_matrix_tool # noqa: E402, F401  # Phase 6
import tools.clustering_tool  # noqa: E402, F401  # Phase 6
import tools.valuation_tool   # noqa: E402, F401  # Phase 6
import tools.competitor_evolution_tool  # noqa: E402, F401  # Phase 7
import tools.advanced_tools  # noqa: E402, F401  # Auditable advanced capabilities

__all__ = ["Tool", "ToolRegistry", "tool_registry"]
