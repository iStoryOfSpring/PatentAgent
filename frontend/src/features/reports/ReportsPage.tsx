import { useEffect, useState } from "react";
import { Download, FileText, Loader2, Plus } from "lucide-react";
import { createReport, fetchReports, reportUrl } from "../../api";
import type { ReportSummary } from "../../types";

export function ReportsPage({ activeSessionId, onError }: { activeSessionId: string; onError: (message: string) => void }) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [creating, setCreating] = useState(false);
  const refresh = () => fetchReports().then(result => setReports(result.reports)).catch(error => onError((error as Error).message));
  useEffect(() => { void refresh(); }, []);
  const create = async () => {
    if (!activeSessionId) return onError("请先选择一个会话");
    setCreating(true);
    try {
      await createReport(activeSessionId, `PatentAgent 专利分析报告 ${new Date().toLocaleDateString()}`);
      await refresh();
    } catch (error) { onError((error as Error).message); } finally { setCreating(false); }
  };
  return <div className="h-full overflow-y-auto p-5 md:p-8"><div className="mx-auto max-w-5xl"><div className="flex items-center justify-between gap-4"><div><h1 className="text-2xl font-bold">分析报告</h1><p className="mt-1 text-sm text-slate-500">从持久化会话与工具证据生成可追溯 HTML 报告。</p></div><button onClick={create} disabled={creating || !activeSessionId} className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}生成当前会话报告</button></div><div className="mt-6 space-y-3">{reports.map(report => <article key={report.id} className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="rounded-xl bg-blue-50 p-3 text-blue-600"><FileText className="h-5 w-5" /></div><div className="min-w-0 flex-1"><h3 className="truncate font-semibold text-slate-800">{report.title}</h3><p className="mt-1 text-xs text-slate-400">{new Date(report.created_at).toLocaleString()} · {report.session_id}</p></div><a href={reportUrl(report.id)} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:border-blue-200 hover:text-blue-700"><Download className="h-3.5 w-3.5" />打开 HTML</a></article>)}{!reports.length && <div className="rounded-2xl border border-dashed border-slate-300 p-12 text-center text-sm text-slate-500">还没有报告。完成一次分析后，可生成当前会话报告。</div>}</div></div></div>;
}
