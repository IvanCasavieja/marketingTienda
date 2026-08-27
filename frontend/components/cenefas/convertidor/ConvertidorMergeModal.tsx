"use client";
import { useEffect, useRef, useState } from "react";
import { Loader2, Merge, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { convertidorApi, type ConvertidorRow, type MaPair } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { DonTinoTrabajando } from "@/components/DonTinoTrabajando";

interface Props {
  pair: MaPair;
  rowA: ConvertidorRow;
  rowB: ConvertidorRow;
  onConfirm: (descripcion: string) => Promise<void>;
  onClose: () => void;
}

const DESCRIPTION_WARN_CHARS = 60; // mismo umbral que ConvertidorAiModal.tsx

export default function ConvertidorMergeModal({ pair, rowA, rowB, onConfirm, onClose }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"not_configured" | "generic" | null>(null);
  const [value, setValue] = useState("");
  const [confirming, setConfirming] = useState(false);
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
      .generarDescripcionesIA([
        {
          row_id: rowA.row_id,
          codigo: `${pair.sku1}-${pair.sku2}`,
          nombre_articulo: pair.base,
          descripcion_web: rowA.descripcion_web || rowB.descripcion_web,
          es_fiambre_kg: rowA.es_fiambre_kg || rowB.es_fiambre_kg,
          // Es el MISMO producto con dos SKUs, así que la unidad de cobro es la
          // misma: alcanza con la que haya resuelto cualquiera de las dos filas.
          unidad_venta: rowA.unidad_venta || rowB.unidad_venta || "",
        },
      ])
      .then(({ data }) => {
        const sugerida = data.suggestions[0]?.descripcion;
        if (mountedRef.current) setValue(sugerida || pair.base);
      })
      .catch((err) => {
        if (!mountedRef.current) return;
        setLoadError(err?.response?.status === 503 ? "not_configured" : "generic");
        setValue(pair.base);
      })
      .finally(finishLoading);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleConfirm() {
    const trimmed = value.trim();
    if (!trimmed) return;
    setConfirming(true);
    try {
      await onConfirm(trimmed);
    } finally {
      if (mountedRef.current) setConfirming(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <p className="text-sm font-semibold flex items-center gap-1.5 text-slate-800 dark:text-slate-100">
            <Merge size={15} className="text-brand-500" /> {t("convertidor.merge.modalTitle")}
          </p>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <div className="text-xs text-slate-500 dark:text-slate-400 space-y-1">
            <p>{pair.sku1} · {rowA.nombre_articulo}</p>
            <p>{pair.sku2} · {rowB.nombre_articulo}</p>
          </div>
          <p className="text-xs text-slate-400">
            {t("convertidor.merge.combinedSkuNotice", { sku: `${pair.sku1}-${pair.sku2}` })}
          </p>

          {loading && (
            <div className="flex flex-col items-center gap-3 py-8">
              <DonTinoTrabajando size={72} />
              <p className="text-xs text-slate-400">{t("convertidor.ai.loading")}</p>
            </div>
          )}

          {!loading && loadError === "not_configured" && (
            <p className="text-sm text-amber-600 dark:text-amber-400 text-center py-4">
              {t("convertidor.ai.notConfigured")}
            </p>
          )}
          {!loading && loadError === "generic" && (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-4">
              {t("convertidor.ai.genericError")}
            </p>
          )}

          {!loading && (
            <div>
              <label className="text-[10px] text-slate-400 uppercase tracking-wide">
                {t("convertidor.merge.descripcionUnica")}
              </label>
              <input
                value={value}
                disabled={confirming}
                onChange={(e) => setValue(e.target.value)}
                className="input text-sm w-full mt-1"
              />
              {value.trim().length > DESCRIPTION_WARN_CHARS && (
                <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                  {t("convertidor.ai.tooLong")}
                </p>
              )}
            </div>
          )}
        </div>

        {!loading && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 flex gap-2">
            <button onClick={onClose} disabled={confirming} className="btn-ghost flex-1 text-xs disabled:opacity-50">
              {t("convertidor.merge.cancel")}
            </button>
            <button
              onClick={handleConfirm}
              disabled={confirming || !value.trim()}
              className="btn-primary flex-1 text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              {confirming ? <Loader2 size={13} className="animate-spin" /> : <Merge size={13} />}
              {confirming ? t("convertidor.merge.confirming") : t("convertidor.merge.confirm")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
