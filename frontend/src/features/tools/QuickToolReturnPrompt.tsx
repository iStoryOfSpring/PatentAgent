import { ArrowRight, CheckCircle2, X } from "lucide-react";

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
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="快捷工具完成提示"
      className="fixed bottom-5 right-5 z-[90] w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-emerald-200 bg-white p-4 shadow-2xl shadow-slate-900/15"
    >
      <button
        type="button"
        onClick={onStay}
        aria-label="关闭快捷工具完成提示"
        className="absolute right-3 top-3 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
      >
        <X className="h-4 w-4" />
      </button>
      <div className="flex items-start gap-3 pr-5">
        <div className="rounded-full bg-emerald-100 p-2 text-emerald-600">
          <CheckCircle2 className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-900">工具执行完成</h2>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            结果已保存到当前会话。回到聊天页面后，智能助手可以继续结合这份结果进行分析。
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
        以后不再提示
      </label>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onStay}
          className="rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:bg-slate-50"
        >
          留在当前页面
        </button>
        <button
          type="button"
          onClick={onReturnToChat}
          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700"
        >
          回到聊天页面
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
