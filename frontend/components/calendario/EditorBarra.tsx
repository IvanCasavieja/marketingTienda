'use client'

import { useEffect, useMemo, useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { PALETA, colorPorDefecto, textoSobre } from '@/lib/calendario/colores'
import { nombreMes } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'

const TITULO: Record<string, string> = {
  comercial: 'acción',
  retail: 'campaña',
  header: 'banner',
}

export function EditorBarra() {
  const edicion = useCalendario(s => s.edicion)
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const cerrar = useCalendario(s => s.cerrarEditor)
  const guardar = useCalendario(s => s.guardarBarra)
  const borrar = useCalendario(s => s.borrarBarra)

  const esAlta = !edicion?.barra
  const etiqueta = TITULO[edicion?.seccion ?? 'comercial']

  const [nombre, setNombre] = useState('')
  const [desde, setDesde] = useState(1)
  const [duracion, setDuracion] = useState(7)
  const [color, setColor] = useState<string>(PALETA[0])

  useEffect(() => {
    if (!edicion) return
    if (edicion.barra) {
      setNombre(edicion.barra.nombre)
      setDesde(edicion.barra.desde)
      setDuracion(edicion.barra.hasta - edicion.barra.desde + 1)
      setColor(edicion.barra.color ?? colorPorDefecto(edicion.barra.nombre))
    } else {
      const inicio = edicion.diaInicial ?? 1
      setNombre('')
      setDesde(inicio)
      setDuracion(Math.min(7, mes.dias - inicio + 1))
      setColor(PALETA[Math.floor(Math.random() * PALETA.length)])
    }
  }, [edicion, mes.dias])

  const hasta = useMemo(
    () => Math.min(mes.dias, desde + Math.max(1, duracion) - 1),
    [desde, duracion, mes.dias],
  )

  if (!edicion) return null

  const valido = nombre.trim().length > 0

  function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!valido) return
    guardar({ nombre: nombre.trim(), desde, hasta, color })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={cerrar}
    >
      <form
        onSubmit={enviar}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-md overflow-hidden rounded-xl bg-white dark:bg-slate-900 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {esAlta ? `Nueva ${etiqueta}` : `Editar ${etiqueta}`}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">{nombreMes(mes.clave)}</p>
          </div>
          <button type="button" onClick={cerrar} className="rounded-lg p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-600 dark:hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="space-y-4 px-4 py-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Nombre</span>
            <input
              autoFocus
              value={nombre}
              onChange={e => setNombre(e.target.value)}
              placeholder={esAlta ? 'Ej: Fiesta de Italia' : ''}
              className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-300 dark:focus:ring-slate-300"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Arranca el día</span>
              <select
                value={desde}
                onChange={e => setDesde(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-300"
              >
                {Array.from({ length: mes.dias }, (_, i) => i + 1).map(d => (
                  <option key={d} value={d}>{d} · {mes.dow[String(d)]}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Duración (días)</span>
              <input
                type="number"
                min={1}
                max={mes.dias - desde + 1}
                value={duracion}
                onChange={e => setDuracion(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-300"
              />
            </label>
          </div>

          <p className="rounded-lg bg-slate-50 dark:bg-slate-800/40 px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
            Ocupa del <strong>{desde}</strong> al <strong>{hasta}</strong> de {nombreMes(mes.clave)}
            {hasta === mes.dias && desde + duracion - 1 > mes.dias && ' (recortado al fin de mes)'}
          </p>

          <div>
            <span className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-400">Color</span>
            <div className="flex flex-wrap gap-1.5">
              {PALETA.map(c => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  style={{ backgroundColor: c }}
                  className={`h-7 w-7 rounded-md ring-1 ring-black/10 transition ${
                    color === c ? 'ring-2 ring-slate-900 ring-offset-1 dark:ring-slate-100 dark:ring-offset-slate-900' : 'hover:scale-110'
                  }`}
                />
              ))}
            </div>
          </div>

          <div
            className="truncate rounded px-2 py-1.5 text-[11px] font-medium ring-1 ring-black/5"
            style={{ backgroundColor: color, color: textoSobre(color) }}
          >
            {nombre.trim() || 'Así se va a ver en el calendario'}
          </div>

          {edicion.seccion === 'comercial' && !esAlta && (
            <button
              type="button"
              disabled
              title="La ficha con tareas, piezas y estructura web todavía no está construida"
              className="w-full rounded-lg border border-dashed border-slate-300 dark:border-slate-600 px-3 py-2 text-xs text-slate-400 dark:text-slate-500"
            >
              Abrir ficha de la acción · próximamente
            </button>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 px-4 py-3">
          {!esAlta ? (
            <button
              type="button"
              onClick={borrar}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40"
            >
              <Trash2 className="h-3.5 w-3.5" /> Eliminar
            </button>
          ) : <span />}
          <div className="flex gap-2">
            <button type="button" onClick={cerrar} className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={!valido}
              className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {esAlta ? 'Crear' : 'Guardar'}
            </button>
          </div>
        </footer>
      </form>
    </div>
  )
}
