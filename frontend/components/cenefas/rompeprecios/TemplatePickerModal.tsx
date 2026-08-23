"use client";
import { useEffect, useMemo, useState } from "react";
import { Search, Plus, X, Loader2, Trash2, RefreshCw, ExternalLink, FileType2, ChevronLeft, CheckSquare, Square, ListChecks } from "lucide-react";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaTemplateRecord } from "@/types/cenefas";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useEscapeKey } from "@/hooks/useEscapeKey";

// Reemplaza a SizeTemplateUploadModal + la grilla fija de 4 tamaños de
// RompePreciosPanel: dentro de un mismo mundo puede haber muchos diseños
// distintos para el mismo tamaño (ej: dos A4 de campañas distintas), así que
// el picker pasa a ser un listado buscable en vez de "una plantilla por
// tamaño". Vive en dos vistas dentro del mismo modal (no se cierra al pasar
// de una a otra): "list" (buscar/elegir/eliminar/reemplazar/editar) y
// "create" (subir una nueva con la convención de nombre Accion-AAAAMM-Tipo).

export const TEMPLATE_TYPES: { id: string; label: string }[] = [
  { id: "a4",      label: "A4" },
  { id: "3xa4",    label: "3xA4" },
  { id: "6xa4",    label: "6xA4" },
  { id: "a5",      label: "A5" },
  { id: "pinchos", label: "Pinchos" },
];

export function typeLabel(id: string | undefined | null): string {
  return TEMPLATE_TYPES.find((t) => t.id === id)?.label ?? id ?? "?";
}

function toTitleCase(raw: string): string {
  return raw
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - 1 + i);

interface TemplatePickerModalProps {
  /** Slug del destino/mundo. Dinámico: los mundos se crean desde la UI. */
  category: string;
  categoryLabel: string;
  onClose: () => void;
  onSelect: (tmpl: CenefaTemplateRecord) => void;
  /**
   * Cuando viene, el picker arranca en modo seleccion multiple: se tildan
   * varias plantillas y se agregan todas juntas. Sin esto habia que elegir
   * una, cerrar, volver a abrir y repetir.
   */
  onSelectMany?: (tmpls: CenefaTemplateRecord[]) => void;
  /** Cuantas se pueden tildar como maximo (las de mas quedan deshabilitadas). */
  maxSeleccion?: number;
}

export default function TemplatePickerModal({ category, categoryLabel, onClose, onSelect, onSelectMany, maxSeleccion }: TemplatePickerModalProps) {
  const { t } = useTranslation();
  useEscapeKey(onClose);

  const [view, setView] = useState<"list" | "create">("list");
  const [templates, setTemplates] = useState<CenefaTemplateRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Selección múltiple -- los templates duplicados de flujos viejos
  // (mismo nombre auto-generado, distinto id) se acumulan de a decenas;
  // borrar uno a la vez con el modal de confirmación individual es
  // impracticable para limpiarlos. Reusa el mismo endpoint de borrado
  // (uno por id, en paralelo) en vez de agregar un endpoint bulk nuevo.
  const [selectMode, setSelectMode] = useState(!!onSelectMany);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // Con onSelectMany el modo tildar es el modo por defecto: es a lo que se
  // vino. El boton de la barra sigue existiendo para volver al modo de a una.
  const modoAgregar = !!onSelectMany;
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkConfirming, setBulkConfirming] = useState(false);

  const [replacingId, setReplacingId] = useState<string | null>(null);
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [replaceSaving, setReplaceSaving] = useState(false);

  // Vista "crear"
  const [tipo, setTipo] = useState<string | null>(null);
  const [accion, setAccion] = useState("");
  const [mes, setMes] = useState<number | null>(null);
  const [anio, setAnio] = useState<number | null>(CURRENT_YEAR);
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);

  function loadTemplates() {
    setLoading(true);
    cenefasV2Api.listTemplates({ category })
      .then(({ data }) => setTemplates(data))
      .catch(() => toast.error(t("cenefas.unknownError")))
      .finally(() => setLoading(false));
  }

  useEffect(loadTemplates, [category]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return templates;
    return templates.filter((tm) => tm.name.toLowerCase().includes(q));
  }, [templates, search]);

  const tipoLabelSel = tipo ? typeLabel(tipo) : null;
  const composedName = accion.trim() && mes && anio && tipoLabelSel
    ? `${toTitleCase(accion)}-${anio}${String(mes).padStart(2, "0")}-${tipoLabelSel}`
    : null;
  const duplicateName = composedName
    ? templates.some((tm) => tm.name.toLowerCase() === composedName.toLowerCase())
    : false;

  function resetCreateForm() {
    setTipo(null);
    setAccion("");
    setMes(null);
    setAnio(CURRENT_YEAR);
    setFile(null);
  }

  async function handleCreate() {
    if (!tipo || !accion.trim() || !mes || !anio || !file || !composedName) {
      toast.error(t("cenefas.rompePrecios.picker.missingFields"));
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", composedName);
      fd.append("category", category);
      const [{ data: definition }, source_pptx_b64] = await Promise.all([
        cenefasV2Api.importPptx(fd),
        fileToBase64(file),
      ]);
      await cenefasV2Api.createTemplate({
        ...definition,
        name: composedName,
        formats: [tipo],
        category,
        source_pptx_b64,
      });
      toast.success(t("cenefas.rompePrecios.picker.saved"));
      resetCreateForm();
      setView("list");
      loadTemplates();
    } catch {
      toast.error(t("cenefas.rompePrecios.picker.saveError"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    setDeleting(true);
    try {
      await cenefasV2Api.deleteTemplate(id);
      setTemplates((prev) => prev.filter((tm) => tm.id !== id));
      toast.success(t("cenefas.rompePrecios.picker.deleted"));
    } catch {
      toast.error(t("cenefas.rompePrecios.picker.deleteError"));
    } finally {
      setDeleting(false);
      setDeletingId(null);
    }
  }

  function toggleSelectMode() {
    setSelectMode((v) => !v);
    setSelectedIds(new Set());
    setBulkConfirming(false);
    setDeletingId(null);
    setReplacingId(null);
  }

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function handleBulkDelete() {
    setBulkDeleting(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => cenefasV2Api.deleteTemplate(id)));
    const okIds = ids.filter((_, i) => results[i].status === "fulfilled");
    const failCount = ids.length - okIds.length;
    setTemplates((prev) => prev.filter((tm) => !okIds.includes(tm.id)));
    setSelectedIds(new Set());
    setBulkConfirming(false);
    setBulkDeleting(false);
    if (failCount === 0) {
      toast.success(t("cenefas.rompePrecios.picker.bulkDeleteOk", { count: okIds.length }));
    } else if (okIds.length === 0) {
      toast.error(t("cenefas.rompePrecios.picker.bulkDeleteAllFailed"));
    } else {
      toast.error(t("cenefas.rompePrecios.picker.bulkDeletePartial", { ok: okIds.length, fail: failCount }));
    }
  }

  async function handleReplace(tm: CenefaTemplateRecord) {
    if (!replaceFile) return;
    setReplaceSaving(true);
    try {
      const fd = new FormData();
      fd.append("file", replaceFile);
      fd.append("name", tm.name);
      fd.append("category", tm.category ?? category);
      const [{ data: definition }, source_pptx_b64] = await Promise.all([
        cenefasV2Api.importPptx(fd),
        fileToBase64(replaceFile),
      ]);
      await cenefasV2Api.updateTemplate(tm.id, {
        ...definition,
        name: tm.name,
        formats: tm.formats,
        category: tm.category ?? category,
        source_pptx_b64,
      });
      toast.success(t("cenefas.rompePrecios.picker.replaced"));
      setReplacingId(null);
      setReplaceFile(null);
      loadTemplates();
    } catch {
      toast.error(t("cenefas.rompePrecios.picker.replaceError"));
    } finally {
      setReplaceSaving(false);
    }
  }

  const months = t("cenefas.rompePrecios.picker.months", { returnObjects: true }) as string[];

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="template-picker-title"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-lg max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            {view === "create" && (
              <button
                onClick={() => setView("list")}
                className="p-1 -ml-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 shrink-0"
                aria-label={t("cenefas.rompePrecios.picker.backToList")}
              >
                <ChevronLeft size={16} />
              </button>
            )}
            <p id="template-picker-title" className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
              {view === "list"
                ? t("cenefas.rompePrecios.picker.title", { category: categoryLabel })
                : t("cenefas.rompePrecios.picker.addNew")}
            </p>
          </div>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0">
            <X size={18} />
          </button>
        </div>

        {view === "list" ? (
          <>
            <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 shrink-0 space-y-2.5">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("cenefas.rompePrecios.picker.searchPlaceholder")}
                    className="input text-sm pl-8 w-full"
                  />
                </div>
                <button
                  type="button"
                  onClick={toggleSelectMode}
                  disabled={templates.length === 0}
                  title={t("cenefas.rompePrecios.picker.selectMultiple")}
                  className={`shrink-0 p-2 rounded-lg border-2 transition-colors disabled:opacity-30 ${
                    selectMode
                      ? "border-brand-400 bg-brand-50 dark:bg-brand-950/30 text-brand-600 dark:text-brand-400"
                      : "border-slate-200 dark:border-slate-700 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                  }`}
                >
                  <ListChecks size={16} />
                </button>
              </div>
              {selectMode ? (
                bulkConfirming ? (
                  <div className="rounded-xl bg-rose-50/50 dark:bg-rose-950/10 px-3 py-2.5 space-y-2">
                    <p className="text-xs text-rose-600 dark:text-rose-400">
                      {t("cenefas.rompePrecios.picker.deleteSelectedConfirm", { count: selectedIds.size })}
                    </p>
                    <div className="flex gap-2">
                      <button
                        disabled={bulkDeleting}
                        onClick={handleBulkDelete}
                        className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:text-rose-800 px-2.5 py-1 rounded-lg bg-rose-100 dark:bg-rose-950/40 hover:bg-rose-200 dark:hover:bg-rose-950/70 disabled:opacity-50"
                      >
                        {bulkDeleting && <Loader2 size={12} className="animate-spin" />}
                        {t("cenefas.rompePrecios.picker.deleteYes")}
                      </button>
                      <button onClick={() => setBulkConfirming(false)} className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 px-2.5 py-1">
                        {t("cenefas.rompePrecios.picker.deleteCancel")}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {t("cenefas.rompePrecios.picker.selectedCount", { count: selectedIds.size })}
                      {maxSeleccion ? ` / ${maxSeleccion}` : ""}
                    </p>
                    {modoAgregar ? (
                      <button
                        type="button"
                        disabled={selectedIds.size === 0}
                        onClick={() => {
                          onSelectMany!(templates.filter((x) => selectedIds.has(x.id)));
                          onClose();
                        }}
                        className="btn-primary text-xs px-3 py-1.5 disabled:opacity-30"
                      >
                        {t("cenefas.rompePrecios.picker.agregarSeleccionadas", { count: selectedIds.size })}
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={selectedIds.size === 0}
                        onClick={() => setBulkConfirming(true)}
                        className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:text-rose-800 px-2.5 py-1 rounded-lg bg-rose-100 dark:bg-rose-950/40 hover:bg-rose-200 dark:hover:bg-rose-950/70 disabled:opacity-30"
                      >
                        <Trash2 size={12} /> {t("cenefas.rompePrecios.picker.deleteSelected")}
                      </button>
                    )}
                  </div>
                )
              ) : (
                <button
                  type="button"
                  onClick={() => setView("create")}
                  className="flex items-center justify-center gap-1.5 w-full text-sm font-semibold text-brand-600 dark:text-brand-400 border-2 border-dashed border-brand-300 dark:border-brand-800 rounded-xl py-2 hover:bg-brand-50 dark:hover:bg-brand-950/20 transition-colors"
                >
                  <Plus size={14} /> {t("cenefas.rompePrecios.picker.addNew")}
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="p-5 space-y-2">
                  {[0, 1, 2].map((i) => <div key={i} className="skeleton h-14 rounded-xl" />)}
                </div>
              ) : filtered.length === 0 ? (
                <p className="px-5 py-8 text-xs text-slate-400 dark:text-slate-500 text-center">
                  {templates.length === 0
                    ? t("cenefas.rompePrecios.picker.empty", { category: categoryLabel })
                    : t("cenefas.rompePrecios.picker.noResults")}
                </p>
              ) : (
                <ul className="divide-y divide-slate-50 dark:divide-slate-800">
                  {filtered.map((tm) => (
                    <li key={tm.id} className="group">
                      {deletingId === tm.id ? (
                        <div className="px-5 py-3 bg-rose-50/50 dark:bg-rose-950/10">
                          <p className="text-xs text-rose-600 dark:text-rose-400 mb-2">
                            {t("cenefas.rompePrecios.picker.deleteConfirm", { name: tm.name })}
                          </p>
                          <div className="flex gap-2">
                            <button
                              disabled={deleting}
                              onClick={() => handleDelete(tm.id)}
                              className="text-xs font-semibold text-rose-600 dark:text-rose-400 hover:text-rose-800 px-2.5 py-1 rounded-lg bg-rose-100 dark:bg-rose-950/40 hover:bg-rose-200 dark:hover:bg-rose-950/70 disabled:opacity-50"
                            >
                              {deleting ? <Loader2 size={12} className="animate-spin" /> : t("cenefas.rompePrecios.picker.deleteYes")}
                            </button>
                            <button onClick={() => setDeletingId(null)} className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 px-2.5 py-1">
                              {t("cenefas.rompePrecios.picker.deleteCancel")}
                            </button>
                          </div>
                        </div>
                      ) : replacingId === tm.id ? (
                        <div className="px-5 py-3 bg-brand-50/50 dark:bg-brand-950/10 space-y-2">
                          <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">{tm.name}</p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">{t("cenefas.rompePrecios.picker.replaceHint")}</p>
                          <label className={`flex items-center gap-2 px-3 py-2 rounded-lg border-2 cursor-pointer transition-all text-xs ${
                            replaceFile ? "border-brand-400 bg-brand-50 dark:bg-brand-950/20" : "border-dashed border-slate-300 dark:border-slate-700 hover:border-slate-400"
                          }`}>
                            <FileType2 size={14} className={replaceFile ? "text-brand-500" : "text-slate-400"} />
                            <span className={`flex-1 truncate ${replaceFile ? "text-brand-700 dark:text-brand-300 font-medium" : "text-slate-400"}`}>
                              {replaceFile ? replaceFile.name : t("cenefas.rompePrecios.picker.chooseFile")}
                            </span>
                            <input type="file" accept=".pptx" className="hidden" onChange={(e) => e.target.files?.[0] && setReplaceFile(e.target.files[0])} />
                          </label>
                          <div className="flex gap-2">
                            <button
                              disabled={!replaceFile || replaceSaving}
                              onClick={() => handleReplace(tm)}
                              className="flex items-center gap-1.5 text-xs font-semibold text-brand-700 dark:text-brand-300 hover:text-brand-900 px-2.5 py-1 rounded-lg bg-brand-100 dark:bg-brand-950/40 hover:bg-brand-200 dark:hover:bg-brand-950/70 disabled:opacity-40"
                            >
                              {replaceSaving && <Loader2 size={12} className="animate-spin" />}
                              {t("cenefas.rompePrecios.picker.replaceSave")}
                            </button>
                            <button onClick={() => { setReplacingId(null); setReplaceFile(null); }} className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 px-2.5 py-1">
                              {t("cenefas.rompePrecios.picker.deleteCancel")}
                            </button>
                          </div>
                        </div>
                      ) : selectMode ? (
                        <button
                          onClick={() => toggleSelected(tm.id)}
                          disabled={
                            !!maxSeleccion && !selectedIds.has(tm.id) && selectedIds.size >= maxSeleccion
                          }
                          className="flex items-center gap-3 w-full text-left px-5 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {selectedIds.has(tm.id)
                            ? <CheckSquare size={16} className="text-brand-500 shrink-0" />
                            : <Square size={16} className="text-slate-300 dark:text-slate-600 shrink-0" />}
                          <span className="min-w-0 flex-1">
                            <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">{tm.name}</p>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                              {tm.formats?.length ? tm.formats.map((f) => typeLabel(f)).join(", ") : "—"}
                            </p>
                          </span>
                        </button>
                      ) : (
                        <div className="flex items-center pr-2">
                          <button
                            onClick={() => onSelect(tm)}
                            className="flex-1 min-w-0 text-left px-5 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
                          >
                            <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">{tm.name}</p>
                            <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                              {tm.formats?.length ? tm.formats.map((f) => typeLabel(f)).join(", ") : "—"}
                            </p>
                          </button>
                          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity shrink-0">
                            <button
                              onClick={() => { setReplacingId(tm.id); setReplaceFile(null); setDeletingId(null); }}
                              title={t("cenefas.rompePrecios.picker.replace")}
                              className="p-1.5 text-slate-300 hover:text-brand-500 dark:text-slate-600 dark:hover:text-brand-400"
                            ><RefreshCw size={13} /></button>
                            <a
                              href={`/materiales/cenefas/v2?template_id=${tm.id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              title={t("cenefas.rompePrecios.picker.editHint")}
                              className="p-1.5 text-slate-300 hover:text-brand-500 dark:text-slate-600 dark:hover:text-brand-400"
                            ><ExternalLink size={13} /></a>
                            <button
                              onClick={() => { setDeletingId(tm.id); setReplacingId(null); }}
                              title={t("cenefas.rompePrecios.picker.delete")}
                              className="p-1.5 text-slate-300 hover:text-rose-500 dark:text-slate-600 dark:hover:text-rose-400"
                            ><Trash2 size={13} /></button>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("cenefas.rompePrecios.picker.typeLabel")}</span>
              <div className="grid grid-cols-3 gap-1.5">
                {TEMPLATE_TYPES.map((tt) => (
                  <button
                    key={tt.id}
                    type="button"
                    onClick={() => setTipo(tt.id)}
                    className={`px-2 py-2 rounded-lg text-xs font-semibold border-2 transition-all ${
                      tipo === tt.id
                        ? "border-brand-400 bg-brand-50 dark:bg-brand-950/20 text-brand-700 dark:text-brand-300"
                        : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600"
                    }`}
                  >
                    {tt.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("cenefas.rompePrecios.picker.actionNameLabel")}</span>
              <input
                type="text"
                value={accion}
                onChange={(e) => setAccion(e.target.value)}
                placeholder={t("cenefas.rompePrecios.picker.actionNamePlaceholder")}
                className="input text-sm"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("cenefas.rompePrecios.picker.monthLabel")}</span>
                <select
                  value={mes ?? ""}
                  onChange={(e) => setMes(e.target.value ? Number(e.target.value) : null)}
                  className="input text-sm"
                >
                  <option value="">{t("cenefas.rompePrecios.picker.selectMonth")}</option>
                  {months.map((m, i) => (
                    <option key={i + 1} value={i + 1}>{m}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("cenefas.rompePrecios.picker.yearLabel")}</span>
                <select
                  value={anio ?? ""}
                  onChange={(e) => setAnio(e.target.value ? Number(e.target.value) : null)}
                  className="input text-sm"
                >
                  {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </label>
            </div>

            <label
              className={`flex items-center gap-2.5 px-3 py-3 rounded-xl border-2 cursor-pointer transition-all ${
                file ? "border-brand-400 bg-brand-50 dark:bg-brand-950/20" : "border-dashed border-slate-300 dark:border-slate-700 hover:border-slate-400"
              }`}
            >
              <FileType2 size={16} className={file ? "text-brand-500" : "text-slate-400"} />
              <span className={`text-sm flex-1 truncate ${file ? "text-brand-700 dark:text-brand-300 font-medium" : "text-slate-400"}`}>
                {file ? file.name : t("cenefas.rompePrecios.picker.chooseFile")}
              </span>
              <input type="file" accept=".pptx" className="hidden" onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])} />
            </label>

            {composedName && (
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2">
                <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wide">{t("cenefas.rompePrecios.picker.namePreview")}</p>
                <p className="text-sm font-mono text-slate-700 dark:text-slate-300 truncate">{composedName}</p>
                {duplicateName && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">{t("cenefas.rompePrecios.picker.duplicateWarning")}</p>
                )}
              </div>
            )}

            <button
              onClick={handleCreate}
              disabled={!tipo || !accion.trim() || !mes || !anio || !file || saving}
              className="btn-primary w-full text-sm py-2 disabled:opacity-40"
            >
              {saving
                ? <span className="flex items-center justify-center gap-1.5"><Loader2 size={14} className="animate-spin" /> {t("cenefas.rompePrecios.picker.saving")}</span>
                : t("cenefas.rompePrecios.picker.save")
              }
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
