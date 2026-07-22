import type { Message, SessionDetail, ToolStep } from "../../types";
import { normalizeAssistantContent } from "../../finalAnswer";

export function messagesFromSession(detail: SessionDetail): Message[] {
  const turns = new globalThis.Map(detail.turns.map(turn => [String(turn.id), turn]));
  const byTurn = new globalThis.Map<string, ToolStep[]>();
  for (const execution of detail.tool_executions) {
    const result = execution.result || null;
    const step: ToolStep = {
      id: execution.id,
      execution_id: execution.id,
      tool: execution.tool_name,
      status: execution.status,
      duration_ms: execution.duration_ms,
      error: execution.error || null,
      parameters: execution.parameters || {},
      result,
      summary: String(result?.summary || ""),
      methodology: String(result?.methodology || ""),
      data_quality: (result?.data_quality || {}) as Record<string, unknown>,
      warnings: (result?.warnings || []) as string[],
      stale: execution.stale,
      origin: "restored",
    };
    byTurn.set(execution.turn_id, [...(byTurn.get(execution.turn_id) || []), step]);
  }
  return detail.messages.map(stored => {
    const turnId = stored.turn_id || undefined;
    const turn = turnId ? turns.get(turnId) : undefined;
    const status = String(turn?.status || "completed") as Message["finalStatus"];
    const metadata = stored.metadata || {};
    const normalizedContent = stored.role === "assistant"
      ? normalizeAssistantContent(stored.content)
      : { content: stored.content, followupSuggestions: [], followupQuestions: [] };
    const pendingQuestion = (turn?.pending_question || {}) as Record<string, unknown>;
    const structuredSuggestions = (
      (metadata.followup_suggestions as { text?: string }[] | undefined) ||
      normalizedContent.followupSuggestions
    );
    const awaiting = status === "awaiting_clarification";
    return {
      id: `stored-${stored.id}`,
      role: stored.role,
      content: normalizedContent.content,
      turnId,
      steps: stored.role === "assistant" && turnId ? byTurn.get(turnId) : undefined,
      finalStatus: status,
      followupQuestions: awaiting ? ["按默认条件继续"] : (
        (metadata.followup_questions || (
          structuredSuggestions.length
            ? structuredSuggestions.map(item => item.text).filter(Boolean)
            : normalizedContent.followupQuestions
        )) as string[]
      ),
      followupSuggestions: structuredSuggestions as Message["followupSuggestions"],
      clarification: awaiting && turnId ? {
        turnId,
        missingFields: (pendingQuestion.missing_fields || []) as string[],
        allowDefaults: Boolean(pendingQuestion.allow_defaults),
      } : undefined,
      canResynthesize: stored.role === "assistant" && ["partial", "failed"].includes(String(status)) && Boolean(turnId),
    };
  });
}
