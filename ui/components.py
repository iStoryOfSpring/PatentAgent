"""Reusable Streamlit UI components (Chinese/English bilingual)."""

import json
import streamlit as st


def T(en: str, zh: str) -> str:
    lang = st.session_state.get("lang", "zh")
    return zh if lang == "zh" else en


def render_tool_card(execution, expanded: bool = False) -> None:
    """Expandable tool execution card."""
    status_icon = {
        "completed": "[OK]",
        "running": "[..]",
        "pending": "[--]",
        "failed": "[XX]",
    }
    icon = status_icon.get(execution.status, "[??]")
    duration_str = f" | {execution.duration_ms:.0f}ms" if execution.duration_ms else ""
    retry_str = f" (retry: {execution.retry_count})" if execution.retry_count > 0 else ""
    title = f"{icon} `{execution.tool_name}` -- {execution.status}{retry_str}{duration_str}"

    with st.expander(title, expanded=expanded):
        if execution.parameters:
            st.caption(T("**Parameters**", "**参数**"))
            st.json(execution.parameters)
        if execution.error:
            st.error(f"{T('Error', '错误')}: {execution.error}")
        if execution.result:
            st.caption(T("**Result**", "**结果**"))
            rt = getattr(execution.result, 'result_type', 'unknown')
            st.text(f"{T('Type', '类型')}: {rt}")
            if hasattr(execution.result, 'data') and isinstance(execution.result.data, list):
                st.caption(f"{T('Items', '条目')}: {len(execution.result.data)}")
            if hasattr(execution.result, 'years'):
                st.caption(f"{T('Range', '范围')}: {min(execution.result.years)}-{max(execution.result.years)}")
            if hasattr(execution.result, 'edge_count'):
                st.caption(f"{T('Edges', '边')}: {execution.result.edge_count}")
            if hasattr(execution.result, 'total_hits'):
                st.caption(f"{T('Hits', '命中')}: {execution.result.total_hits}")


def render_chart_html(chart_html: str, height: int = 500) -> None:
    """Render pyecharts HTML inline."""
    if not chart_html:
        return
    st.components.v1.html(chart_html, height=height, scrolling=True)


def render_approval_buttons(session) -> str | None:
    """Approval buttons. Returns 'APPROVED'|'REJECTED'|'MODIFIED'|None."""
    st.info(T("Analysis plan generated. Please confirm or modify.",
              "分析计划已生成，请确认或修改。"))

    if session.pending_plan:
        plan = session.pending_plan.get("plan", {})
        steps = plan.get("steps", [])
        tokens = plan.get("estimated_tokens", 0)
        for s in steps:
            st.write(
                f"**{s.get('step', '?')}.** `{s.get('tool', '?')}`"
                f" -- {s.get('reason', '')}"
            )
        if tokens:
            st.caption(f"{T('Estimated tokens', '预估 Token')}: {tokens:,}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(T("Approve", "确认执行"), use_container_width=True, type="primary"):
            return "APPROVED"
    with c2:
        if st.button(T("Modify", "修改计划"), use_container_width=True):
            return "MODIFIED"
    with c3:
        if st.button(T("Cancel", "取消"), use_container_width=True):
            return "REJECTED"
    return None


def render_data_panel(store) -> None:
    """Data management panel — clean card style."""
    if store is None or store.is_empty:
        st.warning(T("No patent data loaded", "暂无专利数据"))
        return
    ds = store.get_summary()
    st.metric(T("Total Patents", "专利总量"), f"{ds.total_patents:,}")
    st.caption(
        T(
            f"Period: {ds.year_range[0]} - {ds.year_range[1]}",
            f"时间跨度: {ds.year_range[0]} - {ds.year_range[1]}",
        )
    )
    if ds.ipc_sections:
        st.caption(f"IPC: {', '.join(ds.ipc_sections[:8])}")
    if ds.top_applicants:
        st.caption(f"Top: {ds.top_applicants[0][0]}")

    # 数据指纹：全量 Top 3 关键词 — 优先读 catalog（已算好），否则实时算
    try:
        catalog = st.session_state.get("catalog")
        if catalog is not None and catalog.word_freq_summary:
            top3 = catalog.word_freq_summary["top_words"][:3]
        else:
            from engine.preprocessing import extract_keywords
            df_fp = store.get_all()
            texts = (df_fp['title'].fillna('') + ' ' + df_fp['abstract'].fillna('')).tolist()
            top3 = extract_keywords(texts, pos_filter=True, top_n=3)
        kw_str = ', '.join(f"{w}({c})" for w, c in top3)
        st.caption(f"Top keywords: {kw_str}")
        df_fp = store.get_all()
        src_files = df_fp['source_file'].dropna().unique() if 'source_file' in df_fp.columns else []
        if len(src_files) > 0:
            st.caption(f"Files: {len(src_files)}")
    except Exception:
        pass
    st.caption(f"Dir: {st.session_state.get('input_dir', 'N/A')}")


def _suggest_followups(executed_tools: list, results: dict = None) -> list[dict]:
    """根据已执行的分析工具和实际结果数据，推荐尚未覆盖的分析维度。

    v2.0: 优先使用 ProactiveDiscoveryEngine（基于数据内容），
    降级时使用原有规则（基于工具名称）。

    Returns: [{"label": "...", "action": "...", "prompt": "..."}, ...]
    """
    if not executed_tools:
        return []

    tool_names = {e.tool_name for e in executed_tools if e.status == "completed"}

    # v2.0: Try ProactiveDiscoveryEngine for data-driven suggestions
    if results:
        try:
            from agent.proactive_discovery import ProactiveDiscoveryEngine
            engine = ProactiveDiscoveryEngine()
            signals = engine.discover(results)
            if signals:
                return [
                    {"label": s.title, "prompt": f"帮我{s.description}"}
                    for s in signals[:3]
                ]
        except ImportError:
            pass

    suggestions = []

    # 已覆盖的维度
    has_trend = any("trend" in t for t in tool_names)
    has_words = any("wordcloud" in t or "word_freq" in t for t in tool_names)
    has_ipc = any("ipc" in t for t in tool_names)
    has_country = any("country" in t for t in tool_names)
    has_matrix = any("tech_matrix" in t for t in tool_names)
    has_lifecycle = any("lifecycle" in t for t in tool_names)
    has_clustering = any("clustering" in t for t in tool_names)
    has_valuation = any("valuation" in t for t in tool_names)
    has_burst = any("burst" in t for t in tool_names)

    # 推荐未覆盖的维度
    if not has_matrix:
        suggestions.append({"label": T("Find Innovation Gaps", "找创新空白"),
                            "prompt": "帮我分析技术功效矩阵，找出空白点和创新方向"})
    if not has_clustering and has_words:
        suggestions.append({"label": T("Discover Tech Themes", "发现技术主题"),
                            "prompt": "帮我做专利聚类分析，看看有哪些技术子方向"})
    if not has_valuation:
        suggestions.append({"label": T("Rank Top Patents", "核心专利排名"),
                            "prompt": "帮我评估专利价值，找出最重要的核心专利"})
    if not has_burst and has_trend:
        suggestions.append({"label": T("Find Emerging Tech", "找新兴方向"),
                            "prompt": "帮我检测技术突发词，看看哪些方向最近在爆发"})
    if not has_ipc and has_trend:
        suggestions.append({"label": T("IPC Distribution", "技术分类分布"),
                            "prompt": "帮我分析 IPC 分类分布，看看技术集中在哪些领域"})
    if not has_country:
        suggestions.append({"label": T("Country Distribution", "国家布局"),
                            "prompt": "帮我分析专利申请的国家/地区分布"})

    # 最多 3 个建议
    return suggestions[:3]


def render_followup_buttons(msg_idx: int = 0,
                            tool_executions: list = None) -> str | None:
    """智能追问按钮：根据已执行的分析工具推荐未覆盖的维度。"""
    suggestions = _suggest_followups(tool_executions or [])

    if not suggestions:
        # 兜底：导出按钮
        c1, c2 = st.columns(2)
        with c1:
            if st.button(T("Export Report", "导出报告"), use_container_width=True,
                         key=f"fu_export_{msg_idx}"):
                return "export"
        return None

    # 智能建议按钮
    cols = st.columns(len(suggestions) + 1)  # +1 for export
    for i, sug in enumerate(suggestions):
        with cols[i]:
            if st.button(sug["label"], use_container_width=True,
                         key=f"fu_sug_{msg_idx}_{i}"):
                return f"suggest:{sug['prompt']}"

    # 导出按钮
    with cols[-1]:
        if st.button(T("Export", "导出"), use_container_width=True,
                     key=f"fu_export_{msg_idx}"):
            return "export"
    return None
