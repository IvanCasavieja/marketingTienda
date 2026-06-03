"use client";
import { useEffect, useRef, useState } from "react";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaJob } from "@/types/cenefas";
import {
  ChevronLeft, Download, Loader2, CheckCircle2,
  AlertCircle, Clock, RefreshCw,
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

export default function JobsPage() {
  const [jobs,     setJobs]     = useState<CenefaJob[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dlRef   = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    loadJobs();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // Polling para jobs activos
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

  function fDate(iso: string) {
    try { return format(parseISO(iso), "dd MMM yyyy HH:mm", { locale: es }); }
    catch { return iso; }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
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
                {["Fecha", "Formato", "Estado", "Filas", "Errores", ""].map((h) => (
                  <th key={h} className="table-th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const st  = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.error;
                const active = job.status === "pending" || job.status === "running";
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
                      {job.error_count > 0
                        ? <span className="text-amber-500 font-medium">{job.error_count}</span>
                        : <span className="text-slate-400">0</span>
                      }
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
