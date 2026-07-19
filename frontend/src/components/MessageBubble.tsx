import { User, Bot, Lightbulb, Loader2, RefreshCw, AlertTriangle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { ToolStepCard } from "./ToolStepCard";
import type { Message, ToolStep } from "../types";
import { normalizeAssistantContent } from "../finalAnswer";

export function MessageBubble({ message, onRetry, onFollowup, onResynthesize }: {
  message: Message;
  onRetry?: (step: ToolStep) => void;
  onFollowup?: (text: string, replyToTurnId?: string) => void;
  onResynthesize?: (turnId: string) => void;
}) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const visibleContent = isUser
    ? message.content : normalizeAssistantContent(message.content).content;

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
          {isUser ? "用户" : isSystem ? "系统" : "Agent"}
          {message.intent && (
            <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100 font-normal">
              {message.intent}
            </span>
          )}
        </div>

        {message.streamStatus && (
          <div className="mb-3 flex items-center gap-2 text-xs text-blue-600">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />{message.streamStatus}
          </div>
        )}

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

        {message.error && (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{message.error}</span>
          </div>
        )}

        {message.canResynthesize && message.turnId && onResynthesize && (
          <button onClick={() => onResynthesize(message.turnId!)}
            className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-xs text-blue-700 hover:bg-blue-100">
            <RefreshCw className="w-3.5 h-3.5" /> 仅重试总结
          </button>
        )}

        {message.followupQuestions && message.followupQuestions.length > 0 && onFollowup && (
          <div className="mt-4 flex flex-wrap gap-2">
            {message.followupQuestions.map(question => (
              <button key={question}
                onClick={() => onFollowup(question, message.clarification?.turnId)}
                className="px-3 py-1.5 rounded-full border border-slate-200 bg-slate-50 text-xs text-slate-600 hover:border-blue-300 hover:text-blue-700">
                {question}
                {message.followupSuggestions?.find(item => item.text === question)?.requires_new_tools && (
                  <span className="ml-1 text-[10px] text-blue-500">· 需新分析</span>
                )}
              </button>
            ))}
          </div>
        )}

        {message.recommendations && message.recommendations.length > 0 && (
          <div className="mt-4 grid gap-2">
            <div className="text-xs font-semibold text-slate-500 mb-1 flex items-center gap-1">
              <Lightbulb className="w-4 h-4" /> 策略建议
            </div>
            {message.recommendations.map((rec, i) => (
              <div key={i} className="bg-amber-50 border border-amber-100 p-3 rounded-lg flex items-start gap-3">
                <span className="bg-amber-200 text-amber-800 text-[10px] px-2 py-1 rounded font-medium mt-0.5 whitespace-nowrap">
                  {rec.category}
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
