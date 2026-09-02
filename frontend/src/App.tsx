import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Database, Download, Send,
  Loader2,
  Plus, MessageSquare, Pencil, Trash2,
} from "lucide-react";
import { MessageBubble } from "./components/MessageBubble";
import { LLMAdvancedSettings } from "./components/LLMAdvancedSettings";
import { localizeErrorMessage, toolLabel } from "./uiLabels";
import {
  fetchHealth, runTool, streamChat,
  createSession, fetchSessions, fetchSession, renameSession, deleteSession,
  resynthesizeTurn, fetchProviderProfiles, disconnectLLM,
  fetchCapabilities,
  fetchTask, streamTaskEvents,
} from "./api";
import type { Message, ToolStep, SessionSummary, ProviderProfile } from "./types";
import { normalizeAssistantContent } from "./finalAnswer";
import { useMessageState } from "./features/agent/useMessageState";
import { datasetKeys, useDataSummaryQuery, useDatasetsQuery } from "./features/datasets/queries";
import { providerKeys, useHealthQuery, useProviderProfilesQuery } from "./features/providers/queries";
import { sessionKeys, useSessionsQuery } from "./features/sessions/queries";
import { messagesFromSession } from "./features/sessions/restoreMessages";
import { toolKeys, useSearchStatusQuery, useToolsQuery } from "./features/tools/queries";
import { AppShell, type WorkbenchRoute } from "./features/workbench/AppShell";
import { CapabilityCards } from "./features/capabilities/CapabilityCards";
import { CapabilitiesPage } from "./features/capabilities/CapabilitiesPage";
import { DatasetsPage } from "./features/datasets/DatasetsPage";
import { ReportsPage } from "./features/reports/ReportsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { QuickToolReturnPrompt } from "./features/tools/QuickToolReturnPrompt";
import { useI18n, type TranslationKey, type TranslationParams } from "./i18n";

const QUICK_TOOL_CHAT_PROMPT_KEY = "patentagent_skip_quick_tool_chat_prompt";

type AppError = { key: TranslationKey; params?: TranslationParams } | { raw: string };

function renderAppError(error: AppError | null, locale: "zh-CN" | "en-US", t: (key: TranslationKey, params?: TranslationParams) => string): string | null {
  if (!error) return null;
  if ("raw" in error) return localizeErrorMessage(error.raw, locale);
  const params = error.params
    ? { ...error.params, ...(typeof error.params.message === "string"
      ? { message: localizeErrorMessage(error.params.message, locale) } : {}) }
    : undefined;
  return t(error.key, params);
}

function routeFromPath(pathname: string): WorkbenchRoute {
  if (pathname.startsWith("/datasets")) return "datasets";
  if (pathname.startsWith("/capabilities")) return "capabilities";
  if (pathname.startsWith("/reports")) return "reports";
  if (pathname.startsWith("/settings")) return "settings";
  return "chat";
}

export default function App() {
  const { locale, t } = useI18n();
  const queryClient = useQueryClient();
  const healthQuery = useHealthQuery();
  const toolsQuery = useToolsQuery(healthQuery.isSuccess);
  const searchStatusQuery = useSearchStatusQuery(healthQuery.isSuccess);
  const profilesQuery = useProviderProfilesQuery(healthQuery.isSuccess);
  const summaryQuery = useDataSummaryQuery((healthQuery.data?.patents_loaded || 0) > 0);
  const sessionsQuery = useSessionsQuery();
  const datasetsQuery = useDatasetsQuery();
  const capabilitiesQuery = useQuery({
    queryKey: ["capabilities"], queryFn: fetchCapabilities,
    enabled: healthQuery.isSuccess,
  });

  const dataSummary = summaryQuery.data || null;
  const availableTools = toolsQuery.data?.tools || [];
  const providerProfiles = profilesQuery.data?.profiles || [];
  const sessions = sessionsQuery.data?.sessions || [];
  const datasets = datasetsQuery.data?.datasets || [];
  const capabilities = capabilitiesQuery.data?.capabilities || [];
  const backendOnline = healthQuery.isError ? false : healthQuery.data ? true : null;
  const llmConfigured = Boolean(healthQuery.data?.agent_configured);
  const connectedProfileId = healthQuery.data?.connected_profile?.id || "";
  const connectedSnapshot = healthQuery.data?.connected_profile || null;

  // ── State ──
  const [quickToolLoading, setQuickToolLoading] = useState<string | null>(null);
  const [showQuickToolChatPrompt, setShowQuickToolChatPrompt] = useState(false);
  const [skipQuickToolChatPrompt, setSkipQuickToolChatPrompt] = useState(() => {
    try {
      return window.localStorage.getItem(QUICK_TOOL_CHAT_PROMPT_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [error, setError] = useState<AppError | null>(null);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [route, setRoute] = useState<WorkbenchRoute>(() => routeFromPath(window.location.pathname));

  // LLM
  const [showAdvancedLLM, setShowAdvancedLLM] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  // Chat
  const [messages, setMessages] = useMessageState([
    {
      id: "welcome",
      role: "assistant",
      // Keep the stable message identity in state; MessageBubble resolves the
      // current locale when it renders this welcome message.
      content: "",
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [lastUserQuery, setLastUserQuery] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingClarificationTurnId, setPendingClarificationTurnId] = useState<string | undefined>();
  const [responseMode, setResponseMode] = useState<"detailed" | "concise">("detailed");
  const abortRef = useRef<AbortController | null>(null);
  const activeAgentMessageIdRef = useRef<string | null>(null);
  const activeTurnIdRef = useRef<string | null>(null);
  const sessionInitializationStartedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPopState = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (next: WorkbenchRoute) => {
    const path = next === "chat" ? `/chat/${activeSessionId || "new"}` : `/${next}`;
    window.history.pushState({}, "", path);
    setRoute(next);
  };

  useEffect(() => {
    if (summaryQuery.isError) setError({ key: "errors.dataSummary", params: { message: (summaryQuery.error as Error).message } });
  }, [summaryQuery.error, summaryQuery.isError, t]);

  useEffect(() => {
    if (sessionInitializationStartedRef.current) return;
    sessionInitializationStartedRef.current = true;
    const initializeSessions = async () => {
      try {
        const listed = (await fetchSessions()).sessions;
        const pathSession = window.location.pathname.startsWith("/chat/")
          ? decodeURIComponent(window.location.pathname.slice("/chat/".length)) : "";
        let selected = (pathSession !== "new" ? pathSession : "") || localStorage.getItem("patentagent_session_id") || "";
        let available = listed;
        if (!available.some(item => item.id === selected)) {
          if (available.length) selected = available[0].id;
          else {
            const created = await createSession(t("session.new"));
            available = [created];
            selected = created.id;
          }
        }
        queryClient.setQueryData(sessionKeys.all, { sessions: available });
        setActiveSessionId(selected);
        if (routeFromPath(window.location.pathname) === "chat") {
          window.history.replaceState({}, "", `/chat/${selected}`);
        }
        localStorage.setItem("patentagent_session_id", selected);
        const detail = await fetchSession(selected);
        const restored = messagesFromSession(detail);
        if (restored.length) {
          setMessages(restored);
          setPendingClarificationTurnId([...restored].reverse().find(message => message.clarification)?.clarification?.turnId);
        }
      } catch (e) {
        setError({ key: "errors.sessionInit", params: { message: (e as Error).message } });
      }
    };
    initializeSessions();
  }, [queryClient, setMessages, t]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const refreshSessionList = async () => {
    const result = await fetchSessions();
    queryClient.setQueryData(sessionKeys.all, result);
    return result.sessions;
  };

  const refreshProviderProfiles = async (): Promise<ProviderProfile[]> => {
    const [profileResult, health] = await Promise.all([fetchProviderProfiles(), fetchHealth()]);
    queryClient.setQueryData(providerKeys.profiles, profileResult);
    queryClient.setQueryData(providerKeys.health, health);
    return profileResult.profiles;
  };

  const handleSwitchSession = async (sessionId: string) => {
    if (isStreaming || sessionId === activeSessionId) return;
    const detail = await fetchSession(sessionId);
    setActiveSessionId(sessionId);
    localStorage.setItem("patentagent_session_id", sessionId);
    if (route === "chat") window.history.replaceState({}, "", `/chat/${sessionId}`);
    const restored = messagesFromSession(detail);
    setPendingClarificationTurnId([...restored].reverse().find(message => message.clarification)?.clarification?.turnId);
    setMessages(restored.length ? restored : [{
      id: "welcome-" + sessionId, role: "assistant",
      // The renderer localizes this stable welcome identity at render time.
      content: "",
    }]);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: datasetKeys.summary }),
      queryClient.invalidateQueries({ queryKey: toolKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["capabilities"] }),
    ]);
  };

  const handleNewSession = async () => {
    const currentVersion = healthQuery.data?.dataset_snapshot?.version_id;
    const created = await createSession(t("session.newNumber", { number: sessions.length + 1 }), currentVersion);
    await refreshSessionList();
    await handleSwitchSession(created.id);
  };

  const handleRenameSession = async (session: SessionSummary) => {
    const name = window.prompt(t("session.renamePrompt"), session.name);
    if (!name?.trim()) return;
    await renameSession(session.id, name.trim());
    await refreshSessionList();
  };

  const handleDeleteSession = async (session: SessionSummary) => {
    if (!window.confirm(t("session.deleteConfirm", { name: session.name }))) return;
    await deleteSession(session.id);
    const remaining = (await fetchSessions()).sessions;
    queryClient.setQueryData(sessionKeys.all, { sessions: remaining });
    if (session.id === activeSessionId) {
      const next = remaining[0] || await createSession(t("session.new"));
      await refreshSessionList();
      await handleSwitchSession(next.id);
    }
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
      setError({ key: "errors.disconnect", params: { message: (e as Error).message } });
    } finally {
      setIsConnecting(false);
    }
  };

  // ── Quick tool ──
  const handleQuickTool = async (toolName: string, params: Record<string, unknown> = {}) => {
    if (!dataSummary) {
      setError({ key: "errors.dataRequired" });
      return;
    }
    if (!activeSessionId) {
      setError({ key: "errors.sessionInitializing" });
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
        content: result.summary || "",
        contentKey: result.summary ? undefined : "tool.completed",
        contentParams: result.summary ? undefined : { tool: toolName },
        steps: [step],
      }]);
      if (route === "capabilities" && !skipQuickToolChatPrompt) {
        setShowQuickToolChatPrompt(true);
      }
      refreshSessionList().catch(() => undefined);
    } catch (e) {
      console.error("[PatentAgent] Quick tool failed:", toolName, e);
      const message = (e as Error).message;
      setMessages(prev => [...prev, {
        id: `qt-error-${Date.now()}`, role: "system", content: "",
        steps: [{ id: `qt-error-step-${Date.now()}`, tool: toolName,
          status: "failed", error: message, parameters: params }],
      }]);
    } finally {
      setQuickToolLoading(null);
    }
  };

  const handleQuickToolPromptPreference = (checked: boolean) => {
    setSkipQuickToolChatPrompt(checked);
    try {
      if (checked) window.localStorage.setItem(QUICK_TOOL_CHAT_PROMPT_KEY, "1");
      else window.localStorage.removeItem(QUICK_TOOL_CHAT_PROMPT_KEY);
    } catch {
      // A restricted browser storage context should not block tool execution.
    }
  };

  const handleReturnToChat = () => {
    setShowQuickToolChatPrompt(false);
    navigate("chat");
  };

  // ── Agent chat (SSE streaming) ──
  const handleSendMessage = (textOverride?: string, replyToTurnId?: string) => {
    const text = (textOverride ?? inputText).trim();
    if (!text) return;

    if (!dataSummary) {
      setError({ key: "errors.dataRequired" });
      return;
    }
    if (!llmConfigured) {
      setError({ key: "errors.llmRequired" });
      return;
    }
    if (!activeSessionId) {
      setError({ key: "errors.sessionInitializing" });
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
        if ("turn_id" in event && event.turn_id) activeTurnIdRef.current = event.turn_id;
        switch (event.type) {
          case "intent":
            updateAgent(m => ({
              ...m,
              turnId: event.turn_id || m.turnId,
              intent: event.goal || event.analysis_type,
            }));
            break;
          case "plan":
            updateAgent(m => ({
              ...m,
              plan: { steps: event.steps || [], costWeight: event.cost_weight },
              streamStatus: undefined,
              streamStatusKey: event.requires_confirmation ? "chat.analysisPlanWaiting" : "chat.analysisPlanReady",
              streamStatusParams: undefined,
            }));
            break;
          case "synthesis":
            updateAgent(m => ({
              ...m,
              turnId: event.turn_id,
              streamStatus: undefined,
              streamStatusKey: event.status === "fallback" ? "chat.synthesisFallback" : "chat.synthesisEvidence",
              streamStatusParams: undefined,
            }));
            break;
          case "clarification":
            setPendingClarificationTurnId(event.turn_id);
            updateAgent(m => ({
              ...m,
              turnId: event.turn_id,
              content: event.question,
              streamStatus: undefined,
              streamStatusKey: undefined,
              streamStatusParams: undefined,
              clarification: {
                turnId: event.turn_id,
                missingFields: event.missing_fields,
                allowDefaults: event.allow_defaults,
              },
              followupQuestions: [],
              defaultFollowup: event.allow_defaults,
            }));
            break;
          case "step": {
            const stableStepId = event.execution_id || event.tool;
            const s: ToolStep = {
              id: stableStepId,
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
            updateAgent(m => {
              const steps = [...(m.steps || [])];
              const index = steps.findIndex(item =>
                (event.execution_id && item.execution_id === event.execution_id) ||
                (!event.execution_id && item.tool === event.tool && item.status === "running")
              );
              if (index >= 0) steps[index] = { ...steps[index], ...s };
              else steps.push(s);
              return { ...m, turnId: event.turn_id || m.turnId, steps };
            });
            break;
          }
          case "text":
            updateAgent(m => ({
              ...m,
              content: m.clarification ? m.content : m.content + event.content,
              streamStatus: undefined,
              streamStatusKey: undefined,
              streamStatusParams: undefined,
              contentKey: undefined,
              contentParams: undefined,
            }));
            break;
          case "strategy":
            updateAgent(m => ({
              ...m,
              recommendations: event.report?.recommendations || [],
            }));
            break;
          case "error":
            updateAgent(m => ({
              ...m,
              error: event.message,
              errorKey: undefined,
              errorParams: undefined,
              canResynthesize: Boolean(m.steps?.length),
            }));
            break;
          case "done":
            updateAgent(m => {
              const missingAnswer = !event.answer_present || !m.content.trim();
              const normalized = normalizeAssistantContent(m.content, locale);
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
                streamStatusKey: undefined,
                streamStatusParams: undefined,
                // Keep the model payload raw; MessageBubble applies only the
                // client-generated wrapper normalization for the active locale.
                content: missingAnswer ? "" : m.content,
                contentKey: missingAnswer ? "chat.summaryMissing" : undefined,
                contentParams: undefined,
                error: missingAnswer ? undefined : m.error,
                errorKey: missingAnswer ? "chat.serverSummaryMissing" : m.errorKey,
                errorParams: missingAnswer ? undefined : m.errorParams,
                canResynthesize: missingAnswer || event.final_status === "partial" || event.final_status === "failed",
                followupQuestions: nextQuestions,
                followupSuggestions: nextSuggestions,
              };
            });
            setIsStreaming(false);
            activeAgentMessageIdRef.current = null;
            activeTurnIdRef.current = null;
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
          streamStatusKey: undefined,
          streamStatusParams: undefined,
          error: err.message,
          errorKey: "chat.streamError",
          errorParams: { message: err.message },
          content: m.content || "",
          contentKey: m.content ? undefined : "chat.streamInterrupted",
          contentParams: undefined,
          canResynthesize: Boolean(m.steps?.length && m.turnId),
        }));
        setIsStreaming(false);
        activeAgentMessageIdRef.current = null;
        const recoverTurnId = activeTurnIdRef.current;
        if (recoverTurnId) {
          void fetchTask(recoverTurnId).then(task => {
            if (["completed", "partial", "failed", "cancelled", "interrupted"].includes(task.status)) {
              return fetchSession(activeSessionId).then(detail => setMessages(messagesFromSession(detail)));
            }
            streamTaskEvents(recoverTurnId, stored => {
              const payload = stored.payload;
              if ("type" in payload && payload.type === "done") {
                void fetchSession(activeSessionId).then(detail => setMessages(messagesFromSession(detail)));
              }
            });
          }).catch(() => undefined);
        }
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
        streamStatusKey: undefined,
        streamStatusParams: undefined,
        content: message.content || "",
        contentKey: message.content ? undefined : "chat.analysisStopped",
        contentParams: undefined,
        canResynthesize: Boolean(message.steps?.length && message.turnId),
      } : message));
    }
    activeAgentMessageIdRef.current = null;
    activeTurnIdRef.current = null;
    setIsStreaming(false);
  };

  const handleResynthesize = async (turnId: string) => {
    if (!activeSessionId || !llmConfigured) return;
    try {
      const result = await resynthesizeTurn(activeSessionId, turnId, responseMode);
      setMessages(prev => prev.map(message => message.turnId === turnId && message.role === "assistant" ? {
        ...message,
        content: result.text,
        contentKey: undefined,
        contentParams: undefined,
        finalStatus: result.final_status,
        error: undefined,
        errorKey: undefined,
        errorParams: undefined,
        canResynthesize: result.final_status === "partial",
        followupSuggestions: result.followup_suggestions,
        followupQuestions: result.followup_questions,
      } : message));
    } catch (e) {
      setMessages(prev => prev.map(message => message.turnId === turnId ? {
        ...message,
        error: (e as Error).message,
        errorKey: "errors.resynthesize",
        errorParams: { message: (e as Error).message },
      } : message));
    }
  };

  const activeSession = sessions.find(session => session.id === activeSessionId);
  const activeVersionId = activeSession?.dataset_version_id || healthQuery.data?.dataset_snapshot?.version_id || "";
  const activeDataset = datasets.find(dataset => {
    const version = dataset.latest_version.id || dataset.latest_version.version_id;
    return version === activeVersionId;
  });
  const hasUserConversation = messages.some(message => message.role === "user");

  const refreshDatasetState = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: datasetKeys.all }),
      queryClient.invalidateQueries({ queryKey: datasetKeys.summary }),
      queryClient.invalidateQueries({ queryKey: sessionKeys.all }),
      queryClient.invalidateQueries({ queryKey: toolKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["capabilities"] }),
      queryClient.invalidateQueries({ queryKey: providerKeys.health }),
    ]);
    if (activeSessionId) {
      const detail = await fetchSession(activeSessionId);
      queryClient.setQueryData(sessionKeys.detail(activeSessionId), detail);
    }
  };

  const choosePrompt = (prompt: string) => {
    setInputText(prompt);
    if (route !== "chat") navigate("chat");
  };

  const sessionContext = route === "chat" ? (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-100 p-4">
        <div className="mb-3 flex items-center justify-between"><h2 className="flex items-center gap-2 text-sm font-bold text-slate-800"><MessageSquare className="h-4 w-4 text-blue-500" />{t("chat.session")}</h2><button onClick={handleNewSession} disabled={isStreaming} className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:text-blue-600" aria-label={t("session.new")}><Plus className="h-4 w-4" /></button></div>
        <div className="space-y-1">{sessions.map(session => <div key={session.id} className={`group flex items-center gap-1 rounded-xl border px-2 py-2.5 ${session.id === activeSessionId ? "border-blue-200 bg-blue-50" : "border-transparent hover:bg-slate-50"}`}><button onClick={() => handleSwitchSession(session.id)} disabled={isStreaming} className="min-w-0 flex-1 text-left"><div className="truncate text-xs font-medium text-slate-700">{session.name}</div><div className="mt-0.5 text-[10px] text-slate-400">{t("session.turns", { count: session.turn_count || 0 })} · {session.dataset_version_id ? t("session.bound") : t("session.unbound")}</div></button><button onClick={() => handleRenameSession(session)} className="p-1 text-slate-400 opacity-0 group-hover:opacity-100" aria-label={t("settings.edit")}><Pencil className="h-3 w-3" /></button><button onClick={() => handleDeleteSession(session)} className="p-1 text-slate-400 opacity-0 hover:text-rose-600 group-hover:opacity-100" aria-label={t("tool.delete")}><Trash2 className="h-3 w-3" /></button></div>)}</div>
      </div>
      <div className="p-4"><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center gap-2 text-xs font-semibold text-slate-700"><Database className="h-4 w-4 text-blue-500" />{t("chat.currentData")}</div><div className="mt-2 truncate text-sm font-semibold text-slate-800">{activeDataset?.name || t("chat.defaultDataset")}</div><div className="mt-1 text-[11px] text-slate-500">{dataSummary ? t("chat.dataSummary", { count: dataSummary.total_patents.toLocaleString(), start: dataSummary.year_range[0], end: dataSummary.year_range[1] }) : t("chat.dataNotLoaded")}</div><button onClick={() => navigate("datasets")} className="mt-3 w-full rounded-lg border border-slate-200 bg-white py-2 text-xs text-blue-700">{t("chat.manageDatasets")}</button></div></div>
    </div>
  ) : undefined;

  return (
    <AppShell route={route} onNavigate={navigate} backendOnline={backendOnline}
      datasetLabel={activeDataset?.name || (dataSummary ? t("chat.patentCount", { count: dataSummary.total_patents.toLocaleString() }) : "")}
      llmLabel={connectedSnapshot?.name || selectedProfile?.name || ""} taskRunning={isStreaming}
      error={renderAppError(error, locale, t)} onDismissError={() => setError(null)} context={sessionContext}>
      {route === "chat" && <section className="flex h-full min-w-0 flex-col bg-slate-50">
        <div className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          <div className="mx-auto max-w-[1120px] space-y-4 pb-8">
            {!hasUserConversation && capabilities.length > 0 && <div className="rounded-3xl border border-blue-100 bg-gradient-to-br from-white to-blue-50/70 p-5 shadow-sm"><div className="mb-4"><div className="text-xs font-semibold uppercase tracking-widest text-blue-600">{t("home.dispatcher")}</div><h1 className="mt-1 text-xl font-bold text-slate-900">{t("home.title")}</h1><p className="mt-1 text-sm text-slate-500">{t("home.subtitle")}</p></div><CapabilityCards capabilities={capabilities} onPrompt={choosePrompt} compact /></div>}
            {messages.map(msg => <MessageBubble key={msg.id} message={msg} onRetry={step => handleQuickTool(step.tool, step.parameters || {})} onFollowup={(text, replyToTurnId) => handleSendMessage(text, replyToTurnId)} onResynthesize={handleResynthesize} />)}
            <div ref={messagesEndRef} />
          </div>
        </div>
        <div className="shrink-0 border-t border-slate-200 bg-white/95 px-4 pb-4 pt-3 backdrop-blur-md md:px-8">
          <div className="mx-auto max-w-[860px]"><div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-400"><span className="min-w-0 truncate">{t("chat.dataVersion", { dataset: activeDataset?.name || t("chat.defaultDataset"), version: activeVersionId ? activeVersionId.slice(-8) : t("chat.unbound") })}</span><button onClick={() => navigate("capabilities")} className="shrink-0 text-blue-600">{t("chat.viewAllCapabilities")}</button></div><div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 pl-4 shadow-[0_2px_12px_rgba(0,0,0,0.06)] focus-within:border-blue-300"><textarea value={inputText} onChange={event => setInputText(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); handleSendMessage(); } }} placeholder={backendOnline === false ? t("chat.placeholder.backendOffline") : !llmConfigured ? t("chat.placeholder.llmMissing") : !dataSummary ? t("chat.placeholder.datasetMissing") : t("chat.placeholder.input")} className="max-h-32 min-h-[44px] w-full min-w-0 resize-none bg-transparent py-3 text-sm text-slate-700 focus:outline-none" disabled={isStreaming || backendOnline === false} rows={1} />{isStreaming ? <button onClick={handleStopStreaming} aria-label={t("chat.analysisStopped")} className="mb-1 shrink-0 rounded-xl bg-rose-500 p-2.5 text-white"><Loader2 className="h-4 w-4 animate-spin" /></button> : <button onClick={() => handleSendMessage()} aria-label={t("chat.send")} disabled={!inputText.trim() || !activeSessionId} className="mb-1 shrink-0 rounded-xl bg-blue-600 p-2.5 text-white disabled:opacity-40"><Send className="h-4 w-4" /></button>}</div><div className="mt-2 flex flex-wrap items-center justify-center gap-2 text-[10px] text-slate-400"><button onClick={() => setResponseMode(responseMode === "detailed" ? "concise" : "detailed")} className="rounded border border-slate-200 px-2 py-1">{t("chat.responseMode", { mode: responseMode === "detailed" ? t("chat.detailed") : t("chat.concise") })}</button>{lastUserQuery && !isStreaming && <button onClick={() => handleSendMessage(lastUserQuery)} className="rounded border border-slate-200 px-2 py-1">{t("chat.retryLast")}</button>}<button onClick={() => navigate("reports")} className="flex items-center gap-1 rounded border border-slate-200 px-2 py-1"><Download className="h-3 w-3" />{t("chat.report")}</button></div></div>
        </div>
      </section>}
      {route === "datasets" && <DatasetsPage datasets={datasets} activeSessionId={activeSessionId} activeVersionId={activeVersionId} onChanged={refreshDatasetState} onError={message => setError({ raw: message })} />}
      {route === "capabilities" && <CapabilitiesPage capabilities={capabilities} tools={availableTools} searchStatus={searchStatusQuery.data} loadingTool={quickToolLoading} isStreaming={isStreaming} onPrompt={choosePrompt} onRun={handleQuickTool} />}
      {route === "reports" && <ReportsPage activeSessionId={activeSessionId} onError={message => setError({ raw: message })} />}
      {route === "settings" && <SettingsPage profile={selectedProfile} connected={llmConfigured} onOpen={() => setShowAdvancedLLM(true)} onDisconnect={handleDisconnectLLM} />}
      <QuickToolReturnPrompt
        open={showQuickToolChatPrompt}
        dontRemind={skipQuickToolChatPrompt}
        onDontRemindChange={handleQuickToolPromptPreference}
        onStay={() => setShowQuickToolChatPrompt(false)}
        onReturnToChat={handleReturnToChat}
      />
      <LLMAdvancedSettings
        open={showAdvancedLLM}
        profiles={providerProfiles}
        isStreaming={isStreaming}
        onClose={() => setShowAdvancedLLM(false)}
        onRefresh={refreshProviderProfiles}
        onConnected={profile => {
          void refreshProviderProfiles();
        }}
      />
    </AppShell>
  );
}
