"use client";
import { useState, useRef, useEffect, ChangeEvent, FormEvent } from "react";
import {
  Upload, Presentation, Download, AlertCircle, CheckCircle2, Loader2,
  FileSpreadsheet, FileType2, Plus, Trash2, X, LayoutTemplate, Layers, ChevronRight,
  ChevronDown, Check, Pencil,
} from "lucide-react";
import { toolsApi } from "@/lib/api";
import { useTranslation } from "react-i18next";
import { format } from "date-fns";
import { toast } from "sonner";

type Status = "idle" | "loading" | "success" | "error";

interface TemplateInfo {
  id: number;
  name: string;
  format_name: string;
  created_at: string | null;
}

interface BuiltinTemplate {
  slug: string;
  name: string;
  format_name: string;
}

export default function CenefasPage() {
  const { t } = useTranslation();

  // Generation state
  const [excel, setExcel] = useState<File | null>(null);
  const [customPptx, setCustomPptx] = useState<File | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [selectedBuiltinSlug, setSelectedBuiltinSlug] = useState<string | null>(null);
  const [vigencia, setVigencia] = useState("");
  const [aclaracion, setAclaracion] = useState("Bases y condiciones en redexpres.uy");
  const [otraAlcohol, setOtraAlcohol] = useState(
    "Prohibida la venta de bebidas alcohólicas a menores de 18 años"
  );
  const [banco, setBanco] = useState("");
  const [margin, setMargin] = useState("0");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const downloadRef = useRef<HTMLAnchorElement>(null);

  // Templates state
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [builtinTemplates, setBuiltinTemplates] = useState<BuiltinTemplate[]>([]);

  // New template form state
  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newFormat, setNewFormat] = useState("");
  const [newFile, setNewFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    toolsApi.getCenefaTemplates()
      .then(({ data }) => setTemplates(data))
      .catch(() => {})
      .finally(() => setLoadingTemplates(false));
    toolsApi.getBuiltinTemplates()
      .then(({ data }) => setBuiltinTemplates(data))
      .catch(() => {});
  }, []);

  function selectTemplate(id: number) {
    if (selectedTemplateId === id) {
      setSelectedTemplateId(null);
    } else {
      setSelectedTemplateId(id);
      setSelectedBuiltinSlug(null);
      setCustomPptx(null);
    }
  }

  function selectBuiltin(slug: string) {
    if (selectedBuiltinSlug === slug) {
      setSelectedBuiltinSlug(null);
    } else {
      setSelectedBuiltinSlug(slug);
      setSelectedTemplateId(null);
      setCustomPptx(null);
    }
  }

  function handleCustomPptxChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setCustomPptx(file);
      setSelectedTemplateId(null);
      setSelectedBuiltinSlug(null);
    }
  }

  async function handleUploadTemplate(e: FormEvent) {
    e.preventDefault();
    if (!newFile || !newName.trim()) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("name", newName.trim());
      fd.append("format_name", newFormat.trim());
      fd.append("file", newFile);
      const { data } = await toolsApi.createCenefaTemplate(fd);
      setTemplates((prev) => [data, ...prev]);
      setNewName("");
      setNewFormat("");
      setNewFile(null);
      setShowNewForm(false);
      toast.success(t("cenefas.templateSaved"));
    } catch {
      toast.error(t("cenefas.templateSaveError"));
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteTemplate(id: number) {
    if (!confirm(t("cenefas.templateDeleteConfirm"))) return;
    try {
      await toolsApi.deleteCenefaTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      if (selectedTemplateId === id) setSelectedTemplateId(null);
      toast.success(t("cenefas.templateDeleted"));
    } catch {
      toast.error(t("cenefas.templateDeleteError"));
    }
  }

  async function handleDownloadTemplate() {
    try {
      const { data } = await toolsApi.downloadExcelTemplate();
      const url = URL.createObjectURL(new Blob([data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "plantilla_cenefas.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error(t("cenefas.unknownError"));
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setStatus("loading");
    setErrorMsg("");
    try {
      const fd = new FormData();
      fd.append("excel", excel!);
      if (selectedTemplateId !== null) {
        fd.append("template_id", selectedTemplateId.toString());
      } else if (selectedBuiltinSlug !== null) {
        fd.append("builtin_slug", selectedBuiltinSlug);
      } else {
        fd.append("template", customPptx!);
      }
      fd.append("vigencia", vigencia.trim());
      fd.append("aclaracion", aclaracion.trim());
      fd.append("otra_alcohol", otraAlcohol.trim());
      fd.append("banco", banco.trim());
      fd.append("margin_cm", margin);

      const { data } = await toolsApi.generateCenefas(fd);
      const url = URL.createObjectURL(new Blob([data], {
        type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      }));
      if (downloadRef.current) {
        downloadRef.current.href = url;
        downloadRef.current.download = "cenefas_output.pptx";
        downloadRef.current.click();
        URL.revokeObjectURL(url);
      }
      setStatus("success");
    } catch (err: any) {
      const detail = err?.response?.data
        ? await err.response.data.text?.() ?? t("cenefas.unknownError")
        : err?.message ?? t("cenefas.unknownError");
      setErrorMsg(detail);
      setStatus("error");
    }
  }

  const hasTemplate = selectedTemplateId !== null || !!customPptx || selectedBuiltinSlug !== null;
  const canSubmit = !!excel && hasTemplate && status !== "loading";

  return (
    <div className="animate-fade-in max-w-2xl space-y-6">
      {/* Banner Editor v2 */}
      <a
        href="/herramientas/cenefas/v2"
        className="flex items-center gap-4 p-4 rounded-2xl bg-gradient-to-r from-brand-600 to-brand-500 text-white hover:from-brand-700 hover:to-brand-600 transition-all shadow-sm group"
      >
        <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
          <Layers size={20} className="text-white" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-bold">Nuevo: Editor Visual v2</p>
          <p className="text-xs text-brand-100 mt-0.5">
            Diseñá componentes, aplicá reglas y generá múltiples formatos desde un solo template
          </p>
        </div>
        <ChevronRight size={18} className="text-white/70 group-hover:text-white transition-colors" />
      </a>

      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
          <Presentation size={22} className="text-emerald-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("cenefas.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("cenefas.subtitle")}</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Templates card */}
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
              {t("cenefas.savedTemplates")}
            </p>
            <button
              type="button"
              onClick={() => setShowNewForm(!showNewForm)}
              className="flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors"
            >
              <Plus size={13} />
              {t("cenefas.newTemplate")}
            </button>
          </div>

          {/* Built-in templates */}
          {builtinTemplates.length > 0 && (
            <div className="space-y-2">
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">
                {t("cenefas.builtinTemplates")}
              </p>
              <div className="flex flex-wrap gap-2">
                {builtinTemplates.map((tmpl) => (
                  <button
                    key={tmpl.slug}
                    type="button"
                    onClick={() => selectBuiltin(tmpl.slug)}
                    className={`flex flex-col gap-1 px-3 py-2.5 rounded-xl border-2 cursor-pointer transition-all duration-150 min-w-[120px] text-left ${
                      selectedBuiltinSlug === tmpl.slug
                        ? "border-indigo-400 bg-indigo-50"
                        : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-700"
                    }`}
                  >
                    <p className={`text-xs font-semibold leading-tight ${
                      selectedBuiltinSlug === tmpl.slug ? "text-indigo-700" : "text-slate-700 dark:text-slate-300"
                    }`}>
                      {tmpl.name}
                    </p>
                    {tmpl.format_name && (
                      <span className={`self-start text-[10px] font-bold px-1.5 py-0.5 rounded-md ${
                        selectedBuiltinSlug === tmpl.slug
                          ? "bg-indigo-200 text-indigo-700"
                          : "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400"
                      }`}>
                        {tmpl.format_name}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* New template form */}
          {showNewForm && (
            <div className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3">
              <div className="flex gap-3">
                <label className="flex-1 flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{t("cenefas.templateName")}</span>
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder={t("cenefas.templateNamePlaceholder")}
                    className="input text-sm"
                    required
                  />
                </label>
                <label className="w-32 flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{t("cenefas.templateFormat")}</span>
                  <input
                    type="text"
                    value={newFormat}
                    onChange={(e) => setNewFormat(e.target.value)}
                    placeholder="A4, A5..."
                    className="input text-sm"
                  />
                </label>
              </div>
              <label className="flex flex-col gap-1 cursor-pointer">
                <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{t("cenefas.pptxLabel")}</span>
                <div className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border-2 transition-all duration-150 ${
                  newFile ? "border-brand-400 bg-brand-50" : "border-dashed border-slate-300 hover:border-slate-400"
                }`}>
                  <FileType2 size={15} className={newFile ? "text-brand-500" : "text-slate-400"} />
                  <span className={`text-sm flex-1 truncate ${newFile ? "text-brand-700 font-medium" : "text-slate-400"}`}>
                    {newFile ? newFile.name : t("cenefas.chooseFile")}
                  </span>
                  {newFile && (
                    <button type="button" onClick={() => setNewFile(null)} className="text-slate-400 hover:text-slate-600">
                      <X size={14} />
                    </button>
                  )}
                </div>
                <input
                  type="file"
                  accept=".pptx"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && setNewFile(e.target.files[0])}
                />
              </label>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => { setShowNewForm(false); setNewName(""); setNewFormat(""); setNewFile(null); }}
                  className="btn-ghost text-sm px-3 py-1.5"
                >
                  {t("cenefas.cancel")}
                </button>
                <button
                  type="button"
                  onClick={handleUploadTemplate}
                  disabled={uploading || !newFile || !newName.trim()}
                  className="btn-primary text-sm px-4 py-1.5 disabled:opacity-40"
                >
                  {uploading ? <><Loader2 size={13} className="animate-spin" /> {t("cenefas.uploading")}</> : t("cenefas.uploadTemplate")}
                </button>
              </div>
            </div>
          )}

          {/* Templates list */}
          {loadingTemplates ? (
            <div className="flex gap-2">
              {[1, 2].map((i) => <div key={i} className="skeleton h-16 w-40 rounded-xl" />)}
            </div>
          ) : templates.length === 0 ? (
            <div className="flex items-center gap-3 py-3 text-slate-400">
              <LayoutTemplate size={16} />
              <p className="text-xs">{t("cenefas.noTemplates")}</p>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {templates.map((tmpl) => (
                <div
                  key={tmpl.id}
                  onClick={() => selectTemplate(tmpl.id)}
                  className={`relative group flex flex-col gap-1 px-3 py-2.5 rounded-xl border-2 cursor-pointer transition-all duration-150 min-w-[140px] ${
                    selectedTemplateId === tmpl.id
                      ? "border-emerald-400 bg-emerald-50"
                      : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-xs font-semibold leading-tight truncate max-w-[110px] ${
                      selectedTemplateId === tmpl.id ? "text-emerald-700" : "text-slate-700 dark:text-slate-300"
                    }`}>
                      {tmpl.name}
                    </p>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleDeleteTemplate(tmpl.id); }}
                      className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-500 transition-all shrink-0"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                  {tmpl.format_name && (
                    <span className={`self-start text-[10px] font-bold px-1.5 py-0.5 rounded-md ${
                      selectedTemplateId === tmpl.id ? "bg-emerald-200 text-emerald-700" : "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400"
                    }`}>
                      {tmpl.format_name}
                    </span>
                  )}
                  {tmpl.created_at && (
                    <p className="text-[10px] text-slate-400">
                      {format(new Date(tmpl.created_at), "dd/MM/yy")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Separator */}
          <div className="flex items-center gap-2">
            <div className="h-px flex-1 bg-slate-100 dark:bg-slate-800" />
            <span className="text-[11px] text-slate-400 dark:text-slate-500 px-1">{t("cenefas.orUploadNew")}</span>
            <div className="h-px flex-1 bg-slate-100 dark:bg-slate-800" />
          </div>

          {/* Custom PPTX upload */}
          <FileDropField
            label={t("cenefas.pptxLabel")}
            hint={t("cenefas.pptxHint")}
            accept=".pptx"
            file={customPptx}
            icon={FileType2}
            accentColor="brand"
            onChange={handleCustomPptxChange}
            chooseLabel={t("cenefas.chooseFile")}
            readyLabel={t("cenefas.ready")}
            searchLabel={t("cenefas.search")}
            dimmed={selectedTemplateId !== null}
          />
        </div>

        {/* Excel card */}
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{t("cenefas.filesSection")}</p>
            <button
              type="button"
              onClick={handleDownloadTemplate}
              className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 hover:text-emerald-700 transition-colors"
            >
              <FileSpreadsheet size={13} />
              {t("cenefas.downloadTemplate")}
            </button>
          </div>
          <FileDropField
            label={t("cenefas.excelLabel")}
            hint={t("cenefas.excelHint")}
            accept=".xlsx,.xlsm"
            file={excel}
            icon={FileSpreadsheet}
            accentColor="emerald"
            onChange={(e) => e.target.files?.[0] && setExcel(e.target.files[0])}
            chooseLabel={t("cenefas.chooseFile")}
            readyLabel={t("cenefas.ready")}
            searchLabel={t("cenefas.search")}
          />
        </div>

        {/* Config card */}
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{t("cenefas.configSection")}</p>
          <Field label={t("cenefas.vigencia")} placeholder={t("cenefas.vigenciaPlaceholder")} value={vigencia} onChange={setVigencia} />
          <ComboField label={t("cenefas.aclaracion")} value={aclaracion} onChange={setAclaracion} storageKey="cenefa_opts_aclaracion" />
          <ComboField label={t("cenefas.alcohol")} value={otraAlcohol} onChange={setOtraAlcohol} storageKey="cenefa_opts_segunda_aclaracion" />
          <ComboField label="Banco / Beneficio" value={banco} onChange={setBanco} storageKey="cenefa_opts_banco" />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Margen lateral (cm)</label>
            <input
              type="number"
              min="0"
              max="10"
              step="0.1"
              value={margin}
              onChange={(e) => setMargin(e.target.value)}
              className="input w-32"
              placeholder="0"
            />
          </div>
        </div>

        {/* Feedback */}
        {status === "error" && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <AlertCircle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{errorMsg}</p>
          </div>
        )}
        {status === "success" && (
          <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
            <CheckCircle2 size={16} className="text-emerald-600" />
            <p className="text-sm text-emerald-700 font-medium">{t("cenefas.successMsg")}</p>
          </div>
        )}

        <button type="submit" disabled={!canSubmit} className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed">
          {status === "loading" ? (
            <><Loader2 size={16} className="animate-spin" /> {t("cenefas.generating")}</>
          ) : (
            <><Download size={16} /> {t("cenefas.generate")}</>
          )}
        </button>
      </form>

      <a ref={downloadRef} className="hidden" />
    </div>
  );
}

// ---------------------------------------------------------------------------

function FileDropField({
  label, hint, accept, file, onChange, icon: Icon, accentColor,
  chooseLabel, readyLabel, searchLabel, dimmed,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  icon: React.ElementType;
  accentColor: "emerald" | "brand";
  chooseLabel: string;
  readyLabel: string;
  searchLabel: string;
  dimmed?: boolean;
}) {
  const id = label.replace(/\s+/g, "-").toLowerCase();
  const active = !!file;
  const colors = {
    emerald: {
      border: active ? "border-emerald-400 bg-emerald-50" : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-700",
      icon: active ? "text-emerald-500" : "text-slate-400",
      text: active ? "text-emerald-700 font-medium" : "text-slate-500 dark:text-slate-400",
      badge: "bg-emerald-100 text-emerald-700",
    },
    brand: {
      border: active ? "border-brand-400 bg-brand-50" : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-white dark:hover:bg-slate-700",
      icon: active ? "text-brand-500" : "text-slate-400",
      text: active ? "text-brand-700 font-medium" : "text-slate-500 dark:text-slate-400",
      badge: "bg-brand-100 text-brand-700",
    },
  }[accentColor];

  return (
    <label htmlFor={id} className={`flex flex-col gap-1.5 cursor-pointer transition-opacity ${dimmed ? "opacity-40 pointer-events-none" : ""}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
        <span className="text-xs text-slate-400 dark:text-slate-500">{hint}</span>
      </div>
      <div className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border-2 transition-all duration-150 ${colors.border}`}>
        <Icon size={18} className={`shrink-0 ${colors.icon}`} />
        <span className={`text-sm flex-1 truncate ${colors.text}`}>
          {file ? file.name : chooseLabel}
        </span>
        {!file && (
          <span className="text-xs px-2.5 py-1 rounded-lg bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 font-medium shrink-0">
            {searchLabel}
          </span>
        )}
        {file && (
          <span className={`text-xs px-2.5 py-1 rounded-lg font-medium shrink-0 ${colors.badge}`}>
            {readyLabel}
          </span>
        )}
      </div>
      <input id={id} type="file" accept={accept} onChange={onChange} className="hidden" />
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
    <div ref={ref} className="relative flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
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
                  <button onClick={(e) => { e.stopPropagation(); handleEditSave(idx); }} className="shrink-0 text-emerald-600 hover:text-emerald-700"><Check size={13} /></button>
                  <button onClick={(e) => { e.stopPropagation(); setEditingIdx(null); }} className="shrink-0 text-slate-400 hover:text-slate-600"><X size={13} /></button>
                </>
              ) : (
                <>
                  <span className="flex-1 text-sm text-slate-700 dark:text-slate-300 cursor-pointer truncate" onClick={() => { onChange(opt); setOpen(false); }}>{opt}</span>
                  <button onClick={(e) => { e.stopPropagation(); setEditingIdx(idx); setEditingVal(opt); }} className="shrink-0 p-0.5 text-slate-300 hover:text-brand-500 opacity-0 group-hover:opacity-100"><Pencil size={11} /></button>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(idx); }} className="shrink-0 p-0.5 text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100"><Trash2 size={11} /></button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, placeholder, value, onChange }: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="input text-sm" />
    </label>
  );
}
