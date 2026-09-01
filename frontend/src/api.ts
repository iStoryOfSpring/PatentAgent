// All backend API calls. Vite proxy forwards /api → localhost:8000.
import type {
  HealthResponse, DataSummary, Tool, ToolResult, LLMConfig, SSEEvent,
  SessionSummary, SessionDetail,
  ProviderCredentials, ProviderProfile, ProviderProfileInput, ProviderProbeResult,
  AgentTask, DatasetVersion, SearchCapabilityStatus, TaskEvent,
  CapabilityDefinition, DatasetImportStatus, DatasetRecord, ReportSummary,
} from "./types";

const BASE = "/api";

export interface ApiErrorDetail {
  message?: string;
  category?: string;
  stages?: Record<string, { status: string; latency_ms?: number }>;
}

export class ApiError extends Error {
  detail?: ApiErrorDetail;

  constructor(message: string, detail?: ApiErrorDetail) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const raw = (body as { detail?: string | ApiErrorDetail }).detail;
    const detail = typeof raw === "object" && raw ? raw : undefined;
    const message = typeof raw === "string" ? raw : detail?.message || res.statusText;
    throw new ApiError(message, detail);
  }
  return res.json();
}

// ── Health ──

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

// ── Data ──

export function fetchDataSummary(): Promise<DataSummary> {
  return request<DataSummary>("/data/summary");
}

export type SourceFormat = "auto" | "wos_dii" | "google_patents_jsonl" | "uspto_grant_xml" | "uspto_file_wrapper_json";

export function loadData(inputDir: string, sourceFormat: SourceFormat = "auto"): Promise<DataSummary> {
  return request<DataSummary>("/data/load", {
    method: "POST",
    body: JSON.stringify({ input_dir: inputDir, source_format: sourceFormat }),
  });
}

export function fetchDatasets(): Promise<{ datasets: DatasetRecord[]; trace_id?: string }> {
  return request<{ datasets: DatasetRecord[]; trace_id?: string }>("/datasets");
}

export async function uploadDataset(
  files: File[], name: string, sourceFormat: SourceFormat = "auto", datasetId = "",
): Promise<{ import_id: string; status: string; dataset_id: string; files: string[] }> {
  const form = new FormData();
  files.forEach(file => form.append("files", file));
  form.append("name", name);
  form.append("source_format", sourceFormat);
  if (datasetId) form.append("dataset_id", datasetId);
  const response = await fetch(`${BASE}/datasets/imports`, { method: "POST", body: form });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError((body as { detail?: string }).detail || response.statusText);
  }
  return response.json();
}

export function fetchImport(id: string): Promise<DatasetImportStatus> {
  return request<{ import: DatasetImportStatus }>(`/imports/${id}`).then(result => result.import);
}

export function updateDataset(
  id: string, values: { name?: string; status?: "ready" | "archived" },
): Promise<DatasetRecord> {
  return request<{ dataset: DatasetRecord }>(`/datasets/${id}`, {
    method: "PATCH", body: JSON.stringify(values),
  }).then(result => result.dataset);
}

export function fetchDatasetVersions(id: string): Promise<{ versions: DatasetVersion[] }> {
  return request<{ versions: DatasetVersion[] }>(`/datasets/${id}/versions`);
}

// ── Tools ──

export function fetchTools(): Promise<{ tools: Tool[] }> {
  return request<{ tools: Tool[] }>("/tools");
}

export function fetchCapabilities(): Promise<{ capabilities: CapabilityDefinition[] }> {
  return request<{ capabilities: CapabilityDefinition[] }>("/capabilities");
}

export function fetchSearchStatus(): Promise<SearchCapabilityStatus> {
  return request<SearchCapabilityStatus>("/search/status");
}

export function runTool(name: string, params: Record<string, unknown> = {}, sessionId?: string): Promise<ToolResult> {
  return request<ToolResult>(`/tools/${name}`, {
    method: "POST",
    body: JSON.stringify({ params, session_id: sessionId }),
  });
}

// ── LLM Config ──

export function configureLLM(config: LLMConfig): Promise<{
  status: string; provider: string; model: string; probe: string; tool_roundtrip: boolean;
  structured_output: boolean;
}> {
  return request("/agent/config", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function fetchProviderProfiles(): Promise<{ profiles: ProviderProfile[] }> {
  return request<{ profiles: ProviderProfile[] }>("/llm/profiles");
}

export function createProviderProfile(profile: ProviderProfileInput): Promise<ProviderProfile> {
  return request<ProviderProfile>("/llm/profiles", {
    method: "POST", body: JSON.stringify(profile),
  });
}

export function updateProviderProfile(
  id: string, profile: Partial<ProviderProfileInput>,
): Promise<ProviderProfile> {
  return request<ProviderProfile>(`/llm/profiles/${id}`, {
    method: "PATCH", body: JSON.stringify(profile),
  });
}

export function deleteProviderProfile(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/llm/profiles/${id}`, { method: "DELETE" });
}

export function probeProviderProfile(
  id: string, credentials: ProviderCredentials,
): Promise<ProviderProbeResult> {
  return request<ProviderProbeResult>(`/llm/profiles/${id}/probe`, {
    method: "POST", body: JSON.stringify(credentials),
  });
}

export function activateProviderProfile(
  id: string, credentials: ProviderCredentials,
): Promise<ProviderProbeResult> {
  return request<ProviderProbeResult>(`/llm/profiles/${id}/activate`, {
    method: "POST", body: JSON.stringify(credentials),
  });
}

export function discoverProviderModels(
  id: string, credentials: ProviderCredentials,
): Promise<{ models: string[]; latency_ms: number; manual_entry_allowed: boolean }> {
  return request(`/llm/profiles/${id}/models`, {
    method: "POST", body: JSON.stringify(credentials),
  });
}

export function disconnectLLM(): Promise<{ status: string }> {
  return request<{ status: string }>("/llm/disconnect", { method: "POST" });
}

// ── Persistent sessions ──

export function createSession(name = "新会话", datasetVersionId?: string): Promise<SessionSummary> {
  return request<SessionSummary>("/sessions", {
    method: "POST", body: JSON.stringify({ name, dataset_version_id: datasetVersionId }),
  });
}

export function bindSessionDataset(id: string, datasetVersionId: string): Promise<{
  session: SessionSummary; stale_evidence_count: number;
}> {
  return request(`/sessions/${id}/dataset`, {
    method: "PUT", body: JSON.stringify({ dataset_version_id: datasetVersionId }),
  });
}

export function fetchSessions(): Promise<{ sessions: SessionSummary[] }> {
  return request<{ sessions: SessionSummary[] }>("/sessions");
}

export function fetchSession(id: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${id}`);
}

export function renameSession(id: string, name: string): Promise<SessionSummary> {
  return request<SessionSummary>(`/sessions/${id}`, {
    method: "PATCH", body: JSON.stringify({ name }),
  });
}

export function deleteSession(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/sessions/${id}`, { method: "DELETE" });
}

export function resynthesizeTurn(
  sessionId: string, turnId: string, responseMode: "detailed" | "concise",
): Promise<{
  text: string; final_status: "completed" | "partial"; answer_present: boolean;
  evidence_refs?: string[]; followup_suggestions?: import("./types").FollowupSuggestion[];
  followup_questions?: string[];
}> {
  return request(`/sessions/${sessionId}/turns/${turnId}/resynthesize`, {
    method: "POST", body: JSON.stringify({ response_mode: responseMode }),
  });
}

// ── Persistent Agent tasks ──

export function fetchTask(id: string): Promise<AgentTask> {
  return request<{ task: AgentTask }>(`/tasks/${id}`).then(result => result.task);
}

export function cancelTask(id: string): Promise<AgentTask> {
  return request<{ task: AgentTask }>(`/tasks/${id}/cancel`, { method: "POST" }).then(result => result.task);
}

export function resumeTask(id: string, responseMode: "detailed" | "concise" = "detailed") {
  return request(`/tasks/${id}/resume`, {
    method: "POST",
    body: JSON.stringify({ response_mode: responseMode }),
  });
}

export function streamTaskEvents(
  id: string,
  onEvent: (event: TaskEvent) => void,
  afterEventId = 0,
): AbortController {
  const controller = new AbortController();
  void (async () => {
    const response = await fetch(`${BASE}/tasks/${id}/events`, {
      headers: afterEventId ? { "Last-Event-ID": String(afterEventId) } : undefined,
      signal: controller.signal,
    });
    if (!response.ok || !response.body) throw new Error(response.statusText);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const idLine = block.split("\n").find(line => line.startsWith("id: "));
        const dataLine = block.split("\n").find(line => line.startsWith("data: "));
        if (dataLine) {
          const payload = JSON.parse(dataLine.slice(6)) as import("./types").SSEEvent;
          onEvent({
            id: Number(idLine?.slice(4) || 0), task_id: id,
            event_type: payload.type, payload, created_at: "",
          });
        }
      }
    }
  })().catch(error => {
    if ((error as Error).name !== "AbortError") console.error("任务事件恢复失败", error);
  });
  return controller;
}

// ── SSE streaming chat ──

export function streamChat(
  message: string,
  sessionId: string,
  responseMode: "detailed" | "concise",
  onEvent: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  replyToTurnId?: string,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(BASE + "/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId, response_mode: responseMode, reply_to_turn_id: replyToTurnId }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || response.statusText);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let sawDone = false;

      const emit = (raw: string) => {
        let event: SSEEvent;
        try {
          event = JSON.parse(raw) as SSEEvent;
        } catch {
          throw new Error("服务器返回了无法解析的 SSE 事件");
        }
        if (event.type === "done") sawDone = true;
        onEvent(event);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const dataLine = line.split("\n").find(part => part.startsWith("data: "));
          if (dataLine) {
            emit(dataLine.slice(6));
          }
        }
      }

      // Process remaining buffer
      const dataLine = buffer.trim().split("\n").find(part => part.startsWith("data: "));
      if (dataLine) {
        emit(dataLine.slice(6));
      }

      if (!sawDone) throw new Error("对话流在最终完成事件之前中断");
      onDone();
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError(err as Error);
      }
    }
  })();

  return controller;
}

// ── Report export ──

export function exportReport(messages: { role: string; content: string }[], title: string): Promise<string> {
  return fetch(BASE + "/report/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, title }),
  }).then(res => res.text());
}

export function createReport(
  sessionId: string, title: string, turnId?: string,
): Promise<ReportSummary> {
  return request<{ report: ReportSummary }>("/reports", {
    method: "POST", body: JSON.stringify({ session_id: sessionId, title, turn_id: turnId }),
  }).then(result => result.report);
}

export function fetchReports(): Promise<{ reports: ReportSummary[] }> {
  return request<{ reports: ReportSummary[] }>("/reports");
}

export function reportUrl(id: string): string {
  return `${BASE}/reports/${id}`;
}
