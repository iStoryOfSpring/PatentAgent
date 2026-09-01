import type { CapabilityDefinition, SearchCapabilityStatus, Tool } from "../../types";
import { CapabilityCards } from "./CapabilityCards";
import { QuickToolsPanel } from "../tools/QuickToolsPanel";

export function CapabilitiesPage({ capabilities, tools, searchStatus, loadingTool, isStreaming, onPrompt, onRun }: {
  capabilities: CapabilityDefinition[];
  tools: Tool[];
  searchStatus?: SearchCapabilityStatus;
  loadingTool: string | null;
  isStreaming: boolean;
  onPrompt: (prompt: string) => void;
  onRun: (tool: string, params?: Record<string, unknown>) => void;
}) {
  return <div className="h-full overflow-y-auto p-5 md:p-8"><div className="mx-auto max-w-7xl"><div><h1 className="text-2xl font-bold">能力与工具</h1><p className="mt-1 text-sm text-slate-500">能力卡用于组织问题，底层工具仍由总 Agent 按数据门槛动态选择。</p></div><div className="mt-6"><CapabilityCards capabilities={capabilities} onPrompt={onPrompt} /></div><div className="mt-8"><QuickToolsPanel className="flex w-full flex-col rounded-2xl border border-slate-200 bg-white shadow-sm" tools={tools} isStreaming={isStreaming} loadingTool={loadingTool} searchStatus={searchStatus} onRun={onRun} /></div></div></div>;
}
