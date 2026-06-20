"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { preciosApi, type Producto, type PreciosListResponse } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";
import { Search, ExternalLink, ChevronLeft, ChevronRight, Tag } from "lucide-react";
import { SkeletonRow } from "@/components/ui/SkeletonCard";
import { toast } from "sonner";

const TIENDA_COLORS: Record<string, string> = {
  "Disco":      "bg-blue-500/15 text-blue-300",
  "Devoto":     "bg-green-500/15 text-green-300",
  "Géant":      "bg-purple-500/15 text-purple-300",
  "Ta-Ta":      "bg-red-500/15 text-red-300",
  "Farmashop":  "bg-orange-500/15 text-orange-300",
};

function TiendaBadge({ tienda }: { tienda: string }) {
  const cls = TIENDA_COLORS[tienda] ?? "bg-slate-500/15 text-slate-300";
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full ${cls}`}>
      {tienda}
    </span>
  );
}

function PrecioBadge({ precio, precioLista }: { precio: number | null; precioLista: number | null }) {
  if (precio === null) return <span className="text-slate-600 text-xs">—</span>;
  const hasDesc = precioLista !== null && precioLista > precio;
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="text-sm font-semibold text-slate-100">{fMoneyExact(precio)}</span>
      {hasDesc && (
        <span className="text-[11px] text-slate-500 line-through">{fMoneyExact(precioLista!)}</span>
      )}
    </div>
  );
}

const PAGE_SIZE = 50;

export default function PreciosPage() {
  const [tiendas,    setTiendas]    = useState<string[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [result,     setResult]     = useState<PreciosListResponse | null>(null);
  const [loading,    setLoading]    = useState(true);

  const [q,          setQ]          = useState("");
  const [tienda,     setTienda]     = useState("");
  const [categoria,  setCategoria]  = useState("");
  const [marca,      setMarca]      = useState("");
  const [page,       setPage]       = useState(1);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cargar tiendas disponibles al montar
  useEffect(() => {
    preciosApi.tiendas()
      .then(({ data }) => setTiendas(data))
      .catch(() => {});
  }, []);

  // Actualizar categorías cuando cambia la tienda seleccionada
  useEffect(() => {
    preciosApi.categorias(tienda || undefined)
      .then(({ data }) => setCategorias(data))
      .catch(() => {});
    setCategoria("");
  }, [tienda]);

  const load = useCallback(async (newPage = page) => {
    setLoading(true);
    try {
      const { data } = await preciosApi.list({
        q:         q      || undefined,
        tienda:    tienda || undefined,
        categoria: categoria || undefined,
        marca:     marca  || undefined,
        page:      newPage,
        page_size: PAGE_SIZE,
      });
      setResult(data);
      setPage(newPage);
    } catch {
      toast.error("Error al cargar productos");
    } finally {
      setLoading(false);
    }
  }, [q, tienda, categoria, marca, page]);

  // Debounce de búsqueda de texto
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(1), 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, tienda, categoria, marca]);

  const totalPages = result ? Math.ceil(result.total / PAGE_SIZE) : 1;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div>
        <h1 className="section-title flex items-center gap-2">
          <Tag size={20} className="text-brand-400" />
          Catálogo de precios
        </h1>
        <p className="section-sub mt-0.5">
          {result ? `${result.total.toLocaleString("es-UY")} productos de supermercados uruguayos` : "Cargando…"}
        </p>
      </div>

      {/* Filtros */}
      <div className="card flex flex-wrap gap-3">
        {/* Búsqueda */}
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por nombre, SKU, código de barras..."
            className="input pl-8 w-full text-sm"
          />
        </div>

        {/* Tienda */}
        <select
          value={tienda}
          onChange={(e) => { setTienda(e.target.value); setPage(1); }}
          className="input text-sm min-w-[140px]"
        >
          <option value="">Todas las tiendas</option>
          {tiendas.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        {/* Categoría */}
        <select
          value={categoria}
          onChange={(e) => { setCategoria(e.target.value); setPage(1); }}
          className="input text-sm min-w-[200px]"
          disabled={categorias.length === 0}
        >
          <option value="">Todas las categorías</option>
          {categorias.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        {/* Marca */}
        <input
          value={marca}
          onChange={(e) => setMarca(e.target.value)}
          placeholder="Filtrar por marca..."
          className="input text-sm min-w-[160px]"
        />
      </div>

      {/* Tabla */}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-slate-500 text-xs uppercase tracking-wider">
              <th className="text-left px-4 py-3 font-medium">Producto</th>
              <th className="text-left px-4 py-3 font-medium hidden md:table-cell">Marca</th>
              <th className="text-left px-4 py-3 font-medium hidden lg:table-cell">Categoría</th>
              <th className="text-left px-4 py-3 font-medium">Tienda</th>
              <th className="text-right px-4 py-3 font-medium">Precio</th>
              <th className="px-4 py-3 w-8"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-4 py-3"><SkeletonRow /></td>
                  </tr>
                ))
              : (result?.items ?? []).map((p: Producto) => (
                  <tr key={p.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-200 leading-tight max-w-xs truncate">
                        {p.nombre ?? "—"}
                      </div>
                      {p.sku && (
                        <div className="text-[11px] text-slate-600 mt-0.5">SKU {p.sku}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-400 hidden md:table-cell">
                      {p.marca ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs hidden lg:table-cell max-w-[180px] truncate">
                      {p.categoria ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <TiendaBadge tienda={p.tienda} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <PrecioBadge precio={p.precio} precioLista={p.precio_lista} />
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-600 hover:text-brand-400 transition-colors"
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
                <td colSpan={6} className="px-4 py-12 text-center text-slate-600">
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
              className="btn-ghost p-1 disabled:opacity-30"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="px-3 text-slate-400">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => load(page + 1)}
              disabled={page >= totalPages || loading}
              className="btn-ghost p-1 disabled:opacity-30"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
