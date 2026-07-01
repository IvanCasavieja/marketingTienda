"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { preciosApi, type ProductoVivo } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";
import { Search, ExternalLink, Loader2, TrendingDown, Store } from "lucide-react";
import { toast } from "sonner";

// ── Colores por cadena ────────────────────────────────────────────────────────

const CADENA_CONFIG: Record<string, { bg: string; dot: string; label: string }> = {
  "Disco":     { bg: "bg-blue-500/10 text-blue-600 dark:text-blue-400",       dot: "bg-blue-500",    label: "Disco" },
  "Devoto":    { bg: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400", dot: "bg-emerald-500", label: "Devoto" },
  "Geant":     { bg: "bg-violet-500/10 text-violet-600 dark:text-violet-400",   dot: "bg-violet-500",  label: "Géant" },
  "Ta-Ta":     { bg: "bg-rose-500/10 text-rose-600 dark:text-rose-400",       dot: "bg-rose-500",    label: "Ta-Ta" },
  "ElDorado":  { bg: "bg-amber-500/10 text-amber-600 dark:text-amber-400",    dot: "bg-amber-500",   label: "El Dorado" },
  "FarmaShop": { bg: "bg-teal-500/10 text-teal-600 dark:text-teal-400",       dot: "bg-teal-500",    label: "FarmaShop" },
  "Botiga":    { bg: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400", dot: "bg-fuchsia-500", label: "Botiga" },
};

function CadenaBadge({ tienda }: { tienda: string }) {
  const cfg = CADENA_CONFIG[tienda];
  if (!cfg) return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">
      {tienda}
    </span>
  );
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full ${cfg.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="animate-pulse flex items-center gap-4 px-5 py-4 border-b border-slate-100 dark:border-slate-800 last:border-0">
      <div className="flex-1 space-y-2">
        <div className="h-3.5 bg-slate-100 dark:bg-slate-800 rounded w-2/3" />
        <div className="h-2.5 bg-slate-100 dark:bg-slate-800 rounded w-1/3" />
      </div>
      <div className="h-3 w-16 bg-slate-100 dark:bg-slate-800 rounded" />
      <div className="h-5 w-14 bg-slate-100 dark:bg-slate-800 rounded-full" />
      <div className="h-4 w-20 bg-slate-100 dark:bg-slate-800 rounded" />
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function PreciosPage() {
  const [q,         setQ]         = useState("");
  const [loading,   setLoading]   = useState(false);
  const [results,   setResults]   = useState<ProductoVivo[] | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [sortDir,   setSortDir]   = useState<"asc" | "desc">("asc");
  const [filterCadena, setFilterCadena] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  const buscar = useCallback(async (term: string) => {
    const t = term.trim();
    if (t.length < 2) return;
    setLoading(true);
    try {
      const { data } = await preciosApi.buscarVivo(t);
      setResults(data.items);
      setLastQuery(t);
      setFilterCadena(null);
    } catch {
      toast.error("Error al buscar");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Cadenas únicas en resultados
  const cadenas = results
    ? [...new Set(results.map((r) => r.tienda))].sort()
    : [];

  // Filtrar + ordenar
  const visible = results
    ? [...results]
        .filter((r) => !filterCadena || r.tienda === filterCadena)
        .sort((a, b) => {
          const pa = a.precio ?? Infinity;
          const pb = b.precio ?? Infinity;
          return sortDir === "asc" ? pa - pb : pb - pa;
        })
    : [];

  const cheapest = visible.find((r) => r.precio !== null);

  return (
    <div className="min-h-screen p-6 lg:p-10 max-w-4xl mx-auto">

      {/* Hero search */}
      <div className={`transition-all duration-500 ${results !== null || loading ? "mb-6" : "mb-0 mt-20"}`}>
        <div className={`text-center transition-all duration-500 ${results !== null || loading ? "mb-4" : "mb-8"}`}>
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-brand-600/10 mb-4">
            <Search size={22} className="text-brand-600" />
          </div>
          <h1 className={`font-bold text-slate-900 dark:text-slate-100 transition-all duration-500 ${
            results !== null || loading ? "text-xl" : "text-3xl"
          }`}>
            Buscar precios en vivo
          </h1>
          {!(results !== null || loading) && (
            <p className="text-slate-500 dark:text-slate-400 mt-2 text-sm">
              Ta-Ta · El Dorado · Disco · Devoto · Géant · FarmaShop · Botiga — en tiempo real
            </p>
          )}
        </div>

        {/* Input */}
        <form onSubmit={(e) => { e.preventDefault(); buscar(q); }} className="relative group">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-500 transition-colors" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ej: arroz 5kg, leche entera, jabón dove… (Enter para buscar)"
            className="w-full pl-11 pr-32 py-3.5 text-base rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500 shadow-sm transition-all"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || q.trim().length < 2}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-2 rounded-xl bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-2"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {loading ? "Buscando…" : "Buscar"}
          </button>
        </form>
      </div>

      {/* Estado vacío */}
      {!loading && results === null && q.length < 2 && (
        <div className="mt-16 text-center space-y-6">
          <div className="grid grid-cols-3 gap-3 max-w-sm mx-auto">
            {Object.entries(CADENA_CONFIG).map(([key, cfg]) => (
              <div key={key} className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium ${cfg.bg}`}>
                <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
                {cfg.label}
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400">134+ sucursales consultadas en tiempo real</p>
        </div>
      )}

      {/* Skeleton */}
      {loading && (
        <div className="card p-0 overflow-hidden">
          {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {/* Resultados */}
      {!loading && results !== null && (
        <div className="space-y-4">

          {/* Barra de control */}
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              {/* Filtro por cadena */}
              <button
                onClick={() => setFilterCadena(null)}
                className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all ${
                  !filterCadena
                    ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                }`}
              >
                Todas ({results.length})
              </button>
              {cadenas.map((c) => {
                const n = results.filter((r) => r.tienda === c).length;
                const cfg = CADENA_CONFIG[c];
                return (
                  <button
                    key={c}
                    onClick={() => setFilterCadena(filterCadena === c ? null : c)}
                    className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full font-medium transition-all ${
                      filterCadena === c
                        ? `${cfg?.dot ?? "bg-slate-500"} text-white`
                        : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                    }`}
                  >
                    {cfg?.label ?? c} · {n}
                  </button>
                );
              })}
            </div>

            {/* Sort por precio */}
            <button
              onClick={() => setSortDir((d) => d === "asc" ? "desc" : "asc")}
              className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
            >
              <TrendingDown size={13} className={sortDir === "desc" ? "rotate-180 transition-transform" : "transition-transform"} />
              Precio {sortDir === "asc" ? "↑ menor primero" : "↓ mayor primero"}
            </button>
          </div>

          {/* Resumen */}
          {cheapest && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-100 dark:border-emerald-900 text-sm">
              <Store size={14} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span className="text-emerald-700 dark:text-emerald-400">
                Más barato: <strong>{cheapest.nombre}</strong> en <strong>{CADENA_CONFIG[cheapest.tienda]?.label ?? cheapest.tienda}</strong>{" "}
                {cheapest.sucursal_nombre && `(${cheapest.sucursal_nombre})`} —{" "}
                <strong>{fMoneyExact(cheapest.precio!)}</strong>
              </span>
            </div>
          )}

          {visible.length === 0 ? (
            <div className="text-center py-16 text-slate-400 space-y-2">
              <Search size={32} className="mx-auto opacity-20" />
              <p className="text-sm">Sin resultados para <em>"{lastQuery}"</em></p>
              <p className="text-xs text-slate-300 dark:text-slate-600">
                Probá con menos palabras, ej: "arroz saman" en vez de "arroz saman parboiled 5kg"
              </p>
            </div>
          ) : (
            <div className="card p-0 overflow-hidden divide-y divide-slate-50 dark:divide-slate-800/60">
              {visible.map((p, i) => {
                const hasDesc = p.precio_lista !== null && p.precio_lista > (p.precio ?? 0);
                const pct     = hasDesc ? Math.round((1 - (p.precio ?? 0) / p.precio_lista!) * 100) : 0;
                const isCheap = p === cheapest && !filterCadena;
                return (
                  <div
                    key={`${p.tienda}-${p.sucursal_id}-${i}`}
                    className={`flex items-center gap-4 px-5 py-3.5 hover:bg-slate-50/60 dark:hover:bg-slate-800/30 transition-colors group ${
                      isCheap ? "bg-emerald-50/40 dark:bg-emerald-950/20" : ""
                    }`}
                  >
                    {/* Nombre + sucursal */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                          {p.nombre ?? "—"}
                        </span>
                        {isCheap && (
                          <span className="shrink-0 text-[9px] font-bold uppercase tracking-wide bg-emerald-500 text-white px-1.5 py-0.5 rounded-full">
                            mejor precio
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <CadenaBadge tienda={p.tienda} />
                        {p.sucursal_nombre && (
                          <span className="text-[11px] text-slate-400 truncate">{p.sucursal_nombre}</span>
                        )}
                      </div>
                    </div>

                    {/* Precio */}
                    <div className="text-right shrink-0">
                      <div className="flex items-center gap-2 justify-end">
                        {hasDesc && (
                          <span className="text-[10px] font-bold bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400 px-1.5 py-0.5 rounded-full">
                            -{pct}%
                          </span>
                        )}
                        <span className="text-base font-bold text-slate-900 dark:text-slate-100">
                          {p.precio !== null ? fMoneyExact(p.precio) : "—"}
                        </span>
                      </div>
                      {hasDesc && (
                        <span className="text-[11px] text-slate-400 line-through">
                          {fMoneyExact(p.precio_lista!)}
                        </span>
                      )}
                    </div>

                    {/* Link */}
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-slate-300 dark:text-slate-600 hover:text-brand-600 dark:hover:text-brand-400 opacity-0 group-hover:opacity-100 transition-all"
                      title="Ver en tienda"
                    >
                      <ExternalLink size={14} />
                    </a>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
