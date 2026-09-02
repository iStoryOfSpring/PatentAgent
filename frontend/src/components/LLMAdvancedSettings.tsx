import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowLeft, ChevronDown, ChevronUp, Copy, Eye, EyeOff,
  ExternalLink, Loader2, Plus, RefreshCw, Save, TestTube2, Trash2, X, Zap,
} from "lucide-react";
import {
  ApiError,
  activateProviderProfile, createProviderProfile, deleteProviderProfile,
  discoverProviderModels, probeProviderProfile, updateProviderProfile,
} from "../api";
import type {
  ProviderCredentials, ProviderProfile, ProviderProfileInput, ProviderProtocol,
  ProviderProbeResult,
} from "../types";
import {
  authModeLabel, errorCategoryLabel, localizeErrorMessage, probeStageLabel, protocolLabel, reasoningEffortLabel, thinkingModeLabel,
} from "../uiLabels";
import { useI18n, type TranslationKey, type TranslationParams } from "../i18n";

type Preset = { label: string; profile: ProviderProfileInput };
type LlmError = { key: TranslationKey; params?: TranslationParams } | { raw: string };

const PRESET_NAME_KEYS: Partial<Record<string, TranslationKey>> = {
  "自定义": "settings.customProviderName",
  Ollama: "settings.localOllamaName",
  vLLM: "settings.localVllmName",
};

const PRESET_LABEL_KEYS: Partial<Record<string, TranslationKey>> = {
  "自定义": "settings.custom",
};

function isLlmError(value: unknown): value is LlmError {
  return Boolean(value && typeof value === "object" && "key" in value && typeof value.key === "string");
}

function renderLlmError(error: LlmError | null, locale: "zh-CN" | "en-US", t: (key: TranslationKey, params?: TranslationParams) => string): string {
  if (!error) return "";
  if ("raw" in error) return localizeErrorMessage(error.raw, locale);
  const params = error.params
    ? { ...error.params, ...(typeof error.params.message === "string"
      ? { message: localizeErrorMessage(error.params.message, locale) } : {}) }
    : undefined;
  return t(error.key, params);
}

function toLlmError(cause: unknown): LlmError {
  return isLlmError(cause)
    ? cause
    : { raw: cause instanceof Error ? cause.message : String(cause) };
}

const baseProfile = (): ProviderProfileInput => ({
  name: "自定义供应商",
  protocol: "openai_chat",
  notes: "",
  website_url: "",
  base_url: "",
  model: "",
  selected: false,
  auth_mode: "bearer",
  auth_header_name: "Authorization",
  auth_prefix: "Bearer ",
  timeout_seconds: 60,
  max_retries: 2,
  max_output_tokens: 8192,
  temperature: null,
  reasoning_effort: "default",
  thinking_mode: "auto",
  model_discovery_path: "/models",
  extra_headers: [],
  extra_body: {},
});

const PRESETS: Preset[] = [
  { label: "OpenAI", profile: { ...baseProfile(), name: "OpenAI", website_url: "https://openai.com", base_url: "https://api.openai.com/v1", model: "gpt-4.1" } },
  { label: "Claude", profile: { ...baseProfile(), name: "Claude", protocol: "anthropic_messages", website_url: "https://www.anthropic.com", base_url: "https://api.anthropic.com", model: "claude-sonnet-4-6", auth_mode: "x_api_key", auth_header_name: "x-api-key", auth_prefix: "", model_discovery_path: "/v1/models" } },
  { label: "DeepSeek", profile: { ...baseProfile(), name: "DeepSeek", protocol: "deepseek_chat", website_url: "https://www.deepseek.com", base_url: "https://api.deepseek.com/v1", model: "deepseek-v4-flash" } },
  { label: "OpenRouter", profile: { ...baseProfile(), name: "OpenRouter", website_url: "https://openrouter.ai", base_url: "https://openrouter.ai/api/v1", model: "openai/gpt-4.1" } },
  { label: "Ollama", profile: { ...baseProfile(), name: "本地 Ollama", website_url: "https://ollama.com", base_url: "http://localhost:11434/v1", model: "llama3.1", auth_mode: "none", auth_prefix: "" } },
  { label: "vLLM", profile: { ...baseProfile(), name: "本地 vLLM", website_url: "https://docs.vllm.ai", base_url: "http://localhost:8001/v1", model: "", auth_mode: "none", auth_prefix: "" } },
  { label: "自定义", profile: baseProfile() },
];

const RESERVED_BODY_KEYS = new Set([
  "model", "messages", "tools", "tool_choice", "response_format",
  "max_tokens", "max_completion_tokens", "stream",
]);

const groupModels = (models: string[]) => models.reduce<Record<string, string[]>>((groups, model) => {
  const namespace = model.includes("/") ? model.split("/", 1)[0] :
    model.startsWith("claude") ? "Anthropic" :
    /^(gpt|o\d)/.test(model) ? "OpenAI" :
    model.startsWith("deepseek") ? "DeepSeek" : "其他 / 本地";
  (groups[namespace] ||= []).push(model);
  return groups;
}, {});

const asInput = (profile: ProviderProfile): ProviderProfileInput => ({
  name: profile.name,
  protocol: profile.protocol,
  notes: profile.notes,
  website_url: profile.website_url,
  base_url: profile.base_url,
  model: profile.model,
  selected: profile.selected,
  auth_mode: profile.auth_mode,
  auth_header_name: profile.auth_header_name,
  auth_prefix: profile.auth_prefix,
  timeout_seconds: profile.timeout_seconds,
  max_retries: profile.max_retries,
  max_output_tokens: profile.max_output_tokens,
  temperature: profile.temperature,
  reasoning_effort: profile.reasoning_effort,
  thinking_mode: profile.thinking_mode,
  model_discovery_path: profile.model_discovery_path,
  extra_headers: profile.extra_headers.map(header => ({ ...header, value: header.sensitive ? "" : header.value })),
  extra_body: profile.extra_body,
});

interface Props {
  open: boolean;
  profiles: ProviderProfile[];
  isStreaming: boolean;
  onClose: () => void;
  onRefresh: () => Promise<ProviderProfile[]>;
  onConnected: (profile: ProviderProfile) => void;
}

export function LLMAdvancedSettings({
  open, profiles, isStreaming, onClose, onRefresh, onConnected,
}: Props) {
  const { locale, t } = useI18n();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProviderProfileInput>(baseProfile());
  const [baseline, setBaseline] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [sensitiveHeaders, setSensitiveHeaders] = useState<Record<string, string>>({});
  const [extraBodyText, setExtraBodyText] = useState("{}");
  const [jsonError, setJsonError] = useState<LlmError | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState<"save" | "probe" | "activate" | "models" | null>(null);
  const [error, setError] = useState<LlmError | null>(null);
  const [probe, setProbe] = useState<ProviderProbeResult | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [mobileEditor, setMobileEditor] = useState(false);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== baseline,
    [draft, baseline],
  );
  const groupedModels = useMemo(() => groupModels(models), [models]);
  const presetLabel = (preset: Preset) => {
    const key = PRESET_LABEL_KEYS[preset.label];
    return key ? t(key) : preset.label;
  };
  const presetProfile = (preset: Preset): ProviderProfileInput => {
    const key = PRESET_NAME_KEYS[preset.label];
    return key ? { ...preset.profile, name: t(key) } : preset.profile;
  };

  const loadDraft = (profile?: ProviderProfile, preset?: ProviderProfileInput) => {
    const value = profile ? asInput(profile) : { ...(preset || baseProfile()), extra_headers: [...(preset?.extra_headers || [])], extra_body: { ...(preset?.extra_body || {}) } };
    setEditingId(profile?.id || null);
    setDraft(value);
    setBaseline(profile ? JSON.stringify(value) : "");
    setExtraBodyText(JSON.stringify(value.extra_body, null, 2));
    setApiKey("");
    setSensitiveHeaders({});
    setProbe(null);
    setModels([]);
    setError(null);
    setJsonError(null);
    setMobileEditor(true);
  };

  useEffect(() => {
    if (!open) return;
    const current = profiles.find(profile => profile.selected) || profiles[0];
    if (current) loadDraft(current);
    else loadDraft(undefined, presetProfile(PRESETS[0]));
    // Opening the modal intentionally resets secret inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const credentials = (): ProviderCredentials => ({ api_key: apiKey, sensitive_headers: sensitiveHeaders });

  const confirmDiscard = () => !dirty || window.confirm(t("settings.discardConfirm"));

  const selectProfile = (profile: ProviderProfile) => {
    if (isStreaming) return;
    if (!confirmDiscard()) return;
    loadDraft(profile);
  };

  const selectPreset = (preset: Preset) => {
    if (isStreaming) return;
    if (!confirmDiscard()) return;
    loadDraft(undefined, presetProfile(preset));
  };

  const parseExtraBody = (text: string) => {
    setExtraBodyText(text);
    try {
      const parsed = JSON.parse(text);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        setJsonError({ key: "settings.extraBodyInvalid" });
        return;
      }
      const conflicts = Object.keys(parsed).filter(key => RESERVED_BODY_KEYS.has(key));
      if (conflicts.length) {
        setJsonError({ key: "settings.jsonReserved", params: { keys: conflicts.join(", ") } });
        return;
      }
      setJsonError(null);
      setDraft(current => ({ ...current, extra_body: parsed }));
    } catch (cause) {
      setJsonError({ raw: (cause as Error).message });
    }
  };

  const save = async (): Promise<ProviderProfile> => {
    if (jsonError) throw { key: "settings.extraBodyFix" } satisfies LlmError;
    if (!draft.name.trim()) {
      throw { key: "settings.nameRequired" } satisfies LlmError;
    }
    setBusy("save");
    try {
      const saved = editingId
        ? await updateProviderProfile(editingId, draft)
        : await createProviderProfile(draft);
      setEditingId(saved.id);
      const value = asInput(saved);
      setDraft(value);
      setBaseline(JSON.stringify(value));
      await onRefresh();
      return saved;
    } finally {
      setBusy(null);
    }
  };

  const withSaved = async (action: "probe" | "activate" | "models") => {
    setError(null);
    setProbe(null);
    try {
      if (!draft.base_url.trim()) throw { key: "settings.addressRequired" } satisfies LlmError;
      if (action !== "models" && !draft.model.trim()) throw { key: "settings.modelRequired" } satisfies LlmError;
      if (
        action !== "models" && draft.auth_mode !== "none" && !apiKey &&
        !currentStored?.credential_loaded
      ) throw { key: "settings.keyRequired" } satisfies LlmError;
      const saved = dirty || !editingId ? await save() : profiles.find(item => item.id === editingId)!;
      setBusy(action);
      if (action === "models") {
        const result = await discoverProviderModels(saved.id, credentials());
        setModels(result.models);
      } else if (action === "probe") {
        setProbe(await probeProviderProfile(saved.id, credentials()));
      } else {
        const result = await activateProviderProfile(saved.id, credentials());
        setProbe(result);
        const refreshed = await onRefresh();
        const connected = refreshed.find(item => item.id === saved.id) || result.profile || saved;
        onConnected(connected);
        setBaseline(JSON.stringify(asInput(connected)));
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.detail?.stages && action !== "models") {
        setProbe({
          status: "failed", stages: cause.detail.stages,
          error_category: cause.detail.category, message: cause.message,
        });
      }
      setError(toLlmError(cause));
      await onRefresh().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  };

  const close = () => {
    if (!confirmDiscard()) return;
    onClose();
  };

  const remove = async () => {
    if (!editingId) return;
    const current = profiles.find(item => item.id === editingId);
    if (!current || !window.confirm(t("settings.deleteConfirm", { name: current.name }))) return;
    setError(null);
    try {
      await deleteProviderProfile(editingId);
      const refreshed = await onRefresh();
      if (refreshed[0]) loadDraft(refreshed[0]);
      else loadDraft(undefined, presetProfile(PRESETS[0]));
    } catch (cause) {
      setError(toLlmError(cause));
    }
  };

  const duplicate = async () => {
    setError(null);
    try {
      const copied = await createProviderProfile({ ...draft, name: `${draft.name} ${t("settings.copySuffix")}`, selected: false });
      await onRefresh();
      loadDraft(copied);
    } catch (cause) {
      setError(toLlmError(cause));
    }
  };

  const setField = <K extends keyof ProviderProfileInput>(key: K, value: ProviderProfileInput[K]) => {
    setDraft(current => ({ ...current, [key]: value }));
    setProbe(null);
  };

  const currentStored = profiles.find(profile => profile.id === editingId);

  return (
    <div className="fixed inset-0 z-[100] bg-slate-950/35 backdrop-blur-sm flex items-center justify-center p-0 lg:p-6" role="dialog" aria-modal="true" aria-label={t("settings.advancedTitle")}>
      <div className="w-full h-full lg:h-[min(900px,94vh)] lg:max-w-[1240px] bg-white lg:rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <header className="h-16 px-5 border-b border-slate-200 flex items-center justify-between shrink-0">
          <div>
            <h2 className="font-bold text-slate-900">{t("settings.advancedTitle")}</h2>
            <p className="text-xs text-slate-500">{t("settings.advancedSubtitle")}</p>
          </div>
          <button onClick={close} className="p-2 rounded-lg hover:bg-slate-100" aria-label={t("settings.closeAdvanced")}><X className="w-5 h-5" /></button>
        </header>

        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[300px_1fr]">
          <aside className={`${mobileEditor ? "hidden lg:flex" : "flex"} min-h-0 border-r border-slate-200 bg-slate-50 flex-col`}>
            <div className="p-4 border-b border-slate-200">
              <div className="text-xs font-semibold text-slate-500 mb-2">{t("settings.addPreset")}</div>
              <div className="flex flex-wrap gap-1.5">
                {PRESETS.map(preset => <button key={preset.label} onClick={() => selectPreset(preset)} disabled={isStreaming} className="px-2 py-1 text-xs bg-white border border-slate-200 rounded-md hover:border-blue-300 hover:text-blue-700 disabled:opacity-50">{presetLabel(preset)}</button>)}
              </div>
            </div>
            <div className="p-3 overflow-y-auto space-y-2 flex-1">
              {profiles.map(profile => (
                <button key={profile.id} onClick={() => selectProfile(profile)} disabled={isStreaming} className={`w-full text-left p-3 rounded-xl border disabled:opacity-60 ${editingId === profile.id ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white hover:border-slate-300"}`}>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-slate-800 truncate flex-1">{profile.name}</span>
                    {profile.connected && <span className="w-2 h-2 rounded-full bg-emerald-500" title={t("settings.connectedTitle")} />}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 truncate">{protocolLabel(profile.protocol, locale)} · {profile.model || t("settings.unspecifiedModel")}</div>
                  <div className={`text-[10px] mt-1 ${profile.connected ? "text-emerald-600" : profile.probe_status === "failed" ? "text-rose-600" : profile.credential_loaded ? "text-amber-600" : "text-slate-400"}`}>
                    {profile.connected ? t("settings.connectedTitle") : profile.needs_reconnect ? t("settings.needsReconnect") : profile.probe_status === "failed" ? `${t("settings.probeFailed")}${profile.probe_error_category ? ` · ${errorCategoryLabel(profile.probe_error_category, locale)}` : ""}` : profile.auth_mode === "none" ? t("settings.noAuthNotConnected") : profile.credential_loaded ? t("settings.credentialLoadedNotConnected") : t("settings.awaitCredential")}
                  </div>
                </button>
              ))}
              {!profiles.length && <div className="text-sm text-slate-500 text-center py-8">{t("settings.noProfiles")}<br />{t("settings.startPreset")}</div>}
            </div>
          </aside>

          <section className={`${mobileEditor ? "flex" : "hidden lg:flex"} min-h-0 flex-col`}>
            <div className="lg:hidden px-4 py-2 border-b border-slate-200"><button onClick={() => { if (confirmDiscard()) setMobileEditor(false); }} className="text-sm text-slate-600 flex items-center gap-1"><ArrowLeft className="w-4 h-4" />{t("settings.providerList")}</button></div>
            <div className="flex-1 overflow-y-auto p-4 md:p-6">
              {error && <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-sm flex gap-2"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />{renderLlmError(error, locale, t)}</div>}
              <div className="max-w-[820px] mx-auto space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-slate-800 mb-3">{t("settings.basicInfo")}</h3>
                  <div className="grid lg:grid-cols-2 gap-4">
                    <label className="field-label">{t("settings.providerName")}<input value={draft.name} onChange={e => setField("name", e.target.value)} className="field-input" /></label>
                    <label className="field-label">{t("settings.protocol")}<select value={draft.protocol} onChange={e => { const value = e.target.value as ProviderProtocol; setField("protocol", value); if (value !== "deepseek_chat") setField("thinking_mode", "auto"); }} className="field-input"><option value="openai_chat">{t("settings.protocolOpenAI")}</option><option value="anthropic_messages">{t("settings.protocolAnthropic")}</option><option value="deepseek_chat">{t("settings.protocolDeepSeek")}</option></select><span className="field-help">{t("settings.protocolHelp")}</span></label>
                    <label className="field-label">{t("settings.website")}<input value={draft.website_url} onChange={e => setField("website_url", e.target.value)} placeholder="https://example.com" className="field-input" /></label>
                    <label className="field-label lg:col-span-2">{t("settings.notes")}<textarea value={draft.notes} onChange={e => setField("notes", e.target.value)} rows={2} className="field-input resize-y" placeholder={t("settings.notesPlaceholder")} /></label>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-bold text-slate-800 mb-3">{t("settings.connection")}</h3>
                  <div className="grid lg:grid-cols-2 gap-4">
                    <label className="field-label lg:col-span-2">{t("settings.requestUrl")}<input value={draft.base_url} onChange={e => setField("base_url", e.target.value)} placeholder="https://api.example.com/v1" className="field-input font-mono" /><span className="field-help">{t("settings.requestUrlHelp")}</span></label>
                    <label className="field-label">{t("settings.authMode")}<select value={draft.auth_mode} onChange={e => setField("auth_mode", e.target.value as ProviderProfileInput["auth_mode"])} className="field-input"><option value="bearer">{authModeLabel("bearer", locale)}</option><option value="x_api_key">{authModeLabel("x_api_key", locale)}</option><option value="custom_header">{authModeLabel("custom_header", locale)}</option><option value="none">{authModeLabel("none", locale)}</option></select><span className="field-help">{t("settings.authHelp")}</span></label>
                    {draft.auth_mode !== "none" && <label className="field-label">{t("settings.apiKey")}<div className="relative"><input aria-label={t("settings.apiKey")} type={showKey ? "text" : "password"} value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={currentStored?.credential_loaded ? t("settings.loadedKeyPlaceholder") : t("settings.enterKeyPlaceholder")} className="field-input pr-10" autoComplete="off" /><button type="button" onClick={() => setShowKey(v => !v)} aria-label={showKey ? t("settings.hideApiKey") : t("settings.showApiKey")} className="absolute right-2 top-2.5 text-slate-400">{showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div><span className="field-help">{t("settings.apiKeyHelp")}</span></label>}
                    {draft.auth_mode !== "none" && <><label className="field-label">{t("settings.authHeader")}<input value={draft.auth_header_name} onChange={e => setField("auth_header_name", e.target.value)} className="field-input" /><span className="field-help">{t("settings.authHeaderHelp")}</span></label><label className="field-label">{t("settings.prefix")}<input value={draft.auth_prefix} onChange={e => setField("auth_prefix", e.target.value)} className="field-input" /><span className="field-help">{t("settings.prefixHelp")}</span></label></>}
                    <label className="field-label">{t("settings.modelId")}<div className="flex min-w-0 gap-2"><input list="provider-model-list" value={draft.model} onChange={e => setField("model", e.target.value)} className="field-input min-w-0" /><button type="button" onClick={() => withSaved("models")} disabled={Boolean(busy)} className="secondary-button shrink-0">{busy === "models" ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}{t("settings.discoverModels")}</button></div><datalist id="provider-model-list">{models.map(model => <option key={model} value={model} />)}</datalist>{models.length > 0 ? <select aria-label={t("settings.discoveredModels")} value={models.includes(draft.model) ? draft.model : ""} onChange={e => { if (e.target.value) setField("model", e.target.value); }} className="field-input"><option value="">{t("settings.chooseDiscovered")}</option>{Object.entries(groupedModels).map(([group, entries]) => <optgroup key={group} label={group === "其他 / 本地" ? t("settings.otherLocal") : group}>{entries.map(model => <option key={model} value={model}>{model}</option>)}</optgroup>)}</select> : null}<span className="field-help">{t("settings.modelIdHelp")}</span>{models.length > 0 && <span className="field-help">{t("settings.discoveredCount", { count: models.length })}</span>}</label>
                    <label className="field-label">{t("settings.modelPath")}<input value={draft.model_discovery_path} onChange={e => setField("model_discovery_path", e.target.value)} className="field-input font-mono" /><span className="field-help">{t("settings.modelPathHelp")}</span></label>
                  </div>
                </div>

                <div>
                  <button type="button" onClick={() => setAdvanced(value => !value)} className="w-full flex items-center justify-between py-2 text-sm font-bold text-slate-800 border-b border-slate-200">{t("settings.expert")}{advanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}</button>
                  {advanced && <div className="pt-4 space-y-5">
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      <label className="field-label">{t("settings.timeout")}<input type="number" min={5} max={300} value={draft.timeout_seconds} onChange={e => setField("timeout_seconds", Number(e.target.value))} className="field-input" /><span className="field-help">{t("settings.timeoutHelp")}</span></label>
                      <label className="field-label">{t("settings.retries")}<input type="number" min={0} max={5} value={draft.max_retries} onChange={e => setField("max_retries", Number(e.target.value))} className="field-input" /></label>
                      <label className="field-label">{t("settings.maxOutput")}<input type="number" min={256} max={32768} value={draft.max_output_tokens} onChange={e => setField("max_output_tokens", Number(e.target.value))} className="field-input" /><span className="field-help">{t("settings.maxOutputHelp")}</span></label>
                      <label className="field-label">{t("settings.temperature")}<input type="number" min={0} max={2} step={0.1} value={draft.temperature ?? ""} onChange={e => setField("temperature", e.target.value === "" ? null : Number(e.target.value))} className="field-input" /><span className="field-help">{t("settings.temperatureHelp")}</span></label>
                      <label className="field-label">{t("settings.reasoning")}<select value={draft.reasoning_effort} onChange={e => setField("reasoning_effort", e.target.value as ProviderProfileInput["reasoning_effort"])} className="field-input"><option value="default">{t("settings.serviceDefault")}</option><option value="low">{reasoningEffortLabel("low", locale)}</option><option value="medium">{reasoningEffortLabel("medium", locale)}</option><option value="high">{reasoningEffortLabel("high", locale)}</option><option value="max">{reasoningEffortLabel("max", locale)}</option></select><span className="field-help">{t("settings.reasoningHelp")}</span></label>
                      {draft.protocol === "deepseek_chat" && <label className="field-label">{t("settings.thinkingMode")}<select value={draft.thinking_mode} onChange={e => setField("thinking_mode", e.target.value as ProviderProfileInput["thinking_mode"])} className="field-input"><option value="auto">{thinkingModeLabel("auto", locale)}</option><option value="enabled">{thinkingModeLabel("enabled", locale)}</option><option value="disabled">{thinkingModeLabel("disabled", locale)}</option></select><span className="field-help">{t("settings.thinkingHelp")}</span></label>}
                    </div>

                    <div>
                      <div className="flex flex-wrap justify-between items-center gap-2 mb-2"><span className="text-xs font-semibold text-slate-600">{t("settings.extraHeaders")}</span><button type="button" onClick={() => setField("extra_headers", [...draft.extra_headers, { name: "", value: "", sensitive: false }])} className="secondary-button"><Plus className="w-3 h-3" />{t("settings.addHeader")}</button></div>
                      <p className="field-help mb-2">{t("settings.extraHeadersHelp")}</p>
                      <div className="space-y-2">{draft.extra_headers.map((header, index) => <div key={index} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-2 items-center"><input aria-label={t("settings.extraHeaderName") + ` ${index + 1}`} value={header.name} onChange={e => { const oldName = header.name; const newName = e.target.value; const next = [...draft.extra_headers]; next[index] = { ...header, name: newName }; if (header.sensitive && sensitiveHeaders[oldName]) setSensitiveHeaders(values => { const updated = { ...values, [newName]: values[oldName] }; delete updated[oldName]; return updated; }); setField("extra_headers", next); }} placeholder={t("settings.extraHeaderName")} className="field-input font-mono" /><input aria-label={t("settings.extraHeaderValue") + ` ${index + 1}`} type={header.sensitive ? "password" : "text"} value={header.sensitive ? (sensitiveHeaders[header.name] || "") : header.value} onChange={e => header.sensitive ? setSensitiveHeaders(values => ({ ...values, [header.name]: e.target.value })) : (() => { const next = [...draft.extra_headers]; next[index] = { ...header, value: e.target.value }; setField("extra_headers", next); })()} placeholder={header.sensitive && header.credential_loaded ? t("settings.loaded") : t("settings.extraHeaderValue")} className="field-input" /><label className="text-xs text-slate-600 flex items-center gap-1"><input type="checkbox" checked={header.sensitive} onChange={e => { const next = [...draft.extra_headers]; next[index] = { ...header, sensitive: e.target.checked, value: e.target.checked ? "" : header.value }; setField("extra_headers", next); }} />{t("settings.sensitive")}</label><button type="button" onClick={() => setField("extra_headers", draft.extra_headers.filter((_, i) => i !== index))} aria-label={t("settings.deleteExtraHeader", { index: index + 1 })} className="p-2 text-rose-500"><Trash2 className="w-4 h-4" /></button></div>)}</div>
                    </div>

                    <div>
                      <div className="flex flex-wrap justify-between items-center gap-2 mb-2"><span className="text-xs font-semibold text-slate-600">{t("settings.extraBody")}</span><div className="flex gap-2"><button type="button" onClick={() => parseExtraBody("{}") } className="secondary-button">{t("settings.restoreDefault")}</button><button type="button" onClick={() => { try { const formatted = JSON.stringify(JSON.parse(extraBodyText), null, 2); parseExtraBody(formatted); } catch { /* existing error remains visible */ } }} className="secondary-button">{t("settings.format")}</button></div></div>
                      <textarea value={extraBodyText} onChange={e => parseExtraBody(e.target.value)} rows={7} spellCheck={false} className={`field-input font-mono text-xs ${jsonError ? "border-rose-400" : ""}`} />
                      {jsonError ? <p className="text-xs text-rose-600 mt-1">{renderLlmError(jsonError, locale, t)}</p> : <p className="field-help">{t("settings.extraBodyHelp")}</p>}
                    </div>
                  </div>}
                </div>

                {probe && <div className={`p-4 rounded-xl border ${probe.status === "failed" ? "border-rose-200 bg-rose-50" : "border-emerald-200 bg-emerald-50"}`}><div className={`font-semibold text-sm mb-2 ${probe.status === "failed" ? "text-rose-800" : "text-emerald-800"}`}>{probe.status === "failed" ? `${t("settings.probeFail")}${probe.error_category ? ` · ${errorCategoryLabel(probe.error_category, locale)}` : ""}` : `${t("settings.probePass")}${probe.latency_ms ? ` · ${t("settings.probeLatency", { latency: probe.latency_ms })}` : ""}`}</div><div className="grid sm:grid-cols-2 gap-2">{Object.entries(probe.stages || {}).map(([name, result]) => <div key={name} className={`text-xs flex justify-between bg-white/70 rounded px-2 py-1 ${result.status === "passed" ? "text-emerald-700" : "text-rose-700"}`}><span>{probeStageLabel(name, locale)}</span><span>{result.status === "passed" ? t("settings.passed") : t("settings.failed")}{result.latency_ms ? ` · ${t("settings.probeLatency", { latency: result.latency_ms })}` : ""}</span></div>)}</div></div>}
              </div>
            </div>

            <footer className="border-t border-slate-200 p-3 md:px-6 bg-white flex flex-wrap items-center gap-2 shrink-0">
              <button onClick={remove} disabled={!editingId || isStreaming || Boolean(currentStored?.connected)} className="secondary-button text-rose-600 disabled:opacity-40" title={currentStored?.connected ? t("settings.disconnectFirst") : t("settings.deleteProfile")}><Trash2 className="w-4 h-4" />{t("settings.deleteProfile")}</button>
              <button onClick={duplicate} disabled={Boolean(busy)} className="secondary-button"><Copy className="w-4 h-4" />{t("settings.copy")}</button>
              <div className="flex-1" />
              {dirty && <span className="text-xs text-amber-600">{t("settings.unsaved")}</span>}
              <button onClick={() => save().catch(cause => setError(toLlmError(cause)))} disabled={Boolean(busy) || isStreaming} className="secondary-button">{busy === "save" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}{t("settings.save")}</button>
              <button onClick={() => withSaved("probe")} disabled={Boolean(busy) || isStreaming} className="secondary-button"><TestTube2 className="w-4 h-4" />{t("settings.testConnection")}</button>
              <button onClick={() => withSaved("activate")} disabled={Boolean(busy) || isStreaming} className="primary-button">{busy === "activate" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}{t("settings.saveConnect")}</button>
            </footer>
          </section>
        </div>
      </div>
    </div>
  );
}
