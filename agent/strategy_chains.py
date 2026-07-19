"""Decision-oriented analysis chain templates.

Each Chain is a state machine defining a multi-tool workflow for a specific
patent analysis use case. Chains include:
  - Conditional branching based on intermediate results
  - Data dependency declarations between tools
  - Strategy trigger points for recommendation generation

The four chains map to real-world patent analysis scenarios:
  1. TechnologyLandscapeChain  — 技术全景挖掘
  2. FTORiskChain               — 侵权风险排查
  3. CompetitorIntelChain       — 竞争对手监控
  4. AssetValuationChain        — 资产评估与运营
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable


# ═══════════════════════════════════════════════════════════════════
# Chain step definitions
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ChainStep:
    tool_name: str
    params: dict = field(default_factory=dict)
    reason: str = ""
    # If True, this step's result triggers a strategy insight extraction
    triggers_strategy: bool = False
    # If set, this step only runs when the condition evaluates to True
    condition: Optional[str] = None  # e.g. "trend_direction == 'up'"
    # Declares which prior step's result this step depends on
    depends_on: Optional[str] = None  # prior step's tool_name
    # If True, skip this step without error when data is missing
    optional: bool = False


@dataclass
class ChainDefinition:
    chain_id: str
    name: str
    description: str
    steps: list[ChainStep]
    # Which recommendation categories this chain generates
    recommendation_categories: list[str] = field(default_factory=list)
    # Intent keywords that trigger this chain
    trigger_keywords: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Chain 1: Technology Landscape (技术全景挖掘)
# ═══════════════════════════════════════════════════════════════════

TECHNOLOGY_LANDSCAPE = ChainDefinition(
    chain_id="technology_landscape",
    name="技术全景挖掘",
    description="绘制技术全景图，识别高频区域和低共现复核候选，辅助研发立项前的信息核查。",
    trigger_keywords=[
        "技术全景", "全景", "总览", "概况", "概览", "landscape",
        "技术地图", "技术热点", "热点", "空白点", "蓝海", "红海",
        "技术方向", "技术趋势", "技术路线",
    ],
    recommendation_categories=["R&D_INVESTMENT", "PATENT_FILING"],
    steps=[
        ChainStep(
            tool_name="get_dataset_summary",
            reason="了解数据全貌：专利总量、时间跨度、IPC分类、主要申请人",
        ),
        ChainStep(
            tool_name="analyze_patent_trend",
            params={"chart_type": "yearly"},
            reason="分析公开趋势，并结合尾年完整性判断数据变化",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_lifecycle",
            reason="核对累计公开量与年度增长信号，并检查尾年完整性",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_ipc_distribution",
            reason="了解技术构成分布，识别核心和边缘技术分类",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="generate_wordcloud",
            reason="提取高频技术关键词，快速了解技术主题",
        ),
        ChainStep(
            tool_name="analyze_burst_terms",
            reason="检测近期爆发式增长的新兴技术方向",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_tech_matrix",
            reason="构建 Derwent 摘要代理功效矩阵，筛出低共现复核候选",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_clustering",
            reason="自动发现专利文本中的技术主题群组",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_country_distribution",
            reason="了解全球专利布局地域分布",
            optional=True,
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Chain 2: FTO Risk Assessment (侵权风险排查)
# ═══════════════════════════════════════════════════════════════════

FTO_RISK = ChainDefinition(
    chain_id="fto_risk",
    name="侵权风险排查",
    description="检索目标市场的有效专利，评估侵权风险，生成规避设计建议。",
    trigger_keywords=[
        "侵权", "FTO", "自由实施", "freedom to operate",
        "风险排查", "规避设计", "专利壁垒", "障碍专利",
        "产品上市", "出海", "出口", "目标市场",
    ],
    recommendation_categories=["RISK_MITIGATION", "PATENT_FILING"],
    steps=[
        ChainStep(
            tool_name="get_dataset_summary",
            reason="了解数据范围和规模",
        ),
        ChainStep(
            tool_name="search_patents",
            reason="用 TF-IDF 词项相似度筛查目标技术领域的相关专利",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_ipc_distribution",
            reason="分析风险专利的IPC分类集中度",
        ),
        ChainStep(
            tool_name="analyze_country_distribution",
            reason="确认风险专利的地域覆盖（哪些国家有同族）",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="read_patent_details",
            reason="深入阅读高风险专利的权利要求和引证信息",
            condition="search_returned_high_risk",
            depends_on="search_patents",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_patent_valuation",
            reason="评估障碍专利的引证影响力（高被引专利风险更大）",
            optional=True,
            triggers_strategy=True,
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Chain 3: Competitor Intelligence (竞争对手监控)
# ═══════════════════════════════════════════════════════════════════

COMPETITOR_INTEL = ChainDefinition(
    chain_id="competitor_intel",
    name="竞争对手监控",
    description="追踪竞争对手的研发动向、技术布局和核心人才，制定竞争应对策略。",
    trigger_keywords=[
        "竞争对手", "竞对", "竞争者", "对手", "competitor",
        "对标", "benchmark", "竞争格局", "竞争态势",
        "专利布局", "研发布局", "技术布局", "人才挖掘",
    ],
    recommendation_categories=[
        "PATENT_FILING", "PARTNERSHIP", "TALENT_ACQUISITION", "R&D_INVESTMENT",
    ],
    steps=[
        ChainStep(
            tool_name="get_dataset_summary",
            reason="了解数据全貌，识别主要申请人",
        ),
        ChainStep(
            tool_name="analyze_patent_trend",
            params={"chart_type": "yearly"},
            reason="分析各申请人的公开趋势变化",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_ipc_distribution",
            reason="对比各申请人的技术布局差异",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_competitor_evolution",
            reason="量化主要申请人的 IPC 画像、集中度和年度技术重心变化",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_co_network",
            reason="分析申请人合作网络，识别产学研关键节点",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_tech_matrix",
            reason="对比各申请人的技术功效覆盖方向",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_patent_valuation",
            reason="评估竞争对手核心专利的价值和影响力",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_clustering",
            reason="发现竞争对手的技术主题群组",
            optional=True,
        ),
        ChainStep(
            tool_name="analyze_country_distribution",
            reason="分析竞争对手的全球市场布局策略",
            optional=True,
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Chain 4: Asset Valuation & Portfolio (资产评估与运营)
# ═══════════════════════════════════════════════════════════════════

ASSET_VALUATION = ChainDefinition(
    chain_id="asset_valuation",
    name="资产评估与运营",
    description="基于引证网络和同族规模评估专利价值，筛选核心资产，优化专利组合。",
    trigger_keywords=[
        "专利价值", "价值评估", "资产评估", "valuation",
        "核心专利", "重要专利", "高价值", "排名",
        "专利维护", "放弃", "许可", "转让", "运营",
        "投资组合", "portfolio", "成本优化",
    ],
    recommendation_categories=[
        "PORTFOLIO_PRUNE", "LICENSING", "PATENT_FILING",
    ],
    steps=[
        ChainStep(
            tool_name="get_dataset_summary",
            reason="了解专利组合总体规模和结构",
        ),
        ChainStep(
            tool_name="analyze_patent_valuation",
            reason="基于SS/RO/BC引证指标 + 5个辅助维度评估专利价值排名",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_clustering",
            reason="按技术主题分组，了解价值在不同技术方向上的分布",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_country_distribution",
            reason="分析同族地域覆盖广度（影响专利商业价值）",
            triggers_strategy=True,
        ),
        ChainStep(
            tool_name="analyze_ipc_distribution",
            reason="了解专利组合的技术分类覆盖，发现布局缺口",
        ),
        ChainStep(
            tool_name="analyze_tech_matrix",
            reason="在技术功效矩阵上叠加价值维度，发现高价值空白点",
            optional=True,
            triggers_strategy=True,
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Chain registry
# ═══════════════════════════════════════════════════════════════════

ALL_CHAINS: dict[str, ChainDefinition] = {
    "technology_landscape": TECHNOLOGY_LANDSCAPE,
    "fto_risk": FTO_RISK,
    "competitor_intel": COMPETITOR_INTEL,
    "asset_valuation": ASSET_VALUATION,
}


def select_chain(intent_goal: str, intent_analysis_type: str,
                 user_message: str) -> Optional[ChainDefinition]:
    """Select the most appropriate analysis chain based on user intent.

    Strategy:
      1. First check intent_analysis_type for direct matches
      2. Then scan user message for trigger keywords
      3. Default to technology_landscape for general queries
    """
    msg_lower = user_message.lower()

    # Direct type match
    type_to_chain = {
        "landscape": "technology_landscape",
        "competitor": "competitor_intel",
        "risk": "fto_risk",
        "fto": "fto_risk",
        "valuation": "asset_valuation",
        "portfolio": "asset_valuation",
    }
    if intent_analysis_type in type_to_chain:
        return ALL_CHAINS[type_to_chain[intent_analysis_type]]

    # Keyword scoring
    scores: dict[str, int] = {}
    for chain_id, chain_def in ALL_CHAINS.items():
        score = 0
        for kw in chain_def.trigger_keywords:
            if kw.lower() in msg_lower or kw.lower() in intent_goal.lower():
                score += 1
        if score > 0:
            scores[chain_id] = score

    if scores:
        return ALL_CHAINS[max(scores, key=scores.get)]

    # Default: technology landscape for any general analysis query
    return ALL_CHAINS["technology_landscape"]
