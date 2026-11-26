"use client";
// Las piezas del tablero de Clientes VIP. Tranqui y legible (la auditoría del
// 25/11/2026 pidió menos "hecho con IA"): fondo blanco, un solo color para los
// datos y el texto en grises.
import { useState } from "react";
import { clientesVipApi } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { FilaDimension, Informe, KpiMes, NotaDeMemoria, Prediccion, SegmentoResumen, Segmento, Carga } from "@/lib/clientes-vip/tipos";
import { QUE_ES, ejeDePlata, mesCorto, mesLargo, numero, plata, variacion } from "@/lib/clientes-vip/tipos";

export const CAJA = "rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900";
export const TITULO = "text-sm font-semibold text-slate-900 dark:text-slate-100";

/** ▲ 2,3% / ▼ 1,1%, con lo que se compara. */
export function Cambio({ v, contra }: { v: number | null; contra?: string }) {
  if (v === null || v === undefined) return <span className="text-xs text-slate-400">{contra ? `sin dato ${contra}` : "—"}</span>;
  const sube = v >= 0;
  return (
    <span className={`text-xs tabular-nums ${sube ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
      <span aria-hidden>{sube ? "▲" : "▼"}</span> {numero(Math.abs(v), 1)}%{contra ? <span className="text-slate-400"> {contra}</span> : null}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Indicadores del mes
// ---------------------------------------------------------------------------

export function Indicadores({ meses, totalClientes }: { meses: KpiMes[]; totalClientes: number }) {
  const m = meses[meses.length - 1];
  const ant = meses[meses.length - 2];
  const anio = meses.find((x) => x.mes === `${Number(m.mes.slice(0, 4)) - 1}${m.mes.slice(4)}`);
  const mPct = m.venta ? (100 * m.margen) / m.venta : 0;
  const pct = (k: KpiMes | undefined) => (k && k.venta ? (100 * k.margen) / k.venta : null);
  const puntos = (a: number | null, b: number | null) => (a !== null && b !== null ? Math.round((a - b) * 10) / 10 : null);
  const tiles: { titulo: string; valor: string; cambios: { v: number | null; contra: string; puntos?: boolean }[] }[] = [
    { titulo: "Venta", valor: plata(m.venta), cambios: [
      { v: variacion(m.venta, ant?.venta), contra: "vs mes anterior" },
      { v: variacion(m.venta, anio?.venta), contra: "vs año anterior" }] },
    { titulo: "Margen", valor: `${numero(mPct, 1)}%`, cambios: [
      { v: puntos(mPct, pct(ant)), contra: "pts vs mes anterior", puntos: true },
      { v: puntos(mPct, pct(anio)), contra: "pts vs año anterior", puntos: true }] },
    { titulo: "Compraron", valor: `${numero(m.clientes)} de ${numero(totalClientes)}`, cambios: [
      { v: variacion(m.clientes, ant?.clientes), contra: "vs mes anterior" },
      { v: variacion(m.clientes, anio?.clientes), contra: "vs año anterior" }] },
    { titulo: "Ticket promedio", valor: plata(m.ticket_promedio), cambios: [
      { v: variacion(m.ticket_promedio, ant?.ticket_promedio), contra: "vs mes anterior" },
      { v: variacion(m.ticket_promedio, anio?.ticket_promedio), contra: "vs año anterior" }] },
    { titulo: "Compras por cliente", valor: numero(m.frecuencia, 1), cambios: [
      { v: variacion(m.frecuencia, ant?.frecuencia), contra: "vs mes anterior" },
      { v: variacion(m.frecuencia, anio?.frecuencia), contra: "vs año anterior" }] },
  ];
  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {tiles.map((t) => (
        <div key={t.titulo} className={`${CAJA} p-4`}>
          <p className="text-xs text-slate-500 dark:text-slate-400">{t.titulo} · {mesCorto(m.mes)}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{t.valor}</p>
          <div className="mt-2 flex flex-col gap-0.5">
            {t.cambios.map((c) => c.puntos
              ? <span key={c.contra} className="text-xs tabular-nums text-slate-500">{c.v === null ? `sin dato ${c.contra.replace("pts ", "")}` : `${c.v >= 0 ? "+" : "−"}${numero(Math.abs(c.v), 1)} ${c.contra}`}</span>
              : <Cambio key={c.contra} v={c.v} contra={c.contra} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Venta por mes, con lo que espera Valentina
// ---------------------------------------------------------------------------

type Punto = { mes: string; venta: number; esperada?: boolean; desde?: number; hasta?: number };

function Globo({ active, payload }: { active?: boolean; payload?: { payload: Punto }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-xs shadow-sm">
      <p className="font-medium text-slate-900 dark:text-slate-100">{mesLargo(p.mes)}</p>
      <p className="text-slate-600 dark:text-slate-300 tabular-nums">{p.esperada ? "Esperada: " : ""}{plata(p.venta)}</p>
      {p.esperada && <p className="text-slate-400 tabular-nums">entre {plata(p.desde)} y {plata(p.hasta)}</p>}
    </div>
  );
}

export function GraficoVentas({ meses, prediccion }: { meses: KpiMes[]; prediccion: Prediccion | null }) {
  const datos: Punto[] = meses.slice(-24).map((m) => ({ mes: m.mes, venta: m.venta }));
  if (prediccion?.venta) datos.push({ mes: prediccion.mes, venta: prediccion.venta, esperada: true, desde: prediccion.desde, hasta: prediccion.hasta });
  const eje = ejeDePlata(Math.max(0, ...datos.map((d) => d.venta)));
  return (
    <div className={`${CAJA} p-5`}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className={TITULO}>Venta por mes</h2>
        <span className="text-xs text-slate-400 hidden sm:inline">sin IVA · la última barra, con borde punteado, es la esperada</span>
      </div>
      <div className="h-64 mt-4" role="img" aria-label="Venta por mes de los clientes VIP">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={datos} margin={{ top: 4, right: 4, bottom: 0, left: 4 }} barCategoryGap="22%">
            <XAxis dataKey="mes" tickFormatter={mesCorto} tickLine={false} axisLine={false}
                   tick={{ fontSize: 11 }} className="[&_text]:fill-slate-400" interval="preserveStartEnd" minTickGap={8} />
            <YAxis tickFormatter={eje} tickLine={false} axisLine={false}
                   width={56} tick={{ fontSize: 11 }} className="[&_text]:fill-slate-400" />
            <Tooltip content={<Globo />} cursor={{ className: "fill-slate-100 dark:fill-slate-800" }} />
            <Bar dataKey="venta" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {datos.map((d) => (
                <Cell key={d.mes} fill="#2a78d6"
                      className={d.esperada ? "fill-[#2a78d6]/25 stroke-[#2a78d6] dark:fill-[#3987e5]/25 dark:stroke-[#3987e5]" : "fill-[#2a78d6] dark:fill-[#3987e5]"}
                      strokeDasharray={d.esperada ? "4 3" : undefined} strokeWidth={d.esperada ? 1.5 : 0} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** «Lo que viene»: la predicción de Valentina si ya analizó el último mes;
 *  si no, el cálculo rápido de la plataforma, dicho como tal. */
export function LoQueViene({ suya, rapida, ultimo }: { suya: Prediccion | null; rapida: Prediccion | null; ultimo: KpiMes }) {
  const p = suya?.venta ? suya : rapida;
  return (
    <div className={`${CAJA} p-5 flex flex-col`}>
      <h2 className={TITULO}>Lo que viene</h2>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
        {suya?.venta ? "Por Valentina, economista del Escuadrón Lechuza" : "Cálculo rápido de la plataforma: Valentina todavía no analizó este mes"}
      </p>
      {p?.venta ? (
        <>
          <p className="mt-4 text-xs text-slate-500">Venta esperada de {mesLargo(p.mes)}</p>
          <p className="text-3xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{plata(p.venta)}</p>
          {p.desde && p.hasta ? <p className="text-sm text-slate-500 tabular-nums">entre {plata(p.desde)} y {plata(p.hasta)}</p> : null}
          <div className="mt-3 flex flex-col gap-1">
            <Cambio v={variacion(p.venta, ultimo.venta)} contra={`vs ${mesCorto(ultimo.mes)}`} />
            {p.contra_anio_anterior !== undefined && <Cambio v={p.contra_anio_anterior} contra="vs el mismo mes del año pasado" />}
          </div>
          {p.como && (
            <p className="mt-auto pt-4 text-xs text-slate-400">
              Cómo: {p.como}.{p.margen_error ? ` Se equivoca en promedio un ${numero(p.margen_error, 1)}%.` : ""}
            </p>
          )}
        </>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Hace falta al menos un mes cargado.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// El informe de Valentina (Escuadrón Lechuza, desde la nube)
// ---------------------------------------------------------------------------

export function InformeDelMes({ informe, ultimoMes }: { informe: Informe | null; ultimoMes: string }) {
  const viejo = informe && informe.mes !== ultimoMes;
  return (
    <div className={`${CAJA} p-5`}>
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h2 className={TITULO}>El informe del mes</h2>
        <span className="text-xs text-slate-400">
          {informe ? informe.autor : "Valentina, economista del Escuadrón Lechuza"}
          {informe?.fecha ? ` · ${new Date(informe.fecha).toLocaleDateString("es-UY", { day: "numeric", month: "long" })}` : ""}
        </span>
      </div>
      {!informe || viejo ? (
        <p className="mt-3 text-sm text-slate-500">
          {viejo ? `Este es el de ${mesLargo(informe!.mes)}. ` : ""}Valentina analiza {mesLargo(ultimoMes)} en su próxima vuelta
          (de lunes a viernes, cada hora de 8 a 18) y lo manda por mail.
        </p>
      ) : null}
      {informe && (
        <div className="mt-2 text-sm text-slate-700 dark:text-slate-300 leading-relaxed
                        [&_h3]:mt-5 [&_h3]:mb-1.5 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-slate-900 dark:[&_h3]:text-slate-100
                        [&_ul]:list-disc [&_ul]:pl-5 [&_li]:my-1 [&_p]:my-1.5 [&_strong]:text-slate-900 dark:[&_strong]:text-slate-100">
          <ReactMarkdown>{informe.analisis}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lo que aprendió Valentina: su memoria, para ver qué sabe y qué le enseñaron
// ---------------------------------------------------------------------------

export function MemoriaDeValentina({ cuantas }: { cuantas: number }) {
  const [notas, setNotas] = useState<NotaDeMemoria[] | null>(null);
  const [error, setError] = useState(false);
  function abrir(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || notas) return;
    clientesVipApi.memoria().then(({ data }) => setNotas(data.filter((n) => !n.tema.startsWith("_")))).catch(() => setError(true));
  }
  return (
    <details className={`${CAJA} p-5`} onToggle={abrir}>
      <summary className={`${TITULO} cursor-pointer`}>
        Lo que aprendió Valentina <span className="font-normal text-slate-400">· {cuantas} {cuantas === 1 ? "cosa" : "cosas"}</span>
      </summary>
      <p className="mt-2 text-xs text-slate-500">
        Lo que le enseñaron por mail y lo que sacó de sus análisis e investigaciones. Lo lee antes de cada informe.
        Para enseñarle algo (o discutirle), respondé su mail.
      </p>
      {error && <p className="mt-3 text-sm text-red-700 dark:text-red-400">No se pudo traer su memoria.</p>}
      {notas && !notas.length && <p className="mt-3 text-sm text-slate-500">Todavía no anotó nada.</p>}
      {notas && notas.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
          {notas.map((n) => (
            <li key={n.id} className="py-2.5">
              <p className="text-xs text-slate-400">{n.tema}{n.fuente ? ` · ${n.fuente}` : ""}</p>
              <p className="text-sm text-slate-700 dark:text-slate-300">{n.texto}</p>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

// ---------------------------------------------------------------------------
// Segmentos
// ---------------------------------------------------------------------------

const PUNTO: Record<Segmento, string> = {
  Creciendo: "bg-emerald-500", Estable: "bg-slate-400", Nuevo: "bg-sky-500",
  Bajando: "bg-amber-500", "En riesgo": "bg-orange-600", Perdido: "bg-red-600",
};

export function Segmentos({ segmentos, elegido, onElegir }: {
  segmentos: SegmentoResumen[]; elegido: string | null; onElegir: (s: string | null) => void
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {segmentos.map((s) => {
        const activo = elegido === s.segmento;
        return (
          <button key={s.segmento} onClick={() => onElegir(activo ? null : s.segmento)} title={QUE_ES[s.segmento]}
                  aria-pressed={activo}
                  className={`${CAJA} p-4 text-left transition-colors ${activo ? "ring-2 ring-slate-900 dark:ring-slate-100" : "hover:border-slate-300 dark:hover:border-slate-600"}`}>
            <span className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
              <span className={`w-2 h-2 rounded-full ${PUNTO[s.segmento]}`} aria-hidden /> {s.segmento}
            </span>
            <span className="mt-1 block text-xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{numero(s.clientes)}</span>
            <span className="block text-xs text-slate-500 tabular-nums">{plata(s.venta_3m)} en 3 meses</span>
            <span className="mt-1 block"><Cambio v={variacion(s.venta_3m, s.venta_3m_antes)} contra="vs 3 antes" /></span>
          </button>
        );
      })}
    </div>
  );
}

export function PuntoSegmento({ s }: { s: Segmento }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${PUNTO[s]}`} aria-hidden />;
}

// ---------------------------------------------------------------------------
// Categorías, sucursales, canales y marca propia
// ---------------------------------------------------------------------------

const PESTANAS = [
  { clave: "categoria", nombre: "Categorías" }, { clave: "sucursal", nombre: "Sucursales" },
  { clave: "canal", nombre: "Canales" }, { clave: "marca_propia", nombre: "Marca propia" },
] as const;

export function Dimensiones({ dims }: { dims: Record<string, FilaDimension[]> }) {
  const [pestana, setPestana] = useState<(typeof PESTANAS)[number]["clave"]>("categoria");
  const [todas, setTodas] = useState(false);
  const filas = dims[pestana] ?? [];
  const total = filas.reduce((a, f) => a + f.venta_3m, 0);
  const visibles = todas ? filas : filas.slice(0, 10);
  return (
    <div className={`${CAJA} p-5`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className={TITULO}>Dónde compran</h2>
        <div className="flex gap-1 rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5" role="tablist">
          {PESTANAS.map((p) => (
            <button key={p.clave} role="tab" aria-selected={pestana === p.clave} onClick={() => { setPestana(p.clave); setTodas(false); }}
                    className={`px-2.5 py-1 rounded-md text-xs ${pestana === p.clave ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm" : "text-slate-500"}`}>
              {p.nombre}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400">
              <th className="py-2 font-normal">Nombre</th>
              <th className="py-2 font-normal text-right">Últimos 3 meses</th>
              <th className="py-2 font-normal text-right hidden sm:table-cell">Parte</th>
              <th className="py-2 font-normal text-right">vs 3 antes</th>
              <th className="py-2 font-normal text-right hidden md:table-cell">vs año anterior</th>
              <th className="py-2 font-normal text-right hidden md:table-cell">Margen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {visibles.map((f) => (
              <tr key={f.valor}>
                <td className="py-2 pr-3 text-slate-800 dark:text-slate-200">{f.valor}</td>
                <td className="py-2 text-right tabular-nums text-slate-700 dark:text-slate-300">{plata(f.venta_3m)}</td>
                <td className="py-2 text-right tabular-nums text-slate-500 hidden sm:table-cell">{total ? `${numero((100 * f.venta_3m) / total, 1)}%` : "—"}</td>
                <td className="py-2 text-right"><Cambio v={f.contra_3m_antes} /></td>
                <td className="py-2 text-right hidden md:table-cell"><Cambio v={f.contra_anio_anterior} /></td>
                <td className="py-2 text-right tabular-nums text-slate-500 hidden md:table-cell">{f.margen_3m === null ? "—" : `${numero(f.margen_3m, 1)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filas.length > 10 && (
          <button onClick={() => setTodas(!todas)} className="mt-2 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">
            {todas ? "Ver menos" : `Ver las ${filas.length}`}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Las cargas
// ---------------------------------------------------------------------------

export function Cargas({ cargas }: { cargas: Carga[] }) {
  if (!cargas.length) return null;
  return (
    <details className={`${CAJA} p-5`}>
      <summary className={`${TITULO} cursor-pointer`}>Archivos cargados</summary>
      <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800 text-sm">
        {cargas.map((c) => (
          <li key={c.id} className="py-2 flex flex-wrap justify-between gap-2">
            <span className="text-slate-800 dark:text-slate-200">{c.archivo}
              <span className="text-slate-400"> · {c.meses.length === 1 ? mesLargo(c.meses[0]) : `${mesCorto(c.meses[0])} a ${mesCorto(c.meses[c.meses.length - 1])}`}</span>
            </span>
            <span className="text-xs text-slate-500">
              {c.estado === "lista" ? `${numero(c.clientes)} clientes · ${plata(c.venta)}` : "se cortó a la mitad: volvé a cargarlo"}
              {c.subido_por ? ` · ${c.subido_por}` : ""}
              {c.fecha ? ` · ${new Date(c.fecha).toLocaleDateString("es-UY")}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
