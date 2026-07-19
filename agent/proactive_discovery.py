"""Proactive discovery engine.

Unlike the existing _suggest_followups() which only checks "which tool names
were executed", this engine examines the actual data content of tool results
to surface meaningful follow-up questions.

Discovery logic:
  1. Content-based: what signals are present in the actual analysis data?
  2. Anomaly-based: what surprising patterns were detected?
  3. Gap-based: what important dimensions are still uncovered?
  4. Registered coverage: which evidence-bounded tool should come next?
"""

from dataclasses import dataclass, field
from typing import Any

from models.analysis_results import AnalysisResult


@dataclass
class DiscoverySignal:
    """A single proactive discovery suggestion."""
    category: str  # "anomaly", "gap", "deep_dive", "comparison", "methodology"
    title: str     # Short label for the suggestion button
    description: str  # What the user would learn
    suggested_tools: list[str] = field(default_factory=list)
    priority: int = 3  # 1 (low) – 5 (high)


class ProactiveDiscoveryEngine:
    """Generates discovery suggestions based on actual analysis content."""

    def discover(self, results: dict[str, AnalysisResult],
                 user_message: str = "") -> list[DiscoverySignal]:
        """Analyze results and produce ranked discovery suggestions."""
        signals: list[DiscoverySignal] = []

        # Collect signals from each analysis dimension
        signals.extend(self._from_trend(results))
        signals.extend(self._from_burst(results))
        signals.extend(self._from_matrix(results))
        signals.extend(self._from_clustering(results))
        signals.extend(self._from_valuation(results))
        signals.extend(self._from_coverage_gaps(results))
        signals.extend(self._from_methodology(results))

        # De-duplicate by title
        seen = set()
        unique = []
        for s in signals:
            if s.title not in seen:
                seen.add(s.title)
                unique.append(s)
        signals = unique

        # Sort by priority descending
        signals.sort(key=lambda s: s.priority, reverse=True)
        return signals[:4]  # Top 4 most important

    # ── Content-based discovery ──

    def _from_trend(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        trend = results.get("analyze_patent_trend")
        if not trend:
            return []

        data = getattr(trend, 'data', [])
        if not isinstance(data, list) or len(data) < 3:
            return []

        counts = [d.get('count', 0) for d in data[-3:]]
        if len(counts) < 3:
            return []

        signals = []
        # Sharp growth → suggest cumulative/growth consistency check
        if counts[-1] > counts[-3] * 1.2 and "analyze_lifecycle" not in results:
            signals.append(DiscoverySignal(
                category="deep_dive",
                title="生命周期判断前的数据核验",
                description=f"公开量增长{(counts[-1]/counts[-3] - 1)*100:.0f}%，需检查尾年完整性并核验趋势一致性",
                suggested_tools=["analyze_lifecycle"],
                priority=5,
            ))

        # Sharp decline → suggest competitive analysis
        if counts[-1] < counts[-3] * 0.8 and "analyze_co_network" not in results:
            signals.append(DiscoverySignal(
                category="anomaly",
                title="分析专利量下降原因",
                description="申请量明显下滑，需要分析是市场因素还是技术路线转移",
                suggested_tools=["analyze_co_network", "analyze_ipc_distribution"],
                priority=4,
            ))

        return signals

    def _from_burst(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        burst = results.get("analyze_burst_terms")
        if not burst:
            return []

        data = getattr(burst, 'data', [])
        if not isinstance(data, list) or not data:
            return []

        # Strong burst signals → deep dive
        high_burst = [t for t in data[:5] if t.get('burst', 0) > 2.0]
        if high_burst:
            terms = ', '.join(t.get('term', '') for t in high_burst[:3])
            return [DiscoverySignal(
                category="deep_dive",
                title=f"深挖突发增长方向: {terms}",
                description="这些关键词近期爆发式增长，可能代表新兴技术机会",
                suggested_tools=["search_patents", "analyze_yearly_keywords"],
                priority=5,
            )]
        return []

    def _from_matrix(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        matrix = results.get("analyze_tech_matrix")
        if not matrix:
            return []

        gaps = (getattr(matrix, 'gap_recommendations', []) or
                getattr(matrix, '_gap_recommendations', []))
        if not gaps:
            return []

        # Top gaps → innovation recommendations
        true_gaps = [g for g in gaps if g.get('patent_count', 999) <= 2]
        if true_gaps:
            top = true_gaps[0]
            return [DiscoverySignal(
                category="deep_dive",
                title=f"探索绝对空白点: {top.get('function','?')} + {top.get('effect','?')}",
                description=(
                    f"该组合在当前代理功效矩阵中仅共现 {top.get('patent_count', 0)} 次；"
                    "需核对术语质量和相关专利，不能直接判定为蓝海"
                ),
                suggested_tools=["search_patents", "analyze_clustering"],
                priority=5,
            )]
        return []

    def _from_clustering(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        clustering = results.get("analyze_clustering")
        if not clustering:
            return []

        cluster_kw = getattr(clustering, 'cluster_keywords', {})
        patents_per = getattr(clustering, 'patents_per_cluster', {})

        if not cluster_kw:
            return []

        # Small clusters → niche opportunities
        signals = []
        for cid, kws in cluster_kw.items():
            count = patents_per.get(int(cid), 0)
            if count < 5 and kws:
                signals.append(DiscoverySignal(
                    category="deep_dive",
                    title=f"探索小众技术方向: {', '.join(kws[:3])}",
                    description=f"该技术方向仅有 {count} 件专利，可能是差异化机会",
                    suggested_tools=["search_patents", "analyze_burst_terms"],
                    priority=3,
                ))

        return signals[:2]

    def _from_valuation(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        valuation = results.get("analyze_patent_valuation")
        if not valuation:
            return []

        val_data = getattr(valuation, 'data', [])
        if not isinstance(val_data, list) or not val_data:
            return []

        # High-value top patent → suggest deep read
        top_patents = val_data[:3]
        if top_patents:
            pns = [p.get('patent_number', '') for p in top_patents if p.get('patent_number')]
            if pns:
                return [DiscoverySignal(
                    category="deep_dive",
                    title="深入阅读最高价值专利",
                    description=f"Top {len(pns)} 件高价值专利值得全文精读，了解技术细节和权利要求范围",
                    suggested_tools=["read_patent_details"],
                    priority=4,
                )]
        return []

    def _from_coverage_gaps(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        """Detect analysis dimensions that haven't been covered yet."""
        all_tools = {
            "analyze_burst_terms",
            "analyze_yearly_keywords",
            "analyze_country_distribution",
            "analyze_tech_roadmap",
            "analyze_co_network",
            "analyze_clustering",
            "analyze_tech_matrix",
            "analyze_patent_valuation",
            "analyze_lifecycle",
        }
        executed = set(results.keys())
        missing = all_tools - executed

        tool_descriptions = {
            "analyze_tech_matrix": ("功效矩阵分析", "发现技术空白点和创新机会", 4),
            "analyze_burst_terms": ("突发词检测", "识别快速兴起的新技术方向", 4),
            "analyze_country_distribution": ("国家分布分析", "了解全球市场布局策略", 3),
            "analyze_tech_roadmap": ("技术路线图", "可视化技术演进脉络", 3),
            "analyze_co_network": ("合作网络分析", "发现产学研合作格局", 3),
            "analyze_clustering": ("专利聚类", "自动发现技术主题群组", 3),
            "analyze_patent_valuation": ("价值筛查", "按可用工程指标生成待复核排序", 4),
            "analyze_lifecycle": ("公开增长概况", "查看累计公开量与年度增长，不判定生命周期", 4),
            "analyze_yearly_keywords": ("逐年关键词", "追踪技术热点的时间迁移", 2),
        }

        signals = []
        for tool in sorted(missing):
            if tool in tool_descriptions:
                title, desc, priority = tool_descriptions[tool]
                signals.append(DiscoverySignal(
                    category="gap",
                    title=title,
                    description=desc,
                    suggested_tools=[tool],
                    priority=priority,
                ))

        return signals[:3]

    def _from_methodology(self, results: dict[str, Any]) -> list[DiscoverySignal]:
        """Legacy chapter hints are intentionally disabled.

        Tool evidence and limitations now come only from tool_evidence.json via
        the Tool registry. The old chapter index is retained as archival content,
        but must not create unregistered method claims.
        """
        return []
