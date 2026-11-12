"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CalendarClock, Check, ChevronRight, ListChecks, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { calendarioApi } from "@/lib/api";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { fechaCorta, hoyIso, sumarDias } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";
import { ETIQUETA_ESTADO_TAREA, type EstadoTarea, type Tarea } from "@/lib/calendario/tipos";
import { mundoDe, mundosDe } from "@/lib/mundos";

/**
 * Mis tareas: lo que la persona tiene asignado, en todos sus mundos.
 *
 * Es la otra mitad del pedido de Ivan (12/11/2026): quien lidera asigna las
 * tareas en la ficha de cada acción, y cada uno necesita "poder ver qué tarea
 * es la que tiene asignada" sin recorrer el calendario acción por acción.
 */

type MiTarea = Tarea & {
  accion: { id: string; mundo: string; nombre: string; banda: string; color: string | null; desde: string; hasta: string };
};

const TONO: Record<EstadoTarea, string> = {
  pendiente: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  "en-proceso": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  hecha: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
};
const ESTADOS: EstadoTarea[] = ["pendiente", "en-proceso", "hecha"];

export default function MisTareasPage() {
  const { allowed, checked, user } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });
  const [tareas, setTareas] = useState<MiTarea[] | null>(null);
  const [verHechas, setVerHechas] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const { data } = await calendarioApi.misTareas();
      setTareas(data as MiTarea[]);
    } catch {
      setTareas(prev => prev ?? []);
      toast.error("No se pudieron traer tus tareas. Probá de nuevo en un momento.");
    }
  }, []);

  useEffect(() => { if (allowed) void cargar(); }, [allowed, cargar]);

  async function cambiarEstado(t: MiTarea, estado: EstadoTarea) {
    setTareas(prev => prev?.map(x => (x.id === t.id ? { ...x, estado } : x)) ?? null);
    try {
      await calendarioApi.cambiarTarea(t.id, { estado });
    } catch {
      toast.error("No se pudo guardar el cambio.");
      void cargar();
    }
  }

  if (checked && !allowed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="font-medium text-slate-600 dark:text-slate-400">No tenés acceso al calendario.</p>
      </div>
    );
  }
  if (!allowed || tareas === null) {
    return <div className="flex h-64 items-center justify-center text-sm text-slate-400">Cargando tus tareas…</div>;
  }

  const hoy = hoyIso();
  const enUnaSemana = sumarDias(hoy, 7);
  const abiertas = tareas.filter(t => t.estado !== "hecha");
  const hechas = tareas.filter(t => t.estado === "hecha");
  const grupos = [
    { titulo: "Vencidas", tono: "text-rose-600 dark:text-rose-400", lista: abiertas.filter(t => t.vence && t.vence < hoy) },
    { titulo: "Para esta semana", tono: "text-slate-900 dark:text-slate-100", lista: abiertas.filter(t => t.vence && t.vence >= hoy && t.vence <= enUnaSemana) },
    { titulo: "Más adelante", tono: "text-slate-900 dark:text-slate-100", lista: abiertas.filter(t => t.vence && t.vence > enUnaSemana) },
    { titulo: "Sin fecha", tono: "text-slate-900 dark:text-slate-100", lista: abiertas.filter(t => !t.vence) },
  ].filter(g => g.lista.length > 0);
  const variosMundos = mundosDe(user).length > 1;

  return (
    <div className="mx-auto max-w-3xl animate-fade-in">
      <header className="mb-6 flex items-center gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white">
          <ListChecks className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Mis tareas</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            {abiertas.length === 0
              ? "No tenés nada pendiente."
              : abiertas.length === 1 ? "Tenés 1 tarea pendiente." : `Tenés ${abiertas.length} tareas pendientes.`}
          </p>
        </div>
      </header>

      {tareas.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center dark:border-slate-700 dark:bg-slate-900">
          <p className="text-base font-semibold text-slate-700 dark:text-slate-200">Todavía no te asignaron ninguna tarea</p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Cuando alguien te asigne una en una acción del calendario, te llega un aviso y aparece acá.
          </p>
        </div>
      )}

      <div className="space-y-7">
        {grupos.map(g => (
          <section key={g.titulo}>
            <h2 className={`mb-2.5 text-base font-bold ${g.tono}`}>
              {g.titulo} <span className="font-semibold text-slate-400">· {g.lista.length}</span>
            </h2>
            <ul className="space-y-2.5">
              {g.lista.map(t => <Fila key={t.id} tarea={t} hoy={hoy} conMundo={variosMundos} onEstado={cambiarEstado} />)}
            </ul>
          </section>
        ))}

        {hechas.length > 0 && (
          <section>
            <button
              type="button"
              onClick={() => setVerHechas(v => !v)}
              className="mb-2.5 flex items-center gap-1 text-base font-bold text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            >
              <ChevronRight className={`h-4 w-4 transition ${verHechas ? "rotate-90" : ""}`} />
              Hechas · {hechas.length}
            </button>
            {verHechas && (
              <ul className="space-y-2.5">
                {hechas.map(t => <Fila key={t.id} tarea={t} hoy={hoy} conMundo={variosMundos} onEstado={cambiarEstado} />)}
              </ul>
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function Fila({ tarea, hoy, conMundo, onEstado }: {
  tarea: MiTarea;
  hoy: string;
  conMundo: boolean;
  onEstado: (t: MiTarea, estado: EstadoTarea) => void;
}) {
  const hecha = tarea.estado === "hecha";
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoy;
  const mundo = mundoDe(tarea.accion.mundo);

  return (
    <li className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-700 dark:bg-slate-900">
      <button
        type="button"
        onClick={() => onEstado(tarea, hecha ? "pendiente" : "hecha")}
        aria-label={hecha ? `Desmarcar ${tarea.titulo}` : `Marcar ${tarea.titulo} como hecha`}
        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border-2 transition ${
          hecha ? "border-emerald-500 bg-emerald-500 text-white" : "border-slate-300 hover:border-emerald-500 dark:border-slate-600"
        }`}
      >
        {hecha && <Check className="h-4 w-4" strokeWidth={3} />}
      </button>

      <div className="min-w-0 flex-1">
        <p className={`text-base font-semibold leading-snug ${hecha ? "text-slate-400 line-through" : "text-slate-900 dark:text-slate-100"}`}>
          {tarea.titulo}
        </p>
        {tarea.descripcion && <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{tarea.descripcion}</p>}

        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <Link
            href={`/calendario?accion=${encodeURIComponent(tarea.accion.id)}`}
            className="flex min-w-0 items-center gap-2 rounded-lg bg-slate-100 py-1 pl-1.5 pr-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            title="Abrir la acción en el calendario"
          >
            <span className="h-4 w-4 shrink-0 rounded" style={{ backgroundColor: tarea.accion.color ?? "#cbd5e1" }} />
            <span className="truncate">{tarea.accion.nombre}</span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          </Link>
          {conMundo && mundo && (
            <span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: mundo.color }} /> {mundo.nombre}
            </span>
          )}
          {tarea.vence && (
            <span className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium ${
              vencida ? "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300" : "text-slate-600 dark:text-slate-400"
            }`}>
              <CalendarClock className="h-4 w-4" /> {vencida ? "Venció el" : "Vence el"} {fechaCorta(tarea.vence)}
            </span>
          )}
          <select
            value={tarea.estado}
            onChange={e => onEstado(tarea, e.target.value as EstadoTarea)}
            aria-label={`Estado de ${tarea.titulo}`}
            className={`ml-auto cursor-pointer appearance-none rounded-lg border-0 px-3 py-1 text-sm font-semibold outline-none ${TONO[tarea.estado]}`}
          >
            {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
          </select>
        </div>
      </div>
    </li>
  );
}
