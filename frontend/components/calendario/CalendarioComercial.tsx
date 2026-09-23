'use client'

import { CalendarDays } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, useAnchoTotal } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { diaDeHoy } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

export function CalendarioComercial() {
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable } = usePermisosCalendario()

  const acciones = mes.comercial.reduce((n, b) => n + b.filas.reduce((m, f) => m + f.length, 0), 0)

  return (
    <Seccion
      icono={<CalendarDays className="h-4 w-4" />}
      titulo="Calendario comercial"
      bajada="Las acciones de marketing por tipo, tal cual el Excel. Tocá una acción para ver su estructura."
      contador={`${acciones} acciones`}
    >
      <MarcoScroll ancho={ancho}>
          <CabeceraDias mes={mes} hoy={hoy} titulo="Tipo de acción" />

          {mes.comercial.map(banda => (
            <div key={banda.id} className="flex">
              <EtiquetaBanda filas={banda.filas.length}>{banda.nombre}</EtiquetaBanda>
              <div className="flex-1">
                {banda.filas.map((fila, i) => (
                  <FilaRejilla
                    key={i}
                    mes={mes}
                    fila={fila}
                    hoy={hoy}
                    editable
                    onBarra={b => abrirAccion({ bandaId: banda.id, filaIdx: i, barraId: b.id })}
                    onDiaVacio={editable
                      ? d => abrirEditor({ seccion: 'comercial', bandaId: banda.id, filaIdx: i, barra: null, diaInicial: d })
                      : undefined}
                  />
                ))}
              </div>
            </div>
          ))}

          {mes.comercial.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-slate-400 dark:text-slate-500">
              No hay datos comerciales cargados para este mes.
            </div>
          )}
      </MarcoScroll>
    </Seccion>
  )
}
