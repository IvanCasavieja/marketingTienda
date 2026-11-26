'use client'

import { useEffect, useId, useState } from 'react'
import { Pencil } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { calendarioApi } from '@/lib/api'
import { delEquipo, type Persona } from '@/lib/calendario/tipos'
import type { DetalleEntregas } from '@/lib/calendario/entregas'
import { cambioDeQuien, quienDeLaTarjeta } from '@/lib/calendario/tablero'
import { useVistaEntregas } from '@/store/entregas'
import { useTableros } from '@/store/tiposDeTarea'
import { esFechaGuardable } from '../CampoFecha'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/**
 * Quién la hace, el nombre, el vencimiento y el responsable de Tienda de una
 * tarjeta sin acción (24/11/2026). Las de una acción se cambian en su ficha
 * del calendario; estas no tienen acción, así que se cambian acá, en la
 * tarjeta. Lo pedido (el detalle) y los archivos se cambian como en cualquier
 * tarjeta: "Cambiar el pedido…" y «Lo que se pidió».
 *
 * «¿Quién la hace?» (26/11/2026, H-018 del cuaderno): una tarjeta pedida para
 * Publicis no se podía pasar a la agencia de verdad, que nunca recibía el
 * pedido. Ofrece lo mismo que al crearla: todas las agencias (GET
 * /calendario/tableros) y la gente de Tienda.
 *
 * Lo ve quien gestiona tareas (`calendario.tareas`), lo mismo que exige el
 * servidor para cambiar una tarea (PATCH /calendario/tareas/{id}).
 */
export function EditarTarjetaSinAccion({ detalle, onListo }: { detalle: DetalleEntregas; onListo: () => void }) {
  const { t } = useTranslation()
  const [abierto, setAbierto] = useState(false)

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="flex min-h-[44px] items-center gap-2 rounded-xl px-3 text-left text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        <Pencil className="h-4 w-4 shrink-0" aria-hidden /> {t('calendario.tarjetaSinAccion.cambiar')}
      </button>
    )
  }
  // Se arma de nuevo cada vez que se abre: arranca de lo que está guardado
  // ahora, no de lo que se escribió la vez anterior.
  return <FormularioDeLaTarjeta detalle={detalle} onCerrar={() => setAbierto(false)} onListo={onListo} />
}

function FormularioDeLaTarjeta({ detalle, onCerrar, onListo }: {
  detalle: DetalleEntregas
  onCerrar: () => void
  onListo: () => void
}) {
  const { t } = useTranslation()
  const tarea = detalle.tarea
  const mundo = detalle.accion.mundo
  const huboCambios = useVistaEntregas(s => s.huboCambios)
  const { tableros } = useTableros(mundo)
  const [personas, setPersonas] = useState<Persona[] | null>(null)
  const [titulo, setTitulo] = useState(tarea.titulo)
  const [vence, setVence] = useState(tarea.vence ?? '')
  const [responsable, setResponsable] = useState(tarea.responsable != null ? String(tarea.responsable) : '')
  // Quién la hace: lo que se eligió acá; si no se tocó, lo que tiene guardado.
  const [elegido, setElegido] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const idDelAviso = useId()

  useEffect(() => {
    let vivo = true
    calendarioApi.personas(mundo)
      .then(({ data }) => { if (vivo) setPersonas(data) })
      .catch(() => { if (vivo) setPersonas([]) })
    return () => { vivo = false }
  }, [mundo])

  const agencias = tableros?.map(a => a.nombre) ?? []
  const equipo = delEquipo(personas ?? [])
  const guardado = quienDeLaTarjeta(tarea.quienLaHace, tarea.asignadoA, agencias)
  const quien = elegido ?? guardado
  const cambio = cambioDeQuien(guardado, quien)
  const agenciaGuardada = guardado.startsWith('agencia:') ? guardado.slice('agencia:'.length) : null
  const personaGuardada = guardado.startsWith('persona:') ? Number(guardado.slice('persona:'.length)) : null
  // El responsable de Tienda va solo si la hace una agencia (0090).
  const deAgencia = quien.startsWith('agencia:') || quien === 'fuera'
  const cargando = tableros === null || personas === null

  function nombreDe(id: number): string {
    return equipo.find(p => p.id === id)?.nombre ?? detalle.personas[String(id)] ?? ''
  }

  let avisoDelCambio: string | null = null
  if (cambio && 'agencia' in cambio) {
    // Una agencia sin cuentas todavía (uno de los tres tableros) no tiene a quién avisarle.
    const sinUsuarios = tableros?.find(a => a.nombre === cambio.agencia)?.cuentas === 0
    avisoDelCambio = sinUsuarios
      ? t('calendario.quienLaHace.pasaALaAgenciaSinUsuarios', { agencia: cambio.agencia })
      : t('calendario.quienLaHace.pasaALaAgencia', { agencia: cambio.agencia })
  } else if (cambio) {
    const persona = nombreDe(cambio.asignadoA)
    avisoDelCambio = agenciaGuardada
      ? t('calendario.quienLaHace.dejaLaAgencia', { agencia: agenciaGuardada, persona })
      : t('calendario.quienLaHace.pasaAPersona', { persona })
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    if (!titulo.trim() || guardando) return
    const cambios: Record<string, unknown> = { ...(cambio ?? {}) }
    if (titulo.trim() !== tarea.titulo) cambios.titulo = titulo.trim()
    const v = esFechaGuardable(vence) ? vence : null
    if (v !== (tarea.vence ?? null)) cambios.vence = v
    if (deAgencia) {
      const r = responsable ? Number(responsable) : null
      if (r !== (tarea.responsable ?? null)) cambios.responsable = r
    }
    if (Object.keys(cambios).length === 0) {
      onCerrar()
      return
    }
    setGuardando(true)
    try {
      await calendarioApi.cambiarTarea(tarea.id, cambios)
      toast.success('Listo: se guardaron los cambios de la tarjeta.')
      onCerrar()
      onListo()
      // Si cambió quién la hace, en el tablero pasa a otra pestaña: que se vea ya.
      huboCambios()
    } catch (err) {
      toast.error(detalleDeError(err) ?? 'No se pudieron guardar los cambios. Probá de nuevo.')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <form
      onSubmit={guardar}
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onCerrar() } }}
      className="space-y-3 rounded-2xl border border-slate-300 p-3.5 dark:border-slate-700"
      aria-label="Cambiar la tarjeta"
    >
      <p className="text-sm font-bold text-slate-900 dark:text-slate-100">La tarjeta (sin acción)</p>
      <label className="block">
        <span className="etiqueta-campo">Nombre</span>
        <input value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={500} className="campo" autoFocus />
      </label>
      <div>
        <label className="block">
          <span className="etiqueta-campo">{t('calendario.quienLaHace.titulo')}</span>
          <select
            value={quien}
            onChange={e => setElegido(e.target.value)}
            className="campo"
            disabled={cargando}
            aria-describedby={avisoDelCambio ? idDelAviso : undefined}
          >
            {cargando ? (
              <option value={quien}>{t('calendario.quienLaHace.cargando')}</option>
            ) : (
              <>
                {quien === '' && <option value="">{t('calendario.quienLaHace.elegir')}</option>}
                {guardado === 'fuera' && (
                  <option value="fuera">{t('calendario.quienLaHace.deAfuera', { agencia: tarea.quienLaHace?.nombre ?? '' })}</option>
                )}
                <optgroup label={t('calendario.quienLaHace.agencias')}>
                  {/* La que la tiene hoy aunque ya no esté en la lista (se quedó sin cuentas): para no perderla. */}
                  {agenciaGuardada && !agencias.includes(agenciaGuardada) && <option value={guardado}>{agenciaGuardada}</option>}
                  {(tableros ?? []).map(a => (
                    <option key={a.nombre} value={`agencia:${a.nombre}`}>
                      {a.cuentas === 0 ? t('calendario.quienLaHace.sinUsuarios', { agencia: a.nombre }) : a.nombre}
                    </option>
                  ))}
                </optgroup>
                <optgroup label={t('calendario.quienLaHace.tienda')}>
                  {personaGuardada != null && !equipo.some(p => p.id === personaGuardada) && (
                    <option value={guardado}>{nombreDe(personaGuardada) || t('calendario.quienLaHace.quienLaHaceHoy')}</option>
                  )}
                  {equipo.map(p => <option key={p.id} value={`persona:${p.id}`}>{p.nombre}</option>)}
                </optgroup>
              </>
            )}
          </select>
        </label>
        {avisoDelCambio && (
          <p id={idDelAviso} role="status" className="mt-1 text-xs text-slate-600 dark:text-slate-400">{avisoDelCambio}</p>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {deAgencia && (
          <label className="block">
            <span className="etiqueta-campo">Responsable de Tienda</span>
            <select value={responsable} onChange={e => setResponsable(e.target.value)} className="campo" disabled={personas === null}>
              <option value="">{personas === null ? 'Cargando…' : 'Sin asignar por ahora'}</option>
              {/* Quien ya está aunque no venga en la lista (para no perderlo). */}
              {personas !== null && responsable && !personas.some(p => String(p.id) === responsable) && (
                <option value={responsable}>{detalle.personas[responsable] ?? 'Quien la lleva hoy'}</option>
              )}
              {equipo.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
            </select>
          </label>
        )}
        <label className="block">
          <span className="etiqueta-campo">Vence el (opcional)</span>
          <input type="date" min="2000-01-01" max="2100-12-31" value={vence} onChange={e => setVence(e.target.value)} className="campo" />
        </label>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button type="button" onClick={onCerrar} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
          Cancelar
        </button>
        <button
          type="submit"
          disabled={!titulo.trim() || guardando}
          className="min-h-[44px] rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 active:scale-[.98] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400 sm:min-h-[40px]"
        >
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </form>
  )
}
