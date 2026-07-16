"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { convertidorApi, type ConvertidorRow, type DescripcionSugerencia } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { DonTinoTrabajando } from "@/components/DonTinoTrabajando";

interface Props {
  rows: ConvertidorRow[]; // ya filtradas por el caller: solo las que faltan descripción
  onApprove: (rowId: number, sku: string, descripcion: string) => Promise<void>;
  onClose: () => void;
}

type RowState = { value: string; status: "pending" | "approving" | "approved" | "error" };

// Mismo umbral que DESCRIPTION_WARN_CHARS en
// backend/app/services/cenefas/validation_engine.py (60) — se recalcula acá
// en vivo mientras el usuario edita la sugerencia, no solo el "too_long"
// estático que vino del backend al momento de generarla.
const DESCRIPTION_WARN_CHARS = 60;

export default function ConvertidorAiModal({ rows, onApprove, onClose }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"not_configured" | "generic" | null>(null);
  const [meta, setMeta] = useState<{
    failedRowIds: number[];
    truncated: boolean;
    requested: number;
    processed: number;
  } | null>(null);
  const [state, setState] = useState<Map<number, RowState>>(new Map());
  const [approvingAll, setApprovingAll] = useState(false);
  // Si el usuario cierra el modal a mitad de "Aprobar todas", el for-loop de
  // approveAll sigue corriendo (JS no cancela un await por un unmount) —
  // este flag corta el loop entre iteraciones y evita setState en un
  // componente ya desmontado. Los PATCH que ya salieron antes de cerrar
  // siguen su curso igual (correcto: ya se comprometió a guardarlos).
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  useEscapeKey(onClose);

  useEffect(() => {
    convertidorApi
      .generarDescripcionesIA(
        rows.map((r) => ({
          row_id: r.row_id,
          codigo: r.codigo,
          nombre_articulo: r.nombre_articulo,
          descripcion_web: r.descripcion_web,
        }))
      )
      .then(({ data }) => {
        const next = new Map<number, RowState>();
        data.suggestions.forEach((s: DescripcionSugerencia) =>
          next.set(s.row_id, { value: s.descripcion, status: "pending" })
        );
        setState(next);
        setMeta({
          failedRowIds: data.failed_row_ids,
          truncated: data.truncated,
          requested: data.requested_count,
          processed: data.processed_count,
        });
      })
      .catch((err) => setLoadError(err?.response?.status === 503 ? "not_configured" : "generic"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function approveOne(rowId: number, sku: string) {
    const row = state.get(rowId);
    if (!row) return;
    setState((prev) => new Map(prev).set(rowId, { ...row, status: "approving" }));
    try {
      await onApprove(rowId, sku, row.value);
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

          {!loading && !loadError && meta?.truncated && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t("convertidor.ai.truncatedNotice", { processed: meta.processed, requested: meta.requested })}
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
                    <p className="text-[10px] text-slate-400 truncate">
                      {row.codigo} · {row.nombre_articulo}
                    </p>
                    <input
                      value={s.value}
                      disabled={s.status === "approved" || s.status === "approving"}
                      onChange={(e) => setState((prev) => new Map(prev).set(row.row_id, { ...s, value: e.target.value }))}
                      className="input text-xs w-full"
                    />
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
              disabled={approvingAll}
              className="btn-primary w-full text-xs disabled:opacity-50"
            >
              {approvingAll ? t("convertidor.ai.approving") : t("convertidor.ai.approveAll")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
