'use client'

import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { toast } from 'sonner'
import { calendarioApi } from '@/lib/api'
import { delEquipo, type Persona } from '@/lib/calendario/tipos'
import type { DetalleEntregas } from '@/lib/calendario/entregas'
import { esFechaGuardable } from '../CampoFecha'

function detalleDeError(e: unknown): string | null {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : null
}

/**
 * El nombre, el vencimiento y el responsable de Tienda de una tarjeta sin
 * acción (24/11/2026). Las de una acción se cambian en su ficha del
 * calendario; estas no tienen acción, así que se cambian acá, en la tarjeta.
 * Lo pedido (el detalle) y los archivos se cambian como en cualquier tarjeta:
 * "Cambiar el pedido…" y «Lo que se pidió».
 *
 * Lo ve quien gestiona tareas (`calendario.tareas`), lo mismo que exige el
 * servidor para cambiar una tarea (PATCH /calendario/tareas/{id}).
 */
export function EditarTarjetaSinAccion({ detalle, onListo }: { detalle: DetalleEntregas; onListo: () => void }) {
  const t = detalle.tarea
  const deAgencia = t.quienLaHace?.tipo === 'agencia' || t.quienLaHace?.tipo === 'fuera'
  const [abierto, setAbierto] = useState(false)
  const [titulo, setTitulo] = useState(t.titulo)
  const [vence, setVence] = useState(t.vence ?? '')
  const [responsable, setResponsable] = useState(t.responsable != null ? String(t.responsable) : '')
  const [personas, setPersonas] = useState<Persona[] | null>(null)
  const [guardando, setGuardando] = useState(false)

  function abrir() {
    // Desde lo que está guardado ahora, no desde lo que se escribió la vez anterior.
    setTitulo(t.titulo)
    setVence(t.vence ?? '')
    setResponsable(t.responsable != null ? String(t.responsable) : '')
    setAbierto(true)
    if (deAgencia && personas === null) {
      calendarioApi.personas(detalle.accion.mundo)
        .then(({ data }) => setPersonas(data))
        .catch(() => setPersonas([]))
    }
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    if (!titulo.trim() || guardando) return
    const cambios: Record<string, unknown> = {}
    if (titulo.trim() !== t.titulo) cambios.titulo = titulo.trim()
    const v = esFechaGuardable(vence) ? vence : null
    if (v !== (t.vence ?? null)) cambios.vence = v
    if (deAgencia) {
      const r = responsable ? Number(responsable) : null
      if (r !== (t.responsable ?? null)) cambios.responsable = r
    }
    if (Object.keys(cambios).length === 0) {
      setAbierto(false)
      return
    }
    setGuardando(true)
    try {
      await calendarioApi.cambiarTarea(t.id, cambios)
      toast.success('Listo: se guardaron los cambios de la tarjeta.')
      setAbierto(false)
      onListo()
    } catch (err) {
      toast.error(detalleDeError(err) ?? 'No se pudieron guardar los cambios. Probá de nuevo.')
    } finally {
      setGuardando(false)
    }
  }

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={abrir}
        className="flex min-h-[44px] items-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        <Pencil className="h-4 w-4" /> Cambiar el nombre, la fecha o el responsable
      </button>
    )
  }

  return (
    <form
      onSubmit={guardar}
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setAbierto(false) } }}
      className="space-y-3 rounded-2xl border border-slate-300 p-3.5 dark:border-slate-700"
      aria-label="Cambiar la tarjeta"
    >
      <p className="text-sm font-bold text-slate-900 dark:text-slate-100">La tarjeta (sin acción)</p>
      <label className="block">
        <span className="etiqueta-campo">Nombre</span>
        <input value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={500} className="campo" autoFocus />
      </label>
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
              {delEquipo(personas ?? []).map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
            </select>
          </label>
        )}
        <label className="block">
          <span className="etiqueta-campo">Vence el (opcional)</span>
          <input type="date" min="2000-01-01" max="2100-12-31" value={vence} onChange={e => setVence(e.target.value)} className="campo" />
        </label>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button type="button" onClick={() => setAbierto(false)} className="min-h-[44px] rounded-xl px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800 sm:min-h-[40px]">
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
