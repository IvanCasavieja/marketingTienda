"use client";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { AlertTriangle, FileText, Loader2, Trash2, Upload, X } from "lucide-react";
import { facturacionApi, facturacionCuentasApi, type ConfirmarDocumentoPayload, type FacturacionCuenta, type FacturacionDocumento } from "@/lib/api";
import { FileDropField } from "@/components/cenefas/redexpres/RedExpresPanel";
import { DogTiMascot, DogTiMini } from "@/components/DogTiMascot";
import { fMoneyExact } from "@/lib/format";
import { useEscapeKey } from "@/hooks/useEscapeKey";

// Flujo: subir PDF -> DogTi lo lee (extracting) -> formulario de revisión
// precompletado con lo que propuso, editable -> confirmar (crea el
// movimiento/canje) o descartar. Mismo criterio que el Convertidor de
// Excel: nada se guarda hasta que el usuario confirma lo que ve en pantalla.

type Step = "upload" | "extracting" | "review";

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

export default function FacturaUploadModal({ onClose, onConfirmed }: FacturaUploadModalProps) {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [documento, setDocumento] = useState<FacturacionDocumento | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const pdfUrlRef = useRef<string | null>(null);

  // Campos del formulario de revisión
  const [tipo, setTipo] = useState<"movimiento" | "canje">("movimiento");
  const [tipoMovimiento, setTipoMovimiento] = useState<"entrada" | "salida">("salida");
  const [monto, setMonto] = useState("");
  const [moneda, setMoneda] = useState("UYU");
  const [concepto, setConcepto] = useState("");
  const [proveedorMarca, setProveedorMarca] = useState("");
  const [numeroFactura, setNumeroFactura] = useState("");
  const [fecha, setFecha] = useState(todayISO());
  const [cuentaId, setCuentaId] = useState<number | null>(null);
  const [estado, setEstado] = useState("pendiente");
  const [vigenciaDesde, setVigenciaDesde] = useState("");
  const [vigenciaHasta, setVigenciaHasta] = useState("");

  const [cuentas, setCuentas] = useState<FacturacionCuenta[]>([]);
  useEffect(() => {
    facturacionCuentasApi.listar().then(({ data }) => setCuentas(data)).catch(() => {});
  }, []);

  useEffect(() => {
    pdfUrlRef.current = pdfUrl;
  }, [pdfUrl]);

  useEffect(() => {
    // Revoca el object URL del blob al desmontar, sin importar en qué paso
    // haya quedado el modal -- evita filtrar memoria del blob del PDF.
    return () => {
      if (pdfUrlRef.current) URL.revokeObjectURL(pdfUrlRef.current);
    };
  }, []);

  function handleClose() {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    onClose();
  }

  useEscapeKey(handleClose, step !== "extracting" && !confirming && !discarding);

  function initFormFromExtraccion(doc: FacturacionDocumento) {
    const ex = doc.extraccion;
    setTipo(ex?.tipo_sugerido === "canje" ? "canje" : "movimiento");
    // Una factura de proveedor recibida es casi siempre una salida (plata que
    // sale) -- DogTi no adivina esto, el usuario la cambia a mano si hace falta.
    setTipoMovimiento("salida");
    setMonto(ex?.monto != null ? String(ex.monto) : "");
    setMoneda(ex?.moneda || "UYU");
    setConcepto(ex?.concepto || "");
    setProveedorMarca(ex?.proveedor_marca || "");
    setNumeroFactura(ex?.numero_factura || "");
    setFecha(ex?.fecha || todayISO());
    // DogTi matchea por nombre contra las cuentas activas que ya le pasamos
    // como opciones -- si no encontró señal clara en el documento, o el
    // nombre sugerido no matchea ninguna (cuenta desactivada entre medio,
    // etc.), no se precompleta y la persona elige a mano.
    const sugerida = ex?.cuenta_sugerida
      ? cuentas.find((c) => c.nombre.toLowerCase() === ex.cuenta_sugerida!.toLowerCase())
      : undefined;
    setCuentaId(sugerida?.id ?? null);
    setEstado("pendiente");
    setVigenciaDesde(ex?.vigencia_desde || "");
    setVigenciaHasta(ex?.vigencia_hasta || "");
  }

  async function handleUpload() {
    if (!file) return;
    setStep("extracting");
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await facturacionApi.uploadDocumento(fd);
      setDocumento(data);
      initFormFromExtraccion(data);
      setStep("review");
      facturacionApi
        .getDocumentoPdfBlob(data.id)
        .then(({ data: blob }) => setPdfUrl(URL.createObjectURL(blob as Blob)))
        .catch(() => {});
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("facturacion.upload.error"));
      setStep("upload");
    }
  }

  async function handleConfirm() {
    if (!documento || cuentaId === null) return;
    setConfirming(true);
    setError(null);
    try {
      const payload: ConfirmarDocumentoPayload = {
        tipo,
        tipo_movimiento: tipoMovimiento,
        monto: parseFloat(monto) || 0,
        moneda: moneda || "UYU",
        concepto,
        proveedor_marca: proveedorMarca || undefined,
        numero_factura: numeroFactura || undefined,
        fecha,
        cuenta_id: cuentaId,
        estado: tipo === "canje" ? estado : undefined,
        vigencia_desde: tipo === "canje" ? vigenciaDesde || undefined : undefined,
        vigencia_hasta: tipo === "canje" ? vigenciaHasta || undefined : undefined,
      };
      await facturacionApi.confirmarDocumento(documento.id, payload);
      toast.success(t("facturacion.upload.confirmSuccess"));
      onConfirmed();
      handleClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("facturacion.upload.error"));
    } finally {
      setConfirming(false);
    }
  }

  async function handleDiscard() {
    if (!documento) return;
    setDiscarding(true);
    setError(null);
    try {
      await facturacionApi.descartarDocumento(documento.id);
      toast.success(t("facturacion.upload.discardSuccess"));
      handleClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? t("facturacion.upload.error"));
    } finally {
      setDiscarding(false);
    }
  }

  const canConfirm = monto.trim() !== "" && !isNaN(parseFloat(monto)) && concepto.trim() !== "" && fecha !== "" && cuentaId !== null;
  const ex = documento?.extraccion;

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

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {step === "upload" && (
            <>
              <FileDropField
                label={t("facturacion.upload.title")}
                hint=".pdf"
                accept=".pdf"
                file={file}
                onChange={(e: ChangeEvent<HTMLInputElement>) => e.target.files?.[0] && setFile(e.target.files[0])}
                icon={FileText}
                accentColor="brand"
                chooseLabel={t("cenefas.chooseFile")}
                readyLabel={t("cenefas.ready")}
                searchLabel={t("cenefas.search")}
              />
              {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            </>
          )}

          {step === "extracting" && (
            <div className="flex flex-col items-center gap-3 py-10">
              <DogTiMascot size={72} />
              <p className="text-xs text-slate-400">{t("facturacion.upload.processing")}</p>
            </div>
          )}

          {step === "review" && documento && (
            <>
              {documento.extraction_error && (
                <div className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 rounded-lg px-3 py-2">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                  <span>{t("facturacion.upload.extractError")}</span>
                </div>
              )}

              {/* Panel de análisis -- siempre visible cuando DogTi pudo leer
                  el PDF (no solo cuando la confianza es baja), para que la
                  persona vea qué entendió antes de mirar el formulario. */}
              {!documento.extraction_error && ex && (
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

              {pdfUrl && (
                <div>
                  <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">{t("facturacion.upload.pdfPreview")}</p>
                  <iframe src={pdfUrl} className="w-full h-56 rounded-lg border border-slate-200 dark:border-slate-700" />
                </div>
              )}

              {/* Toggle Movimiento / Canje */}
              <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => setTipo("movimiento")}
                  className={`flex-1 py-2 transition-colors ${tipo === "movimiento" ? "bg-brand-600 text-white" : "bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"}`}
                >
                  {t("facturacion.upload.typeMovimiento")}
                </button>
                <button
                  type="button"
                  onClick={() => setTipo("canje")}
                  className={`flex-1 py-2 transition-colors ${tipo === "canje" ? "bg-brand-600 text-white" : "bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"}`}
                >
                  {t("facturacion.upload.typeCanje")}
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {tipo === "movimiento" && (
                  <Field label={t("facturacion.upload.fieldTipoMovimiento")}>
                    <select value={tipoMovimiento} onChange={(e) => setTipoMovimiento(e.target.value as "entrada" | "salida")} className="input text-sm">
                      <option value="salida">{t("facturacion.salida")}</option>
                      <option value="entrada">{t("facturacion.entrada")}</option>
                    </select>
                  </Field>
                )}
                {tipo === "canje" && (
                  <Field label={t("facturacion.upload.fieldEstado")}>
                    <select value={estado} onChange={(e) => setEstado(e.target.value)} className="input text-sm">
                      <option value="pendiente">{t("facturacion.estados.pendiente")}</option>
                      <option value="activo">{t("facturacion.estados.activo")}</option>
                      <option value="cerrado">{t("facturacion.estados.cerrado")}</option>
                    </select>
                  </Field>
                )}
                <Field label={t("facturacion.upload.fieldCuenta")}>
                  <select
                    value={cuentaId ?? ""}
                    onChange={(e) => setCuentaId(e.target.value ? Number(e.target.value) : null)}
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
                  <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className="input text-sm" />
                </Field>

                <Field label={t("facturacion.upload.fieldMonto")}>
                  <input type="number" step="0.01" min="0" value={monto} onChange={(e) => setMonto(e.target.value)} className="input text-sm" />
                </Field>
                <Field label={t("facturacion.upload.fieldMoneda")}>
                  <input type="text" value={moneda} onChange={(e) => setMoneda(e.target.value)} className="input text-sm" />
                </Field>

                <Field label={t("facturacion.upload.fieldProveedor")}>
                  <input type="text" value={proveedorMarca} onChange={(e) => setProveedorMarca(e.target.value)} className="input text-sm" />
                </Field>
                <Field label={t("facturacion.upload.fieldNumeroFactura")}>
                  <input type="text" value={numeroFactura} onChange={(e) => setNumeroFactura(e.target.value)} className="input text-sm" />
                </Field>

                <div className="col-span-2">
                  <Field label={t("facturacion.upload.fieldConcepto")}>
                    <input type="text" value={concepto} onChange={(e) => setConcepto(e.target.value)} className="input text-sm" />
                  </Field>
                </div>

                {tipo === "canje" && (
                  <>
                    <Field label={t("facturacion.upload.fieldVigenciaDesde")}>
                      <input type="date" value={vigenciaDesde} onChange={(e) => setVigenciaDesde(e.target.value)} className="input text-sm" />
                    </Field>
                    <Field label={t("facturacion.upload.fieldVigenciaHasta")}>
                      <input type="date" value={vigenciaHasta} onChange={(e) => setVigenciaHasta(e.target.value)} className="input text-sm" />
                    </Field>
                  </>
                )}
              </div>

              {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            </>
          )}
        </div>

        {step === "upload" && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={handleUpload}
              disabled={!file}
              className="btn-primary w-full text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              <Upload size={13} /> {t("facturacion.upload.analyze")}
            </button>
          </div>
        )}

        {step === "review" && (
          <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 flex gap-2">
            <button
              onClick={handleDiscard}
              disabled={confirming || discarding}
              className="btn-ghost flex-1 text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              {discarding ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              {discarding ? t("facturacion.upload.discarding") : t("facturacion.upload.discard")}
            </button>
            <button
              onClick={handleConfirm}
              disabled={confirming || discarding || !canConfirm}
              className="btn-primary flex-1 text-xs flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              {confirming && <Loader2 size={13} className="animate-spin" />}
              {confirming ? t("facturacion.upload.confirming") : t("facturacion.upload.confirm")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
