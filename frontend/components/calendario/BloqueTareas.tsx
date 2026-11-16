'use client'

import { useState } from 'react'
import { CalendarClock, Check, CornerDownRight, Layers, ListChecks, Plus, Trash2, UserRound } from 'lucide-react'
import { toast } from 'sonner'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { CampoFecha, esFechaGuardable } from './CampoFecha'
import { useCalendario } from '@/lib/calendario/store'
import {
  ETIQUETA_ESTADO_TAREA, NIVELES_DE_TAREA, nivelDeTarea,
  type BarraGuardada, type EstadoTarea, type Persona, type Tarea,
} from '@/lib/calendario/tipos'
import { proximoPaso } from '@/lib/calendario/entregas'
import { useVistaEntregas } from '@/store/entregas'
import {
  FormularioEntregas, configInicial, configParaEnviar, faltaEnConfig, type ConfigEntregas,
} from './entregas/FormularioEntregas'
import { FasesCompactas, faseActualTexto } from './entregas/LineaDeFases'

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
  'en-proceso': 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
  hecha: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200',
}
const ESTADOS: EstadoTarea[] = ['pendiente', 'en-proceso', 'hecha']

/** Las pastillas de una tarea (a quién, cuándo, estado): mismo alto y mismo radio. */
const PASTILLA = 'h-9 rounded-lg border-0 text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-brand-500 sm:h-8'

export function BloqueTareas({ accion, personas, usuarioId, gestiona, conTitulo = true }: {
  accion: BarraGuardada
  personas: Persona[]
  usuarioId: number | null
  gestiona: boolean
  /** Sin el título "Tareas": dentro de la pestaña que ya lo dice. */
  conTitulo?: boolean
}) {
  const tareas = accion.tareas ?? []
  const hechas = tareas.filter(t => t.estado === 'hecha').length
  const raices = tareas.filter(t => !t.parentId || !tareas.some(x => x.id === t.parentId))
  const todas = tareas.length > 0 && hechas === tareas.length

  return (
    <section>
      {(conTitulo || tareas.length > 0) && (
        <div className="mb-3 flex items-center gap-2">
          {conTitulo && (
            <>
              <ListChecks className="h-5 w-5 text-brand-600 dark:text-brand-300" />
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Tareas</h3>
            </>
          )}
          {tareas.length > 0 && (
            <span className={`text-sm tabular-nums ${todas ? 'font-semibold text-emerald-700 dark:text-emerald-300' : 'text-slate-600 dark:text-slate-400'}`}>
              {todas ? '¡Todas hechas!' : `${hechas} de ${tareas.length} hechas`}
            </span>
          )}
        </div>
      )}

      {tareas.length > 0 && (
        <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" role="progressbar" aria-valuemin={0} aria-valuemax={tareas.length} aria-valuenow={hechas} aria-label="Tareas hechas">
          <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-500 ease-suave" style={{ width: `${(hechas / tareas.length) * 100}%` }} />
        </div>
      )}

      {tareas.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-slate-300 px-5 py-8 text-center dark:border-slate-700">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
            <ListChecks className="h-5 w-5" />
          </span>
          <p className="max-w-xs text-sm text-slate-600 dark:text-slate-400">
            {gestiona
              ? 'Esta acción todavía no tiene tareas. Creá la primera y asignásela a alguien: le llega un aviso.'
              : 'Esta acción todavía no tiene tareas. Las crea y las asigna quien lidera el equipo.'}
          </p>
        </div>
      )}

      <ul className="space-y-2">
        {raices.map(t => (
          <ItemTarea
            key={t.id} tarea={t} todas={tareas} accionId={accion.id}
            personas={personas} usuarioId={usuarioId} gestiona={gestiona}
          />
        ))}
      </ul>

      {gestiona && <NuevaTarea accionId={accion.id} parentId={null} personas={personas} usuarioId={usuarioId} etiqueta="Nueva tarea" />}
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
  const personasEstado = useCalendario(s => s.personasEstado)
  const [agregando, setAgregando] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const [sumandoEntregas, setSumandoEntregas] = useState(false)

  const hijas = todas.filter(t => t.parentId === tarea.id)
  const nivel = nivelDeTarea(tarea, todas)
  const esMia = usuarioId != null && tarea.asignadoA === usuarioId
  // Una tarea con entregas queda hecha sola cuando se aprueba la última fase:
  // quien entrega no la tilda (lo mismo exige el servidor). Quien lidera sí.
  const conEntregas = Boolean(tarea.entrega)
  const puedeEstado = gestiona || (esMia && !conEntregas)
  const hecha = tarea.estado === 'hecha'
  const vencida = !hecha && !!tarea.vence && tarea.vence < hoyIso()
  const asignado = personas.find(p => p.id === tarea.asignadoA)

  return (
    <li>
      <div className={`rounded-2xl border px-3.5 py-3 transition-colors duration-300 ${
        hecha
          ? 'border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-800/30'
          : esMia
            ? 'border-brand-300 bg-brand-50/60 dark:border-brand-500/40 dark:bg-brand-500/[.07]'
            : vencida
              ? 'border-rose-200 bg-white dark:border-rose-500/30 dark:bg-slate-900'
              : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'
      }`}>
        <div className="flex items-start gap-3">
          {/* El tilde: un área de 40px para el dedo, con el cuadrado de 24 adentro */}
          <button
            type="button"
            disabled={!puedeEstado}
            onClick={() => cambiar(tarea.id, { estado: hecha ? 'pendiente' : 'hecha' })}
            title={
              conEntregas && !gestiona ? 'Queda hecha sola cuando se aprueba la última fase'
                : !puedeEstado ? 'Solo quien la tiene asignada puede tildarla'
                  : hecha ? 'Volver a pendiente' : 'Marcar como hecha'
            }
            aria-label={hecha ? `Desmarcar ${tarea.titulo}` : `Marcar ${tarea.titulo} como hecha`}
            aria-pressed={hecha}
            className="group/tilde -m-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl disabled:cursor-not-allowed"
          >
            <span className={`flex h-6 w-6 items-center justify-center rounded-md border-2 transition duration-200 group-active/tilde:scale-90 ${
              hecha
                ? 'border-emerald-500 bg-emerald-500 text-white'
                : 'border-slate-300 bg-white group-hover/tilde:border-emerald-500 group-hover/tilde:bg-emerald-50 dark:border-slate-600 dark:bg-slate-900 dark:group-hover/tilde:bg-emerald-500/10'
            } ${!puedeEstado ? 'opacity-50' : ''}`}>
              {hecha && <Check className="h-4 w-4 animate-tilde" strokeWidth={3} />}
            </span>
          </button>

          <div className="min-w-0 flex-1">
            <p className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-[15px] font-semibold leading-snug transition-colors duration-300 ${
              hecha ? 'text-slate-400 line-through decoration-slate-300 dark:text-slate-500 dark:decoration-slate-600' : 'text-slate-900 dark:text-slate-100'
            }`}>
              <span className="min-w-0 break-words">{tarea.titulo}</span>
              {vencida && (
                <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-rose-700 no-underline dark:bg-rose-500/15 dark:text-rose-300">
                  Vencida
                </span>
              )}
            </p>
            {tarea.descripcion && (
              <p className="mt-0.5 whitespace-pre-line text-sm text-slate-600 dark:text-slate-400">{tarea.descripcion}</p>
            )}

            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {gestiona ? (
                <label className="relative flex items-center">
                  <UserRound className="pointer-events-none absolute left-2.5 h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
                  <select
                    value={tarea.asignadoA ?? ''}
                    onChange={e => cambiar(tarea.id, { asignadoA: e.target.value ? Number(e.target.value) : null })}
                    aria-label={`A quién se asigna ${tarea.titulo}`}
                    className={`${PASTILLA} max-w-[12rem] cursor-pointer bg-slate-100 pl-8 pr-7 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700`}
                  >
                    <option value="">Sin asignar</option>
                    {/* Alguien que ya no abre este mundo igual se muestra: no se pierde de quién era. */}
                    {/* Sin la lista de personas todavía no se sabe quién es: no se dice que ya no está. */}
                    {tarea.asignadoA != null && !asignado && (
                      <option value={tarea.asignadoA}>{personasEstado === 'ok' ? 'Alguien que ya no ve este calendario' : 'Asignada'}</option>
                    )}
                    {personas.map(p => <option key={p.id} value={p.id}>{p.nombre}{p.id === usuarioId ? ' (vos)' : ''}</option>)}
                  </select>
                </label>
              ) : (
                <span className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium ${
                  esMia ? 'bg-brand-100 text-brand-800 dark:bg-brand-500/20 dark:text-brand-100' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                }`}>
                  <UserRound className="h-4 w-4" />
                  {tarea.asignadoA == null ? 'Sin asignar' : esMia ? 'La tenés vos' : asignado?.nombre ?? 'Otra persona'}
                </span>
              )}

              {gestiona ? (
                <label className="relative flex items-center">
                  <CalendarClock className={`pointer-events-none absolute left-2.5 h-4 w-4 ${vencida ? 'text-rose-600 dark:text-rose-300' : 'text-slate-500 dark:text-slate-400'}`} aria-hidden />
                  <CampoFecha
                    valor={tarea.vence}
                    onGuardar={vence => cambiar(tarea.id, { vence })}
                    aria-label={`Cuándo vence ${tarea.titulo}`}
                    className={`${PASTILLA} pl-8 pr-2 ${
                      vencida
                        ? 'bg-rose-100 text-rose-700 hover:bg-rose-200 dark:bg-rose-500/15 dark:text-rose-200'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700'
                    }`}
                  />
                </label>
              ) : tarea.vence && (
                <span className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium ${
                  vencida ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
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
                className={`${PASTILLA} cursor-pointer appearance-none px-3 font-semibold disabled:cursor-not-allowed disabled:opacity-70 ${TONO[tarea.estado]}`}
              >
                {ESTADOS.map(e => <option key={e} value={e}>{ETIQUETA_ESTADO_TAREA[e]}</option>)}
              </select>

              {gestiona && (
                <span className="ml-auto flex items-center gap-0.5">
                  {!conEntregas && (
                    <button
                      type="button"
                      onClick={() => setSumandoEntregas(v => !v)}
                      aria-expanded={sumandoEntregas}
                      title="Que lleve entregas por fases para aprobar"
                      className="flex h-9 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-8"
                    >
                      <Layers className="h-4 w-4" /> Entregas
                    </button>
                  )}
                  {nivel < NIVELES_DE_TAREA && (
                    <button
                      type="button"
                      onClick={() => setAgregando(v => !v)}
                      aria-expanded={agregando}
                      className="flex h-9 items-center gap-1 rounded-lg px-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-brand-700 active:scale-95 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-200 sm:h-8"
                    >
                      <Plus className="h-4 w-4" /> Subtarea
                    </button>
                  )}
                  {confirmando ? (
                    <button
                      type="button"
                      autoFocus
                      onClick={() => borrar(tarea.id)}
                      onBlur={() => setConfirmando(false)}
                      className="h-9 animate-scale-in rounded-lg bg-rose-600 px-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 active:scale-95 sm:h-8"
                    >
                      {hijas.length > 0 ? 'Borrar con sus subtareas' : 'Sí, borrar'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmando(true)}
                      aria-label={`Borrar ${tarea.titulo}`}
                      title="Borrar la tarea"
                      className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 active:scale-95 dark:text-slate-500 dark:hover:bg-rose-500/10 dark:hover:text-rose-300 sm:h-8 sm:w-8"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </span>
              )}
            </div>

            {tarea.entrega && (
              <EntregasDeLaTarea tarea={tarea} personas={personas} usuarioId={usuarioId} />
            )}
          </div>
        </div>
        {sumandoEntregas && !conEntregas && (
          <SumarEntregas
            tarea={tarea} accionId={accionId} personas={personas} usuarioId={usuarioId}
            onListo={() => setSumandoEntregas(false)}
          />
        )}
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
              accionId={accionId} parentId={tarea.id} personas={personas} usuarioId={usuarioId}
              etiqueta="Nueva subtarea" abierta onListo={() => setAgregando(false)}
            />
          )}
        </div>
      )}
    </li>
  )
}

function NuevaTarea({ accionId, parentId, personas, usuarioId, etiqueta, abierta = false, onListo }: {
  accionId: string
  parentId: string | null
  personas: Persona[]
  usuarioId: number | null
  etiqueta: string
  abierta?: boolean
  onListo?: () => void
}) {
  const crear = useCalendario(s => s.crearTarea)
  const configurarEntregas = useCalendario(s => s.configurarEntregas)
  const personasEstado = useCalendario(s => s.personasEstado)
  const [abierto, setAbierto] = useState(abierta)
  const [titulo, setTitulo] = useState('')
  const [asignadoA, setAsignadoA] = useState('')
  const [vence, setVence] = useState('')
  // Con entregas por fases: la agencia (o quien diseña) sube versiones y la
  // cadena de aprobadores las aprueba o las devuelve (15/11/2026).
  const [conEntregas, setConEntregas] = useState(false)
  const [config, setConfig] = useState<ConfigEntregas>(() => configInicial())
  const responsable = asignadoA ? Number(asignadoA) : null
  const faltaEntregas = !conEntregas ? null
    : responsable == null ? 'Elegí quién entrega (la agencia o quien diseña).'
      : faltaEnConfig(config, responsable)
  const valida = titulo.trim() !== '' && !faltaEntregas

  function cerrar() {
    setTitulo(''); setAsignadoA(''); setVence('')
    setConEntregas(false); setConfig(configInicial())
    setAbierto(false)
    onListo?.()
  }

  function crearLaEscrita() {
    if (!valida) return
    const id = crear(accionId, {
      titulo, parentId, asignadoA: responsable,
      vence: esFechaGuardable(vence) ? vence : null,
    })
    // Va en la cola de la acción, detrás del alta de la tarea.
    if (id && conEntregas) {
      void configurarEntregas(accionId, id, configParaEnviar(config)).then(ok => {
        if (ok) toast.success('Listo: la tarea lleva entregas. Ya puede entregar la primera fase.')
      })
    }
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    crearLaEscrita()
    // Se queda abierto para cargar la siguiente: las tareas se cargan de a varias.
    setTitulo('')
    if (conEntregas) { setConEntregas(false); setConfig(configInicial()) }
  }

  /** "Listo" con algo escrito se lee como "guardá esto y cerrá": antes la
   *  tiraba sin avisar (pruebas del 15/11/2026). */
  function listo() {
    crearLaEscrita()
    cerrar()
  }

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="mt-3 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-300 px-4 text-sm font-semibold text-slate-600 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 active:scale-[.99] dark:border-slate-700 dark:text-slate-300 dark:hover:border-brand-500/60 dark:hover:bg-brand-500/10 dark:hover:text-brand-200"
      >
        <Plus className="h-4 w-4" /> {etiqueta}
      </button>
    )
  }

  return (
    <form
      onSubmit={enviar}
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); cerrar() } }}
      className="mt-3 animate-scale-in space-y-3 rounded-2xl border border-brand-200 bg-brand-50/50 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/[.06]"
    >
      <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-800 dark:text-brand-200">
        {parentId && <CornerDownRight className="h-4 w-4" />} {etiqueta}
      </p>
      <input
        autoFocus
        value={titulo}
        onChange={e => setTitulo(e.target.value)}
        placeholder="Qué hay que hacer. Ej: Arte del header desktop"
        aria-label="Qué hay que hacer"
        maxLength={500}
        className="campo"
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="etiqueta-campo">{conEntregas ? 'Quién entrega (agencia o diseño)' : 'Para quién'}</span>
          <select value={asignadoA} onChange={e => setAsignadoA(e.target.value)} className="campo">
            <option value="">{conEntregas ? 'Elegí quién entrega…' : 'Sin asignar por ahora'}</option>
            {personas.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </select>
          {personasEstado === 'error' && (
            <span className="mt-1 block text-xs text-amber-700 dark:text-amber-300">
              No se pudo traer la lista de personas. Se vuelve a intentar sola en unos segundos.
            </span>
          )}
        </label>
        <label className="block">
          <span className="etiqueta-campo">Vence el (opcional)</span>
          <input type="date" min="2000-01-01" max="2100-12-31" value={vence} onChange={e => setVence(e.target.value)} className="campo" />
        </label>
      </div>

      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${
        conEntregas ? 'border-brand-300 bg-white dark:border-brand-500/40 dark:bg-slate-900' : 'border-slate-200 bg-white/60 hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900/40'
      }`}>
        <input
          type="checkbox"
          checked={conEntregas}
          onChange={e => setConEntregas(e.target.checked)}
          className="mt-0.5 h-5 w-5 shrink-0 rounded accent-brand-600"
        />
        <span className="min-w-0">
          <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <Layers className="h-4 w-4 text-brand-600 dark:text-brand-300" /> Lleva entregas para aprobar
          </span>
          <span className="block text-xs text-slate-600 dark:text-slate-400">
            Quien entrega sube la pieza por fases; quienes aprueban la aprueban o piden cambios marcando sobre la imagen.
          </span>
        </span>
      </label>

      {conEntregas && (
        <div className="animate-fade-in rounded-xl border border-slate-200 bg-white p-3.5 dark:border-slate-700 dark:bg-slate-900">
          <FormularioEntregas
            valor={config}
            onCambiar={setConfig}
            personas={personas}
            responsableId={responsable}
            usuarioId={usuarioId}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {titulo.trim() && faltaEntregas && (
          <p className="mr-auto text-xs text-amber-700 dark:text-amber-300">{faltaEntregas}</p>
        )}
        <button type="button" onClick={listo} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Listo
        </button>
        <button
          type="submit"
          disabled={!valida}
          className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
        >
          {conEntregas ? 'Crear tarea con entregas' : 'Crear tarea'}
        </button>
      </div>
    </form>
  )
}

/**
 * En la tarea, si lleva entregas: en qué fase va y el próximo paso, con su
 * botón. Es la puerta a la vista de entregas (encima de la ficha).
 */
function EntregasDeLaTarea({ tarea, personas, usuarioId }: {
  tarea: Tarea
  personas: Persona[]
  usuarioId: number | null
}) {
  const abrir = useVistaEntregas(s => s.abrir)
  const r = tarea.entrega!
  const nombreDe = (id: number | null) => personas.find(p => p.id === id)?.nombre ?? 'alguien'
  const paso = proximoPaso(r, tarea.asignadoA, usuarioId, nombreDe)
  const meToca = paso.aQuien === 'vos'
  return (
    <div className={`mt-3 rounded-xl border p-2.5 ${
      meToca ? 'border-brand-200 bg-brand-50/70 dark:border-brand-500/30 dark:bg-brand-500/10' : 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/40'
    }`}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium text-slate-600 dark:text-slate-300">
        <Layers className="h-3.5 w-3.5 text-brand-600 dark:text-brand-300" aria-hidden />
        <FasesCompactas resumen={r} />
        {faseActualTexto(r)}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <p className={`min-w-0 flex-1 text-sm font-semibold ${meToca ? 'text-brand-800 dark:text-brand-100' : 'text-slate-700 dark:text-slate-200'}`}>
          {paso.texto}
        </p>
        <button
          type="button"
          onClick={() => abrir(tarea.id, paso.accion ?? 'ver')}
          className={`min-h-[40px] shrink-0 rounded-xl px-3.5 text-sm font-bold transition active:scale-[.98] ${
            meToca ? 'bg-brand-600 text-white shadow-sm hover:bg-brand-700' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-200 dark:ring-slate-700 dark:hover:bg-slate-800'
          }`}
        >
          {paso.accion === 'entregar' ? 'Entregar' : paso.accion === 'revisar' ? 'Revisar' : 'Ver entregas'}
        </button>
      </div>
    </div>
  )
}

/** Sumarle entregas a una tarea que ya existe (quien lidera). */
function SumarEntregas({ tarea, accionId, personas, usuarioId, onListo }: {
  tarea: Tarea
  accionId: string
  personas: Persona[]
  usuarioId: number | null
  onListo: () => void
}) {
  const configurar = useCalendario(s => s.configurarEntregas)
  const [config, setConfig] = useState<ConfigEntregas>(() => configInicial())
  const [guardando, setGuardando] = useState(false)
  const falta = tarea.asignadoA == null
    ? 'Primero asigná la tarea a quien va a entregar (la agencia o quien diseña).'
    : faltaEnConfig(config, tarea.asignadoA)

  async function guardar() {
    if (falta || guardando) return
    setGuardando(true)
    const ok = await configurar(accionId, tarea.id, configParaEnviar(config))
    setGuardando(false)
    if (ok) {
      toast.success('Listo: la tarea lleva entregas.')
      onListo()
    }
  }

  return (
    <div className="mt-2 animate-scale-in space-y-3 rounded-2xl border border-brand-200 bg-brand-50/50 p-3.5 dark:border-brand-500/30 dark:bg-brand-500/[.06]">
      <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-800 dark:text-brand-200">
        <Layers className="h-4 w-4" /> Que «{tarea.titulo}» lleve entregas
      </p>
      <div className="rounded-xl border border-slate-200 bg-white p-3.5 dark:border-slate-700 dark:bg-slate-900">
        <FormularioEntregas valor={config} onCambiar={setConfig} personas={personas} responsableId={tarea.asignadoA} usuarioId={usuarioId} />
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {falta && <p className="mr-auto text-xs text-amber-700 dark:text-amber-300">{falta}</p>}
        <button type="button" onClick={onListo} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button
          type="button"
          onClick={() => void guardar()}
          disabled={!!falta || guardando}
          className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
        >
          Guardar
        </button>
      </div>
    </div>
  )
}
