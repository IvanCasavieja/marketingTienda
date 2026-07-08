"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { preciosApi, type ProductoVivo } from "@/lib/api";
import { fMoneyByCurrency } from "@/lib/format";
import { Search, ExternalLink, Loader2, TrendingDown, Store, AlertTriangle, BarChart3, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import ComparisonModal from "@/components/precios/ComparisonModal";
import { CADENA_CONFIG, CadenaBadge } from "@/components/precios/cadenaConfig";

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="animate-pulse flex items-center gap-4 px-4 py-3 border-b border-slate-100 dark:border-slate-800 last:border-0">
      <div className="flex-1 space-y-1.5">
        <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded w-1/2" />
        <div className="h-2.5 bg-slate-100 dark:bg-slate-800 rounded w-1/4" />
      </div>
      <div className="h-3 w-16 bg-slate-100 dark:bg-slate-800 rounded" />
      <div className="h-4 w-14 bg-slate-100 dark:bg-slate-800 rounded-full" />
      <div className="h-6 w-10 bg-slate-100 dark:bg-slate-800 rounded-lg" />
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function PreciosPage() {
  const [q,            setQ]            = useState("");
  const [loading,      setLoading]      = useState(false);
  const [streaming,    setStreaming]     = useState(false);
  const [results,      setResults]      = useState<ProductoVivo[] | null>(null);
  const [lastQuery,    setLastQuery]    = useState("");
  const [sortMode,       setSortMode]       = useState<"relevancia" | "precio-asc" | "precio-desc">("relevancia");
  const [filterCadenas,  setFilterCadenas]  = useState<Set<string>>(new Set());
  const [filterSucursal, setFilterSucursal] = useState<string | null>(null);
  const [cadenasDone,    setCadenasDone]    = useState<string[]>([]);
  const [cadenaErrors,   setCadenaErrors]   = useState<Record<string, string>>({});
  const [showChart,      setShowChart]      = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const buscar = useCallback(async (term: string) => {
    const t = term.trim();
    if (t.length < 2) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setStreaming(false);
    setResults([]);
    setLastQuery(t);
    setFilterCadenas(new Set());
    setFilterSucursal(null);
    setSortMode("relevancia");
    setCadenasDone([]);
    setCadenaErrors({});

    try {
      const response = await preciosApi.buscarVivoStream(t, ctrl.signal);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader  = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (!payload) continue;
          try {
            const data = JSON.parse(payload);
            if (data.done) {
              setLoading(false);
              setStreaming(false);
            } else if (data.cadena !== undefined) {
              setStreaming(true);
              setLoading(false);
              setCadenasDone((prev) => [...prev, data.cadena]);
              setResults((prev) => [...(prev ?? []), ...(data.items as ProductoVivo[])]);
              if (data.error) {
                setCadenaErrors((prev) => ({ ...prev, [data.cadena]: data.error }));
              }
            }
          } catch { /* línea incompleta */ }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      toast.error("Error al buscar");
      setResults((prev) => prev ?? []);
    } finally {
      setLoading(false);
      setStreaming(false);
    }
  }, []);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const ALL_CADENAS = ["Ta-Ta", "ElDorado", "GDU", "FarmaShop", "Botiga", "Fama", "Stienda", "BlackDog", "CoverCompany", "DIMM", "Electrohogar"];

  // Multi-selección: los chips se van sumando entre sí — solo "Todas" los apaga
  // a todos de una. Vacío = mostrar todas las cadenas.
  function toggleCadena(c: string) {
    setFilterCadenas((prev) => {
      const next = new Set(prev);
      next.has(c) ? next.delete(c) : next.add(c);
      return next;
    });
    setFilterSucursal(null);
  }

  const cadenas = results ? [...new Set(results.map((r) => r.tienda))].sort() : [];

  // Sucursales disponibles según las cadenas activas (solo las que tienen nombre).
  // Agrupadas por cadena — Ta-Ta y El Dorado usan nombres de departamento (ej.
  // "Montevideo", "Maldonado") que se repiten entre sí, así que la clave del filtro
  // es "cadena||nombre" y no el nombre solo, para no mezclar sucursales de cadenas distintas.
  const sucursalKey = (r: ProductoVivo) => `${r.tienda}||${r.sucursal_nombre}`;
  const sucursalesPorCadena = results
    ? (() => {
        const vistos = new Set<string>();
        const lista: { key: string; tienda: string; nombre: string }[] = [];
        for (const r of results) {
          if (!r.sucursal_nombre) continue;
          if (filterCadenas.size > 0 && !filterCadenas.has(r.tienda)) continue;
          const key = sucursalKey(r);
          if (vistos.has(key)) continue;
          vistos.add(key);
          lista.push({ key, tienda: r.tienda, nombre: r.sucursal_nombre });
        }
        lista.sort((a, b) =>
          (CADENA_CONFIG[a.tienda]?.label ?? a.tienda).localeCompare(CADENA_CONFIG[b.tienda]?.label ?? b.tienda) ||
          a.nombre.localeCompare(b.nombre)
        );
        return lista;
      })()
    : [];

  const sucursalGroups: { tienda: string; items: typeof sucursalesPorCadena }[] = [];
  for (const s of sucursalesPorCadena) {
    const grupo = sucursalGroups.find((g) => g.tienda === s.tienda);
    if (grupo) grupo.items.push(s);
    else sucursalGroups.push({ tienda: s.tienda, items: [s] });
  }

  const visible = results
    ? [...results]
        .filter((r) => filterCadenas.size === 0 || filterCadenas.has(r.tienda))
        .filter((r) => !filterSucursal || sucursalKey(r) === filterSucursal)
        .sort((a, b) => {
          if (sortMode === "relevancia") {
            if (b.relevancia !== a.relevancia) return b.relevancia - a.relevancia;
            return (a.precio ?? Infinity) - (b.precio ?? Infinity);
          }
          const pa = a.precio ?? Infinity;
          const pb = b.precio ?? Infinity;
          return sortMode === "precio-asc" ? pa - pb : pb - pa;
        })
    : [];

  // "Más barato" solo compara resultados en la misma moneda que el más relevante —
  // comparar USD contra UYU crudo daría un ganador sin sentido.
  const cheapest = results
    ? (() => {
        const conPrecio = results.filter(r => r.precio !== null);
        if (conPrecio.length === 0) return undefined;
        const monedaRef = [...conPrecio].sort((a, b) => b.relevancia - a.relevancia)[0].moneda;
        return conPrecio
          .filter(r => r.moneda === monedaRef)
          .reduce<ProductoVivo | null>(
            (min, r) => !min || (r.precio ?? Infinity) < (min.precio ?? Infinity) ? r : min, null
          ) ?? undefined;
      })()
    : undefined;
  const hasResults = results !== null && results.length > 0;
  const hasSearched = results !== null; // true aunque haya 0 resultados
  const isActive   = hasSearched || loading || streaming;

  return (
    /* h-full + flex-col hace que la página ocupe exactamente el viewport sin crecer */
    <div className="h-full flex flex-col gap-3 max-w-4xl mx-auto">

      {/* ── Barra de búsqueda ──────────────────────────────────────────────── */}
      <div className={`shrink-0 transition-all duration-500 ${isActive ? "" : "mt-16"}`}>
        {!hasSearched && !loading && !streaming && (
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-brand-600/10 mb-3">
              <Search size={22} className="text-brand-600" />
            </div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">Buscar precios en vivo</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-2 text-sm">
              Supermercados, farmacias y electrodomésticos — en tiempo real
            </p>
          </div>
        )}
        {isActive && (
          <div className="flex items-center gap-3 mb-3">
            <Search size={16} className="text-brand-600 shrink-0" />
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">Buscar precios en vivo</h1>
          </div>
        )}

        <form onSubmit={(e) => { e.preventDefault(); buscar(q); }} className="relative group">
          <Search size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-500 transition-colors" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ej: arroz 5kg, leche entera, jabón dove… (Enter para buscar)"
            className="w-full pl-11 pr-32 py-3 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500 shadow-sm transition-all"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || q.trim().length < 2}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-2"
          >
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            {loading ? "Buscando…" : "Buscar"}
          </button>
        </form>
      </div>

      {/* ── Estado inicial vacío (solo antes de la primera búsqueda) ────────── */}
      {!hasSearched && !loading && !streaming && (
        <div className="mt-10 text-center space-y-5">
          <div className="flex flex-wrap justify-center gap-2 max-w-2xl mx-auto">
            {Object.entries(CADENA_CONFIG).map(([key, cfg]) => (
              <div key={key} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap ${cfg.bg}`}>
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
                {cfg.label}
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400">13 cadenas · 134+ sucursales consultadas en tiempo real</p>
        </div>
      )}

      {/* ── Panel de resultados (ocupa el resto del viewport) ─────────────── */}
      {isActive && (
        <div className="flex-1 min-h-0 flex flex-col gap-2">

          {/* Barra de control */}
          <div className="shrink-0 flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 flex-wrap min-w-0 flex-1">
              <button
                onClick={() => { setFilterCadenas(new Set()); setFilterSucursal(null); }}
                className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all ${
                  filterCadenas.size === 0
                    ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700"
                }`}
              >
                Todas {results && `(${results.length})`}
              </button>
              {cadenas.map((c) => {
                const n   = results!.filter((r) => r.tienda === c).length;
                const cfg = CADENA_CONFIG[c];
                return (
                  <button
                    key={c}
                    onClick={() => toggleCadena(c)}
                    className={`inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full font-medium transition-all ${
                      filterCadenas.has(c)
                        ? `${cfg?.dot ?? "bg-slate-500"} text-white`
                        : "bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700"
                    }`}
                  >
                    {cfg?.label ?? c} · {n}
                  </button>
                );
              })}
              {/* Chips de progreso mientras streamea */}
              {streaming && ALL_CADENAS.filter(c => !cadenasDone.includes(c)).map(c => (
                <span key={c} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400">
                  <Loader2 size={9} className="animate-spin" />
                  {CADENA_CONFIG[c]?.label ?? c}
                </span>
              ))}
              {/* Chips de cadenas con 0 resultados (completaron pero sin productos) */}
              {!streaming && hasSearched && cadenasDone
                .filter(c => !cadenas.includes(c) && !cadenaErrors[c])
                .map(c => (
                  <span key={c} title="Respondió pero sin resultados" className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400">
                    {CADENA_CONFIG[c]?.label ?? c} · 0
                  </span>
                ))}
              {/* Chips de cadenas que nunca respondieron (timeout o corte de conexión) */}
              {!streaming && hasSearched && ALL_CADENAS
                .filter(c => !cadenasDone.includes(c) && !cadenaErrors[c])
                .map(c => (
                  <span key={c} title="Sin respuesta — posible bloqueo geográfico o timeout" className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-300 dark:text-slate-600 line-through cursor-help">
                    {CADENA_CONFIG[c]?.label ?? c}
                  </span>
                ))}
              {/* Chips de error para cadenas que fallaron con excepción */}
              {!streaming && hasSearched && Object.entries(cadenaErrors).map(([c, err]) => (
                <span key={c} title={err} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400 cursor-help">
                  <AlertTriangle size={9} />
                  {CADENA_CONFIG[c]?.label ?? c}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {/* Filtro de sucursal — solo visible cuando hay sucursales disponibles.
                  Agrupado por cadena (optgroup) porque Ta-Ta y El Dorado nombran sus
                  sucursales por departamento y pueden coincidir (ej. "Montevideo" en ambas). */}
              {sucursalesPorCadena.length > 0 && (
                <select
                  value={filterSucursal ?? ""}
                  onChange={(e) => setFilterSucursal(e.target.value || null)}
                  className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition-all max-w-[200px]"
                >
                  <option value="">Todas las sucursales</option>
                  {sucursalGroups.map(({ tienda, items }) => (
                    <optgroup key={tienda} label={CADENA_CONFIG[tienda]?.label ?? tienda}>
                      {items.map((s) => (
                        <option key={s.key} value={s.key}>{s.nombre}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              )}

              <button
                onClick={() => setSortMode(m =>
                  m === "relevancia" ? "precio-asc" : m === "precio-asc" ? "precio-desc" : "relevancia"
                )}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
              >
                <TrendingDown size={13} className={sortMode === "precio-desc" ? "rotate-180 transition-transform" : "transition-transform"} />
                {sortMode === "relevancia" ? "Por relevancia" : sortMode === "precio-asc" ? "Precio: menor primero" : "Precio: mayor primero"}
              </button>

              {hasResults && (
                <button
                  onClick={() => setShowChart(true)}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                >
                  <BarChart3 size={13} />
                  Ver gráfico
                </button>
              )}
            </div>
          </div>

          {/* Banner más barato */}
          {cheapest && (
            <div className="shrink-0 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-100 dark:border-emerald-900 text-sm">
              <Store size={13} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span className="text-emerald-700 dark:text-emerald-400 text-xs">
                Más barato: <strong>{cheapest.nombre}</strong> en{" "}
                <strong>{CADENA_CONFIG[cheapest.tienda]?.label ?? cheapest.tienda}</strong>
                {cheapest.sucursal_nombre && ` (${cheapest.sucursal_nombre})`} —{" "}
                <strong>{fMoneyByCurrency(cheapest.precio!, cheapest.moneda)}</strong>
              </span>
            </div>
          )}

          {/* Contenedor scrolleable */}
          <div className="flex-1 min-h-0 rounded-xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden flex flex-col shadow-sm">

            {/* Skeleton */}
            {loading && (!results || results.length === 0) && (
              <div className="overflow-y-auto flex-1">
                {Array.from({ length: 12 }).map((_, i) => <SkeletonRow key={i} />)}
              </div>
            )}

            {/* Sin resultados */}
            {!loading && !streaming && results !== null && results.length === 0 && (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400 py-16">
                <Search size={28} className="opacity-20" />
                <p className="text-sm">Sin resultados para <em>"{lastQuery}"</em></p>
                {Object.keys(cadenaErrors).length > 0 && (
                  <div className="mt-2 space-y-1 max-w-sm text-left">
                    {Object.entries(cadenaErrors).map(([c, err]) => (
                      <p key={c} className="text-[11px] text-amber-500 flex items-start gap-1">
                        <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                        <span><strong>{CADENA_CONFIG[c]?.label ?? c}</strong>: {err}</span>
                      </p>
                    ))}
                  </div>
                )}
                <p className="text-xs text-slate-300 dark:text-slate-600">
                  Probá con menos palabras, ej: "arroz saman" en vez de "arroz saman parboiled 5kg"
                </p>
              </div>
            )}

            {/* Tabla con header sticky */}
            {hasResults && (
              <>
                {/* Header */}
                <div className="shrink-0 flex items-center px-4 py-2 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-100 dark:border-slate-800 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                  <div className="flex-1">Producto</div>
                  <div className="w-28 text-right mr-3">Precio</div>
                  <div className="w-14 text-center">Ver</div>
                </div>

                {/* Filas */}
                <div className="flex-1 overflow-y-auto divide-y divide-slate-50 dark:divide-slate-800/50">
                  {visible.length === 0 ? (
                    <div className="py-8 text-center text-sm text-slate-400">
                      Ningún resultado de{" "}
                      <em>{[...filterCadenas].map((c) => CADENA_CONFIG[c]?.label ?? c).join(", ")}</em>
                      {" "}para este término.
                    </div>
                  ) : visible.map((p, i) => {
                    const hasDesc = p.precio_lista !== null && p.precio_lista > (p.precio ?? 0);
                    const pct     = hasDesc ? Math.round((1 - (p.precio ?? 0) / p.precio_lista!) * 100) : 0;
                    const isCheap = p === cheapest && filterCadenas.size === 0;
                    const borderCfg = CADENA_CONFIG[p.tienda];

                    return (
                      <div
                        key={`${p.tienda}-${p.sucursal_id}-${i}`}
                        className={`flex items-center gap-3 px-4 py-2.5 border-l-[3px] hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors group ${
                          borderCfg?.border ?? "border-l-slate-200"
                        } ${isCheap ? "bg-emerald-50/50 dark:bg-emerald-950/20" : ""}`}
                      >
                        {/* Nombre + cadena + sucursal */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                              {p.nombre ?? "—"}
                            </span>
                            {isCheap && (
                              <span className="shrink-0 text-[9px] font-bold uppercase tracking-wide bg-emerald-500 text-white px-1.5 py-0.5 rounded-full">
                                mejor precio
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <CadenaBadge tienda={p.tienda} />
                            {p.sucursal_nombre && (
                              <span className="text-[11px] text-slate-400 truncate">{p.sucursal_nombre}</span>
                            )}
                            {p.tienda_real && p.tienda_real !== p.tienda && (
                              <span
                                title={`${CADENA_CONFIG[p.tienda]?.label ?? p.tienda} y ${CADENA_CONFIG[p.tienda_real]?.label ?? p.tienda_real} comparten catálogo — el link te lleva a ${CADENA_CONFIG[p.tienda_real]?.label ?? p.tienda_real}`}
                                className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-600 dark:text-amber-400 shrink-0"
                              >
                                <ArrowRight size={10} />
                                en realidad es de {CADENA_CONFIG[p.tienda_real]?.label ?? p.tienda_real}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Precio */}
                        <div className="text-right shrink-0 w-28">
                          <div className="flex items-center gap-1.5 justify-end">
                            {hasDesc && (
                              <span className="text-[10px] font-bold bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400 px-1.5 py-0.5 rounded-full">
                                -{pct}%
                              </span>
                            )}
                            <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                              {p.precio !== null ? fMoneyByCurrency(p.precio, p.moneda) : "—"}
                            </span>
                          </div>
                          {hasDesc && (
                            <span className="text-[11px] text-slate-400 line-through">{fMoneyByCurrency(p.precio_lista!, p.moneda)}</span>
                          )}
                        </div>

                        {/* Link */}
                        <div className="w-14 flex justify-center">
                          <a
                            href={p.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 hover:border-brand-500 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-all"
                            title="Ver en tienda"
                          >
                            <ExternalLink size={11} />
                            Ver
                          </a>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {showChart && (
        <ComparisonModal items={visible} onClose={() => setShowChart(false)} />
      )}
    </div>
  );
}
