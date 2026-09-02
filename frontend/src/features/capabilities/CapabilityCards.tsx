import { Activity, Network, Route, Search, Sparkles, Target } from "lucide-react";
import type { CapabilityDefinition } from "../../types";
import { useI18n, type TranslationKey } from "../../i18n";

const ICONS = { search: Search, chart: Activity, sparkles: Sparkles, network: Network, route: Route, target: Target };

const CAPABILITY_KEYS: Record<string, { name: TranslationKey; description: TranslationKey; prompts: TranslationKey[] }> = {
  patent_search: {
    name: "capability.patent_search.name", description: "capability.patent_search.description",
    prompts: ["capability.patent_search.prompt.0", "capability.patent_search.prompt.1"],
  },
  technology_landscape: {
    name: "capability.technology_landscape.name", description: "capability.technology_landscape.description",
    prompts: ["capability.technology_landscape.prompt.0", "capability.technology_landscape.prompt.1"],
  },
  technology_topics: {
    name: "capability.technology_topics.name", description: "capability.technology_topics.description",
    prompts: ["capability.technology_topics.prompt.0", "capability.technology_topics.prompt.1"],
  },
  competition: {
    name: "capability.competition.name", description: "capability.competition.description",
    prompts: ["capability.competition.prompt.0", "capability.competition.prompt.1"],
  },
  technology_roadmap: {
    name: "capability.technology_roadmap.name", description: "capability.technology_roadmap.description",
    prompts: ["capability.technology_roadmap.prompt.0", "capability.technology_roadmap.prompt.1"],
  },
  value_opportunity: {
    name: "capability.value_opportunity.name", description: "capability.value_opportunity.description",
    prompts: ["capability.value_opportunity.prompt.0", "capability.value_opportunity.prompt.1"],
  },
  citation_family: {
    name: "capability.citation_family.name", description: "capability.citation_family.description",
    prompts: ["capability.citation_family.prompt.0", "capability.citation_family.prompt.1"],
  },
  search_monitor: {
    name: "capability.search_monitor.name", description: "capability.search_monitor.description",
    prompts: ["capability.search_monitor.prompt.0", "capability.search_monitor.prompt.1"],
  },
  legal_claims: {
    name: "capability.legal_claims.name", description: "capability.legal_claims.description",
    prompts: ["capability.legal_claims.prompt.0", "capability.legal_claims.prompt.1"],
  },
};

export function CapabilityCards({ capabilities, onPrompt, compact = false }: {
  capabilities: CapabilityDefinition[];
  onPrompt: (prompt: string) => void;
  compact?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className={`grid gap-3 ${compact ? "md:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-3"}`}>
      {capabilities.map(item => {
        const Icon = ICONS[item.icon as keyof typeof ICONS] || Sparkles;
        const translation = CAPABILITY_KEYS[item.id];
        const tone = item.availability === "available"
          ? "bg-emerald-50 text-emerald-700"
          : item.availability === "partial"
            ? "bg-amber-50 text-amber-700"
            : "bg-slate-100 text-slate-500";
        return (
          <article key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
            <div className="flex items-start justify-between gap-3">
              <div className="rounded-xl bg-blue-50 p-2 text-blue-700"><Icon className="h-5 w-5" /></div>
              <span className={`rounded-full px-2 py-1 text-[10px] ${tone}`}>
                {t("capability.available", { available: item.available_tool_count, total: item.tool_count })}
              </span>
            </div>
            <h3 className="mt-3 min-w-0 break-words font-semibold text-slate-800">{translation ? t(translation.name) : item.name}</h3>
            <p className="mt-1 min-h-10 break-words text-xs leading-5 text-slate-500">{translation ? t(translation.description) : item.description}</p>
            <div className="mt-3 space-y-1.5">
              {item.prompts.slice(0, compact ? 1 : 2).map((prompt, index) => {
                const displayPrompt = translation?.prompts[index] ? t(translation.prompts[index]) : prompt;
                return <button key={prompt} onClick={() => onPrompt(displayPrompt)} className="block w-full min-w-0 break-words rounded-lg bg-slate-50 px-2.5 py-2 text-left text-xs text-slate-600 hover:bg-blue-50 hover:text-blue-700" title={displayPrompt}>{displayPrompt}</button>;
              })}
            </div>
            {item.availability !== "available" && (
              <p className="mt-2 truncate text-[10px] text-amber-600" title={item.tools.filter(tool => !tool.available).map(tool => tool.reason).join("；")}>
                {item.availability === "partial" ? t("capability.partial") : t("capability.unavailable")}
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}
