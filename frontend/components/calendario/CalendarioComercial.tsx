'use client'

import { useState } from 'react'
import { CalendarDays, Eye, EyeOff } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, useAnchoTotal } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { diaDeHoy, isoDe } from '@/lib/calendario/fechas'
import { useCalendario, useMesActivo } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

export function CalendarioComercial() {
  const mes = useMesActivo()
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable } = usePermisosCalendario()
  const barras = useCalendario(s => s.barras)

  /** "2/5": cuántas tareas de la acción están hechas. Sin tareas, nada. */
  const tareasDe = (id: string) => {
    const tareas = barras[id]?.tareas ?? []
    if (tareas.length === 0) return null
    return `${tareas.filter(t => t.estado === 'hecha').length}/${tareas.length}`
  }

  // Trece tipos de acción para diez acciones: la mayoría de los renglones
  // están vacíos y hay que recorrerlos para encontrar algo. Se pueden esconder
  // los que no tienen nada este mes; para cargar en uno vacío se vuelven a ver.
  const [soloConAcciones, setSoloConAcciones] = useState(false)
  const bandas = soloConAcciones
    ? mes.comercial.filter(b => b.filas.some(f => f.length > 0))
    : mes.comercial
  const vacias = mes.comercial.length - mes.comercial.filter(b => b.filas.some(f => f.length > 0)).length

  const acciones = mes.comercial.reduce((n, b) => n + b.filas.reduce((m, f) => m + f.length, 0), 0)

  return (
    <Seccion
      icono={<CalendarDays className="h-4 w-4" />}
      titulo="Calendario comercial"
      bajada="Las acciones por tipo. Tocá una acción para ver sus tareas, sus piezas y sus avisos."
      contador={`${acciones} acciones`}
      acciones={vacias > 0 ? (
        <button
          type="button"
          onClick={() => setSoloConAcciones(v => !v)}
          aria-pressed={soloConAcciones}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          {soloConAcciones ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          {soloConAcciones ? `Ver los ${vacias} tipos vacíos` : 'Ocultar tipos vacíos'}
        </button>
      ) : undefined}
    >
      <MarcoScroll ancho={ancho}>
          <CabeceraDias mes={mes} hoy={hoy} titulo="Tipo de acción" />

          {bandas.map(banda => (
            <div key={banda.id} className="flex">
              <EtiquetaBanda
                filas={banda.filas.length}
                onAgregar={editable
                  ? () => abrirEditor({ seccion: 'comercial', banda: banda.id, carril: 0, barra: null, fechaInicial: isoDe(mes.clave, hoy ?? 1) })
                  : undefined}
                tituloAgregar={`Nueva acción en ${banda.nombre}`}
              >
                {banda.nombre}
              </EtiquetaBanda>
              <div className="flex-1">
                {banda.filas.map((fila, i) => (
                  <FilaRejilla
                    key={i}
                    mes={mes}
                    fila={fila}
                    hoy={hoy}
                    editable
                    onBarra={b => abrirAccion(b.id)}
                    detalleDe={b => tareasDe(b.id)}
                    onDiaVacio={editable
                      ? d => abrirEditor({ seccion: 'comercial', banda: banda.id, carril: i, barra: null, fechaInicial: isoDe(mes.clave, d) })
                      : undefined}
                  />
                ))}
              </div>
            </div>
          ))}
      </MarcoScroll>
    </Seccion>
  )
}
