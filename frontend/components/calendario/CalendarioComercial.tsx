'use client'

import { CalendarDays } from 'lucide-react'
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
