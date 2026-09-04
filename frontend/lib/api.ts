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

// Endpoints donde un 401 significa "credenciales inválidas", no "sesión
// vencida" -- nunca hubo una sesión que intentar refrescar. Sin esta
// exclusión, un login con contraseña incorrecta disparaba además un
// /auth/refresh (que también falla, no hay nada que refrescar) y terminaba
// en window.location.href = "/login" -- una recarga completa de la página
// que tira el toast de error antes de que el usuario llegue a verlo.
const _NO_REFRESH_RETRY = ["/auth/login", "/auth/register", "/auth/forgot-password", "/auth/reset-password"];

// Response interceptor: auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    const isAuthEndpoint = _NO_REFRESH_RETRY.some((p) => original?.url?.includes(p));
    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true;
      try {
        const refreshRes = await axios.post(
          `${BASE_URL}/auth/refresh`,
          {},
          { withCredentials: true },
        );
        // Save new token from refresh response if present (mobile path)
        const newToken = refreshRes.data?.access_token;
        if (newToken) {
          saveAccessToken(newToken);
          // `original` ya trae el header Authorization con el token VIEJO,
          // puesto por el request interceptor en el intento original — ese
          // interceptor solo lo agrega si todavía no está seteado, así que
          // sin esta línea el reintento reenvía el mismo token vencido,
          // pega otro 401 (ahora sin reintentar de nuevo, por _retry) y el
          // error termina en pantalla como si el refresh nunca hubiera
          // pasado. Pisarlo acá a mano asegura que el reintento use el
          // token nuevo.
          original.headers["Authorization"] = `Bearer ${newToken}`;
        }
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
  // El CRUD de plantillas v1 (PPTX crudo) se eliminó en 08/2026 -- hay un
  // solo sistema de plantillas, ver cenefasV2Api.
  downloadExcelTemplate: (destino: string = "cenefas") =>
    api.get("/tools/cenefas/template", { params: { destino }, responseType: "blob" }),
  getBuiltinTemplates: () =>
    api.get<{ slug: string; name: string; format_name: string }[]>("/tools/cenefas/builtin-templates"),
};

// Total de tokens/costo que gastó UN agente en UNA tarea puntual (puede ser
// más de una llamada si hubo vueltas de tool-use) -- ver resumir_usage() en
// backend/app/services/ai_usage_service.py. Se muestra chico debajo de cada
// respuesta del bot en las burbujas de chat de la familia Tino.
export interface AiTaskUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface ChatMessageResponse {
  reply: string;
  usage?: AiTaskUsage;
}

export const chatApi = {
  sendMessage: (message: string, history: { role: string; content: string }[]) =>
    api.post<ChatMessageResponse>("/chat/message", { message, history }),
};

// ---------------------------------------------------------------------------
// Cenefas v2
// ---------------------------------------------------------------------------

import type {
  CenefaFormat,
  CenefaJob,
  CenefaTemplate,
  CenefaTemplateRecord,
  CenefaComponent,
  ComponentBounds,
  ComponentOverride,
  CenefaDestino,
  CenefaLote,
  CenefaLoteItem,
} from "@/types/cenefas";

export const cenefasV2Api = {
  // Formatos del sistema
  // Informe de produccion: cuantas cenefas se hicieron, cuantas correctas y
  // cuanto vale. `costo` es el precio por cenefa disenada -- viaja en la
  // consulta para poder cambiarlo sin un deploy.
  getInforme: (params?: {
    desde?: string; hasta?: string; template?: string; costo?: number;
  }) => api.get<CenefaInforme>("/tools/cenefas/v2/informe", { params }),

  downloadInforme: (params?: {
    desde?: string; hasta?: string; template?: string; costo?: number;
  }) => api.get("/tools/cenefas/v2/informe/export", { params, responseType: "blob" }),

  downloadInformePdf: (params?: {
    desde?: string; hasta?: string; template?: string; costo?: number;
  }) => api.get("/tools/cenefas/v2/informe/export/pdf", { params, responseType: "blob" }),

  // Marca una corrida como revisada y correcta por una persona. La validacion
  // automatica dice si la cenefa se pudo armar, no si quedo bien.
  verificarCorrida: (jobId: string, verificado: boolean) =>
    api.patch<{ id: string; verificado: boolean; verificado_at: string | null }>(
      `/tools/cenefas/v2/informe/${jobId}/verificar`, { verificado }),

  // Lo que el modulo aprendio de como se lo usa. Nada esta activo hasta que
  // una persona lo aprueba: ver conocimiento.py.
  listarConocimiento: (params?: { estado?: string; tipo?: string }) =>
    api.get<CenefaConocimiento[]>("/tools/cenefas/v2/conocimiento", { params }),

  decidirConocimiento: (id: string, estado: string, contenido?: string) =>
    api.patch<{ id: string; estado: string; contenido: string }>(
      `/tools/cenefas/v2/conocimiento/${id}`, { estado, contenido }),

  getFormats: () => api.get<CenefaFormat[]>("/tools/cenefas/v2/formats"),

  // Agrupa los componentes de una plantilla multi-banda (3xA4/6xA4/A5/
  // pinchos) en bandas -- una por cenefa de la hoja. Reusa la misma lógica
  // que ya corre en generación (_detect_slot_bands), para que el editor
  // standalone pueda vincular edición entre bandas igual que ya hace
  // PreviewStep con job.slot_bands.
  detectSlotBands: (components: CenefaComponent[]) =>
    api.post<{ slot_bands: string[][] | null }>(
      "/tools/cenefas/v2/slot-bands", { components }),

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
  updateTemplate: (id: string, payload: CenefaTemplate & { category?: string; source_pptx_b64?: string }) =>
    api.put<{ id: string; name: string }>(`/tools/cenefas/v2/templates/${id}`, payload),
  renameTemplate: (id: string, name: string) =>
    api.patch<{ id: string; name: string }>(`/tools/cenefas/v2/templates/${id}/rename`, { name }),
  deleteTemplate: (id: string) =>
    api.delete(`/tools/cenefas/v2/templates/${id}`),

  // Destinos ("mundos")
  listDestinos: () =>
    api.get<CenefaDestino[]>("/tools/cenefas/v2/destinos"),
  createDestino: (payload: { nombre: string; descripcion?: string; icono?: string; color?: string; cobrable?: boolean }) =>
    api.post<CenefaDestino>("/tools/cenefas/v2/destinos", payload),
  deleteDestino: (slug: string) =>
    api.delete(`/tools/cenefas/v2/destinos/${slug}`),

  // Lotes: varios Excel, cada uno contra varias plantillas
  createLote: (formData: FormData) =>
    api.post<{ lote_id: string; cenefas: CenefaLoteItem[] }>("/tools/cenefas/v2/lotes", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getLote: (loteId: string) =>
    api.get<CenefaLote>(`/tools/cenefas/v2/lotes/${loteId}`),
  confirmLote: (loteId: string) =>
    api.post<{ lote_id: string; confirmadas: number }>(`/tools/cenefas/v2/lotes/${loteId}/confirm`),
  downloadLote: (loteId: string) =>
    api.get(`/tools/cenefas/v2/lotes/${loteId}/download`, { responseType: "blob" }),

  // Jobs
  listJobs: () => api.get<CenefaJob[]>("/tools/cenefas/v2/jobs"),
  getJob: (id: string) => api.get<CenefaJob>(`/tools/cenefas/v2/jobs/${id}`),
  createJob: (formData: FormData) =>
    api.post<{ job_id: string; status: string; format: string }>(
      "/tools/cenefas/v2/jobs",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    ),
  confirmJob: (id: string, components: ComponentOverride[]) =>
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
  matched: boolean;

  // Contexto del export de gestión: no se exporta, sirve para entender de
  // dónde salió cada valor calculado y poder corregirlo.
  nombreArticulo: string;
  comprador: string;
  moneda: string;
  ofertaOrigen: string;
  ofertaDet: string;
  descripcionWeb: string;
  precioRaw: string;
  precioAnteriorRaw: string;
  esFiambreKg: boolean;
  /**
   * De dónde salió la descripción: "excel" (la escribió una persona en el
   * listado), "catalogo" (la puso la plataforma) o "" (falta). Una escrita en el
   * Excel no se vuelve a proponer: si alguien la escribió, por algo la escribió
   * (decisión de 2026-08-24, ver match_rows en convertidor.py).
   */
  descripcionOrigen: string;
  /**
   * "100g" | "kg" | "" — con qué unidad se cobra el producto, cuando el nombre
   * de gestión no lo dice (morcilla por kilo, queso de corte y panceta por
   * 100 g). Es lo que le permite a Tinín escribir el gramaje sin inventarlo.
   * Ver _unidad_de_venta en backend/app/services/cenefas/convertidor.py.
   */
  unidadVenta: string;
  /**
   * Se vende por 100 g pero el precio que vino parece el del kilo. La app no
   * divide sola: lo propone y una persona confirma. Ver el bloque de
   * comentarios en backend/app/services/cenefas/convertidor.py.
   */
  precioDeKiloEn100g: boolean;
  warningsMecanica: string[];

  // Las 27 variables — es lo que se exporta y lo que consume la cenefa.
  codigo: string;
  descripcion: string;
  mecanica: string;
  /** Titular grande ("2x1", "25% OFF"). Texto: se imprime tal cual venga. */
  tipoOferta: string;
  unidadMoneda: string;
  precioRegular: string;
  decimalPrecioRegular: string;
  precioOferta: string;
  decimalPrecioOferta: string;
  ofertaUno: string;
  decimalPrecioUno: string;
  ofertaDos: string;
  decimalPrecioDos: string;
  ofertaTres: string;
  decimalPrecioTres: string;
  ofertaCuatro: string;
  decimalPrecioCuatro: string;
  precioBanco: string;
  decimalPrecioBanco: string;
  banco: string;
  vigencia: string;
  aclaracionUno: string;
  aclaracionDos: string;
  aclaracionTres: string;
  legales: string;
  dia: string;
  mes: string;
  "año": string;

  warnings: string[];
}

/** Una columna del Excel subido, con muestras para poder reconocerla. */
/**
 * Un grupo unificado guardado que toca los SKU de la grilla actual.
 *
 * `completo: false` es el caso que importa: la promo de hoy trae parte del
 * grupo, así que la descripción guardada menciona un producto que NO está en
 * oferta -- y un cartel de góndola no puede anunciar algo que no se vende a
 * ese precio. Hay que reescribirla con los que sí vinieron.
 */
export interface GrupoUnificado {
  id: string;
  nombre: string;
  descripcion: string;
  /** Todos los SKU del grupo, como se guardó. */
  skus: string[];
  /** Los que sí están en este listado. */
  presentes: string[];
  /** Los que faltan. Vacío = el grupo vino entero. */
  faltantes: string[];
  completo: boolean;
}

export interface BuscarGruposResponse {
  grupos: GrupoUnificado[];
  parciales: GrupoUnificado[];
}

/** Un OFERTADET que el motor no reconoce, con la familia que propone Tinín. */
export interface SugerenciaMecanica {
  ofertadet_norm: string;
  ofertadet_display: string;
  /** combo | mxn | segunda | sin_mecanica */
  familia: string;
  motivo: string;
}

export interface MecanicaAprendida {
  ofertadet_norm: string;
  ofertadet_display: string;
  familia: string;
}

export interface SugerirMecanicaIAResponse {
  sugerencias: SugerenciaMecanica[];
  ya_aprendidas: MecanicaAprendida[];
  errores: string[];
  /** {familia: qué significa} — para explicar cada opción del desplegable. */
  familias: Record<string, string>;
}

/** Una columna del archivo que el Convertidor no reconoció, con la propuesta de Tinín. */
export interface SugerenciaColumna {
  header_norm: string;
  header_display: string;
  muestras: string[];
  /** El campo que Tinín propone. null = "esto no es ninguno de los campos". */
  campo: string | null;
  motivo: string;
}

/** Una columna de nombre raro que ya se confirmó antes y por eso ya funciona. */
export interface AliasAprendido {
  header_norm: string;
  header_display: string;
  campo: string;
}

export interface SugerirColumnasIAResponse {
  sugerencias: SugerenciaColumna[];
  ya_aprendidas: AliasAprendido[];
  errores: string[];
  /** Los campos a los que se puede atar una columna, para el desplegable. */
  campos: string[];
}

export interface ConvertidorColumna {
  nombre: string;
  muestras: string[];
}

/**
 * La columna OFERTA trae precios en vez del titular de la mecanica ("2x$299",
 * "6x4"). Pasa cuando alguien edita el Excel a mano: el Convertidor la sigue
 * leyendo como titular, la mecanica queda sin parsear y el precio que estaba ahi
 * no lo usa nadie. La app NO lo cambia sola -- lo propone y la persona decide.
 */
export interface OfertaConPrecios {
  /** Nombre de la columna tal como viene en el archivo. */
  columna: string;
  /** El campo al que se esta leyendo hoy: "oferta". */
  campo_actual: string;
  /** El campo que se propone: "precio". */
  campo_propuesto: string;
  /** Valores que lo delatan, para mostrarlos. */
  muestras: string[];
}

/**
 * Una hoja del archivo subido. Un boceto real trae varias y son listados
 * distintos (el export crudo de gestion, el "Frente" curado a mano, el
 * "Dorso"), cada uno con sus propias columnas y su propio mapeo.
 */
export interface ConvertidorHoja {
  /** Indice 0-based. Es lo que se le manda al backend para convertirla. */
  indice: number;
  nombre: string;
  columnas: ConvertidorColumna[];
  /**
   * Campos de entrada que el Convertidor ya reconoce solo en esta hoja
   * (codigo, precio, oferta, ofertaDet, comprador...). Sirve para no pedir a
   * mano una variable que el archivo ya trae resuelta -- ver
   * `resuelta_por_campo`.
   */
  campos_reconocidos: string[];
  /** null = la columna OFERTA esta bien. */
  oferta_con_precios: OfertaConPrecios | null;
  total_filas: number;
  /** Por que no se puede convertir. null = se puede. */
  error: string | null;
}

/** Lo que Tinin marco como bebida con alcohol, para confirmar. */
export interface DetectarAlcoholIAResponse {
  alcohol: { row_id: number; codigo: string; texto: string; motivo: string }[];
  errores: string[];
  /** Cuantas filas se le pasaron a Tinin (las que el chequeo por tipo no vio). */
  revisadas: number;
  /** Cuantas ya estaban reconocidas por codigo, sin gastar IA. */
  ya_reconocidas: number;
  /** El texto exacto de la leyenda, para no duplicarlo en el front. */
  leyenda: string;
}

export interface ConvertidorColumnasResponse {
  hojas: ConvertidorHoja[];
  /** La primera hoja con filas: con la que conviene arrancar. */
  hoja_sugerida: number;
  /** Compat: las columnas de la hoja sugerida. */
  columnas: ConvertidorColumna[];
  variables_mapeables: string[];
  /** Compat: los campos reconocidos de la hoja sugerida. */
  campos_reconocidos: string[];
  /**
   * {variable_mapeable: campo_de_entrada} -- esa variable deja de pedirse a mano
   * cuando ese campo ya vino reconocido, porque el Convertidor la calcula solo.
   * Hoy es una sola: tipoOferta sale de la columna OFERTA leida junto con
   * OFERTADET. Viene del backend para no duplicar aca de donde sale cada
   * variable calculada.
   */
  resuelta_por_campo: Record<string, string>;
  /** Compat: el aviso de la hoja sugerida. */
  oferta_con_precios: OfertaConPrecios | null;
  /** {campo: que es} -- a que campos se puede reasignar una columna. */
  campos_asignables: Record<string, string>;
  total_filas: number;
}

/** Plantilla de mapeo reutilizable: {variable: nombre_de_columna}. */
/** Un bloque de cifras del informe de cenefas. */
/** Algo que el modulo de cenefas aprendio de como se lo usa. */
export interface CenefaConocimiento {
  id: string;
  /** alias_columna | plantilla | aviso | correccion | preferencia */
  tipo: string;
  contenido: string;
  detalle: Record<string, unknown> & { confianza?: string };
  /** revision_previa | mapeo | grilla | job | manual */
  origen: string;
  /** propuesto | activo | descartado | archivado */
  estado: string;
  veces_visto: number;
  visto_at: string | null;
  decidido_at: string | null;
}

export interface CenefaInformeBloque {
  corridas: number;
  cenefas: number;
  correctas: number;
  avisos: number;
  criticos: number;
  /** Corridas que una persona reviso y marco como correctas. */
  verificadas_corridas: number;
  /** Cenefas de esas corridas verificadas. */
  verificadas: number;
  costo: number;
  costo_correctas: number;
  costo_verificadas: number;
  /**
   * Lo que hacia falta de verdad: filas del listado x formatos distintos
   * pedidos, sin pagar de nuevo el reproceso del mismo Excel. Solo viene
   * cuando hay `excel_nombre` guardado (desde el 23/08/2026) -- ausente en
   * los bloques que agrupan corridas de antes de esa fecha.
   */
  cenefas_reales?: number;
  costo_real?: number;
}

/** Un mundo (destino) con su produccion. `cobrable=false` -> valorizado en 0. */
export interface CenefaInformeMundo extends CenefaInformeBloque {
  /** Slug del destino. Vacio = corridas sin mundo registrado. */
  mundo: string;
  nombre: string;
  cobrable: boolean;
}

/**
 * Produccion declarada: cenefas hechas antes de que el job guardara el mundo.
 * No tiene corridas detras -- es una cifra afirmada, no medida, y por eso va
 * en su propio renglon en vez de sumarse en silencio.
 */
export interface CenefaInformeDeclarada {
  mundo: string;
  nombre: string;
  cobrable: boolean;
  cenefas: number;
  nota: string;
  costo: number;
}

export interface CenefaInforme {
  costo_unitario: number;
  /** TODO lo que paso por el motor, valorizado. Cifra bruta. */
  total: CenefaInformeBloque & { desde: string | null; hasta: string | null };
  por_mes: (CenefaInformeBloque & { mes: string })[];
  por_plantilla: (CenefaInformeBloque & { plantilla: string })[];
  por_mundo: CenefaInformeMundo[];
  declaradas: CenefaInformeDeclarada[];
  /** Lo facturable: mundos cobrables, medido mas declarado. */
  cobrable: CenefaInformeBloque & {
    declaradas: number;
    cenefas_totales: number;
    costo_total: number;
    /** Medido con la regla de listado x formatos, mas lo declarado (que ya es real). */
    cenefas_reales_totales: number;
    costo_real_total: number;
  };
  /** Mundos marcados sin costo (Redexpres, pruebas). Volumen si, plata no. */
  sin_costo: CenefaInformeBloque;
  /** Corridas anteriores a que el job guardara el mundo. No se valorizan. */
  sin_clasificar: CenefaInformeBloque;
  plantillas: string[];
  detalle?: {
    id: string;
    fecha: string | null;
    formato: string;
    plantilla: string;
    excel: string;
    cenefas: number;
    correctas: number;
    avisos: number;
    criticos: number;
    verificado: boolean;
    verificado_at: string | null;
    costo: number;
  }[];
  /** Las corridas agrupadas por listado, para ver cuantos intentos llevo cada uno. */
  intentos?: {
    excel: string;
    plantilla: string;
    /** true cuando el grupo se armo por formato + cantidad, sin nombres. */
    sin_registrar: boolean;
    intentos: number;
    primera: string | null;
    ultima: string | null;
    cenefas: number;
    correctas: number;
    criticos: number;
    verificado: boolean;
    costo: number;
    detalle: {
      id: string; fecha: string | null; cenefas: number;
      correctas: number; criticos: number; verificado: boolean;
    }[];
  }[];
}

export interface ConvertidorMapeo {
  id: string;
  nombre: string;
  destino: string | null;
  /** {variable: nombre_de_columna} — la variable se lee de esa columna. */
  mapeo: Record<string, string>;
  /** {variable: texto_fijo} — el mismo texto para todas las filas. */
  valores?: Record<string, string>;
  updated_at?: string | null;
}

// Preset reutilizable de "banco con descuento": resuelve precioBanco/banco
// como precioOferta × multiplicador en vez de mapear una columna del Excel —
// para descuentos que Tienda Inglesa define como porcentaje fijo ("15%
// extra con Club Card Scotia") y que gestión nunca trae calculados por fila.
export interface BancoPreset {
  id: string;
  nombre: string;
  multiplicador: number;
}

export interface ConvertidorSummary {
  total: number;
  matched_count: number;
  unmatched_count: number;
}

// Par "mismo producto, dos SKUs" (sufijo suelto M/A en el nombre) detectado
// por el backend -- todavía sin unificar. "base" es el nombre más largo de
// los dos, sin el sufijo, usado como punto de partida para la sugerencia IA.
export interface MaPair {
  sku1: string;
  sku2: string;
  nombre1: string;
  nombre2: string;
  base: string;
}

export interface ConvertidorPreviewResponse extends ConvertidorSummary {
  rows: ConvertidorRow[];
  ma_pairs: MaPair[];
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

/** Una fila de la solapa Plurales del Diccionario: un grupo de varios SKU
 * que comparten un cartel. Vive en cenefa_grupos_unificados, nunca en el
 * catálogo singular. */
export interface GrupoUnificadoItem {
  id: string;
  nombre: string;
  descripcion: string;
  skus: string[];
  updated_at: string | null;
}

// Grupo de variantes de la misma línea de producto ("Unificar categorías") que
// Tinín propuso a partir del nombre crudo de TODAS las filas cargadas -- distinto
// de MaPair (que son pares exactos "mismo SKU, sufijo M/A" detectados sin IA sin
// necesitar ver todas las filas a la vez). Al aprobar un grupo, el frontend lo
// combina en una sola fila (mismo criterio que un MaPair, ver commitUnificacion
// en ConvertidorGrid.tsx) -- no hay endpoint de confirmación aparte.
/** Una redacción alternativa para el cartel de un grupo unificado. */
export interface OpcionDescripcion {
  texto: string;
  /** 2-5 palabras que dicen en qué se diferencia, para el desplegable. */
  etiqueta: string;
}

export interface UnificarGrupoItem {
  row_ids: number[];
  skus: string[];
  grupo: string;
  descripcion: string;
  /**
   * 2 o 3 redacciones alternativas, ordenadas de la más segura a la más
   * riesgosa: Tinín solo ve los productos EN OFERTA, no el surtido completo, así
   * que "todas las variedades" puede ser mentira. La persona elige. Puede venir
   * vacío si el análisis degradó a una sola opción (ver _parsear_opciones en
   * backend/app/services/cenefas/convertidor_ai.py).
   */
  opciones?: OpcionDescripcion[];
}

export interface UnificarCategoriasIAResponse {
  grupos: UnificarGrupoItem[];
  truncated: boolean;
  // true si el análisis en sí falló (red, JSON cortado, etc.) -- distinto de
  // "Claude ya revisó todo y no encontró grupos" (grupos: [], error: false).
  error: boolean;
}

export const convertidorApi = {
  columnas: (formData: FormData) =>
    api.post<ConvertidorColumnasResponse>("/tools/cenefas/convertidor/columnas", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  preview: (formData: FormData) =>
    api.post<ConvertidorPreviewResponse>("/tools/cenefas/convertidor/preview", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  listarMapeos: (destino?: string) =>
    api.get<ConvertidorMapeo[]>("/tools/cenefas/convertidor/mapeos", {
      params: { destino: destino || undefined },
    }),
  guardarMapeo: (payload: {
    nombre: string;
    destino?: string | null;
    mapeo: Record<string, string>;
    valores: Record<string, string>;
  }) =>
    api.post<ConvertidorMapeo>("/tools/cenefas/convertidor/mapeos", payload),
  borrarMapeo: (id: string) =>
    api.delete(`/tools/cenefas/convertidor/mapeos/${id}`),
  listarBancos: () =>
    api.get<BancoPreset[]>("/tools/cenefas/convertidor/bancos"),
  guardarBanco: (payload: { nombre: string; multiplicador: number }) =>
    api.post<BancoPreset>("/tools/cenefas/convertidor/bancos", payload),
  borrarBanco: (id: string) =>
    api.delete(`/tools/cenefas/convertidor/bancos/${id}`),
  updateDescripcion: (sku: string, descripcion: string) =>
    api.patch<{ sku: string; descripcion: string }>(
      `/tools/cenefas/convertidor/descripciones/${encodeURIComponent(sku)}`,
      { descripcion }
    ),
  listarDescripciones: (q?: string, limit = 100, offset = 0) =>
    api.get<{ items: SkuDescripcionItem[]; total: number }>("/tools/cenefas/convertidor/descripciones", {
      params: { q: q || undefined, limit, offset },
    }),
  export: (rows: ConvertidorRow[]) =>
    api.post("/tools/cenefas/convertidor/export", { rows }, { responseType: "blob" }),
  generarDescripcionesIA: (
    rows: {
      row_id: number;
      codigo: string;
      nombreArticulo: string;
      descripcionWeb: string;
      esFiambreKg: boolean;
      unidadVenta: string;
    }[]
  ) =>
    api.post<GenerarDescripcionesIAResponse>("/tools/cenefas/convertidor/descripciones/generar-ia", { rows }),
  /**
   * Bebidas con alcohol entre las filas que el chequeo por TIPO no reconocio
   * ("cerveza", "whisky", "fernet"...). Se le pregunta a Tinin solo por las que
   * quedan: una cerveza ya esta resuelta por codigo y no vale gastar una
   * llamada. El filtro lo aplica el backend, que usa la MISMA funcion que
   * despues decide la leyenda al generar -- asi no hay dos criterios.
   */
  /**
   * Le pide a Tinín que diga qué es cada columna que el Convertidor no
   * reconoció. NO aplica nada: devuelve propuestas para confirmar. Lo que ya
   * está aprendido no se vuelve a preguntar (ni se gasta una llamada en él).
   */
  /**
   * Le pide a Tinín la familia de mecánica de los OFERTADET que el motor no
   * reconoce. Se agrupa por tipo, no por fila: cuarenta filas con el mismo
   * OFERTADET nuevo son UNA pregunta.
   */
  /**
   * Recuerda un grupo por su CONJUNTO de SKU. Las descripciones individuales de
   * cada SKU no se tocan: son las que permiten rearmar el texto cuando mañana
   * venga solo una parte del grupo.
   */
  guardarGrupoUnificado: (nombre: string, descripcion: string, skus: string[]) =>
    api.post<{ id: string; nombre: string; skus: string[] }>(
      "/tools/cenefas/convertidor/grupos-unificados", { nombre, descripcion, skus }),
  /** Grupos guardados que tocan los SKU de este listado. */
  buscarGruposUnificados: (skus: string[]) =>
    api.post<BuscarGruposResponse>(
      "/tools/cenefas/convertidor/grupos-unificados/buscar", { skus }),
  /** La solapa Plurales del Diccionario: grupos de varios SKU con un cartel. */
  listarGruposUnificados: (q?: string, limit = 100, offset = 0) =>
    api.get<{ items: GrupoUnificadoItem[]; total: number }>(
      "/tools/cenefas/convertidor/grupos-unificados",
      { params: { q: q || undefined, limit, offset } }),
  updateGrupoUnificado: (id: string, payload: { nombre?: string; descripcion?: string }) =>
    api.patch<GrupoUnificadoItem>(
      `/tools/cenefas/convertidor/grupos-unificados/${id}`, payload),
  deleteGrupoUnificado: (id: string) =>
    api.delete(`/tools/cenefas/convertidor/grupos-unificados/${id}`),
  /** Descarga del Diccionario a Excel, una solapa por vez. */
  exportDiccionario: (tipo: "singulares" | "plurales") =>
    api.get(
      tipo === "plurales"
        ? "/tools/cenefas/convertidor/grupos-unificados/export"
        : "/tools/cenefas/convertidor/descripciones/export",
      { responseType: "blob" }),
  sugerirMecanicaIA: (rows: { ofertaDet: string; oferta: string }[]) =>
    api.post<SugerirMecanicaIAResponse>(
      "/tools/cenefas/convertidor/mecanica/sugerir-ia", { rows }),
  /** Guarda las confirmaciones. Ese OFERTADET no vuelve a pasar por IA nunca. */
  confirmarAliasMecanica: (
    mecanicas: { ofertadet_norm: string; ofertadet_display: string; familia: string }[]
  ) =>
    api.post<{ guardados: number }>(
      "/tools/cenefas/convertidor/mecanica/confirmar-alias", { mecanicas }),
  sugerirColumnasIA: (excel: File, hoja?: string) => {
    const fd = new FormData();
    fd.append("excel", excel);
    if (hoja) fd.append("hoja", hoja);
    return api.post<SugerirColumnasIAResponse>(
      "/tools/cenefas/convertidor/columnas/sugerir-ia", fd,
      { headers: { "Content-Type": "multipart/form-data" } });
  },
  /**
   * Guarda las confirmaciones. De acá en adelante esos encabezados los resuelve
   * el código, sin pasar nunca más por IA. `campo: null` también se guarda: es
   * una respuesta válida ("esta columna no es ninguno") y evita repreguntar.
   */
  confirmarAliasColumnas: (aliases: { header_norm: string; campo: string | null }[]) =>
    api.post<{ guardados: number }>(
      "/tools/cenefas/convertidor/columnas/confirmar-alias", { aliases }),
  detectarAlcoholIA: (
    rows: { row_id: number; codigo: string; descripcion: string; nombreArticulo: string }[]
  ) =>
    api.post<DetectarAlcoholIAResponse>("/tools/cenefas/convertidor/alcohol/detectar-ia", { rows }),
  unificarCategoriasIA: (
    rows: { row_id: number; codigo: string; nombreArticulo: string; descripcion: string }[]
  ) =>
    api.post<UnificarCategoriasIAResponse>("/tools/cenefas/convertidor/categorias/unificar-ia", { rows }),
};

// "convertidor" o el slug de un mundo de cenefas. No es una unión cerrada
// porque los mundos se crean desde la UI (ver cenefa_destinos).
export type TininContexto = "convertidor" | (string & {});

export interface TininConsultarResponse {
  respuesta: string;
  usage?: AiTaskUsage;
}

export const tininApi = {
  consultar: (
    mensaje: string,
    historial: { role: "user" | "assistant"; content: string }[],
    contexto?: TininContexto,
    // Las filas que la persona tiene en pantalla. Sin esto Tinin no puede
    // contestar "por que esta fila esta marcada" y solo tira hipotesis.
    filas?: object[],
  ) =>
    api.post<TininConsultarResponse>("/tools/cenefas/convertidor/tinin/consultar", {
      mensaje,
      historial,
      filas: filas ?? [],
      contexto,
    }),
};

// ---------------------------------------------------------------------------
// Facturación — presupuesto y canjes, extraídos por DogTi de facturas PDF
// ---------------------------------------------------------------------------

// Tal cual la tool registrar_extraccion_factura de DogTi (ver
// backend/app/services/facturacion/extraccion.py) -- lo que propone antes de
// que el usuario lo revise y edite.
export interface FacturacionExtraccion {
  tipo_sugerido: "movimiento" | "canje";
  proveedor_marca: string;
  concepto: string;
  monto: number;
  moneda: string;
  fecha: string;
  numero_factura?: string | null;
  cuenta_sugerida?: string | null;
  cuenta_recomendada?: string | null;
  vigencia_desde?: string | null;
  vigencia_hasta?: string | null;
  confianza: "alta" | "media" | "baja";
  notas?: string | null;
}

export interface FacturacionDocumento {
  id: number;
  filename: string;
  status: "pendiente_revision" | "confirmado" | "descartado";
  extraccion: FacturacionExtraccion | null;
  extraction_error: string | null;
  created_at: string | null;
}

export interface FacturacionMovimiento {
  id: number;
  tipo: "entrada" | "salida";
  monto: number;
  moneda: string;
  concepto: string;
  proveedor_marca: string | null;
  numero_factura: string | null;
  fecha: string;
  cuenta_id: number | null;
  documento_id: number | null;
  created_at: string | null;
}

// "Eliminar" una cuenta desde el panel de administración solo la desactiva
// (activa=false) -- nunca se borra, así que movimientos/canjes viejos
// conservan su cuenta y su historial para siempre. Ver FacturacionCuenta
// en el backend.
export interface FacturacionCuenta {
  id: number;
  nombre: string;
  activa: boolean;
}

export interface FacturacionDashboardResponse {
  // Cuentas activas -- para poblar los selects de Presupuesto/Canjes.
  cuentas: { id: number; nombre: string }[];
  presupuesto: {
    cuenta_id: number | null;
    entradas_total: number;
    salidas_total: number;
    saldo: number;
    movimientos: FacturacionMovimiento[];
    movimientos_total: number;
  };
  canjes: {
    cuenta_id: number | null;
    total_valor: number;
    por_estado: Record<string, number>;
  };
  general: {
    // Saldo del presupuesto (entradas - salidas) + valor de canjes, de
    // TODAS las cuentas juntas (nunca se filtra).
    total: number;
    por_cuenta: { cuenta_id: number | null; cuenta: string; monto: number }[];
  };
}

export interface ConfirmarDocumentoPayload {
  tipo: "movimiento" | "canje";
  tipo_movimiento?: "entrada" | "salida";
  monto: number;
  moneda?: string;
  concepto: string;
  proveedor_marca?: string | null;
  numero_factura?: string | null;
  fecha: string;
  cuenta_id: number;
  estado?: string | null;
  vigencia_desde?: string | null;
  vigencia_hasta?: string | null;
}

export const facturacionApi = {
  // Un solo POST con varios "files" -- el backend corre las extracciones de
  // Claude en paralelo y devuelve un documento por archivo, en el mismo
  // orden en que se mandaron (ver crear_documentos_y_extraer en el backend).
  uploadDocumentos: (files: File[]) => {
    const formData = new FormData();
    for (const file of files) formData.append("files", file);
    return api.post<FacturacionDocumento[]>("/facturacion/documentos/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  getDocumento: (id: number) => api.get<FacturacionDocumento>(`/facturacion/documentos/${id}`),
  // Blob (no un <iframe src> directo a la URL cruda) -- así el interceptor de
  // axios adjunta el header Authorization, sin depender de que el navegador
  // mande la cookie de sesión en una navegación cross-site (ver el comentario
  // sobre Safari/ITP más arriba en este archivo).
  getDocumentoPdfBlob: (id: number) =>
    api.get(`/facturacion/documentos/${id}/pdf`, { responseType: "blob" }),
  confirmarDocumento: (id: number, payload: ConfirmarDocumentoPayload) =>
    api.post<{ tipo: string; id: number }>(`/facturacion/documentos/${id}/confirmar`, payload),
  descartarDocumento: (id: number) =>
    api.post<{ status: string }>(`/facturacion/documentos/${id}/descartar`),
  dashboard: (params?: {
    limit?: number; offset?: number;
    presupuesto_cuenta_id?: number; canjes_cuenta_id?: number;
  }) =>
    api.get<FacturacionDashboardResponse>("/facturacion/dashboard", { params }),
};

export const facturacionCuentasApi = {
  listar: (incluirInactivas = false) =>
    api.get<FacturacionCuenta[]>("/facturacion/cuentas", { params: { incluir_inactivas: incluirInactivas } }),
  crear: (nombre: string) =>
    api.post<FacturacionCuenta>("/facturacion/cuentas", { nombre }),
  editar: (id: number, payload: { nombre?: string; activa?: boolean }) =>
    api.patch<FacturacionCuenta>(`/facturacion/cuentas/${id}`, payload),
};

export type DogtiContexto = "dashboard";

export const dogtiApi = {
  consultar: (
    mensaje: string,
    historial: { role: "user" | "assistant"; content: string }[],
    contexto?: DogtiContexto
  ) =>
    api.post<TininConsultarResponse>("/facturacion/dogti/consultar", {
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
  usage?: AiTaskUsage;
}

export interface ReporteIAResponse {
  reporte: string;
  usage?: AiTaskUsage;
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

export interface UserStats {
  login_count: number;
  last_login_at: string | null;
  last_login_ip: string | null;
  cenefas_generated_count: number;
  ai_cost_last_30d_usd: number;
  account_created_at: string | null;
}

export const adminApi = {
  auditLog: (limit = 50, offset = 0, userId?: number) =>
    api.get<AuditLogEntry[]>("/admin/audit-log", { params: { limit, offset, user_id: userId } }),
  aiUsageSummary: (dateFrom?: string, dateTo?: string, userId?: number) =>
    api.get<AiUsageSummary>("/admin/ai-usage/summary", { params: { date_from: dateFrom, date_to: dateTo, user_id: userId } }),
  userStats: (userId: number) =>
    api.get<UserStats>(`/admin/users/${userId}/stats`),
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
