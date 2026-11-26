"use client";
// La carga del archivo mensual de Clientes VIP: el navegador lo lee (en un
// Web Worker, lib/clientes-vip/lector.worker.ts), muestra qué trae y sube solo
// el resumen, en tandas. Ver lib/clientes-vip/resumen.ts.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileUp, Loader2, X, CheckCircle2, AlertTriangle } from "lucide-react";
import { clientesVipApi } from "@/lib/api";
import { extractErrorDetail } from "@/lib/errors";
import type { Resumen } from "@/lib/clientes-vip/resumen";
import type { ParteDetalle } from "@/lib/clientes-vip/detalle";
import type { MensajeDelLector } from "@/lib/clientes-vip/lector.worker";
import { mesLargo, numero, plata } from "@/lib/clientes-vip/tipos";

const POR_TANDA = 5000;

type Paso =
  | { tipo: "elegir" }
  | { tipo: "leyendo"; nombre: string; leido: number; total: number; filas: number }
  | { tipo: "comprimiendo"; nombre: string; partes: number }
  | { tipo: "revisar"; archivo: File; resumen: Resumen; detalle: ParteDetalle[] }
  | { tipo: "subiendo"; hecho: number; total: number }
  | { tipo: "listo"; clientes: number; meses: string[] }
  | { tipo: "error"; mensaje: string };

/** Las filas que no entran, con su número y el porqué, para saber cuál
 *  corregir en el archivo (H-088, 26/11/2026: con una fecha «30/13/2019» se
 *  rebotaba la carga entera sin decir qué fila era). */
function FilasQueNoEntran({ r }: { r: Resumen }) {
  const { t } = useTranslation();
  const resto = r.descartadas - r.primerasDescartadas.length;
  return (
    <div className="mt-3 text-sm text-amber-700 dark:text-amber-400">
      <p>{t("clientesVip.carga.noEntran", { count: r.descartadas, n: numero(r.descartadas) })}</p>
      <ul className="mt-1 pl-5 list-disc space-y-0.5">
        {r.primerasDescartadas.map((d) => (
          <li key={`${d.archivo}|${d.fila}`}>
            {d.archivo
              ? t("clientesVip.carga.filaDe", { fila: numero(d.fila), archivo: d.archivo })
              : t("clientesVip.carga.fila", { fila: numero(d.fila) })}
            {": "}
            {t(`clientesVip.carga.motivo.${d.motivo}`, { dato: d.dato })}
          </li>
        ))}
        {resto > 0 && <li>{t("clientesVip.carga.yMas", { count: resto, n: numero(resto) })}</li>}
      </ul>
      <p className="mt-1">{t(r.filas.length ? "clientesVip.carga.queHacer" : "clientesVip.carga.ningunaSirve")}</p>
    </div>
  );
}

async function conReintento<T>(fn: () => Promise<T>, veces = 3): Promise<T> {
  for (let i = 1; ; i++) {
    try {
      return await fn();
    } catch (err) {
      const estado = (err as { response?: { status?: number } })?.response?.status;
      // Un 4xx no se arregla reintentando (datos, permisos, base llena).
      if (i >= veces || (estado && estado < 500)) throw err;
      await new Promise((r) => setTimeout(r, 1500 * i));
    }
  }
}

export default function CargarArchivo({
  mesesCargados, onCerrar, onCargado,
}: { mesesCargados: string[]; onCerrar: () => void; onCargado: () => void }) {
  const [paso, setPaso] = useState<Paso>({ tipo: "elegir" });
  const [arrastrando, setArrastrando] = useState(false);
  const lector = useRef<Worker | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => lector.current?.terminate(), []);

  function leer(archivo: File) {
    if (!/\.(csv|zip)$/i.test(archivo.name)) {
      setPaso({ tipo: "error", mensaje: "Tiene que ser un .csv o un .zip con el CSV adentro. Si es un Excel, guardalo como CSV (separado por punto y coma)." });
      return;
    }
    lector.current?.terminate();
    const w = new Worker(new URL("../../lib/clientes-vip/lector.worker.ts", import.meta.url));
    lector.current = w;
    setPaso({ tipo: "leyendo", nombre: archivo.name, leido: 0, total: archivo.size, filas: 0 });
    w.onmessage = (e: MessageEvent<MensajeDelLector>) => {
      const m = e.data;
      if (m.tipo === "avance") setPaso({ tipo: "leyendo", nombre: archivo.name, leido: m.leido, total: m.total, filas: m.filas });
      else if (m.tipo === "comprimiendo") setPaso({ tipo: "comprimiendo", nombre: archivo.name, partes: m.partes });
      else if (m.tipo === "listo") { setPaso({ tipo: "revisar", archivo, resumen: m.resumen, detalle: m.detalle }); w.terminate(); }
      else { setPaso({ tipo: "error", mensaje: m.mensaje }); w.terminate(); }
    };
    w.onerror = () => setPaso({ tipo: "error", mensaje: "El navegador no pudo leer el archivo. Probá de nuevo con Chrome o Edge actualizados." });
    w.postMessage({ archivo });
  }

  async function subir(archivo: File, r: Resumen, detalle: ParteDetalle[]) {
    const total = Math.ceil(r.filas.length / POR_TANDA) + detalle.length + 1;
    setPaso({ tipo: "subiendo", hecho: 0, total });
    try {
      const { data: carga } = await conReintento(() => clientesVipApi.empezar({
        archivo: archivo.name, meses: r.meses, filas_archivo: r.filasArchivo, filas: r.filas.length,
      }));
      for (let i = 0, n = 0; i < r.filas.length; i += POR_TANDA, n++) {
        const tanda = r.filas.slice(i, i + POR_TANDA);
        await conReintento(() => clientesVipApi.tanda(carga.id, tanda));
        setPaso({ tipo: "subiendo", hecho: n + 1, total });
      }
      // El detalle para Valentina (lo que pidió Emilia), en partes comprimidas.
      const base = Math.ceil(r.filas.length / POR_TANDA);
      for (let i = 0; i < detalle.length; i++) {
        await conReintento(() => clientesVipApi.detalle(carga.id, detalle[i]));
        setPaso({ tipo: "subiendo", hecho: base + i + 1, total });
      }
      const { data } = await conReintento(() => clientesVipApi.terminar(carga.id, {
        dimensiones: r.dimensiones, clientes: r.clientes, venta: r.venta,
      }));
      setPaso({ tipo: "listo", clientes: data.clientes, meses: r.meses });
      onCargado();
    } catch (err) {
      setPaso({ tipo: "error", mensaje: extractErrorDetail(err, "No se pudo terminar la carga. Probá de nuevo: lo que ya estaba no se perdió.") });
    }
  }

  const caja = "rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5";

  return (
    <section className={caja} aria-label="Cargar archivo de clientes VIP">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">Cargar el archivo del mes</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            El CSV de compras de los clientes VIP, o el .zip que lo trae. Se lee en tu computadora: solo se sube el resumen.
          </p>
        </div>
        <button onClick={onCerrar} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Cerrar">
          <X size={16} />
        </button>
      </div>

      {paso.tipo === "elegir" && (
        <div
          onDragOver={(e) => { e.preventDefault(); setArrastrando(true); }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={(e) => { e.preventDefault(); setArrastrando(false); const f = e.dataTransfer.files?.[0]; if (f) leer(f); }}
          className={`rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${arrastrando ? "border-slate-500 bg-slate-50 dark:bg-slate-800" : "border-slate-200 dark:border-slate-700"}`}
        >
          <FileUp size={22} className="mx-auto text-slate-400 mb-3" />
          <p className="text-sm text-slate-600 dark:text-slate-300">Arrastrá el archivo acá o</p>
          <button onClick={() => input.current?.click()} className="mt-2 btn-primary text-sm">Elegir archivo</button>
          <input ref={input} type="file" accept=".csv,.zip" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) leer(f); e.target.value = ""; }} />
        </div>
      )}

      {paso.tipo === "leyendo" && (
        <div className="py-4">
          <div className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <Loader2 size={15} className="animate-spin" /> Leyendo {paso.nombre}…
          </div>
          <div className="mt-3 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div className="h-full bg-slate-700 dark:bg-slate-300 transition-[width] duration-300" style={{ width: `${Math.min(100, (100 * paso.leido) / Math.max(1, paso.total))}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">{numero(paso.filas)} filas leídas · un archivo de un año tarda alrededor de un minuto</p>
        </div>
      )}

      {paso.tipo === "comprimiendo" && (
        <div className="py-4 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <Loader2 size={15} className="animate-spin" /> Preparando el detalle para Valentina… {paso.partes > 0 ? `(${paso.partes} partes)` : ""}
        </div>
      )}

      {paso.tipo === "revisar" && (() => {
        const r = paso.resumen;
        const pisa = r.meses.filter((m) => mesesCargados.includes(m));
        const hayFilas = r.filas.length > 0;
        return (
          <div>
            {hayFilas && <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div><dt className="text-slate-500">Meses</dt><dd className="font-medium text-slate-900 dark:text-slate-100">{mesLargo(r.meses[0])}{r.meses.length > 1 ? ` a ${mesLargo(r.meses[r.meses.length - 1])}` : ""}</dd></div>
              <div><dt className="text-slate-500">Clientes</dt><dd className="font-medium text-slate-900 dark:text-slate-100">{numero(r.clientes)}</dd></div>
              <div><dt className="text-slate-500">Venta</dt><dd className="font-medium text-slate-900 dark:text-slate-100">{plata(r.venta)}</dd></div>
              <div><dt className="text-slate-500">Filas del archivo</dt><dd className="font-medium text-slate-900 dark:text-slate-100">{numero(r.filasArchivo)}</dd></div>
            </dl>}
            {r.descartadas > 0 && <FilasQueNoEntran r={r} />}
            {pisa.length > 0 && (
              <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                Ya había datos de {pisa.length === 1 ? mesLargo(pisa[0]) : `${pisa.length} de estos meses`}: se reemplazan por los de este archivo.
              </p>
            )}
            <div className="mt-5 flex gap-2">
              {hayFilas && <button onClick={() => subir(paso.archivo, r, paso.detalle)} className="btn-primary text-sm">Cargar {r.meses.length === 1 ? "el mes" : `los ${r.meses.length} meses`}</button>}
              <button onClick={() => setPaso({ tipo: "elegir" })}
                      className={hayFilas ? "px-3 py-2 rounded-lg text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" : "btn-primary text-sm"}>Elegir otro</button>
            </div>
          </div>
        );
      })()}

      {paso.tipo === "subiendo" && (
        <div className="py-4">
          <div className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <Loader2 size={15} className="animate-spin" /> Subiendo el resumen…
          </div>
          <div className="mt-3 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div className="h-full bg-slate-700 dark:bg-slate-300 transition-[width] duration-300" style={{ width: `${(100 * paso.hecho) / paso.total}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">No cierres esta pestaña hasta que termine.</p>
        </div>
      )}

      {paso.tipo === "listo" && (
        <div className="flex items-start gap-3 py-2">
          <CheckCircle2 size={18} className="text-emerald-600 mt-0.5 shrink-0" />
          <div className="text-sm text-slate-700 dark:text-slate-200">
            <p className="font-medium">Listo: {numero(paso.clientes)} clientes con datos hasta {mesLargo(paso.meses[paso.meses.length - 1])}.</p>
            <p className="text-slate-500 dark:text-slate-400 mt-0.5">Valentina, la economista del Escuadrón Lechuza, los analiza en su próxima vuelta (de lunes a viernes, cada hora de 8 a 18): su informe aparece acá y les llega por mail a quienes tienen acceso.</p>
            <button onClick={onCerrar} className="mt-3 btn-primary text-sm">Ver el tablero</button>
          </div>
        </div>
      )}

      {paso.tipo === "error" && (
        <div className="flex items-start gap-3 py-2">
          <AlertTriangle size={18} className="text-red-600 mt-0.5 shrink-0" />
          <div className="text-sm">
            <p className="text-slate-700 dark:text-slate-200">{paso.mensaje}</p>
            <button onClick={() => setPaso({ tipo: "elegir" })} className="mt-3 btn-primary text-sm">Probar de nuevo</button>
          </div>
        </div>
      )}
    </section>
  );
}
