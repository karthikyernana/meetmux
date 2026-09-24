/**
 * Typed API client for PlanGuard backend.
 * All requests go through /api/v1 (proxied by Vite dev server).
 */

const BASE = "/api/v1";

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = res.statusText;
    try {
      const err = await res.json();
      code = err.error_code ?? code;
      message = err.message ?? message;
    } catch {}
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Typed response types ────────────────────────────────────────────────────

export interface WorkspaceOut {
  id: string;
  name: string;
  environment_label: string;
  status: string;
  created_at: string;
  updated_at: string;
  connection_state: string | null;
  last_snapshot_at: string | null;
  open_recommendation_count: number;
}

export interface ConnectionCreate {
  host: string;
  port: number;
  database_name: string;
  username: string;
  password: string;
  ssl_mode: string;
}

export interface CapabilityCheck {
  name: string;
  status: "ok" | "warning" | "failed";
  detail: string | null;
}

export interface ConnectionTestResult {
  success: boolean;
  server_version: string | null;
  capabilities: CapabilityCheck[];
  error: string | null;
}

export interface ConnectionOut {
  id: string;
  workspace_id: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  ssl_mode: string;
  server_version: string | null;
  capability_status: Record<string, { status: string; detail: string | null }> | null;
  created_at: string;
  updated_at: string;
}

export interface QueryFingerprintOut {
  id: string;
  workspace_id: string;
  queryid: number | null;
  normalized_sql: string;
  current_database: string | null;
  workload_impact_score: number | null;
  calls: number | null;
  mean_exec_time: number | null;
  total_exec_time: number | null;
  contains_seq_scan: boolean;
  recommendation_status: string | null;
  state: string;
}

export interface PlanNodeOut {
  node_type: string;
  relation_name: string | null;
  startup_cost: number;
  total_cost: number;
  plan_rows: number;
  actual_rows: number | null;
  filter: string | null;
  index_cond: string | null;
  sort_key: string[] | null;
  children: PlanNodeOut[];
}

export interface ExperimentOut {
  id: string;
  candidate_id: string;
  status: string;
  hypopg_available: boolean;
  before_cost: number | null;
  after_cost: number | null;
  before_sort_nodes: number | null;
  after_sort_nodes: number | null;
  plan_changed: boolean | null;
  plan_diff: {
    plan_changed: boolean;
    scan_change?: { before: string; after: string };
    cost?: { before: number; after: number; reduction_ratio: number };
    sort?: { before: number; after: number };
    rows?: { before: number; after: number };
  } | null;
  storage_estimate_bytes: number | null;
  before_plan_json: unknown | null;
  after_plan_json: unknown | null;
  error_code: string | null;
  error_message: string | null;
}

export interface RecommendationOut {
  id: string;
  candidate_id: string;
  experiment_id: string | null;
  workspace_id: string;
  status: "RECOMMENDED" | "REVIEW_REQUIRED" | "INCONCLUSIVE" | "REJECTED";
  score: number | null;
  benefit_score: number | null;
  storage_penalty: number | null;
  write_penalty: number | null;
  overlap_penalty: number | null;
  evidence_quality: "HIGH" | "MEDIUM" | "LOW" | null;
  reason_codes: string[];
  explanation: string | null;
  ai_explanation: string | null;
  jev_review_path: string | null;
  created_at: string;
}

export interface MigrationArtifactOut {
  id: string;
  recommendation_id: string;
  sql_text: string;
  rollback_sql_text: string | null;
  index_name: string;
  created_at: string;
  version: number;
}

export interface JobOut {
  job_id: string;
  status: string;
}

// ── API Methods ─────────────────────────────────────────────────────────────

export const api = {
  // Workspaces
  workspaces: {
    list: () => request<WorkspaceOut[]>("GET", "/workspaces"),
    get: (id: string) => request<WorkspaceOut>("GET", `/workspaces/${id}`),
    create: (body: { name: string; environment_label?: string }) =>
      request<WorkspaceOut>("POST", "/workspaces", body),
    update: (id: string, body: { name?: string; environment_label?: string }) =>
      request<WorkspaceOut>("PATCH", `/workspaces/${id}`, body),
    delete: (id: string) => request<void>("DELETE", `/workspaces/${id}`),
  },

  // Connections
  connections: {
    test: (workspaceId: string, body: ConnectionCreate) =>
      request<ConnectionTestResult>("POST", `/workspaces/${workspaceId}/connection/test`, body),
    save: (workspaceId: string, body: ConnectionCreate) =>
      request<ConnectionOut>("POST", `/workspaces/${workspaceId}/connection`, body),
    status: (workspaceId: string) =>
      request<ConnectionOut>("GET", `/workspaces/${workspaceId}/connection/status`),
  },

  // Snapshots / workload
  snapshots: {
    capture: (workspaceId: string) =>
      request<JobOut>("POST", `/workspaces/${workspaceId}/snapshots`),
    list: (workspaceId: string) =>
      request<object[]>("GET", `/workspaces/${workspaceId}/snapshots`),
  },

  // Queries
  queries: {
    list: (workspaceId: string, params?: Record<string, string>) => {
      const qs = params ? `?${new URLSearchParams(params)}` : "";
      return request<QueryFingerprintOut[]>("GET", `/workspaces/${workspaceId}/queries${qs}`);
    },
    get: (workspaceId: string, queryId: string) =>
      request<QueryFingerprintOut>("GET", `/workspaces/${workspaceId}/queries/${queryId}`),
    analyze: (workspaceId: string, queryId: string) =>
      request<JobOut>("POST", `/workspaces/${workspaceId}/queries/${queryId}/analyze`),
    candidates: (workspaceId: string, queryId: string) =>
      request<object[]>("GET", `/workspaces/${workspaceId}/queries/${queryId}/candidates`),
    generateCandidates: (workspaceId: string, queryId: string) =>
      request<JobOut>("POST", `/workspaces/${workspaceId}/queries/${queryId}/candidates`),
  },

  // Experiments
  experiments: {
    create: (candidateId: string, queryFingerprintId: string) =>
      request<ExperimentOut>("POST", "/experiments", { candidate_id: candidateId, query_fingerprint_id: queryFingerprintId }),
    get: (id: string) => request<ExperimentOut>("GET", `/experiments/${id}`),
    run: (id: string) => request<JobOut>("POST", `/experiments/${id}/run`),
  },

  // Recommendations
  recommendations: {
    list: (workspaceId: string) =>
      request<RecommendationOut[]>("GET", `/workspaces/${workspaceId}/recommendations`),
    get: (id: string) => request<RecommendationOut>("GET", `/recommendations/${id}`),
    generateMigration: (id: string) =>
      request<MigrationArtifactOut>("POST", `/recommendations/${id}/migration`),
  },

  // Indexes
  indexes: {
    list: (workspaceId: string) =>
      request<object[]>("GET", `/workspaces/${workspaceId}/indexes`),
  },

  // Jobs
  jobs: {
    get: (id: string) => request<JobOut>("GET", `/jobs/${id}`),
  },
};
