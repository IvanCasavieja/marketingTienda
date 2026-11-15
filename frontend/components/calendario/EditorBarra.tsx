'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, Trash2, X } from 'lucide-react'
import { SIN_CATEGORIA, esSinCategoria } from '@/lib/calendario/categorias'
import { PALETA, colorPorDefecto, textoSobre } from '@/lib/calendario/colores'
import {
  claveDe, diasEntre, mesSiguiente, nombreMes, primerDiaDe, rangoLargo, sumarDias, ultimoDiaDe,
} from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import { formatosDeCanal, tituloDeCanal, type BarraGuardada } from '@/lib/calendario/tipos'
import { useDialogo } from './useDialogo'
import { esFechaGuardable } from './CampoFecha'
import { CLASE_MANIJA, useDeslizarParaCerrar } from './useDeslizarParaCerrar'

const TEXTOS: Record<string, { nueva: string; editar: string; unaSola: string }> = {
  comercial: { nueva: 'Nueva acción', editar: 'Editar acción', unaSola: 'Es una sola acción' },
  retail: { nueva: 'Nueva campaña', editar: 'Editar campaña', unaSola: 'Es una sola campaña' },
  header: { nueva: 'Nuevo banner', editar: 'Editar banner', unaSola: 'Es un solo banner' },
  envio: { nueva: 'Nuevo envío', editar: 'Editar envío', unaSola: 'Es un solo envío' },
}

/** Los meses que toca un rango, para decir "se ve en setiembre y octubre". */
function mesesQueToca(desde: string, hasta: string): string[] {
  const out: string[] = []
  for (let c = claveDe(desde); c <= claveDe(hasta) && out.length < 40; c = mesSiguiente(c, 1)) {
    out.push(nombreMes(c).split(' ')[0])
  }
  return out
}

export function EditorBarra() {
  const edicion = useCalendario(s => s.edicion)
  const mesActivo = useCalendario(s => s.mesActivo)
  const cerrar = useCalendario(s => s.cerrarEditor)
  const guardar = useCalendario(s => s.guardarBarra)
  const borrar = useCalendario(s => s.borrarBarra)

  const esAlta = !edicion?.barra
  const textos = TEXTOS[edicion?.seccion ?? 'comercial']
  // Un envío suelto sale un día y a una hora: no tiene fecha de fin.
  const esEnvio = edicion?.seccion === 'envio'
  const formatos = esEnvio && edicion ? formatosDeCanal(edicion.banda) : []

  const [nombre, setNombre] = useState('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [color, setColor] = useState<string>(PALETA[0])
  const [formato, setFormato] = useState('')
  const [hora, setHora] = useState('')
  // Eliminar pide confirmación: se lleva las tareas, piezas y avisos, y no
  // se puede deshacer (pruebas del 15/11/2026: un clic borraba todo).
  // Atada a la edición abierta: al abrir otra, vuelve a no estar confirmando.
  const [confirmandoEn, setConfirmandoEn] = useState<object | null>(null)
  const confirmandoBorrar = edicion !== null && confirmandoEn === edicion

  useEffect(() => {
    if (!edicion) return
    const formatosDelCanal = edicion.seccion === 'envio' ? formatosDeCanal(edicion.banda) : []
    if (edicion.barra) {
      setNombre(edicion.barra.nombre)
      setDesde(edicion.barra.desde)
      setHasta(edicion.barra.hasta)
      setColor(edicion.barra.color ?? colorPorDefecto(edicion.barra.nombre))
      setFormato(edicion.barra.formato || formatosDelCanal[0] || '')
      setHora(edicion.barra.hora ?? '')
    } else {
      // Por defecto una semana, sin pasarse del mes donde se hizo clic. Para
      // que cruce de mes alcanza con correr la fecha de fin.
      const inicio = edicion.fechaInicial ?? primerDiaDe(mesActivo)
      const finDeMes = ultimoDiaDe(claveDe(inicio))
      const semana = sumarDias(inicio, 6)
      setNombre('')
      setDesde(inicio)
      setHasta(semana < finDeMes ? semana : finDeMes)
      setColor(PALETA[Math.floor(Math.random() * PALETA.length)])
      setFormato(formatosDelCanal[0] ?? '')
      setHora('')
    }
  }, [edicion, mesActivo])

  // Escape cierra el editor, y solo el editor: la ficha que puede estar
  // abajo se queda. Por eso va en la captura y corta ahí el evento.
  useEffect(() => {
    if (!edicion) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      cerrar()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [edicion, cerrar])

  const formRef = useRef<HTMLFormElement>(null)
  useDialogo(Boolean(edicion), formRef)
  useDeslizarParaCerrar(formRef, Boolean(edicion), cerrar)

  if (!edicion) return null

  const hastaReal = esEnvio ? desde : hasta
  // Completas y con un año real: el campo de fecha deja escribir 0202.
  const fechasCompletas = esFechaGuardable(desde) && esFechaGuardable(hastaReal)
  const fechasOk = fechasCompletas && hastaReal >= desde
  const valido = nombre.trim().length > 0 && fechasOk
  const dias = fechasOk ? diasEntre(desde, hastaReal) + 1 : 0
  const meses = fechasOk ? mesesQueToca(desde, hastaReal) : []

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!valido) return
    guardar({
      nombre: nombre.trim(), desde, hasta: hastaReal, color,
      ...(esEnvio ? { formato: formato || null, hora: hora || undefined } : {}),
    })
  }

  // En una acción la categoría no se elige acá sino en su ficha: acá solo se
  // dice cuál tiene, o que se le pone después.
  const categoria = edicion.barra?.banda ?? edicion.banda
  const bajadaDeAccion = !esSinCategoria(categoria)
    ? `Categoría: ${categoria}`
    : esAlta
      ? 'La categoría y las tareas se cargan después, adentro de la acción.'
      : SIN_CATEGORIA

  // z-[60]: por encima de la ficha (z-50), desde donde también se abre; si no, quedaba tapado.
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-4"
    >
      <div className="velo animate-fade-in" onClick={cerrar} aria-hidden />
      <form
        ref={formRef}
        onSubmit={enviar}
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-titulo"
        aria-describedby="editor-bajada"
        className="relative flex max-h-[92dvh] w-full max-w-md animate-sheet-up flex-col overflow-hidden rounded-t-3xl bg-white shadow-panel dark:bg-slate-900 dark:ring-1 dark:ring-slate-800 sm:animate-scale-in sm:rounded-2xl"
      >
        <div aria-hidden className={CLASE_MANIJA} />
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-5 pb-3.5 pt-4 dark:border-slate-800">
          <div className="min-w-0">
            <h3 id="editor-titulo" className="text-lg font-bold text-slate-900 dark:text-slate-100">
              {esAlta ? textos.nueva : textos.editar}
            </h3>
            <p id="editor-bajada" className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
              {edicion.seccion === 'header'
                ? `Posición ${edicion.banda.replace('pos-', '')} del header`
                : esEnvio
                  ? `${tituloDeCanal(edicion.banda)} · envío suelto, sin una acción detrás`
                  : edicion.seccion === 'comercial'
                    ? bajadaDeAccion
                    : edicion.banda}
            </p>
          </div>
          <button
            type="button"
            onClick={cerrar}
            aria-label="Cerrar sin guardar"
            title="Cerrar (Esc)"
            className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200 sm:h-10 sm:w-10"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 py-5">
          <label className="block">
            <span className="etiqueta-campo">Nombre</span>
            <input
              autoFocus
              value={nombre}
              onChange={e => setNombre(e.target.value)}
              maxLength={1000}
              placeholder={esAlta ? (esEnvio ? 'Ej: Mailing Día de la Madre' : 'Ej: Fiesta de Italia') : ''}
              className="campo"
            />
          </label>

          {esEnvio ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="etiqueta-campo">Sale el</span>
                  <input type="date" min="2000-01-01" max="2100-12-31" value={desde} onChange={e => setDesde(e.target.value)} className="campo" />
                </label>
                <label className="block">
                  <span className="etiqueta-campo">A las</span>
                  <input type="time" value={hora} onChange={e => setHora(e.target.value)} className="campo" />
                </label>
              </div>
              {formatos.length > 1 && (
                <label className="block">
                  <span className="etiqueta-campo">Qué es</span>
                  <select value={formato} onChange={e => setFormato(e.target.value)} className="campo">
                    {formatos.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </label>
              )}
              <p className="rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm text-slate-600 dark:bg-slate-800/50 dark:text-slate-300">
                {desde
                  ? <>Sale <strong className="text-slate-900 dark:text-white">{rangoLargo(desde, desde)}</strong>{hora ? ` a las ${hora}` : ', sin hora todavía'}.</>
                  : <span className="font-medium text-rose-600 dark:text-rose-400">Falta la fecha en que sale.</span>}
              </p>
            </>
          ) : (
          <>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="etiqueta-campo">Arranca</span>
              <input
                type="date"
                min="2000-01-01"
                max="2100-12-31"
                value={desde}
                onChange={e => {
                  const v = e.target.value
                  setDesde(v)
                  // Si el inicio pasa al fin, el fin lo acompaña: nunca queda al revés.
                  if (v && hasta && hasta < v) setHasta(v)
                }}
                className="campo"
              />
            </label>
            <label className="block">
              <span className="etiqueta-campo">Termina</span>
              <input
                type="date"
                value={hasta}
                min={desde || '2000-01-01'}
                max="2100-12-31"
                onChange={e => setHasta(e.target.value)}
                aria-invalid={!fechasOk || undefined}
                className={`campo ${!fechasOk ? '!border-rose-400 focus:!ring-rose-500/25' : ''}`}
              />
            </label>
          </div>

          <p className={`rounded-xl px-3.5 py-2.5 text-sm ${fechasOk ? 'bg-slate-50 text-slate-600 dark:bg-slate-800/50 dark:text-slate-300' : 'bg-rose-50 dark:bg-rose-500/10'}`} aria-live="polite">
            {fechasOk ? (
              <>
                Va <strong className="text-slate-900 dark:text-white">{rangoLargo(desde, hasta)}</strong> · {dias === 1 ? '1 día' : `${dias} días`}
                {meses.length > 1 && (
                  <span className="mt-1 block text-[13px]">
                    {textos.unaSola}: se ve en {meses.slice(0, -1).join(', ')} y {meses[meses.length - 1]}, y
                    lo que le cambies en un mes cambia en todos.
                  </span>
                )}
              </>
            ) : (
              <span className="font-medium text-rose-700 dark:text-rose-300">
                {fechasCompletas ? 'La fecha de fin no puede ser anterior a la de inicio.' : 'Revisá las fechas: tienen que estar completas y con un año real.'}
              </span>
            )}
          </p>
          </>
          )}

          <fieldset>
            <legend className="etiqueta-campo">Color</legend>
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Color">
              {PALETA.map((c, i) => {
                const elegido = color === c
                return (
                  <button
                    key={c}
                    type="button"
                    role="radio"
                    aria-checked={elegido}
                    aria-label={`Color ${i + 1}`}
                    title={c}
                    onClick={() => setColor(c)}
                    style={{ backgroundColor: c, color: textoSobre(c) }}
                    className={`flex h-9 w-9 items-center justify-center rounded-xl ring-1 ring-inset ring-black/10 transition duration-150 ease-suave sm:h-8 sm:w-8 sm:rounded-lg ${
                      elegido
                        ? 'scale-110 shadow-md ring-2 ring-slate-900 ring-offset-2 ring-offset-white dark:ring-white dark:ring-offset-slate-900'
                        : 'hover:scale-110 active:scale-95'
                    }`}
                  >
                    {elegido && <Check className="h-4 w-4 animate-tilde" strokeWidth={3} />}
                  </button>
                )
              })}
            </div>
          </fieldset>

          {/* Así queda: la barra como se va a ver en el calendario */}
          <div>
            <span className="etiqueta-campo">Así se va a ver</span>
            <div className="rounded-xl bg-slate-50 p-2.5 dark:bg-slate-800/50">
              <div
                className="truncate rounded-lg px-2.5 text-[13px] font-semibold leading-8 shadow-sm ring-1 ring-inset ring-black/[.06] transition-colors duration-200"
                style={{ backgroundColor: color, color: textoSobre(color) }}
              >
                {nombre.trim() || (esAlta ? 'El nombre va acá' : 'Sin nombre')}
              </div>
            </div>
          </div>
        </div>

        {confirmandoBorrar && edicion.barra ? (
          <ConfirmarBorrado
            barra={edicion.barra}
            onSi={() => { setConfirmandoEn(null); borrar() }}
            onNo={() => setConfirmandoEn(null)}
          />
        ) : (
        <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-800 dark:bg-slate-800/40">
          {!esAlta ? (
            <button
              type="button"
              onClick={() => setConfirmandoEn(edicion)}
              className="flex min-h-[44px] items-center gap-1.5 rounded-xl px-3 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 active:scale-95 dark:text-rose-400 dark:hover:bg-rose-500/10 sm:min-h-[40px]"
            >
              <Trash2 className="h-4 w-4" /> Eliminar
            </button>
          ) : <span />}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={cerrar}
              className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 active:scale-95 dark:text-slate-300 dark:hover:bg-slate-700 sm:min-h-[40px]"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={!valido}
              className="min-h-[44px] rounded-xl bg-brand-600 px-5 text-sm font-semibold text-white shadow-sm shadow-brand-600/25 transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
            >
              {esAlta ? 'Crear' : 'Guardar'}
            </button>
          </div>
        </footer>
        )}
      </form>
    </div>
  )
}

/** "¿Seguro?" antes de eliminar, diciendo qué se va con la acción. */
function ConfirmarBorrado({ barra, onSi, onNo }: { barra: BarraGuardada; onSi: () => void; onNo: () => void }) {
  const cosas = [
    [barra.tareas?.length ?? 0, 'tarea', 'tareas'],
    [barra.piezas?.length ?? 0, 'pieza', 'piezas'],
    [barra.avisos?.length ?? 0, 'aviso', 'avisos'],
  ] as const
  const lista = cosas.filter(([n]) => n > 0).map(([n, una, varias]) => `${n} ${n === 1 ? una : varias}`)
  const queSeVa = lista.length === 0
    ? ''
    : ` Se ${lista.length === 1 && cosas.find(([n]) => n > 0)?.[0] === 1 ? 'va' : 'van'} con ella ${
      lista.length === 1 ? lista[0] : `${lista.slice(0, -1).join(', ')} y ${lista[lista.length - 1]}`}.`
  return (
    <footer
      role="alertdialog"
      aria-labelledby="confirmar-borrado"
      className="shrink-0 animate-fade-in space-y-3 border-t border-rose-200 bg-rose-50 px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] dark:border-rose-500/30 dark:bg-rose-500/10"
    >
      <p id="confirmar-borrado" className="text-sm text-rose-900 dark:text-rose-100">
        ¿Eliminar <strong>{barra.nombre}</strong>?{queSeVa} No se puede deshacer.
      </p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          autoFocus
          onClick={onNo}
          className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-700 transition hover:bg-white/70 active:scale-95 dark:text-slate-200 dark:hover:bg-slate-800 sm:min-h-[40px]"
        >
          No, dejarla
        </button>
        <button
          type="button"
          onClick={onSi}
          className="flex min-h-[44px] items-center gap-1.5 rounded-xl bg-rose-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 active:scale-[.98] sm:min-h-[40px]"
        >
          <Trash2 className="h-4 w-4" /> Sí, eliminar
        </button>
      </div>
    </footer>
  )
}
