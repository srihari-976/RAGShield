export interface UserSummary {
  id: string;
  tenant_id: string;
  username: string;
  email: string;
  full_name: string | null;
  department: string | null;
  is_active: boolean;
  is_admin: boolean;
  roles: string[];
  created_at: string;
}

export interface IdentityInfo {
  user_id: string;
  tenant_id: string;
  username: string;
  full_name: string | null;
  roles: string[];
  permissions: string[];
  is_admin: boolean;
}

export interface TenantSummary {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  user_count: number;
  document_count: number;
}

export interface DocumentSummary {
  id: string;
  tenant_id: string;
  title: string;
  document_type: string;
  owner_id: string;
  classification: string;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number;
  status: string;
  error_message: string | null;
  chunk_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentPermission {
  id: string;
  document_id: string;
  action: string;
  principal_type: string;
  principal_id: string | null;
}

export interface Policy {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  action: string;
  rule: string;
  effect: string;
  priority: number;
  is_active: boolean;
}

export interface RoleInfo {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface MessageSummary {
  id: string;
  role: string;
  content: string;
  created_at: string;
  latency_ms: number | null;
  grounded: boolean | null;
  abstained: boolean | null;
  metadata_json: string | null;
}

export interface ModelConfig {
  id: string;
  name: string;
  type: string;
  provider: string;
  model: string;
  base_url: string | null;
  is_active: boolean;
  context_window: number;
  temperature: number;
  top_p: number;
  max_tokens: number;
  timeout: number;
  metadata: Record<string, unknown> | null;
}

export interface TraceItem {
  request_id: string;
  tenant_id: string;
  user_id: string;
  model: string | null;
  route_version: string | null;
  total_ms: number;
  status: string;
  started_at: string;
  spans: unknown[];
}

export interface AuditEntry {
  id: string;
  tenant_id: string;
  user_id: string | null;
  username: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  decision: string | null;
  query_text: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  request_id: string | null;
}

export interface LatencyStats {
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  avg_ms: number;
  count: number;
  window_hours: number;
}

export interface EvaluationRun {
  id: string;
  name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  metrics: Record<string, unknown> | null;
  question_count: number;
  created_by: string | null;
}

export interface GoldenQuestion {
  id: string;
  question: string;
  reference_answer: string | null;
  expected_document_ids: string[] | null;
  created_at: string;
}

export interface SecurityMatrix {
  name: string;
  passed: boolean;
  details: string;
}

export interface EvaluationGate {
  enabled: boolean;
  thresholds: Record<string, number>;
}

export interface PromptVersion {
  id: string;
  name: string;
  version: number;
  content: string;
  is_active: boolean;
  updated_at: string;
}
