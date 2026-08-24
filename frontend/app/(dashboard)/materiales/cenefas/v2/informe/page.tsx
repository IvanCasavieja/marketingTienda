"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api, type CenefaInforme } from "@/lib/api";
import { useSuperuserGuard } from "@/hooks/useSuperuserGuard";

// Informe de produccion de cenefas.
//
// Responde "cuanto se hizo y cuanto vale": cada cenefa disenada tiene un
// costo y ese es el criterio con el que se valoriza el trabajo. Cada corrida
// cuenta por separado aunque sea el mismo listado reprocesado -- es trabajo
// pedido a la herramienta.
//
// Solo entran las corridas confirmadas. Una en "preview" es una
// previsualizacion que nadie confirmo, y una en "error" no produjo nada.

const numero = (n: number) => n.toLocaleString("es-UY");
const pesos = (n: number) => `$${Math.round(n).toLocaleString("es-UY")}`;

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
  const [marcando, setMarcando] = useState<string | null>(null);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [plantilla, setPlantilla] = useState("");
  const [costo, setCosto] = useState(45);
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

  async function bajarExcel() {
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
        <button
          onClick={bajarExcel}
          disabled={bajando || !data}
          className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 disabled:opacity-40"
        >
          {bajando ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
          Bajar en Excel
        </button>
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
            Costo por cenefa
          </span>
          <input
            type="number" min={0} step={1} className="input text-sm w-full" value={costo}
            onChange={(e) => setCosto(Math.max(0, Number(e.target.value) || 0))}
          />
        </label>
      </div>

      {cargando && (
        <div className="card p-10 flex items-center justify-center text-slate-400">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}

      {!cargando && t && (
        <>
          {/* Lo que importa: cuanto se hizo y cuanto vale */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { etiqueta: "Cenefas generadas", valor: numero(t.cenefas),
                pie: `${numero(t.corridas)} corridas` },
              { etiqueta: "Salieron correctas", valor: numero(t.correctas),
                pie: t.cenefas ? `${((t.correctas * 100) / t.cenefas).toFixed(1)}% del total` : "—",
                acento: "text-emerald-600 dark:text-emerald-400" },
              { etiqueta: "Valor total", valor: pesos(t.costo),
                pie: `a ${pesos(data.costo_unitario)} por cenefa` },
              { etiqueta: "Verificadas a mano", valor: numero(t.verificadas),
                pie: `${numero(t.verificadas_corridas)} de ${numero(t.corridas)} corridas · ${pesos(t.costo_verificadas)}`,
                acento: "text-brand-600 dark:text-brand-400" },
            ].map((c) => (
              <div key={c.etiqueta} className="card p-4">
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
              <span className="text-amber-600 dark:text-amber-400">
                <b>{numero(t.avisos)}</b> salieron con algo para revisar
              </span>
              <span className="text-rose-600 dark:text-rose-400">
                <b>{numero(t.criticos)}</b> no se pudieron armar
              </span>
            </div>
          )}

          <Tabla titulo="Por mes" primeraColumna="Mes"
                 filas={data.por_mes.map((m) => ({ clave: m.mes, etiqueta: nombreDeMes(m.mes), ...m }))} />

          <Tabla titulo="Por plantilla" primeraColumna="Plantilla"
                 filas={data.por_plantilla.map((p) => ({ clave: p.plantilla, etiqueta: p.plantilla, ...p }))} />

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
                      {["Fecha", "Plantilla", "Excel", "Cenefas", "Correctas", "Valor"].map((h, i) => (
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
                        <td className="px-3 py-1.5 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                          {numero(d.correctas)}
                        </td>
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
            «Correctas» es lo que no encontró problemas la validación automática al generar.
            «Salió bien» es lo que confirmó una persona abriendo el archivo — queda registrado
            quién y cuándo. Solo se cuentan las corridas confirmadas, y cada una cuenta por
            separado aunque sea el mismo listado reprocesado. Hasta el 23/08/2026 no se guardaba
            qué plantilla ni qué Excel se había usado, así que esas corridas aparecen como
            «sin registrar».
          </p>
        </>
      )}
    </div>
  );
}

interface FilaTabla {
  clave: string;
  etiqueta: string;
  corridas: number;
  cenefas: number;
  correctas: number;
  costo: number;
}

function Tabla({ titulo, primeraColumna, filas }: {
  titulo: string; primeraColumna: string; filas: FilaTabla[];
}) {
  if (filas.length === 0) return null;
  return (
    <div className="card p-0 overflow-hidden">
      <p className="px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-widest">
        {titulo}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead className="bg-slate-100 dark:bg-slate-800">
            <tr>
              {[primeraColumna, "Corridas", "Cenefas", "Correctas", "Valor"].map((h, i) => (
                <th key={h}
                    className={`px-3 py-2 font-semibold text-slate-500 dark:text-slate-300 uppercase tracking-wide text-[10px] ${i ? "text-right" : "text-left"}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.clave} className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300 max-w-[320px] truncate"
                    title={f.etiqueta}>{f.etiqueta}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500">{numero(f.corridas)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{numero(f.cenefas)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                  {numero(f.correctas)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">{pesos(f.costo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
