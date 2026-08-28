"use client";
import { useEffect, useRef, useState } from "react";
import {
  BookOpen, Search, Pencil, Check, X, Loader2, ChevronLeft, ChevronRight,
  Download, Layers, Tag, Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type SkuDescripcionItem, type GrupoUnificadoItem } from "@/lib/api";

// Diccionario en dos solapas (decisión de Ivan, 2026-08-28):
//
//   Singulares — sku_descripciones: UN SKU, UNA descripción de ESE producto.
//   Plurales   — cenefa_grupos_unificados: varios SKU que comparten un cartel
//                ("Coca-Cola Light o Zero 2.25 L"), con la lista de SKU como
//                dato propio.
//
// Ninguna pisa a la otra: unificar en el Convertidor escribe SOLO en la tabla
// de grupos, y el catálogo singular rechaza claves combinadas (ver
// _RE_CLAVE_PLURAL en backend convertidor.py). Cada solapa se descarga a
// Excel por separado.

const PAGE_SIZE = 100;

type Tab = "singulares" | "plurales";

export default function DiccionarioPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("singulares");

  // ── Singulares ─────────────────────────────────────────────────────────
  const [items, setItems] = useState<SkuDescripcionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editingSku, setEditingSku] = useState<string | null>(null);
  const [editDescripcion, setEditDescripcion] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Plurales ───────────────────────────────────────────────────────────
  const [grupos, setGrupos] = useState<GrupoUnificadoItem[]>([]);
  const [totalGrupos, setTotalGrupos] = useState(0);
  const [qG, setQG] = useState("");
  const [pageG, setPageG] = useState(0);
  const [loadingG, setLoadingG] = useState(true);
  const [editingGrupo, setEditingGrupo] = useState<string | null>(null);
  const [editGrupoDesc, setEditGrupoDesc] = useState("");
  const [deletingGrupo, setDeletingGrupo] = useState<string | null>(null);
  const debounceGRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [descargando, setDescargando] = useState(false);

  async function load(query: string, pageArg: number) {
    setLoading(true);
    try {
      const { data } = await convertidorApi.listarDescripciones(query, PAGE_SIZE, pageArg * PAGE_SIZE);
      setItems(data.items);
      setTotal(data.total);
    } catch {
      toast.error(t("diccionario.loadError"));
    } finally {
      setLoading(false);
    }
  }

  async function loadGrupos(query: string, pageArg: number) {
    setLoadingG(true);
    try {
      const { data } = await convertidorApi.listarGruposUnificados(query, PAGE_SIZE, pageArg * PAGE_SIZE);
      setGrupos(data.items);
      setTotalGrupos(data.total);
    } catch {
      toast.error(t("diccionario.loadError"));
    } finally {
      setLoadingG(false);
    }
  }

  useEffect(() => {
    load("", 0);
    loadGrupos("", 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setPage(0); load(q, 0); }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => {
    if (debounceGRef.current) clearTimeout(debounceGRef.current);
    debounceGRef.current = setTimeout(() => { setPageG(0); loadGrupos(qG, 0); }, 350);
    return () => { if (debounceGRef.current) clearTimeout(debounceGRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qG]);

  function goToPage(newPage: number) {
    setEditingSku(null);
    setPage(newPage);
    load(q, newPage);
  }

  function goToPageG(newPage: number) {
    setEditingGrupo(null);
    setPageG(newPage);
    loadGrupos(qG, newPage);
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const totalPagesG = Math.max(1, Math.ceil(totalGrupos / PAGE_SIZE));

  // ── edición singular ─────────────────────────────────────────────────────
  function startEdit(item: SkuDescripcionItem) {
    setEditingSku(item.sku);
    setEditDescripcion(item.descripcion);
  }

  async function saveEdit(sku: string) {
    const descripcion = editDescripcion.trim();
    if (!descripcion) return;
    setSavingEdit(true);
    try {
      await convertidorApi.updateDescripcion(sku, descripcion);
      setItems((prev) => prev.map((it) => (it.sku === sku ? { ...it, descripcion } : it)));
      toast.success(t("diccionario.editSuccess"));
      setEditingSku(null);
    } catch {
      toast.error(t("diccionario.editError"));
    } finally {
      setSavingEdit(false);
    }
  }

  // ── edición / borrado plural ─────────────────────────────────────────────
  function startEditGrupo(g: GrupoUnificadoItem) {
    setEditingGrupo(g.id);
    setEditGrupoDesc(g.descripcion);
  }

  async function saveEditGrupo(id: string) {
    const descripcion = editGrupoDesc.trim();
    if (!descripcion) return;
    setSavingEdit(true);
    try {
      await convertidorApi.updateGrupoUnificado(id, { descripcion });
      setGrupos((prev) => prev.map((g) => (g.id === id ? { ...g, descripcion } : g)));
      toast.success(t("diccionario.editSuccess"));
      setEditingGrupo(null);
    } catch {
      toast.error(t("diccionario.editError"));
    } finally {
      setSavingEdit(false);
    }
  }

  async function borrarGrupo(g: GrupoUnificadoItem) {
    if (!confirm(t("diccionario.deleteGrupoConfirm", { nombre: g.nombre }))) return;
    setDeletingGrupo(g.id);
    try {
      await convertidorApi.deleteGrupoUnificado(g.id);
      setGrupos((prev) => prev.filter((x) => x.id !== g.id));
      setTotalGrupos((n) => Math.max(0, n - 1));
      toast.success(t("diccionario.deleteGrupoOk"));
    } catch {
      toast.error(t("diccionario.deleteGrupoError"));
    } finally {
      setDeletingGrupo(null);
    }
  }

  // ── descarga por solapa ──────────────────────────────────────────────────
  async function handleDescargar() {
    setDescargando(true);
    try {
      const { data } = await convertidorApi.exportDiccionario(tab);
      const url = URL.createObjectURL(new Blob([data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `diccionario_${tab}_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error(t("diccionario.downloadError"));
    } finally {
      setDescargando(false);
    }
  }

  const tabBtn = (activo: boolean) =>
    `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
      activo
        ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
        : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
    }`;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
            <BookOpen size={22} className="text-emerald-400" />
          </div>
          <div>
            <h1 className="section-title">{t("diccionario.title")}</h1>
            <p className="section-sub mt-0.5">{t("diccionario.subtitle")}</p>
          </div>
        </div>
        <button
          onClick={handleDescargar}
          disabled={descargando || (tab === "singulares" ? total === 0 : totalGrupos === 0)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {descargando ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
          {t("diccionario.download")}
        </button>
      </div>

      {/* Solapas */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1 w-fit">
          <button onClick={() => setTab("singulares")} className={tabBtn(tab === "singulares")}>
            <Tag size={13} /> {t("diccionario.tabSingulares")}
            <span className="text-[10px] opacity-60">{total}</span>
          </button>
          <button onClick={() => setTab("plurales")} className={tabBtn(tab === "plurales")}>
            <Layers size={13} /> {t("diccionario.tabPlurales")}
            <span className="text-[10px] opacity-60">{totalGrupos}</span>
          </button>
        </div>
        <p className="text-xs text-slate-400 dark:text-slate-500">
          {tab === "singulares" ? t("diccionario.singularHint") : t("diccionario.pluralHint")}
        </p>
      </div>

      {/* Búsqueda */}
      <div className="relative max-w-md">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        {tab === "singulares" ? (
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("diccionario.searchPlaceholder")}
            className="w-full text-sm bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl pl-9 pr-3 py-2.5 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
          />
        ) : (
          <input
            value={qG}
            onChange={(e) => setQG(e.target.value)}
            placeholder={t("diccionario.searchPlaceholderPlural")}
            className="w-full text-sm bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl pl-9 pr-3 py-2.5 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
          />
        )}
      </div>

      {/* ── SOLAPA SINGULARES ─────────────────────────────────────────────── */}
      {tab === "singulares" && (
        <>
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            {loading ? (
              <div className="p-10 flex justify-center"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
            ) : items.length === 0 ? (
              <p className="p-10 text-center text-sm text-slate-400">
                {q ? t("diccionario.noResults") : t("diccionario.empty")}
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">
                    <th className="px-4 py-3 w-40">{t("diccionario.colSku")}</th>
                    <th className="px-4 py-3">{t("diccionario.colDescripcion")}</th>
                    <th className="px-4 py-3 w-20"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const isEditing = editingSku === item.sku;
                    return (
                      <tr
                        key={item.sku}
                        className="border-b border-slate-50 dark:border-slate-800/60 last:border-0 hover:bg-slate-50/60 dark:hover:bg-slate-800/30"
                      >
                        <td className="px-4 py-2.5">
                          <span className="font-mono text-xs text-slate-600 dark:text-slate-300">{item.sku}</span>
                        </td>
                        <td className="px-4 py-2.5">
                          {isEditing ? (
                            <input
                              value={editDescripcion}
                              onChange={(e) => setEditDescripcion(e.target.value)}
                              autoFocus
                              className="w-full text-sm bg-slate-100 dark:bg-slate-800 rounded-lg px-2 py-1.5 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                            />
                          ) : (
                            <span className="text-slate-700 dark:text-slate-300">{item.descripcion}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          {isEditing ? (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => saveEdit(item.sku)}
                                disabled={savingEdit}
                                className="text-emerald-500 hover:text-emerald-600 disabled:opacity-40"
                              >
                                <Check size={15} />
                              </button>
                              <button onClick={() => setEditingSku(null)} className="text-slate-400 hover:text-slate-600">
                                <X size={15} />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => startEdit(item)}
                              className="text-slate-400 hover:text-brand-500"
                              title={t("diccionario.edit") as string}
                            >
                              <Pencil size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {!loading && items.length > 0 && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-400">{t("diccionario.totalCount", { count: total })}</p>
              {totalPages > 1 && (
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => goToPage(page - 1)}
                    disabled={page === 0}
                    className="w-7 h-7 flex items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="text-xs text-slate-400">
                    {t("diccionario.pageOf", { page: page + 1, total: totalPages })}
                  </span>
                  <button
                    onClick={() => goToPage(page + 1)}
                    disabled={page + 1 >= totalPages}
                    className="w-7 h-7 flex items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── SOLAPA PLURALES ───────────────────────────────────────────────── */}
      {tab === "plurales" && (
        <>
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            {loadingG ? (
              <div className="p-10 flex justify-center"><Loader2 size={20} className="animate-spin text-slate-400" /></div>
            ) : grupos.length === 0 ? (
              <p className="p-10 text-center text-sm text-slate-400">
                {qG ? t("diccionario.gruposNoResults") : t("diccionario.gruposEmpty")}
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">
                    <th className="px-4 py-3">{t("diccionario.colDescripcion")}</th>
                    <th className="px-4 py-3 w-64">{t("diccionario.colSkus")}</th>
                    <th className="px-4 py-3 w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {grupos.map((g) => {
                    const isEditing = editingGrupo === g.id;
                    return (
                      <tr
                        key={g.id}
                        className="border-b border-slate-50 dark:border-slate-800/60 last:border-0 hover:bg-slate-50/60 dark:hover:bg-slate-800/30 align-top"
                      >
                        <td className="px-4 py-2.5">
                          {isEditing ? (
                            <input
                              value={editGrupoDesc}
                              onChange={(e) => setEditGrupoDesc(e.target.value)}
                              autoFocus
                              className="w-full text-sm bg-slate-100 dark:bg-slate-800 rounded-lg px-2 py-1.5 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                            />
                          ) : (
                            <>
                              <span className="text-slate-700 dark:text-slate-300">{g.descripcion}</span>
                              {g.nombre && g.nombre !== g.descripcion && (
                                <span className="block text-[11px] text-slate-400 mt-0.5">{g.nombre}</span>
                              )}
                            </>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex flex-wrap gap-1">
                            {g.skus.map((s) => (
                              <span key={s} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                                {s}
                              </span>
                            ))}
                          </div>
                          <span className="block text-[10px] text-slate-400 mt-1">
                            {t("diccionario.skuCount", { count: g.skus.length })}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          {isEditing ? (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => saveEditGrupo(g.id)}
                                disabled={savingEdit}
                                className="text-emerald-500 hover:text-emerald-600 disabled:opacity-40"
                              >
                                <Check size={15} />
                              </button>
                              <button onClick={() => setEditingGrupo(null)} className="text-slate-400 hover:text-slate-600">
                                <X size={15} />
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => startEditGrupo(g)}
                                className="text-slate-400 hover:text-brand-500"
                                title={t("diccionario.edit") as string}
                              >
                                <Pencil size={14} />
                              </button>
                              <button
                                onClick={() => borrarGrupo(g)}
                                disabled={deletingGrupo === g.id}
                                className="text-slate-400 hover:text-rose-500 disabled:opacity-40"
                                title={t("diccionario.deleteGrupo") as string}
                              >
                                {deletingGrupo === g.id
                                  ? <Loader2 size={14} className="animate-spin" />
                                  : <Trash2 size={14} />}
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {!loadingG && grupos.length > 0 && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-400">{t("diccionario.totalCount", { count: totalGrupos })}</p>
              {totalPagesG > 1 && (
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => goToPageG(pageG - 1)}
                    disabled={pageG === 0}
                    className="w-7 h-7 flex items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="text-xs text-slate-400">
                    {t("diccionario.pageOf", { page: pageG + 1, total: totalPagesG })}
                  </span>
                  <button
                    onClick={() => goToPageG(pageG + 1)}
                    disabled={pageG + 1 >= totalPagesG}
                    className="w-7 h-7 flex items-center justify-center rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
