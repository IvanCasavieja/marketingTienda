"use client";
import { useEffect, useRef, useState } from "react";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaJob, CenefaJobIssue } from "@/types/cenefas";
import {
  ChevronLeft, Download, Loader2, CheckCircle2,
  AlertCircle, Clock, RefreshCw, X, AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { es } from "date-fns/locale";

const STATUS_CONFIG = {
  pending: { label: "En espera",   color: "text-slate-400",   bg: "bg-slate-100",   icon: <Clock      size={12} /> },
  running: { label: "Generando…",  color: "text-blue-600",    bg: "bg-blue-50",     icon: <Loader2    size={12} className="animate-spin" /> },
  done:    { label: "Listo",       color: "text-emerald-600", bg: "bg-emerald-50",  icon: <CheckCircle2 size={12} /> },
  error:   { label: "Error",       color: "text-red-600",     bg: "bg-red-50",      icon: <AlertCircle size={12} /> },
};

const FORMAT_LABELS: Record<string, string> = {
  a4:      "A4",
  a3:      "A3",
  "3xa4":  "3×A4",
  pinchos: "Pinchos",
};

const ISSUE_TYPE_LABELS: Record<string, string> = {
  missing_price:       "Precio faltante",
  invalid_price:       "Precio inválido",
  empty_description:   "Descripción vacía",
  description_too_long:"Descripción muy larga",
  description_long:    "Descripción larga",
  combo_missing_price: "Combo sin precio",
  pbanco_without_banco:"Precio banco sin banco",
};

export default function JobsPage() {
  const [jobs,     setJobs]     = useState<CenefaJob[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [detailJob,   setDetailJob]   = useState<CenefaJob | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dlRef   = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    loadJobs();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  useEffect(() => {
    const active = jobs.some((j) => j.status === "pending" || j.status === "running");
    if (active && !pollRef.current) {
      pollRef.current = setInterval(loadJobs, 3000);
    } else if (!active && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [jobs]);

  async function loadJobs() {
    try {
      const { data } = await cenefasV2Api.listJobs();
      setJobs(data);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload(job: CenefaJob) {
    setDownloading(job.id);
    try {
      const { data } = await cenefasV2Api.downloadJob(job.id);
      const url = URL.createObjectURL(new Blob([data]));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = `cenefas_${job.format}_${job.id.slice(0, 8)}.pptx`;
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
    } catch {
      toast.error("El archivo ya no está disponible (expira a las 24 h)");
    } finally {
      setDownloading(null);
    }
  }

  async function handleOpenDetail(job: CenefaJob) {
    // Si ya tenemos los errores cargados, mostramos directo
    if (job.errors !== undefined || job.warnings !== undefined) {
      setDetailJob(job);
      return;
    }
    setLoadingDetail(true);
    try {
      const { data } = await cenefasV2Api.getJob(job.id);
      // Actualizar en la lista local para no re-fetchear
      setJobs((prev) => prev.map((j) => j.id === data.id ? { ...j, ...data } : j));
      setDetailJob({ ...job, ...data });
    } catch {
      toast.error("No se pudo cargar el detalle");
    } finally {
      setLoadingDetail(false);
    }
  }

  function fDate(iso: string) {
    try { return format(parseISO(iso), "dd MMM yyyy HH:mm", { locale: es }); }
    catch { return iso; }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">

      {/* Modal de detalle de errores */}
      {detailJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div>
                <p className="font-semibold text-slate-800 text-sm">
                  Detalle de issues · {fDate(detailJob.created_at)}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {FORMAT_LABELS[detailJob.format] ?? detailJob.format.toUpperCase()} · {detailJob.row_count} filas
                </p>
              </div>
              <button onClick={() => setDetailJob(null)} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100">
                <X size={16} />
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-5 space-y-4">
              {/* Errores */}
              {detailJob.errors && detailJob.errors.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertCircle size={13} className="text-rose-500" />
                    <p className="text-xs font-semibold text-rose-600 uppercase tracking-wider">
                      Errores ({detailJob.errors.length})
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    {detailJob.errors.map((e, i) => (
                      <IssueRow key={i} issue={e} variant="error" />
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {detailJob.warnings && detailJob.warnings.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle size={13} className="text-amber-500" />
                    <p className="text-xs font-semibold text-amber-600 uppercase tracking-wider">
                      Advertencias ({detailJob.warnings.length})
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    {detailJob.warnings.map((w, i) => (
                      <IssueRow key={i} issue={w} variant="warning" />
                    ))}
                  </div>
                </div>
              )}

              {/* Sin issues con detalle */}
              {(!detailJob.errors || detailJob.errors.length === 0) &&
               (!detailJob.warnings || detailJob.warnings.length === 0) && (
                <p className="text-sm text-slate-400 text-center py-8">
                  No hay detalle de errores disponible para esta generación.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <a href="/herramientas/cenefas/v2/generar"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
          <ChevronLeft size={18} />
        </a>
        <div>
          <h1 className="text-xl font-bold text-slate-800">Historial de generaciones</h1>
          <p className="text-sm text-slate-500">Últimos 20 trabajos de tu equipo · Los archivos expiran a las 24 h</p>
        </div>
        <button onClick={loadJobs}
          className="ml-auto p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          title="Actualizar">
          <RefreshCw size={15} />
        </button>
      </div>

      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={22} className="animate-spin text-slate-300" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="py-16 text-center">
            <Clock size={28} className="mx-auto text-slate-300 mb-3" />
            <p className="text-sm font-medium text-slate-500">Sin generaciones aún</p>
            <p className="text-xs text-slate-400 mt-1">
              Cuando generes cenefas desde el editor, aparecerán acá.
            </p>
            <a href="/herramientas/cenefas/v2/generar"
              className="inline-flex items-center gap-1.5 mt-4 text-xs text-brand-600 hover:text-brand-700 font-medium">
              Generar ahora →
            </a>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100">
                {["Fecha", "Formato", "Estado", "Filas", "Issues", ""].map((h) => (
                  <th key={h} className="table-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const st     = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.error;
                const active = job.status === "pending" || job.status === "running";
                const hasIssues = job.error_count > 0;
                return (
                  <tr key={job.id} className="table-tr">
                    <td className="table-td text-xs text-slate-500">
                      {fDate(job.created_at)}
                    </td>
                    <td className="table-td">
                      <span className="text-xs font-semibold text-slate-700">
                        {FORMAT_LABELS[job.format] ?? job.format.toUpperCase()}
                      </span>
                    </td>
                    <td className="table-td">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${st.bg} ${st.color}`}>
                        {st.icon} {st.label}
                      </span>
                    </td>
                    <td className="table-td text-sm text-slate-600">
                      {job.row_count ?? (active ? "—" : "—")}
                    </td>
                    <td className="table-td text-sm">
                      {hasIssues ? (
                        <button
                          onClick={() => handleOpenDetail(job)}
                          disabled={loadingDetail}
                          className="inline-flex items-center gap-1 text-amber-500 font-semibold hover:text-amber-600 hover:underline transition-colors disabled:opacity-50"
                          title="Ver detalle de errores"
                        >
                          {loadingDetail ? <Loader2 size={11} className="animate-spin" /> : <AlertCircle size={11} />}
                          {job.error_count}
                        </button>
                      ) : (
                        <span className="text-slate-400">0</span>
                      )}
                    </td>
                    <td className="table-td text-right">
                      {job.status === "done" && (
                        <button
                          onClick={() => handleDownload(job)}
                          disabled={downloading === job.id}
                          className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50"
                        >
                          {downloading === job.id
                            ? <Loader2 size={12} className="animate-spin" />
                            : <Download size={12} />
                          }
                          Descargar
                        </button>
                      )}
                      {active && (
                        <span className="text-xs text-slate-400">procesando…</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <a ref={dlRef} className="hidden" />
    </div>
  );
}

function IssueRow({ issue, variant }: { issue: CenefaJobIssue; variant: "error" | "warning" }) {
  const isError = variant === "error";
  return (
    <div className={`flex items-start gap-3 px-3 py-2.5 rounded-xl border text-xs ${
      isError
        ? "bg-rose-50 border-rose-100"
        : "bg-amber-50 border-amber-100"
    }`}>
      <span className={`font-semibold shrink-0 ${isError ? "text-rose-500" : "text-amber-500"}`}>
        F{issue.row}
      </span>
      <span className={`shrink-0 font-medium ${isError ? "text-rose-700" : "text-amber-700"}`}>
        {ISSUE_TYPE_LABELS[issue.type] ?? issue.type}
      </span>
      <span className="text-slate-500 truncate flex-1" title={issue.detail}>
        {issue.product !== `Fila ${issue.row}` && (
          <span className="font-medium text-slate-600 mr-1">{issue.product} ·</span>
        )}
        {issue.detail}
      </span>
    </div>
  );
}
