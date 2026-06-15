"use client";
import { useEffect, useRef, useState } from "react";
import {
  Upload, ChevronLeft, ChevronRight, FileSpreadsheet,
  CheckCircle2, AlertCircle, Loader2, Download, RefreshCw,
  Trash2, Pencil, Check, X,
} from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaFormat, CenefaJob, CenefaTemplateRecord } from "@/types/cenefas";

type Step     = 1 | 2 | 3;
type TmplMode = "v2" | "builtin";

const BUILTINS = [
  { slug: "a4",        label: "Cenefa A4",      formats: ["a4"] },
  { slug: "pinchos",   label: "Pinchos",         formats: ["pinchos"] },
  { slug: "black",     label: "Cenefas 3xA4",    formats: ["3xa4"] },
];

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export default function GenerarPage() {
  const [step, setStep] = useState<Step>(1);

  // Configuración
  const [tmplMode,    setTmplMode]    = useState<TmplMode>("v2");
  const [templates,   setTemplates]   = useState<CenefaTemplateRecord[]>([]);
  const [formats,     setFormats]     = useState<CenefaFormat[]>([]);
  const [templateId,  setTemplateId]  = useState("");
  const [builtinSlug, setBuiltinSlug] = useState("a4");
  const [excel,       setExcel]       = useState<File | null>(null);
  const [formatId,    setFormatId]    = useState("a4");
  const [vigencia,    setVigencia]    = useState("");
  const [aclaracion,  setAclaracion]  = useState("Bases y condiciones en redexpres.uy");
  const [otraAlcohol, setOtraAlcohol] = useState(
    "Prohibida la venta de bebidas alcohólicas a menores de 18 años"
  );
  const [banco, setBanco] = useState("");

  // Validación
  const [validating,        setValidating]        = useState(false);
  const [showMissingModal,  setShowMissingModal]  = useState(false);
  const [validation,  setValidation]  = useState<{
    total_rows: number;
    missing_required: string[];
    rule_summary: { rule_id: string; hits: number; pct: number }[];
    status: string;
  } | null>(null);

  // Job
  const [job,     setJob]     = useState<CenefaJob | null>(null);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dlRef   = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const paramId = params.get("template_id");

    Promise.all([
      cenefasV2Api.listTemplates(),
      cenefasV2Api.getFormats(),
    ]).then(([tmplRes, fmtRes]) => {
      setTemplates(tmplRes.data);
      setFormats(fmtRes.data);

      if (paramId) {
        setTemplateId(paramId);
        setTmplMode("v2");
        // Pre-seleccionar el formato del template
        const tmpl = tmplRes.data.find((t: any) => t.id === paramId);
        if (tmpl?.formats?.[0]) setFormatId(tmpl.formats[0]);
      }
    }).catch(() => {});
  }, []);

  // Polling del job
  useEffect(() => {
    if (polling && job?.id) {
      pollRef.current = setInterval(async () => {
        try {
          const { data } = await cenefasV2Api.getJob(job.id);
          setJob(data);
          if (data.status === "done" || data.status === "error") {
            setPolling(false);
            clearInterval(pollRef.current!);
          }
        } catch { /* ignore */ }
      }, 2000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [polling, job?.id]);

  // ── Step 1 → 2: validar (solo para v2 templates)
  async function handleNext() {
    if (!excel) { toast.error("Cargá el archivo Excel"); return; }

    if (tmplMode === "builtin") {
      // Los templates predeterminados no tienen reglas/variables — saltar validación
      await handleStartJob(true);
      return;
    }

    if (!templateId) { toast.error("Seleccioná un template v2"); return; }

    setValidating(true);
    try {
      const fd = new FormData();
      fd.append("excel",       excel);
      fd.append("template_id", templateId);
      fd.append("vigencia",    vigencia);
      fd.append("aclaracion",  aclaracion);
      fd.append("otra_alcohol", otraAlcohol);
      fd.append("banco",       banco);
      const { data } = await cenefasV2Api.validateCsv(fd);
      setValidation(data);
      setStep(2);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Error al validar");
    } finally {
      setValidating(false);
    }
  }

  // ── Crear job (llamado desde step 2 o directo para builtins)
  async function handleStartJob(direct = false) {
    if (!excel) return;
    try {
      const fd = new FormData();
      fd.append("excel",       excel);
      fd.append("format_id",   formatId);
      fd.append("vigencia",    vigencia);
      fd.append("aclaracion",  aclaracion);
      fd.append("otra_alcohol", otraAlcohol);
      fd.append("banco",       banco);

      if (tmplMode === "v2") {
        fd.append("template_v2_id", templateId);
      } else {
        fd.append("builtin_slug", builtinSlug);
      }

      const { data } = await cenefasV2Api.createJob(fd);
      setJob({
        id: data.job_id, status: "pending",
        format: data.format, export_type: "pptx",
        error_count: 0, created_at: new Date().toISOString(),
      });
      setPolling(true);
      setStep(3);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Error al iniciar la generación");
    }
  }

  async function handleDownload() {
    if (!job) return;
    try {
      const { data } = await cenefasV2Api.downloadJob(job.id);
      const url = URL.createObjectURL(new Blob([data]));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = `cenefas_${formatId}.pptx`;
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Error al descargar");
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <a href="/herramientas/cenefas/v2"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
          <ChevronLeft size={18} />
        </a>
        <div>
          <h1 className="text-xl font-bold text-slate-800">Generar cenefas</h1>
          <p className="text-sm text-slate-500">Motor v2 — componentes inteligentes</p>
        </div>
      </div>

      <Stepper current={step} />

      {/* ── STEP 1: Configuración ── */}
      {step === 1 && (
        <div className="card p-6 space-y-5">

          {/* Modo template */}
          <div>
            <SectionLabel>Tipo de plantilla</SectionLabel>
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => setTmplMode("v2")}
                className={`flex-1 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                  tmplMode === "v2"
                    ? "border-brand-500 bg-brand-50 text-brand-700"
                    : "border-slate-200 text-slate-500 hover:border-slate-300"
                }`}
              >
                Template del editor ✦
              </button>
              <button
                onClick={() => setTmplMode("builtin")}
                className={`flex-1 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                  tmplMode === "builtin"
                    ? "border-slate-400 bg-slate-50 text-slate-700"
                    : "border-slate-200 text-slate-400 hover:border-slate-300"
                }`}
              >
                Plantilla clásica
              </button>
            </div>
            {tmplMode === "builtin" && (
              <p className="text-[11px] text-slate-400 mt-1.5">
                Usa el motor original (PPTX fijo). Para más personalización, usá el Editor de plantillas.
              </p>
            )}
          </div>

          {/* Selector según modo */}
          {tmplMode === "v2" ? (
            <div>
              <SectionLabel>Template v2</SectionLabel>
              <TemplateList
                templates={templates}
                selectedId={templateId}
                onSelect={setTemplateId}
                onRenamed={(id, name) =>
                  setTemplates((prev) => prev.map((t) => t.id === id ? { ...t, name } : t))
                }
                onDeleted={(id) => {
                  setTemplates((prev) => prev.filter((t) => t.id !== id));
                  if (templateId === id) setTemplateId("");
                }}
              />
            </div>
          ) : (
            <div>
              <SectionLabel>Plantilla predeterminada</SectionLabel>
              <div className="grid grid-cols-3 gap-2 mt-2">
                {BUILTINS.map((b) => (
                  <button
                    key={b.slug}
                    onClick={() => { setBuiltinSlug(b.slug); setFormatId(b.formats[0]); }}
                    className={`p-3 rounded-xl border text-center transition-all ${
                      builtinSlug === b.slug
                        ? "border-brand-500 bg-brand-50 text-brand-700"
                        : "border-slate-200 text-slate-600 hover:border-brand-300"
                    }`}
                  >
                    <p className="text-sm font-semibold">{b.label}</p>
                    <p className="text-[10px] text-slate-400">{b.formats.join(", ")}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Excel */}
          <div>
            <SectionLabel>Archivo Excel</SectionLabel>
            <label className="flex flex-col items-center gap-2 border-2 border-dashed border-slate-200 rounded-xl p-5 cursor-pointer hover:border-brand-400 transition-colors mt-1">
              <FileSpreadsheet size={26} className={excel ? "text-emerald-500" : "text-slate-300"} />
              <p className="text-sm font-medium text-slate-600">
                {excel ? excel.name : "Cargá el Excel de productos"}
              </p>
              <p className="text-xs text-slate-400">.xlsx o .xlsm</p>
              <input type="file" accept=".xlsx,.xlsm" className="hidden"
                onChange={(e) => setExcel(e.target.files?.[0] ?? null)} />
            </label>
          </div>

          {/* Formato de salida */}
          <div>
            <SectionLabel>Formato de salida</SectionLabel>
            <div className="grid grid-cols-4 gap-2 mt-2">
              {formats.map((f) => (
                <button key={f.id} onClick={() => setFormatId(f.id)}
                  className={`p-3 rounded-xl border text-center transition-all ${
                    formatId === f.id
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-slate-200 text-slate-600 hover:border-brand-300"
                  }`}
                >
                  <p className="text-sm font-semibold">{f.label}</p>
                  <p className="text-[10px] text-slate-400">{f.width_cm}×{f.height_cm}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Metadata */}
          <div>
            <SectionLabel>Metadata (opcional)</SectionLabel>
            <div className="grid grid-cols-2 gap-3 mt-2">
              <Field label="Vigencia"    value={vigencia}    onChange={setVigencia} />
              <Field label="Banco"       value={banco}       onChange={setBanco} />
              <div className="col-span-2">
                <Field label="Aclaración" value={aclaracion} onChange={setAclaracion} />
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button onClick={handleNext} disabled={validating || !excel || (tmplMode === "v2" && !templateId)}
              className="btn-primary flex items-center gap-2 px-5 py-2.5 disabled:opacity-50">
              {validating ? <Loader2 size={15} className="animate-spin" /> : <ChevronRight size={15} />}
              {tmplMode === "builtin" ? "Generar" : "Siguiente — Validar"}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Validación (solo para v2) ── */}
      {step === 2 && validation && (
        <div className="card p-6 space-y-5">
          <div className="grid grid-cols-3 gap-4">
            <StatBox label="Filas"          value={validation.total_rows}            color="text-slate-700" />
            <StatBox label="Vars faltantes" value={validation.missing_required.length} color="text-rose-600" />
            <StatBox label="Reglas activas" value={validation.rule_summary.filter((r) => r.hits > 0).length} color="text-brand-600" />
          </div>

          {validation.missing_required.length > 0 && (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-rose-700 flex items-center gap-2 mb-2">
                <AlertCircle size={15} /> Variables requeridas faltantes
              </p>
              {validation.missing_required.map((v) => (
                <p key={v} className="text-xs text-rose-600 font-mono">• {v}</p>
              ))}
            </div>
          )}

          {validation.rule_summary.length > 0 && (
            <div>
              <SectionLabel>Resumen de reglas</SectionLabel>
              <div className="space-y-1.5 mt-2">
                {validation.rule_summary.map((r) => (
                  <div key={r.rule_id} className="flex items-center gap-3 text-xs">
                    <span className="text-slate-600 truncate flex-1 font-medium">
                      {(r as any).rule_name || r.rule_id}
                    </span>
                    <div className="w-24 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                      <div className="h-full bg-brand-400 rounded-full" style={{ width: `${r.pct}%` }} />
                    </div>
                    <span className="text-slate-400 w-10 text-right">{r.pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {validation.status === "ok" && (
            <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
              <CheckCircle2 size={16} /> El CSV está listo para generar
            </div>
          )}

          <div className="flex justify-between pt-2">
            <button onClick={() => setStep(1)} className="btn-secondary flex items-center gap-2 px-4 py-2">
              <ChevronLeft size={15} /> Volver
            </button>
            <button
              onClick={() => {
                if (validation.missing_required.length > 0) setShowMissingModal(true);
                else handleStartJob();
              }}
              className="btn-primary flex items-center gap-2 px-5 py-2.5">
              <ChevronRight size={15} /> Generar cenefas
            </button>
          </div>

          {/* Modal de variables faltantes */}
          {showMissingModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
              <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-sm w-full mx-4 space-y-4">
                <div className="flex items-center gap-2 text-amber-600">
                  <AlertCircle size={20} />
                  <p className="font-semibold text-base">Variables no encontradas</p>
                </div>
                <p className="text-sm text-slate-600">
                  Las siguientes columnas no se encontraron en tu Excel:
                </p>
                <div className="bg-rose-50 border border-rose-200 rounded-xl p-3">
                  {validation.missing_required.map((v) => (
                    <p key={v} className="text-xs text-rose-600 font-mono">• {v}</p>
                  ))}
                </div>
                <p className="text-sm text-slate-500">
                  Solo se rellenarán las variables disponibles. ¿Querés continuar igual?
                </p>
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setShowMissingModal(false)}
                    className="flex-1 btn-secondary py-2 text-sm">
                    Cancelar
                  </button>
                  <button onClick={() => { setShowMissingModal(false); handleStartJob(); }}
                    className="flex-1 btn-primary py-2 text-sm">
                    Continuar igual
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── STEP 3: Exportación ── */}
      {step === 3 && job && (
        <div className="card p-6 space-y-6 text-center">
          {job.status === "pending" || job.status === "running" ? (
            <>
              <Loader2 size={40} className="animate-spin text-brand-500 mx-auto" />
              <div>
                <p className="text-base font-semibold text-slate-700">Generando cenefas…</p>
                <p className="text-sm text-slate-400 mt-1 capitalize">{job.status}</p>
              </div>
            </>
          ) : job.status === "done" ? (
            <>
              <CheckCircle2 size={40} className="text-emerald-500 mx-auto" />
              <div>
                <p className="text-base font-semibold text-slate-700">¡Listo!</p>
                {job.row_count && (
                  <p className="text-sm text-slate-400 mt-1">
                    {job.row_count} productos generados • {job.error_count} errores de datos
                  </p>
                )}
              </div>
              <div className="flex justify-center gap-3">
                <button onClick={handleDownload}
                  className="btn-primary flex items-center gap-2 px-6 py-2.5">
                  <Download size={15} /> Descargar PPTX
                </button>
                <button onClick={() => { setStep(1); setJob(null); setValidation(null); }}
                  className="btn-secondary flex items-center gap-2 px-4 py-2.5">
                  <RefreshCw size={14} /> Nueva generación
                </button>
              </div>
            </>
          ) : (
            <>
              <AlertCircle size={40} className="text-rose-500 mx-auto" />
              <p className="text-base font-semibold text-slate-700">Error en la generación</p>
              <p className="text-sm text-rose-500">
                {(job as any).validation_report?.error ?? "Error desconocido"}
              </p>
              <button onClick={() => setStep(1)} className="btn-secondary flex items-center gap-2 px-4 py-2 mx-auto">
                <ChevronLeft size={14} /> Volver al inicio
              </button>
            </>
          )}
        </div>
      )}

      <a ref={dlRef} className="hidden" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function Stepper({ current }: { current: Step }) {
  const steps = [
    { n: 1 as Step, label: "Configuración" },
    { n: 2 as Step, label: "Validación" },
    { n: 3 as Step, label: "Exportación" },
  ];
  return (
    <div className="flex items-center">
      {steps.map(({ n, label }, i) => (
        <div key={n} className="flex items-center flex-1">
          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
              n < current ? "bg-emerald-500 text-white"
              : n === current ? "bg-brand-600 text-white"
              : "bg-slate-100 text-slate-400"
            }`}>
              {n < current ? <CheckCircle2 size={14} /> : n}
            </div>
            <span className={`text-xs font-medium ${n === current ? "text-brand-600" : "text-slate-400"}`}>
              {label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`flex-1 h-px mx-3 ${n < current ? "bg-emerald-300" : "bg-slate-200"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{children}</p>;
}

function TemplateList({
  templates, selectedId, onSelect, onRenamed, onDeleted,
}: {
  templates:  CenefaTemplateRecord[];
  selectedId: string;
  onSelect:   (id: string) => void;
  onRenamed:  (id: string, name: string) => void;
  onDeleted:  (id: string) => void;
}) {
  const [editingId,   setEditingId]   = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [deletingId,  setDeletingId]  = useState<string | null>(null);

  async function handleRename(id: string) {
    if (!editingName.trim()) return;
    try {
      await cenefasV2Api.renameTemplate(id, editingName.trim());
      onRenamed(id, editingName.trim());
      toast.success("Nombre actualizado");
    } catch {
      toast.error("Error al renombrar");
    } finally {
      setEditingId(null);
    }
  }

  async function handleDelete(id: string) {
    try {
      await cenefasV2Api.deleteTemplate(id);
      onDeleted(id);
      toast.success("Template eliminado");
    } catch {
      toast.error("Error al eliminar");
    } finally {
      setDeletingId(null);
    }
  }

  if (templates.length === 0) {
    return (
      <p className="text-xs text-amber-600 flex items-center gap-1.5 mt-1.5">
        <AlertCircle size={13} />
        No hay templates v2.{" "}
        <a href="/herramientas/cenefas/v2" className="underline">Creá uno en el editor</a>.
      </p>
    );
  }

  return (
    <div className="mt-1 space-y-1">
      {templates.map((t) => {
        const isSelected = selectedId === t.id;
        const isEditing  = editingId === t.id;
        const isDeleting = deletingId === t.id;

        return (
          <div
            key={t.id}
            onClick={() => !isEditing && onSelect(t.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl border cursor-pointer transition-all group ${
              isSelected
                ? "border-brand-500 bg-brand-50"
                : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
            }`}
          >
            {isEditing ? (
              <>
                <input
                  autoFocus
                  className="flex-1 text-sm bg-transparent outline-none border-b border-brand-400"
                  value={editingName}
                  onChange={(e) => setEditingName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleRename(t.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
                <button onClick={(e) => { e.stopPropagation(); handleRename(t.id); }}
                  className="text-emerald-600 hover:text-emerald-700">
                  <Check size={14} />
                </button>
                <button onClick={(e) => { e.stopPropagation(); setEditingId(null); }}
                  className="text-slate-400 hover:text-slate-600">
                  <X size={14} />
                </button>
              </>
            ) : isDeleting ? (
              <>
                <span className="flex-1 text-sm text-rose-600">¿Eliminar "{t.name}"?</span>
                <button onClick={(e) => { e.stopPropagation(); handleDelete(t.id); }}
                  className="text-xs font-semibold text-rose-600 hover:text-rose-800 px-2 py-0.5 rounded bg-rose-50 hover:bg-rose-100">
                  Sí, borrar
                </button>
                <button onClick={(e) => { e.stopPropagation(); setDeletingId(null); }}
                  className="text-xs text-slate-500 hover:text-slate-700">
                  Cancelar
                </button>
              </>
            ) : (
              <>
                <span className={`flex-1 text-sm truncate ${isSelected ? "text-brand-700 font-medium" : "text-slate-700"}`}>
                  {t.name}
                </span>
                <span className="text-[10px] text-slate-400 shrink-0">{t.formats?.join(", ")}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); setEditingId(t.id); setEditingName(t.name); setDeletingId(null); }}
                  className="p-1 text-slate-300 hover:text-brand-500 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Renombrar"
                >
                  <Pencil size={12} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeletingId(t.id); setEditingId(null); }}
                  className="p-1 text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Eliminar"
                >
                  <Trash2 size={12} />
                </button>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-500">{label}</span>
      <input className="input text-sm" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function StatBox({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-slate-50 rounded-xl p-4 text-center">
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      <p className="text-xs text-slate-400 mt-1">{label}</p>
    </div>
  );
}
