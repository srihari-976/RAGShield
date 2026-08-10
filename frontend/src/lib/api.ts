import axios from "axios";
import type { AxiosResponse } from "axios";
import type {
  ConversationSummary,
  DocumentPermission,
  DocumentSummary,
  EvaluationRun,
  GoldenQuestion,
  IdentityInfo,
  MessageSummary,
  Policy,
  RoleInfo,
  TenantSummary,
  UserSummary,
} from "./types";

const API = "/api/v1";

const api = axios.create({ baseURL: API });

export const ACCESS_TOKEN_KEY = "ragshield_access";
export const REFRESH_TOKEN_KEY = "ragshield_refresh";

function getToken(key: string): string | null {
  return localStorage.getItem(key);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function getAccessToken() {
  return getToken(ACCESS_TOKEN_KEY);
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshPromise: Promise<string> | null = null;

async function doRefresh(): Promise<string> {
  const refresh = getToken(REFRESH_TOKEN_KEY);
  if (!refresh) throw new Error("no refresh token");
  const resp = await axios.post(`${API}/auth/refresh`, { refresh_token: refresh });
  setTokens(resp.data.access_token, resp.data.refresh_token);
  return resp.data.access_token;
}

api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry && getToken(REFRESH_TOKEN_KEY)) {
      original._retry = true;
      try {
        refreshPromise = refreshPromise || doRefresh();
        const token = await refreshPromise;
        refreshPromise = null;
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      } catch {
        refreshPromise = null;
        clearTokens();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

function errMsg(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const d = e.response?.data as { detail?: unknown };
    if (typeof d?.detail === "string") return d.detail;
    if (Array.isArray(d?.detail)) return d.detail.map((x) => (x as { msg?: string }).msg || JSON.stringify(x)).join("; ");
    return `${e.message}${e.response?.status ? ` (${e.response.status})` : ""}`;
  }
  return String(e);
}

// ---------- auth ----------
export async function login(username: string, password: string) {
  const form = new URLSearchParams({ username, password });
  const resp = await api.post("/auth/login", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  setTokens(resp.data.access_token, resp.data.refresh_token);
  return resp.data;
}

export async function getIdentity(): Promise<IdentityInfo> {
  const resp = await api.get("/auth/identity");
  return resp.data;
}

// ---------- tenants ----------
export const tenantsApi = {
  list: () => api.get<TenantSummary[], AxiosResponse<TenantSummary[]>>("/admin/tenants").then((r) => r.data),
  create: (body: Record<string, unknown>) => api.post<TenantSummary, AxiosResponse<TenantSummary>>("/admin/tenants", body).then((r) => r.data),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch<TenantSummary, AxiosResponse<TenantSummary>>(`/admin/tenants/${id}`, body).then((r) => r.data),
};

// ---------- users ----------
export const usersApi = {
  list: (tenantId?: string) =>
    api.get<UserSummary[], AxiosResponse<UserSummary[]>>("/admin/users", { params: { tenant_id: tenantId } }).then((r) => r.data),
  create: (body: Record<string, unknown>) => api.post<UserSummary, AxiosResponse<UserSummary>>("/admin/users", body).then((r) => r.data),
  update: (id: string, body: Record<string, unknown>) =>
    api.patch<UserSummary, AxiosResponse<UserSummary>>(`/admin/users/${id}`, body).then((r) => r.data),
  roles: () => api.get<RoleInfo[], AxiosResponse<RoleInfo[]>>("/admin/users/roles/list").then((r) => r.data),
  permissions: () => api.get<string[], AxiosResponse<string[]>>("/admin/users/permissions/list").then((r) => r.data),
};

// ---------- documents ----------
export const documentsApi = {
  list: () => api.get<DocumentSummary[], AxiosResponse<DocumentSummary[]>>("/admin/documents").then((r) => r.data),
  upload: (file: File, title: string, documentType: string, classification: string, acl?: Record<string, unknown>) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("document_type", documentType);
    form.append("classification", classification);
    if (acl) form.append("acl", JSON.stringify(acl));
    return api
      .post<DocumentSummary, AxiosResponse<DocumentSummary>>("/admin/documents/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  delete: (id: string) => api.delete(`/admin/documents/${id}`),
  reindex: (id: string) => api.post<DocumentSummary, AxiosResponse<DocumentSummary>>(`/admin/documents/${id}/reindex`).then((r) => r.data),
  replace: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post<DocumentSummary, AxiosResponse<DocumentSummary>>(`/admin/documents/${id}/replace`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  search: (query: string) =>
    api.get<DocumentSummary[], AxiosResponse<DocumentSummary[]>>("/admin/documents/search/query", { params: { q: query } }).then((r) => r.data),
};

// ---------- permissions ----------
export const permissionsApi = {
  document: (docId: string) =>
    api.get<DocumentPermission[], AxiosResponse<DocumentPermission[]>>(`/admin/permissions/documents/${docId}`).then((r) => r.data),
  grant: (docId: string, body: Record<string, unknown>) =>
    api.post<DocumentPermission, AxiosResponse<DocumentPermission>>(`/admin/permissions/documents/${docId}`, body).then((r) => r.data),
  revoke: (docId: string, permId: string) => api.delete(`/admin/permissions/documents/${docId}/${permId}`),
  policies: () => api.get<Policy[], AxiosResponse<Policy[]>>("/admin/permissions/policies").then((r) => r.data),
  createPolicy: (body: Record<string, unknown>) =>
    api.post<Policy, AxiosResponse<Policy>>("/admin/permissions/policies", body).then((r) => r.data),
  deletePolicy: (id: string) => api.delete(`/admin/permissions/policies/${id}`),
  testPolicy: (id: string, body: Record<string, unknown>) => api.post(`/admin/permissions/policies/${id}/test`, body),
};

// ---------- evaluation ----------
export const evaluationApi = {
  golden: () => api.get<GoldenQuestion[], AxiosResponse<GoldenQuestion[]>>("/admin/evaluation/golden").then((r) => r.data),
  createGolden: (body: Record<string, unknown>) => api.post("/admin/evaluation/golden", body),
  deleteGolden: (id: string) => api.delete(`/admin/evaluation/golden/${id}`),
  runs: () => api.get<EvaluationRun[], AxiosResponse<EvaluationRun[]>>("/admin/evaluation/runs").then((r) => r.data),
  run: (body: Record<string, unknown>) => api.post<EvaluationRun, AxiosResponse<EvaluationRun>>("/admin/evaluation/runs", body).then((r) => r.data),
  runItems: (runId: string) => api.get(`/admin/evaluation/runs/${runId}/items`),
  gate: (runId: string) => api.get("/admin/settings/evaluation-gate", { params: { run_id: runId } }),
  agreement: () => api.get("/admin/evaluation/agreement"),
  disagreements: () => api.get("/admin/evaluation/disagreements"),
  adjudications: () => api.get("/admin/evaluation/adjudications"),
  adjudicate: (body: Record<string, unknown>) => api.post("/admin/evaluation/adjudicate", body),
};

// ---------- observability ----------
export const observabilityApi = {
  latency: (hours = 24) => api.get("/admin/observability/latency", { params: { hours } }),
  traces: (limit = 100) => api.get("/admin/observability/traces", { params: { limit } }),
  security: (hours = 24) => api.get("/admin/observability/security", { params: { hours } }),
};

// ---------- audit ----------
export const auditApi = {
  logs: (limit = 100, action?: string) => api.get("/admin/audit/logs", { params: { limit, action } }),
  security: (limit = 100) => api.get("/admin/audit/security-events", { params: { limit } }),
};

// ---------- settings ----------
export const settingsApi = {
  prompts: () => api.get("/admin/settings/prompts"),
  createPrompt: (body: Record<string, unknown>) => api.post("/admin/settings/prompts", body),
  activatePrompt: (version: string) => api.post(`/admin/settings/prompts/${version}/activate`),
  experiments: () => api.get("/admin/settings/experiments"),
  createExperiment: (body: Record<string, unknown>) => api.post("/admin/settings/experiments", body),
  toggleExperiment: (id: string, active: boolean) =>
    api.post(`/admin/settings/experiments/${id}/toggle`, null, { params: { active } }),
};

// ---------- models ----------
export const modelsApi = {
  list: () => api.get("/models"),
  config: () => api.get("/admin/models/config"),
  update: (body: Record<string, unknown>) => api.post("/admin/models/config", body),
};

// ---------- chat ----------
export const chatApi = {
  conversations: () => api.get<ConversationSummary[], AxiosResponse<ConversationSummary[]>>("/chat/conversations").then((r) => r.data),
  messages: (id: string) => api.get<MessageSummary[], AxiosResponse<MessageSummary[]>>(`/chat/conversations/${id}`).then((r) => r.data),
};

export { errMsg };
