"use client";
import { useEffect, useRef, useState } from "react";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaComponent, CenefaJob, CenefaTemplate, ComponentBounds } from "@/types/cenefas";
import { ArrowLeft, Download, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import Canvas from "@/components/cenefas/editor/Canvas";

// Paso compartido por Redexpres y Rompe Precios: el job se generó hasta
// quedar en status="preview" (ver jobs.py) con la definición de componentes
// y la primera fila real de productos. Acá se muestra en el mismo Canvas del
// editor v2, con datos resueltos en vez de {variable}, permitiendo arrastrar
// componentes antes de confirmar el render final.

interface PreviewStepProps {
  jobId: string;
  onBack: () => void;
}

export default function PreviewStep({ jobId, onBack }: PreviewStepProps) {
  const { t } = useTranslation();
  const [job, setJob] = useState<CenefaJob | null>(null);
  const [template, setTemplate] = useState<CenefaTemplate | null>(null);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const dirtyBounds = useRef<Record<string, ComponentBounds>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dlRef = useRef<HTMLAnchorElement>(null);

  // Poll hasta que el job llegue a "preview" (o falle)
  useEffect(() => {
    async function tick() {
      try {
        const { data } = await cenefasV2Api.getJob(jobId);
        setJob(data);
        if (data.status === "preview" && data.template_def) {
          setTemplate(data.template_def);
          if (pollRef.current) clearInterval(pollRef.current);
        } else if (data.status === "error") {
          setErrorMsg(data.validation_report?.error ?? t("cenefas.previewStep.previewError"));
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        /* ignore, reintenta en el próximo tick */
      }
    }
    tick();
    pollRef.current = setInterval(tick, 1500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  function handleUpdateComponent(id: string, updates: Partial<CenefaComponent>) {
    setTemplate((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        components: prev.components.map((c) => (c.id === id ? { ...c, ...updates } : c)),
      };
    });
    if (updates.base_bounds) {
      dirtyBounds.current[id] = updates.base_bounds;
    }
  }

  async function triggerDownload() {
    const { data: blob } = await cenefasV2Api.downloadJob(jobId);
    const url = URL.createObjectURL(new Blob([blob]));
    if (dlRef.current) {
      dlRef.current.href = url;
      dlRef.current.download = `cenefa_${jobId.slice(0, 8)}.pptx`;
      dlRef.current.click();
    }
    URL.revokeObjectURL(url);
    toast.success(t("cenefas.previewStep.downloaded"));
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      // Un job ya confirmado no se puede volver a confirmar (el backend
      // devuelve 409 — es un guard a propósito contra renders duplicados).
      // Si ya se confirmó en esta sesión, solo volvemos a descargar el
      // mismo archivo ya generado, sin tocar el job de nuevo.
      if (confirmed) {
        await triggerDownload();
        return;
      }

      const components = Object.entries(dirtyBounds.current).map(([id, base_bounds]) => ({ id, base_bounds }));
      await cenefasV2Api.confirmJob(jobId, components);

      // Poll hasta "done", después descarga automática. OJO: no pisar el
      // estado `job` acá con setJob(data) — apenas se confirma, el status
      // pasa a "running" y _job_to_dict() deja de mandar template_def/
      // preview_product (solo van con status="preview"), así que
      // sobreescribir job vaciaba el Canvas (previewData quedaba en {})
      // justo al confirmar, antes incluso de terminar de renderizar.
      //
      // Límite de intentos: sin esto, un job trabado en "running" (ver
      // _RENDER_TIMEOUT_SECONDS en jobs.py, que debería evitar esto del lado
      // del backend) dejaba este loop esperando en silencio para siempre —
      // "no para de estar cargando" sin ningún error visible. 150 × 1200ms =
      // 180s, alineado con el timeout del backend más el margen del propio
      // polling.
      const MAX_CONFIRM_ATTEMPTS = 150;
      await new Promise<void>((resolve, reject) => {
        let attempts = 0;
        const iv = setInterval(async () => {
          attempts++;
          try {
            const { data } = await cenefasV2Api.getJob(jobId);
            if (data.status === "done") {
              clearInterval(iv);
              resolve();
            } else if (data.status === "error") {
              clearInterval(iv);
              reject(new Error(data.validation_report?.error ?? t("cenefas.previewStep.generateError")));
            } else if (attempts >= MAX_CONFIRM_ATTEMPTS) {
              clearInterval(iv);
              reject(new Error(t("cenefas.previewStep.confirmTimeout")));
            }
          } catch {
            if (attempts >= MAX_CONFIRM_ATTEMPTS) {
              clearInterval(iv);
              reject(new Error(t("cenefas.previewStep.confirmTimeout")));
            }
            /* si no, reintenta */
          }
        }, 1200);
      });

      await triggerDownload();
      setConfirmed(true);
    } catch (e: any) {
      toast.error(e?.message ?? t("cenefas.previewStep.confirmError"));
    } finally {
      setConfirming(false);
    }
  }

  if (errorMsg) {
    return (
      <div className="card p-8 flex flex-col items-center text-center gap-3">
        <p className="text-sm text-red-500">{errorMsg}</p>
        <button onClick={onBack} className="btn-secondary text-sm py-2 px-4">
          <ArrowLeft size={14} /> {t("cenefas.previewStep.back")}
        </button>
      </div>
    );
  }

  if (!template || !job) {
    return (
      <div className="card p-10 flex flex-col items-center justify-center gap-3">
        <RefreshCw size={22} className="animate-spin text-slate-400" />
        <p className="text-sm text-slate-500 dark:text-slate-400">{t("cenefas.previewStep.generatingPreview")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("cenefas.previewStep.title")}</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t("cenefas.previewStep.subtitle", { count: job.row_count ?? 0 })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onBack} disabled={confirming} className="btn-secondary text-xs py-2 px-3 disabled:opacity-50">
            <ArrowLeft size={13} /> {t("cenefas.previewStep.back")}
          </button>
          <button onClick={handleConfirm} disabled={confirming} className="btn-primary text-xs py-2 px-4 disabled:opacity-50">
            {confirming
              ? <span className="flex items-center gap-1.5"><Loader2 size={13} className="animate-spin" /> {t("cenefas.generating")}</span>
              : <span className="flex items-center gap-1.5">
                  <Download size={13} />
                  {confirmed ? t("cenefas.previewStep.downloadAgain") : t("cenefas.previewStep.confirmAndDownload")}
                </span>
            }
          </button>
        </div>
      </div>

      <Canvas
        className="h-[70vh]"
        template={template}
        activeFormat={job.format}
        selectedComponentId={selectedComponentId}
        onSelectComponent={setSelectedComponentId}
        onUpdateComponent={handleUpdateComponent}
        previewData={job.preview_product ?? {}}
        slotBands={job.slot_bands}
        previewProducts={job.preview_products}
      />

      <a ref={dlRef} className="hidden" />
    </div>
  );
}
