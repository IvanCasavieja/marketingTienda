"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, FileText, Loader2, Trash2, Upload, X } from "lucide-react";
import { facturacionApi, facturacionCuentasApi, type ConfirmarDocumentoPayload, type FacturacionCuenta, type FacturacionDocumento } from "@/lib/api";
import { DogTiMascot, DogTiMini } from "@/components/DogTiMascot";
import { fMoneyExact } from "@/lib/format";
import { useEscapeKey } from "@/hooks/useEscapeKey";

// Flujo: subir uno o varios PDFs -> DogTi los lee todos en paralelo
// (extracting) -> revisión paginada, una factura por página, cada una
// precompletada con lo que DogTi propuso y editable -> confirmar (crea el
// movimiento/canje) o descartar, página por página. Mismo criterio que el
// Convertidor de Excel: nada se guarda hasta que el usuario confirma lo que
// ve en pantalla, factura por factura.

type Step = "upload" | "extracting" | "review";
type Resultado = "pendiente" | "confirmado" | "descartado";

// Mismo tope que _MAX_ARCHIVOS_POR_CARGA en el backend (ver
// routes/facturacion.py) -- todo el lote corre dentro de una sola request.
const MAX_ARCHIVOS = 10;

interface DocForm {
  documento: FacturacionDocumento;
  pdfUrl: string | null;
  pdfLoading: boolean;
  tipo: "movimiento" | "canje";
  tipoMovimiento: "entrada" | "salida";
  monto: string;
  moneda: string;
  concepto: string;
  proveedorMarca: string;
  numeroFactura: string;
  fecha: string;
  cuentaId: number | null;
  estado: string;
  vigenciaDesde: string;
  vigenciaHasta: string;
  resultado: Resultado;
  confirming: boolean;
  discarding: boolean;
  error: string | null;
}

interface FacturaUploadModalProps {
  onClose: () => void;
  onConfirmed: () => void;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{label}</span>
      {children}
    </label>
  );
}

const CONFIANZA_BADGE: Record<string, string> = {
  alta: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  media: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  baja: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400",
};

function initDocForm(documento: FacturacionDocumento, cuentas: FacturacionCuenta[]): DocForm {
  const ex = documento.extraccion;
  // DogTi matchea por nombre contra las cuentas activas que ya le pasamos
  // como opciones -- si no encontró señal clara en el documento, o el
  // nombre sugerido no matchea ninguna (cuenta desactivada entre medio,
  // etc.), no se precompleta y la persona elige a mano.
  const sugerida = ex?.cuenta_sugerida
    ? cuentas.find((c) => c.nombre.toLowerCase() === ex.cuenta_sugerida!.toLowerCase())
    : undefined;
  return {
    documento,
    pdfUrl: null,
    pdfLoading: false,
    tipo: ex?.tipo_sugerido === "canje" ? "canje" : "movimiento",
    // Una factura de proveedor recibida es casi siempre una salida (plata
    // que sale) -- DogTi no adivina esto, el usuario la cambia a mano si
    // hace falta.
    tipoMovimiento: "salida",
    monto: ex?.monto != null ? String(ex.monto) : "",
    moneda: ex?.moneda || "UYU",
    concepto: ex?.concepto || "",
    proveedorMarca: ex?.proveedor_marca || "",
    numeroFactura: ex?.numero_factura || "",
    fecha: ex?.fecha || todayISO(),
    cuentaId: sugerida?.id ?? null,
    estado: "pendiente",
    vigenciaDesde: ex?.vigencia_desde || "",
    vigenciaHasta: ex?.vigencia_hasta || "",
    resultado: "pendiente",
    confirming: false,
    discarding: false,
    error: null,
  };
}

export default function FacturaUploadModal({ onClose, onConfirmed }: FacturaUploadModalProps) {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>("upload");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [docs, setDocs] = useState<DocForm[]>([]);
  const [pagina, setPagina] = useState(0);
  const docsRef = useRef<DocForm[]>([]);

  const [cuentas, setCuentas] = useState<FacturacionCuenta[]>([]);
  useEffect(() => {
    facturacionCuentasApi.listar().then(({ data }) => setCuentas(data)).catch(() => {});
  }, []);

  useEffect(() => {
    docsRef.current = docs;
  }, [docs]);

  useEffect(() => {
    // Revoca los object URLs de los blobs de PDF al desmontar, sin importar
    // en qué paso haya quedado el modal -- evita filtrar memoria.
    return () => {
      docsRef.current.forEach((d) => {
        if (d.pdfUrl) URL.revokeObjectURL(d.pdfUrl);
      });
    };
  }, []);

  function handleClose() {
    docs.forEach((d) => {
      if (d.pdfUrl) URL.revokeObjectURL(d.pdfUrl);
    });
    onClose();
  }

  const busy = docs.some((d) => d.confirming || d.discarding);
  useEscapeKey(handleClose, step !== "extracting" && !busy);

  function handleAddFiles(newFiles: File[]) {
    setUploadError(null);
    setFiles((prev) => {
      const merged = [...prev];
      let dropped = false;
      for (const f of newFiles) {
        if (merged.length >= MAX_ARCHIVOS) { dropped = true; break; }
        if (!merged.some((m) => m.name === f.name && m.size === f.size)) merged.push(f);
      }
      if (dropped) toast.error(t("facturacion.upload.maxFilesReached", { max: MAX_ARCHIVOS }));
      return merged;
    });
  }

  function handleRemoveFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleUpload() {
    if (files.length === 0) return;
    setStep("extracting");
    setUploadError(null);
    try {
      const { data } = await facturacionApi.uploadDocumentos(files);
      setDocs(data.map((d) => initDocForm(d, cuentas)));
      setPagina(0);
      setStep("review");
    } catch (err: any) {
      setUploadError(err?.response?.data?.detail ?? t("facturacion.upload.error"));
      setStep("upload");
    }
  }

  function updateDoc(index: number, patch: Partial<DocForm>) {
    setDocs((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  }

  // Carga el PDF de la página actual la primera vez que se visita.
  const current = docs[pagina] as DocForm | undefined;
  useEffect(() => {
    if (step !== "review" || !current || current.pdfUrl || current.pdfLoading) return;
    const docId = current.documento.id;
    const idx = pagina;
    updateDoc(idx, { pdfLoading: true });
    facturacionApi
      .getDocumentoPdfBlob(docId)
      .then(({ data: blob }) => {
        updateDoc(idx, { pdfUrl: URL.createObjectURL(blob as Blob), pdfLoading: false });
      })
      .catch(() => {
        updateDoc(idx, { pdfLoading: false });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, pagina, current?.documento.id, current?.pdfUrl, current?.pdfLoading]);

  function siguientePendiente(desde: number): number | null {
    for (let i = desde + 1; i < docs.length; i++) {
      if (docs[i].resultado === "pendiente") return i;
    }
    for (let i = 0; i < docs.length; i++) {
      if (docs[i].resultado === "pendiente") return i;
    }
    return null;
  }

  async function handleConfirm() {
    if (!current || current.cuentaId === null) return;
    const idx = pagina;
    updateDoc(idx, { confirming: true, error: null });
    try {
      const payload: ConfirmarDocumentoPayload = {
        tipo: current.tipo,
        tipo_movimiento: current.tipoMovimiento,
        monto: parseFloat(current.monto) || 0,
        moneda: current.moneda || "UYU",
        concepto: current.concepto,
        proveedor_marca: current.proveedorMarca || undefined,
        numero_factura: current.numeroFactura || undefined,
        fecha: current.fecha,
        cuenta_id: current.cuentaId,
        estado: current.tipo === "canje" ? current.estado : undefined,
        vigencia_desde: current.tipo === "canje" ? current.vigenciaDesde || undefined : undefined,
        vigencia_hasta: current.tipo === "canje" ? current.vigenciaHasta || undefined : undefined,
      };
      await facturacionApi.confirmarDocumento(current.documento.id, payload);
      updateDoc(idx, { resultado: "confirmado", confirming: false });
      toast.success(t("facturacion.upload.confirmSuccess"));
      onConfirmed();
      const siguiente = siguientePendiente(idx);
      if (siguiente !== null) setPagina(siguiente);
    } catch (err: any) {
      updateDoc(idx, { confirming: false, error: err?.response?.data?.detail ?? t("facturacion.upload.error") });
    }
  }

  async function handleDiscard() {
    if (!current) return;
    const idx = pagina;
    updateDoc(idx, { discarding: true, error: null });
    try {
      await facturacionApi.descartarDocumento(current.documento.id);
      updateDoc(idx, { resultado: "descartado", discarding: false });
      toast.success(t("facturacion.upload.discardSuccess"));
      const siguiente = siguientePendiente(idx);
      if (siguiente !== null) setPagina(siguiente);
    } catch (err: any) {
      updateDoc(idx, { discarding: false, error: err?.response?.data?.detail ?? t("facturacion.upload.error") });
    }
  }

  const canConfirm =
    !!current &&
    current.monto.trim() !== "" &&
    !isNaN(parseFloat(current.monto)) &&
    current.concepto.trim() !== "" &&
    current.fecha !== "" &&
    current.cuentaId !== null;
  const ex = current?.documento.extraccion;
  const todoResuelto = docs.length > 0 && docs.every((d) => d.resultado !== "pendiente");

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={step === "extracting" ? undefined : handleClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <p className="text-sm font-semibold flex items-center gap-1.5 text-slate-800 dark:text-slate-100">
            <FileText size={15} className="text-brand-500" /> {t("facturacion.upload.title")}
          </p>
          {step !== "extracting" && (
            <button onClick={handleClose} aria-label={t("facturacion.upload.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
              <X size={18} />
            </button>
          )}
        </div>

        {step === "review" && docs.length > 1 && (
          <div className="flex items-center gap-2 px-5 py-2.5 border-b border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setPagina((p) => Math.max(0, p - 1))}
              disabled={pagina === 0}
              aria-label={t("facturacion.upload.prevPage")}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 disabled:opacity-30 disabled:hover:text-slate-400"
            >
              <ChevronLeft size={16} />
            </button>
            <div className="flex items-center gap-1.5 flex-1 justify-center flex-wrap">
              {docs.map((d, i) => (
                <button
                  key={d.documento.id}
                  type="button"
                  onClick={() => setPagina(i)}
                  title={d.documento.filename}
                  className={`w-6 h-6 rounded-full text-[11px] font-semibold flex items-center justify-center transition-colors ${
                    i === pagina
                      ? "bg-brand-600 text-white"
                      : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
                >
                  {d.resultado === "confirmado" ? <Check size={12} /> : d.resultado === "descartado" ? <X size={12} /> : i + 1}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setPagina((p) => Math.min(docs.length - 1, p + 1))}
              disabled={pagina === docs.length - 1}
              aria-label={t("facturacion.upload.nextPage")}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 disabled:opacity-30 disabled:hover:text-slate-400"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
        {step === "review" && docs.length > 1 && (
          <p className="text-center text-[11px] text-slate-400 dark:text-slate-500 -mt-1 pb-1">
            {t("facturacion.upload.pageOf", { page: pagina + 1, total: docs.length })} · {current?.documento.filename}
          </p>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {step === "upload" && (
            <>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("facturacion.upload.title")}</span>
                  <span className="text-xs text-slate-400 dark:text-slate-500">{t("facturacion.upload.filesHint", { max: MAX_ARCHIVOS })}</span>
                </div>
                <div className="flex flex-col gap-2">
                  {files.map((f, i) => (
                    <div
                      key={`${f.name}-${f.size}-${i}`}
                      className="flex items-center gap-2 px-3 py-2.5 rounded-xl border-2 border-brand-400 bg-brand-50 dark:bg-brand-500/10 dark:border-brand-500/40"
                    >
                      <FileText size={16} className="shrink-0 text-brand-500" />
                      <span className="text-sm flex-1 truncate text-brand-700 dark:text-brand-300 font-medium">{f.name}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveFile(i)}
                        aria-label={t("facturacion.upload.removeFile")}
                        className="text-slate-400 hover:text-red-500 shrink-0"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                  {files.length < MAX_ARCHIVOS && (
                    <label className="flex items-center gap-2 px-3 py-3 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700 text-sm text-slate-500 dark:text-slate-400 cursor-pointer hover:border-brand-300 dark:hover:border-brand-500/40 hover:bg-brand-50/50 dark:hover:bg-brand-500/5 transition-colors">
                      <Upload size={16} className="shrink-0" />
                      {t("facturacion.upload.addFile")}
                      <input
                        type="file"
                        accept=".pdf"
                        multiple
                        className="hidden"
                        onChange={(e) => {
                          handleAddFiles(Array.from(e.target.files ?? []));
                          e.target.value = "";
                        }}
                      />
                    </label>
                  )}
                </div>
              </div>
              {uploadError && <p className="text-sm text-red-600 dark:text-red-400">{uploadError}</p>}
            </>
          )}

          {step === "extracting" && (
            <div className="flex flex-col items-center gap-3 py-10">
              <DogTiMascot size={72} />
              <p className="text-xs text-slate-400">
                {t("facturacion.upload.processing", { count: files.length })}
              </p>
            </div>
          )}

          {step === "review" && current && current.resultado !== "pendiente" && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${current.resultado === "confirmado" ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"}`}>
                {current.resultado === "confirmado" ? <Check size={20} /> : <X size={20} />}
              </div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {current.resultado === "confirmado" ? t("facturacion.upload.estadoConfirmado") : t("facturacion.upload.estadoDescartado")}
              </p>
              <p className="text-xs text-slate-400">{current.documento.filename}</p>
            </div>
          )}

          {step === "review" && current && current.resultado === "pendiente" && (
            <>
              {current.documento.extraction_error && (
                <div className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 rounded-lg px-3 py-2">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                  <span>{t("facturacion.upload.extractError")}</span>
                </div>
              )}

              {/* Panel de análisis -- siempre visible cuando DogTi pudo leer
                  el PDF (no solo cuando la confianza es baja), para que la
                  persona vea qué entendió antes de mirar el formulario. */}
              {!current.documento.extraction_error && ex && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 px-3 py-3 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <DogTiMini />
                    <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">{t("facturacion.upload.analysisTitle")}</span>
                    <span className={`ml-auto text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 ${CONFIANZA_BADGE[ex.confianza]}`}>
                      {t(`facturacion.upload.confianza.${ex.confianza}`)}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400">
                    {t("facturacion.upload.analysisSummary", {
                      proveedor: ex.proveedor_marca || "—",
                      concepto: ex.concepto || "—",
                      monto: `${ex.moneda || "UYU"} ${fMoneyExact(ex.monto)}`,
                      tipo: ex.tipo_sugerido === "canje" ? t("facturacion.upload.typeCanje") : t("facturacion.upload.typeMovimiento"),
                    })}
                  </p>
                  {ex.cuenta_sugerida && (
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {t("facturacion.upload.cuentaDetectada", { cuenta: ex.cuenta_sugerida })}
                    </p>
                  )}
                  {ex.notas && ex.notas.trim() !== "" && (
                    <p className="text-xs text-amber-700 dark:text-amber-400 flex items-start gap-1.5 pt-0.5">
                      <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                      <span>{ex.notas}</span>
                    </p>
                  )}
                </div>
              )}

              {cuentas.length === 0 && (
                <div className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 rounded-lg px-3 py-2">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                  <span>
                    {t("facturacion.cuentas.sinCuentas")}{" "}
                    <Link href="/facturacion/cuentas" className="underline font-medium">
                      {t("facturacion.cuentas.crearPrimera")}
                    </Link>
                  </span>
                </div>
              )}

              {current.pdfLoading && (
                <div className="w-full h-56 rounded-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center">
                  <Loader2 size={20} className="animate-spin text-slate-300" />
                </div>
              )}
              {current.pdfUrl && (
                <div>
                  <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">{t("facturacion.upload.pdfPreview")}</p>
                  <iframe src={current.pdfUrl} className="w-full h-56 rounded-lg border border-slate-200 dark:border-slate-700" />
                </div>
              )}

              {/* Toggle Movimiento / Canje */}
              <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => updateDoc(pagina, { tipo: "movimiento" })}
                  className={`flex-1 py-2 transition-colors ${current.tipo === "movimiento" ? "bg-brand-600 text-white" : "bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"}`}
                >
                  {t("facturacion.upload.typeMovimiento")}
                </button>
                <button
                  type="button"
                  onClick={() => updateDoc(pagina, { tipo: "canje" })}
                  className={`flex-1 py-2 transition-colors ${current.tipo === "canje" ? "bg-brand-600 text-white" : "bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"}`}
                >
                  {t("facturacion.upload.typeCanje")}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {current.tipo === "movimiento" && (
                  <Field label={t("facturacion.upload.fieldTipoMovimiento")}>
                    <select
                      value={current.tipoMovimiento}
                      onChange={(e) => updateDoc(pagina, { tipoMovimiento: e.target.value as "entrada" | "salida" })}
                      className="input text-sm"
                    >
                      <option value="salida">{t("facturacion.salida")}</option>
                      <option value="entrada">{t("facturacion.entrada")}</option>
                    </select>
                  </Field>
                )}
                {current.tipo === "canje" && (
                  <Field label={t("facturacion.upload.fieldEstado")}>
                    <select value={current.estado} onChange={(e) => updateDoc(pagina, { estado: e.target.value })} className="input text-sm">
                      <option value="pendiente">{t("facturacion.estados.pendiente")}</option>
                      <option value="activo">{t("facturacion.estados.activo")}</option>
                      <option value="cerrado">{t("facturacion.estados.cerrado")}</option>
                    </select>
                  </Field>
                )}
                <Field label={t("facturacion.upload.fieldCuenta")}>
                  <select
                    value={current.cuentaId ?? ""}
                    onChange={(e) => updateDoc(pagina, { cuentaId: e.target.value ? Number(e.target.value) : null })}
                    disabled={cuentas.length === 0}
                    className="input text-sm disabled:opacity-50"
                  >
                    <option value="" disabled>—</option>
                    {cuentas.map((c) => (
                      <option key={c.id} value={c.id}>{c.nombre}</option>
                    ))}
                  </select>
                </Field>
                <Field label={t("facturacion.upload.fieldFecha")}>
                  <input type="date" value={current.fecha} onChange={(e) => updateDoc(pagina, { fecha: e.target.value })} className="input text-sm" />
                </Field>

                <Field label={t("facturacion.upload.fieldMonto")}>
                  <input type="number" step="0.01" min="0" value={current.monto} onChange={(e) => updateDoc(pagina, { monto: e.target.value })} className="input text-sm" />
                </Field>
                <Field label={t("facturacion.upload.fieldMoneda")}>
                  <input type="text" value={current.moneda} onChange={(e) => updateDoc(pagina, { moneda: e.target.value })} className="input text-sm" />
                </Field>

                <Field label={t("facturacion.upload.fieldProveedor")}>
                  <input type="text" value={current.proveedorMarca} onChange={(e) => updateDoc(pagina, { proveedorMarca: e.target.value })} className="input text-sm" />
                </Field>
                <Field label={t("facturacion.upload.fieldNumeroFactura")}>
                  <input type="text" value={current.numeroFactura} onChange={(e) => updateDoc(pagina, { numeroFactura: e.target.value })} className="input text-sm" />
                </Field>

                <div className="col-span-2">
                  <Field label={t("facturacion.upload.fieldConcepto")}>
                    <input type="text" value={current.concepto} onChange={(e) => updateDoc(pagina, { concepto: e.target.value })} className="input text-sm" />
                  </Field>
                </div>

                {current.tipo === "canje" && (
                  <>
                    <Field label={t("facturacion.upload.fieldVigenciaDesde")}>
                      <input type="date" value={current.vigenciaDesde} onChange={(e) => updateDoc(pagina, { vigenciaDesde: e.target.value })} className="input text-sm" />
                    </Field>
                    <Field label={t("facturacion.upload.fieldVigenciaHasta")}>
                      <input type="date" value={current.vigenciaHasta} onChange={(e) => updateDoc(pagina, { vigenciaHasta: e.target.value })} className="input text-sm" />
                    </Field>
                  </>
                )}
              </div>

              {current.error && <p className="text-sm text-red-600 dark:text-red-400">{current.error}</p>}
            </>
          )}

          {step === "review" && todoResuelto && (
            <div className="flex flex-col items-center gap-1 text-center pt-2">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t("facturacion.upload.allResolvedTitle")}</p>
              <p className="text-xs text-slate-400">{t("facturacion.upload.allResolvedSub", { count: docs.length })}</p>
            </div>
          )}
        </div>

        {step === "upload" && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={handleUpload}
              disabled={files.length === 0}
              className="btn-primary w-full text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              <Upload size={13} /> {t("facturacion.upload.analyze", { count: files.length || 1 })}
            </button>
          </div>
        )}

        {step === "review" && current?.resultado === "pendiente" && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 flex gap-2">
            <button
              onClick={handleDiscard}
              disabled={current.confirming || current.discarding}
              className="btn-ghost flex-1 text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              {current.discarding ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              {current.discarding ? t("facturacion.upload.discarding") : t("facturacion.upload.discard")}
            </button>
            <button
              onClick={handleConfirm}
              disabled={current.confirming || current.discarding || !canConfirm}
              className="btn-primary flex-1 text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              {current.confirming && <Loader2 size={13} className="animate-spin" />}
              {current.confirming ? t("facturacion.upload.confirming") : t("facturacion.upload.confirm")}
            </button>
          </div>
        )}

        {step === "review" && current && current.resultado !== "pendiente" && !todoResuelto && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={() => {
                const siguiente = siguientePendiente(pagina);
                if (siguiente !== null) setPagina(siguiente);
              }}
              className="btn-ghost w-full text-xs flex items-center justify-center gap-1.5"
            >
              {t("facturacion.upload.nextPage")} <ChevronRight size={13} />
            </button>
          </div>
        )}

        {step === "review" && todoResuelto && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
            <button onClick={handleClose} className="btn-primary w-full text-xs">
              {t("facturacion.upload.close")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
