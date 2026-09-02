import type { CapabilityDefinition, SearchCapabilityStatus, Tool } from "../../types";
import { CapabilityCards } from "./CapabilityCards";
import { QuickToolsPanel } from "../tools/QuickToolsPanel";
import { useI18n } from "../../i18n";

export function CapabilitiesPage({ capabilities, tools, searchStatus, loadingTool, isStreaming, onPrompt, onRun }: {
  capabilities: CapabilityDefinition[];
  tools: Tool[];
  searchStatus?: SearchCapabilityStatus;
  loadingTool: string | null;
  isStreaming: boolean;
  onPrompt: (prompt: string) => void;
  onRun: (tool: string, params?: Record<string, unknown>) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl px-5 pt-5 md:px-8 md:pt-8">
        <div>
          <h1 className="text-2xl font-bold">{t("capabilities.title")}</h1>
          <p className="mt-1 text-sm text-slate-500">{t("capabilities.subtitle")}</p>
        </div>
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)] lg:items-start">
          <div className="order-last min-w-0 lg:order-first">
            <CapabilityCards capabilities={capabilities} onPrompt={onPrompt} />
          </div>
          <div className="order-first min-w-0 lg:sticky lg:top-0 lg:order-last">
            <QuickToolsPanel
              className="flex w-full flex-col rounded-2xl border border-slate-200 bg-white shadow-sm lg:max-h-[calc(100dvh-9rem)] lg:overflow-y-auto"
              tools={tools}
              isStreaming={isStreaming}
              loadingTool={loadingTool}
              searchStatus={searchStatus}
              onRun={onRun}
            />
          </div>
        </div>
        <div className="pb-5 md:pb-8" aria-hidden="true" />
      </div>
    </div>
  );
}
