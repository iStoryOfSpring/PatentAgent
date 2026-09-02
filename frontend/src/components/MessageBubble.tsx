import { User, Bot, Lightbulb, Loader2, RefreshCw, AlertTriangle, ListChecks } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { ToolStepCard } from "./ToolStepCard";
import type { Message, ToolStep } from "../types";
import { normalizeAssistantContent } from "../finalAnswer";
import { intentLabel, localizeErrorMessage, recommendationCategoryLabel, toolLabel, toolOrTextLabel } from "../uiLabels";
import { useI18n } from "../i18n";

export function MessageBubble({ message, onRetry, onFollowup, onResynthesize }: {
  message: Message;
  onRetry?: (step: ToolStep) => void;
  onFollowup?: (text: string, replyToTurnId?: string) => void;
  onResynthesize?: (turnId: string) => void;
}) {
  const { locale, t } = useI18n();
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const localizedErrorParams = message.errorParams
    ? { ...message.errorParams, ...(typeof message.errorParams.message === "string"
      ? { message: localizeErrorMessage(message.errorParams.message, locale) } : {}) }
    : undefined;
  const localizedContentParams = message.contentParams
    ? {
      ...message.contentParams,
      ...(message.contentKey === "tool.completed" && typeof message.contentParams.tool === "string"
        ? { tool: toolLabel(message.contentParams.tool, locale) } : {}),
    }
    : undefined;
  const visibleContent = message.contentKey
    ? t(message.contentKey, localizedContentParams)
    : message.id === "welcome"
      ? t("chat.welcome")
      : message.id.startsWith("welcome-")
        ? t("chat.newSessionWelcome")
        : isUser
          ? message.content : normalizeAssistantContent(message.content, locale).content;
  const streamStatus = message.streamStatusKey
    ? t(message.streamStatusKey, message.streamStatusParams)
    : message.streamStatus;
  const errorText = message.errorKey
    ? t(message.errorKey, localizedErrorParams)
    : message.error
      ? localizeErrorMessage(message.error, locale)
      : "";
  const followupQuestions = [
    ...(message.defaultFollowup ? [t("chat.continueDefault")] : []),
    ...(message.followupQuestions || []),
  ];

  return (
    <div className={`flex gap-4 p-4 ${isUser ? "bg-transparent" : "bg-white rounded-xl shadow-sm border border-slate-100"}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
        isUser ? "bg-indigo-100 text-indigo-600" :
        isSystem ? "bg-emerald-100 text-emerald-600" :
        "bg-blue-600 text-white"
      }`}>
        {isUser ? <User className="w-5 h-5" /> :
         isSystem ? <Bot className="w-5 h-5" /> :
         <Bot className="w-5 h-5" />}
      </div>
      <div className="flex-1 overflow-hidden">
        <div className="font-semibold text-sm text-slate-800 mb-1 flex items-center gap-2">
          {isUser ? t("message.user") : isSystem ? t("message.system") : t("message.assistant")}
          {message.intent && (
            <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100 font-normal">
              {intentLabel(message.intent, locale)}
            </span>
          )}
        </div>

        {streamStatus && (
          <div className="mb-3 flex items-center gap-2 text-xs text-blue-600">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />{streamStatus}
          </div>
        )}

        {message.plan?.steps?.length ? (
          <div className="mb-3 rounded-xl border border-blue-100 bg-blue-50/60 p-3">
            <div className="mb-2 flex items-center justify-between text-xs font-semibold text-blue-800">
              <span className="flex items-center gap-1.5"><ListChecks className="h-3.5 w-3.5" />{t("message.analysisPlan")}</span>
              {typeof message.plan.costWeight === "number" && <span className="font-normal text-blue-500" title={t("message.planCostTitle")}>{t("message.planCost", { value: message.plan.costWeight })}</span>}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {message.plan.steps.map((step, index) => (
                <span key={index} className="rounded-full border border-blue-100 bg-white px-2.5 py-1 text-[11px] text-slate-600">
                  {index + 1}. {toolOrTextLabel(step.tool || step.name || step.description || t("message.analysisStep"), locale)}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {message.steps && message.steps.length > 0 && (
          <div className="mb-3">
            {message.steps.map(step => (
              <ToolStepCard key={step.id} step={step} onRetry={onRetry} />
            ))}
          </div>
        )}

        {visibleContent && (
          <div className="text-slate-700 text-sm leading-relaxed prose prose-slate prose-sm max-w-[800px]
            prose-headings:text-slate-800 prose-headings:font-semibold
            prose-h1:text-lg prose-h2:text-base prose-h3:text-sm
            prose-p:my-1 prose-ul:my-1 prose-ol:my-1
            prose-li:my-0.5 prose-code:bg-slate-100 prose-code:px-1 prose-code:rounded
            prose-strong:text-slate-800">
            <ReactMarkdown>{visibleContent}</ReactMarkdown>
          </div>
        )}

        {errorText && (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorText}</span>
          </div>
        )}

        {message.canResynthesize && message.turnId && onResynthesize && (
          <button onClick={() => onResynthesize(message.turnId!)}
            className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-xs text-blue-700 hover:bg-blue-100">
            <RefreshCw className="w-3.5 h-3.5" /> {t("message.retrySummary")}
          </button>
        )}

        {followupQuestions.length > 0 && onFollowup && (
          <div className="mt-4 flex flex-wrap gap-2">
            {followupQuestions.map(question => (
              <button key={question}
                onClick={() => onFollowup(question, message.clarification?.turnId)}
                className="px-3 py-1.5 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-600 hover:border-blue-300 hover:text-blue-700">
                {question}
                {message.followupSuggestions?.find(item => item.text === question)?.requires_new_tools && (
            <span className="ml-1 text-[10px] text-blue-500">{t("message.needsNewAnalysis")}</span>
                )}
              </button>
            ))}
          </div>
        )}

        {message.recommendations && message.recommendations.length > 0 && (
          <div className="mt-4 grid gap-2">
            <div className="text-xs font-semibold text-slate-500 mb-1 flex items-center gap-1">
              <Lightbulb className="w-4 h-4" /> {t("message.strategyAdvice")}
            </div>
            {message.recommendations.map((rec, i) => (
              <div key={i} className="bg-amber-50 border border-amber-100 p-3 rounded-lg flex items-start gap-3">
                <span className="bg-amber-200 text-amber-800 text-[10px] px-2 py-1 rounded font-medium mt-0.5 whitespace-nowrap">
                  {recommendationCategoryLabel(rec.category, locale)}
                </span>
                <p className="text-sm text-amber-900 m-0">
                  {rec.recommendation}
                  <span className="ml-2 text-amber-500 text-xs">
                    {"◆".repeat(rec.urgency)}
                  </span>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
