"""PatentAgent Streamlit GUI

Usage: streamlit run ui/app.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime

import streamlit as st

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from engine.parser import PatentMiner
from storage.datastore import PatentDataStore
from models.session import Session
from tools import tool_registry
from agent.llm import LLMClient, LLMProvider
from agent.orchestrator import (
    PatentAgentOrchestrator, build_default_knowledge,
)
from ui.components import (
    render_tool_card, render_chart_html, render_approval_buttons,
    render_data_panel, render_followup_buttons,
)
from ui.report import ReportGenerator

# ── Streamlit caching: avoid rebuilding heavy objects on every rerun ──

@st.cache_resource(ttl=600, show_spinner="Loading patent data...")
def _cached_load_store(input_dir: str) -> PatentDataStore:
    """Cached PatentDataStore — rebuilds only when input_dir changes or TTL expires."""
    miner = PatentMiner(input_dir=input_dir)
    store = PatentDataStore()
    store.load_from_miner(miner)
    return store


@st.cache_resource(ttl=3600, show_spinner=False)
def _cached_llm_client(provider: str, api_key: str, base_url: str) -> LLMClient | None:
    """Cached LLM client — avoids recreating on every rerun."""
    if not api_key:
        return None
    pmap = {"Claude": LLMProvider.CLAUDE, "OpenAI": LLMProvider.OPENAI,
            "DeepSeek": LLMProvider.DEEPSEEK}
    try:
        return LLMClient(provider=pmap[provider], api_key=api_key,
                         base_url=base_url or None)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _cached_knowledge() -> dict:
    """Cached knowledge base — load once per session."""
    return build_default_knowledge()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_tool_result(tool_name: str, _input_dir: str) -> str | None:
    """Cached quick-tool result. Invalidated when cache key changes."""
    return None  # Placeholder — actual caching is per tool_name

print("=" * 60)
print("  PatentAgent starting...")
print("  Do NOT close this window")
print("=" * 60)


def T(en: str, zh: str) -> str:
    lang = st.session_state.get("lang", "zh")
    return zh if lang == "zh" else en


st.set_page_config(
    page_title="PatentAgent",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS: hide Streamlit defaults + unified typography ──
st.markdown("""
<style>
    /* ===== hide Streamlit default chrome ===== */
    #MainMenu        { visibility: hidden; }
    header[data-testid="stHeader"] { visibility: hidden; }
    footer           { visibility: hidden; }
    div[data-testid="stToolbar"] { display: none; }
    div[data-testid="stDecoration"] { display: none; }
    div[data-testid="stStatusWidget"] { display: none; }
    section[data-testid="stSidebar"] div[data-testid="stSidebarNav"] { display: none; }
    button[title="View fullscreen"] { display: none; }

    /* ===== global typography ===== */
    html, body, [class*="css"] {
        font-family: "PingFang SC", "Microsoft YaHei", -apple-system,
                     BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    h1, h2, h3, h4 { font-weight: 600; letter-spacing: -0.02em; }
    p, li, label, .stMarkdown { line-height: 1.7; }

    /* ===== sidebar refinements ===== */
    section[data-testid="stSidebar"] {
        background: #f8f9fb;
        border-right: 1px solid #e8eaed;
    }
    section[data-testid="stSidebar"] .stButton > button {
        font-size: 0.875rem;
        border-radius: 6px;
        border: 1px solid #dde0e4;
        background: #fff;
        transition: background 0.15s, border-color 0.15s;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #f0f2f5;
        border-color: #c4c8ce;
    }

    /* ===== main area cards / containers ===== */
    div[data-testid="stExpander"] {
        border: 1px solid #e8eaed;
        border-radius: 8px;
        box-shadow: none;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stExpander"] summary {
        font-size: 0.875rem;
        padding: 0.5rem 0.75rem;
        color: #444;
    }
    div.stChatMessage {
        background: transparent !important;
        padding: 0.5rem 0;
    }

    /* ===== chat bubbles ===== */
    div[data-testid="stChatMessage"] {
        border-radius: 12px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.75rem;
    }

    /* ===== buttons (main area) ===== */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.15s;
    }
    .stButton > button[kind="primary"] {
        background: #1d4ed8;
        border-color: #1d4ed8;
    }
    .stButton > button[kind="primary"]:hover {
        background: #1e40af;
        border-color: #1e40af;
    }

    /* ===== inputs ===== */
    input[type="text"], input[type="password"], .stTextInput > div > input {
        border-radius: 6px;
        border: 1px solid #dde0e4;
    }
    input[type="text"]:focus, input[type="password"]:focus {
        border-color: #1d4ed8;
        box-shadow: 0 0 0 2px rgba(29,80,216,0.12);
    }

    /* ===== tabs ===== */
    button[data-baseweb="tab"] {
        font-size: 0.875rem;
        font-weight: 500;
        padding: 0.5rem 1rem;
    }

    /* ===== metric cards ===== */
    div[data-testid="stMetric"] {
        background: #f8f9fb;
        border: 1px solid #e8eaed;
        border-radius: 8px;
        padding: 0.75rem 1rem;
    }
    div[data-testid="stMetric"] label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #888;
    }

    /* ===== progress bar ===== */
    div[data-testid="stProgress"] > div {
        background: #e8eaed;
    }
    div[data-testid="stProgress"] > div > div {
        background: #1d4ed8;
    }

    /* ===== info/warning/error boxes ===== */
    div[data-testid="stNotification"] {
        border-radius: 8px;
        border: none;
    }

    /* ===== captions ===== */
    .stCaption, div[data-testid="stCaptionContainer"] p {
        font-size: 0.85rem !important;
        color: #555 !important;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

_DEFAULTS = {
    "messages": [],
    "data_loaded": False,
    "storage": None,
    "agent": None,
    "llm_client": None,
    "llm_configured": False,
    "provider": "Claude",
    "api_key": "",
    "base_url": "",
    "input_dir": "./my_patents",
    "sessions": [],
    "active_session_id": None,
    "open_tabs": {},
    "active_tab": "chat",
    "show_classic": False,
    "lang": "zh",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v



# ── helper functions (defined before use) ──
def _get_active_session() -> Session | None:
    sid = st.session_state.active_session_id
    for s in st.session_state.sessions:
        if s.id == sid:
            return s
    return None


def _new_session() -> Session:
    s = Session(
        id=str(uuid.uuid4()),
        name=f"Chat_{datetime.now().strftime('%m%d_%H%M')}",
        created_at=datetime.now(),
        dataset_id="default",
    )
    st.session_state.sessions.insert(0, s)
    st.session_state.active_session_id = s.id
    return s


def _run_quick_tool(tool_name: str, label: str):
    if not st.session_state.data_loaded:
        st.error(T("Please load patent data first", "请先加载专利数据"))
        return
    try:
        tool = tool_registry.get_tool(tool_name)
        result = asyncio.run(tool.execute(st.session_state.storage))
        # Render result inline — no st.rerun() needed
        if result.chart_html:
            with st.container(border=True):
                st.caption(f"**{label}**")
                st.components.v1.html(result.chart_html, height=500, scrolling=True)
        else:
            st.info(T("No chart generated", "未生成图表"))
    except Exception as e:
        st.error(T(f"Failed: {e}", f"执行失败: {e}"))


def _close_tab(tab_id: str):
    if tab_id in st.session_state.open_tabs:
        del st.session_state.open_tabs[tab_id]
    if st.session_state.active_tab == tab_id:
        st.session_state.active_tab = "chat"


def _export_report(msg: dict):
    st.divider()
    st.subheader(T("Export Report", "导出分析报告"))
    gen = ReportGenerator()
    gen.add_section(T("Analysis Conclusion", "分析结论"), msg.get("content", ""))
    if msg.get("tool_executions"):
        for e in msg["tool_executions"]:
            if e.status == "completed" and e.result:
                gen.add_section(
                    e.tool_name,
                    f"Status: {e.status}  Time: {e.duration_ms:.0f}ms",
                    getattr(e.result, 'chart_html', None),
                )
    html_report = gen.generate_html(title="PatentAgent Report")
    st.download_button(
        T("Download HTML Report", "下载 HTML 报告"),
        data=html_report.encode("utf-8"),
        file_name=f"patent_report_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
        mime="text/html",
    )


def _export_latest_report():
    for msg in reversed(st.session_state.messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            _export_report(msg)
            return
    st.info(T("No analysis content to export", "暂无分析内容可导出"))


def _render_chat_area(session):
    """Render the Agent chat area."""
    # ── WAITING_APPROVAL ──
    if session and session.status == "awaiting_approval" and session.pending_plan:
        decision = render_approval_buttons(session)
        if decision == "APPROVED":
            if st.session_state.agent and st.session_state.data_loaded:
                with st.spinner(T("Executing...", "执行中...")):
                    resp = asyncio.run(st.session_state.agent.resume_with_approval(
                        session=session, storage=st.session_state.storage,
                        decision="APPROVED",
                    ))
                    st.session_state.messages.append({
                        "role": "assistant", "content": resp.text,
                        "charts": resp.charts,
                        "tool_executions": resp.tool_executions,
                    })
                    if session:
                        session.messages = st.session_state.messages
        elif decision == "REJECTED":
            session.status = "idle"
            session.pending_plan = None
            st.session_state.messages.append({
                "role": "assistant",
                "content": T("Cancelled.", "已取消。"),
            })
        elif decision == "MODIFIED":
            st.text_area(
                T("Modification notes", "修改说明"), key="modify_notes",
                placeholder=T("Describe what to adjust...", "描述需要调整的内容..."),
            )
            if st.button(T("Submit", "提交修改")):
                resp = asyncio.run(st.session_state.agent.resume_with_approval(
                    session=session, storage=st.session_state.storage,
                    decision="MODIFIED",
                    modifications={"notes": st.session_state.get("modify_notes", "")},
                ))
                st.session_state.messages.append({
                    "role": "assistant", "content": resp.text,
                    "charts": resp.charts,
                    "tool_executions": resp.tool_executions,
                })

    # ── Messages ──
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tool_executions"):
                for e in msg["tool_executions"]:
                    render_tool_card(e)
            if msg.get("charts"):
                for chart_html in msg["charts"]:
                    if chart_html:
                        render_chart_html(chart_html, height=550)
            if msg["role"] == "assistant" and msg.get("content"):
                followup = render_followup_buttons(
                    idx, msg.get("tool_executions"),
                )
                if followup == "export":
                    _export_report(msg)
                elif followup and followup.startswith("suggest:"):
                    st.session_state["_auto_prompt"] = followup.split("suggest:", 1)[1]
                    st.rerun()

    # ── Auto-prompt ──
    auto_prompt = st.session_state.pop("_auto_prompt", None)

    # ── Input ──
    prompt = auto_prompt or st.chat_input(
        T("Describe your patent analysis needs...", "描述你的专利分析需求...")
    )
    if prompt:
        if not st.session_state.llm_configured:
            st.error(T("Please connect LLM first", "请先连接 LLM"))
        elif not st.session_state.data_loaded:
            st.error(T("Please load patent data first", "请先加载专利数据"))
        else:
            if session is None:
                session = _new_session()
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            if session.status == "awaiting_approval" and session.pending_plan:
                st.warning(T("A pending plan needs approval.", "有待确认的分析计划。"))
            else:
                with st.chat_message("assistant"):
                    with st.spinner(T("Analyzing...", "分析中...")):
                        resp = asyncio.run(st.session_state.agent.process_query(
                            prompt, session, st.session_state.storage,
                        ))
                        if resp.needs_approval:
                            st.markdown(resp.text)
                            st.warning(T("Please approve or modify.", "请确认或修改。"))
                            st.session_state.messages.append({
                                "role": "assistant", "content": resp.text,
                                "charts": [], "tool_executions": [],
                            })
                        else:
                            st.markdown(resp.text)
                            if resp.charts:
                                for c in resp.charts:
                                    if c:
                                        render_chart_html(c, height=550)
                            if resp.tool_executions:
                                for e in resp.tool_executions:
                                    render_tool_card(e)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": resp.text,
                                "charts": resp.charts,
                                "tool_executions": resp.tool_executions,
                            })
                if session:
                    session.messages = st.session_state.messages


# ═══════════════════ Top bar ═══════════════════
col_title, col_lang, col_export = st.columns([6, 1, 1])
with col_title:
    st.title(T("PatentAgent", "PatentAgent"))
with col_lang:
    if st.button("EN / 中文", use_container_width=True):
        cur = st.session_state.get("lang", "zh")
        st.session_state["lang"] = "en" if cur == "zh" else "zh"
        st.rerun()
with col_export:
    if st.button(T("Export", "导出"), use_container_width=True):
        if st.session_state.messages:
            _export_latest_report()
        else:
            st.info(T("Nothing to export yet", "暂无内容可导出"))

# ═══════════════════ Sidebar ═══════════════════
with st.sidebar:
    st.subheader(T("Data Management", "数据管理"))
    input_dir = st.text_input(
        T("Patent data directory", "专利数据目录"),
        value=st.session_state.input_dir,
        label_visibility="collapsed",
        placeholder="./my_patents",
    )
    c_load, c_refresh = st.columns(2)
    with c_load:
        if st.button(T("Load", "加载"), use_container_width=True):
            with st.spinner(T("Parsing...", "解析中...")):
                store = _cached_load_store(input_dir)
                if not store.is_empty:
                    st.session_state.storage = store
                    st.session_state.data_loaded = True
                    st.session_state.input_dir = input_dir
                    st.rerun()
                else:
                    st.error(T("No valid data found", "无有效数据"))
    with c_refresh:
        if st.button(T("Refresh", "刷新"), use_container_width=True):
            st.session_state.data_loaded = False
            st.rerun()

    if st.session_state.data_loaded:
        render_data_panel(st.session_state.storage)
        c1, c2 = st.columns(2)
        with c1:
            if st.button(T("Switch Dataset", "切换数据集"), use_container_width=True):
                st.session_state.data_loaded = False
                st.rerun()
        with c2:
            if st.button(T("Import New", "导入新数据"), use_container_width=True):
                st.session_state.data_loaded = False
                st.rerun()

    st.divider()

    with st.expander(T("LLM Settings", "LLM 设置"), expanded=not st.session_state.llm_configured):
        provider_name = st.selectbox(
            T("Provider", "供应商"), ["Claude", "OpenAI", "DeepSeek"],
            label_visibility="collapsed",
        )
        api_key = st.text_input("API Key", type="password",
                                value=st.session_state.api_key,
                                label_visibility="collapsed", placeholder="API Key")
        base_url = st.text_input("Base URL", value=st.session_state.base_url,
                                 label_visibility="collapsed",
                                 placeholder=T("Leave blank for default", "留空使用默认"))
        if st.button(T("Connect", "连接"), use_container_width=True):
            if not api_key:
                st.error(T("API Key required", "请输入 API Key"))
            else:
                client = _cached_llm_client(provider_name, api_key, base_url)
                if client is None:
                    st.error(T(f"Connection failed", f"连接失败"))
                else:
                    agent = PatentAgentOrchestrator(
                        llm_client=client, tool_registry=tool_registry,
                        knowledge_base=_cached_knowledge(),
                    )
                    st.session_state.llm_client = client
                    st.session_state.llm_configured = True
                    st.session_state.agent = agent
                    st.session_state.provider = provider_name
                    st.session_state.api_key = api_key
                    st.session_state.base_url = base_url
                    st.success(T(f"Connected to {provider_name}", f"已连接 {provider_name}"))

    st.divider()

    with st.expander(T("Quick Tools", "快捷工具")):
        if st.button(T("Dataset Overview", "数据总览"), use_container_width=True):
            _run_quick_tool("get_dataset_summary", T("Overview", "总览"))
        if st.button(T("Trend Analysis", "趋势分析"), use_container_width=True):
            _run_quick_tool("analyze_patent_trend", T("Trend", "趋势"))
        if st.button(T("Growth Trend", "增长趋势"), use_container_width=True):
            _run_quick_tool("analyze_lifecycle", T("Trend", "增长趋势"))
        if st.button(T("IPC Heatmap", "IPC热力图"), use_container_width=True):
            _run_quick_tool("analyze_ipc_distribution", T("IPC", "IPC"))
        if st.button(T("Word Cloud", "词云热点"), use_container_width=True):
            _run_quick_tool("generate_wordcloud", T("WordCloud", "词云"))
        if st.button(T("Burst Terms", "突发词检测"), use_container_width=True):
            _run_quick_tool("analyze_burst_terms", T("Burst", "突发词"))
        if st.button(T("Yearly Keywords", "逐年关键词"), use_container_width=True):
            _run_quick_tool("analyze_yearly_keywords", T("Yearly KW", "逐年词"))
        if st.button(T("Country Distribution", "国家分布"), use_container_width=True):
            _run_quick_tool("analyze_country_distribution", T("Country", "国家"))
        if st.button(T("Co-Applicant Network", "合作网络"), use_container_width=True):
            _run_quick_tool("analyze_co_network", T("Network", "网络"))
        if st.button(T("Tech Roadmap", "技术路线图"), use_container_width=True):
            _run_quick_tool("analyze_tech_roadmap", T("Roadmap", "路线图"))
        if st.button(T("Tech-Effect Matrix", "技术功效矩阵"), use_container_width=True):
            _run_quick_tool("analyze_tech_matrix", T("Tech Matrix", "功效矩阵"))
        if st.button(T("Patent Clustering", "专利聚类"), use_container_width=True):
            _run_quick_tool("analyze_clustering", T("Clustering", "聚类"))
        if st.button(T("Patent Valuation", "专利价值评估"), use_container_width=True):
            _run_quick_tool("analyze_patent_valuation", T("Valuation", "价值评估"))
        if st.button(T("Classic Mode", "经典模式"), use_container_width=True):
            st.session_state.show_classic = not st.session_state.show_classic

    st.divider()

    st.subheader(T("Sessions", "会话"))
    if st.button(T("New Session", "新建会话"), use_container_width=True):
        _new_session()
        st.session_state.messages = []
        st.rerun()

    if st.session_state.sessions:
        for s in st.session_state.sessions[:10]:
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                sicon = {"completed": "[OK]", "awaiting_approval": "[?]",
                         "executing": "[..]", "cancelled": "[X]"}.get(s.status, "[ ]")
                is_active = s.id == st.session_state.active_session_id
                label = f"{sicon} {s.name}"
                if is_active:
                    label = f"**{label}**"
                st.caption(label)
            with c2:
                if st.button(">", key=f"sw_{s.id}", help=T("Switch", "切换")):
                    st.session_state.active_session_id = s.id
                    st.session_state.messages = s.messages or []
                    st.rerun()
            with c3:
                if st.button("X", key=f"del_{s.id}", help=T("Delete", "删除")):
                    st.session_state.sessions.remove(s)
                    if s.id == st.session_state.active_session_id:
                        st.session_state.active_session_id = None
                        st.session_state.messages = []
                    st.rerun()

    st.divider()
    if st.button(T("Clear Chat", "清空对话"), use_container_width=True):
        st.session_state.messages = []
        s = _get_active_session()
        if s:
            s.messages = []
        st.rerun()

# ═══════════════════ Main area: tabs ═══════════════════
tab_ids = ["chat"]
tab_labels = [T("PatentAgent Chat", "PatentAgent 对话")]
tab_ids += list(st.session_state.open_tabs.keys())
for tid in tab_ids[1:]:
    tab_labels.append(st.session_state.open_tabs[tid]['label'])

tabs = st.tabs(tab_labels)

with tabs[0]:
    _render_chat_area(_get_active_session())

for i, tid in enumerate(tab_ids[1:], start=1):
    with tabs[i]:
        info = st.session_state.open_tabs.get(tid, {})
        c_close, c_refresh, c_empty = st.columns([2, 2, 8])
        with c_close:
            if st.button(T("Close Tab", "关闭标签"), key=f"close_{tid}", use_container_width=True):
                _close_tab(tid)
                st.rerun()
        with c_refresh:
            if st.button(T("Refresh", "刷新"), key=f"rerun_{tid}", use_container_width=True):
                tool = tool_registry.get_tool(info.get("tool", ""))
                result = asyncio.run(tool.execute(st.session_state.storage))
                st.session_state.open_tabs[tid]["chart_html"] = result.chart_html or ""
                st.rerun()
        chart_html = info.get("chart_html", "")
        if chart_html:
            st.components.v1.html(chart_html, height=600, scrolling=True)
        else:
            st.info(T("No chart generated", "未生成图表"))

# 自动跳转到 active_tab（JS 注入）
_target = st.session_state.active_tab
if _target != "chat" and _target in tab_ids:
    _idx = tab_ids.index(_target)
    st.markdown(f"""
    <script>
    (function() {{
        var btns = parent.document.querySelectorAll('button[data-baseweb="tab"]');
        if (btns.length > {_idx}) {{
            setTimeout(function() {{ btns[{_idx}].click(); }}, 100);
        }}
    }})();
    </script>
    """, unsafe_allow_html=True)

# ═══════════════════ Classic Mode ═══════════════════
if st.session_state.show_classic:
    st.divider()
    st.subheader(T("Classic Batch Mode", "经典批处理模式"))
    if not st.session_state.data_loaded:
        st.warning(T("Please load patent data first", "请先加载专利数据"))
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            do_trend = st.checkbox(T("Monthly Trend", "月度趋势"), value=True)
            do_lifecycle = st.checkbox(T("Growth Trend", "增长趋势"), value=True)
            do_ipc = st.checkbox(T("IPC Heatmap", "IPC热力图"), value=True)
        with c2:
            do_nlp = st.checkbox(T("Word Cloud", "词云词频"), value=True)
            do_country = st.checkbox(T("Country Distribution", "国家分布"), value=True)
            do_yearly = st.checkbox(T("Yearly Keywords", "逐年关键词"), value=False)
        with c3:
            do_burst = st.checkbox(T("Burst Terms", "突发词"), value=False)
            do_roadmap = st.checkbox(T("Tech Roadmap", "技术路线图"), value=False)
            do_csv = st.checkbox(T("Export CSV", "导出CSV"), value=False)
        if st.button(T("Run Batch Analysis", "批量分析"), type="primary"):
            store = st.session_state.storage
            all_opts = [
                ("analyze_patent_trend", do_trend, {}),
                ("analyze_lifecycle", do_lifecycle, {}),
                ("analyze_ipc_distribution", do_ipc, {}),
                ("generate_wordcloud", do_nlp, {}),
                ("analyze_country_distribution", do_country, {}),
                ("analyze_yearly_keywords", do_yearly, {}),
                ("analyze_burst_terms", do_burst, {}),
                ("analyze_tech_roadmap", do_roadmap, {}),
            ]
            progress = st.progress(0)
            total = sum(1 for _, v, _ in all_opts if v)
            completed = 0
            for tool_name, enabled, params in all_opts:
                if not enabled:
                    continue
                completed += 1
                progress.progress(completed / max(total, 1),
                                  text=f"[{completed}/{total}] {tool_name}")
                result = asyncio.run(
                    tool_registry.get_tool(tool_name).execute(store, **params)
                )
                if result.chart_html:
                    with st.expander(tool_name, expanded=(total <= 4)):
                        st.components.v1.html(result.chart_html, height=500, scrolling=True)
            if do_csv:
                csv = store.get_all().to_csv(index=False).encode("utf-8-sig")
                st.download_button(T("Download CSV", "下载 CSV"), csv, "patent_data.csv")
            progress.empty()
            st.success(T(f"Completed {total} analyses", f"完成 {total} 项分析"))
