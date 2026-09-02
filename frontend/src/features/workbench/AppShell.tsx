import { useState, type ReactNode } from "react";
import { Bot, Database, FileText, Github, Menu, MessageSquare, Settings, Sparkles, X } from "lucide-react";
import { useI18n } from "../../i18n";

export type WorkbenchRoute = "chat" | "datasets" | "capabilities" | "reports" | "settings";

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
  const { locale, setLocale, t } = useI18n();
  const nav = [
    { id: "chat" as const, label: t("nav.chat"), icon: MessageSquare },
    { id: "datasets" as const, label: t("nav.datasets"), icon: Database },
    { id: "capabilities" as const, label: t("nav.capabilities"), icon: Sparkles },
    { id: "reports" as const, label: t("nav.reports"), icon: FileText },
    { id: "settings" as const, label: t("nav.settings"), icon: Settings },
  ];
  return (
    <div className="h-screen w-screen overflow-hidden bg-slate-50 text-slate-900">
      <div className="flex h-full">
        <nav className="w-[72px] shrink-0 border-r border-slate-200 bg-slate-950 text-white flex flex-col items-center py-3">
          <div className="mb-5 rounded-xl bg-blue-600 p-2.5 shadow-lg shadow-blue-950/30" title="PatentAgent">
            <Bot className="h-5 w-5" />
          </div>
          <div className="flex flex-1 flex-col gap-2">
            {nav.map(item => {
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
          <div className={`h-2.5 w-2.5 rounded-full ${backendOnline ? "bg-emerald-400" : backendOnline === false ? "bg-rose-400" : "bg-amber-300"}`} title={backendOnline ? t("status.backendOnline") : t("status.backendError")} />
        </nav>

        {context && <aside className="hidden w-[276px] shrink-0 border-r border-slate-200 bg-white lg:block overflow-y-auto">{context}</aside>}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="h-14 shrink-0 border-b border-slate-200 bg-white px-4 md:px-6 flex items-center justify-between gap-4">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              {context && <button onClick={() => setShowContext(true)} className="shrink-0 rounded-lg border border-slate-200 p-2 text-slate-500 lg:hidden" aria-label={t("status.openContext")}><Menu className="h-4 w-4" /></button>}
              <div className="min-w-0">
              <div className="truncate font-semibold text-slate-800">{t("app.title")}</div>
              <div className="truncate text-[11px] text-slate-400">{t("app.subtitle")}</div>
              </div>
            </div>
            <div className="flex min-w-0 shrink-0 items-center gap-2">
              <div className="hidden min-w-0 items-center gap-2 text-xs md:flex">
                <StatusDot ok={Boolean(datasetLabel)} label={datasetLabel || t("status.datasetNotLoaded")} />
                <StatusDot ok={Boolean(llmLabel)} label={llmLabel || t("status.llmNotConnected")} />
                {taskRunning && <span className="shrink-0 rounded-full bg-blue-50 px-2.5 py-1 text-blue-700">{t("status.analysisRunning")}</span>}
              </div>
              <label className="sr-only" htmlFor="locale-select">{t("language.label")}</label>
              <select
                id="locale-select"
                aria-label={t("language.label")}
                value={locale}
                onChange={event => setLocale(event.target.value as typeof locale)}
                className="h-8 max-w-[6.5rem] shrink-0 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-600 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
              >
                <option value="zh-CN">{t("language.zh")}</option>
                <option value="en-US">{t("language.en")}</option>
              </select>
            </div>
          </header>
          {error && <div className="flex justify-between gap-3 border-b border-rose-200 bg-rose-50 px-5 py-2 text-sm text-rose-700"><span className="min-w-0 break-words">{error}</span><button onClick={onDismissError} aria-label={t("errors.dismiss")} className="shrink-0">×</button></div>}
          <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
          <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-2 text-center text-[11px] text-slate-400">
            <a
              href="https://github.com/iStoryOfSpring/PatentAgent"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded px-2 py-1 transition-colors hover:bg-slate-50 hover:text-slate-600"
            >
              <Github className="h-3.5 w-3.5" />
              {t("footer.githubRepo")}
              <span className="hidden sm:inline">· github.com/iStoryOfSpring/PatentAgent</span>
            </a>
          </footer>
        </div>
      </div>
      {context && showContext && <div className="fixed inset-0 z-50 flex bg-slate-950/40 lg:hidden" role="dialog" aria-modal="true" aria-label={t("status.contextOverlay")}><div className="relative h-full w-[min(86vw,320px)] overflow-y-auto bg-white shadow-2xl"><button onClick={() => setShowContext(false)} className="absolute right-3 top-3 z-10 rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500" aria-label={t("status.closeContext")}><X className="h-4 w-4" /></button>{context}</div><button className="flex-1" aria-label={t("status.contextOverlay")} onClick={() => setShowContext(false)} /></div>}
    </div>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return <span className="max-w-52 truncate rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600"><span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-slate-300"}`} />{label}</span>;
}
