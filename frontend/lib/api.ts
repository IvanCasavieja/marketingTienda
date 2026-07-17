import axios, { AxiosInstance } from "axios";
import type { Ga4FunnelResponse } from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ── Token storage ─────────────────────────────────────────────────────────────
// On mobile browsers (especially Safari iOS) cross-site httpOnly cookies are
// blocked by ITP / Private Browsing even when SameSite=None; Secure is set.
// We store the access token in localStorage as fallback so auth works on all
// platforms. The backend accepts both cookie AND Authorization header.
const TOKEN_KEY = "mktg_at";

export function saveAccessToken(token: string): void {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, token);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearAccessToken(): void {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

// El backend exige este header en cualquier request que escriba/borre datos
// (POST/PUT/PATCH/DELETE) — una cookie sola puede viajar en un request
// cross-site forjado por otro sitio (CSRF), pero nadie fuera de nuestro
// propio origen puede leer este token de localStorage para forjar el header.
// Los fetch() crudos de este archivo (streaming) no pasan por el interceptor
// de axios, así que necesitan agregarlo a mano.
function authHeader(): Record<string, string> {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── Axios instance ────────────────────────────────────────────────────────────
export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // still send cookies when the browser supports them
});

// Request interceptor: attach token as Authorization header (fallback for mobile)
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token && !config.headers["Authorization"]) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        const refreshRes = await axios.post(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true },
        );
        // Save new token from refresh response if present (mobile path)
        const newToken = refreshRes.data?.access_token;
        if (newToken) saveAccessToken(newToken);
        return api(original);
      } catch {
        clearAccessToken();
        if (typeof window !== "undefined") window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (email: string, password: string) => {
    const res = await api.post("/auth/login", { email, password });
    // Save access_token from body — works even when cookies are blocked (mobile)
    if (res.data?.access_token) saveAccessToken(res.data.access_token);
    return res;
  },
  register: (email: string, full_name: string, password: string) =>
    api.post("/auth/register", { email, full_name, password }),
  me: () => api.get("/auth/me"),
  logout: async () => {
    clearAccessToken();
    return api.post("/auth/logout");
  },
  forgotPassword: (email: string) => api.post("/auth/forgot-password", { email }),
  resetPassword: (token: string, new_password: string) =>
    api.post("/auth/reset-password", { token, new_password }),
  changePassword: async (current_password: string, new_password: string) => {
    const res = await api.post("/auth/change-password", { current_password, new_password });
    // El backend invalida el token viejo al cambiar la contraseña (por
    // seguridad) y emite uno nuevo en la misma respuesta — sin guardarlo acá,
    // la siguiente request se cae con 401 y el interceptor manda a /login,
    // como si cambiar la contraseña te hubiera desconectado.
    if (res.data?.access_token) saveAccessToken(res.data.access_token);
    return res;
  },
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
  getGa4Funnel: (date_from: string, date_to: string) =>
    api.get<Ga4FunnelResponse>("/metrics/ga4-funnel", { params: { date_from, date_to } }),
  getSpendByObjective: (date_from: string, date_to: string) =>
    api.get("/metrics/spend-by-objective", { params: { date_from, date_to } }),
};

export const analyticsApi = {
  streamDebate: (platforms: string[], date_from: string, date_to: string, user_prompt: string = "", signal?: AbortSignal) =>
    fetch(`${BASE_URL}/analytics/analyze/debate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      credentials: "include",
      signal,
      body: JSON.stringify({ platforms, date_from, date_to, analysis_type: "debate", user_prompt }),
    }),
  streamDebateTurn: (
    platforms: string[], date_from: string, date_to: string,
    history: object[], user_message: string,
    signal?: AbortSignal,
    conversation_id?: number | null,
    date_from_2?: string, date_to_2?: string,
  ) =>
    fetch(`${BASE_URL}/analytics/debate/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      credentials: "include",
      signal,
      body: JSON.stringify({
        platforms, date_from, date_to, history, user_message,
        ...(conversation_id ? { conversation_id } : {}),
        ...(date_from_2 && date_to_2 ? { date_from_2, date_to_2 } : {}),
      }),
    }),
  streamDebateVerdict: (
    platforms: string[], date_from: string, date_to: string,
    history: object[],
    signal?: AbortSignal,
    conversation_id?: number | null,
    date_from_2?: string, date_to_2?: string,
  ) =>
    fetch(`${BASE_URL}/analytics/debate/verdict`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      credentials: "include",
      signal,
      body: JSON.stringify({
        platforms, date_from, date_to, history,
        ...(conversation_id ? { conversation_id } : {}),
        ...(date_from_2 && date_to_2 ? { date_from_2, date_to_2 } : {}),
      }),
    }),
  getHistory: () => api.get("/analytics/history"),
  getAnalysis: (id: number) => api.get(`/analytics/history/${id}`),
  getAvailablePlatforms: () => api.get("/analytics/available-platforms"),
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
  delete: (id: number, current_password: string) =>
    api.delete(`/connections/${id}`, { data: { current_password } }),
};

export const toolsApi = {
  getCenefaTemplates: () => api.get("/tools/cenefas/templates"),
  createCenefaTemplate: (formData: FormData) =>
    api.post("/tools/cenefas/templates", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  deleteCenefaTemplate: (id: number) => api.delete(`/tools/cenefas/templates/${id}`),
  downloadCenefaTemplate: (id: number) =>
    api.get(`/tools/cenefas/templates/${id}/download`, { responseType: "blob" }),
  downloadExcelTemplate: (destino: "redexpres" | "rompe_precios" = "redexpres") =>
    api.get("/tools/cenefas/template", { params: { destino }, responseType: "blob" }),
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
  ComponentBounds,
} from "@/types/cenefas";

export const cenefasV2Api = {
  // Formatos del sistema
  getFormats: () => api.get<CenefaFormat[]>("/tools/cenefas/v2/formats"),

  // Templates
  listTemplates: (params?: { category?: string }) =>
    api.get<CenefaTemplateRecord[]>("/tools/cenefas/v2/templates", { params }),
  getTemplate: (id: string) =>
    api.get<CenefaTemplateRecord>(`/tools/cenefas/v2/templates/${id}`),
  createTemplate: (payload: CenefaTemplate & { category?: string; source_pptx_b64?: string }) =>
    api.post<{ id: string; name: string; created_at: string }>(
      "/tools/cenefas/v2/templates",
      payload
    ),
  updateTemplate: (id: string, payload: CenefaTemplate) =>
    api.put<{ id: string; name: string }>(`/tools/cenefas/v2/templates/${id}`, payload),
  renameTemplate: (id: string, name: string) =>
    api.patch<{ id: string; name: string }>(`/tools/cenefas/v2/templates/${id}/rename`, { name }),
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
  confirmJob: (id: string, components: { id: string; base_bounds: ComponentBounds }[]) =>
    api.post<{ job_id: string; status: string }>(
      `/tools/cenefas/v2/jobs/${id}/confirm`,
      { components }
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

// ---------------------------------------------------------------------------
// Convertidor de Excel
// ---------------------------------------------------------------------------

export interface ConvertidorRow {
  row_id: number;
  codigo: string;
  nombre_articulo: string;
  descripcion: string;
  moneda: string;
  precio_anterior: number | null;
  precio_anterior_raw: string;
  precio: number | null;
  precio_raw: string;
  oferta: string;
  oferta_det: string;
  descripcion_web: string;
  vigencia: string;
  aclaracion1: string;
  aclaracion2: string;
  aclaracion3: string;
  matched: boolean;
  warnings: string[];
}

export interface ConvertidorSummary {
  total: number;
  matched_count: number;
  unmatched_count: number;
  learned_count: number;
}

export interface ConvertidorPreviewResponse extends ConvertidorSummary {
  rows: ConvertidorRow[];
}

export interface DescripcionSugerencia {
  row_id: number;
  codigo: string;
  descripcion: string;
  too_long: boolean;
}

export interface GenerarDescripcionesIAResponse {
  suggestions: DescripcionSugerencia[];
  failed_row_ids: number[];
  requested_count: number;
  processed_count: number;
  truncated: boolean;
}

export interface SkuDescripcionItem {
  sku: string;
  descripcion: string;
  updated_at: string | null;
}

export const convertidorApi = {
  preview: (formData: FormData) =>
    api.post<ConvertidorPreviewResponse>("/tools/cenefas/convertidor/preview", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  updateDescripcion: (sku: string, descripcion: string) =>
    api.patch<{ sku: string; descripcion: string }>(
      `/tools/cenefas/convertidor/descripciones/${encodeURIComponent(sku)}`,
      { descripcion }
    ),
  listarDescripciones: (q?: string, limit = 100, offset = 0) =>
    api.get<{ items: SkuDescripcionItem[]; total: number }>("/tools/cenefas/convertidor/descripciones", {
      params: { q: q || undefined, limit, offset },
    }),
  export: (rows: ConvertidorRow[], destino: string = "redexpres") =>
    api.post("/tools/cenefas/convertidor/export", { rows, destino }, { responseType: "blob" }),
  generarDescripcionesIA: (
    rows: { row_id: number; codigo: string; nombre_articulo: string; descripcion_web: string }[]
  ) =>
    api.post<GenerarDescripcionesIAResponse>("/tools/cenefas/convertidor/descripciones/generar-ia", { rows }),
};

export type TininContexto = "convertidor" | "rompe_precios" | "redexpres";

export interface TininConsultarResponse {
  respuesta: string;
}

export const tininApi = {
  consultar: (
    mensaje: string,
    historial: { role: "user" | "assistant"; content: string }[],
    contexto?: TininContexto
  ) =>
    api.post<TininConsultarResponse>("/tools/cenefas/convertidor/tinin/consultar", {
      mensaje,
      historial,
      contexto,
    }),
};

// ---------------------------------------------------------------------------
// Precios — catálogo de supermercados uruguayos
// ---------------------------------------------------------------------------

export interface ProductoVivo {
  tienda:          string;
  url:             string;
  nombre:          string | null;
  precio:          number | null;
  precio_lista:    number | null;
  sku:             string | null;
  barcode:         string | null;
  marca:           string | null;
  categoria:       string | null;
  sucursal_id:     string | null;
  sucursal_nombre: string | null;
  relevancia:      number;
  moneda:          string | null;
  tienda_real:     string | null;
}

export interface BuscarVivoResponse {
  query: string;
  total: number;
  items: ProductoVivo[];
}

export interface ConsultarIAResponse {
  tipo: "seleccion" | "respuesta";
  mantener: number[] | null;
  respuesta: string;
}

export interface ReporteIAResponse {
  reporte: string;
}

export const preciosApi = {
  buscarVivo: (q: string) =>
    api.get<BuscarVivoResponse>("/precios/buscar-vivo", { params: { q } }),

  buscarVivoStream: async (q: string, signal?: AbortSignal, cadenas?: string[]): Promise<Response> => {
    const doFetch = () => {
      const token = getAccessToken();
      const params = new URLSearchParams({ q });
      if (cadenas && cadenas.length > 0) params.set("cadenas", cadenas.join(","));
      return fetch(
        `${BASE_URL}/precios/buscar-vivo-stream?${params.toString()}`,
        {
          headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          credentials: "include",
          signal,
        },
      );
    };

    let response = await doFetch();
    if (response.status === 401) {
      try {
        const refreshRes = await axios.post(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true },
        );
        const newToken = refreshRes.data?.access_token;
        if (newToken) saveAccessToken(newToken);
        response = await doFetch();
      } catch {
        clearAccessToken();
        if (typeof window !== "undefined") window.location.href = "/login";
      }
    }
    return response;
  },

  consultarIA: (
    termino: string,
    items: { tienda: string; nombre: string; precio: number; moneda: string }[],
    mensaje: string,
  ) =>
    api.post<ConsultarIAResponse>("/precios/ia/consultar", { termino, items, mensaje }),

  generarReporteIA: (
    items: { tienda: string; nombre: string; precio: number; moneda: string }[],
    nuestro_precio?: number | null,
    nuestra_moneda?: string | null,
  ) =>
    api.post<ReporteIAResponse>("/precios/ia/reporte", { items, nuestro_precio, nuestra_moneda }),

  cotizacionDolar: () => api.get<CotizacionDolar>("/precios/cotizacion-dolar"),

};

export interface CotizacionDolar {
  fecha:   string;
  compra:  number;
  venta:   number;
  fuente:  string;
}

// ---------------------------------------------------------------------------
// Listas de monitoreo + notificaciones
// ---------------------------------------------------------------------------

export interface WatchlistItem {
  id: number;
  watchlist_id: number;
  tienda: string;
  sku: string | null;
  nombre: string;
  termino_busqueda: string;
  url: string;
  precio_actual: number;
  moneda: string;
  sucursal_id: string | null;
  sucursal_nombre: string | null;
  ultimo_chequeo: string | null;
  created_at: string | null;
}

export type WatchlistEstado = "activa" | "finalizada";

export interface WatchlistConItems {
  id: number;
  nombre: string;
  created_at: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  estado: WatchlistEstado;
  es_propia: boolean;
  compartida_por: string | null;
  items: WatchlistItem[];
}

export interface WatchlistHistorialFila {
  producto: string;
  tienda: string;
  precio: number;
  moneda: string;
  checked_at: string | null;
}

export interface UsuarioCompartible {
  id: number;
  email: string;
  full_name: string;
}

export interface Notificacion {
  id: number;
  tipo: string;
  mensaje: string;
  leida: boolean;
  watchlist_item_id: number | null;
  origen_tipo: string | null;
  origen_ref: string | null;
  created_at: string | null;
}

export const watchlistApi = {
  listar: () => api.get<WatchlistConItems[]>("/watchlist"),
  crear: (nombre: string, fecha_fin?: string | null) =>
    api.post<WatchlistConItems>("/watchlist", { nombre, fecha_fin }),
  actualizar: (id: number, payload: { fecha_fin?: string | null; estado?: WatchlistEstado }) =>
    api.patch<WatchlistConItems>(`/watchlist/${id}`, payload),
  eliminar: (id: number) => api.delete(`/watchlist/${id}`),
  agregarItem: (
    watchlistId: number,
    item: {
      tienda: string; sku: string | null; nombre: string; termino_busqueda: string; url: string;
      precio: number; moneda: string; sucursal_id?: string | null; sucursal_nombre?: string | null;
    },
  ) => api.post<WatchlistItem>(`/watchlist/${watchlistId}/items`, item),
  eliminarItem: (itemId: number) => api.delete(`/watchlist/items/${itemId}`),
  historial: (id: number) => api.get<WatchlistHistorialFila[]>(`/watchlist/${id}/historial`),
  usuariosCompartibles: () => api.get<UsuarioCompartible[]>("/watchlist/usuarios-compartibles"),
  listarCompartidos: (id: number) => api.get<UsuarioCompartible[]>(`/watchlist/${id}/compartidos`),
  compartir: (id: number, userId: number) => api.post(`/watchlist/${id}/compartir`, { user_id: userId }),
  dejarDeCompartir: (id: number, userId: number) => api.delete(`/watchlist/${id}/compartir/${userId}`),

  notificaciones: () => api.get<Notificacion[]>("/notificaciones"),
  notificacionesNoLeidasCount: () => api.get<{ count: number }>("/notificaciones/no-leidas/count"),
  marcarLeida: (id: number) => api.post(`/notificaciones/${id}/marcar-leida`),
  marcarTodasLeidas: () => api.post("/notificaciones/marcar-todas-leidas"),
};

// ---------------------------------------------------------------------------
// Admin — audit log y uso/costo de IA
// ---------------------------------------------------------------------------

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  user_email: string | null;
  action: string;
  resource: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string | null;
}

export interface AiUsageByKey {
  cost_usd: number;
}

export interface AiUsageSummary {
  date_from: string;
  date_to: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  by_provider: ({ provider: string } & AiUsageByKey)[];
  by_feature: ({ feature: string } & AiUsageByKey)[];
  by_user: ({ user_id: number | null; user_email: string | null } & AiUsageByKey)[];
  daily: ({ date: string } & AiUsageByKey)[];
}

export const adminApi = {
  auditLog: (limit = 50, offset = 0) =>
    api.get<AuditLogEntry[]>("/admin/audit-log", { params: { limit, offset } }),
  aiUsageSummary: (dateFrom?: string, dateTo?: string) =>
    api.get<AiUsageSummary>("/admin/ai-usage/summary", { params: { date_from: dateFrom, date_to: dateTo } }),
};

// ---------------------------------------------------------------------------
// Redexpress — planilla de pedidos
// ---------------------------------------------------------------------------

export interface PlanillaRow {
  id: number;
  local_nombre: string;
  year: number;
  month: number;
  a4_oferta_vertical: number | null;
  cenefa_oferta_x3: number | null;
  pinchos: number | null;
  afiche_54x74: number | null;
  cenefa_valle_del_sol: number | null;
  cenefa_supremo_hogar: number | null;
  bombas_3xa4: number | null;
  bombas_a4: number | null;
  bombas_74x54: number | null;
  pinchos_bombas: number | null;
  sticker_valle_del_sol: number | null;
  sticker_carne: number | null;
  cenefas_preciazos: number | null;
  cenefas_a4_preciazos: number | null;
  afiche_super_ahorro: number | null;
  afiche_grande_preciazos: number | null;
  pinchos_dias_expres: number | null;
  hojas_amarillas: string | null;
  otros: string | null;
  confirmado: boolean;
  confirmed_at: string | null;
  updated_at: string | null;
  can_edit: boolean;
}

export const redexpresApi = {
  getMeses: () => api.get<{ year: number; month: number }[]>("/redexpres/meses"),
  crearMes: (year: number, month: number) => api.post("/redexpres/meses", { year, month }),
  getPlanilla: (year: number, month: number) =>
    api.get<PlanillaRow[]>(`/redexpres/planilla/${year}/${month}`),
  getMiPlanilla: (year: number, month: number, local?: string) =>
    api.get<PlanillaRow[]>(`/redexpres/mi-planilla/${year}/${month}`, {
      params: local ? { local } : undefined,
    }),
  getLocales: () =>
    api.get<{ local_nombre: string; user_ids: number[] }[]>("/redexpres/locales"),
  updateRow: (year: number, month: number, local_nombre: string, data: Partial<PlanillaRow>) =>
    api.patch<PlanillaRow>(`/redexpres/planilla/${year}/${month}/${encodeURIComponent(local_nombre)}`, data),
  confirmar: (year: number, month: number, local_nombre: string) =>
    api.post(`/redexpres/planilla/${year}/${month}/${encodeURIComponent(local_nombre)}/confirmar`),
  desconfirmar: (year: number, month: number, local_nombre: string) =>
    api.post(`/redexpres/planilla/${year}/${month}/${encodeURIComponent(local_nombre)}/desconfirmar`),
  getAsignaciones: () => api.get("/redexpres/asignaciones"),
  createAsignacion: (user_id: number, local_nombre: string) =>
    api.post("/redexpres/asignaciones", { user_id, local_nombre }),
  deleteAsignacion: (id: number) => api.delete(`/redexpres/asignaciones/${id}`),
};
