"""Test the autonomous reasoning and strategic recommendation system."""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.analysis_results import (
    StrategyReport, StrategicRecommendation, CrossToolInsight,
    YearlyTrendResult, SCurveResult, TechEffectMatrix,
    WordFreqResult, ValueIndicators, BurstTermResult,
    ClusteringResult, IPCMatrixResult,
)
from agent.strategy_chains import ALL_CHAINS, select_chain
from agent.cross_tool_synthesis import CrossToolAnalyzer
from agent.recommendation_engine import StrategicAdvisor
from agent.adaptive_planner import AdaptivePlanner, ReviewDecision
from agent.proactive_discovery import ProactiveDiscoveryEngine


class TestStrategyChains(unittest.TestCase):

    def test_all_four_chains_defined(self):
        self.assertIn("technology_landscape", ALL_CHAINS)
        self.assertIn("fto_risk", ALL_CHAINS)
        self.assertIn("competitor_intel", ALL_CHAINS)
        self.assertIn("asset_valuation", ALL_CHAINS)

    def test_each_chain_has_steps(self):
        for chain_id, chain in ALL_CHAINS.items():
            self.assertGreater(len(chain.steps), 1,
                              f"{chain_id} should have >1 step")
            # First step should always be dataset summary
            self.assertEqual(
                chain.steps[0].tool_name, "get_dataset_summary",
                f"{chain_id} first step should be get_dataset_summary",
            )

    def test_chain_selection_landscape(self):
        chain = select_chain("", "overview", "给我做一个技术全景分析")
        self.assertEqual(chain.chain_id, "technology_landscape")

    def test_chain_selection_competitor(self):
        chain = select_chain("", "competitor", "帮我分析竞争对手")
        self.assertEqual(chain.chain_id, "competitor_intel")

    def test_chain_selection_fto(self):
        chain = select_chain("", "fto", "帮我做FTO分析 排查侵权风险")
        self.assertEqual(chain.chain_id, "fto_risk")

    def test_chain_selection_valuation(self):
        chain = select_chain("", "valuation", "评估专利价值 优化资产组合")
        self.assertEqual(chain.chain_id, "asset_valuation")

    def test_chain_selection_keyword_match(self):
        chain = select_chain("", "general", "帮我找找技术空白点和蓝海机会")
        self.assertEqual(chain.chain_id, "technology_landscape")


class TestCrossToolAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = CrossToolAnalyzer()

    def test_empty_results(self):
        insights = self.analyzer.analyze({})
        self.assertEqual(len(insights), 0)

    def test_trend_ipc_correlation(self):
        trend = YearlyTrendResult(
            result_type="yearly_trend",
            data=[
                {"year": 2020, "count": 100},
                {"year": 2021, "count": 120},
                {"year": 2022, "count": 150},
            ],
        )
        ipc = IPCMatrixResult(
            result_type="ipc_matrix",
            years=[2020, 2021, 2022],
            sections=["H", "B", "C"],
            matrix=[
                [40, 30, 30],
                [50, 35, 35],
                [65, 40, 45],
            ],
        )
        insights = self.analyzer.analyze({
            "analyze_patent_trend": trend,
            "analyze_ipc_distribution": ipc,
        })
        trend_insights = [i for i in insights if i.insight_type == "trend_vs_ipc"]
        self.assertGreater(len(trend_insights), 0)
        self.assertIn("H", trend_insights[0].description)

    def test_burst_matrix_correlation(self):
        burst = BurstTermResult(
            result_type="burst_terms",
            data=[
                {"term": "solid_electrolyte", "burst": 3.5},
                {"term": "silicon_anode", "burst": 2.8},
            ],
        )
        matrix = TechEffectMatrix(
            result_type="tech_effect_matrix",
            functions=["solid_electrolyte", "lithium_metal", "cathode_coating"],
            effects=["cycle_life", "energy_density", "safety"],
            matrix=[[5, 3, 2], [4, 6, 1], [2, 2, 0]],
        )
        insights = self.analyzer.analyze({
            "analyze_tech_matrix": matrix,
            "analyze_burst_terms": burst,
        })
        matrix_insights = [i for i in insights if i.insight_type == "matrix_vs_burst"]
        self.assertGreater(len(matrix_insights), 0)


class TestStrategicAdvisor(unittest.TestCase):

    def _make_trend(self, counts):
        return YearlyTrendResult(
            result_type="yearly_trend",
            data=[{"year": 2020 + i, "count": c} for i, c in enumerate(counts)],
        )

    def _make_lifecycle(self, counts):
        import numpy as np
        return SCurveResult(
            result_type="s_curve",
            years=list(range(2020, 2020 + len(counts))),
            counts=counts,
            cumulative=np.cumsum(counts).tolist(),
            fitted=np.cumsum(counts).astype(float).tolist(),
        )

    def test_growth_stage_generates_investment_rec(self):
        trend = self._make_trend([100, 130, 170])
        lifecycle = self._make_lifecycle([100, 130, 170])

        advisor = StrategicAdvisor(
            results={
                "analyze_patent_trend": trend,
                "analyze_lifecycle": lifecycle,
            },
            cross_tool_insights=[],
            chain_name="technology_landscape",
        )
        report = advisor.generate()

        investment_recs = [
            r for r in report.recommendations
            if r.category == "R&D_INVESTMENT"
        ]
        self.assertGreater(len(investment_recs), 0)
        # Growing trend → should suggest investment
        self.assertIn("投入", investment_recs[0].recommendation)

    def test_decline_generates_warning(self):
        trend = self._make_trend([170, 130, 100])
        lifecycle = self._make_lifecycle([170, 130, 100])

        advisor = StrategicAdvisor(
            results={
                "analyze_patent_trend": trend,
                "analyze_lifecycle": lifecycle,
            },
            cross_tool_insights=[],
            chain_name="technology_landscape",
        )
        report = advisor.generate()

        investment_recs = [
            r for r in report.recommendations
            if r.category == "R&D_INVESTMENT"
        ]
        self.assertGreater(len(investment_recs), 0)
        # Declining trend → should suggest caution
        self.assertIn("减少", investment_recs[0].recommendation)

    def test_gaps_generate_filing_rec(self):
        matrix = TechEffectMatrix(
            result_type="tech_effect_matrix",
            functions=["cathode", "anode", "electrolyte"],
            effects=["safety", "capacity", "cost"],
            matrix=[[10, 8, 5], [6, 4, 0], [3, 2, 0]],
        )
        # Manually attach gap recommendations (as tool layer does)
        matrix._gap_recommendations = [
            {"function": "anode", "effect": "cost", "patent_count": 0},
            {"function": "electrolyte", "effect": "capacity", "patent_count": 1},
            {"function": "electrolyte", "effect": "cost", "patent_count": 0},
        ]

        advisor = StrategicAdvisor(
            results={"analyze_tech_matrix": matrix},
            cross_tool_insights=[],
            chain_name="technology_landscape",
        )
        report = advisor.generate()

        filing_recs = [
            r for r in report.recommendations
            if r.category == "PATENT_FILING"
        ]
        self.assertGreater(len(filing_recs), 0)
        self.assertIn("anode", filing_recs[0].recommendation)
        self.assertIn("cost", filing_recs[0].recommendation)

    def test_report_has_all_required_fields(self):
        advisor = StrategicAdvisor({}, [], "test")
        report = advisor.generate()
        self.assertEqual(report.result_type, "strategy_report")
        self.assertIsInstance(report.executive_summary, str)
        self.assertIsInstance(report.recommendations, list)
        self.assertIsInstance(report.risk_factors, list)
        self.assertIsInstance(report.data_limitations, list)
        self.assertIsInstance(report.followup_analyses, list)


class TestAdaptivePlanner(unittest.TestCase):

    async def _run_review(self, step, execution, remaining, all_execs):
        planner = AdaptivePlanner()
        return await planner.review_intermediate(
            step, execution, remaining, all_execs,
        )

    def test_continue_on_success(self):
        import asyncio
        from models.session import ToolExecution
        from models.analysis_results import YearlyTrendResult

        exec_result = YearlyTrendResult(
            result_type="yearly_trend",
            data=[{"year": 2020, "count": 100}],
        )
        exec = ToolExecution(
            id="test", tool_name="analyze_patent_trend",
            parameters={}, status="completed", result=exec_result,
        )
        result = asyncio.run(self._run_review(
            {"tool": "analyze_patent_trend"}, exec, [], [exec],
        ))
        self.assertEqual(result.decision, ReviewDecision.CONTINUE)

    def test_data_gap_on_failure(self):
        import asyncio
        from models.session import ToolExecution

        exec = ToolExecution(
            id="test", tool_name="analyze_patent_trend",
            parameters={}, status="failed", error="KeyError: 'year'",
        )
        result = asyncio.run(self._run_review(
            {"tool": "analyze_patent_trend"}, exec, [], [exec],
        ))
        self.assertEqual(result.decision, ReviewDecision.DATA_GAP)


class TestProactiveDiscovery(unittest.TestCase):

    def test_empty_results(self):
        engine = ProactiveDiscoveryEngine()
        signals = engine.discover({})
        # Should still suggest some methodology-based gaps
        self.assertIsInstance(signals, list)

    def test_growth_trend_triggers_lifecycle_suggestion(self):
        trend = YearlyTrendResult(
            result_type="yearly_trend",
            data=[
                {"year": 2020, "count": 100},
                {"year": 2021, "count": 130},
                {"year": 2022, "count": 170},
            ],
        )
        engine = ProactiveDiscoveryEngine()
        signals = engine.discover({"analyze_patent_trend": trend})
        lifecycle_signals = [
            s for s in signals if "生命周期" in s.title
        ]
        self.assertGreater(len(lifecycle_signals), 0)

    def test_burst_triggers_deep_dive(self):
        burst = BurstTermResult(
            result_type="burst_terms",
            data=[
                {"term": "solid_electrolyte", "burst": 3.5},
                {"term": "quantum_dot", "burst": 2.8},
            ],
        )
        engine = ProactiveDiscoveryEngine()
        signals = engine.discover({"analyze_burst_terms": burst})
        self.assertGreater(len(signals), 0)
        # Should suggest deep dive into burst terms
        deep_dives = [s for s in signals if s.category == "deep_dive"]
        self.assertGreater(len(deep_dives), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
