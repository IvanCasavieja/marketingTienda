"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Camera, ChevronDown, ChevronRight, Clock, Database, RefreshCw } from "lucide-react";
import { colocacionApi, type FilaResumenColocacion } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import { mundoEfectivo, useMundoElegido } from "@/lib/mundos";
import { rangoLargo } from "@/lib/calendario/fechas";
import { textoSobre } from "@/lib/calendario/colores";
import { PUNTO, cuandoVence } from "@/lib/colocacion/estados";

type Resumen = Awaited<ReturnType<typeof colocacionApi.resumen>>["data"];

/**
 * "Colocación": la vista general de las fotos que mandan los locales.
 *
 * Cada acción del mundo con un pedido abierto (algún local sin la foto
 * aprobada), con su porcentaje de cumplimiento y los locales atrasados, que
 * son a los que hay que llamar. Tocar una lleva a su tablero, en la ficha de
 * la acción. Abajo, las que se completaron hace poco.
 */
export default function ColocacionPage() {
  const { user, loading } = useCurrentUser();
  const elegido = useMundoElegido((s) => s.elegido);
  const mundo = mundoEfectivo(user, elegido);
  const puede = hasPermission(user, "calendario.edit");
  const [datos, setDatos] = useState<Resumen | null>(null);
  const [fallo, setFallo] = useState(false);
  const [vuelta, setVuelta] = useState(0);
  const [verCompletas, setVerCompletas] = useState(false);
  const clave = mundo?.clave;

  useEffect(() => {
    if (!clave || !puede) return;
    let vivo = true;
    colocacionApi.resumen(clave)
      .then(({ data }) => { if (vivo) { setDatos(data); setFallo(false); } })
      .catch(() => { if (vivo) setFallo(true); });
    return () => { vivo = false; };
  }, [clave, puede, vuelta]);

  if (loading) return null;

  if (!puede) {
    return (
      <div className="mx-auto max-w-3xl animate-fade-in">
        <Titulo mundo={mundo?.nombre} />
        <p className="card mt-4 p-6 text-sm text-slate-600 dark:text-slate-300">
          Esta pantalla es de quien edita el calendario: pide las fotos a los locales y las revisa.
        </p>
      </div>
    );
  }

  const deEsteMundo = datos?.mundo === clave ? datos : null;

  return (
    <div className="mx-auto max-w-3xl animate-fade-in space-y-5">
      <div className="flex items-start gap-3">
        <Titulo mundo={mundo?.nombre} />
        <button type="button" onClick={() => setVuelta((v) => v + 1)} className="boton-icono ml-auto" aria-label="Actualizar" title="Actualizar">
          <RefreshCw className="h-5 w-5" />
        </button>
      </div>

      {fallo && !deEsteMundo && (
        <div className="card flex items-center gap-3 p-4 text-sm text-slate-700 dark:text-slate-200">
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-500" /> No se pudo traer el resumen.
          <button type="button" onClick={() => setVuelta((v) => v + 1)} className="btn-secondary ml-auto">Probar de nuevo</button>
        </div>
      )}

      {!deEsteMundo && !fallo && (
        <div className="space-y-3" aria-label="Cargando…">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton h-36 rounded-2xl" />)}
        </div>
      )}

      {deEsteMundo && !deEsteMundo.tipoLocal && (
        <p className="card p-6 text-sm text-slate-600 dark:text-slate-300">
          {mundo?.nombre} no tiene locales con usuario: acá no se piden fotos de colocación.
        </p>
      )}

      {deEsteMundo?.tipoLocal && deEsteMundo.abiertas.length === 0 && (
        <div className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
          <Camera className="h-8 w-8 text-slate-300 dark:text-slate-600" />
          <p className="text-base font-semibold text-slate-800 dark:text-slate-100">No hay pedidos de foto abiertos</p>
          <p className="max-w-md text-sm text-slate-600 dark:text-slate-300">
            Se piden desde la ficha de cada acción del calendario, en la pestaña <strong>Fotos</strong>.
          </p>
          <Link href="/calendario" className="btn-secondary mt-2">Ir al calendario</Link>
        </div>
      )}

      {deEsteMundo && deEsteMundo.abiertas.length > 0 && (
        <ul className="space-y-3">
          {deEsteMundo.abiertas.map((f) => <Fila key={f.pedidoId} fila={f} hoy={deEsteMundo.hoy} />)}
        </ul>
      )}

      {deEsteMundo && deEsteMundo.completas.length > 0 && (
        <section>
          <button
            type="button"
            onClick={() => setVerCompletas((v) => !v)}
            aria-expanded={verCompletas}
            className="flex min-h-[44px] w-full items-center gap-2 rounded-xl px-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${verCompletas ? "" : "-rotate-90"}`} />
            Completas en los últimos 30 días · {deEsteMundo.completas.length}
          </button>
          {verCompletas && (
            <ul className="mt-2 space-y-3 animate-fade-in">
              {deEsteMundo.completas.map((f) => <Fila key={f.pedidoId} fila={f} hoy={deEsteMundo.hoy} />)}
            </ul>
          )}
        </section>
      )}

      {deEsteMundo && (
        <p className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          <Database className="h-3.5 w-3.5" />
          Las fotos ocupan {deEsteMundo.espacio.ocupadoMb.toLocaleString("es-UY")} MB de {deEsteMundo.espacio.topeMb} MB.
          Se borran solas 120 días después de que termina cada acción.
        </p>
      )}
    </div>
  );
}

function Titulo({ mundo }: { mundo?: string }) {
  return (
    <div>
      <h1 className="flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-slate-100 sm:text-2xl">
        <Camera className="h-6 w-6 text-brand-600 dark:text-brand-300" /> Colocación
      </h1>
      <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
        Las fotos que mandan los locales de cómo quedó la cartelería{mundo ? ` de cada acción de ${mundo}` : ""}.
      </p>
    </div>
  );
}

function Fila({ fila, hoy }: { fila: FilaResumenColocacion; hoy: string }) {
  const r = fila.resumen;
  const vence = cuandoVence(fila.limite, hoy);
  const completa = r.total > 0 && r.aprobadas === r.total;
  const atrasados = fila.atrasados;
  const color = fila.accion.color ?? "#94a3b8";
  return (
    <li>
      <Link
        href={`/calendario?accion=${encodeURIComponent(fila.accion.id)}&pestana=fotos`}
        className="card card-hover group block overflow-hidden"
      >
        <div className="h-1.5" style={{ backgroundColor: color }} aria-hidden />
        <div className="space-y-3 p-4">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-bold text-slate-900 dark:text-white">{fila.accion.nombre}</p>
              <p className="text-sm text-slate-600 dark:text-slate-400">Va {rangoLargo(fila.accion.desde, fila.accion.hasta)}</p>
            </div>
            <span
              className="shrink-0 rounded-xl px-2.5 py-1 text-lg font-bold tabular-nums"
              style={{ backgroundColor: color, color: textoSobre(color) }}
            >
              {r.porcentaje}%
            </span>
          </div>

          <div className="flex h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" aria-hidden>
            <div className={`h-full ${PUNTO.aprobada}`} style={{ width: `${r.total ? (r.aprobadas / r.total) * 100 : 0}%` }} />
            <div className={`h-full ${PUNTO.enviada}`} style={{ width: `${r.total ? (r.enviadas / r.total) * 100 : 0}%` }} />
            <div className={`h-full ${PUNTO.atrasada}`} style={{ width: `${r.total ? (r.atrasadas / r.total) * 100 : 0}%` }} />
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            <span className="text-slate-700 dark:text-slate-200"><strong>{r.aprobadas}</strong> de {r.total} aprobadas</span>
            {r.enviadas > 0 && <span className="font-semibold text-sky-700 dark:text-sky-300">{r.enviadas} por revisar</span>}
            {r.devueltas > 0 && <span className="text-amber-700 dark:text-amber-300">{r.devueltas} devueltas</span>}
            {!completa && (
              <span className={`flex items-center gap-1 ${vence.vencida ? "text-rose-700 dark:text-rose-300" : "text-slate-500 dark:text-slate-400"}`}>
                <Clock className="h-3.5 w-3.5" /> Límite: {vence.texto}
              </span>
            )}
          </div>

          {atrasados.length > 0 && (
            <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:bg-rose-500/10 dark:text-rose-100">
              <strong>{atrasados.length} {atrasados.length === 1 ? "atrasado" : "atrasados"}:</strong>{" "}
              {atrasados.slice(0, 6).join(", ")}{atrasados.length > 6 ? ` y ${atrasados.length - 6} más` : ""}
            </p>
          )}

          <span className="flex items-center gap-1 text-sm font-semibold text-brand-600 group-hover:text-brand-700 dark:text-brand-300">
            Abrir el tablero <ChevronRight className="h-4 w-4" />
          </span>
        </div>
      </Link>
    </li>
  );
}
