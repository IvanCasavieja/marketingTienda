"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, Layers, ShieldAlert } from "lucide-react";
import { entregasApi } from "@/lib/api";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { COLUMNAS, numero, proximoPaso, type Metricas, type MomentoEntrega, type Tarjeta } from "@/lib/calendario/entregas";
import { hoyIso } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";
import { SEGUNDOS_ENTRE_REVISIONES } from "@/lib/calendario/store";
import { mundoEfectivo, useMundoElegido } from "@/lib/mundos";
import { useVistaEntregas } from "@/store/entregas";
import { TarjetaEntrega } from "@/components/calendario/entregas/TarjetaEntrega";

/**
 * El tablero de entregas de un mundo, como el de Trello con la agencia:
 * cuatro columnas (le toca a la agencia, para revisar, volvió con cambios,
 * aprobadas) y una tarjeta por tarea que lleva entregas. Arriba, cuánto
 * retrabajo hubo. Lo que es de quien mira va primero en cada columna.
 *
 * `/entregas?tarea=ta-xxx` abre esa tarea encima: es a donde lleva un aviso
 * de la campanita.
 */

const COLOR_COLUMNA: Record<MomentoEntrega, string> = {
  produccion: "bg-sky-500",
  revision: "bg-amber-500",
  cambios: "bg-rose-500",
  aprobada: "bg-emerald-500",
};

function AbrirTareaDeLaUrl() {
  const params = useSearchParams();
  const router = useRouter();
  const tarea = params.get("tarea");
  useEffect(() => {
    if (!tarea) return;
    useVistaEntregas.getState().abrir(tarea);
    router.replace("/entregas");
  }, [tarea, router]);
  return null;
}

export default function EntregasPage() {
  const { allowed, checked, user } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });
  const elegido = useMundoElegido(s => s.elegido);
  const mundo = mundoEfectivo(user, elegido);
  const cambios = useVistaEntregas(s => s.cambios);
  const [datos, setDatos] = useState<{ mundo: string; tarjetas: Tarjeta[]; metricas: Metricas } | null>(null);
  const [error, setError] = useState(false);
  const [dias, setDias] = useState(90);
  const [pestana, setPestana] = useState<MomentoEntrega | null>(null);
  const rev = useRef<number | null>(null);
  const claveMundo = mundo?.clave;

  const cargar = useCallback(async (desdeCero: boolean) => {
    if (!claveMundo) return;
    try {
      const { data } = await entregasApi.tablero(claveMundo, desdeCero ? null : rev.current, dias);
      if (data.sinCambios) return;
      rev.current = data.rev;
      setDatos({ mundo: claveMundo, tarjetas: data.tarjetas ?? [], metricas: data.metricas! });
      setError(false);
    } catch {
      setError(true);
    }
  }, [claveMundo, dias]);

  // Como el calendario: se pregunta cada 15 s si cambió algo (si no, la
  // respuesta es una línea) y al volver a la pestaña. Al cambiar de mundo o
  // de período, o después de entregar o decidir algo, se trae todo.
  useEffect(() => {
    if (!allowed || !claveMundo) return;
    void cargar(true);
    const revisar = () => { if (document.visibilityState === "visible") void cargar(false); };
    const intervalo = window.setInterval(revisar, SEGUNDOS_ENTRE_REVISIONES * 1000);
    document.addEventListener("visibilitychange", revisar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", revisar);
    };
  }, [allowed, claveMundo, cargar, cambios]);

  if (checked && !allowed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="font-medium text-slate-600 dark:text-slate-400">No tenés acceso al calendario.</p>
      </div>
    );
  }

  const hoy = hoyIso();
  const yo = user?.id ?? null;
  const delMundo = datos && datos.mundo === claveMundo ? datos : null;
  const tarjetas = delMundo?.tarjetas ?? [];
  const meToca = (t: Tarjeta) => proximoPaso(t.entrega, t.asignadoA, yo, () => "").aQuien === "vos";
  const columnas = COLUMNAS.map(c => ({
    ...c,
    lista: tarjetas
      .filter(t => t.entrega.momento === c.momento)
      // Lo que me toca a mí, primero; después, lo que vence antes.
      .sort((a, b) => Number(meToca(b)) - Number(meToca(a)) || (a.vence ?? "9999").localeCompare(b.vence ?? "9999")),
  }));
  // En el teléfono se ve una columna: la que tiene algo mío, o la primera con algo.
  const conMiTurno = columnas.find(c => c.lista.some(meToca))?.momento;
  const conAlgo = columnas.find(c => c.lista.length > 0)?.momento;
  const activa: MomentoEntrega = pestana ?? conMiTurno ?? conAlgo ?? "produccion";

  return (
    <div className="mx-auto max-w-7xl animate-fade-in">
      <Suspense fallback={null}><AbrirTareaDeLaUrl /></Suspense>

      <header className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm shadow-brand-600/30">
          <Layers className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">Entregas</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Las piezas con la agencia{mundo ? ` en ${mundo.nombre}` : ""}: en qué fase va cada una y a quién le toca.
          </p>
        </div>
      </header>

      {!delMundo && !error && (
        <div className="space-y-4" role="status" aria-label="Cargando el tablero…">
          <div className="grid grid-cols-3 gap-3">{[0, 1, 2].map(i => <div key={i} className="skeleton h-24 rounded-2xl" />)}</div>
          <div className="grid gap-3 md:grid-cols-4">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-64 rounded-2xl" />)}</div>
        </div>
      )}
      {error && !delMundo && (
        <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          No se pudo traer el tablero. Se vuelve a intentar solo en unos segundos.
        </p>
      )}

      {delMundo && (
        <>
          <MetricasDeRetrabajo metricas={delMundo.metricas} dias={dias} onDias={setDias} />

          {tarjetas.length === 0 ? (
            <div className="mt-6 flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center dark:border-slate-700 dark:bg-slate-900">
              <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                <Layers className="h-6 w-6" />
              </span>
              <p className="text-base font-semibold text-slate-800 dark:text-slate-100">Todavía no hay piezas con entregas</p>
              <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
                Se arman desde la ficha de una acción del calendario: «Nueva tarea» y tildar «Lleva entregas para aprobar».
              </p>
            </div>
          ) : (
            <>
              {/* En el teléfono no entran cuatro columnas: se elige cuál ver. */}
              <div className="segmentado mt-6 md:hidden" role="tablist" aria-label="Columna del tablero">
                {columnas.map(c => (
                  <button
                    key={c.momento}
                    type="button"
                    role="tab"
                    aria-selected={activa === c.momento}
                    onClick={() => setPestana(c.momento)}
                    className="segmento !min-h-[44px] !flex-1 !px-1 flex-col !gap-0 text-xs leading-tight"
                  >
                    <span className="flex items-center gap-1">
                      <span className={`h-1.5 w-1.5 rounded-full ${COLOR_COLUMNA[c.momento]}`} aria-hidden />
                      {c.lista.length}
                    </span>
                    <span className="truncate">{c.titulo}</span>
                  </button>
                ))}
              </div>

              <div className="mt-4 grid gap-4 md:mt-6 md:grid-cols-4">
                {columnas.map(c => (
                  <section
                    key={c.momento}
                    aria-labelledby={`col-${c.momento}`}
                    className={`rounded-2xl bg-slate-100/70 p-2.5 dark:bg-slate-900/60 ${activa === c.momento ? "" : "hidden md:block"}`}
                  >
                    <div className="mb-2.5 px-1.5 pt-1">
                      <h2 id={`col-${c.momento}`} className="flex items-center gap-2">
                        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${COLOR_COLUMNA[c.momento]}`} aria-hidden />
                        <span className="whitespace-nowrap text-sm font-bold text-slate-900 dark:text-slate-100">{c.titulo}</span>
                        <span className="rounded-full bg-white px-2 py-0.5 text-xs font-bold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">{c.lista.length}</span>
                      </h2>
                      <p className="mt-0.5 pl-[1.125rem] text-xs text-slate-500 dark:text-slate-400">{c.bajada}</p>
                    </div>
                    {c.lista.length === 0 ? (
                      <p className="rounded-xl border border-dashed border-slate-300 px-3 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                        Nada por acá.
                      </p>
                    ) : (
                      <ul className="space-y-2.5">
                        {c.lista.map((t, i) => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={yo} hoy={hoy} orden={i} />)}
                      </ul>
                    )}
                  </section>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Cuánto retrabajo hubo: las rondas que llevó aprobar cada fase y cuántas se
 * aprobaron a la primera. Dos números arriba y, para quien quiera, el
 * detalle por tipo de pieza, por responsable y por mundo.
 */
function MetricasDeRetrabajo({ metricas, dias, onDias }: { metricas: Metricas; dias: number; onDias: (d: number) => void }) {
  const [verDetalle, setVerDetalle] = useState(false);
  const sinDatos = metricas.fases === 0;
  return (
    <section aria-labelledby="retrabajo" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 id="retrabajo" className="text-base font-bold text-slate-900 dark:text-slate-100">Retrabajo</h2>
        <div className="segmentado ml-auto !p-0.5" role="group" aria-label="Período">
          {[30, 90, 365].map(d => (
            <button key={d} type="button" aria-pressed={dias === d} onClick={() => onDias(d)} className="segmento !min-h-[32px] !flex-none whitespace-nowrap !px-2.5 text-xs">
              {d === 365 ? "1 año" : `${d} días`}
            </button>
          ))}
        </div>
      </div>

      {sinDatos ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Todavía no se aprobó ninguna fase en este período: cuando se aprueben, acá se ve cuántas rondas llevaron.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 sm:gap-3">
            <Dato etiqueta="Rondas hasta aprobar" valor={numero(metricas.rondasPromedio)} bajada="promedio por fase" />
            <Dato etiqueta="Aprobado a la primera" valor={metricas.aLaPrimera == null ? "—" : `${metricas.aLaPrimera}%`} bajada="de las fases" />
            <Dato etiqueta="Fases aprobadas" valor={String(metricas.fases)} bajada={dias === 365 ? "en el último año" : `en ${dias} días`} />
          </div>
          <button
            type="button"
            onClick={() => setVerDetalle(v => !v)}
            aria-expanded={verDetalle}
            className="-ml-2 mt-3 flex min-h-[40px] items-center gap-1 rounded-xl px-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${verDetalle ? "rotate-180" : ""}`} />
            {verDetalle ? "Ocultar el detalle" : "Ver por tipo de pieza, responsable y mundo"}
          </button>
          {verDetalle && (
            <>
              <div className="mt-2 grid gap-5 lg:grid-cols-3">
                <TablaDeRetrabajo titulo="Por tipo de pieza" filas={metricas.porTipo} />
                <TablaDeRetrabajo titulo="Por responsable" filas={metricas.porResponsable} />
                <TablaDeRetrabajo titulo="Por mundo" filas={metricas.porMundo} />
              </div>
              <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
                La barra es el % de fases aprobadas a la primera. «Por mundo» compara los mundos a los que entrás.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}

function Dato({ etiqueta, valor, bajada }: { etiqueta: string; valor: string; bajada: string }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-slate-800/50">
      <p className="text-xs font-semibold leading-tight text-slate-600 dark:text-slate-400">{etiqueta}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100 sm:text-3xl">{valor}</p>
      <p className="text-[11px] text-slate-500 dark:text-slate-400">{bajada}</p>
    </div>
  );
}

/** Una fila por grupo: cuántas fases, rondas promedio y una barra con el %
 *  aprobado a la primera (sobre el 100 %), con el número al lado. */
function TablaDeRetrabajo({ titulo, filas }: { titulo: string; filas: Metricas["porTipo"] }) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{titulo}</h3>
      <table className="w-full text-sm">
        <thead className="sr-only">
          <tr><th>Quién o qué</th><th>Fases</th><th>Rondas promedio</th><th>Aprobado a la primera</th></tr>
        </thead>
        <tbody>
          {filas.map(f => (
            <tr key={String(f.clave)} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
              <td className="max-w-0 py-2 pr-2">
                <span className="block truncate font-medium text-slate-800 dark:text-slate-200" title={f.nombre ?? String(f.clave)}>{f.nombre ?? String(f.clave)}</span>
                <span className="text-xs text-slate-500 dark:text-slate-400">{f.fases === 1 ? "1 fase" : `${f.fases} fases`} · {numero(f.rondasPromedio)} rondas</span>
              </td>
              <td className="w-[45%] py-2">
                <span className="flex items-center gap-2">
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700" title={`${f.aLaPrimera ?? 0}% aprobado a la primera`}>
                    <span className="block h-full rounded-full bg-brand-500" style={{ width: `${f.aLaPrimera ?? 0}%` }} />
                  </span>
                  <span className="w-10 text-right text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-300">{f.aLaPrimera ?? 0}%</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
