"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { preciosApi, type ProductoVivo } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";
import { Search, ExternalLink, Zap, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const TIENDA_COLORS: Record<string, string> = {
  "Disco":   "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  "Devoto":  "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300",
  "Geant":   "bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  "Ta-Ta":   "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
  "ElDorado":"bg-yellow-50 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300",
};

function TiendaBadge({ tienda }: { tienda: string }) {
  const cls = TIENDA_COLORS[tienda] ?? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
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
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{fMoneyExact(precio)}</span>
      </div>
      {hasDesc && (
        <span className="text-[11px] text-slate-400 line-through">{fMoneyExact(precioLista!)}</span>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-b border-slate-50 dark:border-slate-800 animate-pulse">
      {[50, 20, 15, 20, 15].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded" style={{ width: `${w}%` }} />
        </td>
      ))}
      <td className="px-4 py-3" />
    </tr>
  );
}

export default function PreciosPage() {
  const [q,         setQ]         = useState("");
  const [loading,   setLoading]   = useState(false);
  const [results,   setResults]   = useState<ProductoVivo[] | null>(null);
  const [lastQuery, setLastQuery] = useState("");

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef    = useRef<HTMLInputElement>(null);

  const buscar = useCallback(async (term: string) => {
    if (term.length < 2) { setResults(null); return; }
    setLoading(true);
    try {
      const { data } = await preciosApi.buscarVivo(term);
      setResults(data.items);
      setLastQuery(term);
    } catch {
      toast.error("Error al buscar — revisá la conexión");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => buscar(q), 700);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [q, buscar]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const tiendas = results
    ? [...new Set(results.map((r) => r.tienda))].sort()
    : [];

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto space-y-6">

      {/* Header */}
      <div className="space-y-1">
        <h1 className="section-title flex items-center gap-2">
          <Zap size={17} className="text-brand-600" />
          Buscar producto en vivo
        </h1>
        <p className="section-sub">
          Ta-Ta · El Dorado · Disco · Devoto · Géant — todas las sucursales, en tiempo real
        </p>
      </div>

      {/* Buscador */}
      <div className="relative">
        <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ej: arroz 5kg, leche entera, jabón dove…"
          className="input pl-11 pr-4 py-3 text-base w-full rounded-xl"
        />
        {loading && (
          <RefreshCw size={15} className="absolute right-4 top-1/2 -translate-y-1/2 text-brand-500 animate-spin" />
        )}
      </div>

      {/* Resultados */}
      {q.length < 2 && !results && (
        <div className="text-center py-20 text-slate-400">
          <Search size={36} className="mx-auto mb-3 opacity-20" />
          <p className="text-sm">Escribí al menos 2 caracteres para buscar</p>
        </div>
      )}

      {loading && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <tbody>{Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)}</tbody>
          </table>
        </div>
      )}

      {!loading && results !== null && (
        <>
          {/* Resumen */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm text-slate-500 dark:text-slate-400">
              <span className="font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                {results.length.toLocaleString("es-UY")}
              </span>{" "}
              resultados para <span className="italic">"{lastQuery}"</span>
            </span>
            {tiendas.map((t) => {
              const n = results.filter((r) => r.tienda === t).length;
              return (
                <span key={t} className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 tabular-nums">
                  {t} ({n})
                </span>
              );
            })}
          </div>

          {results.length === 0 ? (
            <div className="text-center py-16 text-slate-400">
              <p className="text-sm">Sin resultados en ninguna cadena para <span className="italic">"{lastQuery}"</span>.</p>
              <p className="text-xs mt-1 text-slate-300 dark:text-slate-600">Probá con menos palabras o sin especificaciones (ej: "arroz saman" en vez de "arroz saman parboiled 5kg").</p>
            </div>
          ) : (
            <div className="card overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
                    <th className="table-th">Producto</th>
                    <th className="table-th hidden md:table-cell">Marca</th>
                    <th className="table-th">Tienda</th>
                    <th className="table-th">Sucursal</th>
                    <th className="table-th text-right">Precio</th>
                    <th className="table-th w-8" />
                  </tr>
                </thead>
                <tbody>
                  {results.map((p, i) => (
                    <tr key={`${p.tienda}-${p.sucursal_id}-${i}`} className="table-tr">
                      <td className="table-td">
                        <div className="font-medium text-slate-800 dark:text-slate-200 leading-tight max-w-xs">
                          {p.nombre ?? "—"}
                        </div>
                        {p.sku && <div className="text-[11px] text-slate-400 mt-0.5">SKU {p.sku}</div>}
                      </td>
                      <td className="table-td text-slate-500 dark:text-slate-400 hidden md:table-cell">
                        {p.marca ?? "—"}
                      </td>
                      <td className="table-td">
                        <TiendaBadge tienda={p.tienda} />
                      </td>
                      <td className="table-td text-xs text-slate-500 dark:text-slate-400">
                        {p.sucursal_nombre ?? "—"}
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
