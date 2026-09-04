"use client";
import { useEffect, useRef, useState } from "react";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaComponent, CenefaJob, CenefaTemplate, ComponentOverride } from "@/types/cenefas";
import { ArrowLeft, Download, Loader2, RefreshCw, Save, X } from "lucide-react";
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
  // Al confirmar, si hay cambios y el job viene de una plantilla del equipo,
  // se pregunta si guardarlos ahí para las próximas veces (ver Parte 3 del
  // plan) — nunca si no hay `template_id` (builtin/upload al vuelo) o si no
  // se tocó nada.
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);

  // Por componente, lo que la persona cambió en este preview (arrastre =
  // base_bounds; resize con los 4 puntos = base_bounds + style.font_size,
  // y segments si el cuadro es multi-segmento). Se manda como
  // position_overrides al confirmar (siempre, aplica solo a ESTE job) y,
  // si la persona elige "Guardar", se usa además para armar el `template`
  // completo que se persiste con updateTemplate.
  const dirtyOverrides = useRef<Record<string, ComponentOverride>>({});
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
    const previo = dirtyOverrides.current[id] ?? { id };
    dirtyOverrides.current[id] = {
      ...previo,
      ...(updates.base_bounds ? { base_bounds: updates.base_bounds } : {}),
      ...(updates.style       ? { style: { ...previo.style, ...updates.style } } : {}),
      ...(updates.segments    ? { segments: updates.segments } : {}),
    };
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

      const components = Object.values(dirtyOverrides.current);
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
      // "no para de estar cargando" sin ningún error visible. 550 × 1200ms =
      // 660s, con margen sobre los 600s del backend (confirmado en vivo:
      // 1291 productos reales tardan más de 180s en la instancia de Render,
      // que corre con 1 sola CPU -- ver _RENDER_TIMEOUT_SECONDS en jobs.py).
      const MAX_CONFIRM_ATTEMPTS = 550;
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

  // Click del botón principal: si hay cambios pendientes y el job viene de
  // una plantilla propia del equipo, primero pregunta si guardarlos ahí
  // (modal) antes de seguir. Sin cambios, o sin `template_id` (builtin/
  // upload al vuelo, sin plantilla propia a la que guardar), sigue directo
  // — cero cambio de comportamiento respecto de antes.
  function handleConfirmClick() {
    if (confirmed) { handleConfirm(); return; }
    const hayCambios = Object.keys(dirtyOverrides.current).length > 0;
    if (hayCambios && job?.template_id) {
      setShowSaveModal(true);
      return;
    }
    handleConfirm();
  }

  async function handleSaveModalChoice(guardar: boolean) {
    setShowSaveModal(false);
    if (guardar && job?.template_id && template) {
      setSavingTemplate(true);
      try {
        // `template` ya tiene los base_bounds/font_size finales (Canvas.tsx
        // escribe directo sobre este estado en handleUpdateComponent) — se
        // manda tal cual, mismo objeto que ya se está mostrando.
        await cenefasV2Api.updateTemplate(job.template_id, template);
        toast.success("Guardado en la plantilla — las próximas cenefas ya salen con este diseño.");
      } catch {
        toast.error("No se pudo guardar el cambio en la plantilla (esta cenefa se descarga igual).");
      } finally {
        setSavingTemplate(false);
      }
    }
    // El job se confirma con position_overrides igual que siempre, sin
    // depender de si el guardado de arriba salió bien: esta descarga ya
    // sale con el diseño nuevo de cualquier manera.
    handleConfirm();
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
          <button onClick={handleConfirmClick} disabled={confirming} className="btn-primary text-xs py-2 px-4 disabled:opacity-50">
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

      {showSaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="card w-full max-w-md p-5 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                Vimos que hiciste cambios en el diseño de esta cenefa
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
                ¿Querés guardarlos en la plantilla para las próximas veces? Si guardás,
                las siguientes cenefas que generes desde esta plantilla ya van a salir
                con este diseño, sin que tengas que volver a ajustarlas.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
              <button
                onClick={() => handleSaveModalChoice(false)}
                disabled={savingTemplate}
                className="btn-secondary text-xs py-2 px-3.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                <X size={13} /> Solo esta vez
              </button>
              <button
                onClick={() => handleSaveModalChoice(true)}
                disabled={savingTemplate}
                className="btn-primary text-xs py-2 px-3.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                {savingTemplate
                  ? <Loader2 size={13} className="animate-spin" />
                  : <Save size={13} />}
                Guardar en la plantilla
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
