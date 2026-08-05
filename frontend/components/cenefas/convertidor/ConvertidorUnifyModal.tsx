"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Layers, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { convertidorApi, type ConvertidorRow, type UnificarGrupoItem } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { DonTinoTrabajando } from "@/components/DonTinoTrabajando";

interface Props {
  // TODAS las filas de la grilla (matcheadas o no) -- a diferencia de
  // ConvertidorAiModal, acá importa el nombre crudo de cada una, no si ya
  // tiene descripción resuelta.
  rows: ConvertidorRow[];
  onApprove: (grupo: UnificarGrupoItem) => Promise<void>;
  onClose: () => void;
}

type GrupoState = UnificarGrupoItem & {
  status: "pending" | "approving" | "approved" | "error";
};

// Mismo umbral que ConvertidorAiModal.tsx / DESCRIPTION_WARN_CHARS en
// backend/app/services/cenefas/validation_engine.py.
const DESCRIPTION_WARN_CHARS = 60;

export default function ConvertidorUnifyModal({ rows, onApprove, onClose }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"not_configured" | "generic" | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [grupos, setGrupos] = useState<GrupoState[]>([]);
  // "error" es distinto de un vacío legítimo -- data.error=true significa que el
  // análisis en sí falló (red, JSON cortado, etc.), no que Tinín ya revisó todo
  // y no encontró nada para unificar (ver detectar_grupos_unificables).
  const [analysisError, setAnalysisError] = useState(false);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  useEscapeKey(onClose);

  useEffect(() => {
    // Mismo piso mínimo que ConvertidorAiModal.tsx -- nunca corta la
    // animación antes de que la IA real termine, solo evita que se sienta
    // cortada cuando la respuesta llega muy rápido.
    const MIN_LOADING_MS = 6000;
    const start = Date.now();
    const finishLoading = () => {
      const remaining = Math.max(0, MIN_LOADING_MS - (Date.now() - start));
      setTimeout(() => {
        if (mountedRef.current) setLoading(false);
      }, remaining);
    };

    convertidorApi
      .unificarCategoriasIA(
        rows.map((r) => ({
          row_id: r.row_id,
          codigo: r.codigo,
          nombre_articulo: r.nombre_articulo,
          descripcion: r.descripcion,
        }))
      )
      .then(({ data }) => {
        if (!mountedRef.current) return;
        setGrupos(data.grupos.map((g) => ({ ...g, status: "pending" as const })));
        setTruncated(data.truncated);
        setAnalysisError(data.error);
      })
      .catch((err) => {
        if (!mountedRef.current) return;
        setLoadError(err?.response?.status === 503 ? "not_configured" : "generic");
      })
      .finally(finishLoading);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateGrupo(idx: number, patch: Partial<GrupoState>) {
    setGrupos((prev) => prev.map((g, i) => (i === idx ? { ...g, ...patch } : g)));
  }

  async function approveGrupo(idx: number) {
    const g = grupos[idx];
    if (!g || g.status === "approving" || g.status === "approved") return;
    if (!g.grupo.trim() || !g.descripcion.trim()) return;
    updateGrupo(idx, { status: "approving" });
    try {
      await onApprove(g);
      if (mountedRef.current) updateGrupo(idx, { status: "approved" });
    } catch {
      if (mountedRef.current) updateGrupo(idx, { status: "error" });
    }
  }

  function nombreDeFila(rowId: number): string {
    return rows.find((r) => r.row_id === rowId)?.nombre_articulo || "—";
  }

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
            <Layers size={15} className="text-brand-500" /> {t("convertidor.unificar.modalTitle")}
          </p>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {loading && (
            <div className="flex flex-col items-center gap-3 py-8">
              <DonTinoTrabajando size={72} />
              <p className="text-xs text-slate-400">{t("convertidor.unificar.loading")}</p>
            </div>
          )}

          {!loading && loadError === "not_configured" && (
            <p className="text-sm text-amber-600 dark:text-amber-400 text-center py-8">
              {t("convertidor.ai.notConfigured")}
            </p>
          )}
          {!loading && loadError === "generic" && (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
              {t("convertidor.ai.genericError")}
            </p>
          )}

          {!loading && !loadError && analysisError && (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
              {t("convertidor.ai.genericError")}
            </p>
          )}

          {!loading && !loadError && !analysisError && truncated && (
            <p className="text-xs text-amber-600 dark:text-amber-400">{t("convertidor.unificar.truncated")}</p>
          )}

          {!loading && !loadError && !analysisError && grupos.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-8">
              {t("convertidor.unificar.noGroups")}
            </p>
          )}

          {!loading &&
            !loadError &&
            !analysisError &&
            grupos.map((g, idx) => (
              <div key={idx} className="border border-slate-100 dark:border-slate-800 rounded-lg p-3 space-y-2">
                <input
                  value={g.grupo}
                  disabled={g.status === "approved" || g.status === "approving"}
                  onChange={(e) => updateGrupo(idx, { grupo: e.target.value })}
                  className="input text-xs w-full font-semibold"
                />
                <div className="text-[10px] text-slate-400 space-y-0.5">
                  {g.row_ids.map((rowId, i) => (
                    <p key={rowId} className="truncate">
                      {g.skus[i]} · {nombreDeFila(rowId)}
                    </p>
                  ))}
                </div>
                {g.status !== "approved" && (
                  <p className="text-[10px] text-amber-600 dark:text-amber-400">
                    {t("convertidor.unificar.combinedSkuNotice", { codigo: g.skus.join(" - "), count: g.skus.length })}
                  </p>
                )}
                <div>
                  <label className="text-[10px] text-slate-400 uppercase tracking-wide">
                    {t("convertidor.unificar.descripcionUnificada")}
                  </label>
                  <input
                    value={g.descripcion}
                    disabled={g.status === "approved" || g.status === "approving"}
                    onChange={(e) => updateGrupo(idx, { descripcion: e.target.value })}
                    className="input text-xs w-full mt-1"
                  />
                  {g.descripcion.trim().length > DESCRIPTION_WARN_CHARS && (
                    <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                      {t("convertidor.ai.tooLong")}
                    </p>
                  )}
                  {g.status === "error" && (
                    <p className="text-[10px] text-red-600 dark:text-red-400 mt-0.5">
                      {t("convertidor.ai.rowError")}
                    </p>
                  )}
                </div>
                <div className="flex justify-end">
                  {g.status === "approved" ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-500">
                      <Check size={14} /> {t("convertidor.unificar.approved")}
                    </span>
                  ) : (
                    <button
                      onClick={() => approveGrupo(idx)}
                      disabled={g.status === "approving" || !g.grupo.trim() || !g.descripcion.trim()}
                      className={`text-xs disabled:opacity-50 ${
                        g.status === "error" ? "btn-secondary border-red-300 text-red-600 dark:text-red-400" : "btn-primary"
                      }`}
                    >
                      {g.status === "approving" ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : g.status === "error" ? (
                        t("convertidor.ai.retry")
                      ) : (
                        t("convertidor.unificar.approve")
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
