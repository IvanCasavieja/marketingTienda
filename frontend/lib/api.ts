import axios, { AxiosInstance } from "axios";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // sends httpOnly cookies on every request
});

// Auto-refresh on 401 — cookies are sent automatically, no token reading needed
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        await axios.post(`${BASE_URL}/auth/refresh`, {}, { withCredentials: true });
        return api(original);
      } catch {
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: (email: string, password: string, join_code?: string) =>
    api.post("/auth/login", { email, password, join_code: join_code || undefined }),
  register: (email: string, full_name: string, password: string, join_code?: string) =>
    api.post("/auth/register", { email, full_name, password, join_code: join_code || undefined }),
  me: () => api.get("/auth/me"),
  logout: () => api.post("/auth/logout"),
  joinTeam: (join_code: string) => api.post("/auth/join-team", { join_code }),
  teamMembers: () => api.get("/auth/team-members"),
  removeTeamMember: (userId: number) => api.delete(`/auth/team-members/${userId}`),
  updateTeamType: (team_type: string) => api.patch("/auth/team-group/type", { team_type }),
};

export const metricsApi = {
  sync: (platform: string, date_from: string, date_to: string) =>
    api.post("/metrics/sync", { platform, date_from, date_to }),
  getMetrics: (date_from: string, date_to: string, platforms?: string) =>
    api.get("/metrics/", { params: { date_from, date_to, platforms } }),
  getSummary: (date_from: string, date_to: string) =>
    api.get("/metrics/summary", { params: { date_from, date_to } }),
  getAutoSyncStatus: () =>
    api.get<{
      last_run: string | null;
      next_run: string | null;
      interval_hours: number;
      active: boolean;
    }>("/metrics/auto-sync/status"),
};

export const analyticsApi = {
  analyze: (platforms: string[], date_from: string, date_to: string, analysis_type: string) =>
    api.post("/analytics/analyze", { platforms, date_from, date_to, analysis_type }),
  streamAnalyze: (platforms: string[], date_from: string, date_to: string, analysis_type: string) =>
    fetch(`${BASE_URL}/analytics/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ platforms, date_from, date_to, analysis_type }),
    }),
  getHistory: () => api.get("/analytics/history"),
  getAnalysis: (id: number) => api.get(`/analytics/history/${id}`),
};

export const sfmcApi = {
  getEmail: (date_from: string, date_to: string) =>
    api.post("/sfmc/email", { date_from, date_to }),
  getWhatsApp: (date_from: string, date_to: string) =>
    api.post("/sfmc/whatsapp", { date_from, date_to }),
};

export const connectionsApi = {
  list: () => api.get("/connections/"),
  create: (data: object) => api.post("/connections/", data),
  delete: (id: number) => api.delete(`/connections/${id}`),
};

export const toolsApi = {
  generateCenefas: (formData: FormData) =>
    api.post("/tools/cenefas/generate", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      responseType: "blob",
    }),
  getCenefaTemplates: () => api.get("/tools/cenefas/templates"),
  createCenefaTemplate: (formData: FormData) =>
    api.post("/tools/cenefas/templates", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  deleteCenefaTemplate: (id: number) => api.delete(`/tools/cenefas/templates/${id}`),
  downloadExcelTemplate: () =>
    api.get("/tools/cenefas/template", { responseType: "blob" }),
  getBuiltinTemplates: () =>
    api.get<{ slug: string; name: string; format_name: string }[]>("/tools/cenefas/builtin-templates"),
};

export const chatApi = {
  sendMessage: (message: string, history: { role: string; content: string }[]) =>
    api.post<{ reply: string }>("/chat/message", { message, history }),
};

// ---------------------------------------------------------------------------
// Cenefas v2
// ---------------------------------------------------------------------------

import type {
  CenefaFormat,
  CenefaJob,
  CenefaTemplate,
  CenefaTemplateRecord,
} from "@/types/cenefas";

export const cenefasV2Api = {
  // Formatos del sistema
  getFormats: () => api.get<CenefaFormat[]>("/tools/cenefas/v2/formats"),

  // Templates
  listTemplates: () => api.get<CenefaTemplateRecord[]>("/tools/cenefas/v2/templates"),
  getTemplate: (id: string) =>
    api.get<CenefaTemplateRecord>(`/tools/cenefas/v2/templates/${id}`),
  createTemplate: (payload: CenefaTemplate) =>
    api.post<{ id: string; name: string; created_at: string }>(
      "/tools/cenefas/v2/templates",
      payload
    ),
  updateTemplate: (id: string, payload: CenefaTemplate) =>
    api.put<{ id: string; name: string }>(`/tools/cenefas/v2/templates/${id}`, payload),
  deleteTemplate: (id: string) =>
    api.delete(`/tools/cenefas/v2/templates/${id}`),

  // Jobs
  listJobs: () => api.get<CenefaJob[]>("/tools/cenefas/v2/jobs"),
  getJob: (id: string) => api.get<CenefaJob>(`/tools/cenefas/v2/jobs/${id}`),
  createJob: (formData: FormData) =>
    api.post<{ job_id: string; status: string; format: string }>(
      "/tools/cenefas/v2/jobs",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    ),
  downloadJob: (id: string) =>
    api.get(`/tools/cenefas/v2/jobs/${id}/download`, { responseType: "blob" }),

  // Validación
  validateCsv: (formData: FormData) =>
    api.post("/tools/cenefas/v2/validate", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  // Importar PPTX → definición v2
  importPptx: (formData: FormData) =>
    api.post<CenefaTemplate>("/tools/cenefas/v2/import-pptx", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),

  // Definiciones de templates predeterminados
  getBuiltinDefinitions: () =>
    api.get<{ slug: string; name: string; format_id: string; definition: CenefaTemplate }[]>(
      "/tools/cenefas/v2/builtin-definitions"
    ),
};
