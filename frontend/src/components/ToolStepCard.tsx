import { lazy, Suspense, useState } from "react";
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import type { ToolStep } from "../types";
import { formatDisplayJson, localizeErrorMessage, originLabel, statusLabel, toolLabel } from "../uiLabels";
import { useI18n } from "../i18n";

const VisualizationPanel = lazy(() => import("./VisualizationPanel").then(module => ({
  default: module.VisualizationPanel,
})));

export function ToolStepCard({ step, onRetry }: { step: ToolStep; onRetry?: (step: ToolStep) => void }) {
  const [expanded, setExpanded] = useState(true);
  const [warningsExpanded, setWarningsExpanded] = useState(false);
  const { locale, t } = useI18n();

  return (
    <div className="my-3 border border-slate-200 rounded-lg bg-white overflow-hidden shadow-sm">
      <div
        className="flex min-w-0 flex-wrap items-center justify-between gap-2 p-3 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-sm font-medium text-slate-700">
          {step.status === "running" && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
          {step.status === "completed" && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
          {step.status === "failed" && <XCircle className="w-4 h-4 text-rose-500" />}
          {step.status === "skipped" && <AlertTriangle className="w-4 h-4 text-amber-500" />}
          <span className="min-w-0 max-w-full break-words bg-slate-100 px-2 py-1 rounded text-slate-600" title={t("tool.idTitle", { id: step.tool })}>
            {toolLabel(step.tool, locale)}
          </span>
          <span className="text-xs text-slate-500">{statusLabel(step.status, locale)}</span>
          {step.status === "completed" && step.duration_ms != null && (
            <span className="text-slate-400 text-xs ml-2">{t("tool.duration", { value: step.duration_ms })}</span>
          )}
          {step.origin && <span className="text-[10px] text-blue-600">{originLabel(step.origin, locale)}</span>}
          {step.stale && <span className="text-[10px] text-amber-600">{t("tool.dataChanged")}</span>}
        </div>
        {expanded
          ? <ChevronDown className="w-4 h-4 text-slate-400" />
          : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </div>

      {expanded && (
        <div className="p-3 border-t border-slate-100 space-y-3 text-sm">
          {step.summary && <p className="text-slate-700">{step.summary}</p>}
          {step.warnings && step.warnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 overflow-hidden">
              <button onClick={() => setWarningsExpanded(v => !v)}
                className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left text-xs text-amber-800">
                <span className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5"/>{t("tool.dataLimit", { count: step.warnings.length })}</span>
                <span className="truncate text-amber-700/80">{warningsExpanded ? t("tool.collapse") : step.warnings[0]}</span>
              </button>
              {warningsExpanded && <div className="px-3 pb-2 space-y-1 border-t border-amber-100 pt-2">
                {step.warnings.map((warning, i) => <p key={i} className="text-xs text-amber-800">{i + 1}. {warning}</p>)}
              </div>}
            </div>
          )}
          {step.methodology && (
            <details className="text-xs text-slate-500"><summary className="cursor-pointer font-medium">{t("tool.methodQuality")}</summary>
              <p className="mt-2">{step.methodology}</p>
              {step.parameters && <pre className="mt-2 whitespace-pre-wrap">{t("tool.parameters")}: {formatDisplayJson(step.parameters, locale, false)}</pre>}
              {step.data_quality && <pre className="mt-2 whitespace-pre-wrap">{t("tool.quality")}: {formatDisplayJson(step.data_quality, locale, false)}</pre>}
            </details>
          )}
        </div>
      )}
      {expanded && (step.result || step.chart_html) && (
        <Suspense fallback={<div className="p-6 text-xs text-slate-500">{t("tool.loadingVisualization")}</div>}>
          <VisualizationPanel result={step.result} chartHtml={step.chart_html} toolName={step.tool}/>
        </Suspense>
      )}
      {expanded && step.error && (
        <div className="p-3 text-sm text-rose-600 bg-rose-50 border-t border-rose-100">
          {localizeErrorMessage(step.error, locale)}
          {onRetry && step.status === "failed" && (
            <button onClick={() => onRetry(step)} className="ml-3 px-2 py-1 bg-white border border-rose-200 rounded text-xs">
              {t("tool.retry")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
