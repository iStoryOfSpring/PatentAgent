"""多 Agent 协作编排（Phase 7）

架构: Orchestrator → Search Agent ∥ Analysis Agent → Report Agent

每个子 Agent 有独立的:
  - system prompt（专注自身领域）
  - 工具集（仅暴露相关 Tool）
  - 上下文窗口（仅接收相关数据，防止上下文膨胀）
"""

import asyncio
import json
import logging
from typing import Optional

from agent.llm import LLMClient, ChatResponse
from agent.prompts import SYSTEM_PROMPT
from tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# ── 子 Agent 专用 Prompt ──
SEARCH_AGENT_PROMPT = """你是专利检索专家。你的任务是根据用户需求，搜索和筛选最相关的专利文献。

可用工具: TF-IDF 相关专利筛查、相似专利查找、当前数据源记录获取。

工作原则:
1. 优先使用 TF-IDF 词项检索筛出相关专利，不将其解释为语义嵌入或查全检索
2. 对搜索结果中的高相关专利，获取详细信息
3. 识别关键申请人和技术领域
4. 将检索结果结构化返回
"""

ANALYSIS_AGENT_PROMPT = """你是专利分析专家。你的任务是对专利数据进行深度分析。

可用工具: 趋势分析、IPC分类、词云、生命周期、聚类、技术功效矩阵、价值评估。

工作原则:
1. 从多个维度分析专利数据（趋势、构成、热点、价值）
2. 每个分析都要有数据支撑
3. 发现数据中的模式和异常
4. 将分析结果以结构化 JSON 返回
"""

REPORT_AGENT_PROMPT = """你是专利报告撰写专家。你的任务是将检索和分析结果整理为专业的分析报告。

工作原则:
1. 先给出总体结论，再逐维度展开
2. 引用具体数据和发现
3. 指出数据局限性
4. 给出可行的后续分析方向
5. 报告结构: 概述 → 数据总览 → 趋势 → 热点 → 竞对 → 路线图 → 关键专利 → 结论
"""


class SubAgent:
    """子 Agent: 独立的 prompt + 工具子集 + 上下文窗口。

    每个 SubAgent 专注于一个领域，只接收相关工具和数据，
    防止单 Agent 上下文窗口膨胀。
    """

    def __init__(self,
                 name: str,
                 llm_client: LLMClient,
                 tools: list,
                 system_prompt: str):
        self.name = name
        self.llm = llm_client
        self.tools = tools
        self.system_prompt = system_prompt
        self._tool_registry = self._build_tool_map(tools)

    def _build_tool_map(self, tools: list) -> dict:
        """从 Tool 对象列表构建名称→Tool 映射"""
        result = {}
        for t in tools:
            name = getattr(t, 'name', '')
            if name:
                result[name] = t
        return result

    def _get_tool_schemas(self) -> list[dict]:
        """获取工具 Schema 列表（LLM function calling 格式）"""
        return [t.to_schema() for t in self.tools]

    async def run(self, task: dict,
                  storage=None,
                  max_steps: int = 5,
                  previous_results: list = None) -> dict:
        """执行子任务，返回结构化结果。

        Args:
            task: {"goal": "...", "context": "...", "suggested_tools": [...]}
            storage: PatentDataStore 实例
            max_steps: 最大工具调用步数
            previous_results: 前序子 Agent 的结果（Report Agent 使用）

        Returns:
            {"agent": self.name, "result": [...], "summary": "..."}
        """
        goal = task.get("goal", "")
        context = task.get("context", "")

        # 如果有前序结果，附加到上下文
        if previous_results:
            prev_summary = json.dumps(
                [r.get("summary", "") for r in previous_results],
                ensure_ascii=False,
            )
            context = f"{context}\n\n前序分析结果:\n{prev_summary}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"任务目标: {goal}\n\n上下文: {context}"},
        ]

        tool_schemas = self._get_tool_schemas()
        results = []
        step_count = 0

        while step_count < max_steps:
            step_count += 1
            try:
                response = await self.llm.chat(
                    messages=messages,
                    tools=tool_schemas if tool_schemas else None,
                )
            except Exception as e:
                logger.error(f"[{self.name}] LLM 调用失败: {e}")
                break

            # 不再调用工具 → 任务完成
            if not response.tool_calls:
                # 解析 LLM 的最终文本
                text = response.text or ""
                results.append({"type": "llm_response", "content": text})
                break

            # 执行工具调用
            for tc in response.tool_calls[:3]:  # 每轮最多 3 个工具调用
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})
                tool = self._tool_registry.get(tool_name)

                if tool and storage:
                    try:
                        result = await tool.run(storage, **tool_args)
                        results.append({
                            "type": "tool_result",
                            "tool": tool_name,
                            "result_type": getattr(result, 'result_type', 'unknown'),
                            "has_chart": bool(getattr(result, 'chart_html', None)),
                        })
                        # 将结果反馈给 LLM
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": tool_name, "arguments": json.dumps(tool_args)},
                            }],
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps({"status": "completed", "result_type": getattr(result, 'result_type', '')}),
                        })
                    except Exception as e:
                        results.append({
                            "type": "tool_error",
                            "tool": tool_name,
                            "error": str(e),
                        })
                elif not tool:
                    results.append({
                        "type": "tool_not_found",
                        "tool": tool_name,
                    })

        # 生成摘要
        summary = self._summarize_results(results)
        return {
            "agent": self.name,
            "goal": goal,
            "result": results,
            "summary": summary,
        }

    def _summarize_results(self, results: list) -> str:
        """从工具执行结果中提取摘要"""
        tools_used = set()
        total_results = 0
        has_charts = False
        for r in results:
            if r.get("type") == "tool_result":
                tools_used.add(r.get("tool", ""))
                total_results += 1
                if r.get("has_chart"):
                    has_charts = True

        parts = []
        if tools_used:
            parts.append(f"使用工具: {', '.join(tools_used)}")
        parts.append(f"工具调用: {total_results} 次")
        if has_charts:
            parts.append("含图表")
        return "; ".join(parts) if parts else "无结果"


class MultiAgentOrchestrator:
    """多 Agent 编排器: Orchestrator → Search ∥ Analysis → Report。

    用于复杂分析需求，将任务分解后并行分派给专业子 Agent。
    """

    def __init__(self, llm_client: LLMClient,
                 tool_registry: ToolRegistry):
        self.llm = llm_client
        self.tool_registry = tool_registry

        # 工具分组
        search_tool_names = [
            "search_patents", "read_patent_details",
            "get_dataset_summary",
        ]
        analysis_tool_names = [
            "analyze_patent_trend", "analyze_lifecycle",
            "analyze_ipc_distribution", "generate_wordcloud",
            "analyze_burst_terms", "analyze_yearly_keywords",
            "analyze_co_network", "analyze_country_distribution",
            "analyze_tech_roadmap", "analyze_tech_matrix",
            "analyze_clustering", "analyze_patent_valuation",
        ]

        search_tools = [self._get_tool(n) for n in search_tool_names]
        analysis_tools = [self._get_tool(n) for n in analysis_tool_names]
        search_tools = [t for t in search_tools if t]
        analysis_tools = [t for t in analysis_tools if t]

        self.search_agent = SubAgent(
            "search", llm_client, search_tools, SEARCH_AGENT_PROMPT,
        )
        self.analysis_agent = SubAgent(
            "analysis", llm_client, analysis_tools, ANALYSIS_AGENT_PROMPT,
        )
        self.report_agent = SubAgent(
            "report", llm_client, [], REPORT_AGENT_PROMPT,
        )

    def _get_tool(self, name: str):
        try:
            return self.tool_registry.get_tool(name)
        except KeyError:
            return None

    async def execute_complex_analysis(self,
                                       user_query: str,
                                       session=None) -> dict:
        """执行复杂分析: 分解 → 并行 → 汇总。

        Args:
            user_query: 用户原始查询
            session: Session 对象（含 dataset_id 等上下文）

        Returns:
            综合分析报告 dict
        """
        # 从 session 获取 storage
        storage = getattr(session, 'storage', None) if session else None

        # 1. Orchestrator 分解任务
        plan = await self._decompose(user_query)

        # 2. 并行调用子 Agent
        results = await asyncio.gather(
            self.search_agent.run(plan.get("search_subtasks", {}), storage=storage),
            self.analysis_agent.run(plan.get("analysis_subtasks", {}), storage=storage),
        )
        search_result, analysis_result = results[0], results[1]

        # 3. 报告 Agent 汇总
        report = await self.report_agent.run(
            plan.get("report_config", {}),
            storage=storage,
            previous_results=[search_result, analysis_result],
        )

        return report

    async def _decompose(self, user_query: str) -> dict:
        """用 LLM 将用户查询分解为检索和分析子任务。

        Returns:
            {"search_subtasks": {...}, "analysis_subtasks": {...}, "report_config": {...}}
        """
        prompt = (
            f"你是任务分解专家。将以下用户请求分解为搜索和分析两个子任务。\n\n"
            f"用户请求: {user_query}\n\n"
            f"返回 JSON:\n"
            f'{{"search_subtasks": {{"goal": "检索目标", "context": "检索上下文"}}, '
            f'"analysis_subtasks": {{"goal": "分析目标", "context": "分析上下文"}}, '
            f'"report_config": {{"goal": "生成综合分析报告", "context": "综合检索和分析结果"}}}}\n'
            f"只返回 JSON。"
        )

        try:
            response = await self.llm.chat([
                {"role": "user", "content": prompt},
            ])
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception:
            return {
                "search_subtasks": {
                    "goal": f"检索与'{user_query}'相关的专利文献",
                    "context": user_query,
                },
                "analysis_subtasks": {
                    "goal": f"对'{user_query}'相关专利进行多维度分析",
                    "context": user_query,
                },
                "report_config": {
                    "goal": f"生成'{user_query}'的综合分析报告",
                    "context": f"综合检索和分析结果",
                },
            }
