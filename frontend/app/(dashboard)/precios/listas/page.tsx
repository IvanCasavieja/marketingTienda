"use client";
import { useEffect, useState } from "react";
import * as XLSX from "xlsx";
import { watchlistApi, type WatchlistConItems } from "@/lib/api";
import { fMoneyByCurrency } from "@/lib/format";
import { CadenaBadge } from "@/components/precios/cadenaConfig";
import CompartirListaModal from "@/components/precios/CompartirListaModal";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import {
  Loader2, Star, Trash2, ExternalLink, ClipboardList, Share2, CalendarClock,
  CheckCircle2, LogOut, Download, Pencil, X, Check,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

type Tab = "mias" | "compartidas" | "finalizadas";

function formatFecha(iso: string | null, locale: string, sinChequear: string): string {
  if (!iso) return sinChequear;
  const d = new Date(iso);
  return d.toLocaleDateString(locale, { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function ListasMonitoreoPage() {
  const { t, i18n } = useTranslation();
  const { user: currentUser } = useCurrentUser();
  const currentUserId = currentUser?.id ?? null;
  const [listas, setListas] = useState<WatchlistConItems[] | null>(null);
  const [tab, setTab] = useState<Tab>("mias");
  const [borrando, setBorrando] = useState<number | null>(null);
  const [compartiendoLista, setCompartiendoLista] = useState<WatchlistConItems | null>(null);
  const [editandoFechaId, setEditandoFechaId] = useState<number | null>(null);
  const [fechaEditada, setFechaEditada] = useState("");
  const [guardandoFecha, setGuardandoFecha] = useState(false);
  const [finalizando, setFinalizando] = useState<number | null>(null);
  const [saliendoDe, setSaliendoDe] = useState<number | null>(null);
  const [exportando, setExportando] = useState<number | null>(null);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    try {
      const { data } = await watchlistApi.listar();
      setListas(data);
    } catch {
      toast.error(t("precios.listas.loadError"));
      setListas([]);
    }
  }

  async function eliminarLista(id: number) {
    setBorrando(id);
    try {
      await watchlistApi.eliminar(id);
      setListas((prev) => prev?.filter((l) => l.id !== id) ?? null);
      toast.success(t("precios.listas.listDeleted"));
    } catch {
      toast.error(t("precios.listas.listDeleteError"));
    } finally {
      setBorrando(null);
    }
  }

  async function eliminarItem(watchlistId: number, itemId: number) {
    try {
      await watchlistApi.eliminarItem(itemId);
      setListas((prev) =>
        prev?.map((l) =>
          l.id === watchlistId ? { ...l, items: l.items.filter((it) => it.id !== itemId) } : l
        ) ?? null
      );
    } catch {
      toast.error(t("precios.listas.itemDeleteError"));
    }
  }

  async function finalizarAhora(id: number) {
    setFinalizando(id);
    try {
      await watchlistApi.actualizar(id, { estado: "finalizada" });
      setListas((prev) => prev?.map((l) => (l.id === id ? { ...l, estado: "finalizada" } : l)) ?? null);
      toast.success(t("precios.listas.finalized"));
    } catch {
      toast.error(t("precios.listas.finalizeError"));
    } finally {
      setFinalizando(null);
    }
  }

  async function salirDeCompartida(id: number) {
    if (currentUserId === null) return;
    setSaliendoDe(id);
    try {
      await watchlistApi.dejarDeCompartir(id, currentUserId);
      setListas((prev) => prev?.filter((l) => l.id !== id) ?? null);
    } catch {
      toast.error(t("precios.listas.compartir.removeError"));
    } finally {
      setSaliendoDe(null);
    }
  }

  function abrirEdicionFecha(lista: WatchlistConItems) {
    setEditandoFechaId(lista.id);
    setFechaEditada(lista.fecha_fin ?? "");
  }

  async function guardarFecha(id: number) {
    setGuardandoFecha(true);
    try {
      await watchlistApi.actualizar(id, { fecha_fin: fechaEditada || null });
      setListas((prev) => prev?.map((l) => (l.id === id ? { ...l, fecha_fin: fechaEditada || null } : l)) ?? null);
      setEditandoFechaId(null);
      toast.success(t("precios.listas.durationSaved"));
    } catch {
      toast.error(t("precios.listas.durationSaveError"));
    } finally {
      setGuardandoFecha(false);
    }
  }

  async function exportarHistorial(lista: WatchlistConItems) {
    setExportando(lista.id);
    try {
      const { data } = await watchlistApi.historial(lista.id);
      const rows = data.map((h) => ({
        [t("precios.listas.historialCols.producto")]: h.producto,
        [t("precios.listas.historialCols.tienda")]: h.tienda,
        [t("precios.listas.historialCols.precio")]: h.precio,
        [t("precios.listas.historialCols.moneda")]: h.moneda,
        [t("precios.listas.historialCols.fecha")]: formatFecha(h.checked_at, i18n.language, ""),
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      ws["!cols"] = [{ wch: 32 }, { wch: 14 }, { wch: 12 }, { wch: 10 }, { wch: 14 }];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, "Historial");
      const nombreArchivo = lista.nombre.trim().replace(/[^a-zA-Z0-9]+/g, "_").slice(0, 40) || "lista";
      XLSX.writeFile(wb, `historial_${nombreArchivo}.xlsx`);
    } catch {
      toast.error(t("precios.listas.exportError"));
    } finally {
      setExportando(null);
    }
  }

  if (listas === null) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={22} className="animate-spin text-slate-400" />
      </div>
    );
  }

  const mias = listas.filter((l) => l.es_propia && l.estado === "activa");
  const compartidas = listas.filter((l) => !l.es_propia && l.estado === "activa");
  const finalizadas = listas
    .filter((l) => l.estado === "finalizada")
    .sort((a, b) => (b.fecha_fin ?? b.created_at ?? "").localeCompare(a.fecha_fin ?? a.created_at ?? ""));

  const visibles = tab === "mias" ? mias : tab === "compartidas" ? compartidas : finalizadas;

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "mias", label: t("precios.listas.tabMine"), count: mias.length },
    { id: "compartidas", label: t("precios.listas.tabShared"), count: compartidas.length },
    { id: "finalizadas", label: t("precios.listas.tabFinished"), count: finalizadas.length },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("sidebar.listasMonitoreo")}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
          {t("precios.listas.subtitle")}
        </p>
      </div>

      <div className="flex items-center gap-1 border-b border-slate-200 dark:border-slate-800">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={`px-3.5 py-2 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
              tab === tb.id
                ? "border-brand-600 text-brand-600 dark:text-brand-400"
                : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            }`}
          >
            {tb.label}
            {tb.count > 0 && (
              <span
                className={`text-[10.5px] px-1.5 py-0.5 rounded-full ${
                  tab === tb.id
                    ? "bg-brand-600/15 text-brand-600 dark:text-brand-400"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
                }`}
              >
                {tb.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {visibles.length === 0 && tab === "mias" && (
        <div className="card p-10 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-brand-600/10 flex items-center justify-center">
            <Star size={22} className="text-brand-600" />
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm">
            {t("precios.listas.emptyStart")}{" "}
            <a href="/precios" className="text-brand-600 hover:underline">{t("sidebar.buscarPrecios")}</a>
            {t("precios.listas.emptyEnd")}
          </p>
        </div>
      )}
      {visibles.length === 0 && tab === "compartidas" && (
        <div className="card p-10 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-brand-600/10 flex items-center justify-center">
            <Share2 size={20} className="text-brand-600" />
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm">{t("precios.listas.emptyShared")}</p>
        </div>
      )}
      {visibles.length === 0 && tab === "finalizadas" && (
        <div className="card p-10 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-brand-600/10 flex items-center justify-center">
            <CheckCircle2 size={20} className="text-brand-600" />
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm">{t("precios.listas.emptyFinished")}</p>
        </div>
      )}

      {visibles.map((lista) => (
        <div key={lista.id} className="card overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex-wrap">
            <ClipboardList size={15} className="text-brand-500 shrink-0" />
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{lista.nombre}</p>
            <span className="text-xs text-slate-400 shrink-0">{t("precios.listas.productCount", { count: lista.items.length })}</span>

            {!lista.es_propia && lista.compartida_por && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-600 dark:text-violet-300 shrink-0 flex items-center gap-1">
                <Share2 size={10} />
                {t("precios.listas.sharedBy", { name: lista.compartida_por })}
              </span>
            )}

            {lista.estado === "finalizada" && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-500/15 text-slate-600 dark:text-slate-300 shrink-0">
                {t("precios.listas.finishedBadge")}
              </span>
            )}

            {editandoFechaId === lista.id ? (
              <div className="flex items-center gap-1 shrink-0">
                <input
                  type="date"
                  value={fechaEditada}
                  onChange={(e) => setFechaEditada(e.target.value)}
                  className="input text-xs py-1 px-2"
                />
                <button
                  onClick={() => guardarFecha(lista.id)}
                  disabled={guardandoFecha}
                  className="text-emerald-500 hover:text-emerald-600 disabled:opacity-40"
                  title={t("precios.listas.saveDuration")}
                >
                  {guardandoFecha ? <Loader2 size={13} className="animate-spin" /> : <Check size={14} />}
                </button>
                <button onClick={() => setEditandoFechaId(null)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                  <X size={14} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => lista.es_propia && lista.estado === "activa" && abrirEdicionFecha(lista)}
                className={`text-[11px] px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-600 dark:text-sky-300 shrink-0 flex items-center gap-1 ${
                  lista.es_propia && lista.estado === "activa" ? "hover:bg-sky-500/25 cursor-pointer" : "cursor-default"
                }`}
                title={lista.es_propia && lista.estado === "activa" ? t("precios.listas.editDuration") : undefined}
              >
                <CalendarClock size={10} />
                {lista.fecha_fin
                  ? t("precios.listas.durationUntil", { date: formatFecha(lista.fecha_fin, i18n.language, "") })
                  : t("precios.listas.durationUnlimited")}
                {lista.es_propia && lista.estado === "activa" && <Pencil size={9} className="opacity-60" />}
              </button>
            )}

            <div className="flex-1" />

            {lista.estado === "finalizada" && (
              <button
                onClick={() => exportarHistorial(lista)}
                disabled={exportando === lista.id}
                className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-500/25 transition-colors shrink-0 disabled:opacity-40"
              >
                {exportando === lista.id ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                {t("precios.downloadExcel")}
              </button>
            )}

            {lista.es_propia && lista.estado === "activa" && (
              <>
                <button
                  onClick={() => setCompartiendoLista(lista)}
                  className="text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
                  title={t("precios.listas.compartir.title")}
                >
                  <Share2 size={14} />
                </button>
                <button
                  onClick={() => finalizarAhora(lista.id)}
                  disabled={finalizando === lista.id}
                  className="text-slate-400 hover:text-amber-600 dark:hover:text-amber-400 transition-colors shrink-0 disabled:opacity-40"
                  title={t("precios.listas.finalizeNow")}
                >
                  {finalizando === lista.id ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                </button>
              </>
            )}

            {!lista.es_propia && (
              <button
                onClick={() => salirDeCompartida(lista.id)}
                disabled={saliendoDe === lista.id}
                className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors shrink-0 disabled:opacity-40"
                title={t("precios.listas.leaveShared")}
              >
                {saliendoDe === lista.id ? <Loader2 size={14} className="animate-spin" /> : <LogOut size={14} />}
              </button>
            )}

            {lista.es_propia && (
              <button
                onClick={() => eliminarLista(lista.id)}
                disabled={borrando === lista.id}
                className="text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors shrink-0 disabled:opacity-40"
                title={t("precios.listas.deleteList")}
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>

          {lista.items.length === 0 ? (
            <p className="text-xs text-slate-400 text-center py-6">{t("precios.listas.emptyList")}</p>
          ) : (
            <div className="divide-y divide-slate-50 dark:divide-slate-800">
              {lista.items.map((item) => (
                <div key={item.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{item.nombre}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <CadenaBadge tienda={item.tienda} />
                      {item.sucursal_nombre && (
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">{item.sucursal_nombre}</span>
                      )}
                      <span className="text-[11px] text-slate-400">
                        {t("precios.listas.lastCheck")}: {formatFecha(item.ultimo_chequeo, i18n.language, t("precios.listas.neverChecked"))}
                      </span>
                    </div>
                  </div>
                  <span className="text-sm font-bold text-slate-900 dark:text-slate-100 shrink-0">
                    {fMoneyByCurrency(item.precio_actual, item.moneda)}
                  </span>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
                    title={t("precios.viewInStore")}
                  >
                    <ExternalLink size={14} />
                  </a>
                  {lista.es_propia && (
                    <button
                      onClick={() => eliminarItem(lista.id, item.id)}
                      className="text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors shrink-0"
                      title={t("precios.listas.unfollow")}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {compartiendoLista && (
        <CompartirListaModal
          watchlistId={compartiendoLista.id}
          nombre={compartiendoLista.nombre}
          onClose={() => setCompartiendoLista(null)}
        />
      )}
    </div>
  );
}
