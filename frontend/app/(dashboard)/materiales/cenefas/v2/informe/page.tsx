"use client";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronLeft, ChevronRight, Download, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api, type CenefaInforme } from "@/lib/api";
import { useSuperuserGuard } from "@/hooks/useSuperuserGuard";

// Informe de produccion de cenefas.
//
// El numero que vale es el REAL: filas del listado x formatos distintos,
// sin contar de nuevo el reproceso (Ivan, 01/09). El bruto -- cada corrida
// contada de nuevo aunque sea el mismo listado -- queda solo como
// referencia, apagado y rotulado. La plata sale SIEMPRE de reales x costo.
//
// Solo entran las corridas confirmadas. Una en "preview" es una
// previsualizacion que nadie confirmo, y una en "error" no produjo nada.

const numero = (n: number) => n.toLocaleString("es-UY");
const pesos = (n: number) => `$${Math.round(n).toLocaleString("es-UY")}`;

// El costo vigente acordado el 01/09. El campo editable existe para poder
// cambiar el precio sin deploy, pero cualquier otro valor es una simulacion
// y la pantalla lo marca.
const COSTO_VIGENTE = 49;

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre",
];

function nombreDeMes(ym: string) {
  const [a, m] = ym.split("-");
  return `${MESES[Number(m) - 1] ?? m} ${a}`;
}

export default function InformePage() {
  const allowed = useSuperuserGuard();
  const [data, setData] = useState<CenefaInforme | null>(null);
  const [cargando, setCargando] = useState(true);
  const [bajando, setBajando] = useState(false);
  const [bajandoPdf, setBajandoPdf] = useState(false);
  const [marcando, setMarcando] = useState<string | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [plantilla, setPlantilla] = useState("");
  const [costo, setCosto] = useState(COSTO_VIGENTE);
  // Lo tipeado no se aplica hasta blur/Enter: aplicar por tecla refetcheaba
  // el informe entero con costos intermedios ("55" pasaba por 5) y borrar
  // el campo lo dejaba momentaneamente valuado en $0.
  const [costoInput, setCostoInput] = useState(String(COSTO_VIGENTE));
  const dlRef = useRef<HTMLAnchorElement>(null);

  const params = useCallback(
    () => ({
      desde: desde || undefined,
      hasta: hasta || undefined,
      template: plantilla || undefined,
      costo,
    }),
    [desde, hasta, plantilla, costo],
  );

  useEffect(() => {
    let vivo = true;
    setCargando(true);
    cenefasV2Api
      .getInforme(params())
      .then(({ data }) => { if (vivo) setData(data); })
      .catch(() => { if (vivo) toast.error("No se pudo cargar el informe"); })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [params]);

  // Marca una corrida como revisada. Se actualiza en el acto tanto la fila
  // como los totales, para no volver a pedir el informe entero por un click.
  async function alternarVerificado(id: string, verificado: boolean, cenefas: number) {
    setMarcando(id);
    try {
      await cenefasV2Api.verificarCorrida(id, verificado);
      setData((prev) => {
        if (!prev) return prev;
        const signo = verificado ? 1 : -1;
        return {
          ...prev,
          total: {
            ...prev.total,
            verificadas_corridas: prev.total.verificadas_corridas + signo,
            verificadas: prev.total.verificadas + signo * cenefas,
            costo_verificadas: prev.total.costo_verificadas + signo * cenefas * prev.costo_unitario,
          },
          detalle: prev.detalle?.map((d) => (d.id === id ? { ...d, verificado } : d)),
        };
      });
    } catch {
      toast.error("No se pudo guardar la verificación");
    } finally {
      setMarcando(null);
    }
  }

  // Si el costo en pantalla no es el vigente, lo que se baja es una
  // simulacion: se avisa antes de generar un archivo que alguien puede mandar.
  function confirmarCostoSimulado(): boolean {
    if (costo === COSTO_VIGENTE) return true;
    return window.confirm(
      `Estás por bajar el informe valuado a $${costo} por cenefa, ` +
      `distinto del vigente ($${COSTO_VIGENTE}). ¿Seguro?`,
    );
  }

  async function bajarExcel() {
    if (!confirmarCostoSimulado()) return;
    setBajando(true);
    try {
      const { data: blob } = await cenefasV2Api.downloadInforme(params());
      const url = URL.createObjectURL(new Blob([blob as BlobPart]));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = "informe_cenefas.xlsx";
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
    } catch {
      toast.error("No se pudo generar el Excel");
    } finally {
      setBajando(false);
    }
  }

  // El PDF es el que se manda como informe semanal: lo real adelante y el
  // respaldo detras. El Excel queda para auditar corrida por corrida.
  async function bajarPdf() {
    if (!confirmarCostoSimulado()) return;
    setBajandoPdf(true);
    try {
      const { data: blob } = await cenefasV2Api.downloadInformePdf(params());
      const url = URL.createObjectURL(new Blob([blob as BlobPart]));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = "informe_semanal_cenefas.pdf";
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
    } catch {
      toast.error("No se pudo generar el PDF");
    } finally {
      setBajandoPdf(false);
    }
  }

  if (!allowed) return null;

  const t = data?.total;

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">
      <a ref={dlRef} className="hidden" />

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Link
            href="/materiales/cenefas/v2"
            className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ChevronLeft size={18} />
          </Link>
          <div>
            <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">
              Informe de producción
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t?.desde
                ? `Cenefas generadas entre el ${t.desde.slice(0, 10)} y el ${t.hasta?.slice(0, 10)}`
                : "Cenefas generadas y confirmadas"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={bajarPdf}
            disabled={bajandoPdf || !data}
            className="btn-primary text-xs px-3 py-2 flex items-center gap-1.5 disabled:opacity-40"
          >
            {bajandoPdf ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            Bajar en PDF
          </button>
          <button
            onClick={bajarExcel}
            disabled={bajando || !data}
            className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 disabled:opacity-40"
          >
            {bajando ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            Bajar en Excel
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="card p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">Desde</span>
          <input type="date" className="input text-sm w-full" value={desde}
                 onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">Hasta</span>
          <input type="date" className="input text-sm w-full" value={hasta}
                 onChange={(e) => setHasta(e.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">Plantilla</span>
          <select className="input text-sm w-full" value={plantilla}
                  onChange={(e) => setPlantilla(e.target.value)}>
            <option value="">Todas</option>
            {(data?.plantillas ?? []).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">
            Costo por cenefa · vigente ${COSTO_VIGENTE}
          </span>
          <input
            type="number" min={0} step={1} className="input text-sm w-full" value={costoInput}
            onChange={(e) => setCostoInput(e.target.value)}
            onBlur={() => setCosto(Math.max(0, Number(costoInput) || 0) || COSTO_VIGENTE)}
            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
          />
        </label>
      </div>

      {costo !== COSTO_VIGENTE && (
        <div className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 rounded-lg px-3 py-2">
          <span>
            Estás viendo una <b>simulación a ${numero(costo)}</b> por cenefa — el costo
            vigente es ${COSTO_VIGENTE}. Todos los montos de la página (y lo que bajes
            en PDF o Excel) usan el costo simulado.
          </span>
        </div>
      )}

      {cargando && (
        <div className="card p-10 flex items-center justify-center text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {!cargando && t && (
        <>
          {/* Lo que importa: cuanto hacia falta de verdad y cuanto vale. El
              real va primero -- es la respuesta a "cuanto se trabajo", no el
              bruto con reproceso. */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { etiqueta: "Cenefas reales", valor: numero(data.cobrable.cenefas_reales_totales),
                pie: "listado × formato distinto, sin contar el reproceso",
                acento: "text-emerald-600 dark:text-emerald-400", clase: "" },
              { etiqueta: "Valor real", valor: pesos(data.cobrable.costo_real_total),
                pie: `a ${pesos(data.costo_unitario)} c/u`,
                acento: "text-emerald-600 dark:text-emerald-400", clase: "" },
              // La tarjeta de «Salió bien» solo aparece cuando alguien la
              // esta usando: un "0 de 432 · $0" gigante lee como que nada
              // salio bien, cuando en realidad nadie tildo el check todavia.
              ...(t.verificadas_corridas > 0 ? [
                { etiqueta: "Con «Salió bien» tildado", valor: numero(t.verificadas),
                  pie: `${numero(t.verificadas_corridas)} de ${numero(t.corridas)} corridas · ${pesos(t.costo_verificadas)}`,
                  acento: "text-brand-600 dark:text-brand-400", clase: "" },
              ] : []),
              // Bruto: todo lo que paso por el motor, contando cada pasada.
              // Referencia para auditar, apagado y al final. Cuando la
              // tarjeta de verificadas esta oculta, ocupa dos columnas para
              // que la fila quede completa (Ivan, 01/09) y el pie alcanza
              // para explicar que significa en vez de solo negarlo.
              { etiqueta: "Bruto medido (con reproceso)", valor: numero(t.cenefas),
                pie: `${numero(t.corridas)} corridas — acá cada pasada cuenta, aunque sea el mismo listado reprocesado hasta que salió bien. Referencia para auditar el trabajo de la máquina`,
                acento: "text-slate-400 dark:text-slate-500",
                clase: t.verificadas_corridas > 0 ? "" : "sm:col-span-2 lg:col-span-2" },
            ].map((c) => (
              <div key={c.etiqueta} className={`card p-4 ${c.clase}`}>
                <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">
                  {c.etiqueta}
                </p>
                <p className={`text-2xl font-bold mt-1 ${c.acento ?? "text-slate-800 dark:text-slate-100"}`}>
                  {c.valor}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">{c.pie}</p>
              </div>
            ))}
          </div>

          {(t.avisos > 0 || t.criticos > 0) && (
            <div className="card p-4 flex gap-6 flex-wrap text-sm">
              <span className="text-slate-400 text-xs uppercase tracking-widest font-semibold">
                Bruto, con reproceso:
              </span>
              <span className="text-amber-600 dark:text-amber-400">
                <b>{numero(t.avisos)}</b> salieron con algo para revisar
              </span>
              <span className="text-rose-600 dark:text-rose-400">
                <b>{numero(t.criticos)}</b> no se pudieron armar
              </span>
            </div>
          )}

          {/* Mismo armado que el PDF semanal: primero los componentes de lo
              real (medido sin reproceso + declarado), el TOTAL REAL
              destacado, y recien despues el bruto como referencia apagada.
              "Cobrable/facturable" se reserva para lo real -- llamarle
              cobrable al bruto invitaba a tomar el numero inflado. */}
          <div className="card p-0 overflow-hidden">
            <p className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-widest">
              Qué se factura
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <tbody>
                  {[
                    { clave: "medido", etiqueta: "Medido (reales)",
                      detalle: (data.por_mundo
                        .filter((m) => m.cobrable && m.cenefas_reales)
                        .map((m) => `${m.nombre} (${numero(m.cenefas_reales!)})`)
                        .join(" + ") || "Mundos cobrables")
                        + " — listado × formatos distintos, sin contar de nuevo el reproceso",
                      cenefas: data.cobrable.cenefas_reales ?? 0,
                      costo: data.cobrable.costo_real ?? 0 },
                    ...data.declaradas.filter((d) => d.cobrable).map((d) => ({
                      clave: `dec-${d.mundo}`, etiqueta: `Declarado · ${d.nombre}`,
                      detalle: d.nota, cenefas: d.cenefas, costo: d.costo,
                    })),
                    { clave: "totalreal", etiqueta: "TOTAL REAL", real: true,
                      detalle: `Medido + declarado, a $${numero(costo)} por cenefa — este es el número que se factura`,
                      cenefas: data.cobrable.cenefas_reales_totales, costo: data.cobrable.costo_real_total },
                    { clave: "bruto", etiqueta: "Referencia: bruto medido", apagado: true,
                      detalle: "Todo lo que pasó por el motor; cada reproceso cuenta de nuevo. No se factura",
                      cenefas: data.cobrable.cenefas, costo: data.cobrable.costo },
                    { clave: "sincosto", etiqueta: "Sin costo", apagado: true,
                      detalle: "Mundos marcados sin costo (Redexpres, pruebas)",
                      cenefas: data.sin_costo.cenefas, costo: 0 },
                    // Ivan (01/09): esas ~25 mil fueron las pruebas de la
                    // puesta a punto -- mostrarlas esta bien, pero con su
                    // nombre real, no "sin clasificar" a secas.
                    { clave: "sinclas", etiqueta: "Pruebas iniciales (antes del 23/08)", apagado: true,
                      detalle: "La puesta a punto de la herramienta, sin mundo registrado. El trabajo real de esa etapa está declarado aparte y esto no se valoriza",
                      cenefas: data.sin_clasificar.cenefas, costo: 0 },
                  ].filter((f) => f.cenefas > 0 || f.clave === "totalreal").map((f) => (
                    <tr key={f.clave}
                        className={`border-b border-slate-100 dark:border-slate-800 ${
                          f.real ? "bg-slate-50 dark:bg-slate-800/40" : ""}`}>
                      <td className={`px-3 py-2 ${
                        f.real ? "font-semibold text-emerald-700 dark:text-emerald-400"
                               : f.apagado ? "text-slate-400" : "text-slate-700 dark:text-slate-300"}`}>
                        {f.etiqueta}
                        <span className="block text-[10px] text-slate-400 font-normal">{f.detalle}</span>
                      </td>
                      <td className={`px-3 py-2 text-right tabular-nums whitespace-nowrap ${
                        f.real ? "font-semibold text-emerald-700 dark:text-emerald-400"
                               : f.apagado ? "text-slate-400" : ""}`}>
                        {numero(f.cenefas)}
                      </td>
                      <td className={`px-3 py-2 text-right tabular-nums whitespace-nowrap ${
                        f.real ? "font-bold text-emerald-700 dark:text-emerald-400"
                               : f.apagado ? "text-slate-400" : "font-medium"}`}>
                        {pesos(f.costo)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Mismo criterio que el PDF: lo declarado entra como fila propia
              (Parrilla y Vinos no puede desaparecer por no tener corridas),
              lo sin costo va apagado, y "(sin clasificar)" -- que no es lo
              mismo que sin costo: no tiene mundo -- cierra la tabla. */}
          <Tabla titulo="Por mundo" primeraColumna="Mundo"
                 filas={[
                   ...data.por_mundo.filter((m) => m.mundo).map((m) => ({
                     clave: m.mundo,
                     etiqueta: m.cobrable ? m.nombre : `${m.nombre} · sin costo`,
                     apagada: !m.cobrable,
                     corridas: m.corridas, cenefas: m.cenefas,
                     cenefas_reales: m.cenefas_reales, costo_real: m.costo_real,
                     costo: m.costo,
                   })),
                   ...data.declaradas.filter((d) => d.cobrable).map((d) => ({
                     clave: `dec-${d.mundo}`,
                     etiqueta: `${d.nombre} · declarado`,
                     cenefas_reales: d.cenefas, costo_real: d.costo, costo: d.costo,
                   })),
                   ...data.por_mundo.filter((m) => !m.mundo).map((m) => ({
                     clave: "(sin clasificar)",
                     etiqueta: "Pruebas iniciales (antes del 23/08) — no se valoriza",
                     apagada: true,
                     corridas: m.corridas, cenefas: m.cenefas,
                     cenefas_reales: m.cenefas_reales, costo_real: 0, costo: 0,
                   })),
                 ]} />

          <Tabla titulo="Por mes" primeraColumna="Mes"
                 filas={data.por_mes.map((m) => ({ clave: m.mes, etiqueta: nombreDeMes(m.mes), ...m }))} />

          <Tabla titulo="Por plantilla" primeraColumna="Plantilla"
                 filas={data.por_plantilla.map((p) => ({ clave: p.plantilla, etiqueta: p.plantilla, ...p }))} />

          {/* Historial de intentos: el mismo listado se reprocesa varias veces
              hasta que sale bien; agrupado se ve cuantas llevo cada uno. */}
          {data.intentos && data.intentos.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
                  Historial de intentos
                </p>
                <span className="text-[11px] text-slate-400">
                  {numero(data.detalle?.length ? data.total.corridas : 0)} corridas
                  {" → "}{numero(data.intentos.length)} listados distintos
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-slate-100 dark:bg-slate-800">
                    <tr>
                      {["", "Listado", "Plantilla", "Intentos", "Cenefas", "Último"].map((h, i) => (
                        <th key={h || i}
                            className={`px-3 py-2 font-semibold text-slate-500 dark:text-slate-300 uppercase tracking-wide text-[10px] ${i > 2 ? "text-right" : "text-left"}`}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.intentos.map((g) => {
                      const clave = `${g.excel}|${g.plantilla}`;
                      const desplegado = abierto === clave;
                      return (
                        <Fragment key={clave}>
                          <tr
                              onClick={() => setAbierto(desplegado ? null : clave)}
                              className="border-b border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40">
                            <td className="px-3 py-2 text-slate-400 w-8">
                              {desplegado ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            </td>
                            <td className="px-3 py-2 text-slate-700 dark:text-slate-300 max-w-[260px] truncate"
                                title={g.sin_registrar ? "Sin nombre guardado: agrupado por formato y cantidad, puede juntar listados distintos" : g.excel}>
                              {g.excel}
                              {g.sin_registrar && (
                                <span className="ml-1.5 text-[10px] text-amber-600 dark:text-amber-400">sin nombre</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-slate-500 max-w-[220px] truncate" title={g.plantilla}>
                              {g.plantilla}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {g.intentos > 1 ? (
                                <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
                                  <RefreshCw size={10} /> {g.intentos}
                                </span>
                              ) : (
                                <span className="text-slate-400">1</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">{numero(g.cenefas)}</td>
                            <td className="px-3 py-2 text-right text-slate-500 whitespace-nowrap">
                              {(g.ultima ?? "").slice(0, 10)}
                            </td>
                          </tr>
                          {desplegado && g.detalle.map((d, i) => (
                            <tr key={d.id} className="bg-slate-50 dark:bg-slate-900/40 border-b border-slate-100 dark:border-slate-800">
                              <td />
                              <td colSpan={2} className="px-3 py-1 text-slate-500">
                                intento {i + 1} · {(d.fecha ?? "").slice(0, 16).replace("T", " ")}
                                {i === g.detalle.length - 1 && (
                                  <span className="ml-2 text-emerald-600 dark:text-emerald-400">el que quedó</span>
                                )}
                              </td>
                              <td className="px-3 py-1 text-right text-slate-400">
                                {d.criticos > 0 ? (
                                  <span className="text-rose-600 dark:text-rose-400">
                                    {numero(d.criticos)} sin armar
                                  </span>
                                ) : "limpio"}
                              </td>
                              <td className="px-3 py-1 text-right tabular-nums text-slate-500">{numero(d.cenefas)}</td>
                              <td />
                            </tr>
                          ))}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="px-4 py-3 text-[11px] text-slate-400 dark:text-slate-500">
                Un listado se reprocesa hasta que sale bien: acá cada grupo es un listado y adentro
                están sus intentos, del primero al último. Los marcados «sin nombre» son anteriores
                al 23/08/2026, cuando todavía no se guardaba qué Excel ni qué plantilla se usó — se
                agrupan por formato y cantidad de carteles, así que pueden estar juntando listados
                distintos que casualmente tenían el mismo tamaño.
              </p>
            </div>
          )}

          {data.detalle && data.detalle.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="px-4 py-3 flex items-center justify-between">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
                  Corrida por corrida
                </p>
                <span className="text-[11px] text-slate-400">
                  las {data.detalle.length} más recientes · el Excel trae todas
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-slate-100 dark:bg-slate-800">
                    <tr>
                      {["Fecha", "Plantilla", "Excel", "Cenefas", "Valor"].map((h, i) => (
                        <th key={h}
                            className={`px-3 py-2 font-semibold text-slate-500 dark:text-slate-300 uppercase tracking-wide text-[10px] ${i > 2 ? "text-right" : "text-left"}`}>
                          {h}
                        </th>
                      ))}
                      <th className="px-3 py-2 font-semibold text-slate-500 dark:text-slate-300 uppercase tracking-wide text-[10px] text-center whitespace-nowrap">
                        Salió bien
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.detalle.map((d) => (
                      <tr key={d.id} className="border-b border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-1.5 text-slate-500 whitespace-nowrap">
                          {(d.fecha ?? "").slice(0, 16).replace("T", " ")}
                        </td>
                        <td className="px-3 py-1.5 text-slate-700 dark:text-slate-300 max-w-[240px] truncate"
                            title={d.plantilla}>{d.plantilla}</td>
                        <td className="px-3 py-1.5 text-slate-500 max-w-[240px] truncate"
                            title={d.excel}>{d.excel}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{numero(d.cenefas)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-medium">{pesos(d.costo)}</td>
                        <td className="px-3 py-1.5 text-center">
                          <label className="inline-flex items-center justify-center cursor-pointer"
                                 title="Marcar esta corrida como revisada y correcta">
                            {marcando === d.id ? (
                              <Loader2 size={14} className="animate-spin text-slate-400" />
                            ) : (
                              <input
                                type="checkbox"
                                checked={d.verificado}
                                onChange={(e) => alternarVerificado(d.id, e.target.checked, d.cenefas)}
                                className="w-4 h-4 rounded border-slate-300 dark:border-slate-600 text-brand-600 focus:ring-brand-500 cursor-pointer"
                              />
                            )}
                          </label>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <p className="text-[11px] text-slate-400 dark:text-slate-500">
            «Reales» = filas del listado × formatos distintos generados, sin pagar de nuevo el
            reproceso — es el número que se factura. «Brutas» = todo lo que pasó por el motor,
            solo referencia. «Declarado» = producción anterior al registro en la plataforma,
            con su nota de respaldo. «Salió bien» es el check opcional de una persona que abrió
            el archivo — queda registrado quién y cuándo. Solo se cuentan las corridas
            confirmadas. Hasta el 23/08/2026 no se guardaba qué plantilla ni qué Excel se había
            usado, así que esas corridas aparecen como «sin registrar».
          </p>
        </>
      )}
    </div>
  );
}

interface FilaTabla {
  clave: string;
  etiqueta: string;
  corridas?: number;
  cenefas?: number;
  cenefas_reales?: number;
  costo_real?: number;
  costo: number;
  apagada?: boolean;
}

function Tabla({ titulo, primeraColumna, filas }: {
  titulo: string; primeraColumna: string; filas: FilaTabla[];
}) {
  if (filas.length === 0) return null;
  // La columna de reales solo existe donde el backend la calcula (por mundo
  // y por mes); por plantilla no tiene sentido, cada fila ES un formato.
  // Donde hay reales, la plata es "Valor real" (reales cobrables x costo,
  // mismo criterio que el PDF); donde no, el bruto va rotulado y apagado
  // como referencia -- nunca "Valor" a secas.
  const conReales = filas.some((f) => f.cenefas_reales !== undefined);
  const headers = [primeraColumna, "Corridas", "Brutas",
                   ...(conReales ? ["Reales", "Valor real"] : ["Valor bruto (ref.)"])];
  return (
    <div className="card p-0 overflow-hidden">
      <p className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-widest">
        {titulo}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead className="bg-slate-100 dark:bg-slate-800">
            <tr>
              {headers.map((h, i) => (
                <th key={h}
                    className={`px-3 py-2 font-semibold text-slate-500 dark:text-slate-300 uppercase tracking-wide text-[10px] ${i ? "text-right" : "text-left"}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.clave}
                  className={`border-b border-slate-100 dark:border-slate-800 ${
                    f.apagada ? "text-slate-400 dark:text-slate-500" : ""}`}>
                <td className={`px-3 py-2 max-w-[340px] truncate ${
                      f.apagada ? "" : "text-slate-700 dark:text-slate-300"}`}
                    title={f.etiqueta}>{f.etiqueta}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500 dark:text-slate-500">
                  {f.corridas !== undefined ? numero(f.corridas) : "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500 dark:text-slate-500">
                  {f.cenefas !== undefined ? numero(f.cenefas) : "—"}
                </td>
                {conReales && (
                  <td className={`px-3 py-2 text-right tabular-nums font-medium ${
                    f.apagada ? "" : "text-emerald-600 dark:text-emerald-400"}`}>
                    {f.cenefas_reales !== undefined ? numero(f.cenefas_reales) : "—"}
                  </td>
                )}
                <td className={`px-3 py-2 text-right tabular-nums ${
                  conReales && !f.apagada ? "font-medium" : ""}`}>
                  {conReales
                    ? (f.costo_real ? pesos(f.costo_real) : "—")
                    : pesos(f.costo)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
