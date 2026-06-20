"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { preciosApi, type Producto, type PreciosListResponse, type TiendaStats } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";
import { Search, ExternalLink, ChevronLeft, ChevronRight, Tag, Scale } from "lucide-react";
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
  const [stats,      setStats]      = useState<TiendaStats[] | null>(null);

  const [q,            setQ]           = useState("");
  const [tienda,       setTienda]      = useState("");
  const [categoria,    setCategoria]   = useState("");
  const [marca,        setMarca]       = useState("");
  const [conDescuento, setConDescuento] = useState(false);
  const [page,         setPage]        = useState(1);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    preciosApi.tiendas().then(({ data }) => setTiendas(data)).catch(() => {});
    preciosApi.estadisticas().then(({ data }) => setStats(data.tiendas)).catch(() => {});
  }, []);

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
  }, [q, tienda, categoria, marca, conDescuento]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(1), 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, tienda, categoria, marca, conDescuento]);

  const totalPages = result ? Math.ceil(result.total / PAGE_SIZE) : 1;

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
        <Link href="/precios/comparar" className="btn-secondary text-xs px-3 py-1.5 shrink-0">
          <Scale size={13} />
          Comparar
        </Link>
      </div>

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
              <th className="table-th">Producto</th>
              <th className="table-th hidden md:table-cell">Marca</th>
              <th className="table-th hidden lg:table-cell">Categoría</th>
              <th className="table-th">Tienda</th>
              <th className="table-th text-right">Precio</th>
              <th className="table-th w-8" />
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => <SkeletonRow key={i} />)
              : (result?.items ?? []).map((p: Producto) => (
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
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-400 hover:text-brand-600 transition-colors"
                        title="Ver en tienda"
                      >
                        <ExternalLink size={13} />
                      </a>
                    </td>
                  </tr>
                ))
            }
            {!loading && result?.items.length === 0 && (
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
      {result && result.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            {((page - 1) * PAGE_SIZE + 1).toLocaleString("es-UY")}–
            {Math.min(page * PAGE_SIZE, result.total).toLocaleString("es-UY")} de{" "}
            {result.total.toLocaleString("es-UY")}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => load(page - 1)}
              disabled={page <= 1 || loading}
              className="btn-ghost p-1.5 disabled:opacity-30"
            >
              <ChevronLeft size={15} />
            </button>
            <span className="px-3 text-slate-500 tabular-nums">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => load(page + 1)}
              disabled={page >= totalPages || loading}
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
