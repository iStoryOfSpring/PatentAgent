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
  active_generations?: number;
  trace_id?: string;
  dataset_snapshot?: DatasetVersion | null;
}

export interface DatasetVersion {
  dataset_id: string;
  version_id?: string;
  id?: string;
  content_hash: string;
  schema_version: string | number;
  adapter?: string;
  storage_path?: string;
  import_id?: string;
  import_report?: ImportReport;
  sources: string[];
  record_count: number;
  field_coverage: Record<string, number>;
  created_at?: string;
}

export interface DatasetRecord {
  id: string;
  name: string;
  source_root: string;
  status: "ready" | "archived";
  latest_version: DatasetVersion;
  version_count: number;
}

export interface DatasetImportStatus {
  id: string;
  status: "queued" | "parsing" | "completed" | "failed" | "interrupted";
  dataset_version_id?: string;
  error_category?: string;
  error?: string;
  metrics?: {
    progress?: number;
    stage?: string;
    dataset_id?: string;
    dataset_version_id?: string;
    record_count?: number;
    deduplicated?: boolean;
    warnings?: string[];
    file_detections?: ImportReport["file_detections"];
  };
  created_at: string;
  updated_at: string;
}

export interface CapabilityDefinition {
  id: string;
  name: string;
  icon: string;
  description: string;
  tool_names: string[];
  prompts: string[];
  availability: "available" | "partial" | "unavailable";
  available_tool_count: number;
  tool_count: number;
  tools: { name: string; available: boolean; reason?: string }[];
}

export interface ReportSummary {
  id: string;
  session_id: string;
  turn_id?: string | null;
  title: string;
  format: "html";
  created_at: string;
  download_url?: string;
}

export type TaskState =
  | "created" | "queued" | "planning" | "planned" | "waiting_approval" | "running"
  | "validating" | "synthesizing" | "completed" | "partial" | "failed"
  | "cancelling" | "cancelled" | "interrupted" | "awaiting_clarification";

export interface ErrorInfo {
  category: "data_insufficient" | "input_validation" | "algorithm_failure"
    | "provider_failure" | "synthesis_failure" | "system_failure";
  message: string;
  recoverable: boolean;
  details?: Record<string, unknown>;
}

export interface ExecutionMetrics {
  duration_ms: number;
  cache_hit: boolean;
  retry_count: number;
}

export interface ToolProvenance {
  dataset_id: string;
  dataset_version_id: string;
  dataset_content_hash: string;
  input_count: number;
  analyzed_count: number;
  sampled: boolean;
  sampling_strategy: string | null;
  missing_field_rates: Record<string, number>;
  algorithm: string;
  algorithm_version: string;
  parameters: Record<string, unknown>;
}

export interface AgentTask extends Record<string, unknown> {
  id: string;
  session_id: string;
  status: TaskState;
  trace_id?: string;
  cancel_requested?: boolean;
  error_category?: ErrorInfo["category"];
}

export interface TaskEvent {
  id: number;
  task_id: string;
  event_type: string;
  payload: SSEEvent | Record<string, unknown>;
  created_at: string;
}

export interface DataSummary {
  total_patents: number;
  year_range: [number, number];
  ipc_sections: string[];
  top_applicants: { name: string; count: number }[];
  adapter?: string;
  field_coverage?: Record<string, number>;
  warnings?: string[];
  data_as_of?: string;
  source_capabilities?: Record<string, SourceCapabilities>;
  unsupported_conclusions?: string[];
  import_report?: ImportReport;
}

export interface SourceCapabilities {
  bibliographic: boolean;
  multilingual_text: boolean;
  claims: boolean;
  description: boolean;
  classifications: boolean;
  citations: boolean;
  family: boolean;
  legal_events: boolean;
  prosecution_events: boolean;
  current_legal_status: boolean;
}

export interface ImportReport {
  source_formats: string[];
  files_seen: number;
  records_expected: number;
  records_detected: number;
  records_succeeded: number;
  records_parsed: number;
  records_imported: number;
  records_failed: number;
  records_skipped: number;
  duplicates_merged: number;
  field_conflicts: number;
  field_coverage: Record<string, number>;
  language_distribution: Record<string, number>;
  source_capabilities: Record<string, SourceCapabilities>;
  file_detections: {
    file: string;
    source_format: string;
    method: "manifest" | "user_selected" | "content_signature" | "unknown";
    matched: boolean;
  }[];
  issues: { file: string; record_id: string; location: string; code: string; message: string; sample_hash: string }[];
  warnings: string[];
  parse_rate: number;
  quarantine_path: string;
}

export interface SearchCapabilityStatus {
  model_id: string;
  dependency_installed: boolean;
  model_cached: boolean;
  model_cache_directory: string;
  index_cache_directory: string;
  index_count: number;
  download_size_mb: number;
  modes: ["lexical", "multilingual_hybrid_beta"];
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
  definition?: Record<string, unknown>;
}

export interface ToolResult {
  result_type: string;
  chart_html: string | null;
  summary: string;
  methodology: string;
  data_quality: Record<string, unknown>;
  warnings: string[];
  result_metadata: Record<string, unknown>;
  provenance?: ToolProvenance;
  metrics?: ExecutionMetrics;
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
  probe_status: "not_tested" | "passed" | "failed";
  probe_error_category: string;
  last_probe_at: string;
  created_at: string;
  updated_at: string;
}

export interface ProviderCredentials {
  api_key: string;
  sensitive_headers: Record<string, string>;
}

export interface ProviderProbeResult {
  status: "passed" | "connected" | "failed";
  profile?: ProviderProfile;
  model?: string;
  latency_ms?: number;
  stages?: Record<string, { status: string; latency_ms?: number }>;
  capabilities?: Record<string, unknown>;
  error_category?: string;
  message?: string;
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
  dataset_version_id: string;
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
  provenance?: ToolProvenance;
  metrics?: ExecutionMetrics;
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
  dataset_version_id?: string;
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
  turn_id?: string;
  dataset_version_id?: string;
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
  turn_id?: string;
  dataset_version_id?: string;
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
  plan?: { steps: Record<string, unknown>[]; costWeight?: number };
}
