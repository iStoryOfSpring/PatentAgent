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

type Preset = { label: string; profile: ProviderProfileInput };

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

const protocolLabel = (protocol: ProviderProtocol) => ({
  openai_chat: "OpenAI Chat",
  anthropic_messages: "Anthropic Messages",
  deepseek_chat: "DeepSeek Chat",
}[protocol]);

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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProviderProfileInput>(baseProfile());
  const [baseline, setBaseline] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [sensitiveHeaders, setSensitiveHeaders] = useState<Record<string, string>>({});
  const [extraBodyText, setExtraBodyText] = useState("{}");
  const [jsonError, setJsonError] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState<"save" | "probe" | "activate" | "models" | null>(null);
  const [error, setError] = useState("");
  const [probe, setProbe] = useState<ProviderProbeResult | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [mobileEditor, setMobileEditor] = useState(false);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== baseline,
    [draft, baseline],
  );
  const groupedModels = useMemo(() => groupModels(models), [models]);

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
    setError("");
    setJsonError("");
    setMobileEditor(true);
  };

  useEffect(() => {
    if (!open) return;
    const current = profiles.find(profile => profile.selected) || profiles[0];
    if (current) loadDraft(current);
    else loadDraft(undefined, PRESETS[0].profile);
    // Opening the modal intentionally resets secret inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const credentials = (): ProviderCredentials => ({ api_key: apiKey, sensitive_headers: sensitiveHeaders });

  const confirmDiscard = () => !dirty || window.confirm("当前配置有未保存修改，确认放弃吗？");

  const selectProfile = (profile: ProviderProfile) => {
    if (isStreaming) return;
    if (!confirmDiscard()) return;
    loadDraft(profile);
  };

  const selectPreset = (preset: Preset) => {
    if (isStreaming) return;
    if (!confirmDiscard()) return;
    loadDraft(undefined, preset.profile);
  };

  const parseExtraBody = (text: string) => {
    setExtraBodyText(text);
    try {
      const parsed = JSON.parse(text);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("必须是 JSON 对象");
      const conflicts = Object.keys(parsed).filter(key => RESERVED_BODY_KEYS.has(key));
      if (conflicts.length) throw new Error("保留字段不能覆盖: " + conflicts.join(", "));
      setJsonError("");
      setDraft(current => ({ ...current, extra_body: parsed }));
    } catch (cause) {
      setJsonError((cause as Error).message);
    }
  };

  const save = async (): Promise<ProviderProfile> => {
    if (jsonError) throw new Error("请先修复 Extra Body JSON")
    if (!draft.name.trim()) {
      throw new Error("供应商名称不能为空");
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
    setError("");
    setProbe(null);
    try {
      if (!draft.base_url.trim()) throw new Error("获取模型或连接前必须填写请求地址");
      if (action !== "models" && !draft.model.trim()) throw new Error("测试或连接前必须填写模型 ID");
      if (
        action !== "models" && draft.auth_mode !== "none" && !apiKey &&
        !currentStored?.credential_loaded
      ) throw new Error("当前配置需要 API Key");
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
      setError((cause as Error).message);
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
    if (!current || !window.confirm(`确认删除供应商“${current.name}”？`)) return;
    setError("");
    try {
      await deleteProviderProfile(editingId);
      const refreshed = await onRefresh();
      if (refreshed[0]) loadDraft(refreshed[0]);
      else loadDraft(undefined, PRESETS[0].profile);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };

  const duplicate = async () => {
    setError("");
    try {
      const copied = await createProviderProfile({ ...draft, name: `${draft.name} 副本`, selected: false });
      await onRefresh();
      loadDraft(copied);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };

  const setField = <K extends keyof ProviderProfileInput>(key: K, value: ProviderProfileInput[K]) => {
    setDraft(current => ({ ...current, [key]: value }));
    setProbe(null);
  };

  const currentStored = profiles.find(profile => profile.id === editingId);

  return (
    <div className="fixed inset-0 z-[100] bg-slate-950/35 backdrop-blur-sm flex items-center justify-center p-0 lg:p-6" role="dialog" aria-modal="true" aria-label="LLM 高级设置">
      <div className="w-full h-full lg:h-[min(900px,94vh)] lg:max-w-[1240px] bg-white lg:rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <header className="h-16 px-5 border-b border-slate-200 flex items-center justify-between shrink-0">
          <div>
            <h2 className="font-bold text-slate-900">LLM 高级设置</h2>
            <p className="text-xs text-slate-500">多供应商配置 · 凭证仅保存在后端内存</p>
          </div>
          <button onClick={close} className="p-2 rounded-lg hover:bg-slate-100" aria-label="关闭高级设置"><X className="w-5 h-5" /></button>
        </header>

        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[300px_1fr]">
          <aside className={`${mobileEditor ? "hidden lg:flex" : "flex"} min-h-0 border-r border-slate-200 bg-slate-50 flex-col`}>
            <div className="p-4 border-b border-slate-200">
              <div className="text-xs font-semibold text-slate-500 mb-2">从预设新增</div>
              <div className="flex flex-wrap gap-1.5">
                {PRESETS.map(preset => <button key={preset.label} onClick={() => selectPreset(preset)} disabled={isStreaming} className="px-2 py-1 text-xs bg-white border border-slate-200 rounded-md hover:border-blue-300 hover:text-blue-700 disabled:opacity-50">{preset.label}</button>)}
              </div>
            </div>
            <div className="p-3 overflow-y-auto space-y-2 flex-1">
              {profiles.map(profile => (
                <button key={profile.id} onClick={() => selectProfile(profile)} disabled={isStreaming} className={`w-full text-left p-3 rounded-xl border disabled:opacity-60 ${editingId === profile.id ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white hover:border-slate-300"}`}>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-slate-800 truncate flex-1">{profile.name}</span>
                    {profile.connected && <span className="w-2 h-2 rounded-full bg-emerald-500" title="已连接" />}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 truncate">{protocolLabel(profile.protocol)} · {profile.model || "未指定模型"}</div>
                  <div className={`text-[10px] mt-1 ${profile.connected ? "text-emerald-600" : profile.probe_status === "failed" ? "text-rose-600" : profile.credential_loaded ? "text-amber-600" : "text-slate-400"}`}>
                    {profile.connected ? "已连接" : profile.needs_reconnect ? "配置已修改，需要重新连接" : profile.probe_status === "failed" ? `探测失败${profile.probe_error_category ? ` · ${profile.probe_error_category}` : ""}` : profile.auth_mode === "none" ? "无需凭证，尚未连接" : profile.credential_loaded ? "凭证已载入，尚未连接" : "待输入凭证"}
                  </div>
                </button>
              ))}
              {!profiles.length && <div className="text-sm text-slate-500 text-center py-8">尚无已保存配置<br />请从上方预设开始</div>}
            </div>
          </aside>

          <section className={`${mobileEditor ? "flex" : "hidden lg:flex"} min-h-0 flex-col`}>
            <div className="lg:hidden px-4 py-2 border-b border-slate-200"><button onClick={() => { if (confirmDiscard()) setMobileEditor(false); }} className="text-sm text-slate-600 flex items-center gap-1"><ArrowLeft className="w-4 h-4" />供应商列表</button></div>
            <div className="flex-1 overflow-y-auto p-4 md:p-6">
              {error && <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-sm flex gap-2"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />{error}</div>}
              <div className="max-w-[820px] mx-auto space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-slate-800 mb-3">基础信息</h3>
                  <div className="grid lg:grid-cols-2 gap-4">
                    <label className="field-label">供应商名称<input value={draft.name} onChange={e => setField("name", e.target.value)} className="field-input" /></label>
                    <label className="field-label">API 协议<select value={draft.protocol} onChange={e => { const value = e.target.value as ProviderProtocol; setField("protocol", value); if (value !== "deepseek_chat") setField("thinking_mode", "auto"); }} className="field-input"><option value="openai_chat">OpenAI Chat Compatible</option><option value="anthropic_messages">Anthropic Messages</option><option value="deepseek_chat">DeepSeek Chat</option></select></label>
                    <label className="field-label">官网地址<input value={draft.website_url} onChange={e => setField("website_url", e.target.value)} placeholder="https://example.com" className="field-input" /></label>
                    <label className="field-label lg:col-span-2">备注<textarea value={draft.notes} onChange={e => setField("notes", e.target.value)} rows={2} className="field-input resize-y" placeholder="用途、账号或模型能力说明" /></label>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-bold text-slate-800 mb-3">连接配置</h3>
                  <div className="grid lg:grid-cols-2 gap-4">
                    <label className="field-label lg:col-span-2">请求地址<input value={draft.base_url} onChange={e => setField("base_url", e.target.value)} placeholder="https://api.example.com/v1" className="field-input font-mono" /><span className="field-help">远程地址必须使用 HTTPS；localhost 可使用 HTTP。</span></label>
                    <label className="field-label">鉴权方式<select value={draft.auth_mode} onChange={e => setField("auth_mode", e.target.value as ProviderProfileInput["auth_mode"])} className="field-input"><option value="bearer">Bearer Token</option><option value="x_api_key">x-api-key</option><option value="custom_header">自定义 Header</option><option value="none">无鉴权</option></select></label>
                    {draft.auth_mode !== "none" && <label className="field-label">API Key<div className="relative"><input type={showKey ? "text" : "password"} value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={currentStored?.credential_loaded ? "已在内存中加载；留空继续使用" : "输入本次连接凭证"} className="field-input pr-10" autoComplete="off" /><button type="button" onClick={() => setShowKey(v => !v)} className="absolute right-2 top-2.5 text-slate-400">{showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div></label>}
                    {draft.auth_mode !== "none" && <><label className="field-label">鉴权 Header<input value={draft.auth_header_name} onChange={e => setField("auth_header_name", e.target.value)} className="field-input" /></label><label className="field-label">值前缀<input value={draft.auth_prefix} onChange={e => setField("auth_prefix", e.target.value)} className="field-input" /></label></>}
                    <label className="field-label">模型 ID<div className="flex gap-2"><input list="provider-model-list" value={draft.model} onChange={e => setField("model", e.target.value)} className="field-input min-w-0" /><button type="button" onClick={() => withSaved("models")} disabled={Boolean(busy)} className="secondary-button shrink-0">{busy === "models" ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}获取模型</button></div><datalist id="provider-model-list">{models.map(model => <option key={model} value={model} />)}</datalist>{models.length > 0 && <><select aria-label="已发现模型" value={models.includes(draft.model) ? draft.model : ""} onChange={e => e.target.value && setField("model", e.target.value)} className="field-input"><option value="">选择发现的模型（或继续手工输入）</option>{Object.entries(groupedModels).map(([group, entries]) => <optgroup key={group} label={group}>{entries.map(model => <option key={model} value={model}>{model}</option>)}</optgroup>)}</select><span className="field-help">已发现 {models.length} 个模型，按命名空间/模型族分组。</span></>}</label>
                    <label className="field-label">模型发现路径<input value={draft.model_discovery_path} onChange={e => setField("model_discovery_path", e.target.value)} className="field-input font-mono" /></label>
                  </div>
                </div>

                <div>
                  <button type="button" onClick={() => setAdvanced(value => !value)} className="w-full flex items-center justify-between py-2 text-sm font-bold text-slate-800 border-b border-slate-200">请求参数与专家配置{advanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}</button>
                  {advanced && <div className="pt-4 space-y-5">
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      <label className="field-label">超时（秒）<input type="number" min={5} max={300} value={draft.timeout_seconds} onChange={e => setField("timeout_seconds", Number(e.target.value))} className="field-input" /></label>
                      <label className="field-label">重试次数<input type="number" min={0} max={5} value={draft.max_retries} onChange={e => setField("max_retries", Number(e.target.value))} className="field-input" /></label>
                      <label className="field-label">最大输出 Token<input type="number" min={256} max={32768} value={draft.max_output_tokens} onChange={e => setField("max_output_tokens", Number(e.target.value))} className="field-input" /></label>
                      <label className="field-label">温度（留空为服务默认）<input type="number" min={0} max={2} step={0.1} value={draft.temperature ?? ""} onChange={e => setField("temperature", e.target.value === "" ? null : Number(e.target.value))} className="field-input" /></label>
                      <label className="field-label">推理强度<select value={draft.reasoning_effort} onChange={e => setField("reasoning_effort", e.target.value as ProviderProfileInput["reasoning_effort"])} className="field-input"><option value="default">服务默认</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="max">Max</option></select></label>
                      {draft.protocol === "deepseek_chat" && <label className="field-label">Thinking mode<select value={draft.thinking_mode} onChange={e => setField("thinking_mode", e.target.value as ProviderProfileInput["thinking_mode"])} className="field-input"><option value="auto">Auto</option><option value="enabled">Enabled</option><option value="disabled">Disabled</option></select></label>}
                    </div>

                    <div>
                      <div className="flex justify-between items-center mb-2"><span className="text-xs font-semibold text-slate-600">Extra Headers</span><button type="button" onClick={() => setField("extra_headers", [...draft.extra_headers, { name: "", value: "", sensitive: false }])} className="secondary-button"><Plus className="w-3 h-3" />添加</button></div>
                      <div className="space-y-2">{draft.extra_headers.map((header, index) => <div key={index} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-2 items-center"><input value={header.name} onChange={e => { const oldName = header.name; const newName = e.target.value; const next = [...draft.extra_headers]; next[index] = { ...header, name: newName }; if (header.sensitive && sensitiveHeaders[oldName]) setSensitiveHeaders(values => { const updated = { ...values, [newName]: values[oldName] }; delete updated[oldName]; return updated; }); setField("extra_headers", next); }} placeholder="Header name" className="field-input font-mono" /><input type={header.sensitive ? "password" : "text"} value={header.sensitive ? (sensitiveHeaders[header.name] || "") : header.value} onChange={e => header.sensitive ? setSensitiveHeaders(values => ({ ...values, [header.name]: e.target.value })) : (() => { const next = [...draft.extra_headers]; next[index] = { ...header, value: e.target.value }; setField("extra_headers", next); })()} placeholder={header.sensitive && header.credential_loaded ? "已加载" : "Value"} className="field-input" /><label className="text-xs text-slate-600 flex items-center gap-1"><input type="checkbox" checked={header.sensitive} onChange={e => { const next = [...draft.extra_headers]; next[index] = { ...header, sensitive: e.target.checked, value: e.target.checked ? "" : header.value }; setField("extra_headers", next); }} />敏感</label><button type="button" onClick={() => setField("extra_headers", draft.extra_headers.filter((_, i) => i !== index))} className="p-2 text-rose-500"><Trash2 className="w-4 h-4" /></button></div>)}</div>
                    </div>

                    <div>
                      <div className="flex justify-between items-center mb-2"><span className="text-xs font-semibold text-slate-600">Extra Body JSON</span><div className="flex gap-2"><button type="button" onClick={() => parseExtraBody("{}") } className="secondary-button">恢复默认</button><button type="button" onClick={() => { try { const formatted = JSON.stringify(JSON.parse(extraBodyText), null, 2); parseExtraBody(formatted); } catch { /* existing error remains visible */ } }} className="secondary-button">格式化</button></div></div>
                      <textarea value={extraBodyText} onChange={e => parseExtraBody(e.target.value)} rows={7} spellCheck={false} className={`field-input font-mono text-xs ${jsonError ? "border-rose-400" : ""}`} />
                      {jsonError ? <p className="text-xs text-rose-600 mt-1">{jsonError}</p> : <p className="field-help">编排器管理的 model、messages、tools、tool_choice、response_format 和 max_tokens 不可覆盖。</p>}
                    </div>
                  </div>}
                </div>

                {probe && <div className={`p-4 rounded-xl border ${probe.status === "failed" ? "border-rose-200 bg-rose-50" : "border-emerald-200 bg-emerald-50"}`}><div className={`font-semibold text-sm mb-2 ${probe.status === "failed" ? "text-rose-800" : "text-emerald-800"}`}>{probe.status === "failed" ? `能力探测失败${probe.error_category ? ` · ${probe.error_category}` : ""}` : `能力探测通过 ${probe.latency_ms ? `· ${probe.latency_ms}ms` : ""}`}</div><div className="grid sm:grid-cols-2 gap-2">{Object.entries(probe.stages || {}).map(([name, result]) => <div key={name} className={`text-xs flex justify-between bg-white/70 rounded px-2 py-1 ${result.status === "passed" ? "text-emerald-700" : "text-rose-700"}`}><span>{({ text: "普通文本", tool_selection: "工具选择", tool_result_roundtrip: "工具回传", structured_output: "结构化输出" } as Record<string, string>)[name] || name}</span><span>{result.status === "passed" ? "通过" : "失败"}{result.latency_ms ? ` · ${result.latency_ms}ms` : ""}</span></div>)}</div></div>}
              </div>
            </div>

            <footer className="border-t border-slate-200 p-3 md:px-6 bg-white flex flex-wrap items-center gap-2 shrink-0">
              <button onClick={remove} disabled={!editingId || isStreaming || Boolean(currentStored?.connected)} className="secondary-button text-rose-600 disabled:opacity-40" title={currentStored?.connected ? "请先断开当前连接" : "删除配置"}><Trash2 className="w-4 h-4" />删除</button>
              <button onClick={duplicate} disabled={Boolean(busy)} className="secondary-button"><Copy className="w-4 h-4" />复制</button>
              <div className="flex-1" />
              {dirty && <span className="text-xs text-amber-600">有未保存修改</span>}
              <button onClick={() => save().catch(cause => setError((cause as Error).message))} disabled={Boolean(busy) || isStreaming} className="secondary-button">{busy === "save" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}保存</button>
              <button onClick={() => withSaved("probe")} disabled={Boolean(busy) || isStreaming} className="secondary-button"><TestTube2 className="w-4 h-4" />测试连接</button>
              <button onClick={() => withSaved("activate")} disabled={Boolean(busy) || isStreaming} className="primary-button">{busy === "activate" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}保存并连接</button>
            </footer>
          </section>
        </div>
      </div>
    </div>
  );
}
