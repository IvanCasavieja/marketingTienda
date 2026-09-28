'use client'

import { useEffect, useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { PALETA, colorPorDefecto, textoSobre } from '@/lib/calendario/colores'
import {
  claveDe, diasEntre, mesSiguiente, nombreMes, primerDiaDe, rangoLargo, sumarDias, ultimoDiaDe,
} from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'

const TEXTOS: Record<string, { nueva: string; editar: string; unaSola: string }> = {
  comercial: { nueva: 'Nueva acción', editar: 'Editar acción', unaSola: 'Es una sola acción' },
  retail: { nueva: 'Nueva campaña', editar: 'Editar campaña', unaSola: 'Es una sola campaña' },
  header: { nueva: 'Nuevo banner', editar: 'Editar banner', unaSola: 'Es un solo banner' },
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

  const [nombre, setNombre] = useState('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [color, setColor] = useState<string>(PALETA[0])

  useEffect(() => {
    if (!edicion) return
    if (edicion.barra) {
      setNombre(edicion.barra.nombre)
      setDesde(edicion.barra.desde)
      setHasta(edicion.barra.hasta)
      setColor(edicion.barra.color ?? colorPorDefecto(edicion.barra.nombre))
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
    }
  }, [edicion, mesActivo])

  if (!edicion) return null

  const fechasOk = Boolean(desde) && Boolean(hasta) && hasta >= desde
  const valido = nombre.trim().length > 0 && fechasOk
  const dias = fechasOk ? diasEntre(desde, hasta) + 1 : 0
  const meses = fechasOk ? mesesQueToca(desde, hasta) : []

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
              {esAlta ? textos.nueva : textos.editar}
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {edicion.seccion === 'header' ? `Posición ${edicion.banda.replace('pos-', '')} del header` : edicion.banda}
            </p>
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
              <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Arranca</span>
              <input
                type="date"
                value={desde}
                onChange={e => {
                  const v = e.target.value
                  setDesde(v)
                  // Si el inicio pasa al fin, el fin lo acompaña: nunca queda al revés.
                  if (v && hasta && hasta < v) setHasta(v)
                }}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-300"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Termina</span>
              <input
                type="date"
                value={hasta}
                min={desde || undefined}
                onChange={e => setHasta(e.target.value)}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white px-3 py-2 text-sm outline-none focus:border-slate-900 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-300"
              />
            </label>
          </div>

          <p className="rounded-lg bg-slate-50 dark:bg-slate-800/40 px-3 py-2 text-xs text-slate-600 dark:text-slate-400">
            {fechasOk ? (
              <>
                Va <strong>{rangoLargo(desde, hasta)}</strong> · {dias === 1 ? '1 día' : `${dias} días`}
                {meses.length > 1 && (
                  <span className="mt-1 block">
                    {textos.unaSola}: se ve en {meses.slice(0, -1).join(', ')} y {meses[meses.length - 1]}, y
                    lo que le cambies en un mes cambia en todos.
                  </span>
                )}
              </>
            ) : (
              <span className="text-rose-600 dark:text-rose-400">La fecha de fin no puede ser anterior a la de inicio.</span>
            )}
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
