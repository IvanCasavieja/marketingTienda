"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, AlertTriangle, ArrowLeft, BadgeCheck, CheckCircle2, ChevronLeft, ChevronRight, Download, Loader2, Save, Send, X } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaComponent, CenefaLote, CenefaLoteItem, CenefaTemplate, ComponentOverride } from "@/types/cenefas";
import Canvas from "@/components/cenefas/editor/Canvas";

// Preview de un lote: se recorren de a una las cenefas que se van a generar,
// con siguiente/anterior, viendo la primera página de cada una.
//
// El listado del lote viene LIVIANO (solo estados). El preview de una cenefa
// --definición de componentes + productos-- se pide aparte, y solo el de la
// que se está mirando: traer los 16 en cada polling significaba leer de la
// base varios MB por vuelta, compitiendo con los mismos workers que están
// generando las cenefas. O sea, mirar la pantalla hacía que tardara más.
//
// Cada cenefa del lote es su propio job con su propia plantilla -- mover o
// redimensionar acá edita SOLO la que se está mirando (Canvas.tsx ya vincula
// entre bandas de una misma hoja multi-producto; una cenefa del lote no tiene
// nada que ver con la de al lado, cada una guarda sus propios cambios).

const POLL_MS = 2500;

interface LotePreviewStepProps {
  loteId: string;
  onBack: () => void;
}

export default function LotePreviewStep({ loteId, onBack }: LotePreviewStepProps) {
  const { t } = useTranslation();
  const [lote, setLote] = useState<CenefaLote | null>(null);
  const [indice, setIndice] = useState(0);
  const [detalle, setDetalle] = useState<CenefaLoteItem | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [yaConfirmado, setYaConfirmado] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [bajandoUna, setBajandoUna] = useState<string | null>(null);
  const [verificando, setVerificando] = useState(false);
  const [verifDescartada, setVerifDescartada] = useState(false);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [savingTemplates, setSavingTemplates] = useState(false);
  // Espejo en estado de templatesEditados.current.size, solo para el render
  // del modal — un ref no se puede leer durante el render (React no
  // garantiza que esté al día ahí).
  const [cantPlantillasEditadas, setCantPlantillasEditadas] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dlRef = useRef<HTMLAnchorElement>(null);

  // Por job (cenefa del lote), lo que la persona ajustó en el canvas —
  // arrastre = base_bounds; resize con los 4 puntos = base_bounds +
  // style.font_size (+ segments si es multi-segmento). Se manda tal cual a
  // confirmLote, uno por job, sin importar cuántas cenefas distintas se
  // hayan tocado.
  const overridesPorJob = useRef<Record<string, Record<string, ComponentOverride>>>({});
  // Por plantilla (templateId), el último `template_def` con los cambios ya
  // aplicados — de acá sale lo que se manda a updateTemplate si la persona
  // elige "Guardar" en el modal. Varias cenefas del lote pueden compartir
  // plantilla; se guarda la versión más reciente de cada una.
  const templatesEditados = useRef<Map<string, CenefaTemplate>>(new Map());

  const consultar = useCallback(async () => {
    try {
      const { data } = await cenefasV2Api.getLote(loteId);
      setLote(data);
      if (data.status !== "running" && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {
      /* reintenta en el proximo tick */
    }
  }, [loteId]);

  useEffect(() => {
    consultar();
    pollRef.current = setInterval(consultar, POLL_MS);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [consultar]);

  const total = lote?.cenefas.length ?? 0;
  const posicion = total ? Math.min(indice, total - 1) : 0;
  const actual = lote?.cenefas[posicion];
  const actualId = actual?.id;
  const actualStatus = actual?.status;

  // Preview de la cenefa que se esta mirando. Se vuelve a pedir cuando cambia
  // de posicion o cuando esa cenefa recien llega a "preview".
  useEffect(() => {
    let cancelado = false;
    setDetalle(null);
    setSelectedComponentId(null); // cambiar de cenefa deselecciona -- no es el mismo set de componentes
    if (!actualId || actualStatus !== "preview") return;
    cenefasV2Api.getJob(actualId)
      .then(({ data }) => { if (!cancelado) setDetalle(data as unknown as CenefaLoteItem); })
      .catch(() => { /* se muestra el estado de carga */ });
    return () => { cancelado = true; };
  }, [actualId, actualStatus]);

  useEffect(() => {
    if (!detalle?.template_def) return;
    const descs = detalle.template_def.components
      .filter((c) => c.variable === "descripcion")
      .map((c) => ({ id: c.id.slice(0, 8), x: c.base_bounds.x, y: c.base_bounds.y }));
    // eslint-disable-next-line no-console
    console.log("[CLAUDE-DEBUG] detalle actualizado, descripciones:", JSON.stringify(descs));
  }, [detalle]);

  // Arrastre/resize en el canvas de LA CENEFA QUE SE ESTÁ MIRANDO — se
  // guarda contra actualId (el job actual), nunca se mezcla con lo que se
  // ajustó en otra cenefa del lote.
  function handleUpdateComponent(id: string, updates: Partial<CenefaComponent>) {
    if (!actualId) return;
    // eslint-disable-next-line no-console
    console.log("[CLAUDE-DEBUG] handleUpdateComponent llamado", id, updates.base_bounds, "actualId:", actualId);
    setDetalle((prev) => {
      if (!prev?.template_def) {
        // eslint-disable-next-line no-console
        console.log("[CLAUDE-DEBUG] setDetalle: prev.template_def es null/undefined, NO SE APLICA");
        return prev;
      }
      const nuevoDef: CenefaTemplate = {
        ...prev.template_def,
        components: prev.template_def.components.map((c) => (c.id === id ? { ...c, ...updates } : c)),
      };
      if (actual?.template_id) {
        templatesEditados.current.set(actual.template_id, nuevoDef);
        setCantPlantillasEditadas(templatesEditados.current.size);
      }
      return { ...prev, template_def: nuevoDef };
    });
    const previo = overridesPorJob.current[actualId]?.[id] ?? { id };
    overridesPorJob.current[actualId] = {
      ...overridesPorJob.current[actualId],
      [id]: {
        ...previo,
        ...(updates.base_bounds ? { base_bounds: updates.base_bounds } : {}),
        ...(updates.style       ? { style: { ...previo.style, ...updates.style } } : {}),
        ...(updates.segments    ? { segments: updates.segments } : {}),
      },
    };
  }

  function hayCambiosPendientes(): boolean {
    return Object.values(overridesPorJob.current).some((porComp) => Object.keys(porComp).length > 0);
  }

  async function handleConfirmar() {
    setConfirmando(true);
    setYaConfirmado(true);   // el boton no vuelve: un segundo click no dispara nada
    try {
      const overrides: Record<string, ComponentOverride[]> = {};
      for (const [jobId, porComp] of Object.entries(overridesPorJob.current)) {
        const vals = Object.values(porComp);
        if (vals.length) overrides[jobId] = vals;
      }
      const { data } = await cenefasV2Api.confirmLote(loteId, overrides);
      if (data.confirmadas > 0) {
        toast.success(t("cenefas.lote.generando", { n: data.confirmadas }));
      }
      if (!pollRef.current) pollRef.current = setInterval(consultar, POLL_MS);
      consultar();
    } catch (err: any) {
      setYaConfirmado(false);
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setConfirmando(false);
    }
  }

  // Click del botón "Generar": si hay ajustes pendientes y tocan al menos
  // una plantilla propia del equipo, pregunta primero si guardarlos ahí
  // (mismo criterio que PreviewStep). Sin cambios, sigue directo.
  function handleConfirmarClick() {
    if (hayCambiosPendientes() && cantPlantillasEditadas > 0) {
      setShowSaveModal(true);
      return;
    }
    handleConfirmar();
  }

  async function handleSaveModalChoice(guardar: boolean) {
    setShowSaveModal(false);
    if (guardar) {
      setSavingTemplates(true);
      try {
        await Promise.all(
          [...templatesEditados.current.entries()].map(([id, def]) => cenefasV2Api.updateTemplate(id, def)),
        );
        toast.success(
          templatesEditados.current.size === 1
            ? "Guardado en la plantilla — las próximas cenefas ya salen con este diseño."
            : `Guardado en ${templatesEditados.current.size} plantillas — las próximas cenefas ya salen con este diseño.`,
        );
      } catch {
        toast.error("No se pudo guardar algún cambio en la plantilla (estas cenefas se generan igual).");
      } finally {
        setSavingTemplates(false);
      }
    }
    handleConfirmar();
  }

  async function descargarUna(jobId: string) {
    setBajandoUna(jobId);
    try {
      const { data, headers } = await cenefasV2Api.downloadJob(jobId);
      const url = URL.createObjectURL(new Blob([data]));
      // El backend ya manda el nombre real (plantilla + Excel) en la cabecera.
      const cd = String(headers?.["content-disposition"] ?? "");
      const m = cd.match(/filename="?([^";]+)"?/);
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = m?.[1] ?? "cenefa.pptx";
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setBajandoUna(null);
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

  // Una persona mira el archivo y confirma que salio bien. Ademas de sumar
  // aparte en el informe de produccion, decide la retencion: el archivo de
  // una corrida verificada se conserva para siempre (se puede volver a bajar
  // cuando sea); el de una sin verificar se borra a los dias configurados y
  // solo quedan los numeros.
  async function confirmarVerificacion() {
    setVerificando(true);
    try {
      const hechas = lote?.cenefas.filter((c) => c.status === "done" && c.id) ?? [];
      await Promise.all(hechas.map((c) => cenefasV2Api.verificarCorrida(c.id!, true)));
      toast.success(t("cenefas.lote.verifOk", { n: hechas.length }));
      consultar();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setVerificando(false);
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

  const listas = lote.cenefas.filter((c) => c.status === "done").length;
  const todasVerificadas =
    listas > 0 && lote.cenefas.filter((c) => c.status === "done").every((c) => c.verificado);
  const enPreview = lote.cenefas.filter((c) => c.status === "preview").length;
  const pendientes = lote.cenefas.filter((c) => c.status === "pending" || c.status === "running").length;
  const conError = lote.cenefas.filter((c) => c.status === "error");

  // La revisión de la cenefa que se está mirando. Se de-duplica por título
  // porque el mismo Excel emparejado con varias plantillas repite el hallazgo.
  const revision = (() => {
    const vistos = new Set<string>();
    return (actual?.revision ?? []).filter((r) => {
      if (vistos.has(r.titulo)) return false;
      vistos.add(r.titulo);
      return true;
    });
  })();
  const graves = revision.filter((r) => r.nivel === "alto").length;

  return (
    <div className="space-y-4">
      <a ref={dlRef} className="hidden" />

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600">
          <ArrowLeft size={15} /> {t("cenefas.lote.volver")}
        </button>
        <div className="text-right">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {t("cenefas.lote.resumen", { total, listas })}
          </p>
          {pendientes > 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500 flex items-center gap-1.5 justify-end mt-0.5">
              <Loader2 size={11} className="animate-spin" />
              {t("cenefas.lote.faltanProcesar", { n: pendientes })}
            </p>
          )}
        </div>
      </div>

      {/* Progreso: sin esto, con 16 cenefas parece colgado */}
      {pendientes > 0 && (
        <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
          <div
            className="h-full bg-brand-500 transition-all duration-500"
            style={{ width: `${Math.round(((total - pendientes) / Math.max(total, 1)) * 100)}%` }}
          />
        </div>
      )}

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

      {/* Revisión del archivo: qué va a salir mal, antes de confirmar. Nunca
          bloquea -- a veces el que sabe es el que está mirando. */}
      {revision.length > 0 && (
        <div className="card p-4 space-y-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
              <AlertTriangle size={15} className={graves > 0 ? "text-rose-500" : "text-amber-500"} />
              Revisión del archivo
            </p>
            <span className="text-[11px] text-slate-400">
              {graves > 0
                ? `${graves} para corregir antes de confirmar`
                : `${revision.length} para revisar`}
            </span>
          </div>
          {revision.map((r, i) => (
            <div key={i}
                 className={`rounded-lg p-3 border-l-[3px] ${
                   r.nivel === "alto"
                     ? "border-rose-400 bg-rose-50/60 dark:bg-rose-950/20"
                     : "border-amber-400 bg-amber-50/60 dark:bg-amber-950/20"
                 }`}>
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">{r.titulo}</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">{r.detalle}</p>
              <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-1">
                <span className="font-semibold">Qué hacer: </span>{r.sugerencia}
              </p>
            </div>
          ))}
          <p className="text-[11px] text-slate-400 dark:text-slate-500">
            Podés confirmar igual: esto es un aviso, no un bloqueo.
          </p>
        </div>
      )}

      {/* Navegación */}
      <div className="card p-4 flex items-center justify-between gap-3">
        <button
          onClick={() => setIndice(Math.max(0, posicion - 1))}
          disabled={posicion === 0}
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
            {t("cenefas.lote.posicion", { n: posicion + 1, total })}
            {actual?.row_count ? ` · ${t("cenefas.lote.productos", { n: actual.row_count })}` : ""}
          </p>
        </div>

        <button
          onClick={() => setIndice(Math.min(total - 1, posicion + 1))}
          disabled={posicion >= total - 1}
          className="btn-secondary flex items-center gap-1.5 px-3 py-2 disabled:opacity-30"
        >
          {t("cenefas.lote.siguiente")} <ChevronRight size={15} />
        </button>
      </div>

      {/* Primera página de la cenefa actual */}
      <div className="card p-4">
        {detalle?.template_def ? (
          <Canvas
            key={actualId}
            template={detalle.template_def}
            activeFormat={detalle.format ?? detalle.template_def.master_format}
            selectedComponentId={selectedComponentId}
            onSelectComponent={setSelectedComponentId}
            onUpdateComponent={handleUpdateComponent}
            previewData={detalle.preview_product}
            previewProducts={detalle.preview_products}
            slotBands={detalle.slot_bands}
            className="h-[560px]"
          />
        ) : actualStatus === "done" ? (
          // Al generar la cenefa se libera su preview (ver pop_job_products en
          // jobs.py), asi que no hay nada que dibujar y nunca lo va a haber.
          // Antes esto era un spinner eterno: parecia colgado y no informaba
          // nada. Ahora se dice que esta lista y se ofrece bajarla sola.
          <div className="flex flex-col items-center justify-center h-[560px] gap-4">
            <span className="w-14 h-14 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <CheckCircle2 size={26} className="text-emerald-500" />
            </span>
            <div className="text-center">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                {t("cenefas.lote.yaGenerada")}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                {actual?.row_count
                  ? t("cenefas.lote.productos", { n: actual.row_count })
                  : ""}
              </p>
            </div>
            {actualId && (
              <button
                onClick={() => descargarUna(actualId)}
                disabled={bajandoUna === actualId}
                className="btn-secondary flex items-center gap-2 disabled:opacity-50"
              >
                {bajandoUna === actualId
                  ? <Loader2 size={15} className="animate-spin" />
                  : <Download size={15} />}
                {t("cenefas.lote.descargarUna")}
              </button>
            )}
          </div>
        ) : actualStatus === "error" ? (
          <div className="flex flex-col items-center justify-center h-[560px] gap-3 px-8">
            <span className="w-14 h-14 rounded-full bg-rose-500/10 flex items-center justify-center">
              <AlertCircle size={26} className="text-rose-500" />
            </span>
            <p className="text-sm text-rose-600 dark:text-rose-400 text-center">
              {actual?.validation_report?.error ?? t("cenefas.unknownError")}
            </p>
          </div>
        ) : (
          // Mientras esta cenefa no tenga preview, el cuadro grande no puede
          // mostrar nada. Antes decia "En cola — cenefa 1 de 16", que era
          // repetir la barra de progreso de arriba en un espacio enorme. Se
          // usa para lo que no esta en ningun otro lado: el estado de las 16,
          // y para saltar a cualquiera sin apretar "Siguiente" quince veces.
          <div className="h-[560px] overflow-y-auto -m-1 p-1">
            <div className="grid gap-1.5">
              {lote.cenefas.map((c, i) => {
                const esActual = i === posicion;
                const estado = c.status ?? "pending";
                const color = {
                  done:    "text-emerald-500 bg-emerald-500/10",
                  preview: "text-brand-500 bg-brand-500/10",
                  error:   "text-rose-500 bg-rose-500/10",
                }[estado] ?? "text-slate-400 bg-slate-400/10";
                return (
                  <button
                    key={c.id ?? i}
                    onClick={() => setIndice(i)}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border-2 text-left transition-colors ${
                      esActual
                        ? "border-brand-400 bg-brand-50/50 dark:bg-brand-950/20"
                        : "border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/60"
                    }`}
                  >
                    <span className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold ${color}`}>
                      {i + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
                        {c.template}
                      </span>
                      <span className="block text-[11px] text-slate-400 dark:text-slate-500 truncate">
                        {c.excel}
                      </span>
                    </span>
                    <span className="shrink-0 flex items-center gap-1.5">
                      {estado === "done" && <CheckCircle2 size={14} className="text-emerald-500" />}
                      {estado === "error" && <AlertCircle size={14} className="text-rose-500" />}
                      {(estado === "pending" || estado === "running") && (
                        <Loader2 size={13} className="animate-spin text-slate-400" />
                      )}
                      <span className="text-[11px] text-slate-400 dark:text-slate-500">
                        {t(`cenefas.lote.estado.${estado}`)}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Acciones */}
      <div className="flex flex-wrap gap-3 items-center">
        {enPreview > 0 && !yaConfirmado && (
          <button
            onClick={handleConfirmarClick}
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
            className={`flex items-center gap-2 disabled:opacity-50 ${enPreview > 0 && !yaConfirmado ? "btn-secondary" : "btn-primary"}`}
          >
            {descargando ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            {t("cenefas.lote.descargarZip", { n: listas })}
          </button>
        )}
      </div>

      {/* Verificacion humana: cuando todo termino, se pregunta si salio bien.
          Confirmar guarda el archivo para siempre (se puede volver a bajar
          cuando sea) y la corrida suma como verificada en el informe; sin
          confirmar, el archivo se borra a los dias configurados y quedan solo
          los numeros. */}
      {pendientes === 0 && listas > 0 && !verifDescartada && (
        <div className={`card p-5 border-l-4 ${todasVerificadas ? "border-emerald-400" : "border-brand-400"}`}>
          {todasVerificadas ? (
            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
              <BadgeCheck size={17} /> {t("cenefas.lote.verifHecha")}
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <BadgeCheck size={17} className="text-brand-500" /> {t("cenefas.lote.verifTitulo")}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t("cenefas.lote.verifDetalle")}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={confirmarVerificacion}
                  disabled={verificando}
                  className="btn-primary flex items-center gap-2 disabled:opacity-50"
                >
                  {verificando ? <Loader2 size={15} className="animate-spin" /> : <BadgeCheck size={15} />}
                  {t("cenefas.lote.verifSi")}
                </button>
                <button
                  onClick={() => setVerifDescartada(true)}
                  className="btn-secondary"
                >
                  {t("cenefas.lote.verifAhoraNo")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {showSaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="card w-full max-w-md p-5 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                Vimos que hiciste cambios en el diseño de {cantPlantillasEditadas === 1 ? "esta plantilla" : `${cantPlantillasEditadas} plantillas`}
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5">
                ¿Querés guardarlos para las próximas veces? Si guardás, las siguientes cenefas
                que generes desde {cantPlantillasEditadas === 1 ? "esta plantilla" : "estas plantillas"} ya
                van a salir con este diseño.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
              <button
                onClick={() => handleSaveModalChoice(false)}
                disabled={savingTemplates}
                className="btn-secondary text-xs py-2 px-3.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                <X size={13} /> Solo esta vez
              </button>
              <button
                onClick={() => handleSaveModalChoice(true)}
                disabled={savingTemplates}
                className="btn-primary text-xs py-2 px-3.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                {savingTemplates ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                Guardar en la plantilla
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
