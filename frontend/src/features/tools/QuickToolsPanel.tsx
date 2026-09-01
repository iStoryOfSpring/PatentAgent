import { useState } from "react";
import {
  Activity, Database, FolderSearch, Layers, Loader2, Map, Network,
  PieChart, TrendingUp, Zap,
} from "lucide-react";
import type { SearchCapabilityStatus, Tool } from "../../types";
import {
  enumLabel, parameterHelp, parameterLabel, toolLabel,
} from "../../uiLabels";

export const TOOL_META: Record<string, { label: string; icon: typeof Database }> = {
  get_dataset_summary: { label: "数据总览", icon: Database },
  analyze_patent_trend: { label: "公开趋势", icon: TrendingUp },
  analyze_lifecycle: { label: "增长趋势", icon: Activity },
  analyze_ipc_distribution: { label: "IPC 热力图", icon: Layers },
  generate_wordcloud: { label: "词云热点", icon: PieChart },
  analyze_burst_terms: { label: "近期增长词", icon: Zap },
  analyze_yearly_keywords: { label: "逐年关键词", icon: TrendingUp },
  analyze_country_distribution: { label: "主公开号首次公开局", icon: Map },
  analyze_co_network: { label: "合作网络", icon: Network },
  analyze_tech_roadmap: { label: "年度主题时间线", icon: Activity },
  analyze_tech_matrix: { label: "代理功效矩阵", icon: Layers },
  analyze_clustering: { label: "专利聚类", icon: Network },
  analyze_patent_valuation: { label: "价值筛查", icon: TrendingUp },
  analyze_competitor_evolution: { label: "竞对 IPC 演化", icon: Network },
  search_patents: { label: "相关专利检索", icon: FolderSearch },
  read_patent_details: { label: "专利深读", icon: FolderSearch },
  analyze_entity_portfolio: { label: "主体专利组合", icon: Database },
  analyze_concentration: { label: "竞争集中度", icon: PieChart },
  analyze_citation_network: { label: "专利引证网络", icon: Network },
  analyze_family_geography: { label: "专利族地域布局", icon: Map },
  audit_search_strategy: { label: "检索策略审计", icon: FolderSearch },
  analyze_legal_status: { label: "法律状态分析", icon: Activity },
  monitor_patent_changes: { label: "专利变更监测", icon: Activity },
  analyze_claim_elements: { label: "权利要求要素分析", icon: Layers },
};

interface QuickToolsPanelProps {
  tools: Tool[];
  isStreaming: boolean;
  loadingTool: string | null;
  searchStatus?: SearchCapabilityStatus;
  onRun: (toolName: string, params?: Record<string, unknown>) => void;
  className?: string;
}

export function QuickToolsPanel({ tools, isStreaming, loadingTool, searchStatus, onRun, className }: QuickToolsPanelProps) {
  const [selectedTool, setSelectedTool] = useState<string | null>("search_patents");
  const [toolParams, setToolParams] = useState<Record<string, string>>({});
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});

  return (
    <aside className={className || "hidden lg:flex w-[280px] bg-white border-l border-slate-200 overflow-y-auto flex-col shrink-0"}>
      <div className="p-5 sticky top-0 bg-white/80 backdrop-blur-md border-b border-slate-100 z-20">
        <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-500" /> 快捷工具
        </h2>
        <p className="text-xs text-slate-500 mt-1">{tools.length} 个工具 · 可直接运行单项分析</p>
        <p className="text-[10px] text-slate-400 mt-1">结果会保存到当前会话，便于回到聊天页继续分析。</p>
        <button
          type="button"
          onClick={() => setSelectedTool("search_patents")}
          className="mt-3 w-full rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-left"
        >
          <span className="block text-xs font-semibold text-indigo-800">MiniLM 多语言语义检索（测试版）</span>
          <span className="mt-0.5 block text-[10px] text-indigo-600">
            {!searchStatus?.dependency_installed
              ? "本地语义检索依赖未安装"
              : searchStatus.model_cached
                ? `模型已缓存 · ${searchStatus.index_count} 个数据集索引`
                : `运行依赖已就绪 · 首次使用下载约 ${searchStatus.download_size_mb} MB`}
          </span>
          <span className="mt-1 block text-[10px] text-indigo-500">词法匹配 + 本地语义模型融合排序；首次启用会缓存模型。</span>
        </button>
      </div>
      <div className="p-4 space-y-1">
        {tools.map(tool => {
          const meta = TOOL_META[tool.name] || { label: toolLabel(tool.name), icon: Zap };
          const Icon = meta.icon;
          const availability = tool.availability || { available: true, reason: "" };
          const hasParams = Object.keys(tool.parameters).length > 0;
          const expanded = selectedTool === tool.name;
          const requiredMissing = Object.entries(tool.parameters).some(
            ([name, schema]) => schema.required && !(toolParams[name] ?? "").trim(),
          );
          const hasParamErrors = Object.keys(paramErrors).some(name => name in tool.parameters && paramErrors[name]);
          return (
            <div key={tool.name} className="border-b border-slate-50 pb-1">
              <button
                onClick={() => hasParams ? setSelectedTool(expanded ? null : tool.name) : onRun(tool.name)}
                disabled={isStreaming || !availability.available}
                title={availability.reason || tool.description}
                className="w-full flex items-center gap-3 p-2.5 rounded-xl hover:bg-slate-50 text-slate-700 transition-all disabled:opacity-40 group"
              >
                <div className="w-7 h-7 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                  {loadingTool === tool.name ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
                </div>
                <span className="text-sm font-medium text-left flex-1">{meta.label}</span>
                {hasParams && <span className="text-slate-400 text-xs">{expanded ? "−" : "+"}</span>}
              </button>
              {!availability.available && availability.reason && (
                <p className="px-3 pb-2 text-[10px] text-amber-700">{availability.reason}</p>
              )}
              {expanded && (
                <div className="mx-2 mb-2 p-3 bg-slate-50 rounded-lg space-y-2">
                  {Object.entries(tool.parameters).map(([name, schema]) => (
                    <label key={name} className="block text-[11px] text-slate-600">
                      <span className="font-medium">{parameterLabel(name)}{schema.required ? " *" : ""}</span>
                      <span className="mt-0.5 block text-[10px] leading-4 text-slate-400">{parameterHelp(name, schema)}</span>
                      {name === "retrieval_mode" ? (
                        <span className="mt-1 flex items-start gap-2 rounded border border-indigo-100 bg-white p-2">
                          <input
                            type="checkbox"
                            checked={toolParams[name] === "multilingual_hybrid_beta"}
                            onChange={event => setToolParams(current => ({
                              ...current,
                              [name]: event.target.checked ? "multilingual_hybrid_beta" : "lexical",
                            }))}
                            className="mt-0.5"
                          />
                          <span>
                            <span className="font-medium text-indigo-700">多语言向量检索（测试版）</span>
                            <span className="block mt-0.5 text-[10px] text-slate-500">
                              首次启用会下载约 471 MB 的本地 MiniLM；失败时会回退到词法检索。
                            </span>
                          </span>
                        </span>
                      ) : schema.enum ? (
                        <select value={toolParams[name] || ""} onChange={event => setToolParams(current => ({ ...current, [name]: event.target.value }))}
                          className="mt-1 w-full p-1.5 border rounded bg-white">
                          <option value="">默认</option>
                          {schema.enum.map(value => <option key={value} value={value}>{enumLabel(value)}</option>)}
                        </select>
                      ) : schema.type === "boolean" ? (
                        <select
                          value={toolParams[name] ?? (schema.default === true ? "true" : schema.default === false ? "false" : "")}
                          onChange={event => setToolParams(current => ({ ...current, [name]: event.target.value }))}
                          className="mt-1 w-full p-1.5 border rounded bg-white"
                        >
                          <option value="">默认</option>
                          <option value="true">是</option>
                          <option value="false">否</option>
                        </select>
                      ) : schema.type === "object" || schema.items?.type === "object" ? (
                        <textarea
                          value={toolParams[name] || ""}
                          onChange={event => {
                            setToolParams(current => ({ ...current, [name]: event.target.value }));
                            setParamErrors(current => ({ ...current, [name]: "" }));
                          }}
                          placeholder={schema.items?.type === "object" ? "请输入 JSON 数组，例如 [{\"name\":\"示例\"}]" : "请输入 JSON 对象，例如 {\"year_start\":2020}"}
                          className="mt-1 min-h-16 w-full resize-y rounded border bg-white p-1.5 font-mono text-[11px]"
                        />
                      ) : (
                        <input value={toolParams[name] || ""} onChange={event => {
                          setToolParams(current => ({ ...current, [name]: event.target.value }));
                          setParamErrors(current => ({ ...current, [name]: "" }));
                        }}
                          placeholder={schema.type === "array" ? "多个值请用逗号或换行分隔" : "请输入参数值"} className="mt-1 w-full p-1.5 border rounded bg-white" />
                      )}
                      {paramErrors[name] && <span className="mt-1 block text-[10px] text-rose-600">{paramErrors[name]}</span>}
                    </label>
                  ))}
                  {loadingTool === tool.name && toolParams.retrieval_mode === "multilingual_hybrid_beta" && (
                    <div className="rounded border border-indigo-100 bg-white p-2" role="status">
                      <div className="mb-1 text-[10px] text-indigo-700">正在下载模型或构建数据集索引，请保持页面打开…</div>
                      <div className="h-1.5 overflow-hidden rounded bg-indigo-100">
                        <div className="h-full w-2/3 animate-pulse rounded bg-indigo-500" />
                      </div>
                    </div>
                  )}
                  <button disabled={requiredMissing || hasParamErrors || loadingTool === tool.name} onClick={() => {
                    const params: Record<string, unknown> = {};
                    let invalid = false;
                    const errors: Record<string, string> = {};
                    Object.entries(tool.parameters).forEach(([name, schema]) => {
                      const raw = toolParams[name];
                      if (!raw) return;
                      if (schema.type === "integer") {
                        const value = Number(raw);
                        if (!Number.isInteger(value)) {
                          invalid = true;
                          errors[name] = "请输入整数。";
                          return;
                        }
                        params[name] = value;
                      } else if (schema.type === "boolean") {
                        params[name] = raw === "true";
                      } else if (schema.type === "object" || schema.items?.type === "object") {
                        try {
                          const parsed = JSON.parse(raw);
                          const expectsArray = schema.type === "array" || schema.items?.type === "object";
                          if (!parsed || typeof parsed !== "object" || (expectsArray ? !Array.isArray(parsed) : Array.isArray(parsed))) throw new Error();
                          params[name] = parsed;
                        } catch {
                          invalid = true;
                          errors[name] = schema.items?.type === "object" ? "请输入有效的 JSON 数组。" : "请输入有效的 JSON 对象。";
                        }
                      } else if (schema.type === "array") {
                        params[name] = raw.split(/[\n,]/).map(value => value.trim()).filter(Boolean);
                      } else {
                        params[name] = raw;
                      }
                    });
                    setParamErrors(errors);
                    if (invalid) return;
                    if (
                      tool.name === "search_patents" &&
                      params.retrieval_mode === "multilingual_hybrid_beta" &&
                      !window.confirm("首次启用将下载并缓存约 471 MB 的多语言模型。继续执行？")
                    ) return;
                    onRun(tool.name, params);
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
  );
}
