'use client'

import { useState } from 'react'
import { AlertTriangle, LayoutPanelTop, Lock, Settings2 } from 'lucide-react'
import { CabeceraDias, EtiquetaBanda, FilaRejilla, useAnchoTotal, useFranjaDias, ANCHO_ETIQUETA } from './Rejilla'
import { MarcoScroll } from './MarcoScroll'
import { Seccion } from './Seccion'
import { diaDeHoy, esFinde } from '@/lib/calendario/fechas'
import { ocupacionHeader, useCalendario, type OcupacionDia } from '@/lib/calendario/store'
import { REGLAS_HEADER } from '@/lib/calendario/tipos'
import { usePermisosCalendario } from '@/lib/calendario/permisos'

const TONO_ESTADO: Record<OcupacionDia['estado'], string> = {
  ok: 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200',
  tolerable: 'bg-amber-200 dark:bg-amber-800/70 text-amber-900 dark:text-amber-100',
  excedido: 'bg-rose-500 text-white',
}

export function HeaderHome() {
  const mes = useCalendario(s => s.meses[s.mesActivo])
  const abrirEditor = useCalendario(s => s.abrirEditor)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const moverPosicionesRM = useCalendario(s => s.moverPosicionesRM)
  const [panelAbierto, setPanelAbierto] = useState(false)

  /** Un banner derivado de una acción lleva a la ficha de esa acción. */
  function irAAccion(accionId: string) {
    for (const banda of mes.comercial) {
      for (let i = 0; i < banda.filas.length; i++) {
        if (banda.filas[i].some(b => b.id === accionId)) {
          abrirAccion({ bandaId: banda.id, filaIdx: i, barraId: accionId })
          return
        }
      }
    }
  }

  const ancho = useAnchoTotal(mes.dias)
  const franjaPie = useFranjaDias(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const { editable, moverRM: puedeMover, autor } = usePermisosCalendario()
  const ocupacion = ocupacionHeader(mes)
  const pico = Math.max(...ocupacion.map(o => o.cantidad), 0)

  const esRM = (pos: number) => mes.posicionesRM.includes(pos)

  function cambiarPosicion(indice: number, valor: number) {
    const siguiente = [...mes.posicionesRM]
    const yaEstaEn = siguiente.indexOf(valor)
    if (yaEstaEn !== -1) siguiente[yaEstaEn] = siguiente[indice]  // intercambio, nunca duplica
    siguiente[indice] = valor
    moverPosicionesRM(siguiente, autor)
  }

  return (
    <Seccion
      icono={<LayoutPanelTop className="h-4 w-4" />}
      titulo="Headers de la home"
      bajada={`Las ${REGLAS_HEADER.tope} posiciones del header. Retail Media ocupa ${mes.posicionesRM.join(', ')} y baja sola desde su calendario.`}
      contador={`pico ${pico} de ${REGLAS_HEADER.tope}`}
      acciones={
        <button
          type="button"
          onClick={() => setPanelAbierto(v => !v)}
          disabled={!puedeMover}
          title={puedeMover ? 'Mover las posiciones de Retail Media' : 'Solo Superadmin y Admin pueden mover las posiciones de Retail Media'}
          className="flex items-center gap-1.5 rounded-lg bg-white dark:bg-slate-900 px-2.5 py-1.5 text-[11px] font-medium text-slate-600 dark:text-slate-400 ring-1 ring-slate-200 dark:ring-slate-700 transition hover:bg-slate-50 dark:hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {puedeMover ? <Settings2 className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
          Posiciones de Retail Media
        </button>
      }
    >
      {panelAbierto && puedeMover && (
        <div className="flex flex-wrap items-center gap-3 border-b border-violet-200 dark:border-violet-900 bg-violet-50 dark:bg-violet-950/40 px-4 py-3">
          <span className="text-xs font-medium text-violet-900 dark:text-violet-200">Retail Media ocupa las posiciones:</span>
          {mes.posicionesRM.map((pos, i) => (
            <select
              key={i}
              value={pos}
              onChange={e => cambiarPosicion(i, Number(e.target.value))}
              className="rounded-md border border-violet-300 dark:border-violet-700 bg-white dark:bg-slate-900 px-2 py-1 text-xs font-semibold text-violet-900 dark:text-violet-200"
            >
              {Array.from({ length: REGLAS_HEADER.tope }, (_, n) => n + 1).map(n => (
                <option key={n} value={n}>Posición {n}</option>
              ))}
            </select>
          ))}
          <span className="text-[11px] text-violet-700 dark:text-violet-300">
            Al cambiarlas se le notifica a Macarena, que es quien lleva Retail Media.
          </span>
        </div>
      )}

      {mes.sinLugar.length > 0 && (
        <div className="border-b border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 px-4 py-2.5">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-rose-800 dark:text-rose-200">
            <AlertTriangle className="h-3.5 w-3.5" />
            {mes.sinLugar.length === 1
              ? 'Una acción pide header y no entra'
              : `${mes.sinLugar.length} acciones piden header y no entran`}
          </p>
          <ul className="mt-1 space-y-0.5">
            {mes.sinLugar.map(s => (
              <li key={s.accionId} className="text-[11px] text-rose-700 dark:text-rose-300">
                <button onClick={() => irAAccion(s.accionId)} className="font-medium underline underline-offset-2">
                  {s.nombre}
                </button>
                {' '}· del {s.desde} al {s.hasta}
                {s.diasLlenos.length > 0 && ` · header completo los días ${s.diasLlenos.join(', ')}`}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10px] text-rose-600 dark:text-rose-400">
            El sistema avisa, no decide: qué se baja se resuelve por venta.
          </p>
        </div>
      )}

      <MarcoScroll ancho={ancho}>
          <CabeceraDias mes={mes} hoy={hoy} titulo="Posición" />

          {mes.header.map((pos, idx) => {
            const numero = idx + 1
            const rm = esRM(numero)
            return (
              <div key={pos.id} className="flex">
                <EtiquetaBanda
                  tono={rm ? 'rm' : 'normal'}
                  extra={
                    <span className={`text-[9px] font-medium uppercase tracking-wide ${rm ? 'text-violet-500 dark:text-violet-400' : 'text-slate-400 dark:text-slate-500'}`}>
                      {rm ? 'Retail Media' : 'Marketing'}
                    </span>
                  }
                >
                  {pos.nombre}
                </EtiquetaBanda>
                <div className="flex-1">
                  <FilaRejilla
                    mes={mes}
                    fila={pos.filas[0]}
                    hoy={hoy}
                    editable={editable && !rm}
                    esDerivada={b => b.origen?.tipo === 'retail' || b.origen?.tipo === 'accion'}
                    onBarra={b => {
                      // Las derivadas mandan a su origen; las manuales se editan acá
                      if (b.origen?.tipo === 'accion') return irAAccion(b.origen.accionId)
                      if (b.origen?.tipo === 'retail') return
                      abrirEditor({ seccion: 'header', bandaId: pos.id, filaIdx: 0, barra: b })
                    }}
                    onDiaVacio={editable && !rm
                      ? d => abrirEditor({ seccion: 'header', bandaId: pos.id, filaIdx: 0, barra: null, diaInicial: d })
                      : undefined}
                  />
                </div>
              </div>
            )
          })}

          {/* Contador día por día: cuenta y avisa, no decide qué bajar */}
          <div className="flex border-t-2 border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/40">
            <div
              className="sticky left-0 z-20 shrink-0 border-r border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/40 px-3 py-2"
              style={{ width: ANCHO_ETIQUETA }}
            >
              <div className="text-[11px] font-bold text-slate-700 dark:text-slate-300">Banners ese día</div>
              <div className="text-[9px] text-slate-500 dark:text-slate-400">
                ideal {REGLAS_HEADER.ideal} · tolerable {REGLAS_HEADER.tolerable} · tope {REGLAS_HEADER.tope}
              </div>
            </div>
            <div className="grid shrink-0" style={franjaPie}>
              {ocupacion.map(o => (
                <div
                  key={o.dia}
                  style={{ gridColumn: o.dia, gridRow: 1 }}
                  title={`Día ${o.dia}: ${o.cantidad} banners en el header`}
                  className={[
                    'flex items-center justify-center border-r border-white/60 py-2 text-xs font-bold',
                    TONO_ESTADO[o.estado],
                    esFinde(mes.clave, o.dia) && o.estado === 'ok' ? 'bg-emerald-50' : '',
                  ].join(' ')}
                >
                  {o.cantidad}
                </div>
              ))}
            </div>
          </div>
      </MarcoScroll>

      <footer className="flex flex-wrap items-center gap-4 border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2.5 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-emerald-100 dark:bg-emerald-900/50 ring-1 ring-emerald-300" />
          hasta {REGLAS_HEADER.ideal}, ideal
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-amber-200 dark:bg-amber-800/70 ring-1 ring-amber-400" />
          {REGLAS_HEADER.tolerable}, tolerable
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-rose-500" />
          más de {REGLAS_HEADER.tolerable}, se pasa
        </span>
        <span className="flex items-center gap-1.5 border-l border-slate-200 dark:border-slate-700 pl-4">
          <span className="h-3 w-3 rounded-sm border-l-[3px] border-l-slate-900/40 bg-slate-200 dark:bg-slate-700" />
          derivado · se edita en su origen
        </span>
      </footer>
    </Seccion>
  )
}
