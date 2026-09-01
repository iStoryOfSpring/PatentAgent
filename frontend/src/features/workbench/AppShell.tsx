import { useState, type ReactNode } from "react";
import { Bot, Database, FileText, Menu, MessageSquare, Settings, Sparkles, X } from "lucide-react";

export type WorkbenchRoute = "chat" | "datasets" | "capabilities" | "reports" | "settings";

const NAV: { id: WorkbenchRoute; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "智能分析", icon: MessageSquare },
  { id: "datasets", label: "数据集", icon: Database },
  { id: "capabilities", label: "能力与工具", icon: Sparkles },
  { id: "reports", label: "报告", icon: FileText },
  { id: "settings", label: "设置", icon: Settings },
];

interface AppShellProps {
  route: WorkbenchRoute;
  onNavigate: (route: WorkbenchRoute) => void;
  backendOnline: boolean | null;
  datasetLabel: string;
  llmLabel: string;
  taskRunning: boolean;
  error?: string | null;
  onDismissError?: () => void;
  context?: ReactNode;
  children: ReactNode;
}

export function AppShell({
  route, onNavigate, backendOnline, datasetLabel, llmLabel, taskRunning,
  error, onDismissError, context, children,
}: AppShellProps) {
  const [showContext, setShowContext] = useState(false);
  return (
    <div className="h-screen w-screen overflow-hidden bg-slate-50 text-slate-900">
      <div className="flex h-full">
        <nav className="w-[72px] shrink-0 border-r border-slate-200 bg-slate-950 text-white flex flex-col items-center py-3">
          <div className="mb-5 rounded-xl bg-blue-600 p-2.5 shadow-lg shadow-blue-950/30" title="PatentAgent">
            <Bot className="h-5 w-5" />
          </div>
          <div className="flex flex-1 flex-col gap-2">
            {NAV.map(item => {
              const Icon = item.icon;
              return (
                <button key={item.id} type="button" onClick={() => onNavigate(item.id)}
                  className={`group relative rounded-xl p-3 transition ${route === item.id ? "bg-blue-600 text-white" : "text-slate-400 hover:bg-slate-800 hover:text-white"}`}
                  aria-label={item.label} title={item.label}>
                  <Icon className="h-5 w-5" />
                  <span className="pointer-events-none absolute left-14 top-1/2 z-50 hidden -translate-y-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1 text-xs shadow-lg group-hover:block">{item.label}</span>
                </button>
              );
            })}
          </div>
          <div className={`h-2.5 w-2.5 rounded-full ${backendOnline ? "bg-emerald-400" : backendOnline === false ? "bg-rose-400" : "bg-amber-300"}`} title={backendOnline ? "后端在线" : "后端状态异常"} />
        </nav>

        {context && <aside className="hidden w-[276px] shrink-0 border-r border-slate-200 bg-white lg:block overflow-y-auto">{context}</aside>}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="h-14 shrink-0 border-b border-slate-200 bg-white px-4 md:px-6 flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-2">
              {context && <button onClick={() => setShowContext(true)} className="rounded-lg border border-slate-200 p-2 text-slate-500 lg:hidden" aria-label="打开上下文栏"><Menu className="h-4 w-4" /></button>}
              <div className="min-w-0">
              <div className="font-semibold text-slate-800">PatentAgent 智能专利分析工作台</div>
              <div className="truncate text-[11px] text-slate-400">可追溯分析助手 · 不替代正式查新、FTO 或法律意见</div>
              </div>
            </div>
            <div className="hidden items-center gap-2 text-xs md:flex">
              <StatusDot ok={Boolean(datasetLabel)} label={datasetLabel || "未加载数据"} />
              <StatusDot ok={Boolean(llmLabel)} label={llmLabel || "LLM 未连接"} />
              {taskRunning && <span className="rounded-full bg-blue-50 px-2.5 py-1 text-blue-700">分析进行中</span>}
            </div>
          </header>
          {error && <div className="border-b border-rose-200 bg-rose-50 px-5 py-2 text-sm text-rose-700 flex justify-between"><span>{error}</span><button onClick={onDismissError}>×</button></div>}
          <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
      {context && showContext && <div className="fixed inset-0 z-50 flex bg-slate-950/40 lg:hidden" role="dialog" aria-modal="true" aria-label="上下文栏"><div className="relative h-full w-[min(86vw,320px)] overflow-y-auto bg-white shadow-2xl"><button onClick={() => setShowContext(false)} className="absolute right-3 top-3 z-10 rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500" aria-label="关闭上下文栏"><X className="h-4 w-4" /></button>{context}</div><button className="flex-1" aria-label="关闭上下文栏遮罩" onClick={() => setShowContext(false)} /></div>}
    </div>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return <span className="max-w-52 truncate rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600"><span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-slate-300"}`} />{label}</span>;
}
