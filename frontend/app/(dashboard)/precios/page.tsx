"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { preciosApi, type Producto, type PreciosListResponse, type TiendaStats } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";
import { Search, ExternalLink, ChevronLeft, ChevronRight, Tag, Scale, ArrowUpDown, ArrowUp, ArrowDown, GitCompare, Download, RefreshCw, Clock, History, X } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

const TIENDA_COLORS: Record<string, string> = {
  "Disco":           "bg-blue-50 text-blue-700",
  "Devoto":          "bg-green-50 text-green-700",
  "Géant":           "bg-purple-50 text-purple-700",
  "Ta-Ta":           "bg-red-50 text-red-700",
  "Farmashop":       "bg-orange-50 text-orange-700",
  "Tienda Inglesa":  "bg-teal-50 text-teal-700",
};

const TIENDA_BADGE_DOTS: Record<string, string> = {
  "Disco":           "bg-blue-500",
  "Devoto":          "bg-green-500",
  "Géant":           "bg-purple-500",
  "Ta-Ta":           "bg-red-500",
  "Farmashop":       "bg-orange-500",
  "Tienda Inglesa":  "bg-teal-500",
};

type ProgressData = {
  running:   boolean;
  scan_type: "full" | "gdu" | null;
  gdu: { completados: number; total: number; guardados: number; pct: number };
};

function TiendaBadge({ tienda }: { tienda: string }) {
  const cls = TIENDA_COLORS[tienda] ?? "bg-slate-100 text-slate-600";
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full ${cls}`}>
      {tienda}
    </span>
  );
}

function PrecioBadge({ precio, precioLista }: { precio: number | null; precioLista: number | null }) {
  if (precio === null) return <span className="text-slate-400 text-xs">—</span>;
  const hasDesc = precioLista !== null && precioLista > precio;
  const pct = hasDesc ? Math.round((1 - precio / precioLista!) * 100) : 0;
  return (
    <div className="flex flex-col items-end gap-0.5">
      <div className="flex items-center gap-1.5">
        {hasDesc && (
          <span className="text-[10px] font-bold bg-red-50 text-red-600 px-1.5 py-0.5 rounded-full">
            -{pct}%
          </span>
        )}
        <span className="text-sm font-semibold text-slate-800">{fMoneyExact(precio)}</span>
      </div>
      {hasDesc && (
        <span className="text-[11px] text-slate-400 line-through">{fMoneyExact(precioLista!)}</span>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-b border-slate-50 animate-pulse">
      {[55, 30, 25, 15, 10].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className={`h-3 bg-slate-100 rounded w-${w < 20 ? "[60px]" : "[140px]"}`} />
        </td>
      ))}
      <td className="px-4 py-3" />
    </tr>
  );
}

const PAGE_SIZE = 50;

export default function PreciosPage() {
  const [tiendas,    setTiendas]    = useState<string[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [result,     setResult]     = useState<PreciosListResponse | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [stats,        setStats]        = useState<TiendaStats[] | null>(null);
  const [scraperInfo,  setScraperInfo]  = useState<{ status: string; last_run: string | null; next_run: string | null; last_total: number | null } | null>(null);
  const [triggering,    setTriggering]    = useState(false);
  const [triggeringGdu, setTriggeringGdu] = useState(false);
  const [progress,      setProgress]      = useState<ProgressData | null>(null);

  const [q,            setQ]           = useState("");
  const [tienda,       setTienda]      = useState("");
  const [categoria,    setCategoria]   = useState("");
  const [marca,        setMarca]       = useState("");
  const [conDescuento, setConDescuento] = useState(false);
  const [sortBy,       setSortBy]      = useState("nombre");
  const [sortDir,      setSortDir]     = useState<"asc" | "desc">("asc");
  const [page,         setPage]        = useState(1);

  const debounceRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevRunning   = useRef<boolean>(false);

  const refreshStats = useCallback(() => {
    preciosApi.estadisticas().then(({ data }) => setStats(data.tiendas)).catch(() => {});
    preciosApi.scraperStatus().then(({ data }) => setScraperInfo(data)).catch(() => {});
  }, []);

  useEffect(() => {
    preciosApi.tiendas().then(({ data }) => setTiendas(data)).catch(() => {});
    refreshStats();
    preciosApi.scraperProgress().then(({ data }) => setProgress(data)).catch(() => {});
    preciosApi.historialFechas().then(({ data }) => setFechasHistorial(data)).catch(() => {});
  }, [refreshStats]);

  // Polling — activo solo mientras el scan está corriendo
  useEffect(() => {
    if (!progress?.running) return;

    const interval = setInterval(async () => {
      try {
        const { data } = await preciosApi.scraperProgress();
        setProgress(data);

        if (!data.running && prevRunning.current) {
          // Scan terminó — refrescar todo
          refreshStats();
          load(1);
          const guardados = data.gdu.guardados;
          toast.success(
            guardados
              ? `Scan completado — ${guardados.toLocaleString("es-UY")} productos GDU actualizados`
              : "Scan completado"
          );
        }
        prevRunning.current = data.running;
      } catch {}
    }, 3000);

    prevRunning.current = true;
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress?.running]);

  useEffect(() => {
    preciosApi.categorias(tienda || undefined)
      .then(({ data }) => setCategorias(data))
      .catch(() => {});
    setCategoria("");
  }, [tienda]);

  const load = useCallback(async (newPage = 1) => {
    setLoading(true);
    try {
      const { data } = await preciosApi.list({
        q:             q             || undefined,
        tienda:        tienda        || undefined,
        categoria:     categoria     || undefined,
        marca:         marca         || undefined,
        con_descuento: conDescuento  || undefined,
        sort_by:       sortBy,
        sort_dir:      sortDir,
        page:          newPage,
        page_size:     PAGE_SIZE,
      });
      setResult(data);
      setPage(newPage);
    } catch {
      toast.error("Error al cargar productos");
    } finally {
      setLoading(false);
    }
  }, [q, tienda, categoria, marca, conDescuento, sortBy, sortDir]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(1), 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, tienda, categoria, marca, conDescuento, sortBy, sortDir]);

  const [exporting,         setExporting]         = useState(false);
  const [fechasHistorial,   setFechasHistorial]   = useState<string[]>([]);
  const [fechaSeleccionada, setFechaSeleccionada] = useState<string | null>(null);
  const [historialResult,   setHistorialResult]   = useState<{ total: number; page: number; items: Producto[] } | null>(null);
  const [loadingHistorial,  setLoadingHistorial]  = useState(false);

  const scanActive    = progress?.running ?? false;
  const activeResult  = fechaSeleccionada ? historialResult : result;
  const activeLoading = fechaSeleccionada ? loadingHistorial : loading;
  const totalPages    = activeResult ? Math.ceil(activeResult.total / PAGE_SIZE) : 1;

  async function handleTrigger() {
    setTriggering(true);
    try {
      await preciosApi.scraperTrigger();
      toast.success("Scraping completo iniciado — puede tardar hasta 2 horas");
      setTimeout(() => {
        preciosApi.scraperProgress().then(({ data }) => setProgress(data)).catch(() => {});
        refreshStats();
      }, 1500);
    } catch {
      toast.error("Ya hay un scraping en curso");
    } finally {
      setTriggering(false);
    }
  }

  async function handleTriggerGdu() {
    setTriggeringGdu(true);
    try {
      await preciosApi.scraperTriggerGdu();
      toast.success("Scan GDU iniciado — Geant, Disco y Devoto");
      setTimeout(() => {
        preciosApi.scraperProgress().then(({ data }) => setProgress(data)).catch(() => {});
        refreshStats();
      }, 1500);
    } catch {
      toast.error("Ya hay un scraping en curso");
    } finally {
      setTriggeringGdu(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const { data } = await preciosApi.exportCsv({
        q:             q             || undefined,
        tienda:        tienda        || undefined,
        categoria:     categoria     || undefined,
        marca:         marca         || undefined,
        con_descuento: conDescuento  || undefined,
        limit:         10000,
      });
      const url = URL.createObjectURL(data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `precios_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Error al exportar CSV");
    } finally {
      setExporting(false);
    }
  }

  const loadHistorial = useCallback(async (fecha: string, newPage = 1) => {
    setLoadingHistorial(true);
    try {
      const { data } = await preciosApi.historial({
        fecha,
        q:             q             || undefined,
        tienda:        tienda        || undefined,
        categoria:     categoria     || undefined,
        marca:         marca         || undefined,
        con_descuento: conDescuento  || undefined,
        sort_by:       sortBy,
        sort_dir:      sortDir,
        page:          newPage,
        page_size:     PAGE_SIZE,
      });
      setHistorialResult({ total: data.total, page: data.page, items: data.items });
      setPage(newPage);
    } catch {
      toast.error("Error al cargar historial");
    } finally {
      setLoadingHistorial(false);
    }
  }, [q, tienda, categoria, marca, conDescuento, sortBy, sortDir]);

  useEffect(() => {
    if (!fechaSeleccionada) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => loadHistorial(fechaSeleccionada, 1), 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [fechaSeleccionada, q, tienda, categoria, marca, conDescuento, sortBy, sortDir, loadHistorial]);

  function handleFechaSelect(fecha: string) {
    setFechaSeleccionada(fecha);
    setPage(1);
    setHistorialResult(null);
  }

  function handleSalirHistorial() {
    setFechaSeleccionada(null);
    setHistorialResult(null);
    load(1);
  }

  function handleSort(col: string) {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      setSortDir("asc");
    }
    setPage(1);
  }

  function SortIcon({ col }: { col: string }) {
    if (sortBy !== col) return <ArrowUpDown size={11} className="opacity-30" />;
    return sortDir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />;
  }

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="section-title flex items-center gap-2">
            <Tag size={17} className="text-brand-600" />
            Catálogo de precios
          </h1>
          <p className="section-sub mt-0.5">
            {result
              ? `${result.total.toLocaleString("es-UY")} productos de supermercados uruguayos`
              : "Cargando…"}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleExport}
            disabled={exporting}
            className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-50"
          >
            <Download size={13} />
            {exporting ? "Exportando…" : "CSV"}
          </button>
          <Link href="/precios/comparar" className="btn-secondary text-xs px-3 py-1.5">
            <Scale size={13} />
            Comparar
          </Link>
        </div>
      </div>

      {/* Scraper status */}
      {scraperInfo && (
        <div className="card px-4 py-3 space-y-2.5">
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <div className={`w-2 h-2 rounded-full shrink-0 ${
              (scanActive || scraperInfo.status === "running") ? "bg-amber-400 animate-pulse" :
              scraperInfo.status.startsWith("error") ? "bg-red-400" : "bg-emerald-400"
            }`} />
            <span className="font-medium text-slate-700">
              {scanActive ? (
                progress?.scan_type === "gdu"
                  ? "Escaneando GDU…"
                  : "Scraping en curso…"
              ) : "Scraper"}
            </span>
            {scraperInfo.last_run && !scanActive && (
              <span className="flex items-center gap-1">
                <Clock size={11} />
                Último: {new Date(scraperInfo.last_run).toLocaleString("es-UY")}
                {scraperInfo.last_total && ` · ${scraperInfo.last_total.toLocaleString("es-UY")} productos`}
              </span>
            )}
            {scraperInfo.next_run && !scanActive && scraperInfo.status !== "running" && (
              <span className="text-slate-400">
                Próximo: {new Date(scraperInfo.next_run).toLocaleString("es-UY")}
              </span>
            )}
            <div className="ml-auto flex items-center gap-1">
              <button
                onClick={handleTriggerGdu}
                disabled={triggeringGdu || scanActive || scraperInfo.status === "running"}
                className="btn-ghost text-[11px] px-2 py-1 flex items-center gap-1 disabled:opacity-40"
                title="Escanear solo Geant, Disco y Devoto"
              >
                <RefreshCw size={11} className={triggeringGdu ? "animate-spin" : ""} />
                Solo GDU
              </button>
              <button
                onClick={handleTrigger}
                disabled={triggering || scanActive || scraperInfo.status === "running"}
                className="btn-ghost text-[11px] px-2 py-1 flex items-center gap-1 disabled:opacity-40"
                title="Iniciar scraping completo de todas las tiendas"
              >
                <RefreshCw size={11} className={triggering ? "animate-spin" : ""} />
                Escanear todo
              </button>
            </div>
          </div>

          {/* Barra de progreso — visible cuando hay un scan activo */}
          {scanActive && progress && (
            <div className="space-y-1.5 pt-0.5">
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>
                  {progress.scan_type === "gdu"
                    ? "Geant · Disco · Devoto"
                    : "Todas las tiendas"}
                  {" — "}
                  <span className="tabular-nums">
                    {progress.gdu.completados.toLocaleString("es-UY")}
                  </span>
                  {" de "}
                  <span className="tabular-nums">
                    {progress.gdu.total.toLocaleString("es-UY")}
                  </span>
                  {" categorías "}
                  <span className="text-slate-400">({progress.gdu.pct}%)</span>
                </span>
                <span className="font-medium text-slate-700 tabular-nums">
                  {progress.gdu.guardados.toLocaleString("es-UY")} productos encontrados
                </span>
              </div>
              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-500 rounded-full transition-all duration-700"
                  style={{ width: `${Math.max(progress.gdu.pct, 0.5)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Stats por tienda */}
      {stats && (
        <div className="flex flex-wrap gap-2">
          {stats.map((s) => (
            <div key={s.tienda} className="card px-3 py-2 flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full shrink-0 ${
                  TIENDA_BADGE_DOTS[s.tienda] ?? "bg-slate-400"
                }`}
              />
              <span className="text-xs font-medium text-slate-700">{s.tienda}</span>
              <span className="text-xs text-slate-400">{s.total.toLocaleString("es-UY")}</span>
              {s.con_descuento > 0 && (
                <span className="text-[10px] bg-red-50 text-red-500 px-1.5 py-0.5 rounded-full">
                  {s.con_descuento} ofertas
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Historial de fechas */}
      {fechasHistorial.length > 0 && (
        <div className="card px-4 py-3 flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600 shrink-0">
            <History size={13} />
            Historial
          </div>
          <div className="flex flex-wrap gap-1.5 flex-1">
            {fechasHistorial.map((f) => {
              const label = new Date(f + "T12:00:00").toLocaleDateString("es-UY", { day: "2-digit", month: "short", year: "numeric" });
              const activa = fechaSeleccionada === f;
              return (
                <button
                  key={f}
                  onClick={() => activa ? handleSalirHistorial() : handleFechaSelect(f)}
                  className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${
                    activa
                      ? "bg-brand-600 text-white border-brand-600"
                      : "bg-white text-slate-600 border-slate-200 hover:border-brand-400 hover:text-brand-600"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          {fechaSeleccionada && (
            <button
              onClick={handleSalirHistorial}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 shrink-0"
            >
              <X size={12} /> Ver actual
            </button>
          )}
        </div>
      )}

      {/* Banner snapshot activo */}
      {fechaSeleccionada && (
        <div className="flex items-center gap-2 px-4 py-2 bg-brand-50 border border-brand-200 rounded-xl text-sm text-brand-700">
          <History size={14} />
          <span>
            Viendo snapshot del{" "}
            <strong>
              {new Date(fechaSeleccionada + "T12:00:00").toLocaleDateString("es-UY", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
            </strong>
            {historialResult && ` — ${historialResult.total.toLocaleString("es-UY")} productos`}
          </span>
        </div>
      )}

      {/* Filtros */}
      <div className="card p-4 flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por nombre, SKU, código de barras…"
            className="input pl-8 text-sm"
          />
        </div>

        <select
          value={tienda}
          onChange={(e) => { setTienda(e.target.value); setPage(1); }}
          className="input text-sm min-w-[140px] w-auto"
        >
          <option value="">Todas las tiendas</option>
          {tiendas.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        <select
          value={categoria}
          onChange={(e) => { setCategoria(e.target.value); setPage(1); }}
          className="input text-sm min-w-[200px] w-auto"
          disabled={categorias.length === 0}
        >
          <option value="">Todas las categorías</option>
          {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>

        <input
          value={marca}
          onChange={(e) => setMarca(e.target.value)}
          placeholder="Marca…"
          className="input text-sm min-w-[140px] w-auto"
        />

        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none whitespace-nowrap">
          <input
            type="checkbox"
            checked={conDescuento}
            onChange={(e) => { setConDescuento(e.target.checked); setPage(1); }}
            className="w-4 h-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
          />
          Solo ofertas
        </label>
      </div>

      {/* Tabla */}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50">
              <th className="table-th cursor-pointer hover:text-slate-700" onClick={() => handleSort("nombre")}>
                <span className="flex items-center gap-1">Producto <SortIcon col="nombre" /></span>
              </th>
              <th className="table-th hidden md:table-cell">Marca</th>
              <th className="table-th hidden lg:table-cell cursor-pointer hover:text-slate-700" onClick={() => handleSort("categoria")}>
                <span className="flex items-center gap-1">Categoría <SortIcon col="categoria" /></span>
              </th>
              <th className="table-th cursor-pointer hover:text-slate-700" onClick={() => handleSort("tienda")}>
                <span className="flex items-center gap-1">Tienda <SortIcon col="tienda" /></span>
              </th>
              <th className="table-th text-right cursor-pointer hover:text-slate-700" onClick={() => handleSort("precio")}>
                <span className="flex items-center justify-end gap-1">Precio <SortIcon col="precio" /></span>
              </th>
              <th className="table-th w-8" />
            </tr>
          </thead>
          <tbody>
            {activeLoading
              ? Array.from({ length: 10 }).map((_, i) => <SkeletonRow key={i} />)
              : (activeResult?.items ?? []).map((p: Producto) => (
                  <tr key={p.id} className="table-tr">
                    <td className="table-td">
                      <div className="font-medium text-slate-800 leading-tight max-w-xs truncate">
                        {p.nombre ?? "—"}
                      </div>
                      {p.sku && (
                        <div className="text-[11px] text-slate-400 mt-0.5">SKU {p.sku}</div>
                      )}
                    </td>
                    <td className="table-td text-slate-600 hidden md:table-cell">
                      {p.marca ?? "—"}
                    </td>
                    <td className="table-td text-slate-500 text-xs hidden lg:table-cell max-w-[200px] truncate">
                      {p.categoria ?? "—"}
                    </td>
                    <td className="table-td">
                      <TiendaBadge tienda={p.tienda} />
                    </td>
                    <td className="table-td text-right">
                      <PrecioBadge precio={p.precio} precioLista={p.precio_lista} />
                    </td>
                    <td className="table-td">
                      <div className="flex items-center gap-2">
                        {p.barcode && (
                          <Link
                            href={`/precios/comparar?barcode=${encodeURIComponent(p.barcode)}`}
                            className="text-slate-300 hover:text-brand-600 transition-colors"
                            title="Comparar en otras tiendas"
                          >
                            <GitCompare size={13} />
                          </Link>
                        )}
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-slate-400 hover:text-brand-600 transition-colors"
                          title="Ver en tienda"
                        >
                          <ExternalLink size={13} />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))
            }
            {!activeLoading && activeResult?.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-400 text-sm">
                  Sin productos para los filtros seleccionados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Paginación */}
      {activeResult && activeResult.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            {((page - 1) * PAGE_SIZE + 1).toLocaleString("es-UY")}–
            {Math.min(page * PAGE_SIZE, activeResult.total).toLocaleString("es-UY")} de{" "}
            {activeResult.total.toLocaleString("es-UY")}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => fechaSeleccionada ? loadHistorial(fechaSeleccionada, page - 1) : load(page - 1)}
              disabled={page <= 1 || activeLoading}
              className="btn-ghost p-1.5 disabled:opacity-30"
            >
              <ChevronLeft size={15} />
            </button>
            <span className="px-3 text-slate-500 tabular-nums">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => fechaSeleccionada ? loadHistorial(fechaSeleccionada, page + 1) : load(page + 1)}
              disabled={page >= totalPages || activeLoading}
              className="btn-ghost p-1.5 disabled:opacity-30"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
