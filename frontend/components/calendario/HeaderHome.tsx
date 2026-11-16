'use client'

import { useState } from 'react'
import { AlertTriangle, CalendarSearch, LayoutPanelTop } from 'lucide-react'
import { PanelHeaders } from './PanelHeaders'
import { Seccion } from './Seccion'
import { MarcoScroll } from './MarcoScroll'
import { CabeceraDias, useAnchoTotal, useFranjaDias, ESTILO_ETIQUETA } from './Rejilla'
import { diaDeHoy, esFinde, fechaCorta, rangoLargo } from '@/lib/calendario/fechas'
import { ocupacionHeader, useCalendario, useMesActivo, type OcupacionDia } from '@/lib/calendario/store'
import { REGLAS_HEADER } from '@/lib/calendario/tipos'

const TONO_ESTADO: Record<OcupacionDia['estado'], string> = {
  ok: 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200',
  tolerable: 'bg-amber-200 dark:bg-amber-800/70 text-amber-900 dark:text-amber-100',
  excedido: 'bg-rose-500 text-white',
}

/**
 * El header de la home, resumido.
 *
 * Era una rejilla de 10 posiciones por 31 días: para saber qué se ve un día
 * había que leer una columna entre treinta, y ocupaba un tercio de la pantalla.
 * Acá queda lo que sí se mira de corrido --el conteo día por día, que es la
 * alarma, y lo que no entró-- y el detalle pasa al panel que se abre por fecha.
 */
export function HeaderHome() {
  const mes = useMesActivo()
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const [panelAbierto, setPanelAbierto] = useState(false)
  const [diaDelPanel, setDiaDelPanel] = useState<number | null>(null)

  const ancho = useAnchoTotal(mes.dias)
  const franjaPie = useFranjaDias(mes.dias)
  const hoy = diaDeHoy(mes.clave)
  const ocupacion = ocupacionHeader(mes)
  const pico = Math.max(...ocupacion.map(o => o.cantidad), 0)

  const irAAccion = (accionId: string) => abrirAccion(accionId)

  return (
    <>
      <Seccion
        icono={<LayoutPanelTop className="h-4 w-4" />}
        titulo="Headers de la home"
        bajada={`Las ${REGLAS_HEADER.tope} posiciones. Retail Media ocupa ${mes.posicionesRM.join(', ')} y baja sola desde su calendario.`}
        contador={`pico ${pico} de ${REGLAS_HEADER.tope}`}
        acciones={
          <button
            type="button"
            onClick={() => { setDiaDelPanel(null); setPanelAbierto(true) }}
            className="flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-3.5 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-700 active:scale-[.98] dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200 sm:min-h-[40px] sm:w-auto"
          >
            <CalendarSearch className="h-4 w-4" />
            Ver headers activos por fecha
          </button>
        }
      >
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
                  {' '}· {rangoLargo(s.inicio, s.fin)}
                  {s.diasLlenos.length > 0 && ` · header completo los días ${s.diasLlenos.map(fechaCorta).join(', ')}`}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[10px] text-rose-600 dark:text-rose-400">
              El sistema avisa, no decide: qué se baja se resuelve por venta.
            </p>
          </div>
        )}

        {/* El conteo día por día: es la alarma, y por eso queda a la vista.
            Arriba, los días: sin ellos había que contar columnas. */}
        <MarcoScroll ancho={ancho}>
          <CabeceraDias mes={mes} hoy={hoy} titulo="Día" />
          <div className="flex bg-slate-50 dark:bg-slate-800/40">
            <div
              className="sticky left-0 z-20 shrink-0 border-r border-slate-300 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-[#151e31]"
              style={{ width: ESTILO_ETIQUETA }}
            >
              <div className="text-[11px] font-bold text-slate-700 dark:text-slate-300">Banners ese día</div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                ideal {REGLAS_HEADER.ideal} · tolerable {REGLAS_HEADER.tolerable} · tope {REGLAS_HEADER.tope}
              </div>
            </div>
            <div className="grid shrink-0" style={franjaPie}>
              {ocupacion.map(o => (
                <button
                  key={o.dia}
                  type="button"
                  onClick={() => { setDiaDelPanel(o.dia); setPanelAbierto(true) }}
                  style={{ gridColumn: o.dia, gridRow: 1 }}
                  title={`Día ${o.dia}: ${o.cantidad} banners en el header. Tocá para ver cuáles.`}
                  className={[
                    'flex items-center justify-center border-r border-white/60 py-2.5 text-xs font-bold tabular-nums transition hover:brightness-95 focus-visible:z-10 dark:border-slate-900/60',
                    TONO_ESTADO[o.estado],
                    esFinde(mes.clave, o.dia) && o.estado === 'ok' ? 'bg-emerald-50 dark:bg-emerald-900/30' : '',
                    o.dia === hoy ? 'ring-2 ring-inset ring-brand-500' : '',
                  ].join(' ')}
                >
                  {o.cantidad}
                </button>
              ))}
            </div>
          </div>
        </MarcoScroll>

        <footer className="flex flex-wrap items-center gap-4 border-t border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2.5 text-[11px] text-slate-500 dark:text-slate-400">
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
          <span className="border-l border-slate-300 dark:border-slate-700 pl-4">
            Tocá un día para ver qué hay puesto.
          </span>
        </footer>
      </Seccion>

      <PanelHeaders abierto={panelAbierto} diaInicial={diaDelPanel} onCerrar={() => setPanelAbierto(false)} />
    </>
  )
}
