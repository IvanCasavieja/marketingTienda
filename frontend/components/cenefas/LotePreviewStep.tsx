"use client";
import { useEffect, useRef, useState } from "react";
import {
  AlertCircle, ArrowLeft, ChevronLeft, ChevronRight, Download, Loader2, Send,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaLote } from "@/types/cenefas";
import Canvas from "@/components/cenefas/editor/Canvas";

// Preview de un lote: se recorren de a una las cenefas que se van a generar,
// con siguiente/anterior, viendo la primera página de cada una. Confirmar
// dispara las que estén listas y la descarga viene en un ZIP con una
// subcarpeta por Excel.
//
// A diferencia de PreviewStep (una cenefa suelta) acá no se reposicionan
// cuadros: con varias combinaciones a la vez, mover algo en una no dice nada
// de las otras, y el ajuste real va en el diseño de la plantilla.

interface LotePreviewStepProps {
  loteId: string;
  onBack: () => void;
}

export default function LotePreviewStep({ loteId, onBack }: LotePreviewStepProps) {
  const { t } = useTranslation();
  const [lote, setLote] = useState<CenefaLote | null>(null);
  const [indice, setIndice] = useState(0);
  const [confirmando, setConfirmando] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dlRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    async function tick() {
      try {
        const { data } = await cenefasV2Api.getLote(loteId);
        setLote(data);
        // Se sigue consultando mientras haya algo en curso; en "preview" y en
        // "done" ya no cambia nada por su cuenta.
        if (data.status !== "running" && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* reintenta en el proximo tick */
      }
    }
    tick();
    pollRef.current = setInterval(tick, 1500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loteId]);

  async function handleConfirmar() {
    setConfirmando(true);
    try {
      const { data } = await cenefasV2Api.confirmLote(loteId);
      toast.success(t("cenefas.lote.generando", { n: data.confirmadas }));
      // Vuelve a arrancar el polling: las cenefas pasan a "running".
      if (!pollRef.current) {
        pollRef.current = setInterval(async () => {
          try {
            const { data: d } = await cenefasV2Api.getLote(loteId);
            setLote(d);
            if (d.status !== "running" && pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          } catch { /* reintenta */ }
        }, 1500);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setConfirmando(false);
    }
  }

  async function handleDescargar() {
    setDescargando(true);
    try {
      const { data } = await cenefasV2Api.downloadLote(loteId);
      const url = URL.createObjectURL(new Blob([data], { type: "application/zip" }));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = `cenefas_${loteId.slice(0, 8)}.zip`;
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setDescargando(false);
    }
  }

  if (!lote) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 size={26} className="animate-spin text-slate-400" />
        <p className="text-sm text-slate-500 dark:text-slate-400">{t("cenefas.lote.preparando")}</p>
      </div>
    );
  }

  const total = lote.cenefas.length;
  const actual = lote.cenefas[Math.min(indice, total - 1)];
  const listas = lote.cenefas.filter((c) => c.status === "done").length;
  const enPreview = lote.cenefas.filter((c) => c.status === "preview").length;
  const conError = lote.cenefas.filter((c) => c.status === "error");

  return (
    <div className="space-y-4">
      <a ref={dlRef} className="hidden" />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600">
          <ArrowLeft size={15} /> {t("cenefas.lote.volver")}
        </button>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {t("cenefas.lote.resumen", { total, listas })}
        </p>
      </div>

      {conError.length > 0 && (
        <div className="card p-4 border-l-4 border-rose-400 space-y-1">
          <p className="text-sm font-semibold text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
            <AlertCircle size={15} /> {t("cenefas.lote.conError", { n: conError.length })}
          </p>
          {conError.slice(0, 3).map((c, i) => (
            <p key={i} className="text-xs text-slate-500 dark:text-slate-400">
              {c.excel} × {c.template}: {c.validation_report?.error ?? "—"}
            </p>
          ))}
        </div>
      )}

      {/* Navegación */}
      <div className="card p-4 flex items-center justify-between gap-3">
        <button
          onClick={() => setIndice((i) => Math.max(0, i - 1))}
          disabled={indice === 0}
          className="btn-secondary flex items-center gap-1.5 px-3 py-2 disabled:opacity-30"
        >
          <ChevronLeft size={15} /> {t("cenefas.lote.anterior")}
        </button>

        <div className="min-w-0 text-center">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
            {actual?.template}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{actual?.excel}</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {t("cenefas.lote.posicion", { n: Math.min(indice, total - 1) + 1, total })}
            {actual?.row_count ? ` · ${t("cenefas.lote.productos", { n: actual.row_count })}` : ""}
          </p>
        </div>

        <button
          onClick={() => setIndice((i) => Math.min(total - 1, i + 1))}
          disabled={indice >= total - 1}
          className="btn-secondary flex items-center gap-1.5 px-3 py-2 disabled:opacity-30"
        >
          {t("cenefas.lote.siguiente")} <ChevronRight size={15} />
        </button>
      </div>

      {/* Primera página de la cenefa actual */}
      <div className="card p-4">
        {actual?.template_def ? (
          <Canvas
            template={actual.template_def}
            activeFormat={actual.format ?? actual.template_def.master_format}
            selectedComponentId={null}
            onSelectComponent={() => {}}
            onUpdateComponent={() => {}}
            previewData={actual.preview_product}
            previewProducts={actual.preview_products}
            slotBands={actual.slot_bands}
            className="h-[560px]"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-[560px] gap-3">
            <Loader2 size={22} className="animate-spin text-slate-400" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {t("cenefas.lote.procesando")}
            </p>
          </div>
        )}
      </div>

      {/* Acciones */}
      <div className="flex flex-wrap gap-3">
        {enPreview > 0 && (
          <button
            onClick={handleConfirmar}
            disabled={confirmando}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            {confirmando ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {t("cenefas.lote.generarTodas", { n: enPreview })}
          </button>
        )}
        {listas > 0 && (
          <button
            onClick={handleDescargar}
            disabled={descargando}
            className={`flex items-center gap-2 disabled:opacity-50 ${enPreview > 0 ? "btn-secondary" : "btn-primary"}`}
          >
            {descargando ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            {t("cenefas.lote.descargarZip", { n: listas })}
          </button>
        )}
        {lote.status === "running" && (
          <span className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
            <Loader2 size={15} className="animate-spin" /> {t("cenefas.lote.procesando")}
          </span>
        )}
      </div>
    </div>
  );
}
