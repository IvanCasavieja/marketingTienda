"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import * as XLSX from "xlsx";
import { preciosApi, type ProductoVivo } from "@/lib/api";
import { fMoneyByCurrency } from "@/lib/format";
import { Search, ExternalLink, Loader2, TrendingDown, Store, AlertTriangle, BarChart3, ArrowRight, ChevronDown, ChevronUp, SlidersHorizontal, Check, Download, X, Filter } from "lucide-react";
import { toast } from "sonner";
import ComparisonModal from "@/components/precios/ComparisonModal";
import { CADENA_CONFIG, CADENA_CATEGORIA, CadenaBadge } from "@/components/precios/cadenaConfig";
import DonTinoFloating from "@/components/DonTinoFloating";
import SeguirButton from "@/components/precios/SeguirButton";
import { WatchlistsProvider } from "@/components/precios/WatchlistsContext";
import { useTranslation } from "react-i18next";

const CATEGORIA_KEYS: Record<string, string> = {
  "Supermercados": "precios.categorias.supermercados",
  "Farmacia":       "precios.categorias.farmacia",
  "Electrónica":    "precios.categorias.electronica",
  "Otros":          "precios.categorias.otros",
};

// Cadenas consultadas por defecto — debe reflejar _CADENAS_DEFAULT en
// backend/app/services/scraper/live_search.py. LOi queda fuera de esta lista
// a propósito (ver comentario junto a sourceCadenas en el componente).
const CADENAS_DEFAULT = ["Ta-Ta", "ElDorado", "GDU", "FarmaShop", "Botiga", "Pigalle", "Fama", "Stienda", "BlackDog", "CoverCompany", "DIMM", "Electrohogar"];
const CADENAS_TODAS    = [...CADENAS_DEFAULT, "LOi"];

// Una fila de la lista de resultados — puede representar varias sucursales
// de la misma cadena agrupadas por tener el mismo precio para el mismo
// producto (ver `visibleGrouped` más abajo). Mismo patrón que ChartBarData
// en ComparisonModal.tsx, aplicado acá a la lista en sí (no a un gráfico).
interface GroupedProducto extends ProductoVivo {
  _sucursales: ProductoVivo[];
}

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
  const { t } = useTranslation();
  const [q,            setQ]            = useState("");
  const [loading,      setLoading]      = useState(false);
  const [streaming,    setStreaming]     = useState(false);
  const [results,      setResults]      = useState<ProductoVivo[] | null>(null);
  const [lastQuery,    setLastQuery]    = useState("");
  const [sortMode,       setSortMode]       = useState<"relevancia" | "precio-asc" | "precio-desc">("relevancia");
  const [filterCadenas,  setFilterCadenas]  = useState<Set<string>>(new Set());
  const [filterSucursal, setFilterSucursal] = useState<string | null>(null);
  // Filtro por nombre(s) exacto(s) de producto — multi-selección, alimentado
  // tanto por el modal de "índice de productos" (click manual) como por Don
  // Tino (onApplySeleccion, cuando el usuario le pide un filtro en lenguaje
  // natural). Independiente de filterCadenas/filterSucursal: se puede
  // combinar con ellos (ej. "este producto, pero solo en Ta-Ta"), los tres
  // entran en el mismo .filter() encadenado de `visible`.
  const [filterNombres,  setFilterNombres]  = useState<Set<string>>(new Set());
  const [showProductIndex, setShowProductIndex] = useState(false);
  const [panelFiltro,    setPanelFiltro]    = useState("");
  // Fila (agrupada) sobre la que se clickeó "×N sucursales" — abre el modal
  // que lista cada sucursal individual con su propio link y botón Seguir.
  const [sucursalesModalRow, setSucursalesModalRow] = useState<GroupedProducto | null>(null);
  const [cadenasDone,    setCadenasDone]    = useState<string[]>([]);
  const [cadenaErrors,   setCadenaErrors]   = useState<Record<string, string>>({});
  const [showChart,      setShowChart]      = useState(false);
  const [showDiagnostico, setShowDiagnostico] = useState(false);

  // Fuentes a consultar EN LA PRÓXIMA búsqueda (se elige antes de buscar, a
  // diferencia de filterCadenas que filtra resultados ya traídos). LOi queda
  // afuera por defecto: es un catálogo general sin relación con la mayoría de
  // los términos que se buscan acá, y consultarlo consume presupuesto de su
  // rate limit documentado (60 req/min) sin necesidad — que la persona lo
  // sume a propósito cuando de verdad busca algo que LOi podría vender.
  const [sourceCadenas, setSourceCadenas] = useState<Set<string>>(new Set(CADENAS_DEFAULT));
  const [queriedCadenas, setQueriedCadenas] = useState<string[]>(CADENAS_DEFAULT);
  const [showFuentes, setShowFuentes] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fuentesRef = useRef<HTMLDivElement>(null);

  const buscar = useCallback(async (term: string) => {
    const termino = term.trim();
    if (termino.length < 2) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setStreaming(false);
    setResults([]);
    setLastQuery(termino);
    setFilterCadenas(new Set());
    setFilterSucursal(null);
    setFilterNombres(new Set());
    setPanelFiltro("");
    setSortMode("relevancia");
    setCadenasDone([]);
    setCadenaErrors({});

    const activas = Array.from(sourceCadenas);
    setQueriedCadenas(activas);

    try {
      const response = await preciosApi.buscarVivoStream(termino, ctrl.signal, activas);
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
      toast.error(t("precios.searchError"));
      setResults((prev) => prev ?? []);
    } finally {
      setLoading(false);
      setStreaming(false);
    }
  }, [sourceCadenas]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Cerrar el panel de fuentes al hacer clic afuera.
  useEffect(() => {
    if (!showFuentes) return;
    const onClick = (e: MouseEvent) => {
      if (fuentesRef.current && !fuentesRef.current.contains(e.target as Node)) {
        setShowFuentes(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [showFuentes]);

  function toggleFuente(c: string) {
    setSourceCadenas((prev) => {
      const next = new Set(prev);
      next.has(c) ? next.delete(c) : next.add(c);
      return next;
    });
  }

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

  // Selección desde el modal de "índice de productos" (nombresUnicos más
  // abajo) — multi-selección, suma/saca nombres del filtro (mismo patrón que
  // toggleCadena). A propósito NO toca filterCadenas/filterSucursal:
  // combinarlos es válido ("estos productos puntuales, pero solo en Ta-Ta").
  function toggleNombre(nombre: string) {
    setFilterNombres((prev) => {
      const next = new Set(prev);
      next.has(nombre) ? next.delete(nombre) : next.add(nombre);
      return next;
    });
  }

  // Conteo por cadena una sola vez — se reusa para ordenar los chips (más
  // resultados primero, mucho más útil que orden alfabético con 13 cadenas) y
  // para pintar el número en cada chip sin recalcular un .filter() por chip.
  const cadenaCounts = results
    ? results.reduce<Record<string, number>>((acc, r) => {
        acc[r.tienda] = (acc[r.tienda] ?? 0) + 1;
        return acc;
      }, {})
    : {};
  const cadenas = results
    ? Object.keys(cadenaCounts).sort((a, b) => cadenaCounts[b] - cadenaCounts[a])
    : [];

  // Agrupadas por rubro — con 11-13 cadenas activas, un solo renglón sin
  // orden temático era imposible de escanear. Orden dentro de cada grupo se
  // mantiene por cantidad (heredado de `cadenas`).
  const CATEGORIA_ORDEN = ["Supermercados", "Farmacia", "Electrónica"];
  const cadenasPorCategoria = [...CATEGORIA_ORDEN, "Otros"]
    .map((categoria) => ({
      categoria,
      items: cadenas.filter((c) => (CADENA_CATEGORIA[c] ?? "Otros") === categoria),
    }))
    .filter((g) => g.items.length > 0);

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
        .filter((r) => filterNombres.size === 0 || (!!r.nombre && filterNombres.has(r.nombre)))
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

  // Agrupa `visible` por (cadena, producto, precio, moneda) para pintar la
  // lista: varias sucursales de la misma cadena con el mismo precio para el
  // mismo producto comparten una sola fila (`_sucursales`), con un botón
  // "×N" que abre un modal listando cada sucursal — mismo patrón que
  // ComparisonModal.tsx aplica al gráfico comparativo, acá aplicado a la
  // lista de resultados en sí (no a un gráfico). Achica listas de cadenas
  // con muchas sucursales (Disco/Devoto/Géant, o cualquiera con datos por
  // sucursal) sin perder ningún dato — cada fila colapsada guarda el detalle
  // completo en `_sucursales` para el modal.
  //
  // Filas sin precio (precio === null) NUNCA se agrupan entre sí — "mismo
  // precio" no aplica ahí, agruparlas mezclaría productos sin relación.
  const visibleGrouped: GroupedProducto[] = (() => {
    const porGrupo = new Map<string, GroupedProducto>();
    let sinPrecioIdx = 0;
    for (const r of visible) {
      const key = r.precio !== null && r.nombre
        ? `${r.tienda}::${r.nombre}::${r.precio}::${r.moneda ?? "UYU"}`
        : `__sin_precio_${sinPrecioIdx++}`;
      const existente = porGrupo.get(key);
      if (existente) {
        existente._sucursales.push(r);
      } else {
        porGrupo.set(key, { ...r, _sucursales: [r] });
      }
    }
    return Array.from(porGrupo.values());
  })();

  // Índice de nombres de producto únicos, para el panel lateral — se arma
  // sobre `results` crudo (no `visible`) a propósito, así siempre muestra el
  // universo completo sin importar qué chips de cadena/sucursal estén
  // activos en ese momento. Clickear un nombre ahí filtra `visible` a ese
  // producto exacto en TODAS las cadenas donde aparezca (ver toggleNombre) —
  // pensado para acotar de "una cadena a la vez" a "este producto puntual,
  // dondequiera que esté". Ordenado por cantidad de cadenas distintas que lo
  // tienen — más cadenas primero, porque es la señal más fuerte de "esto es
  // el mismo producto en varios lados" (empate: alfabético).
  const nombresUnicos = results
    ? (() => {
        const conteo = new Map<string, { nombre: string; count: number; cadenas: Set<string> }>();
        for (const r of results) {
          if (!r.nombre) continue;
          const entry = conteo.get(r.nombre) ?? { nombre: r.nombre, count: 0, cadenas: new Set<string>() };
          entry.count++;
          entry.cadenas.add(r.tienda);
          conteo.set(r.nombre, entry);
        }
        return Array.from(conteo.values()).sort(
          (a, b) => b.cadenas.size - a.cadenas.size || a.nombre.localeCompare(b.nombre)
        );
      })()
    : [];

  // Exporta exactamente lo que se ve en pantalla (respeta filtros/orden activos).
  function handleExportExcel() {
    const rows = visible.map((r) => ({
      Cadena:    CADENA_CONFIG[r.tienda]?.label ?? r.tienda,
      Producto:  r.nombre ?? "—",
      Marca:     r.marca ?? "—",
      Precio:    r.precio ?? "",
      Moneda:    r.moneda ?? "UYU",
      "Precio lista": r.precio_lista ?? "",
      Sucursal:  r.sucursal_nombre ?? "—",
      Categoría: r.categoria ?? "—",
      SKU:       r.sku ?? "—",
      URL:       r.url,
    }));
    const ws = XLSX.utils.json_to_sheet(rows);
    ws["!cols"] = [
      { wch: 16 }, { wch: 40 }, { wch: 16 }, { wch: 10 }, { wch: 8 },
      { wch: 12 }, { wch: 24 }, { wch: 16 }, { wch: 16 }, { wch: 40 },
    ];
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Precios");
    const fecha = new Date().toISOString().slice(0, 10);
    const nombreQuery = q.trim().replace(/[^a-zA-Z0-9]+/g, "_").slice(0, 40) || "busqueda";
    XLSX.writeFile(wb, `precios_${nombreQuery}_${fecha}.xlsx`);
  }

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

  // Cadenas sin datos (0 resultados, sin respuesta, o error) — se agrupan
  // detrás de un toggle en vez de mezclarse con los chips de filtro reales,
  // que ya son 11-13 y no dan abasto visualmente si se suma todo junto.
  //
  // "GDU" es una fuente paraguas (el backend consulta Disco+Devoto+Géant de
  // una), pero cada producto vuelve etiquetado con su tienda real — "GDU"
  // como string nunca aparece en un resultado. Sin este caso especial, "GDU"
  // siempre se marcaba como "sin resultado" aunque Disco/Devoto/Géant sí
  // hubieran traído productos, porque la comparación literal contra "GDU"
  // nunca daba match.
  const GDU_MIEMBROS = ["Disco", "Devoto", "Geant"];
  const cadenasSinResultado = !streaming && hasSearched
    ? cadenasDone.filter((c) => {
        if (cadenaErrors[c]) return false;
        if (c === "GDU") return !GDU_MIEMBROS.some((m) => cadenas.includes(m));
        return !cadenas.includes(c);
      })
    : [];
  const cadenasSinRespuesta = !streaming && hasSearched
    ? queriedCadenas.filter((c) => !cadenasDone.includes(c) && !cadenaErrors[c])
    : [];
  const cadenasConError = !streaming && hasSearched ? Object.keys(cadenaErrors) : [];
  const totalDiagnostico = cadenasSinResultado.length + cadenasSinRespuesta.length + cadenasConError.length;

  return (
    /* h-full + flex-col hace que la página ocupe exactamente el viewport sin crecer */
    <WatchlistsProvider>
    <div className="h-full flex flex-col gap-3 max-w-4xl mx-auto">

      {/* ── Barra de búsqueda ──────────────────────────────────────────────── */}
      <div className={`shrink-0 transition-all duration-500 ${isActive ? "" : "mt-16"}`}>
        {!hasSearched && !loading && !streaming && (
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-brand-600/10 mb-3">
              <Search size={22} className="text-brand-600" />
            </div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">{t("precios.title")}</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-2 text-sm">
              {t("precios.subtitle")}
            </p>
          </div>
        )}
        {isActive && (
          <div className="flex items-center gap-3 mb-3">
            <Search size={16} className="text-brand-600 shrink-0" />
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">{t("precios.title")}</h1>
          </div>
        )}

        <form onSubmit={(e) => { e.preventDefault(); buscar(q); }} className="relative group">
          <Search size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-brand-500 transition-colors" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("precios.searchPlaceholder")}
            className="w-full pl-11 pr-32 py-3 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500 shadow-sm transition-all"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || q.trim().length < 2}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-2"
          >
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            {loading ? t("precios.searching") : t("precios.search")}
          </button>
        </form>

        {/* Fuentes a consultar — elegido ANTES de buscar (a diferencia de los
            chips de filtro, que filtran resultados ya traídos). */}
        <div className="relative mt-2" ref={fuentesRef}>
          <button
            type="button"
            onClick={() => setShowFuentes((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
          >
            <SlidersHorizontal size={12} />
            {t("precios.sources")} ({sourceCadenas.size}/{CADENAS_TODAS.length})
          </button>

          {showFuentes && (
            <div className="absolute z-20 mt-2 w-72 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg p-3 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide">
                  {t("precios.sourcesTitle")}
                </span>
                <button
                  type="button"
                  onClick={() => setSourceCadenas(new Set(CADENAS_DEFAULT))}
                  className="text-[11px] text-brand-600 hover:underline"
                >
                  {t("precios.sourcesReset")}
                </button>
              </div>

              {[...CATEGORIA_ORDEN, "Otros"].map((categoria) => {
                const items = CADENAS_TODAS.filter((c) => (CADENA_CATEGORIA[c] ?? "Otros") === categoria);
                if (items.length === 0) return null;
                return (
                  <div key={categoria}>
                    <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide">
                      {CATEGORIA_KEYS[categoria] ? t(CATEGORIA_KEYS[categoria]) : categoria}
                    </span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {items.map((c) => {
                        const cfg = CADENA_CONFIG[c];
                        const active = sourceCadenas.has(c);
                        return (
                          <button
                            key={c}
                            type="button"
                            onClick={() => toggleFuente(c)}
                            className={`inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full font-medium transition-all ${
                              active
                                ? `${cfg?.dot ?? "bg-slate-500"} text-white`
                                : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                            }`}
                          >
                            {active && <Check size={10} />}
                            {cfg?.label ?? c}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}

              <p className="text-[10px] text-slate-400 dark:text-slate-500 pt-1.5 border-t border-slate-100 dark:border-slate-800">
                {t("precios.sourcesLoiNote")}
              </p>
            </div>
          )}
        </div>
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
          <p className="text-xs text-slate-400">{t("precios.chainsCoverage")}</p>
        </div>
      )}

      {/* ── Panel de resultados (ocupa el resto del viewport) ─────────────── */}
      {isActive && (
        <div className="flex-1 min-h-0 flex flex-col gap-2">

          {/* Barra de control — chips en su propia fila (necesitan todo el
              ancho para no amontonarse) y los controles debajo, separados. */}
          <div className="shrink-0 flex flex-col gap-2.5">
            <div className="flex items-start gap-x-4 gap-y-1.5 flex-wrap">
              <button
                onClick={() => { setFilterCadenas(new Set()); setFilterSucursal(null); setFilterNombres(new Set()); }}
                className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all shrink-0 ${
                  filterCadenas.size === 0
                    ? "bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700"
                }`}
              >
                {t("precios.all")} {results && `(${results.length})`}
              </button>

              {cadenasPorCategoria.map(({ categoria, items: chips }) => (
                <div key={categoria} className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide shrink-0">
                    {CATEGORIA_KEYS[categoria] ? t(CATEGORIA_KEYS[categoria]) : categoria}
                  </span>
                  {chips.map((c) => {
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
                        {cfg?.label ?? c} · {cadenaCounts[c]}
                      </button>
                    );
                  })}
                </div>
              ))}

              {/* Chips de progreso mientras streamea */}
              {streaming && queriedCadenas.filter(c => !cadenasDone.includes(c)).map(c => (
                <span key={c} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400">
                  <Loader2 size={9} className="animate-spin" />
                  {CADENA_CONFIG[c]?.label ?? c}
                </span>
              ))}

              {/* Diagnóstico (0 resultados / sin respuesta / error) — agrupado
                  detrás de un toggle para no competir visualmente con los chips
                  de filtro reales, que ya son bastantes. */}
              {totalDiagnostico > 0 && (
                <div className="w-full">
                  <button
                    onClick={() => setShowDiagnostico((v) => !v)}
                    className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors mt-0.5"
                  >
                    {showDiagnostico ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                    {totalDiagnostico} {totalDiagnostico === 1 ? t("precios.chainNoData") : t("precios.chainNoData_plural")}
                  </button>
                  {showDiagnostico && (
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {cadenasSinResultado.map((c) => (
                        <span key={c} title={t("precios.noResultsTooltip")} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400">
                          {CADENA_CONFIG[c]?.label ?? c} · 0
                        </span>
                      ))}
                      {cadenasSinRespuesta.map((c) => (
                        <span key={c} title={t("precios.noResponseTooltip")} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-300 dark:text-slate-600 line-through cursor-help">
                          {CADENA_CONFIG[c]?.label ?? c}
                        </span>
                      ))}
                      {cadenasConError.map((c) => (
                        <span key={c} title={cadenaErrors[c]} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400 cursor-help">
                          <AlertTriangle size={9} />
                          {CADENA_CONFIG[c]?.label ?? c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Controles — sucursal, orden, gráfico. Fila propia para no
                competirle espacio a los chips de arriba. */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Filtro de sucursal — solo visible cuando hay sucursales disponibles.
                  Agrupado por cadena (optgroup) porque Ta-Ta y El Dorado nombran sus
                  sucursales por departamento y pueden coincidir (ej. "Montevideo" en ambas). */}
              {sucursalesPorCadena.length > 0 && (
                <select
                  value={filterSucursal ?? ""}
                  onChange={(e) => setFilterSucursal(e.target.value || null)}
                  className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 transition-all max-w-[200px]"
                >
                  <option value="">{t("precios.allBranches")}</option>
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
                {sortMode === "relevancia" ? t("precios.sortRelevance") : sortMode === "precio-asc" ? t("precios.sortPriceAsc") : t("precios.sortPriceDesc")}
              </button>

              {hasResults && (
                <button
                  onClick={() => setShowProductIndex(true)}
                  className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                    filterNombres.size > 0
                      ? "border-brand-400 bg-brand-50 dark:bg-brand-950/30 text-brand-600 dark:text-brand-400"
                      : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400"
                  }`}
                >
                  <Filter size={13} />
                  {t("precios.productIndexTitle")}
                  {filterNombres.size > 0 && (
                    <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-brand-600 text-white text-[10px] font-bold leading-none">
                      {filterNombres.size}
                    </span>
                  )}
                </button>
              )}

              {hasResults && (
                <div className="flex items-center gap-2 ml-auto">
                  <button
                    onClick={handleExportExcel}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-emerald-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
                  >
                    <Download size={13} />
                    {t("precios.downloadExcel")}
                  </button>
                  <button
                    onClick={() => setShowChart(true)}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                  >
                    <BarChart3 size={13} />
                    {t("precios.viewChart")}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Banner más barato */}
          {cheapest && (
            <div className="shrink-0 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-100 dark:border-emerald-900 text-sm">
              <Store size={13} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span className="text-emerald-700 dark:text-emerald-400 text-xs">
                {t("precios.cheapest")}: <strong>{cheapest.nombre}</strong> {t("precios.at")}{" "}
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
                <p className="text-sm">{t("precios.noResultsFor")} <em>&quot;{lastQuery}&quot;</em></p>
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
                  {t("precios.noResultsHint")}
                </p>
              </div>
            )}

            {/* Tabla con header sticky */}
            {hasResults && (
              <>
                {/* Header */}
                <div className="shrink-0 flex items-center px-4 py-2 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-100 dark:border-slate-800 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                  <div className="flex-1">{t("precios.tableHeaders.product")}</div>
                  <div className="w-28 text-right mr-3">{t("precios.tableHeaders.price")}</div>
                  <div className="w-14 text-center">{t("precios.tableHeaders.view")}</div>
                  <div className="w-5" />
                </div>

                {/* Filas */}
                <div className="flex-1 overflow-y-auto divide-y divide-slate-50 dark:divide-slate-800/50">
                  {visibleGrouped.length === 0 ? (
                    <div className="py-8 text-center text-sm text-slate-400">
                      {t("precios.noResultsFilteredFrom")}{" "}
                      <em>{[...filterCadenas].map((c) => CADENA_CONFIG[c]?.label ?? c).join(", ")}</em>
                      {" "}{t("precios.noResultsFilteredFor")}
                    </div>
                  ) : visibleGrouped.map((p, i) => {
                    const hasDesc = p.precio_lista !== null && p.precio_lista > (p.precio ?? 0);
                    const pct     = hasDesc ? Math.round((1 - (p.precio ?? 0) / p.precio_lista!) * 100) : 0;
                    // `cheapest` viene de `results` crudo — con la agrupación, puede
                    // haber terminado adentro de cualquier fila (no necesariamente la
                    // primera _sucursal), por eso se busca con .includes() en vez de
                    // comparar referencia directa contra `p`.
                    const isCheap = !!cheapest && filterCadenas.size === 0 && p._sucursales.includes(cheapest);
                    const borderCfg = CADENA_CONFIG[p.tienda];
                    const agrupada = p._sucursales.length > 1;

                    return (
                      <div
                        key={`${p.tienda}-${p.sku ?? "x"}-${p.precio ?? "np"}-${i}`}
                        className={`flex items-center gap-3 px-4 py-2.5 border-l-[3px] hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors group ${
                          borderCfg?.border ?? "border-l-slate-200"
                        } ${isCheap ? "bg-emerald-50/50 dark:bg-emerald-950/20" : ""}`}
                      >
                        {/* Nombre + cadena + sucursal(es) */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                              {p.nombre ?? "—"}
                            </span>
                            {isCheap && (
                              <span className="shrink-0 text-[9px] font-bold uppercase tracking-wide bg-emerald-500 text-white px-1.5 py-0.5 rounded-full">
                                {t("precios.bestPrice")}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <CadenaBadge tienda={p.tienda} />
                            {agrupada ? (
                              <button
                                onClick={() => setSucursalesModalRow(p)}
                                className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:underline shrink-0"
                              >
                                ×{p._sucursales.length} {t("precios.branches")}
                              </button>
                            ) : p.sucursal_nombre ? (
                              <span className="text-[11px] text-slate-400 truncate">{p.sucursal_nombre}</span>
                            ) : null}
                            {p.tienda_real && p.tienda_real !== p.tienda && (
                              <span
                                title={t("precios.sharedCatalogTooltip", {
                                  chain1: CADENA_CONFIG[p.tienda]?.label ?? p.tienda,
                                  chain2: CADENA_CONFIG[p.tienda_real]?.label ?? p.tienda_real,
                                })}
                                className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-600 dark:text-amber-400 shrink-0"
                              >
                                <ArrowRight size={10} />
                                {t("precios.actuallyFrom")} {CADENA_CONFIG[p.tienda_real]?.label ?? p.tienda_real}
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

                        {/* Link — con varias sucursales agrupadas no hay un solo link
                            posible (cada una tiene su propia URL), así que este botón
                            abre el mismo modal que el badge "×N" de arriba. */}
                        <div className="w-14 flex justify-center">
                          {agrupada ? (
                            <button
                              onClick={() => setSucursalesModalRow(p)}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 hover:border-brand-500 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-all"
                              title={t("precios.viewBranches")}
                            >
                              <Store size={11} />
                              ×{p._sucursales.length}
                            </button>
                          ) : (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 hover:border-brand-500 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-all"
                              title={t("precios.viewInStore")}
                            >
                              <ExternalLink size={11} />
                              {t("precios.tableHeaders.view")}
                            </a>
                          )}
                        </div>

                        {/* Seguir — solo tiene sentido para una sucursal puntual; en
                            filas agrupadas se elige cuál seguir desde el modal. */}
                        <div className="w-5 flex justify-center">
                          {!agrupada && p.precio !== null && (
                            <SeguirButton
                              producto={{
                                tienda: p.tienda,
                                sku: p.sku,
                                nombre: p.nombre ?? "—",
                                termino_busqueda: lastQuery,
                                url: p.url,
                                precio: p.precio,
                                moneda: p.moneda ?? "UYU",
                                sucursal_id: p.sucursal_id,
                                sucursal_nombre: p.sucursal_nombre,
                              }}
                            />
                          )}
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

      {/* Modal de sucursales — se abre al clickear el badge/botón "×N" de una
          fila agrupada. A diferencia del modal equivalente en
          ComparisonModal.tsx (que solo informa, es de solo lectura), acá cada
          sucursal tiene su propio link "Ver" y su propio botón "Seguir",
          porque cada una tiene su propia URL y puede seguirse por separado. */}
      {sucursalesModalRow && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setSucursalesModalRow(null)}
        >
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-md max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3 px-5 py-4 border-b border-slate-100 dark:border-slate-800">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{sucursalesModalRow.nombre ?? "—"}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {CADENA_CONFIG[sucursalesModalRow.tienda]?.label ?? sucursalesModalRow.tienda}
                  {sucursalesModalRow.precio !== null && ` · ${fMoneyByCurrency(sucursalesModalRow.precio, sucursalesModalRow.moneda)}`}
                  {" · "}{sucursalesModalRow._sucursales.length} {t("precios.branches")}
                </p>
              </div>
              <button
                onClick={() => setSucursalesModalRow(null)}
                className="ml-auto shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-2">
              {sucursalesModalRow._sucursales.map((it, idx) => (
                <div
                  key={`${it.sucursal_id ?? idx}`}
                  className="flex items-center gap-2 py-2 border-b border-slate-50 dark:border-slate-800/60 last:border-0"
                >
                  <span className="flex-1 min-w-0 text-sm text-slate-600 dark:text-slate-300 truncate">
                    {it.sucursal_nombre ?? "—"}
                  </span>
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="shrink-0 inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 hover:border-brand-500 hover:bg-brand-100 dark:hover:bg-brand-900/50 transition-all"
                    title={t("precios.viewInStore")}
                  >
                    <ExternalLink size={10} />
                    {t("precios.tableHeaders.view")}
                  </a>
                  {it.precio !== null && (
                    <SeguirButton
                      producto={{
                        tienda: it.tienda,
                        sku: it.sku,
                        nombre: it.nombre ?? "—",
                        termino_busqueda: lastQuery,
                        url: it.url,
                        precio: it.precio,
                        moneda: it.moneda ?? "UYU",
                        sucursal_id: it.sucursal_id,
                        sucursal_nombre: it.sucursal_nombre,
                      }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Modal de índice de productos — reemplaza el panel lateral fijo de
          antes (los nombres largos quedaban cortados en 256px, y el panel
          competía mal con el resto en modo claro). Ahora es un botón en la
          barra de controles que abre esto: más ancho, nombres completos, y
          multi-selección (clickear varios nombres los suma al filtro, como
          los chips de cadena) — necesario porque Doña Tina también puede
          aplicar varios nombres de una via onApplySeleccion. Unifica por
          nombre EXACTO de producto entre TODAS las cadenas (no por precio ni
          por cadena, a diferencia de la agrupación de la lista de arriba). */}
      {showProductIndex && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setShowProductIndex(false)}
        >
          <div
            className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3 px-5 py-4 border-b border-slate-100 dark:border-slate-800">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("precios.productIndexTitle")}</p>
                <p className="text-xs text-slate-400 mt-0.5">{t("precios.productIndexHint")}</p>
              </div>
              <button
                onClick={() => setShowProductIndex(false)}
                className="ml-auto shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-5 pt-3 pb-2 shrink-0 flex items-center gap-2">
              <input
                autoFocus
                value={panelFiltro}
                onChange={(e) => setPanelFiltro(e.target.value)}
                placeholder={t("precios.productIndexSearch")}
                className="flex-1 text-sm px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
              />
              {filterNombres.size > 0 && (
                <button
                  onClick={() => setFilterNombres(new Set())}
                  className="shrink-0 flex items-center gap-1 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline whitespace-nowrap"
                >
                  <X size={12} /> {t("precios.productIndexClear")}
                </button>
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-2 pb-2">
              {nombresUnicos
                .filter((n) => !panelFiltro.trim() || n.nombre.toLowerCase().includes(panelFiltro.trim().toLowerCase()))
                .map((n) => {
                  const activo = filterNombres.has(n.nombre);
                  return (
                    <button
                      key={n.nombre}
                      onClick={() => toggleNombre(n.nombre)}
                      className={`w-full flex items-start gap-2.5 text-left px-3 py-2.5 rounded-lg transition-colors ${
                        activo
                          ? "bg-brand-50 dark:bg-brand-950/40"
                          : "hover:bg-slate-50 dark:hover:bg-slate-800"
                      }`}
                    >
                      <span className={`mt-0.5 shrink-0 w-4 h-4 rounded border-2 flex items-center justify-center ${
                        activo ? "bg-brand-600 border-brand-600" : "border-slate-300 dark:border-slate-600"
                      }`}>
                        {activo && <Check size={11} className="text-white" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className={`block text-sm ${activo ? "text-brand-700 dark:text-brand-400 font-semibold" : "text-slate-700 dark:text-slate-300"}`}>
                          {n.nombre}
                        </span>
                        <span className="text-[11px] text-slate-400">
                          {n.cadenas.size === 1
                            ? t("precios.productIndexChain", { count: n.cadenas.size })
                            : t("precios.productIndexChains", { count: n.cadenas.size })}
                          {" · "}{n.count}
                        </span>
                      </span>
                    </button>
                  );
                })}
              {nombresUnicos.length === 0 && (
                <p className="text-xs text-slate-400 text-center py-8">—</p>
              )}
            </div>

            <div className="flex justify-end px-5 py-3 border-t border-slate-100 dark:border-slate-800">
              <button onClick={() => setShowProductIndex(false)} className="btn-primary text-sm px-4 py-2">
                {t("precios.productIndexApply")}{filterNombres.size > 0 ? ` (${filterNombres.size})` : ""}
              </button>
            </div>
          </div>
        </div>
      )}

      {showChart && (
        <ComparisonModal items={visible} onClose={() => setShowChart(false)} termino={lastQuery} />
      )}

      {/* Con el gráfico abierto, ComparisonModal ya monta su propia mascota
          flotante (con onApplySeleccion conectado al checklist) en el mismo
          lugar de la pantalla — si esta también se mostrara, quedarían dos
          superpuestas y el usuario terminaría hablándole a la que NO puede
          tocar la selección (esta, la de /precios, no tiene esa conexión). */}
      {!showChart && (
        <DonTinoFloating
          context="precios"
          termino={lastQuery}
          items={visible
            .filter((r) => r.precio !== null)
            .map((r) => ({ id: r.nombre ?? "", tienda: r.tienda, nombre: r.nombre ?? "—", precio: r.precio!, moneda: r.moneda ?? "UYU" }))}
          // Reusa el mismo endpoint/mecanismo que ya usa ComparisonModal para
          // "tildar por pedido en lenguaje natural" — acá `id` es el propio
          // nombre del producto (no hay un id de fila estable en esta pantalla,
          // y filtrar por nombre es justo lo que ya hace filterNombres), así
          // que "mantener" se traduce directo a qué nombres dejar filtrados.
          onApplySeleccion={(ids) => setFilterNombres(new Set(ids.filter(Boolean)))}
          onOpenChart={() => setShowChart(true)}
        />
      )}
    </div>
    </WatchlistsProvider>
  );
}
