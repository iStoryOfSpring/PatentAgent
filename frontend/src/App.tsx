import { useState, useEffect, useRef } from "react";
import {
  Database, Settings, Download, Send, Bot,
  TrendingUp, Activity, Map, Network, Zap,
  Layers, PieChart, FolderSearch, Loader2, AlertTriangle,
  Plus, MessageSquare, Pencil, Trash2, ExternalLink, SlidersHorizontal, Power,
} from "lucide-react";
import { MessageBubble } from "./components/MessageBubble";
import { LLMAdvancedSettings } from "./components/LLMAdvancedSettings";
import {
  fetchHealth, loadData,
  runTool, streamChat, exportReport, fetchTools,
  createSession, fetchSessions, fetchSession, renameSession, deleteSession,
  resynthesizeTurn, fetchProviderProfiles, disconnectLLM,
} from "./api";
import type { Message, DataSummary, ToolStep, Tool, SessionSummary, SessionDetail, ProviderProfile } from "./types";
import { normalizeAssistantContent } from "./finalAnswer";
import { useMessageState } from "./features/agent/useMessageState";
import { useDataSummaryQuery } from "./features/datasets/queries";
import { useHealthQuery, useProviderProfilesQuery } from "./features/providers/queries";
import { useToolsQuery } from "./features/tools/queries";

// ── Quick tools ──
const TOOL_META: Record<string, { label: string; icon: typeof Database }> = {
  get_dataset_summary: { label: "数据总览", icon: Database },
  analyze_patent_trend: { label: "公开趋势", icon: TrendingUp },
  analyze_lifecycle: { label: "增长趋势", icon: Activity },
  analyze_ipc_distribution: { label: "IPC 热力图", icon: Layers },
  generate_wordcloud: { label: "词云热点", icon: PieChart },
  analyze_burst_terms: { label: "近期增长词", icon: Zap },
  analyze_yearly_keywords: { label: "逐年关键词", icon: TrendingUp },
  analyze_country_distribution: { label: "首个公开局", icon: Map },
  analyze_co_network: { label: "合作网络", icon: Network },
  analyze_tech_roadmap: { label: "技术路线图", icon: Activity },
  analyze_tech_matrix: { label: "代理功效矩阵", icon: Layers },
  analyze_clustering: { label: "专利聚类", icon: Network },
  analyze_patent_valuation: { label: "价值筛查", icon: TrendingUp },
  analyze_competitor_evolution: { label: "竞对 IPC 演化", icon: Network },
  search_patents: { label: "相关专利检索", icon: FolderSearch },
  read_patent_details: { label: "专利深读", icon: FolderSearch },
};

function messagesFromSession(detail: SessionDetail): Message[] {
  const turns = new globalThis.Map(detail.turns.map(turn => [String(turn.id), turn]));
  const byTurn = new globalThis.Map<string, ToolStep[]>();
  for (const execution of detail.tool_executions) {
    const result = execution.result || null;
    const step: ToolStep = {
      id: execution.id,
      execution_id: execution.id,
      tool: execution.tool_name,
      status: execution.status,
      duration_ms: execution.duration_ms,
      error: execution.error || null,
      parameters: execution.parameters || {},
      result,
      summary: String(result?.summary || ""),
      methodology: String(result?.methodology || ""),
      data_quality: (result?.data_quality || {}) as Record<string, unknown>,
      warnings: (result?.warnings || []) as string[],
      stale: execution.stale,
      origin: "restored",
    };
    byTurn.set(execution.turn_id, [...(byTurn.get(execution.turn_id) || []), step]);
  }
  return detail.messages.map(stored => {
    const turnId = stored.turn_id || undefined;
    const turn = turnId ? turns.get(turnId) : undefined;
    const status = String(turn?.status || "completed") as Message["finalStatus"];
    const metadata = stored.metadata || {};
    const normalizedContent = stored.role === "assistant"
      ? normalizeAssistantContent(stored.content)
      : { content: stored.content, followupSuggestions: [], followupQuestions: [] };
    const pendingQuestion = (turn?.pending_question || {}) as Record<string, unknown>;
    const structuredSuggestions = (
      (metadata.followup_suggestions as { text?: string }[] | undefined) ||
      normalizedContent.followupSuggestions
    );
    const awaiting = status === "awaiting_clarification";
    return {
      id: `stored-${stored.id}`,
      role: stored.role,
      content: normalizedContent.content,
      turnId,
      steps: stored.role === "assistant" && turnId ? byTurn.get(turnId) : undefined,
      finalStatus: status,
      followupQuestions: awaiting ? ["按默认条件继续"] : (
        (metadata.followup_questions || (
          structuredSuggestions.length
            ? structuredSuggestions.map(item => item.text).filter(Boolean)
            : normalizedContent.followupQuestions
        )) as string[]
      ),
      followupSuggestions: structuredSuggestions as Message["followupSuggestions"],
      clarification: awaiting && turnId ? {
        turnId,
        missingFields: (pendingQuestion.missing_fields || []) as string[],
        allowDefaults: Boolean(pendingQuestion.allow_defaults),
      } : undefined,
      canResynthesize: stored.role === "assistant" && ["partial", "failed"].includes(String(status)) && Boolean(turnId),
    };
  });
}

export default function App() {
  const healthQuery = useHealthQuery();
  const toolsQuery = useToolsQuery(healthQuery.isSuccess);
  const profilesQuery = useProviderProfilesQuery(healthQuery.isSuccess);
  const summaryQuery = useDataSummaryQuery((healthQuery.data?.patents_loaded || 0) > 0);

  // ── State ──
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [dirInput, setDirInput] = useState("./my_patents");
  const [isDataLoading, setIsDataLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null); // null=checking
  const [quickToolLoading, setQuickToolLoading] = useState<string | null>(null);
  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [toolParams, setToolParams] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState("");

  // LLM
  const [providerProfiles, setProviderProfiles] = useState<ProviderProfile[]>([]);
  const [connectedProfileId, setConnectedProfileId] = useState("");
  const [connectedSnapshot, setConnectedSnapshot] = useState<{ id: string; name: string; protocol: ProviderProfile["protocol"]; model: string } | null>(null);
  const [showAdvancedLLM, setShowAdvancedLLM] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  // Chat
  const [messages, setMessages] = useMessageState([
    {
      id: "welcome",
      role: "assistant",
      content: "PatentAgent 已就绪。请加载专利数据，然后输入分析需求，或点击右侧快捷工具一键分析。",
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [lastUserQuery, setLastUserQuery] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingClarificationTurnId, setPendingClarificationTurnId] = useState<string | undefined>();
  const [responseMode, setResponseMode] = useState<"detailed" | "concise">("detailed");
  const abortRef = useRef<AbortController | null>(null);
  const activeAgentMessageIdRef = useRef<string | null>(null);
  const sessionInitializationStartedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Auto-load on mount ──
  useEffect(() => {
    if (healthQuery.data) {
      setBackendOnline(true);
      setLlmConfigured(healthQuery.data.agent_configured);
      setConnectedProfileId(healthQuery.data.connected_profile?.id || "");
      setConnectedSnapshot(healthQuery.data.connected_profile || null);
    } else if (healthQuery.isError) {
      setBackendOnline(false);
    }
  }, [healthQuery.data, healthQuery.isError]);

  useEffect(() => {
    if (profilesQuery.data) setProviderProfiles(profilesQuery.data.profiles);
  }, [profilesQuery.data]);

  useEffect(() => {
    if (toolsQuery.data) setAvailableTools(toolsQuery.data.tools);
  }, [toolsQuery.data]);

  useEffect(() => {
    if (summaryQuery.data) setDataSummary(summaryQuery.data);
    if (summaryQuery.isError) setError("数据摘要加载失败: " + (summaryQuery.error as Error).message);
  }, [summaryQuery.data, summaryQuery.error, summaryQuery.isError]);

  useEffect(() => {
    if (sessionInitializationStartedRef.current) return;
    sessionInitializationStartedRef.current = true;
    const initializeSessions = async () => {
      try {
        const listed = (await fetchSessions()).sessions;
        let selected = localStorage.getItem("patentagent_session_id") || "";
        let available = listed;
        if (!available.some(item => item.id === selected)) {
          if (available.length) selected = available[0].id;
          else {
            const created = await createSession("新会话");
            available = [created];
            selected = created.id;
          }
        }
        setSessions(available);
        setActiveSessionId(selected);
        localStorage.setItem("patentagent_session_id", selected);
        const detail = await fetchSession(selected);
        const restored = messagesFromSession(detail);
        if (restored.length) {
          setMessages(restored);
          setPendingClarificationTurnId([...restored].reverse().find(message => message.clarification)?.clarification?.turnId);
        }
      } catch (e) {
        setError("会话初始化失败: " + (e as Error).message);
      }
    };
    initializeSessions();
  }, []);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const refreshSessionList = async () => {
    setSessions((await fetchSessions()).sessions);
  };

  const refreshProviderProfiles = async (): Promise<ProviderProfile[]> => {
    const [profileResult, health] = await Promise.all([fetchProviderProfiles(), fetchHealth()]);
    setProviderProfiles(profileResult.profiles);
    setLlmConfigured(health.agent_configured);
    setConnectedProfileId(health.connected_profile?.id || "");
    setConnectedSnapshot(health.connected_profile || null);
    return profileResult.profiles;
  };

  const handleSwitchSession = async (sessionId: string) => {
    if (isStreaming || sessionId === activeSessionId) return;
    const detail = await fetchSession(sessionId);
    setActiveSessionId(sessionId);
    localStorage.setItem("patentagent_session_id", sessionId);
    const restored = messagesFromSession(detail);
    setPendingClarificationTurnId([...restored].reverse().find(message => message.clarification)?.clarification?.turnId);
    setMessages(restored.length ? restored : [{
      id: "welcome-" + sessionId, role: "assistant",
      content: "这是一个新会话。你可以提出分析需求，或先运行右侧快捷工具。",
    }]);
  };

  const handleNewSession = async () => {
    const created = await createSession(`新会话 ${sessions.length + 1}`);
    await refreshSessionList();
    await handleSwitchSession(created.id);
  };

  const handleRenameSession = async (session: SessionSummary) => {
    const name = window.prompt("输入新的会话名称", session.name);
    if (!name?.trim()) return;
    await renameSession(session.id, name.trim());
    await refreshSessionList();
  };

  const handleDeleteSession = async (session: SessionSummary) => {
    if (!window.confirm(`确认删除会话“${session.name}”？此操作不可恢复。`)) return;
    await deleteSession(session.id);
    const remaining = (await fetchSessions()).sessions;
    setSessions(remaining);
    if (session.id === activeSessionId) {
      const next = remaining[0] || await createSession("新会话");
      await refreshSessionList();
      await handleSwitchSession(next.id);
    }
  };

  // ── Data loading ──
  const handleLoadData = async () => {
    setIsDataLoading(true);
    setError(null);
    try {
      const data = await loadData(dirInput);
      setDataSummary(data);
      const tools = await fetchTools();
      setAvailableTools(tools.tools);
    } catch (e) {
      setError("加载失败: " + (e as Error).message);
    }
    setIsDataLoading(false);
  };

  // ── LLM config ──
  const selectedProfile = providerProfiles.find(profile => profile.selected)
    || providerProfiles.find(profile => profile.id === connectedProfileId);

  const handleDisconnectLLM = async () => {
    if (isStreaming || !llmConfigured) return;
    setIsConnecting(true);
    setError(null);
    try {
      await disconnectLLM();
      await refreshProviderProfiles();
    } catch (e) {
      setError("断开失败: " + (e as Error).message);
    } finally {
      setIsConnecting(false);
    }
  };

  // ── Quick tool ──
  const handleQuickTool = async (toolName: string, params: Record<string, unknown> = {}) => {
    if (!dataSummary) {
      setError("请先加载专利数据。点击左侧 [加载数据] 按钮。");
      return;
    }
    if (!activeSessionId) {
      setError("会话尚未初始化，请稍后重试。");
      return;
    }
    setError(null);
    setQuickToolLoading(toolName);
    try {
      const result = await runTool(toolName, params, activeSessionId || undefined);
      console.log("[PatentAgent] Tool result:", toolName, result.result_type);
      const stepId = "qt-" + Date.now();
      const step: ToolStep = {
        id: stepId,
        tool: toolName,
        status: "completed",
        chart_html: result.chart_html,
        summary: result.summary,
        methodology: result.methodology,
        data_quality: result.data_quality,
        warnings: result.warnings,
        parameters: (result.result_metadata?.parameters || params) as Record<string, unknown>,
        result: result as Record<string, unknown>,
      };
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: "system",
        content: result.summary || `${TOOL_META[toolName]?.label || toolName}已完成。`,
        steps: [step],
      }]);
      refreshSessionList().catch(() => undefined);
    } catch (e) {
      console.error("[PatentAgent] Quick tool failed:", toolName, e);
      const message = (e as Error).message;
      setMessages(prev => [...prev, {
        id: `qt-error-${Date.now()}`, role: "system", content: "",
        steps: [{ id: `qt-error-step-${Date.now()}`, tool: toolName,
          status: "failed", error: message, parameters: params }],
      }]);
    }
    setQuickToolLoading(null);
  };

  // ── Agent chat (SSE streaming) ──
  const handleSendMessage = (textOverride?: string, replyToTurnId?: string) => {
    const text = (textOverride ?? inputText).trim();
    if (!text) return;

    if (!dataSummary) {
      setError("请先加载专利数据。点击左侧 [加载数据] 按钮。");
      return;
    }
    if (!llmConfigured) {
      setError('请先配置 LLM。在左侧填入 API Key 并点击 [连接]。');
      return;
    }
    if (!activeSessionId) {
      setError("会话尚未初始化，请稍后重试。");
      return;
    }
    if (isStreaming) return;

    setInputText("");
    setLastUserQuery(text);
    setError(null);
    setIsStreaming(true);

    // Add user message
    const userMsg: Message = {
      id: "u-" + Date.now(),
      role: "user",
      content: text,
    };
    setMessages(prev => [...prev, userMsg]);

    // Placeholder agent message
    const agentId = "a-" + Date.now();
    activeAgentMessageIdRef.current = agentId;
    setMessages(prev => [...prev, {
      id: agentId,
      role: "assistant",
      content: "",
      steps: [],
    }]);

    const updateAgent = (updater: (msg: Message) => Message) => {
      setMessages(prev => prev.map(m => m.id === agentId ? updater(m) : m));
    };

    // Start SSE stream
    const effectiveReplyToTurnId = replyToTurnId || pendingClarificationTurnId;
    const controller = streamChat(
      text,
      activeSessionId,
      responseMode,
      (event) => {
        switch (event.type) {
          case "intent":
            updateAgent(m => ({
              ...m,
              intent: event.goal || event.analysis_type,
            }));
            break;
          case "plan":
            // Could show plan steps, but we keep it simple
            break;
          case "synthesis":
            updateAgent(m => ({
              ...m,
              turnId: event.turn_id,
              streamStatus: event.status === "fallback" ? "正在生成结构化降级总结…" : "正在综合工具证据…",
            }));
            break;
          case "clarification":
            setPendingClarificationTurnId(event.turn_id);
            updateAgent(m => ({
              ...m,
              turnId: event.turn_id,
              content: event.question,
              streamStatus: undefined,
              clarification: {
                turnId: event.turn_id,
                missingFields: event.missing_fields,
                allowDefaults: event.allow_defaults,
              },
              followupQuestions: event.allow_defaults ? ["按默认条件继续"] : [],
            }));
            break;
          case "step": {
            const s: ToolStep = {
              id: event.tool + "-" + Date.now(),
              tool: event.tool,
              status: event.status,
              duration_ms: event.duration_ms,
              chart_html: event.chart_html,
              error: event.error,
              summary: event.summary,
              methodology: event.methodology,
              data_quality: event.data_quality,
              warnings: event.warnings,
              parameters: event.parameters,
              result: event.result,
              execution_id: event.execution_id,
              origin: event.origin,
            };
            updateAgent(m => ({
              ...m,
              turnId: event.turn_id || m.turnId,
              steps: [...(m.steps || []), s],
            }));
            break;
          }
          case "text":
            updateAgent(m => ({
              ...m,
              content: m.clarification ? m.content : m.content + event.content,
              streamStatus: undefined,
            }));
            break;
          case "strategy":
            updateAgent(m => ({
              ...m,
              recommendations: event.report?.recommendations || [],
            }));
            break;
          case "error":
            updateAgent(m => ({ ...m, error: event.message, canResynthesize: Boolean(m.steps?.length) }));
            break;
          case "done":
            updateAgent(m => {
              const missingAnswer = !event.answer_present || !m.content.trim();
              const normalized = normalizeAssistantContent(m.content);
              const nextSuggestions = event.followup_suggestions?.length
                ? event.followup_suggestions
                : normalized.followupSuggestions.length
                  ? normalized.followupSuggestions
                  : m.followupSuggestions;
              const nextQuestions = event.followup_questions?.length
                ? event.followup_questions
                : normalized.followupQuestions.length
                  ? normalized.followupQuestions
                  : m.followupQuestions;
              return {
                ...m,
                turnId: event.turn_id,
                finalStatus: event.final_status,
                streamStatus: undefined,
                content: missingAnswer ? "总结未生成。工具结果已保留，请点击“仅重试总结”。" : normalized.content,
                error: missingAnswer ? "服务器未返回有效的最终总结。" : m.error,
                canResynthesize: missingAnswer || event.final_status === "partial" || event.final_status === "failed",
                followupQuestions: nextQuestions,
                followupSuggestions: nextSuggestions,
              };
            });
            setIsStreaming(false);
            activeAgentMessageIdRef.current = null;
            refreshSessionList().catch(() => undefined);
            if (event.final_status !== "awaiting_clarification") {
              setPendingClarificationTurnId(undefined);
            }
            break;
        }
      },
      () => setIsStreaming(false),
      (err) => {
        updateAgent(m => ({
          ...m,
          streamStatus: undefined,
          error: "对话流异常: " + err.message,
          content: m.content || "对话流在总结完成前中断，已经返回的工具结果仍然保留。",
          canResynthesize: Boolean(m.steps?.length && m.turnId),
        }));
        setIsStreaming(false);
        activeAgentMessageIdRef.current = null;
      },
      effectiveReplyToTurnId,
    );
    abortRef.current = controller;
  };

  const handleStopStreaming = () => {
    abortRef.current?.abort();
    const agentId = activeAgentMessageIdRef.current;
    if (agentId) {
      setMessages(prev => prev.map(message => message.id === agentId ? {
        ...message,
        finalStatus: "cancelled",
        streamStatus: undefined,
        content: message.content || "本轮分析已停止。已经返回的工具结果仍然保留。",
        canResynthesize: Boolean(message.steps?.length && message.turnId),
      } : message));
    }
    activeAgentMessageIdRef.current = null;
    setIsStreaming(false);
  };

  const handleResynthesize = async (turnId: string) => {
    if (!activeSessionId || !llmConfigured) return;
    try {
      const result = await resynthesizeTurn(activeSessionId, turnId, responseMode);
      setMessages(prev => prev.map(message => message.turnId === turnId && message.role === "assistant" ? {
        ...message,
        content: result.text,
        finalStatus: result.final_status,
        error: undefined,
        canResynthesize: result.final_status === "partial",
        followupSuggestions: result.followup_suggestions,
        followupQuestions: result.followup_questions,
      } : message));
    } catch (e) {
      setMessages(prev => prev.map(message => message.turnId === turnId ? {
        ...message, error: "重新综合失败: " + (e as Error).message,
      } : message));
    }
  };

  // ── Report export ──
  const handleExport = async () => {
    const msgs = messages
      .filter(m => m.role !== "system")
      .map(m => ({ role: m.role, content: m.content }));
    try {
      const html = await exportReport(msgs, "PatentAgent Report");
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `patent_report_${new Date().toISOString().slice(0, 10)}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError("导出失败: " + (e as Error).message);
    }
  };

  // ── Render ──
  return (
    <div className="h-screen w-screen flex flex-col bg-slate-50 text-slate-900 font-sans overflow-hidden">
      {/* Top bar */}
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-2 text-blue-700 font-bold text-lg">
          <div className="bg-blue-600 text-white p-1.5 rounded-lg">
            <Bot className="w-5 h-5" />
          </div>
          PatentAgent
          <span className="text-slate-400 font-normal text-xs ml-2 border-l border-slate-300 pl-2">
            {dataSummary ? `${dataSummary.total_patents.toLocaleString()} 件` :
             backendOnline === false ? "后端未连接" :
             backendOnline === null ? "检测中..." : "数据未加载"}
          </span>
          {llmConfigured && <span className="text-emerald-500 text-xs ml-1">· LLM 工具调用已就绪</span>}
        </div>
        <div className="flex gap-3 items-center">
          {error && (
            <div className="flex items-center gap-1 text-rose-600 text-xs bg-rose-50 px-3 py-1 rounded-full">
              <AlertTriangle className="w-3 h-3" />
              {error}
              <button onClick={() => setError(null)} className="ml-1 font-bold">&times;</button>
            </div>
          )}
          <button onClick={() => setShowAdvancedLLM(true)} disabled={isStreaming}
            className="xl:hidden flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-md border border-slate-200 disabled:opacity-50">
            <SlidersHorizontal className="w-4 h-4" /> <span className="hidden sm:inline">LLM 设置</span>
          </button>
          <button onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-md border border-slate-200">
            <Download className="w-4 h-4" /> 导出报告
          </button>
        </div>
      </header>

      {/* Main layout */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left sidebar */}
        <aside className="hidden xl:flex w-[300px] bg-white border-r border-slate-200 flex-col overflow-y-auto shrink-0">
          {/* Conversation panel */}
          <div className="p-4 border-b border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-blue-500" /> 会话
              </h2>
              <button onClick={handleNewSession} disabled={isStreaming}
                className="p-1.5 rounded-md border border-slate-200 text-slate-500 hover:text-blue-600 hover:border-blue-200 disabled:opacity-50"
                title="新建会话">
                <Plus className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-1 max-h-44 overflow-y-auto">
              {sessions.map(session => (
                <div key={session.id}
                  className={`group flex items-center gap-1 rounded-lg border px-2 py-2 ${session.id === activeSessionId ? "border-blue-200 bg-blue-50" : "border-transparent hover:bg-slate-50"}`}>
                  <button onClick={() => handleSwitchSession(session.id)}
                    className="flex-1 text-left min-w-0" disabled={isStreaming}>
                    <div className="text-xs font-medium text-slate-700 truncate">{session.name}</div>
                    <div className="text-[10px] text-slate-400">{session.turn_count || 0} 轮</div>
                  </button>
                  <button onClick={() => handleRenameSession(session)}
                    className="p-1 text-slate-400 hover:text-blue-600 opacity-0 group-hover:opacity-100" title="重命名">
                    <Pencil className="w-3 h-3" />
                  </button>
                  <button onClick={() => handleDeleteSession(session)}
                    className="p-1 text-slate-400 hover:text-rose-600 opacity-0 group-hover:opacity-100" title="删除">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
          {/* Data panel */}
          <div className="p-5 border-b border-slate-100">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-500" /> 数据管理
            </h2>
            <div className="mb-3">
              <label className="block text-xs font-medium text-slate-500 mb-1.5">专利数据目录</label>
              <div className="relative">
                <FolderSearch className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text" value={dirInput}
                  onChange={e => setDirInput(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
            </div>
            <button
              onClick={handleLoadData}
              disabled={isDataLoading}
              className="w-full py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-70"
            >
              {isDataLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "加载数据"}
            </button>

            {dataSummary && (
              <div className="mt-5 p-4 bg-slate-50 border border-slate-100 rounded-xl">
                <div className="text-xs font-semibold text-slate-500 mb-3 uppercase">数据概况</div>
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div>
                    <div className="text-2xl font-bold text-slate-800">
                      {(dataSummary.total_patents / 1000).toFixed(1)}k
                    </div>
                    <div className="text-[11px] text-slate-500">专利总量</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-slate-800 mt-1">
                      {dataSummary.year_range[0]}-{dataSummary.year_range[1]}
                    </div>
                    <div className="text-[11px] text-slate-500">年份区间</div>
                  </div>
                </div>
                <div className="mb-3">
                  <div className="text-[11px] text-slate-500 mb-1.5">IPC 分类</div>
                  <div className="flex flex-wrap gap-1.5">
                    {dataSummary.ipc_sections.map(ipc => (
                      <span key={ipc} className="bg-blue-50 text-blue-700 border border-blue-100 px-2 py-0.5 rounded text-[10px] font-mono font-medium">{ipc}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-slate-500 mb-1.5">主要申请人</div>
                  <div className="space-y-1">
                    {dataSummary.top_applicants.map(app => (
                      <div key={app.name} className="flex justify-between items-center text-xs">
                        <span className="text-slate-700 truncate pr-2" title={app.name}>{app.name}</span>
                        <span className="text-slate-400 font-mono">{app.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* LLM settings */}
          <div className="p-5">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Settings className="w-4 h-4 text-slate-500" /> LLM 设置
            </h2>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-start gap-2">
                <div className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${llmConfigured ? "bg-emerald-500" : selectedProfile?.probe_status === "failed" ? "bg-rose-500" : selectedProfile?.needs_reconnect ? "bg-amber-500" : "bg-slate-300"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-semibold text-slate-800 truncate">{connectedSnapshot?.name || selectedProfile?.name || "尚未配置供应商"}</span>
                    {(connectedSnapshot?.protocol || selectedProfile?.protocol) && <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-white border border-slate-200 text-slate-500">{(connectedSnapshot?.protocol || selectedProfile?.protocol)?.replace("_chat", "").replace("_messages", "")}</span>}
                  </div>
                  <div className="text-[11px] text-slate-500 truncate mt-0.5">{connectedSnapshot?.model || selectedProfile?.model || "请打开高级设置新增配置"}</div>
                  <div className={`text-[10px] mt-1 ${llmConfigured ? "text-emerald-600" : selectedProfile?.probe_status === "failed" ? "text-rose-600" : selectedProfile?.credential_loaded ? "text-amber-600" : "text-slate-400"}`}>
                    {llmConfigured ? "已连接，工具调用能力已验证" : selectedProfile?.needs_reconnect ? "配置已修改，需要重新连接" : selectedProfile?.probe_status === "failed" ? `探测失败${selectedProfile.probe_error_category ? ` · ${selectedProfile.probe_error_category}` : ""}` : selectedProfile?.credential_loaded || selectedProfile?.auth_mode === "none" ? "尚未连接" : "待输入凭证"}
                  </div>
                </div>
                {selectedProfile?.website_url && <a href={selectedProfile.website_url} target="_blank" rel="noopener noreferrer" className="p-1 text-slate-400 hover:text-blue-600" title="访问供应商官网"><ExternalLink className="w-3.5 h-3.5" /></a>}
              </div>
              {selectedProfile?.notes && <p className="mt-2 text-[10px] leading-4 text-slate-500 line-clamp-2">{selectedProfile.notes}</p>}
              <div className="grid grid-cols-2 gap-2 mt-3">
                <button onClick={() => setShowAdvancedLLM(true)} disabled={isStreaming} className="py-1.5 rounded-lg border border-slate-200 bg-white text-xs text-slate-700 flex items-center justify-center gap-1 disabled:opacity-50"><SlidersHorizontal className="w-3.5 h-3.5" />{providerProfiles.length ? "切换 / 设置" : "添加供应商"}</button>
                {llmConfigured ? <button onClick={handleDisconnectLLM} disabled={isStreaming || isConnecting} className="py-1.5 rounded-lg border border-slate-200 bg-white text-xs text-slate-600 flex items-center justify-center gap-1 disabled:opacity-50">{isConnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}断开</button> : <button onClick={() => setShowAdvancedLLM(true)} disabled={isStreaming} className="py-1.5 rounded-lg bg-blue-600 text-white text-xs disabled:opacity-50">连接</button>}
              </div>
            </div>
          </div>
        </aside>

        {/* Center chat */}
        <section className="flex-1 min-w-0 flex flex-col bg-slate-50">
          <div className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 space-y-4">
            <div className="max-w-[1120px] mx-auto space-y-4 pb-8">
              {messages.map(msg => (
                <MessageBubble key={msg.id} message={msg}
                  onRetry={step => handleQuickTool(step.tool, step.parameters || {})}
                  onFollowup={(text, replyToTurnId) => handleSendMessage(text, replyToTurnId)}
                  onResynthesize={handleResynthesize} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input */}
          <div className="shrink-0 border-t border-slate-200 bg-white/95 backdrop-blur-md pt-3 pb-4 px-4 md:px-8">
            <div className="max-w-[800px] mx-auto relative">
              <div className="flex items-end gap-2 bg-white rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] border border-slate-200 p-2 pl-4 focus-within:border-blue-300">
                <textarea
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder={
                    backendOnline === false ? "后端未启动，请运行 uvicorn server:app --port 8000" :
                    !llmConfigured ? "请先打开 LLM 设置并连接供应商" :
                    !dataSummary ? "请先在左侧加载数据" :
                    "描述你的分析需求，例如：分析近三年技术趋势"
                  }
                  className="w-full max-h-32 min-h-[44px] py-3 text-sm text-slate-700 bg-transparent resize-none focus:outline-none"
                  disabled={isStreaming || backendOnline === false}
                  rows={1}
                />
                {isStreaming ? (
                  <button onClick={handleStopStreaming}
                    className="mb-1 p-2.5 rounded-xl bg-rose-500 hover:bg-rose-600 text-white transition-colors shadow-sm">
                    <Loader2 className="w-4 h-4 animate-spin" />
                  </button>
                ) : (
                  <button onClick={() => handleSendMessage()}
                    disabled={!inputText.trim() || isStreaming || backendOnline === false || !activeSessionId}
                    className="mb-1 p-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50 shadow-sm shadow-blue-200">
                    <Send className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
            <div className="text-center mt-3 text-[11px] text-slate-400">
              <a href="https://github.com/iStoryOfSpring/PatentAgent" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-white hover:text-slate-600 transition-colors">
                <ExternalLink className="w-3 h-3" /> Source
              </a>
              <button onClick={() => setResponseMode(responseMode === "detailed" ? "concise" : "detailed")}
                className="mr-3 px-2 py-1 rounded bg-white border border-slate-200 text-slate-600">
                回复：{responseMode === "detailed" ? "详细" : "简洁"}
              </button>
              {lastUserQuery && !isStreaming && (
                <button onClick={() => handleSendMessage(lastUserQuery)}
                  className="mr-3 px-2 py-1 rounded bg-white border border-slate-200 text-slate-600">
                  重试上次提问
                </button>
              )}
              {llmConfigured ? "Agent 将完整读取工具证据并综合结论" : "配置 LLM 后可启用 Agent 对话"}
            </div>
          </div>
        </section>

        {/* Right sidebar: quick tools */}
        <aside className="hidden lg:flex w-[280px] bg-white border-l border-slate-200 overflow-y-auto flex-col shrink-0">
          <div className="p-5 sticky top-0 bg-white/80 backdrop-blur-md border-b border-slate-100 z-20">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" /> 快捷工具
            </h2>
            <p className="text-xs text-slate-500 mt-1">{availableTools.length} 个工具 &middot; 按数据能力启用</p>
          </div>
          <div className="p-4 space-y-1">
            {availableTools.map(t => {
              const meta = TOOL_META[t.name] || { label: t.name, icon: Zap };
              const Icon = meta.icon;
              const availability = t.availability || { available: true, reason: "" };
              const hasParams = Object.keys(t.parameters).length > 0;
              const expanded = selectedTool === t.name;
              const requiredMissing = Object.entries(t.parameters).some(
                ([name, schema]) => schema.required && !(toolParams[name] || "").trim(),
              );
              return (
                <div key={t.name} className="border-b border-slate-50 pb-1">
                  <button
                    onClick={() => hasParams ? setSelectedTool(expanded ? null : t.name) : handleQuickTool(t.name)}
                    disabled={isStreaming || !availability.available}
                    title={availability.reason || t.description}
                    className="w-full flex items-center gap-3 p-2.5 rounded-xl hover:bg-slate-50 text-slate-700 transition-all disabled:opacity-40 group"
                  >
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                      {quickToolLoading === t.name ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
                    </div>
                    <span className="text-sm font-medium text-left flex-1">{meta.label}</span>
                    {hasParams && <span className="text-slate-400 text-xs">{expanded ? "−" : "+"}</span>}
                  </button>
                  {!availability.available && availability.reason && (
                    <p className="px-3 pb-2 text-[10px] text-amber-700">{availability.reason}</p>
                  )}
                  {expanded && (
                    <div className="mx-2 mb-2 p-3 bg-slate-50 rounded-lg space-y-2">
                      {Object.entries(t.parameters).map(([name, schema]) => (
                        <label key={name} className="block text-[11px] text-slate-600">
                          {name}{schema.required ? " *" : ""}
                          {schema.enum ? (
                            <select value={toolParams[name] || ""} onChange={e => setToolParams(p => ({...p, [name]: e.target.value}))}
                              className="mt-1 w-full p-1.5 border rounded bg-white">
                              <option value="">默认</option>
                              {schema.enum.map(v => <option key={v}>{v}</option>)}
                            </select>
                          ) : (
                            <input value={toolParams[name] || ""} onChange={e => setToolParams(p => ({...p, [name]: e.target.value}))}
                              placeholder={schema.description}
                              className="mt-1 w-full p-1.5 border rounded bg-white" />
                          )}
                        </label>
                      ))}
                      <button disabled={requiredMissing || quickToolLoading === t.name} onClick={() => {
                        const params: Record<string, unknown> = {};
                        Object.entries(t.parameters).forEach(([name, schema]) => {
                          const raw = toolParams[name];
                          if (!raw) return;
                          params[name] = schema.type === "integer" ? Number(raw) :
                            schema.type === "array" ? raw.split(",").map(v => v.trim()).filter(Boolean) : raw;
                        });
                        handleQuickTool(t.name, params);
                      }} className="w-full py-1.5 bg-indigo-600 text-white text-xs rounded disabled:opacity-40 disabled:cursor-not-allowed">
                        执行
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      </main>
      <LLMAdvancedSettings
        open={showAdvancedLLM}
        profiles={providerProfiles}
        isStreaming={isStreaming}
        onClose={() => setShowAdvancedLLM(false)}
        onRefresh={refreshProviderProfiles}
        onConnected={profile => {
          setLlmConfigured(true);
          setConnectedProfileId(profile.id);
          setConnectedSnapshot({ id: profile.id, name: profile.name, protocol: profile.protocol, model: profile.model });
        }}
      />
    </div>
  );
}
