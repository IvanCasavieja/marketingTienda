"use client";
import { useEffect, useMemo, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";
import { X, BarChart3, Store } from "lucide-react";
import { preciosApi, type ProductoVivo, type CotizacionDolar } from "@/lib/api";
import { fMoneyByCurrency } from "@/lib/format";
import { CADENA_CONFIG, CadenaBadge } from "@/components/precios/cadenaConfig";
import DonaTinaFloating from "@/components/DonaTinaFloating";
import SeguirButton from "@/components/precios/SeguirButton";
import SearchableChecklist from "@/components/ui/SearchableChecklist";
import { useEscapeKey } from "@/hooks/useEscapeKey";

// ── Item con id estable (posición en el pool recibido — no cambia mientras
// el modal está abierto, aunque el buscador del checklist filtre la vista) ──
type ItemConId = ProductoVivo & { _id: string };

const PRESELECCION_INICIAL = 8;
const NUESTRO_COLOR = "#eab308"; // amarillo — distinto de cualquier cadena, para que resalte como "nosotros"

// Una barra del gráfico — puede representar varias sucursales de la misma
// cadena agrupadas por tener el mismo precio (ver chartData más abajo).
interface ChartBarData {
  name: string;
  nombreCompleto: string;
  cadenaLabel: string;
  precio: number;
  precioOriginal: number;
  monedaOriginal: string;
  moneda: "UYU" | "USD";
  fill: string;
  sucursales: string[];
}

function truncar(nombre: string | null, max = 26): string {
  const n = nombre ?? "—";
  return n.length > max ? n.slice(0, max - 1) + "…" : n;
}

// Compra/venta se usan para direcciones distintas — no es la misma tasa ida y
// vuelta. USD→UYU usa "venta" (lo que cuesta en pesos conseguir esos dólares).
// UYU→USD usa "compra" (lo que valen esos pesos si se los cambia por dólares).
function convertir(
  precio: number,
  monedaOrigen: string | null,
  monedaDestino: "UYU" | "USD",
  cot: CotizacionDolar | null,
): number | null {
  const origen = monedaOrigen ?? "UYU";
  if (origen === monedaDestino) return precio;
  if (!cot) return null;
  if (origen === "USD" && monedaDestino === "UYU") return precio * cot.venta;
  if (origen === "UYU" && monedaDestino === "USD") return precio / cot.compra;
  return null; // otras monedas: no hay tasa para convertir
}

const ChartTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const nSucursales = d.sucursales?.length ?? 0;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 shadow-card-hover rounded-xl px-3.5 py-2.5 max-w-[220px]">
      <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1 leading-snug">{d.nombreCompleto}</p>
      <p className="text-[11px] text-slate-400 mb-1">
        {d.cadenaLabel}
        {nSucursales === 1 ? ` · ${d.sucursales[0]}` : ""}
        {nSucursales > 1 ? ` · ${nSucursales} sucursales — click para verlas` : ""}
      </p>
      <p className="text-sm font-bold" style={{ color: d.fill }}>{fMoneyByCurrency(d.precio, d.moneda)}</p>
      {d.monedaOriginal !== d.moneda && (
        <p className="text-[10.5px] text-slate-400 mt-0.5">
          Original: {fMoneyByCurrency(d.precioOriginal, d.monedaOriginal)}
        </p>
      )}
    </div>
  );
};

export default function ComparisonModal({
  items, onClose, termino,
}: {
  items: ProductoVivo[];
  onClose: () => void;
  termino?: string;
}) {
  const withIds: ItemConId[] = useMemo(
    () => items.map((it, idx) => ({ ...it, _id: `${it.tienda}-${it.sucursal_id ?? "x"}-${it.sku ?? "x"}-${idx}` })),
    [items]
  );

  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(withIds.slice(0, PRESELECCION_INICIAL).map((it) => it._id))
  );
  const [ourPrice, setOurPrice] = useState("");
  const [ourCurrency, setOurCurrency] = useState<"UYU" | "USD">("UYU");
  const [monedaVista, setMonedaVista] = useState<"UYU" | "USD">("UYU");
  const [cotizacion, setCotizacion] = useState<CotizacionDolar | null>(null);
  const [cotizacionError, setCotizacionError] = useState(false);
  const [sucursalesModal, setSucursalesModal] = useState<ChartBarData | null>(null);

  useEscapeKey(() => (sucursalesModal ? setSucursalesModal(null) : onClose()));

  useEffect(() => {
    preciosApi.cotizacionDolar()
      .then(({ data }) => setCotizacion(data))
      .catch(() => setCotizacionError(true));
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const seleccionados = useMemo(
    () => withIds.filter((it) => selected.has(it._id) && it.precio !== null),
    [withIds, selected]
  );

  // Vista agrupada del checklist — mismo criterio que el gráfico (cadena +
  // producto + precio): varias sucursales con el mismo precio comparten una
  // sola fila con un checkbox, en vez de una fila casi idéntica por cada una
  // (mismo problema que tenía el gráfico antes de agruparse, acá en la lista
  // de selección). Tildar la fila tilda TODAS sus sucursales a la vez — total
  // el gráfico las iba a mostrar como una sola barra de todos modos. El
  // botón "×N" reusa el mismo modal de sucursales que ya abren las barras
  // del gráfico, para ver el detalle sin salir del checklist.
  const withIdsGrouped = useMemo(() => {
    const porGrupo = new Map<string, ItemConId & { _sucursales: ItemConId[] }>();
    let sinPrecioIdx = 0;
    for (const it of withIds) {
      const key = it.precio !== null && it.nombre
        ? `${it.tienda}::${it.nombre}::${it.precio}::${it.moneda ?? "UYU"}`
        : `__sin_precio_${sinPrecioIdx++}`;
      const existente = porGrupo.get(key);
      if (existente) existente._sucursales.push(it);
      else porGrupo.set(key, { ...it, _sucursales: [it] });
    }
    return Array.from(porGrupo.values());
  }, [withIds]);

  // El checklist necesita "está tildado" a nivel de grupo — se muestra
  // tildado solo si TODAS sus sucursales lo están, para no mostrar un
  // estado ambiguo de "tildado a medias".
  const selectedGrupos = useMemo(() => {
    const next = new Set<string>();
    for (const g of withIdsGrouped) {
      if (g._sucursales.every((s) => selected.has(s._id))) next.add(g._id);
    }
    return next;
  }, [withIdsGrouped, selected]);

  function toggleGrupo(grupoId: string) {
    const grupo = withIdsGrouped.find((g) => g._id === grupoId);
    if (!grupo) return;
    const todosMarcados = grupo._sucursales.every((s) => selected.has(s._id));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const s of grupo._sucursales) {
        todosMarcados ? next.delete(s._id) : next.add(s._id);
      }
      return next;
    });
  }

  // Agrupa por (cadena, producto, precio) — varias sucursales de la misma
  // cadena con el mismo precio para el mismo producto comparten una sola
  // barra (ver `sucursales`); si el precio difiere entre sucursales siguen
  // siendo barras separadas. Esto evita que cadenas con muchas sucursales
  // (Disco/Devoto/Géant, o cualquier otra que reporte por sucursal) saturen
  // el gráfico con barras casi idénticas — ver ChartBarData arriba.
  const { chartData, omitidosPorCotizacion } = useMemo(() => {
    const porGrupo = new Map<string, ChartBarData>();
    let omitidos = 0;

    for (const it of seleccionados) {
      const convertido = convertir(it.precio!, it.moneda, monedaVista, cotizacion);
      if (convertido === null) { omitidos++; continue; }

      const key = `${it.tienda}::${it.nombre ?? ""}::${convertido}`;
      const existente = porGrupo.get(key);
      if (existente) {
        if (it.sucursal_nombre && !existente.sucursales.includes(it.sucursal_nombre)) {
          existente.sucursales.push(it.sucursal_nombre);
        }
        continue;
      }
      porGrupo.set(key, {
        name: truncar(it.nombre),
        nombreCompleto: it.nombre ?? "—",
        cadenaLabel: CADENA_CONFIG[it.tienda]?.label ?? it.tienda,
        precio: convertido,
        precioOriginal: it.precio!,
        monedaOriginal: it.moneda ?? "UYU",
        moneda: monedaVista,
        fill: CADENA_CONFIG[it.tienda]?.hex ?? "#94a3b8",
        sucursales: it.sucursal_nombre ? [it.sucursal_nombre] : [],
      });
    }

    return { chartData: Array.from(porGrupo.values()), omitidosPorCotizacion: omitidos };
  }, [seleccionados, monedaVista, cotizacion]);

  const ourPriceRaw = ourPrice.trim() ? Number(ourPrice) : null;
  const ourPriceNum = ourPriceRaw !== null && Number.isFinite(ourPriceRaw) ? ourPriceRaw : null;
  const ourPriceConvertido = ourPriceNum !== null ? convertir(ourPriceNum, ourCurrency, monedaVista, cotizacion) : null;

  // Para Doña Tina: el pool completo con precio (preguntas + filtro) y los
  // tildados (reporte). Los que no tienen precio quedan afuera — no se les
  // puede preguntar nada numérico ni entran en un reporte.
  const itemsParaDonTino = useMemo(
    () => withIds
      .filter((it) => it.precio !== null)
      .map((it) => ({ id: it._id, tienda: it.tienda, nombre: it.nombre ?? "—", precio: it.precio!, moneda: it.moneda ?? "UYU" })),
    [withIds]
  );
  const chartItemsParaReporte = useMemo(
    () => withIds
      .filter((it) => selected.has(it._id) && it.precio !== null)
      .map((it) => ({ tienda: it.tienda, nombre: it.nombre ?? "—", precio: it.precio!, moneda: it.moneda ?? "UYU" })),
    [withIds, selected]
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="comparison-modal-title" className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100 dark:border-slate-800">
          <BarChart3 size={18} className="text-brand-500" />
          <h2 id="comparison-modal-title" className="text-base font-semibold text-slate-800 dark:text-slate-100">Comparar precios</h2>
          <button onClick={onClose} aria-label="Cerrar" className="ml-auto text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"><X size={18} /></button>
        </div>

        {/* Body — dos columnas */}
        <div className="flex-1 min-h-0 flex flex-col md:flex-row">

          {/* Columna izquierda: precio propio + gráfico */}
          <div className="flex-1 min-w-0 p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-end gap-3 flex-wrap">
              <div>
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Nuestro precio</label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={ourPrice}
                  onChange={(e) => setOurPrice(e.target.value)}
                  placeholder="0.00"
                  className="input text-sm w-36"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Moneda</label>
                <select
                  value={ourCurrency}
                  onChange={(e) => setOurCurrency(e.target.value as "UYU" | "USD")}
                  className="input text-sm w-24"
                >
                  <option value="UYU">$ UYU</option>
                  <option value="USD">U$S</option>
                </select>
              </div>
              <div className="ml-auto">
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Mostrar gráfico en</label>
                <div className="flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                  {(["UYU", "USD"] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setMonedaVista(m)}
                      className={`px-3 py-1.5 text-xs font-semibold transition-colors ${
                        monedaVista === m
                          ? "bg-brand-600 text-white"
                          : "bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
                      }`}
                    >
                      {m === "UYU" ? "Pesos" : "Dólares"}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {cotizacion && (
              <div className="-mt-1 inline-flex self-start items-stretch rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-[11px]">
                <div className="px-2.5 py-1.5 bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5">
                  Cotización BROU
                  <span className="text-slate-400 dark:text-slate-500 font-normal">{cotizacion.fecha}</span>
                </div>
                <div className="px-2.5 py-1 border-l border-slate-200 dark:border-slate-700 flex flex-col items-center justify-center">
                  <span className="text-[9px] text-slate-400 uppercase tracking-wide leading-tight">Compra</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-300 tabular-nums leading-tight">${cotizacion.compra.toFixed(2)}</span>
                </div>
                <div className="px-2.5 py-1 border-l border-slate-200 dark:border-slate-700 flex flex-col items-center justify-center">
                  <span className="text-[9px] text-slate-400 uppercase tracking-wide leading-tight">Venta</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-300 tabular-nums leading-tight">${cotizacion.venta.toFixed(2)}</span>
                </div>
              </div>
            )}
            {cotizacionError && !cotizacion && (
              <p className="text-[10.5px] text-amber-500 -mt-1">
                No se pudo obtener la cotización del dólar — los productos en otra moneda no se muestran en el gráfico.
              </p>
            )}

            {chartData.length === 0 ? (
              <div className="flex-1 min-h-[280px] flex items-center justify-center text-sm text-slate-400 text-center px-6">
                {seleccionados.length === 0
                  ? "Tildá uno o más productos de la lista para armar el gráfico comparativo."
                  : `Los productos tildados están en ${seleccionados[0].moneda ?? "otra moneda"} y todavía no hay cotización para pasarlos a ${monedaVista === "UYU" ? "pesos" : "dólares"}.`}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={340}>
                <BarChart data={chartData} margin={{ top: 12, right: 12, left: 0, bottom: 56 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10.5 }}
                    angle={-35}
                    textAnchor="end"
                    interval={0}
                    height={70}
                  />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip content={<ChartTooltip />} />
                  {ourPriceConvertido !== null && (
                    <ReferenceLine
                      y={ourPriceConvertido}
                      stroke={NUESTRO_COLOR}
                      strokeWidth={2}
                      strokeDasharray="6 4"
                      ifOverflow="extendDomain"
                      label={{ value: "Nuestro precio", position: "insideTopRight", fill: NUESTRO_COLOR, fontSize: 11, fontWeight: 700 }}
                    />
                  )}
                  <Bar
                    dataKey="precio"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={48}
                    label={(props: any) => {
                      const entry: ChartBarData | undefined = chartData[props.index];
                      if (!entry || entry.sucursales.length <= 1) return <g />;
                      return (
                        <text
                          x={props.x + props.width / 2}
                          y={props.y - 6}
                          textAnchor="middle"
                          fontSize={10}
                          fontWeight={700}
                          fill="#64748b"
                        >
                          ×{entry.sucursales.length}
                        </text>
                      );
                    }}
                  >
                    {chartData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={entry.fill}
                        style={{ cursor: entry.sucursales.length > 1 ? "pointer" : "default" }}
                        onClick={() => { if (entry.sucursales.length > 1) setSucursalesModal(entry); }}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}

            {ourPriceNum !== null && (
              <p className="text-[11px] text-slate-400 dark:text-slate-500 -mt-2">
                {ourPriceConvertido !== null
                  ? "La línea punteada muestra nuestro precio contra los productos seleccionados, todos convertidos a la misma moneda."
                  : "No hay cotización disponible para convertir nuestro precio a la moneda del gráfico — no se puede dibujar la línea de referencia."}
              </p>
            )}

            {omitidosPorCotizacion > 0 && (
              <p className="text-[11px] text-amber-500 -mt-2">
                {omitidosPorCotizacion === 1
                  ? "1 producto tildado no se muestra en el gráfico por estar en otra moneda sin cotización disponible."
                  : `${omitidosPorCotizacion} productos tildados no se muestran en el gráfico por estar en otra moneda sin cotización disponible.`}
              </p>
            )}

            {chartData.some((d) => d.sucursales.length > 1) && (
              <p className="text-[11px] text-slate-400 dark:text-slate-500 -mt-2">
                Las barras marcadas con &quot;×N&quot; agrupan varias sucursales con el mismo precio — hacé click para verlas.
              </p>
            )}
          </div>

          {/* Columna derecha: checklist de productos */}
          <div className="w-full md:w-[300px] shrink-0 border-t md:border-t-0 md:border-l border-slate-100 dark:border-slate-800 flex flex-col min-h-0">
            <SearchableChecklist
              items={withIdsGrouped}
              selected={selectedGrupos}
              onToggle={toggleGrupo}
              getId={(it) => it._id}
              getSearchText={(it) => it.nombre ?? ""}
              getGroup={(it) => it.tienda}
              renderGroupHeader={(tienda) => <CadenaBadge tienda={tienda} />}
              renderLabel={(it) => it.nombre ?? "—"}
              renderSubtitle={(it) => (
                <>
                  {it._sucursales.length > 1
                    ? `×${it._sucursales.length} sucursales · `
                    : it.sucursal_nombre ? `${it.sucursal_nombre} · ` : ""}
                  {it.precio !== null ? fMoneyByCurrency(it.precio, it.moneda) : "—"}
                </>
              )}
              renderExtra={(it) => {
                if (it.precio === null) return null;
                if (it._sucursales.length > 1) {
                  return (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSucursalesModal({
                          name: "", nombreCompleto: it.nombre ?? "—",
                          cadenaLabel: CADENA_CONFIG[it.tienda]?.label ?? it.tienda,
                          precio: it.precio!, precioOriginal: it.precio!,
                          monedaOriginal: it.moneda ?? "UYU",
                          moneda: (it.moneda === "USD" ? "USD" : "UYU"),
                          fill: "",
                          sucursales: it._sucursales.map((s) => s.sucursal_nombre ?? "—"),
                        });
                      }}
                      title="Ver sucursales"
                      className="shrink-0 text-slate-300 hover:text-brand-500 transition-colors"
                    >
                      <Store size={12} />
                    </button>
                  );
                }
                return (
                  <SeguirButton
                    producto={{
                      tienda: it.tienda,
                      sku: it.sku,
                      nombre: it.nombre ?? "—",
                      termino_busqueda: termino ?? "",
                      url: it.url,
                      precio: it.precio,
                      moneda: it.moneda ?? "UYU",
                      sucursal_id: it.sucursal_id,
                      sucursal_nombre: it.sucursal_nombre,
                    }}
                  />
                );
              }}
              searchPlaceholder="Filtrar productos..."
              emptyMessage={(q) => `Sin productos para "${q}"`}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-100 dark:border-slate-800">
          <button onClick={onClose} className="btn-secondary text-sm px-4 py-2">Cerrar</button>
        </div>
      </div>

      {/* Modal de sucursales — se abre al clickear una barra agrupada */}
      {sucursalesModal && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setSucursalesModal(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="sucursales-modal-title"
            className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-sm max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3 px-5 py-4 border-b border-slate-100 dark:border-slate-800">
              <div className="min-w-0">
                <p id="sucursales-modal-title" className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{sucursalesModal.nombreCompleto}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {sucursalesModal.cadenaLabel} · {fMoneyByCurrency(sucursalesModal.precio, sucursalesModal.moneda)} · {sucursalesModal.sucursales.length} sucursales
                </p>
              </div>
              <button
                onClick={() => setSucursalesModal(null)}
                aria-label="Cerrar"
                className="ml-auto shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-3">
              {sucursalesModal.sucursales.map((s) => (
                <p key={s} className="text-sm text-slate-600 dark:text-slate-300 py-1.5 border-b border-slate-50 dark:border-slate-800/60 last:border-0">
                  {s}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      <DonaTinaFloating
        context="comparison"
        termino={termino ?? ""}
        items={itemsParaDonTino}
        chartItems={chartItemsParaReporte}
        ourPrice={ourPriceNum}
        ourCurrency={ourCurrency}
        onApplySeleccion={(ids) => setSelected(new Set(ids))}
      />
    </div>
  );
}
