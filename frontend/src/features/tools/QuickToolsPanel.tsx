import { useState } from "react";
import {
  Activity, Database, FolderSearch, Layers, Loader2, Map, Network,
  PieChart, TrendingUp, Zap,
} from "lucide-react";
import type { SearchCapabilityStatus, Tool } from "../../types";

export const TOOL_META: Record<string, { label: string; icon: typeof Database }> = {
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

  return (
    <aside className={className || "hidden lg:flex w-[280px] bg-white border-l border-slate-200 overflow-y-auto flex-col shrink-0"}>
      <div className="p-5 sticky top-0 bg-white/80 backdrop-blur-md border-b border-slate-100 z-20">
        <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-500" /> 快捷工具
        </h2>
        <p className="text-xs text-slate-500 mt-1">{tools.length} 个工具 &middot; 按数据能力启用</p>
        <button
          type="button"
          onClick={() => setSelectedTool("search_patents")}
          className="mt-3 w-full rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-left"
        >
          <span className="block text-xs font-semibold text-indigo-800">MiniLM 多语言检索 Beta</span>
          <span className="mt-0.5 block text-[10px] text-indigo-600">
            {!searchStatus?.dependency_installed
              ? "运行依赖未安装"
              : searchStatus.model_cached
                ? `模型已缓存 · ${searchStatus.index_count} 个数据集索引`
                : `运行依赖已就绪 · 首次使用下载约 ${searchStatus.download_size_mb}MB`}
          </span>
        </button>
      </div>
      <div className="p-4 space-y-1">
        {tools.map(tool => {
          const meta = TOOL_META[tool.name] || { label: tool.name, icon: Zap };
          const Icon = meta.icon;
          const availability = tool.availability || { available: true, reason: "" };
          const hasParams = Object.keys(tool.parameters).length > 0;
          const expanded = selectedTool === tool.name;
          const requiredMissing = Object.entries(tool.parameters).some(
            ([name, schema]) => schema.required && !(toolParams[name] || "").trim(),
          );
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
                      {name}{schema.required ? " *" : ""}
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
                            <span className="font-medium text-indigo-700">多语言向量检索（Beta）</span>
                            <span className="block mt-0.5 text-[10px] text-slate-500">
                              首次启用会下载约 471MB 的本地 MiniLM；失败时明确回退到词法检索。
                            </span>
                          </span>
                        </span>
                      ) : schema.enum ? (
                        <select value={toolParams[name] || ""} onChange={event => setToolParams(current => ({ ...current, [name]: event.target.value }))}
                          className="mt-1 w-full p-1.5 border rounded bg-white">
                          <option value="">默认</option>
                          {schema.enum.map(value => <option key={value}>{value}</option>)}
                        </select>
                      ) : (
                        <input value={toolParams[name] || ""} onChange={event => setToolParams(current => ({ ...current, [name]: event.target.value }))}
                          placeholder={schema.description} className="mt-1 w-full p-1.5 border rounded bg-white" />
                      )}
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
                  <button disabled={requiredMissing || loadingTool === tool.name} onClick={() => {
                    const params: Record<string, unknown> = {};
                    Object.entries(tool.parameters).forEach(([name, schema]) => {
                      const raw = toolParams[name];
                      if (!raw) return;
                      params[name] = schema.type === "integer" ? Number(raw)
                        : schema.type === "array" ? raw.split(",").map(value => value.trim()).filter(Boolean)
                        : raw;
                    });
                    if (
                      tool.name === "search_patents" &&
                      params.retrieval_mode === "multilingual_hybrid_beta" &&
                      !window.confirm("首次启用将下载并缓存约 471MB 的多语言模型。继续执行？")
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
