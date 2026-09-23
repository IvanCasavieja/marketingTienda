'use client'

import { ShoppingBag } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, useAnchoTotal, ANCHO_ETIQUETA } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { diaDeHoy } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import { REGLAS_HEADER, type Banda } from '@/lib/calendario/tipos'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

export function CalendarioRetail() {
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const ancho = useAnchoTotal(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable } = usePermisosCalendario()

  // Agrupar bandas por eComm / Express conservando el orden del Excel
  const grupos: { nombre: string; bandas: Banda[] }[] = []
  for (const b of mes.retail) {
    const g = b.grupo ?? 'eComm'
    if (!grupos.length || grupos[grupos.length - 1].nombre !== g) grupos.push({ nombre: g, bandas: [] })
    grupos[grupos.length - 1].bandas.push(b)
  }

  const campanas = mes.retail.reduce((n, b) => n + b.filas.reduce((m, f) => m + f.length, 0), 0)

  return (
    <Seccion
      icono={<ShoppingBag className="h-4 w-4" />}
      titulo="Calendario Retail Media"
      bajada="Los espacios digitales vendidos a marcas. Lo que se venda como HOME SLIDER baja solo al calendario de headers."
      contador={`${campanas} campañas`}
    >
      <MarcoScroll ancho={ancho}>
          <CabeceraDias mes={mes} hoy={hoy} titulo="Formato" />

          {grupos.map(grupo => (
            <div key={grupo.nombre}>
              <div className="flex border-b border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800">
                <div
                  className="sticky left-0 z-20 shrink-0 bg-slate-100 dark:bg-slate-800 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400"
                  style={{ width: ANCHO_ETIQUETA }}
                >
                  {grupo.nombre}
                </div>
                <div className="flex-1 bg-slate-100 dark:bg-slate-800" />
              </div>

              {grupo.bandas.map(banda => {
                const esHeader = banda.nombre === REGLAS_HEADER.formatoHeader
                return (
                  <div key={banda.id} className="flex">
                    <EtiquetaBanda
                      filas={banda.filas.length}
                      tono={esHeader ? 'rm' : 'normal'}
                      extra={esHeader
                        ? <span className="text-[9px] font-medium uppercase tracking-wide text-violet-500 dark:text-violet-400">
                            baja al header
                          </span>
                        : undefined}
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
                          editable={editable}
                          onBarra={b => abrirEditor({ seccion: 'retail', bandaId: banda.id, filaIdx: i, barra: b })}
                          onDiaVacio={d => abrirEditor({ seccion: 'retail', bandaId: banda.id, filaIdx: i, barra: null, diaInicial: d })}
                        />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          ))}

          {mes.retail.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-slate-400 dark:text-slate-500">
              No hay campañas de Retail Media cargadas para este mes.
            </div>
          )}
      </MarcoScroll>
    </Seccion>
  )
}
