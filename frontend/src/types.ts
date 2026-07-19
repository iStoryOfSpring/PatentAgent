// ── API response types ──

export interface HealthResponse {
  status: string;
  patents_loaded: number;
  year_range: [number, number] | null;
  tools: number;
  agent_configured: boolean;
  selected_profile?: ProviderProfile | null;
  connected_profile?: Pick<ProviderProfile, "id" | "name" | "protocol" | "model"> | null;
  credential_loaded?: boolean;
  llm_capabilities?: Record<string, unknown>;
}

export interface DataSummary {
  total_patents: number;
  year_range: [number, number];
  ipc_sections: string[];
  top_applicants: { name: string; count: number }[];
  adapter?: string;
  field_coverage?: Record<string, number>;
  warnings?: string[];
}

export interface ToolParameter {
  type: "string" | "integer" | "array";
  description?: string;
  required?: boolean;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  items?: { type: string };
}

export interface Tool {
  name: string;
  description: string;
  parameters: Record<string, ToolParameter>;
  methodology?: string;
  evidence_level?: string;
  cost_weight?: number;
  returned_fields?: string[];
  availability?: {
    available: boolean;
    reason?: string;
    field_coverage?: Record<string, number>;
  };
}

export interface ToolResult {
  result_type: string;
  chart_html: string | null;
  summary: string;
  methodology: string;
  data_quality: Record<string, unknown>;
  warnings: string[];
  result_metadata: Record<string, unknown>;
  [key: string]: unknown;  // type-specific fields
}

export interface LLMConfig {
  provider: string;   // "Claude" | "OpenAI" | "DeepSeek"
  api_key: string;
  base_url: string;
  model?: string;
}

export type ProviderProtocol = "openai_chat" | "anthropic_messages" | "deepseek_chat";
export type ProviderAuthMode = "bearer" | "x_api_key" | "custom_header" | "none";
export type ReasoningEffort = "default" | "low" | "medium" | "high" | "max";
export type ThinkingMode = "auto" | "enabled" | "disabled";

export interface ProviderHeader {
  name: string;
  value: string;
  sensitive: boolean;
  credential_loaded?: boolean;
}

export interface ProviderProfileInput {
  name: string;
  protocol: ProviderProtocol;
  notes: string;
  website_url: string;
  base_url: string;
  model: string;
  selected: boolean;
  auth_mode: ProviderAuthMode;
  auth_header_name: string;
  auth_prefix: string;
  timeout_seconds: number;
  max_retries: number;
  max_output_tokens: number;
  temperature: number | null;
  reasoning_effort: ReasoningEffort;
  thinking_mode: ThinkingMode;
  model_discovery_path: string;
  extra_headers: ProviderHeader[];
  extra_body: Record<string, unknown>;
}

export interface ProviderProfile extends ProviderProfileInput {
  id: string;
  schema_version: number;
  credential_loaded: boolean;
  connected: boolean;
  needs_reconnect: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderCredentials {
  api_key: string;
  sensitive_headers: Record<string, string>;
}

export interface ProviderProbeResult {
  status: "passed" | "connected";
  profile?: ProviderProfile;
  model?: string;
  latency_ms?: number;
  stages?: Record<string, { status: string; latency_ms?: number }>;
  capabilities: Record<string, unknown>;
}

export interface FollowupSuggestion {
  text: string;
  kind: "explain" | "drilldown" | "new_analysis" | "method" | "clarification_default";
  requires_new_tools: boolean;
  evidence_ref: string | null;
}

export interface SessionSummary {
  id: string;
  name: string;
  dataset_fingerprint: string;
  status: string;
  created_at: string;
  updated_at: string;
  turn_count?: number;
}

export interface StoredMessage {
  id: number;
  turn_id: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface StoredExecution {
  id: string;
  turn_id: string;
  tool_name: string;
  parameters?: Record<string, unknown>;
  status: "completed" | "failed" | "skipped";
  result?: Record<string, unknown>;
  error?: string;
  duration_ms?: number;
  stale?: boolean;
}

export interface SessionDetail {
  session: SessionSummary;
  messages: StoredMessage[];
  turns: Record<string, unknown>[];
  tool_executions: StoredExecution[];
}

// ── SSE event types ──

export interface SSEIntent {
  type: "intent";
  goal: string;
  analysis_type: string;
  turn_id?: string;
}

export interface SSEPlan {
  type: "plan";
  steps: Record<string, unknown>[];
  decision_source?: "llm" | string;
  tool_calls?: Record<string, unknown>[];
  reused_evidence?: string[];
  validation_status?: string;
  cost_weight?: number;
  requires_confirmation?: boolean;
  provider?: string;
  model?: string;
  request_id?: string;
  usage?: Record<string, number>;
  finish_reason?: string;
}

export interface SSEStep {
  type: "step";
  tool: string;
  status: "running" | "completed" | "failed" | "skipped";
  duration_ms: number;
  chart_html: string | null;
  error: string | null;
  parameters: Record<string, unknown>;
  result: Record<string, unknown> | null;
  summary: string;
  methodology: string;
  data_quality: Record<string, unknown>;
  warnings: string[];
  execution_id?: string;
  origin?: string;
  reused_from_execution_id?: string | null;
  turn_id?: string;
}

export interface SSESynthesis {
  type: "synthesis";
  status: "started" | "retrying" | "fallback";
  turn_id: string;
}

export interface SSEClarification {
  type: "clarification";
  turn_id: string;
  question: string;
  missing_fields: string[];
  allow_defaults: boolean;
}

export interface SSEText {
  type: "text";
  content: string;
}

export interface SSEStrategy {
  type: "strategy";
  report: { recommendations?: { category: string; recommendation: string; urgency: number }[] };
}

export interface SSEDone {
  type: "done";
  session_id: string;
  result_coverage: Record<string, unknown>[];
  coverage_complete: boolean;
  turn_id: string;
  final_status: "completed" | "partial" | "failed" | "awaiting_clarification";
  answer_present: boolean;
  new_execution_ids: string[];
  reused_execution_ids: string[];
  answer_format?: "markdown";
  normalization_mode?: "native" | "llm_repair" | "local_repair" | "fallback";
  followup_questions?: string[];
  followup_suggestions?: FollowupSuggestion[];
}

export interface SSEError {
  type: "error";
  tool?: string;
  message: string;
  recoverable: boolean;
  turn_id?: string;
}

export type SSEEvent = SSEIntent | SSEPlan | SSEStep | SSESynthesis | SSEClarification | SSEText | SSEStrategy | SSEDone | SSEError;

// ── UI types ──

export interface ToolStep {
  id: string;
  tool: string;
  status: "running" | "completed" | "failed" | "skipped";
  duration_ms?: number;
  chart_html?: string | null;
  error?: string | null;
  summary?: string;
  methodology?: string;
  data_quality?: Record<string, unknown>;
  warnings?: string[];
  parameters?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  execution_id?: string;
  origin?: string;
  stale?: boolean;
}

export interface Rec {
  category: string;
  recommendation: string;
  urgency: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  intent?: string;
  steps?: ToolStep[];
  recommendations?: Rec[];
  turnId?: string;
  finalStatus?: "completed" | "partial" | "failed" | "awaiting_clarification" | "cancelled";
  streamStatus?: string;
  error?: string;
  followupQuestions?: string[];
  followupSuggestions?: FollowupSuggestion[];
  clarification?: { turnId: string; missingFields: string[]; allowDefaults: boolean };
  canResynthesize?: boolean;
}
