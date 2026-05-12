"use client";
import { useState, useEffect } from "react";
import { analyticsApi } from "@/lib/api";
import { Analysis, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import { Brain, Loader2, Sparkles, Clock, ChevronRight, BarChart3, AlertTriangle, TrendingUp, Globe } from "lucide-react";
import { toast } from "sonner";
import { SkeletonText } from "@/components/ui/SkeletonCard";

const ANALYSIS_TYPES = [
  {
    value: "full_report",
    label: "Reporte completo",
    desc: "Resumen ejecutivo de todos los canales",
    icon: BarChart3,
    color: "text-brand-600 bg-brand-50",
  },
  {
    value: "anomaly_detection",
    label: "Detección de anomalías",
    desc: "Alertas y problemas críticos",
    icon: AlertTriangle,
    color: "text-amber-600 bg-amber-50",
  },
  {
    value: "optimization",
    label: "Optimización",
    desc: "Recomendaciones accionables",
    icon: TrendingUp,
    color: "text-emerald-600 bg-emerald-50",
  },
  {
    value: "cross_platform",
    label: "Comparativa cross-channel",
    desc: "Ranking de eficiencia por plataforma",
    icon: Globe,
    color: "text-purple-600 bg-purple-50",
  },
];

const ALL_PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"];

function MarkdownOutput({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="prose-analysis space-y-0.5">
      {lines.map((line, i) => {
        if (line.startsWith("## ")) return <h2 key={i}>{line.replace("## ", "")}</h2>;
        if (line.startsWith("### ")) return <h3 key={i}>{line.replace("### ", "")}</h3>;
        if (line.startsWith("**") && line.endsWith("**")) return <p key={i} className="font-semibold text-slate-800 text-sm">{line.replace(/\*\*/g, "")}</p>;
        if (line.startsWith("- ") || line.startsWith("• ")) {
          const content = line.replace(/^[-•] /, "").replace(/\*\*(.*?)\*\*/g, "$1");
          return <li key={i}>{content}</li>;
        }
        if (line.trim() === "") return <div key={i} className="h-1" />;
        const rendered = line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
        return <p key={i} dangerouslySetInnerHTML={{ __html: rendered }} />;
      })}
    </div>
  );
}

export default function AnalyticsPage() {
  const [platforms, setPlatforms]     = useState<string[]>(ALL_PLATFORMS);
  const [analysisType, setType]       = useState("full_report");
  const [dateFrom, setDateFrom]       = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [dateTo, setDateTo]           = useState(format(new Date(), "yyyy-MM-dd"));
  const [result, setResult]           = useState<string>("");
  const [loading, setLoading]         = useState(false);
  const [history, setHistory]         = useState<Analysis[]>([]);
  const [activeAnalysis, setActive]   = useState<number | null>(null);

  useEffect(() => {
    analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
  }, []);

  async function runAnalysis() {
    if (!platforms.length) return toast.error("Seleccioná al menos una plataforma");
    setLoading(true);
    setResult("");
    setActive(null);
    try {
      const { data } = await analyticsApi.analyze(platforms, dateFrom, dateTo, analysisType);
      setResult(data.result);
      setActive(data.id);
      toast.success("Análisis generado por Claude");
      analyticsApi.getHistory().then(({ data }) => setHistory(data)).catch(() => {});
    } catch {
      toast.error("Error al generar análisis");
    } finally {
      setLoading(false);
    }
  }

  async function loadFromHistory(id: number) {
    setActive(id);
    try {
      const { data } = await analyticsApi.getAnalysis(id);
      setResult(data.result);
    } catch { toast.error("Error cargando análisis"); }
  }

  const selectedType = ANALYSIS_TYPES.find((t) => t.value === analysisType);

  return (
    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Análisis con IA</h1>
        <p className="text-sm text-slate-500 mt-0.5">Claude analiza tus campañas y genera insights accionables</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-5">
        {/* ── Config panel ── */}
        <div className="space-y-4">
          {/* Analysis type */}
          <div className="card p-5">
            <p className="section-title mb-3">Tipo de análisis</p>
            <div className="space-y-2">
              {ANALYSIS_TYPES.map(({ value, label, desc, icon: Icon, color }) => (
                <button key={value} onClick={() => setType(value)}
                  className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 text-left transition-all duration-150 ${
                    analysisType === value
                      ? "border-brand-500 bg-brand-50/50"
                      : "border-transparent bg-slate-50 hover:bg-slate-100"
                  }`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
                    <Icon size={15} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{label}</p>
                    <p className="text-xs text-slate-500">{desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Platforms */}
          <div className="card p-5">
            <p className="section-title mb-3">Plataformas</p>
            <div className="space-y-2">
              {ALL_PLATFORMS.map((p) => (
                <label key={p} className="flex items-center gap-3 cursor-pointer group">
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                    platforms.includes(p) ? "bg-brand-600 border-brand-600" : "border-slate-300 group-hover:border-brand-400"
                  }`}
                    onClick={() => setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])}>
                    {platforms.includes(p) && <svg viewBox="0 0 10 8" className="w-2.5 h-2.5" fill="none"><path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </div>
                  <span className="text-sm text-slate-700">{PLATFORM_LABELS[p]}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Date range */}
          <div className="card p-5">
            <p className="section-title mb-3">Período</p>
            <div className="space-y-2.5">
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Desde</label>
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-1 block">Hasta</label>
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input text-sm" />
              </div>
            </div>
          </div>

          <button onClick={runAnalysis} disabled={loading || !platforms.length} className="btn-primary w-full py-3">
            {loading
              ? <><Loader2 size={16} className="animate-spin" /> Analizando con Claude...</>
              : <><Sparkles size={16} /> Generar análisis</>}
          </button>
        </div>

        {/* ── Result panel ── */}
        <div className="space-y-4">
          {/* Main result */}
          <div className="card p-6 min-h-[400px]">
            {loading ? (
              <div className="space-y-6">
                <div className="flex items-center gap-2 text-brand-600">
                  <Brain size={20} className="animate-pulse-slow" />
                  <span className="text-sm font-semibold">Claude está analizando tus campañas...</span>
                </div>
                {[5, 4, 6, 3, 5].map((lines, i) => (
                  <div key={i}>
                    <div className="skeleton h-3 w-32 rounded mb-3" />
                    <SkeletonText lines={lines} />
                  </div>
                ))}
              </div>
            ) : result ? (
              <>
                <div className="flex items-center gap-2 mb-5 pb-4 border-b border-slate-50">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${selectedType?.color}`}>
                    {selectedType && <selectedType.icon size={16} />}
                  </div>
                  <div>
                    <p className="font-semibold text-slate-800 text-sm">{selectedType?.label}</p>
                    <p className="text-xs text-slate-400">Generado por Claude · {format(new Date(), "dd/MM/yyyy HH:mm")}</p>
                  </div>
                </div>
                <MarkdownOutput text={result} />
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-center">
                <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                  <Brain size={28} className="text-slate-300" />
                </div>
                <p className="text-sm font-medium text-slate-500">Configurá y ejecutá un análisis</p>
                <p className="text-xs text-slate-400 mt-1">Claude generará insights sobre tus campañas</p>
              </div>
            )}
          </div>

          {/* History */}
          {history.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-5 py-3.5 border-b border-slate-50 flex items-center gap-2">
                <Clock size={14} className="text-slate-400" />
                <p className="text-sm font-semibold text-slate-700">Análisis recientes</p>
              </div>
              <div className="divide-y divide-slate-50">
                {history.slice(0, 6).map((h) => {
                  const t = ANALYSIS_TYPES.find((x) => x.value === h.analysis_type);
                  return (
                    <button key={h.id} onClick={() => loadFromHistory(h.id)}
                      className={`w-full flex items-center gap-3 px-5 py-3 hover:bg-slate-50 transition-colors text-left ${activeAnalysis === h.id ? "bg-brand-50/50" : ""}`}>
                      {t && (
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${t.color}`}>
                          <t.icon size={13} />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-slate-700">{t?.label}</p>
                        <p className="text-[11px] text-slate-400">{format(new Date(h.created_at), "dd/MM HH:mm")}</p>
                      </div>
                      <ChevronRight size={14} className="text-slate-300 shrink-0" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
