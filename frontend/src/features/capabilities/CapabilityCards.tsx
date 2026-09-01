import { Activity, Network, Route, Search, Sparkles, Target } from "lucide-react";
import type { CapabilityDefinition } from "../../types";

const ICONS = { search: Search, chart: Activity, sparkles: Sparkles, network: Network, route: Route, target: Target };

export function CapabilityCards({ capabilities, onPrompt, compact = false }: {
  capabilities: CapabilityDefinition[];
  onPrompt: (prompt: string) => void;
  compact?: boolean;
}) {
  return (
    <div className={`grid gap-3 ${compact ? "md:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-3"}`}>
      {capabilities.map(item => {
        const Icon = ICONS[item.icon as keyof typeof ICONS] || Sparkles;
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
                {item.available_tool_count}/{item.tool_count} 可用
              </span>
            </div>
            <h3 className="mt-3 font-semibold text-slate-800">{item.name}</h3>
            <p className="mt-1 min-h-10 text-xs leading-5 text-slate-500">{item.description}</p>
            <div className="mt-3 space-y-1.5">
              {item.prompts.slice(0, compact ? 1 : 2).map(prompt => (
                <button key={prompt} onClick={() => onPrompt(prompt)} className="block w-full truncate rounded-lg bg-slate-50 px-2.5 py-2 text-left text-xs text-slate-600 hover:bg-blue-50 hover:text-blue-700" title={prompt}>{prompt}</button>
              ))}
            </div>
            {item.availability !== "available" && (
              <p className="mt-2 truncate text-[10px] text-amber-600" title={item.tools.filter(tool => !tool.available).map(tool => tool.reason).join("；")}>
                {item.availability === "partial" ? "部分工具因字段门槛降级" : "当前数据暂不可用"}
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}
