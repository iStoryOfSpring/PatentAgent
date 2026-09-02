import { ArrowRight, CheckCircle2, X } from "lucide-react";
import { useI18n } from "../../i18n";

interface QuickToolReturnPromptProps {
  open: boolean;
  dontRemind: boolean;
  onDontRemindChange: (checked: boolean) => void;
  onStay: () => void;
  onReturnToChat: () => void;
}

export function QuickToolReturnPrompt({
  open, dontRemind, onDontRemindChange, onStay, onReturnToChat,
}: QuickToolReturnPromptProps) {
  const { t } = useI18n();
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label={t("quick.finishedAria")}
      className="fixed bottom-5 right-5 z-[90] w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-emerald-200 bg-white p-4 shadow-2xl shadow-slate-900/15"
    >
      <button
        type="button"
        onClick={onStay}
        aria-label={t("quick.closeFinishedAria")}
        className="absolute right-3 top-3 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
      >
        <X className="h-4 w-4" />
      </button>
      <div className="flex items-start gap-3 pr-5">
        <div className="rounded-full bg-emerald-100 p-2 text-emerald-600">
          <CheckCircle2 className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{t("quick.finishedTitle")}</h2>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {t("quick.finishedDescription")}
          </p>
        </div>
      </div>
      <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-slate-600">
        <input
          type="checkbox"
          checked={dontRemind}
          onChange={event => onDontRemindChange(event.target.checked)}
          className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600"
        />
        {t("quick.dontRemind")}
      </label>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onStay}
          className="rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:bg-slate-50"
        >
          {t("quick.stay")}
        </button>
        <button
          type="button"
          onClick={onReturnToChat}
          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700"
        >
          {t("quick.returnChat")}
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
