"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { convertidorApi, type ConvertidorRow, type DescripcionSugerencia } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { DonTinoTrabajando } from "@/components/DonTinoTrabajando";

interface PrecioOverride {
  precio?: number;
  precio_anterior?: number;
}

interface Props {
  // ya filtradas y ordenadas por el caller: fiambres por kg primero, después
  // el resto de las que faltan descripción
  rows: ConvertidorRow[];
  onApprove: (rowId: number, sku: string, descripcion: string, precioOverride?: PrecioOverride) => Promise<void>;
  onClose: () => void;
}

type RowState = {
  value: string;
  // Solo se usan cuando la fila es es_fiambre_kg — precargados con el
  // precio÷10 de la fila original, editables antes de aprobar. El precio
  // NUNCA se persiste en el catálogo compartido (solo la descripción va por
  // ese PATCH) — esto viaja únicamente al estado local de la grilla.
  precio: string;
  precioAnterior: string;
  status: "pending" | "approving" | "approved" | "error";
};

function precioDividido(precio: number | null): string {
  if (precio === null || precio === undefined) return "";
  return String(Math.round((precio / 10) * 100) / 100);
}

// Mismo umbral que DESCRIPTION_WARN_CHARS en
// backend/app/services/cenefas/validation_engine.py (60) — se recalcula acá
// en vivo mientras el usuario edita la sugerencia, no solo el "too_long"
// estático que vino del backend al momento de generarla.
const DESCRIPTION_WARN_CHARS = 60;
// Mismo tope que _ROWS_MAX_PER_REQUEST en
// backend/app/services/cenefas/convertidor_ai.py — duplicado acá para poder
// trocear el pedido en tandas de este tamaño y pedirlas todas en secuencia
// (ver el efecto de carga más abajo), en vez de que el usuario tenga que
// cerrar y reabrir el modal para las filas que quedan afuera de la primera.
const ROWS_CHUNK_SIZE = 80;
// slowapi limita /descripciones/generar-ia a 5 pedidos por minuto (ver
// @limiter.limit en cenefas_convertidor.py) -- si una tanda pega 429, se
// espera este piso (o el Retry-After real si vino en la respuesta) antes de
// reintentarla una vez, en vez de darla por perdida de una.
const RATE_LIMIT_RETRY_MS = 60000;

export default function ConvertidorAiModal({ rows, onApprove, onClose }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"not_configured" | "generic" | null>(null);
  const [meta, setMeta] = useState<{ failedRowIds: number[] } | null>(null);
  const [state, setState] = useState<Map<number, RowState>>(new Map());
  // Tandas 2+ (por encima de ROWS_CHUNK_SIZE) se piden solas en segundo
  // plano, sin bloquear la pantalla -- las filas de la primera tanda ya son
  // aprobables mientras el resto sigue cargando.
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreProgress, setLoadMoreProgress] = useState<{ done: number; total: number } | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);
  // Si el usuario cierra el modal a mitad de "Aprobar todas", el for-loop de
  // approveAll sigue corriendo (JS no cancela un await por un unmount) —
  // este flag corta el loop entre iteraciones y evita setState en un
  // componente ya desmontado. Los PATCH que ya salieron antes de cerrar
  // siguen su curso igual (correcto: ya se comprometió a guardarlos).
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  useEscapeKey(onClose);

  function buildRequestItem(r: ConvertidorRow) {
    return {
      row_id: r.row_id,
      codigo: r.codigo,
      nombre_articulo: r.nombre_articulo,
      descripcion_web: r.descripcion_web,
      es_fiambre_kg: r.es_fiambre_kg,
    };
  }

  function applySuggestions(chunkRows: ConvertidorRow[], suggestions: DescripcionSugerencia[]) {
    setState((prev) => {
      const next = new Map(prev);
      suggestions.forEach((s) => {
        const row = chunkRows.find((r) => r.row_id === s.row_id);
        next.set(s.row_id, {
          value: s.descripcion,
          precio: row?.es_fiambre_kg ? precioDividido(row.precio) : "",
          precioAnterior: row?.es_fiambre_kg ? precioDividido(row.precio_anterior) : "",
          status: "pending",
        });
      });
      return next;
    });
  }

  // Reintenta una vez ante 429 (esperando el Retry-After real si vino, o el
  // piso de RATE_LIMIT_RETRY_MS) -- cualquier otro error se propaga tal cual
  // para que el caller decida cómo tratarlo (loadError duro en la primera
  // tanda, fail-soft por fila en las siguientes).
  async function requestChunk(chunkRows: ConvertidorRow[], attemptedRetry = false) {
    try {
      const { data } = await convertidorApi.generarDescripcionesIA(chunkRows.map(buildRequestItem));
      return { suggestions: data.suggestions, failedRowIds: data.failed_row_ids };
    } catch (err: any) {
      if (err?.response?.status === 429 && !attemptedRetry) {
        const retryAfterHeader = err.response.headers?.["retry-after"];
        const waitMs = retryAfterHeader ? Number(retryAfterHeader) * 1000 : RATE_LIMIT_RETRY_MS;
        await new Promise((resolve) => setTimeout(resolve, waitMs));
        if (!mountedRef.current) throw err;
        return requestChunk(chunkRows, true);
      }
      throw err;
    }
  }

  useEffect(() => {
    // Piso mínimo para la pantalla de Tinín picando piedra — esto NUNCA
    // corta la animación antes de que la IA real termine (Math.max abajo:
    // si Claude tarda más que el piso, se espera lo que Claude tarde, sin
    // techo). El piso solo entra a jugar cuando la respuesta llega rápido
    // (lotes chicos, 1-3 productos) y evita que la animación se sienta
    // cortada antes de disfrutarla.
    const MIN_LOADING_MS = 6000;
    const start = Date.now();
    const finishInitialLoading = () => {
      const remaining = Math.max(0, MIN_LOADING_MS - (Date.now() - start));
      setTimeout(() => {
        if (mountedRef.current) setLoading(false);
      }, remaining);
    };

    const chunks: ConvertidorRow[][] = [];
    for (let i = 0; i < rows.length; i += ROWS_CHUNK_SIZE) chunks.push(rows.slice(i, i + ROWS_CHUNK_SIZE));
    if (chunks.length === 0) {
      finishInitialLoading();
      return;
    }

    (async () => {
      let first;
      try {
        first = await requestChunk(chunks[0]);
      } catch (err: any) {
        if (mountedRef.current) setLoadError(err?.response?.status === 503 ? "not_configured" : "generic");
        finishInitialLoading();
        return;
      }
      if (!mountedRef.current) return;
      applySuggestions(chunks[0], first.suggestions);
      setMeta({ failedRowIds: first.failedRowIds });
      finishInitialLoading();

      // El resto de las tandas (si el archivo trae más de ROWS_CHUNK_SIZE
      // productos sin descripción) se piden solas en secuencia, sin que el
      // usuario tenga que cerrar y reabrir el modal -- las filas de la
      // primera tanda ya se pueden ir aprobando mientras tanto.
      if (chunks.length > 1) {
        setLoadingMore(true);
        for (let i = 1; i < chunks.length; i++) {
          if (!mountedRef.current) return;
          setLoadMoreProgress({ done: i * ROWS_CHUNK_SIZE, total: rows.length });
          let result;
          try {
            result = await requestChunk(chunks[i]);
          } catch {
            result = { suggestions: [] as DescripcionSugerencia[], failedRowIds: chunks[i].map((r) => r.row_id) };
          }
          if (!mountedRef.current) return;
          applySuggestions(chunks[i], result.suggestions);
          setMeta((prev) => ({
            failedRowIds: [...(prev?.failedRowIds ?? []), ...result.failedRowIds],
          }));
        }
        if (mountedRef.current) {
          setLoadingMore(false);
          setLoadMoreProgress(null);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function approveOne(rowId: number, sku: string) {
    const row = state.get(rowId);
    if (!row) return;
    setState((prev) => new Map(prev).set(rowId, { ...row, status: "approving" }));
    const rowData = rows.find((r) => r.row_id === rowId);
    const precioOverride: PrecioOverride | undefined = rowData?.es_fiambre_kg
      ? {
          precio: row.precio.trim() ? parseFloat(row.precio) : undefined,
          precio_anterior: row.precioAnterior.trim() ? parseFloat(row.precioAnterior) : undefined,
        }
      : undefined;
    try {
      await onApprove(rowId, sku, row.value, precioOverride);
      if (mountedRef.current) setState((prev) => new Map(prev).set(rowId, { ...row, status: "approved" }));
    } catch {
      if (mountedRef.current) setState((prev) => new Map(prev).set(rowId, { ...row, status: "error" }));
    }
  }

  async function approveAll() {
    setApprovingAll(true);
    // Secuencial, no Promise.all: mismo criterio que el flush de guardados
    // pendientes en handleExport de ConvertidorGrid — no golpear el PATCH
    // con N requests concurrentes, y poder mostrar progreso fila por fila.
    for (const row of rows) {
      if (!mountedRef.current) break;
      const s = state.get(row.row_id);
      // "error" también se reintenta acá -- si no, una fila que falló en un
      // intento individual quedaría trabada ahí para siempre salvo que el
      // usuario la reintente fila por fila.
      if (s && (s.status === "pending" || s.status === "error")) await approveOne(row.row_id, row.codigo);
    }
    if (mountedRef.current) setApprovingAll(false);
  }

  const visibleRows = rows.filter((r) => state.has(r.row_id));

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <p className="text-sm font-semibold flex items-center gap-1.5 text-slate-800 dark:text-slate-100">
            <Sparkles size={15} className="text-brand-500" /> {t("convertidor.ai.modalTitle")}
          </p>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {loading && (
            <div className="flex flex-col items-center gap-3 py-8">
              <DonTinoTrabajando size={72} />
              <p className="text-xs text-slate-400">{t("convertidor.ai.loading")}</p>
            </div>
          )}

          {loadError === "not_configured" && (
            <p className="text-sm text-amber-600 dark:text-amber-400 text-center py-8">
              {t("convertidor.ai.notConfigured")}
            </p>
          )}
          {loadError === "generic" && (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
              {t("convertidor.ai.genericError")}
            </p>
          )}

          {!loading && !loadError && loadingMore && loadMoreProgress && (
            <p className="text-xs text-slate-400 flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin shrink-0" />
              {t("convertidor.ai.loadingMore", { done: loadMoreProgress.done, total: loadMoreProgress.total })}
            </p>
          )}
          {!loading && !loadError && meta && meta.failedRowIds.length > 0 && (
            <p className="text-xs text-slate-400">
              {t("convertidor.ai.failedCount", { count: meta.failedRowIds.length })}
            </p>
          )}

          {!loading &&
            !loadError &&
            visibleRows.map((row) => {
              const s = state.get(row.row_id)!;
              return (
                <div
                  key={row.row_id}
                  className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] text-slate-400 truncate flex items-center gap-1.5">
                      {row.es_fiambre_kg && (
                        <span className="badge badge-yellow text-[9px] px-1.5 py-0 shrink-0">
                          {t("convertidor.ai.fiambreKgBadge")}
                        </span>
                      )}
                      {row.codigo} · {row.nombre_articulo}
                    </p>
                    <input
                      value={s.value}
                      disabled={s.status === "approved" || s.status === "approving"}
                      onChange={(e) => setState((prev) => new Map(prev).set(row.row_id, { ...s, value: e.target.value }))}
                      className="input text-xs w-full"
                    />
                    {row.es_fiambre_kg && (
                      <div className="flex items-center gap-3 mt-1">
                        <label className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                          {t("convertidor.columns.precio")}
                          <input
                            type="text"
                            inputMode="decimal"
                            value={s.precio}
                            disabled={s.status === "approved" || s.status === "approving"}
                            onChange={(e) => setState((prev) => new Map(prev).set(row.row_id, { ...s, precio: e.target.value }))}
                            className="input text-xs w-20 py-0.5"
                          />
                        </label>
                        <label className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                          {t("convertidor.columns.precioAnterior")}
                          <input
                            type="text"
                            inputMode="decimal"
                            value={s.precioAnterior}
                            disabled={s.status === "approved" || s.status === "approving"}
                            onChange={(e) => setState((prev) => new Map(prev).set(row.row_id, { ...s, precioAnterior: e.target.value }))}
                            className="input text-xs w-20 py-0.5"
                          />
                        </label>
                      </div>
                    )}
                    {s.value.trim().length > DESCRIPTION_WARN_CHARS && (
                      <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                        {t("convertidor.ai.tooLong")}
                      </p>
                    )}
                    {s.status === "error" && (
                      <p className="text-[10px] text-red-600 dark:text-red-400 mt-0.5">
                        {t("convertidor.ai.rowError")}
                      </p>
                    )}
                  </div>
                  {s.status === "approved" ? (
                    <Check size={16} className="text-emerald-500 shrink-0" />
                  ) : (
                    <button
                      onClick={() => approveOne(row.row_id, row.codigo)}
                      disabled={s.status === "approving" || approvingAll}
                      className={`text-xs shrink-0 disabled:opacity-50 ${
                        s.status === "error" ? "btn-secondary border-red-300 text-red-600 dark:text-red-400" : "btn-secondary"
                      }`}
                    >
                      {s.status === "approving" ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : s.status === "error" ? (
                        t("convertidor.ai.retry")
                      ) : (
                        t("convertidor.ai.approve")
                      )}
                    </button>
                  )}
                </div>
              );
            })}
        </div>

        {!loading && !loadError && state.size > 0 && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={approveAll}
              disabled={approvingAll || loadingMore}
              className="btn-primary w-full text-xs disabled:opacity-50"
            >
              {approvingAll
                ? t("convertidor.ai.approving")
                : loadingMore
                ? t("convertidor.ai.loadingMore", { done: loadMoreProgress?.done ?? 0, total: loadMoreProgress?.total ?? 0 })
                : t("convertidor.ai.approveAll")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
