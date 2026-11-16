'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Bell, CalendarClock, Check, CopyPlus, LayoutGrid, ListChecks, Loader2, X } from 'lucide-react'
import { toast } from 'sonner'
import { CampoFecha, esFechaGuardable } from './CampoFecha'
import { useDialogo } from './useDialogo'
import { CLASE_MANIJA, useDeslizarParaCerrar } from './useDeslizarParaCerrar'
import {
  alAnioQueViene, chocaCon, cuantas, diaDeLaSemana, enLista, nombreParaLaCopia, queSeCopia, rangoDeLaCopia,
} from '@/lib/calendario/copiar'
import { diasEntre, fechaCorta, fechaLarga, rangoLargo } from '@/lib/calendario/fechas'
import { usePermisosCalendario } from '@/lib/calendario/permisos'
import { useCalendario } from '@/lib/calendario/store'
import type { BarraGuardada } from '@/lib/calendario/tipos'
import type { CalendarioCopia } from '@/lib/api'

/** "30/11/2026": en el aviso de cómo quedó hace falta el año. */
const conAnio = (iso: string) => `${fechaCorta(iso)}/${iso.slice(0, 4)}`

/**
 * "Copiar a otra fecha", desde la ficha de una acción o de un envío suelto
 * (pedido de Ivan, 15/11/2026: que el Ciberlunes 2026 nazca del 2025 con
 * todo lo que tenía).
 *
 * Arranca en "al año que viene" (52 semanas después: mismo día de la
 * semana), que es a lo que se viene casi siempre; se puede elegir otra fecha
 * con el mismo campo que usa el resto del calendario. Antes de copiar dice
 * qué se lleva, qué se resetea y si en esas fechas ya hay una acción con ese
 * nombre, que es la señal de que alguien ya la copió. Eso no frena: avisa.
 */
export function CopiarAccion({ accion, onCerrar }: {
  accion: BarraGuardada
  onCerrar: () => void
}) {
  // Se monta al abrirse y se desmonta al cerrarse: cada vez arranca de cero,
  // al año que viene y con el nombre sugerido.
  const copiarAccion = useCalendario(s => s.copiarAccion)
  const irAAccion = useCalendario(s => s.irAAccion)
  const barras = useCalendario(s => s.barras)
  const personas = useCalendario(s => s.personas)
  const personasEstado = useCalendario(s => s.personasEstado)
  const { gestionaTareas } = usePermisosCalendario()

  const sugerida = alAnioQueViene(accion.desde)
  const [desde, setDesde] = useState(sugerida)
  // Mientras nadie lo toca, el nombre sigue a la fecha ("2025" → el año de la
  // fecha elegida). Si la persona lo escribe, queda el suyo.
  const [nombreEscrito, setNombreEscrito] = useState<string | null>(null)
  const [copiando, setCopiando] = useState(false)

  // Escape cierra esto y no la ficha de abajo (por eso va en la captura y
  // corta ahí el evento, como el editor). Mientras copia no se cierra: la
  // respuesta tiene que tener dónde caer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      if (!copiando) onCerrar()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [copiando, onCerrar])

  const cajaRef = useRef<HTMLFormElement>(null)
  const cerrarSiSePuede = () => { if (!copiando) onCerrar() }
  useDialogo(true, cajaRef)
  useDeslizarParaCerrar(cajaRef, true, cerrarSiSePuede)

  const resumen = useMemo(
    () => queSeCopia(accion, personasEstado === 'ok' ? new Set(personas.map(p => p.id)) : null, gestionaTareas),
    [accion, personas, personasEstado, gestionaTareas],
  )

  const esEnvio = accion.seccion === 'envio'
  const { hasta } = rangoDeLaCopia(accion, esFechaGuardable(desde) ? desde : sugerida)
  // El fin también tiene que ser de un año real (una acción larga corrida al 2100).
  const fechaOk = esFechaGuardable(desde) && esFechaGuardable(hasta)
  const nombreSugerido = fechaOk ? nombreParaLaCopia(accion.nombre, accion.desde, accion.hasta, desde) : accion.nombre
  const nombre = nombreEscrito ?? nombreSugerido
  const valido = fechaOk && nombre.trim().length > 0
  const alAnio = desde === sugerida
  const dias = diasEntre(accion.desde, accion.hasta) + 1
  const corrimiento = fechaOk ? diasEntre(accion.desde, desde) : 0
  const choque = fechaOk ? chocaCon(Object.values(barras), accion.seccion, nombre, desde, hasta) : null
  const mismoDia = fechaOk && diaDeLaSemana(desde) === diaDeLaSemana(accion.desde)

  async function copiar(e: React.FormEvent) {
    e.preventDefault()
    if (!valido || copiando) return
    setCopiando(true)
    const r = await copiarAccion(accion.id, { desde, nombre: nombre.trim() })
    setCopiando(false)
    onCerrar()
    // null: el servidor dijo que no o se cortó la conexión. En los dos casos
    // ya salió el aviso que corresponde (ver escribir en el store).
    if (!r) return
    avisarComoQuedo(r, nombre.trim(), desde)
    // A la acción nueva, por el mismo camino que la campanita: si todavía no
    // está en pantalla (era un reintento), se la busca en el servidor.
    if (!(await irAAccion(r.id))) toast.error('La copia quedó guardada, pero no se pudo abrir: buscala en su mes.')
  }

  const fila = 'flex items-start gap-2.5 text-sm text-slate-700 dark:text-slate-300'
  const nota = 'mt-0.5 block text-[13px] text-amber-700 dark:text-amber-300'

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-4">
      <div className="velo animate-fade-in" onClick={cerrarSiSePuede} aria-hidden />
      <form
        ref={cajaRef}
        onSubmit={copiar}
        role="dialog"
        aria-modal="true"
        aria-labelledby="copiar-titulo"
        aria-describedby="copiar-bajada"
        className="relative flex max-h-[92dvh] w-full max-w-md animate-sheet-up flex-col overflow-hidden rounded-t-3xl bg-white shadow-panel dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl"
      >
        <div aria-hidden className={CLASE_MANIJA} />
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-300 px-5 pb-3.5 pt-4 dark:border-slate-800">
          <div className="min-w-0">
            <h3 id="copiar-titulo" className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-slate-100">
              <CopyPlus className="h-5 w-5 text-brand-600 dark:text-brand-300" aria-hidden /> Copiar a otra fecha
            </h3>
            <p id="copiar-bajada" className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
              {esEnvio ? 'Nace un envío nuevo' : 'Nace una acción nueva'} con lo que tiene <strong className="font-semibold text-slate-700 dark:text-slate-200">{accion.nombre}</strong>.
            </p>
          </div>
          <button
            type="button"
            onClick={cerrarSiSePuede}
            aria-label="Cerrar sin copiar"
            title="Cerrar (Esc)"
            className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200 sm:h-10 sm:w-10"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 py-5">
          <fieldset>
            <legend className="etiqueta-campo">{esEnvio ? 'Sale' : 'Arranca'}</legend>
            <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-stretch">
              <button
                type="button"
                onClick={() => setDesde(sugerida)}
                aria-pressed={alAnio}
                className={`flex min-h-[52px] items-center gap-2.5 rounded-xl border px-3 text-left transition active:scale-[.99] ${
                  alAnio
                    ? 'border-brand-400 bg-brand-50 text-brand-900 ring-1 ring-brand-400 dark:border-brand-500/60 dark:bg-brand-500/10 dark:text-brand-100 dark:ring-brand-500/60'
                    : 'border-slate-300 bg-white text-slate-700 hover:border-brand-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-brand-500/50'
                }`}
              >
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                  alAnio ? 'border-brand-600 bg-brand-600 text-white dark:border-brand-400 dark:bg-brand-400 dark:text-slate-900' : 'border-slate-300 dark:border-slate-600'
                }`}>
                  {alAnio && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">Al año que viene</span>
                  <span className="block text-xs opacity-80">
                    {diaDeLaSemana(sugerida)} {fechaLarga(sugerida)} · 52 semanas después
                  </span>
                </span>
              </button>
              <label className="block">
                <span className="sr-only">Otra fecha</span>
                <CampoFecha
                  valor={desde}
                  onGuardar={f => { if (f) setDesde(f) }}
                  aria-label={esEnvio ? 'Otra fecha en que sale' : 'Otra fecha en que arranca'}
                  className={`campo !h-full min-h-[52px] ${alAnio ? '' : '!border-brand-400 ring-1 ring-brand-400 dark:!border-brand-500/60'}`}
                />
              </label>
            </div>

            <p className="mt-2.5 rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm text-slate-600 dark:bg-slate-800/50 dark:text-slate-300" aria-live="polite">
              {!fechaOk ? (
                <span className="font-medium text-rose-700 dark:text-rose-300">Revisá la fecha: tiene que estar completa y con un año real.</span>
              ) : esEnvio ? (
                <>Sale <strong className="text-slate-900 dark:text-white">{rangoLargo(desde, desde)}</strong>{accion.hora ? ` a las ${accion.hora}` : ''}.</>
              ) : (
                <>
                  Va <strong className="text-slate-900 dark:text-white">{rangoLargo(desde, hasta)}</strong> · {dias === 1 ? '1 día' : `${dias} días`}, como la original.
                </>
              )}
              {fechaOk && (
                <span className="mt-1 block text-[13px]">
                  {mismoDia
                    ? `Cae ${diaDeLaSemana(desde)}, igual que la original.`
                    : `La original ${esEnvio ? 'salía' : 'arrancaba'} un ${diaDeLaSemana(accion.desde)}; esta cae ${diaDeLaSemana(desde)}.`}
                </span>
              )}
            </p>
          </fieldset>

          <label className="block">
            <span className="etiqueta-campo">Nombre</span>
            <input
              value={nombre}
              onChange={e => setNombreEscrito(e.target.value)}
              maxLength={1000}
              className="campo"
            />
            {nombreEscrito === null && nombreSugerido !== accion.nombre && (
              <span className="mt-1.5 block text-[13px] text-slate-500 dark:text-slate-400">
                Le corrimos el año: la original se llama «{accion.nombre}».
              </span>
            )}
          </label>

          <section aria-labelledby="copiar-que">
            <h4 id="copiar-que" className="etiqueta-campo">Qué se copia</h4>
            <ul className="space-y-2.5 rounded-xl border border-slate-300 px-3.5 py-3 dark:border-slate-700">
              {!esEnvio && (
                <li className={fila}>
                  <LayoutGrid className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden />
                  <span>
                    {resumen.piezas === 0 ? 'Sin piezas' : cuantas(resumen.piezas, 'pieza', 'piezas')}
                    {resumen.piezas > 0 && <span className="text-slate-500 dark:text-slate-400"> · en Pendiente y sin la marca de SharePoint</span>}
                  </span>
                </li>
              )}
              <li className={fila}>
                <ListChecks className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden />
                <span>
                  {resumen.tareasSinPermiso > 0 ? (
                    <span className="text-amber-800 dark:text-amber-200">
                      Las {cuantas(resumen.tareasSinPermiso, 'tarea', 'tareas')} no se copian: cargar tareas pide un permiso que no tenés.
                    </span>
                  ) : resumen.tareas === 0 ? 'Sin tareas' : (
                    <>
                      {cuantas(resumen.tareas, 'tarea', 'tareas')}
                      <span className="text-slate-500 dark:text-slate-400"> · en Pendiente, con sus subtareas y el vencimiento corrido</span>
                    </>
                  )}
                  {resumen.sinResponsable > 0 && (
                    <span className={nota}>
                      {resumen.sinResponsable === 1 ? '1 queda' : `${resumen.sinResponsable} quedan`} sin responsable: esa persona ya no entra a este calendario.
                    </span>
                  )}
                </span>
              </li>
              <li className={fila}>
                <Bell className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden />
                <span>
                  {resumen.avisos === 0 && resumen.avisosSinNadie === 0 ? 'Sin avisos' : (
                    <>
                      {cuantas(resumen.avisos, 'aviso', 'avisos')}
                      <span className="text-slate-500 dark:text-slate-400"> · los mismos días antes</span>
                    </>
                  )}
                  {resumen.destinatariosQuitados > 0 && (
                    <span className={nota}>
                      {resumen.destinatariosQuitados === 1 ? 'Sale 1 persona' : `Salen ${resumen.destinatariosQuitados} personas`} de los avisos: ya no entra{resumen.destinatariosQuitados === 1 ? '' : 'n'} a este calendario
                      {resumen.avisosSinNadie > 0 && ` (${resumen.avisosSinNadie === 1 ? 'un aviso queda' : `${resumen.avisosSinNadie} avisos quedan`} sin nadie y no se copia${resumen.avisosSinNadie === 1 ? '' : 'n'})`}.
                    </span>
                  )}
                </span>
              </li>
              {fechaOk && corrimiento !== 0 && (
                <li className={fila}>
                  <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden />
                  <span className="text-slate-500 dark:text-slate-400">
                    Las fechas propias de piezas y tareas se corren lo mismo que {esEnvio ? 'el envío' : 'la acción'}: {Math.abs(corrimiento)} días {corrimiento > 0 ? 'más adelante' : 'antes'}.
                  </span>
                </li>
              )}
            </ul>
          </section>

          {choque && (
            <p role="alert" className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>
                {choque.id === accion.id ? 'Esas fechas se cruzan con la original, que se llama igual.' : (
                  <>Ya hay {esEnvio ? 'un envío' : 'una acción'} <strong>{choque.nombre}</strong> {rangoLargo(choque.desde, choque.hasta)}.</>
                )}{' '}
                Si la copiás igual, van a quedar dos.
              </span>
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-slate-300 bg-slate-50 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-800 dark:bg-slate-800/40">
          <button
            type="button"
            onClick={cerrarSiSePuede}
            disabled={copiando}
            className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 active:scale-95 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-700 sm:min-h-[40px]"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!valido || copiando}
            className="flex min-h-[44px] items-center gap-1.5 rounded-xl bg-brand-600 px-5 text-sm font-semibold text-white shadow-sm shadow-brand-600/25 transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
          >
            {copiando
              ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Copiando…</>
              : <><CopyPlus className="h-4 w-4" aria-hidden /> {choque ? 'Copiar igual' : 'Copiar'}</>}
          </button>
        </footer>
      </form>
    </div>
  )
}

/** El aviso de cómo quedó: qué se copió y, si algo no, por qué. */
function avisarComoQuedo(r: CalendarioCopia, nombre: string, desde: string) {
  if (r.yaExistia) {
    toast.success(`«${nombre}» ya estaba copiada: no se duplicó.`)
    return
  }
  const c = r.copiadas ?? { piezas: 0, tareas: 0, avisos: 0 }
  const lleva = [
    c.piezas ? cuantas(c.piezas, 'pieza', 'piezas') : '',
    c.tareas ? cuantas(c.tareas, 'tarea', 'tareas') : '',
    c.avisos ? cuantas(c.avisos, 'aviso', 'avisos') : '',
  ].filter(Boolean)
  const detalle = [
    lleva.length ? `Con ${enLista(lleva)}${c.piezas || c.tareas ? ', todo en pendiente' : ''}.` : '',
    r.tareasSinPermiso ? `Las ${cuantas(r.tareasSinPermiso, 'tarea', 'tareas')} no se copiaron: cargar tareas pide un permiso que no tenés.` : '',
    r.sinResponsable ? `${r.sinResponsable === 1 ? 'Una tarea quedó' : `${r.sinResponsable} tareas quedaron`} sin responsable: esa persona ya no entra a este calendario.` : '',
    r.destinatariosQuitados ? `${r.destinatariosQuitados === 1 ? 'Salió 1 persona' : `Salieron ${r.destinatariosQuitados} personas`} de los avisos por lo mismo.` : '',
    r.avisados ? `Le llegó el aviso de sus tareas a ${r.avisados === 1 ? '1 persona' : `${r.avisados} personas`}.` : '',
    r.enviadosAhora ? 'Un aviso ya tocaba con la fecha nueva y salió ahora.' : '',
  ].filter(Boolean).join(' ')
  const titulo = `Listo: «${nombre}» arranca el ${conAnio(desde)}.`
  if (r.tareasSinPermiso || r.sinResponsable || r.destinatariosQuitados) toast.warning(titulo, { description: detalle, duration: 10_000 })
  else toast.success(titulo, { description: detalle || undefined, duration: 6_000 })
}
