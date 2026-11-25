"use client";
// La lista de clientes VIP (filtro por segmento, búsqueda, orden) y la ficha
// de cada uno, mes a mes.
import { useEffect, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { clientesVipApi } from "@/lib/api";
import { extractErrorDetail } from "@/lib/errors";
import type { ClienteVip, MesDeCliente, Segmento } from "@/lib/clientes-vip/tipos";
import { QUE_ES, mesCorto, mesLargo, mesesEntre, numero, plata, variacion } from "@/lib/clientes-vip/tipos";
import { CAJA, Cambio, PuntoSegmento, TITULO } from "./Piezas";

const ORDENES = [
  { clave: "riesgo", nombre: "Más riesgo primero" },
  { clave: "caida", nombre: "Los que más bajaron" },
  { clave: "venta", nombre: "Los que más compran" },
  { clave: "esperada", nombre: "Los que más van a comprar" },
  { clave: "cliente", nombre: "Número de cliente" },
];

function Riesgo({ v }: { v: number }) {
  const color = v >= 70 ? "bg-red-600" : v >= 40 ? "bg-amber-500" : "bg-slate-300 dark:bg-slate-600";
  return (
    <span className="inline-flex items-center gap-2" title={`Riesgo de dejar de comprar: ${v} de 100`}>
      <span className="w-14 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
        <span className={`block h-full ${color}`} style={{ width: `${v}%` }} />
      </span>
      <span className="text-xs tabular-nums text-slate-500 w-6">{v}</span>
    </span>
  );
}

export default function ListaClientes({ segmento, onSegmento, ultimoMes }: {
  segmento: string | null; onSegmento: (s: string | null) => void; ultimoMes: string
}) {
  const [q, setQ] = useState("");
  const [buscar, setBuscar] = useState("");
  const [orden, setOrden] = useState("riesgo");
  // La página vale para un filtro: si cambia el filtro, se vuelve a la 1.
  const filtros = `${segmento ?? ""}|${buscar}|${orden}`;
  const [pag, setPag] = useState({ filtros, n: 1 });
  const pagina = pag.filtros === filtros ? pag.n : 1;
  const setPagina = (n: number) => setPag({ filtros, n });
  const pedido = `${filtros}|${pagina}`;
  const [datos, setDatos] = useState<{ total: number; por_pagina: number; filas: ClienteVip[] } | null>(null);
  const [listo, setListo] = useState<string | null>(null);
  const cargando = listo !== pedido;
  const [error, setError] = useState<string | null>(null);
  const [abierto, setAbierto] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setBuscar(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    let vigente = true;
    clientesVipApi.clientes({ segmento: segmento ?? undefined, q: buscar || undefined, orden, pagina })
      .then(({ data }) => { if (vigente) { setDatos(data); setError(null); } })
      .catch((e) => { if (vigente) setError(extractErrorDetail(e, "No se pudo traer la lista de clientes.")); })
      .finally(() => { if (vigente) setListo(pedido); });
    return () => { vigente = false; };
  }, [segmento, buscar, orden, pagina, pedido]);

  const paginas = datos ? Math.max(1, Math.ceil(datos.total / datos.por_pagina)) : 1;

  return (
    <div className={`${CAJA} p-5`}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className={TITULO}>Clientes {segmento ? <span className="font-normal text-slate-500">· {segmento}</span> : null}</h2>
          {segmento && <p className="text-xs text-slate-500 mt-0.5">{QUE_ES[segmento as Segmento]} · <button className="underline" onClick={() => onSegmento(null)}>ver todos</button></p>}
        </div>
        <div className="flex gap-2 flex-wrap">
          <label className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Número, sucursal o categoría"
                   className="pl-8 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-transparent text-sm w-56" />
          </label>
          <select value={orden} onChange={(e) => setOrden(e.target.value)} aria-label="Ordenar"
                  className="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-transparent text-sm">
            {ORDENES.map((o) => <option key={o.clave} value={o.clave}>{o.nombre}</option>)}
          </select>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-700 dark:text-red-400">{error}</p>}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400">
              <th className="py-2 font-normal">Cliente</th>
              <th className="py-2 font-normal">Segmento</th>
              <th className="py-2 font-normal">Riesgo</th>
              <th className="py-2 font-normal text-right">12 meses</th>
              <th className="py-2 font-normal text-right">Últimos 3 vs antes</th>
              <th className="py-2 font-normal text-right hidden md:table-cell">Esperado próximo mes</th>
              <th className="py-2 font-normal hidden lg:table-cell pl-4">Compra más</th>
              <th className="py-2 font-normal hidden lg:table-cell">Sucursal</th>
            </tr>
          </thead>
          <tbody className={`divide-y divide-slate-100 dark:divide-slate-800 ${cargando ? "opacity-60" : ""}`}>
            {datos?.filas.map((c) => (
              <tr key={c.id_cliente} onClick={() => setAbierto(c.id_cliente)} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <td className="py-2 pr-3 tabular-nums font-medium text-slate-800 dark:text-slate-200">{c.id_cliente}</td>
                <td className="py-2 pr-3 whitespace-nowrap text-slate-600 dark:text-slate-300"><PuntoSegmento s={c.segmento} /> {c.segmento}</td>
                <td className="py-2 pr-3"><Riesgo v={c.riesgo} /></td>
                <td className="py-2 text-right tabular-nums text-slate-700 dark:text-slate-300">{plata(c.venta_12m)}</td>
                <td className="py-2 text-right whitespace-nowrap">
                  <span className="tabular-nums text-slate-600 dark:text-slate-300">{plata(c.venta_3m)}</span>{" "}
                  <Cambio v={variacion(c.venta_3m, c.venta_3m_antes)} />
                </td>
                <td className="py-2 text-right tabular-nums text-slate-600 dark:text-slate-300 hidden md:table-cell">{plata(c.venta_esperada)}</td>
                <td className="py-2 pl-4 text-slate-500 hidden lg:table-cell">{c.categoria ?? "—"}</td>
                <td className="py-2 text-slate-500 hidden lg:table-cell">{c.sucursal ?? "—"}</td>
              </tr>
            ))}
            {datos && !datos.filas.length && (
              <tr><td colSpan={8} className="py-6 text-center text-slate-500">Ningún cliente con ese filtro.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {datos && datos.total > datos.por_pagina && (
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span>{numero(datos.total)} clientes</span>
          <div className="flex items-center gap-2">
            <button disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)} className="px-2 py-1 rounded border border-slate-200 dark:border-slate-700 disabled:opacity-40">Anterior</button>
            <span>{pagina} de {paginas}</span>
            <button disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)} className="px-2 py-1 rounded border border-slate-200 dark:border-slate-700 disabled:opacity-40">Siguiente</button>
          </div>
        </div>
      )}

      {abierto !== null && <FichaCliente id={abierto} ultimoMes={ultimoMes} onCerrar={() => setAbierto(null)} />}
    </div>
  );
}

function FichaCliente({ id, ultimoMes, onCerrar }: { id: number; ultimoMes: string; onCerrar: () => void }) {
  const [datos, setDatos] = useState<{ cliente: ClienteVip | null; meses: MesDeCliente[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    clientesVipApi.cliente(id).then(({ data }) => setDatos(data))
      .catch((e) => setError(extractErrorDetail(e, "No se pudo traer el cliente.")));
  }, [id]);
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") onCerrar(); };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [onCerrar]);

  const c = datos?.cliente;
  const ult12 = (datos?.meses ?? []).slice(-12);
  const categorias = new Map<string, number>();
  for (const m of ult12) for (const k of m.categorias) categorias.set(k.nombre, (categorias.get(k.nombre) ?? 0) + k.venta);
  const top = [...categorias.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  // Los meses sin compras van en cero: si no, el gráfico parece terminar en su última compra.
  const porMes = new Map((datos?.meses ?? []).map((m) => [m.mes, m.venta]));
  const serie = datos?.meses.length
    ? mesesEntre(datos.meses[0].mes, ultimoMes).map((mes) => ({ mes, venta: porMes.get(mes) ?? 0 }))
    : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/30" onClick={onCerrar}>
      <div role="dialog" aria-modal="true" aria-label={`Cliente ${id}`} onClick={(e) => e.stopPropagation()}
           className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Cliente {id}</h3>
            {c && <p className="text-sm text-slate-500 mt-0.5"><PuntoSegmento s={c.segmento} /> {c.segmento} · {QUE_ES[c.segmento]}</p>}
          </div>
          <button onClick={onCerrar} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Cerrar"><X size={16} /></button>
        </div>
        {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
        {!datos && !error && <div className="py-10 flex justify-center"><Loader2 className="animate-spin text-slate-400" size={20} /></div>}
        {datos && (
          <>
            {c && (
              <dl className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <div><dt className="text-xs text-slate-500">12 meses</dt><dd className="font-medium tabular-nums">{plata(c.venta_12m)}</dd></div>
                <div><dt className="text-xs text-slate-500">Margen</dt><dd className="font-medium tabular-nums">{c.venta_12m ? `${numero((100 * c.margen_12m) / c.venta_12m, 1)}%` : "—"}</dd></div>
                <div><dt className="text-xs text-slate-500">Riesgo</dt><dd className="font-medium tabular-nums">{c.riesgo} de 100</dd></div>
                <div><dt className="text-xs text-slate-500">Esperado próximo mes</dt><dd className="font-medium tabular-nums">{plata(c.venta_esperada)}</dd></div>
                <div><dt className="text-xs text-slate-500">Compras en 12 meses</dt><dd className="font-medium tabular-nums">{numero(c.tickets_12m)}</dd></div>
                <div><dt className="text-xs text-slate-500">Meses con compra</dt><dd className="font-medium tabular-nums">{c.meses_con_compra} de 12</dd></div>
                <div><dt className="text-xs text-slate-500">Compra online</dt><dd className="font-medium tabular-nums">{c.parte_ecommerce}%</dd></div>
                <div><dt className="text-xs text-slate-500">Última compra</dt><dd className="font-medium">{c.ultimo_mes ? mesLargo(c.ultimo_mes) : "—"}</dd></div>
              </dl>
            )}
            <div className="h-40 mt-6" role="img" aria-label="Venta del cliente por mes">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={serie} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} barCategoryGap="20%">
                  <XAxis dataKey="mes" tickFormatter={mesCorto} tickLine={false} axisLine={false} tick={{ fontSize: 10 }}
                         className="[&_text]:fill-slate-400" interval="preserveStartEnd" minTickGap={6} />
                  <Tooltip cursor={{ className: "fill-slate-100 dark:fill-slate-800" }}
                           formatter={(v) => [plata(Number(v)), "Venta"]} labelFormatter={(m) => mesLargo(String(m))} />
                  <Bar dataKey="venta" radius={[4, 4, 0, 0]} isAnimationActive={false} fill="#2a78d6" className="fill-[#2a78d6] dark:fill-[#3987e5]" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            {top.length > 0 && (
              <div className="mt-5">
                <p className="text-xs text-slate-500 mb-2">Lo que más compra (12 meses)</p>
                <ul className="text-sm space-y-1">
                  {top.map(([n, v]) => (
                    <li key={n} className="flex justify-between gap-3"><span className="text-slate-700 dark:text-slate-300">{n}</span><span className="tabular-nums text-slate-500">{plata(v)}</span></li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
