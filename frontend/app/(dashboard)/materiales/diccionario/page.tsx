"use client";
import { useEffect, useRef, useState } from "react";
import { BookOpen, Search, Pencil, Check, X, Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type SkuDescripcionItem } from "@/lib/api";

// Vista de consulta/búsqueda sobre el catálogo compartido sku_descripciones
// (mismo que alimentan el Convertidor y Tinín) — sin alta manual, las
// entradas nacen de un import del Convertidor o de una corrección puntual.
// Editar acá reusa el mismo PATCH que ya usa el Convertidor.

const PAGE_SIZE = 100;

export default function DiccionarioPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<SkuDescripcionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editingSku, setEditingSku] = useState<string | null>(null);
  const [editDescripcion, setEditDescripcion] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  useEffect(() => {
    load("", 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setPage(0); load(q, 0); }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  function goToPage(newPage: number) {
    setEditingSku(null);
    setPage(newPage);
    load(q, newPage);
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function startEdit(item: SkuDescripcionItem) {
    setEditingSku(item.sku);
    setEditDescripcion(item.descripcion);
  }

  function cancelEdit() {
    setEditingSku(null);
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

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
          <BookOpen size={22} className="text-emerald-400" />
        </div>
        <div>
          <h1 className="section-title">{t("diccionario.title")}</h1>
          <p className="section-sub mt-0.5">{t("diccionario.subtitle")}</p>
        </div>
      </div>

      {/* Búsqueda */}
      <div className="relative max-w-md">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("diccionario.searchPlaceholder")}
          className="w-full text-sm bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl pl-9 pr-3 py-2.5 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
        />
      </div>

      {/* Tabla */}
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
                          <button onClick={cancelEdit} className="text-slate-400 hover:text-slate-600">
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
    </div>
  );
}
