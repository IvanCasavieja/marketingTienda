"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, CalendarClock, CalendarDays, Check, ChevronRight, CircleDashed, Eye, Layers, ListChecks, PartyPopper,
  RotateCcw, ShieldAlert,
} from "lucide-react";
import { toast } from "sonner";
import { calendarioApi, entregasApi } from "@/lib/api";
import { faseActualTexto, FasesCompactas } from "@/components/calendario/entregas/LineaDeFases";
import { TarjetaEntrega } from "@/components/calendario/entregas/TarjetaEntrega";
import { proximoPaso, type Tarjeta } from "@/lib/calendario/entregas";
import { useVistaEntregas } from "@/store/entregas";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { veCalendario } from "@/lib/alcance";
import { Cocarda } from "@/components/calendario/Cocarda";
import { nivelDeCategoria } from "@/lib/calendario/categorias";
import { fechaCorta, hoyIso, sumarDias } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";
import { ETIQUETA_ESTADO_TAREA, type EstadoTarea, type Tarea } from "@/lib/calendario/tipos";
import { mundoEfectivo, mundosDe, useMundoElegido } from "@/lib/mundos";
import { BotonOutlook } from "@/components/calendario/BotonOutlook";

/**
 * Mis tareas: lo que la persona tiene asignado en el mundo en el que está.
 * Si tiene pendientes en otro mundo se le avisa, con el botón para pasar: no
 * se mezclan, pero tampoco se le esconden.
 *
 * Es la otra mitad del pedido de Ivan (12/11/2026): quien lidera asigna las
 * tareas en la ficha de cada acción, y cada uno necesita "poder ver qué tarea
 * es la que tiene asignada" sin recorrer el calendario acción por acción.
 */

type MiTarea = Tarea & {
  accion: {
    id: string; mundo: string; nombre: string; banda: string; color: string | null; desde: string; hasta: string;
    /** La acción queda fuera de lo que esta persona ve del calendario: la
     *  tarea es suya y la ve, pero la ficha no la va a poder abrir. */
    fueraDeAlcance?: boolean;
  };
};

const TONO: Record<EstadoTarea, string> = {
  pendiente: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  "en-proceso": "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200",
  hecha: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200",
};
const ESTADOS: EstadoTarea[] = ["pendiente", "en-proceso", "hecha"];

/** Lo que tarda una tarea recién tildada en irse a "Hechas": lo justo para ver el tilde. */
const MS_DE_SALIDA = 700;

function Esqueleto() {
  return (
    <div className="mx-auto max-w-3xl animate-fade-in" role="status" aria-label="Cargando tus tareas…">
      <div className="mb-7 flex items-center gap-3">
        <div className="skeleton h-12 w-12 rounded-2xl" />
        <div className="space-y-2">
          <div className="skeleton h-6 w-40 rounded-md" />
          <div className="skeleton h-4 w-60 rounded-md" />
        </div>
      </div>
      <div className="skeleton mb-3 h-4 w-32 rounded-md" />
      <div className="space-y-2.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3 rounded-2xl border border-slate-300 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
            <div className="skeleton h-7 w-7 shrink-0 rounded-lg" />
            <div className="flex-1 space-y-2.5">
              <div className="skeleton h-4 w-2/3 rounded-md" />
              <div className="flex gap-2">
                <div className="skeleton h-7 w-40 rounded-lg" />
                <div className="skeleton h-7 w-24 rounded-lg" />
              </div>
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Cargando tus tareas…</span>
    </div>
  );
}

export default function MisTareasPage() {
  const { allowed, checked, user } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });
  const [tareas, setTareas] = useState<MiTarea[] | null>(null);
  const [verHechas, setVerHechas] = useState(false);
  // Las recién tildadas se quedan un instante en su lugar, con el tilde, antes de irse a "Hechas".
  const [saliendo, setSaliendo] = useState<Set<string>>(() => new Set());
  const relojes = useRef(new Map<string, number>());
  const elegido = useMundoElegido(s => s.elegido);
  const elegir = useMundoElegido(s => s.elegir);
  const mundo = mundoEfectivo(user, elegido);
  // Las entregas: lo que espera MI decisión y lo que me devolvieron con cambios.
  const [entregas, setEntregas] = useState<{ paraRevisar: Tarjeta[]; conCambios: Tarjeta[] }>({ paraRevisar: [], conCambios: [] });
  const cambiosEnEntregas = useVistaEntregas(s => s.cambios);

  const cargar = useCallback(async () => {
    try {
      const { data } = await calendarioApi.misTareas();
      setTareas(data as MiTarea[]);
    } catch {
      setTareas(prev => prev ?? []);
      toast.error("No se pudieron traer tus tareas. Probá de nuevo en un momento.");
    }
    try {
      const { data } = await entregasApi.misEntregas();
      setEntregas(data);
    } catch {
      // Sin esto la página igual sirve: se ven las tareas.
    }
  }, []);

  // Se vuelve a traer después de entregar o decidir algo desde la vista de entregas.
  useEffect(() => { if (allowed) void cargar(); }, [allowed, cargar, cambiosEnEntregas]);

  useEffect(() => {
    const pendientes = relojes.current;
    return () => { pendientes.forEach(id => window.clearTimeout(id)); };
  }, []);

  async function cambiarEstado(t: MiTarea, estado: EstadoTarea) {
    setTareas(prev => prev?.map(x => (x.id === t.id ? { ...x, estado } : x)) ?? null);
    try {
      await calendarioApi.cambiarTarea(t.id, { estado });
    } catch {
      toast.error("No se pudo guardar el cambio.");
      void cargar();
    }
  }

  /** El tilde: lo mismo que antes, más un momento para verlo y la opción de deshacer. */
  function tildar(t: MiTarea) {
    const hecha = t.estado === "hecha";
    const antes = t.estado;
    void cambiarEstado(t, hecha ? "pendiente" : "hecha");
    if (hecha) return;
    setSaliendo(s => new Set(s).add(t.id));
    window.clearTimeout(relojes.current.get(t.id));
    relojes.current.set(t.id, window.setTimeout(() => {
      relojes.current.delete(t.id);
      setSaliendo(s => { const n = new Set(s); n.delete(t.id); return n; });
    }, MS_DE_SALIDA));
    toast.success(`Hecha: ${t.titulo}`, {
      action: { label: "Deshacer", onClick: () => void cambiarEstado({ ...t, estado: "hecha" }, antes) },
    });
  }

  if (checked && !allowed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="font-medium text-slate-600 dark:text-slate-400">No tenés acceso al calendario.</p>
      </div>
    );
  }
  if (!allowed || tareas === null) return <Esqueleto />;

  const hoy = hoyIso();
  const enUnaSemana = sumarDias(hoy, 7);
  const deEsteMundo = tareas.filter(t => !mundo || t.accion.mundo === mundo.clave);
  const paraRevisar = entregas.paraRevisar.filter(t => !mundo || t.accion.mundo === mundo.clave);
  const conCambios = entregas.conCambios.filter(t => !mundo || t.accion.mundo === mundo.clave);
  // Lo que volvió con cambios ya está arriba, en su sección: no se repite abajo.
  const yaArriba = new Set(conCambios.map(t => t.tareaId));
  const hayEntregasArriba = paraRevisar.length + conCambios.length > 0;
  const abiertas = deEsteMundo.filter(t => (t.estado !== "hecha" || saliendo.has(t.id)) && !yaArriba.has(t.id));
  const hechas = deEsteMundo.filter(t => t.estado === "hecha" && !saliendo.has(t.id));
  const pendientes = deEsteMundo.filter(t => t.estado !== "hecha");
  // Lo pendiente en los otros mundos a los que entra, contado por mundo.
  const enOtros = mundosDe(user)
    .filter(m => m.clave !== mundo?.clave)
    .map(m => ({ mundo: m, pendientes: tareas.filter(t => t.accion.mundo === m.clave && t.estado !== "hecha").length }))
    .filter(x => x.pendientes > 0);
  const grupos = [
    { id: "vencidas", titulo: "Vencidas", Icono: AlertTriangle, tono: "text-rose-600 dark:text-rose-400", lista: abiertas.filter(t => t.vence && t.vence < hoy) },
    { id: "semana", titulo: "Para esta semana", Icono: CalendarClock, tono: "text-brand-600 dark:text-brand-300", lista: abiertas.filter(t => t.vence && t.vence >= hoy && t.vence <= enUnaSemana) },
    { id: "despues", titulo: "Más adelante", Icono: CalendarDays, tono: "text-slate-500 dark:text-slate-400", lista: abiertas.filter(t => t.vence && t.vence > enUnaSemana) },
    { id: "sinfecha", titulo: "Sin fecha", Icono: CircleDashed, tono: "text-slate-500 dark:text-slate-400", lista: abiertas.filter(t => !t.vence) },
  ].filter(g => g.lista.length > 0);
  const vencidas = pendientes.filter(t => t.vence && t.vence < hoy).length;
  const estaSemana = pendientes.filter(t => t.vence && t.vence >= hoy && t.vence <= enUnaSemana).length;

  return (
    <div className="mx-auto max-w-3xl animate-fade-in">
      <header className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm shadow-brand-600/30">
          <ListChecks className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">Mis tareas</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {pendientes.length === 0 && paraRevisar.length === 0
              ? `No tenés nada pendiente${mundo ? ` en ${mundo.nombre}` : ""}.`
              : `Tenés ${[
                pendientes.length > 0 ? (pendientes.length === 1 ? "1 tarea pendiente" : `${pendientes.length} tareas pendientes`) : "",
                paraRevisar.length > 0 ? (paraRevisar.length === 1 ? "1 pieza para revisar" : `${paraRevisar.length} piezas para revisar`) : "",
              ].filter(Boolean).join(" y ")}${mundo ? ` en ${mundo.nombre}` : ""}.`}
          </p>
        </div>
        {/* Lo urgente, contado: se ve antes de leer la lista */}
        {(vencidas > 0 || estaSemana > 0) && (
          <div className="flex w-full gap-2 sm:w-auto">
            {vencidas > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-rose-100 px-3 py-1.5 text-sm font-semibold text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
                <AlertTriangle className="h-4 w-4" /> {vencidas === 1 ? "1 vencida" : `${vencidas} vencidas`}
              </span>
            )}
            {estaSemana > 0 && (
              <span className="flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-sm font-semibold text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
                <CalendarClock className="h-4 w-4" /> {estaSemana} esta semana
              </span>
            )}
          </div>
        )}
        {/* El link de Outlook es el calendario: quien no lo ve no lo tiene
            (el servidor se lo niega y el botón daba un error). */}
        {veCalendario(user) && (
          <div className="sm:ml-auto">
            <BotonOutlook />
          </div>
        )}
      </header>

      {enOtros.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          <span className="font-semibold">También tenés pendientes en:</span>
          {enOtros.map(({ mundo: m, pendientes: n }) => (
            <button
              key={m.clave}
              type="button"
              onClick={() => elegir(m.clave)}
              className="flex min-h-[36px] items-center gap-1.5 rounded-xl bg-white px-3 font-semibold text-slate-800 shadow-sm ring-1 ring-amber-200/60 transition hover:bg-slate-50 active:scale-95 dark:bg-slate-900 dark:text-slate-100 dark:ring-amber-900/60 dark:hover:bg-slate-800"
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: m.color }} />
              {m.nombre}
              <span className="rounded-full bg-amber-100 px-1.5 text-xs tabular-nums text-amber-800 dark:bg-amber-500/15 dark:text-amber-200">{n}</span>
              <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
            </button>
          ))}
        </div>
      )}

      {/* Las entregas que esperan algo de mí: lo primero que se ve. */}
      {hayEntregasArriba && (
        <div className="mb-8 space-y-6">
          {paraRevisar.length > 0 && (
            <section aria-labelledby="para-revisar">
              <h2 id="para-revisar" className="mb-3 flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100">
                <Eye className="h-[18px] w-[18px] text-amber-600 dark:text-amber-400" aria-hidden />
                Para revisar
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold tabular-nums text-amber-800 dark:bg-amber-500/15 dark:text-amber-200">{paraRevisar.length}</span>
                <span className="text-sm font-normal text-slate-500 dark:text-slate-400">· esperan tu decisión</span>
              </h2>
              <ul className="grid gap-2.5 sm:grid-cols-2">
                {paraRevisar.map((t, i) => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={user?.id ?? null} hoy={hoy} orden={i} />)}
              </ul>
            </section>
          )}
          {conCambios.length > 0 && (
            <section aria-labelledby="con-cambios">
              <h2 id="con-cambios" className="mb-3 flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100">
                <RotateCcw className="h-[18px] w-[18px] text-rose-600 dark:text-rose-400" aria-hidden />
                Te devolvieron con cambios
                <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-bold tabular-nums text-rose-800 dark:bg-rose-500/15 dark:text-rose-200">{conCambios.length}</span>
              </h2>
              <ul className="grid gap-2.5 sm:grid-cols-2">
                {conCambios.map((t, i) => <TarjetaEntrega key={t.tareaId} tarjeta={t} usuarioId={user?.id ?? null} hoy={hoy} orden={i} />)}
              </ul>
            </section>
          )}
        </div>
      )}

      {deEsteMundo.length === 0 && !hayEntregasArriba && (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center dark:border-slate-700 dark:bg-slate-900">
          <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <ListChecks className="h-6 w-6" />
          </span>
          <p className="text-base font-semibold text-slate-800 dark:text-slate-100">Todavía no te asignaron ninguna tarea</p>
          <p className="mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">
            Cuando alguien te asigne una en una acción del calendario, te llega un aviso y aparece acá.
          </p>
        </div>
      )}

      {/* Todo hecho: se festeja, apenas */}
      {deEsteMundo.length > 0 && abiertas.length === 0 && !hayEntregasArriba && (
        <div className="flex animate-rise flex-col items-center rounded-2xl border border-emerald-200 bg-emerald-50/70 px-6 py-12 text-center dark:border-emerald-500/20 dark:bg-emerald-500/[.06]">
          <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
            <PartyPopper className="h-6 w-6" />
          </span>
          <p className="text-base font-semibold text-emerald-900 dark:text-emerald-100">Estás al día</p>
          <p className="mt-1 text-sm text-emerald-800/80 dark:text-emerald-200/80">
            No te queda nada pendiente{mundo ? ` en ${mundo.nombre}` : ""}.
          </p>
        </div>
      )}

      <div className="space-y-8">
        {grupos.map(g => (
          <section key={g.id} aria-labelledby={`grupo-${g.id}`}>
            <h2 id={`grupo-${g.id}`} className={`mb-3 flex items-center gap-2 text-base font-bold ${g.id === "vencidas" ? g.tono : "text-slate-900 dark:text-slate-100"}`}>
              <g.Icono className={`h-[18px] w-[18px] ${g.tono}`} aria-hidden />
              {g.titulo}
              <span className="rounded-full bg-slate-200/70 px-2 py-0.5 text-xs font-bold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">{g.lista.length}</span>
            </h2>
            <ul className="space-y-2.5">
              {g.lista.map((t, i) => (
                <Fila
                  key={t.id} tarea={t} hoy={hoy} orden={i}
                  saliendo={saliendo.has(t.id)}
                  onTildar={tildar} onEstado={cambiarEstado}
                />
              ))}
            </ul>
          </section>
        ))}

        {hechas.length > 0 && (
          <section>
            <button
              type="button"
              onClick={() => setVerHechas(v => !v)}
              aria-expanded={verHechas}
              className="-ml-2 mb-2.5 flex min-h-[40px] items-center gap-1.5 rounded-xl px-2 text-base font-bold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <ChevronRight className={`h-4 w-4 transition-transform duration-200 ${verHechas ? "rotate-90" : ""}`} />
              <Check className="h-4 w-4 text-emerald-500" aria-hidden />
              Hechas
              <span className="text-xs font-normal text-slate-500 dark:text-slate-400">· últimos 30 días</span>
              <span className="rounded-full bg-slate-200/70 px-2 py-0.5 text-xs font-bold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">{hechas.length}</span>
            </button>
            {verHechas && (
              <ul className="space-y-2.5">
                {hechas.map((t, i) => (
                  <Fila key={t.id} tarea={t} hoy={hoy} orden={i} saliendo={false} onTildar={tildar} onEstado={cambiarEstado} />
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function Fila({ tarea, hoy, orden, saliendo, onTildar, onEstado }: {
  tarea: MiTarea;
  hoy: string;
  orden: number;
  /** Recién tildada: se queda un momento, con el tilde, y se va. */
  saliendo: boolean;
  onTildar: (t: MiTarea) => void;
  onEstado: (t: MiTarea, estado: EstadoTarea) => void;
}) {
  const hecha = tarea.estado === "hecha";
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoy;
  const abrirEntregas = useVistaEntregas(s => s.abrir);
  // Una tarea con entregas no se tilda: queda hecha sola cuando se aprueba la
  // última fase. En su lugar va en qué fase está y la puerta a sus entregas.
  const entrega = tarea.entrega;

  return (
    <li
      style={{ animationDelay: `${Math.min(orden, 8) * 35}ms` }}
      className={`flex animate-rise items-start gap-3 rounded-2xl border p-4 shadow-card transition duration-500 ease-suave ${
        saliendo ? "scale-[.98] border-emerald-200 bg-emerald-50/60 opacity-70 dark:border-emerald-500/20 dark:bg-emerald-500/[.06]"
          : vencida ? "border-rose-200 bg-white dark:border-rose-500/30 dark:bg-slate-900"
            : "border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900"
      }`}
    >
      {entrega ? (
        <span
          title="Queda hecha sola cuando se aprueba la última fase"
          className={`-m-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${hecha ? "text-emerald-600 dark:text-emerald-400" : "text-brand-600 dark:text-brand-300"}`}
        >
          {hecha ? <Check className="h-6 w-6" strokeWidth={3} /> : <Layers className="h-6 w-6" />}
        </span>
      ) : (
      /* El tilde: 44px para el dedo, el cuadrado de 28 adentro */
      <button
        type="button"
        onClick={() => onTildar(tarea)}
        aria-label={hecha ? `Desmarcar ${tarea.titulo}` : `Marcar ${tarea.titulo} como hecha`}
        aria-pressed={hecha}
        title={hecha ? "Volver a pendiente" : "Marcar como hecha"}
        className="group/tilde -m-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
      >
        <span className={`flex h-7 w-7 items-center justify-center rounded-lg border-2 transition duration-200 group-active/tilde:scale-90 ${
          hecha
            ? "border-emerald-500 bg-emerald-500 text-white"
            : "border-slate-300 bg-white group-hover/tilde:border-emerald-500 group-hover/tilde:bg-emerald-50 dark:border-slate-600 dark:bg-slate-900 dark:group-hover/tilde:bg-emerald-500/10"
        }`}>
          {hecha && <Check className="h-4 w-4 animate-tilde" strokeWidth={3} />}
        </span>
      </button>
      )}

      <div className="min-w-0 flex-1">
        <p className={`text-base font-semibold leading-snug transition-colors duration-300 ${hecha ? "text-slate-500 line-through decoration-slate-300 dark:text-slate-400 dark:decoration-slate-600" : "text-slate-900 dark:text-slate-100"}`}>
          {tarea.titulo}
        </p>
        {tarea.descripcion && <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">{tarea.descripcion}</p>}

        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          {tarea.accion.fueraDeAlcance ? (
            // La acción no entra en lo que esta persona ve del calendario:
            // se nombra, pero sin enlace a una ficha que no abriría.
            <span
              className="flex min-h-[36px] min-w-0 items-center gap-2 rounded-xl bg-slate-100 py-1 pl-1.5 pr-2.5 text-sm font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-200"
              // El nombre se corta en el teléfono: el title lo dice entero.
              title={`${tarea.accion.nombre} · Esta acción queda fuera de lo que ves del calendario`}
            >
              <span className="h-5 w-5 shrink-0 rounded-md ring-1 ring-inset ring-black/10" style={{ backgroundColor: tarea.accion.color ?? "#cbd5e1" }} />
              <span className="truncate">{tarea.accion.nombre}</span>
            </span>
          ) : (
          <Link
            href={`/calendario?accion=${encodeURIComponent(tarea.accion.id)}`}
            className="group/accion flex min-h-[36px] min-w-0 items-center gap-2 rounded-xl bg-slate-100 py-1 pl-1.5 pr-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-200 active:scale-[.98] dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            title="Abrir la acción en el calendario"
          >
            <span className="h-5 w-5 shrink-0 rounded-md ring-1 ring-inset ring-black/10" style={{ backgroundColor: tarea.accion.color ?? "#cbd5e1" }} />
            <span className="truncate">{tarea.accion.nombre}</span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform group-hover/accion:translate-x-0.5" />
          </Link>
          )}
          {/* La cocarda solo en las tres categorías destacadas: acá lo que se
              mira es la tarea, y una cocarda gris en cada fila sería ruido. En
              un envío suelto `banda` es el canal, que nunca es una de esas. */}
          {["mega", "general", "especial"].includes(nivelDeCategoria(tarea.accion.banda)) && (
            <Cocarda banda={tarea.accion.banda} compacta />
          )}
          {tarea.vence && (
            <span className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium ${
              vencida ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300" : "text-slate-600 dark:text-slate-400"
            }`}>
              <CalendarClock className="h-4 w-4" /> {vencida ? "Venció el" : "Vence el"} {fechaCorta(tarea.vence)}
            </span>
          )}
          {!entrega && (
            <select
              value={tarea.estado}
              onChange={e => onEstado(tarea, e.target.value as EstadoTarea)}
              aria-label={`Estado de ${tarea.titulo}`}
              className={`ml-auto h-9 cursor-pointer appearance-none rounded-lg border-0 px-3 text-sm font-semibold outline-none transition focus-visible:ring-2 focus-visible:ring-brand-500 ${TONO[tarea.estado]}`}
            >
              {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
            </select>
          )}
        </div>

        {entrega && (() => {
          // La tarea es mía: si le toca a alguien, soy yo (entregar) o un aprobador (esperar).
          const paso = proximoPaso(entrega, tarea.asignadoA, tarea.asignadoA, () => "");
          const fase = entrega.fases.find(f => f.id === entrega.faseActual);
          const texto = entrega.momento === "revision" && fase
            ? `Esperando que revisen la ronda ${entrega.ronda} de ${fase.nombre}`
            : paso.texto;
          return (
            <div className="mt-2.5 space-y-2">
              <span className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300">
                <FasesCompactas resumen={entrega} /> {faseActualTexto(entrega)}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <p className={`min-w-0 flex-1 text-sm font-semibold ${paso.aQuien === "vos" ? "text-brand-700 dark:text-brand-200" : "text-slate-600 dark:text-slate-300"}`}>{texto}</p>
                <button
                  type="button"
                  onClick={() => abrirEntregas(tarea.id, paso.accion === "entregar" ? "entregar" : "ver")}
                  className={`flex min-h-[40px] items-center gap-1.5 rounded-xl px-3.5 text-sm font-bold transition active:scale-[.98] ${
                    paso.accion === "entregar"
                      ? "bg-brand-600 text-white shadow-sm hover:bg-brand-700"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                  }`}
                >
                  <Layers className="h-4 w-4" /> {paso.accion === "entregar" ? "Entregar" : "Ver entregas"}
                </button>
              </div>
            </div>
          );
        })()}
      </div>
    </li>
  );
}
