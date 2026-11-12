'use client'

import { useState } from 'react'
import { CalendarClock, Check, CornerDownRight, ListChecks, Plus, Trash2, UserRound } from 'lucide-react'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import {
  ETIQUETA_ESTADO_TAREA, NIVELES_DE_TAREA, nivelDeTarea,
  type BarraGuardada, type EstadoTarea, type Persona, type Tarea,
} from '@/lib/calendario/tipos'

/**
 * Las tareas de una acción.
 *
 * Pedido de Ivan (12/11/2026): quien lidera abre una acción, le crea tareas y
 * subtareas, y se las asigna a cada persona, que se entera por la campanita.
 *
 * - `gestiona` (permiso `calendario.tareas`): crea, asigna, pone fecha y borra.
 * - Los demás ven todo y pueden mover el estado de las tareas que tienen
 *   asignadas, y de ninguna otra. Es lo mismo que exige el servidor.
 */

const TONO: Record<EstadoTarea, string> = {
  pendiente: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'en-proceso': 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  hecha: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
}
const ESTADOS: EstadoTarea[] = ['pendiente', 'en-proceso', 'hecha']

const CAMPO = 'rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100'

export function BloqueTareas({ accion, personas, usuarioId, gestiona }: {
  accion: BarraGuardada
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
}) {
  const tareas = accion.tareas ?? []
  const hechas = tareas.filter(t => t.estado === 'hecha').length
  const raices = tareas.filter(t => !t.parentId || !tareas.some(x => x.id === t.parentId))

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <ListChecks className="h-5 w-5 text-brand-600" />
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Tareas</h3>
        {tareas.length > 0 && (
          <span className="text-sm text-slate-500 dark:text-slate-400">{hechas} de {tareas.length} hechas</span>
        )}
      </div>

      {tareas.length > 0 && (
        <div className="mb-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
          <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${(hechas / tareas.length) * 100}%` }} />
        </div>
      )}

      {tareas.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          {gestiona
            ? 'Esta acción todavía no tiene tareas. Creá la primera y asignásela a alguien: le llega un aviso.'
            : 'Esta acción todavía no tiene tareas. Las crea y las asigna quien lidera el equipo.'}
        </p>
      )}

      <ul className="space-y-2">
        {raices.map(t => (
          <ItemTarea
            key={t.id} tarea={t} todas={tareas} accionId={accion.id}
            personas={personas} usuarioId={usuarioId} gestiona={gestiona}
          />
        ))}
      </ul>

      {gestiona && <NuevaTarea accionId={accion.id} parentId={null} personas={personas} etiqueta="Nueva tarea" />}
    </section>
  )
}

function ItemTarea({ tarea, todas, accionId, personas, usuarioId, gestiona }: {
  tarea: Tarea
  todas: Tarea[]
  accionId: string
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
}) {
  const cambiar = useCalendario(s => s.cambiarTarea)
  const borrar = useCalendario(s => s.borrarTarea)
  const [agregando, setAgregando] = useState(false)
  const [confirmando, setConfirmando] = useState(false)

  const hijas = todas.filter(t => t.parentId === tarea.id)
  const nivel = nivelDeTarea(tarea, todas)
  const esMia = usuarioId != null && tarea.asignadoA === usuarioId
  const puedeEstado = gestiona || esMia
  const hecha = tarea.estado === 'hecha'
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoyIso()
  const asignado = personas.find(p => p.id === tarea.asignadoA)

  return (
    <li>
      <div className={`rounded-xl border px-3 py-2.5 transition ${
        esMia && !hecha
          ? 'border-brand-300 bg-brand-50/60 dark:border-brand-700 dark:bg-brand-950/30'
          : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'
      }`}>
        <div className="flex items-start gap-3">
          <button
            type="button"
            disabled={!puedeEstado}
            onClick={() => cambiar(tarea.id, { estado: hecha ? 'pendiente' : 'hecha' })}
            title={!puedeEstado ? 'Solo quien la tiene asignada puede tildarla' : hecha ? 'Volver a pendiente' : 'Marcar como hecha'}
            aria-label={hecha ? `Desmarcar ${tarea.titulo}` : `Marcar ${tarea.titulo} como hecha`}
            className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border-2 transition ${
              hecha
                ? 'border-emerald-500 bg-emerald-500 text-white'
                : 'border-slate-300 bg-white hover:border-emerald-500 dark:border-slate-600 dark:bg-slate-900'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {hecha && <Check className="h-4 w-4" strokeWidth={3} />}
          </button>

          <div className="min-w-0 flex-1">
            <p className={`text-[15px] font-semibold leading-snug ${
              hecha ? 'text-slate-400 line-through dark:text-slate-500' : 'text-slate-900 dark:text-slate-100'
            }`}>
              {tarea.titulo}
            </p>
            {tarea.descripcion && (
              <p className="mt-0.5 whitespace-pre-line text-sm text-slate-500 dark:text-slate-400">{tarea.descripcion}</p>
            )}

            <div className="mt-2 flex flex-wrap items-center gap-2">
              {gestiona ? (
                <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
                  <UserRound className="h-4 w-4 text-slate-400" />
                  <select
                    value={tarea.asignadoA ?? ''}
                    onChange={e => cambiar(tarea.id, { asignadoA: e.target.value ? Number(e.target.value) : null })}
                    aria-label={`A quién se asigna ${tarea.titulo}`}
                    className="max-w-[11rem] cursor-pointer rounded-md border-0 bg-slate-100 py-1 pl-2 pr-7 text-sm font-medium outline-none hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
                  >
                    <option value="">Sin asignar</option>
                    {/* Alguien que ya no abre este mundo igual se muestra: no se pierde de quién era. */}
                    {tarea.asignadoA != null && !asignado && <option value={tarea.asignadoA}>Alguien que ya no ve este calendario</option>}
                    {personas.map(p => <option key={p.id} value={p.id}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
                  </select>
                </label>
              ) : (
                <span className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-sm font-medium ${
                  esMia ? 'bg-brand-100 text-brand-800 dark:bg-brand-900/50 dark:text-brand-200' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                }`}>
                  <UserRound className="h-4 w-4" />
                  {tarea.asignadoA == null ? 'Sin asignar' : esMia ? 'La tenés vos' : asignado?.nombre ?? 'Otra persona'}
                </span>
              )}

              {gestiona ? (
                <label className={`flex items-center gap-1.5 text-sm ${vencida ? 'text-rose-600' : 'text-slate-600 dark:text-slate-300'}`}>
                  <CalendarClock className="h-4 w-4" />
                  <input
                    type="date"
                    value={tarea.vence ?? ''}
                    onChange={e => cambiar(tarea.id, { vence: e.target.value || null })}
                    aria-label={`Cuándo vence ${tarea.titulo}`}
                    className="rounded-md border-0 bg-slate-100 px-2 py-1 text-sm font-medium outline-none hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
                  />
                </label>
              ) : tarea.vence && (
                <span className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-sm font-medium ${
                  vencida ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
                }`}>
                  <CalendarClock className="h-4 w-4" />
                  {vencida ? 'Venció el' : 'Vence el'} {fechaCorta(tarea.vence)}
                </span>
              )}

              <select
                value={tarea.estado}
                disabled={!puedeEstado}
                onChange={e => cambiar(tarea.id, { estado: e.target.value as EstadoTarea })}
                aria-label={`Estado de ${tarea.titulo}`}
                className={`cursor-pointer appearance-none rounded-md border-0 px-2.5 py-1 text-sm font-semibold outline-none disabled:cursor-not-allowed disabled:opacity-70 ${TONO[tarea.estado]}`}
              >
                {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
              </select>

              {gestiona && (
                <span className="ml-auto flex items-center gap-1">
                  {nivel < NIVELES_DE_TAREA && (
                    <button
                      type="button"
                      onClick={() => setAgregando(v => !v)}
                      className="flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 dark:text-slate-400 dark:hover:bg-slate-800"
                    >
                      <Plus className="h-4 w-4" /> Subtarea
                    </button>
                  )}
                  {confirmando ? (
                    <button
                      type="button"
                      onClick={() => borrar(tarea.id)}
                      onBlur={() => setConfirmando(false)}
                      className="rounded-md bg-rose-600 px-2 py-1 text-sm font-semibold text-white"
                    >
                      {hijas.length > 0 ? 'Borrar con sus subtareas' : 'Sí, borrar'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmando(true)}
                      aria-label={`Borrar ${tarea.titulo}`}
                      className="rounded-md p-1.5 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {(hijas.length > 0 || agregando) && (
        <div className="ml-4 mt-2 border-l-2 border-slate-200 pl-3 dark:border-slate-700">
          <ul className="space-y-2">
            {hijas.map(h => (
              <ItemTarea
                key={h.id} tarea={h} todas={todas} accionId={accionId}
                personas={personas} usuarioId={usuarioId} gestiona={gestiona}
              />
            ))}
          </ul>
          {agregando && (
            <NuevaTarea
              accionId={accionId} parentId={tarea.id} personas={personas}
              etiqueta="Nueva subtarea" abierta onListo={() => setAgregando(false)}
            />
          )}
        </div>
      )}
    </li>
  )
}

function NuevaTarea({ accionId, parentId, personas, etiqueta, abierta = false, onListo }: {
  accionId: string
  parentId: string | null
  personas: Persona[]
  etiqueta: string
  abierta?: boolean
  onListo?: () => void
}) {
  const crear = useCalendario(s => s.crearTarea)
  const [abierto, setAbierto] = useState(abierta)
  const [titulo, setTitulo] = useState('')
  const [asignadoA, setAsignadoA] = useState('')
  const [vence, setVence] = useState('')

  function cerrar() {
    setTitulo(''); setAsignadoA(''); setVence('')
    setAbierto(false)
    onListo?.()
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!titulo.trim()) return
    crear(accionId, {
      titulo, parentId, asignadoA: asignadoA ? Number(asignadoA) : null, vence: vence || null,
    })
    // Se queda abierto para cargar la siguiente: las tareas se cargan de a varias.
    setTitulo('')
  }

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 px-4 py-3 text-sm font-semibold text-slate-600 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        <Plus className="h-4 w-4" /> {etiqueta}
      </button>
    )
  }

  return (
    <form onSubmit={enviar} className="mt-3 space-y-2.5 rounded-xl border border-brand-200 bg-brand-50/50 p-3 dark:border-brand-800 dark:bg-brand-950/20">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-800 dark:text-brand-200">
        {parentId && <CornerDownRight className="h-4 w-4" />} {etiqueta}
      </p>
      <input
        autoFocus
        value={titulo}
        onChange={e => setTitulo(e.target.value)}
        placeholder="Qué hay que hacer. Ej: Arte del header desktop"
        maxLength={500}
        className={`${CAMPO} w-full`}
      />
      <div className="grid gap-2.5 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-400">Para quién</span>
          <select value={asignadoA} onChange={e => setAsignadoA(e.target.value)} className={`${CAMPO} w-full`}>
            <option value="">Sin asignar por ahora</option>
            {personas.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-400">Vence el (opcional)</span>
          <input type="date" value={vence} onChange={e => setVence(e.target.value)} className={`${CAMPO} w-full`} />
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={cerrar} className="rounded-lg px-3.5 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800">
          Listo
        </button>
        <button
          type="submit"
          disabled={!titulo.trim()}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Crear tarea
        </button>
      </div>
    </form>
  )
}
