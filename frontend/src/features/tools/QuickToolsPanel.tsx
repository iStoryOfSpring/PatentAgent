import { useState } from "react";
import {
  Activity, Database, FolderSearch, Layers, Loader2, Map, Network,
  PieChart, TrendingUp, Zap,
} from "lucide-react";
import type { SearchCapabilityStatus, Tool } from "../../types";
import {
  enumLabel, parameterHelp, parameterLabel, toolLabel,
} from "../../uiLabels";
import { useI18n } from "../../i18n";

export const TOOL_META: Record<string, { icon: typeof Database }> = {
  get_dataset_summary: { icon: Database },
  analyze_patent_trend: { icon: TrendingUp },
  analyze_lifecycle: { icon: Activity },
  analyze_ipc_distribution: { icon: Layers },
  generate_wordcloud: { icon: PieChart },
  analyze_burst_terms: { icon: Zap },
  analyze_yearly_keywords: { icon: TrendingUp },
  analyze_country_distribution: { icon: Map },
  analyze_co_network: { icon: Network },
  analyze_tech_roadmap: { icon: Activity },
  analyze_tech_matrix: { icon: Layers },
  analyze_clustering: { icon: Network },
  analyze_patent_valuation: { icon: TrendingUp },
  analyze_competitor_evolution: { icon: Network },
  search_patents: { icon: FolderSearch },
  read_patent_details: { icon: FolderSearch },
  analyze_entity_portfolio: { icon: Database },
  analyze_concentration: { icon: PieChart },
  analyze_citation_network: { icon: Network },
  analyze_family_geography: { icon: Map },
  audit_search_strategy: { icon: FolderSearch },
  analyze_legal_status: { icon: Activity },
  monitor_patent_changes: { icon: Activity },
  analyze_claim_elements: { icon: Layers },
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
  const { locale, t } = useI18n();
  const [selectedTool, setSelectedTool] = useState<string | null>("search_patents");
  const [toolParams, setToolParams] = useState<Record<string, string>>({});
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});

  return (
    <aside className={className || "hidden lg:flex w-[280px] bg-white border-l border-slate-200 overflow-y-auto flex-col shrink-0"}>
      <div className="p-5 sticky top-0 bg-white/80 backdrop-blur-md border-b border-slate-100 z-20">
        <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-500" /> {t("quick.title")}
        </h2>
        <p className="text-xs text-slate-500 mt-1">{t("quick.summary", { count: tools.length })}</p>
        <p className="text-[10px] text-slate-400 mt-1">{t("quick.saved")}</p>
        <button
          type="button"
          onClick={() => setSelectedTool("search_patents")}
          className="mt-3 w-full rounded-lg border border-indigo-200 bg-indigo-50 p-2 text-left"
        >
          <span className="block text-xs font-semibold text-indigo-800">{t("quick.semanticTitle")}</span>
          <span className="mt-0.5 block text-[10px] text-indigo-600">
            {!searchStatus?.dependency_installed
              ? t("quick.dependencyMissing")
              : searchStatus.model_cached
                ? t("quick.modelCached", { count: searchStatus.index_count })
                : t("quick.modelReady", { size: searchStatus.download_size_mb })}
          </span>
          <span className="mt-1 block text-[10px] text-indigo-500">{t("quick.semanticDescription")}</span>
        </button>
      </div>
      <div className="p-4 space-y-1">
        {tools.map(tool => {
          const meta = TOOL_META[tool.name] || { icon: Zap };
          const Icon = meta.icon;
          const availability = tool.availability || { available: true, reason: "" };
          const hasParams = Object.keys(tool.parameters).length > 0;
          const expanded = selectedTool === tool.name;
          const requiredMissing = Object.entries(tool.parameters).some(
            ([name, schema]) => schema.required && !(toolParams[name] ?? "").trim(),
          );
          const hasParamErrors = Object.keys(paramErrors).some(name => name in tool.parameters && paramErrors[name]);
          const toolTitle = !availability.available && availability.reason
            ? availability.reason
            : toolLabel(tool.name, locale);
          return (
            <div key={tool.name} className="border-b border-slate-50 pb-1">
              <button
                onClick={() => hasParams ? setSelectedTool(expanded ? null : tool.name) : onRun(tool.name)}
                disabled={isStreaming || !availability.available}
                title={toolTitle}
                className="w-full flex items-center gap-3 p-2.5 rounded-xl hover:bg-slate-50 text-slate-700 transition-all disabled:opacity-40 group"
              >
                <div className="w-7 h-7 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                  {loadingTool === tool.name ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
                </div>
                <span className="min-w-0 flex-1 break-words text-left text-sm font-medium">{toolLabel(tool.name, locale)}</span>
                {hasParams && <span className="shrink-0 text-slate-400 text-xs">{expanded ? "−" : "+"}</span>}
              </button>
              {!availability.available && availability.reason && (
                <p className="px-3 pb-2 text-[10px] text-amber-700">{availability.reason}</p>
              )}
              {expanded && (
                <div className="mx-2 mb-2 p-3 bg-slate-50 rounded-lg space-y-2">
                  {Object.entries(tool.parameters).map(([name, schema]) => (
                    <label key={name} className="block text-[11px] text-slate-600">
                      <span className="font-medium">{parameterLabel(name, locale)}{schema.required ? " *" : ""}</span>
                      <span className="mt-0.5 block text-[10px] leading-4 text-slate-400">{parameterHelp(name, schema, locale)}</span>
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
                            <span className="font-medium text-indigo-700">{t("quick.semanticMode")}</span>
                            <span className="block mt-0.5 text-[10px] text-slate-500">
                              {t("quick.semanticModeDescription")}
                            </span>
                          </span>
                        </span>
                      ) : schema.enum ? (
                        <select value={toolParams[name] || ""} onChange={event => setToolParams(current => ({ ...current, [name]: event.target.value }))}
                          className="mt-1 w-full p-1.5 border rounded bg-white">
                          <option value="">{t("quick.default")}</option>
                          {schema.enum.map(value => <option key={value} value={value}>{enumLabel(value, locale)}</option>)}
                        </select>
                      ) : schema.type === "boolean" ? (
                        <select
                          value={toolParams[name] ?? (schema.default === true ? "true" : schema.default === false ? "false" : "")}
                          onChange={event => setToolParams(current => ({ ...current, [name]: event.target.value }))}
                          className="mt-1 w-full p-1.5 border rounded bg-white"
                        >
                          <option value="">{t("quick.default")}</option>
                          <option value="true">{t("quick.yes")}</option>
                          <option value="false">{t("quick.no")}</option>
                        </select>
                      ) : schema.type === "object" || schema.items?.type === "object" ? (
                        <textarea
                          value={toolParams[name] || ""}
                          onChange={event => {
                            setToolParams(current => ({ ...current, [name]: event.target.value }));
                            setParamErrors(current => ({ ...current, [name]: "" }));
                          }}
                          placeholder={schema.items?.type === "object" ? t("quick.jsonArrayPlaceholder") : t("quick.jsonObjectPlaceholder")}
                          className="mt-1 min-h-16 w-full resize-y rounded border bg-white p-1.5 font-mono text-[11px]"
                        />
                      ) : (
                        <input value={toolParams[name] || ""} onChange={event => {
                          setToolParams(current => ({ ...current, [name]: event.target.value }));
                          setParamErrors(current => ({ ...current, [name]: "" }));
                        }}
                          placeholder={schema.type === "array" ? t("quick.arrayPlaceholder") : t("quick.valuePlaceholder")} className="mt-1 w-full p-1.5 border rounded bg-white" />
                      )}
                      {paramErrors[name] && <span className="mt-1 block text-[10px] text-rose-600">{paramErrors[name]}</span>}
                    </label>
                  ))}
                  {loadingTool === tool.name && toolParams.retrieval_mode === "multilingual_hybrid_beta" && (
                    <div className="rounded border border-indigo-100 bg-white p-2" role="status">
                      <div className="mb-1 text-[10px] text-indigo-700">{t("quick.downloadIndex")}</div>
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
                          errors[name] = t("quick.invalidInteger");
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
                          errors[name] = schema.items?.type === "object" ? t("quick.invalidArray") : t("quick.invalidObject");
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
                      !window.confirm(t("quick.semanticConfirm"))
                    ) return;
                    onRun(tool.name, params);
                  }} className="w-full py-1.5 bg-indigo-600 text-white text-xs rounded disabled:opacity-40 disabled:cursor-not-allowed">
                    {t("quick.execute")}
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
