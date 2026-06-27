"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Upload, ChevronLeft, ChevronRight, ChevronDown, FileSpreadsheet,
  CheckCircle2, AlertCircle, Loader2, Download, RefreshCw,
  Trash2, Pencil, Check, X, BookOpen, ImageIcon,
} from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaFormat, CenefaJob, CenefaTemplate, CenefaTemplateRecord } from "@/types/cenefas";

type Step     = 1 | 2 | 3;
type TmplMode = "v2" | "builtin";

const VARIABLES_REFERENCE = [
  { name: "descripcion",       desc: "Nombre del producto" },
  { name: "precioActual",      desc: "Precio de venta actual" },
  { name: "precioAnterior",    desc: "Precio anterior o tachado" },
  { name: "precioBanco",       desc: "Precio con beneficio bancario" },
  { name: "banco",             desc: "Nombre del banco o beneficio" },
  { name: "mecanica",          desc: "Mecánica o tipo de oferta (ej: 2x1, Combo, Precio Final)" },
  { name: "aclaracion",        desc: "Texto aclaratorio (ej: bases y condiciones)" },
  { name: "segundaAclaracion", desc: "Segunda aclaración o leyenda de alcohol" },
  { name: "vigencia",          desc: "Período de validez de la oferta" },
  { name: "codigoSKU",         desc: "Código de producto o SKU" },
  { name: "dia",               desc: "Día de la semana o número" },
  { name: "mes",               desc: "Mes de vigencia" },
  { name: "año",               desc: "Año de vigencia" },
  { name: "moneda",            desc: "Símbolo de moneda (ej: $, €)" },
  { name: "categoria",         desc: "Categoría del producto" },
  { name: "subCategoria",      desc: "Subcategoría del producto" },
  { name: "descuento",         desc: "¿Aplica descuento? Columna TRUE/FALSE en Excel" },
] as const;

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

  // Definición del template seleccionado (para detectar variables de imagen)
  const [templateDef,   setTemplateDef]   = useState<CenefaTemplate | null>(null);
  const [imageUploads,  setImageUploads]  = useState<Record<string, { file: File; ext: string }>>({});

  // Validación
  const [validating,        setValidating]        = useState(false);
  const [showMissingModal,  setShowMissingModal]  = useState(false);
  const [validation,  setValidation]  = useState<{
    total_rows: number;
    missing_required: string[];
    rule_summary: { rule_id: string; hits: number; pct: number }[];
    status: string;
  } | null>(null);

  const [varModalOpen, setVarModalOpen] = useState(false);

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

  // Cargar definición del template seleccionado para detectar componentes de imagen
  useEffect(() => {
    setTemplateDef(null);
    setImageUploads({});
    if (templateId && tmplMode === "v2") {
      cenefasV2Api.getTemplate(templateId)
        .then(({ data }) => setTemplateDef(data.definition ?? null))
        .catch(() => {});
    }
  }, [templateId, tmplMode]);

  // Variables de imagen: componentes tipo "image" con variable pero sin imagen estática
  const imageVarNames = useMemo(() => {
    if (!templateDef) return [] as string[];
    const names = new Set<string>();
    templateDef.components.forEach((c) => {
      if (c.type === "image" && c.variable && !c.image_data) {
        names.add(c.variable);
      }
    });
    return [...names];
  }, [templateDef]);

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

        // Codificar imágenes subidas a base64 e incluir como JSON
        const overrides: Record<string, string> = {};
        for (const [varName, upload] of Object.entries(imageUploads)) {
          if (upload) {
            const b64 = await fileToBase64(upload.file);
            overrides[varName] = `${upload.ext}:${b64}`;
          }
        }
        if (Object.keys(overrides).length > 0) {
          fd.append("image_overrides_json", JSON.stringify(overrides));
        }
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

  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const result = e.target?.result as string;
        resolve(result.split(",")[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
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
      {/* Variable reference modal */}
      {varModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <BookOpen size={15} className="text-brand-600" />
                <p className="font-semibold text-slate-800 dark:text-slate-200 text-sm">Referencia de variables</p>
              </div>
              <button onClick={() => setVarModalOpen(false)} className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                <X size={16} />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 divide-y divide-slate-100 dark:divide-slate-800">
              {VARIABLES_REFERENCE.map(({ name, desc }) => (
                <div key={name} className="flex items-center gap-3 px-5 py-2.5">
                  <code className="text-[11px] font-mono text-brand-700 shrink-0 bg-brand-50 border border-brand-100 px-1.5 py-0.5 rounded">
                    {`<<${name}>>`}
                  </code>
                  <span className="text-xs text-slate-500 dark:text-slate-400">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center gap-3">
        <a href="/herramientas/cenefas/v2"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors">
          <ChevronLeft size={18} />
        </a>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-200">Generar cenefas</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Motor v2 — componentes inteligentes</p>
        </div>
        <button
          onClick={() => setVarModalOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-500 hover:text-brand-600 hover:border-brand-300 transition-colors"
        >
          <BookOpen size={12} />
          Variables
        </button>
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
                    : "border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600"
                }`}
              >
                Template del editor ✦
              </button>
              <button
                onClick={() => setTmplMode("builtin")}
                className={`flex-1 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                  tmplMode === "builtin"
                    ? "border-slate-400 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                    : "border-slate-200 dark:border-slate-700 text-slate-400 hover:border-slate-300 dark:hover:border-slate-600"
                }`}
              >
                Plantilla clásica
              </button>
            </div>
            {tmplMode === "builtin" && (
              <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1.5">
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
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
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
            <label className="flex flex-col items-center gap-2 border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-xl p-5 cursor-pointer hover:border-brand-400 transition-colors mt-1">
              <FileSpreadsheet size={26} className={excel ? "text-emerald-500" : "text-slate-300"} />
              <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                {excel ? excel.name : "Cargá el Excel de productos"}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500">.xlsx o .xlsm</p>
              <input type="file" accept=".xlsx,.xlsm" className="hidden"
                onChange={(e) => setExcel(e.target.files?.[0] ?? null)} />
            </label>
          </div>

          {/* Imágenes para componentes de imagen del template */}
          {tmplMode === "v2" && imageVarNames.length > 0 && (
            <div>
              <SectionLabel>Imágenes</SectionLabel>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 mb-2">
                Tu template tiene {imageVarNames.length === 1 ? "un componente de imagen" : `${imageVarNames.length} componentes de imagen`}{" "}
                sin imagen guardada en el template. Podés subir {imageVarNames.length === 1 ? "una imagen" : "las imágenes"} ahora:
              </p>
              <div className="space-y-2">
                {imageVarNames.map((varName) => {
                  const upload = imageUploads[varName];
                  return (
                    <div key={varName}>
                      <label className="flex items-center gap-2.5 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 cursor-pointer hover:border-brand-400 transition-colors">
                        <ImageIcon size={18} className={upload ? "text-emerald-500" : "text-slate-300"} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-slate-700 dark:text-slate-300">
                            <code className="font-mono text-brand-700 bg-brand-50 px-1 py-0.5 rounded text-[10px]">{varName}</code>
                          </p>
                          <p className="text-xs text-slate-400 truncate mt-0.5">
                            {upload ? upload.file.name : "Clic para seleccionar imagen…"}
                          </p>
                        </div>
                        {upload && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              setImageUploads((prev) => {
                                const next = { ...prev };
                                delete next[varName];
                                return next;
                              });
                            }}
                            className="shrink-0 p-1 text-slate-300 hover:text-rose-500 transition-colors"
                          >
                            <X size={14} />
                          </button>
                        )}
                        <input
                          type="file"
                          accept="image/png,image/jpeg,image/gif,image/webp"
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (!file) return;
                            const ext = file.name.split(".").pop()?.toLowerCase() ?? "png";
                            setImageUploads((prev) => ({ ...prev, [varName]: { file, ext } }));
                          }}
                        />
                      </label>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Formato de salida */}
          <div>
            <SectionLabel>Formato de salida</SectionLabel>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
              {formats.map((f) => (
                <button key={f.id} onClick={() => setFormatId(f.id)}
                  className={`p-3 rounded-xl border text-center transition-all ${
                    formatId === f.id
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-slate-200 text-slate-600 hover:border-brand-300"
                  }`}
                >
                  <p className="text-sm font-semibold">{f.label}</p>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500">{f.width_cm}×{f.height_cm}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Metadata */}
          <div>
            <SectionLabel>Metadata (opcional)</SectionLabel>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
              <Field label="Vigencia" value={vigencia} onChange={setVigencia} />
              <ComboField label="Banco / Beneficio" value={banco} onChange={setBanco} storageKey="cenefa_opts_banco" />
              <div className="sm:col-span-2">
                <ComboField label="Aclaración" value={aclaracion} onChange={setAclaracion} storageKey="cenefa_opts_aclaracion" />
              </div>
              <div className="sm:col-span-2">
                <ComboField label="Segunda aclaración" value={otraAlcohol} onChange={setOtraAlcohol} storageKey="cenefa_opts_segunda_aclaracion" />
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
                    <span className="text-slate-600 dark:text-slate-400 truncate flex-1 font-medium">
                      {(r as any).rule_name || r.rule_id}
                    </span>
                    <div className="w-24 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
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
              <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl p-6 max-w-sm w-full mx-4 space-y-4">
                <div className="flex items-center gap-2 text-amber-600">
                  <AlertCircle size={20} />
                  <p className="font-semibold text-base">Variables no encontradas</p>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Las siguientes columnas no se encontraron en tu Excel:
                </p>
                <div className="bg-rose-50 border border-rose-200 rounded-xl p-3">
                  {validation.missing_required.map((v) => (
                    <p key={v} className="text-xs text-rose-600 font-mono">• {v}</p>
                  ))}
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400">
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
                <p className="text-base font-semibold text-slate-700 dark:text-slate-300">Generando cenefas…</p>
                <p className="text-sm text-slate-400 dark:text-slate-500 mt-1 capitalize">{job.status}</p>
              </div>
            </>
          ) : job.status === "done" ? (
            <>
              <CheckCircle2 size={40} className="text-emerald-500 mx-auto" />
              <div>
                <p className="text-base font-semibold text-slate-700 dark:text-slate-300">¡Listo!</p>
                {job.row_count && (
                  <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
                    {job.row_count} productos generados • {job.error_count} errores de datos
                  </p>
                )}
              </div>
              {job.missing_vars && job.missing_vars.length > 0 && (
                <div className="text-left rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-2">
                  <p className="text-sm font-semibold text-amber-800">
                    Variables del template no encontradas en el Excel
                  </p>
                  <p className="text-xs text-amber-700">
                    Estos placeholders existen en el diseño pero el Excel no tiene una columna con ese nombre exacto. Se exportaron en blanco:
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.missing_vars.map((v) => (
                      <code key={v} className="text-xs bg-white border border-amber-300 text-amber-900 rounded px-2 py-0.5 font-mono">
                        {"<<"}{v}{">>"}
                      </code>
                    ))}
                  </div>
                  <p className="text-xs text-amber-600">
                    Agregá una columna con ese nombre exacto en el Excel y generá de nuevo.
                  </p>
                </div>
              )}
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
              <p className="text-base font-semibold text-slate-700 dark:text-slate-300">Error en la generación</p>
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
                : "border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800"
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
                <span className={`flex-1 text-sm truncate ${isSelected ? "text-brand-700 font-medium" : "text-slate-700 dark:text-slate-300"}`}>
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
      <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <input className="input text-sm" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function ComboField({
  label, value, onChange, storageKey,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  storageKey: string;
}) {
  const [options, setOptions] = useState<string[]>([]);
  const [open,       setOpen]       = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editingVal, setEditingVal] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Load from localStorage after mount to avoid SSR hydration mismatch
  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) setOptions(JSON.parse(saved));
    } catch {}
  }, [storageKey]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setEditingIdx(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function persist(next: string[]) {
    setOptions(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  }

  function handleSaveCurrent() {
    const v = value.trim();
    if (!v || options.includes(v)) return;
    persist([...options, v]);
    toast.success("Opción guardada");
  }

  function handleDelete(idx: number) {
    persist(options.filter((_, i) => i !== idx));
  }

  function handleEditSave(idx: number) {
    if (!editingVal.trim()) return;
    const next = [...options];
    next[idx] = editingVal.trim();
    persist(next);
    setEditingIdx(null);
  }

  const canSave = !!value.trim() && !options.includes(value.trim());

  return (
    <div ref={ref} className="relative flex flex-col gap-1">
      <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <div className="flex gap-1 items-stretch">
        <input
          className="input text-sm flex-1 min-w-0"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setOpen(true)}
        />
        {canSave && (
          <button
            type="button"
            onClick={handleSaveCurrent}
            className="shrink-0 px-2.5 text-xs rounded-lg border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors"
            title="Guardar como opción"
          >
            Guardar
          </button>
        )}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 px-2 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
        >
          <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      </div>

      {open && (
        <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg max-h-52 overflow-y-auto">
          {options.length === 0 ? (
            <p className="px-3 py-3 text-xs text-slate-400 text-center">
              Sin opciones guardadas — escribí un valor y hacé clic en "Guardar".
            </p>
          ) : options.map((opt, idx) => (
            <div
              key={idx}
              className="flex items-center gap-1.5 px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800 group border-b border-slate-100 dark:border-slate-800 last:border-0"
            >
              {editingIdx === idx ? (
                <>
                  <input
                    autoFocus
                    className="flex-1 text-sm outline-none border-b border-brand-400 bg-transparent"
                    value={editingVal}
                    onChange={(e) => setEditingVal(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleEditSave(idx);
                      if (e.key === "Escape") setEditingIdx(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button
                    onClick={(e) => { e.stopPropagation(); handleEditSave(idx); }}
                    className="shrink-0 text-emerald-600 hover:text-emerald-700"
                  >
                    <Check size={13} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingIdx(null); }}
                    className="shrink-0 text-slate-400 hover:text-slate-600"
                  >
                    <X size={13} />
                  </button>
                </>
              ) : (
                <>
                  <span
                    className="flex-1 text-sm text-slate-700 dark:text-slate-300 cursor-pointer truncate"
                    onClick={() => { onChange(opt); setOpen(false); }}
                  >
                    {opt}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingIdx(idx); setEditingVal(opt); }}
                    className="shrink-0 p-0.5 text-slate-300 hover:text-brand-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Editar"
                  >
                    <Pencil size={11} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(idx); }}
                    className="shrink-0 p-0.5 text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Eliminar"
                  >
                    <Trash2 size={11} />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-4 text-center">
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{label}</p>
    </div>
  );
}
