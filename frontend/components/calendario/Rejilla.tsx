'use client'

import { textoSobre } from '@/lib/calendario/colores'
import { esFinde } from '@/lib/calendario/fechas'
import {
  ANCHO_ETIQUETA, MINIMO_CON_DOW, MINIMO_CON_NUMERO,
  anchoDias, anchoTotal, columnasDe,
} from '@/lib/calendario/rejilla'
import { useCalendario } from '@/lib/calendario/store'
import type { Barra, Mes } from '@/lib/calendario/tipos'

export { ANCHO_ETIQUETA }

/** Ancho total de la rejilla al zoom actual. */
export function useAnchoTotal(dias: number) {
  const zoom = useCalendario(s => s.zoom)
  return anchoTotal(dias, zoom)
}

/**
 * Estilo de la franja de días. El ancho va explícito además de las columnas:
 * sin él, el contenedor flex estiraba la franja y las líneas seguían de largo
 * más allá del último día cuando la rejilla no llegaba a llenar la pantalla.
 */
function useFranja(dias: number) {
  const zoom = useCalendario(s => s.zoom)
  return {
    gridTemplateColumns: columnasDe(dias, zoom),
    width: anchoDias(dias, zoom),
  }
}

// ---------------------------------------------------------------------------
// Cabecera de días — se queda pegada arriba al scrollear
// ---------------------------------------------------------------------------

export function CabeceraDias({ mes, hoy, titulo }: { mes: Mes; hoy: number | null; titulo?: string }) {
  const zoom = useCalendario(s => s.zoom)
  const franja = useFranja(mes.dias)
  const conDow = zoom >= MINIMO_CON_DOW
  const conNumero = zoom >= MINIMO_CON_NUMERO

  return (
    <div className="sticky top-0 z-30 flex border-b border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-900">
      <div
        className="sticky left-0 z-40 flex shrink-0 items-end border-r border-slate-300 bg-white px-3 pb-1.5 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-400"
        style={{ width: ANCHO_ETIQUETA }}
      >
        {titulo}
      </div>
      <div className="grid shrink-0" style={franja}>
        {Array.from({ length: mes.dias }, (_, i) => i + 1).map(d => {
          const finde = esFinde(mes.clave, d)
          const esHoy = d === hoy
          return (
            <div
              key={d}
              style={{ gridColumn: d, gridRow: 1 }}
              title={`${mes.dow[String(d)]} ${d}`}
              className={[
                'overflow-hidden border-r border-slate-200 px-0.5 pb-1 pt-2 text-center dark:border-slate-700',
                finde ? 'bg-slate-100 dark:bg-slate-800' : '',
                esHoy ? 'bg-sky-100 dark:bg-sky-900/40' : '',
              ].join(' ')}
            >
              {conDow && (
                <div className="text-[10px] uppercase leading-none text-slate-400 dark:text-slate-500">
                  {mes.dow[String(d)]}
                </div>
              )}
              <div
                className={[
                  conDow ? 'mt-0.5' : '',
                  'text-xs font-semibold leading-none',
                  esHoy ? 'text-sky-700 dark:text-sky-300'
                    : finde ? 'text-slate-500 dark:text-slate-400'
                      : 'text-slate-700 dark:text-slate-300',
                ].join(' ')}
              >
                {conNumero || d === 1 || d % 5 === 0 ? d : ''}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Una fila: el fondo de días y encima las barras
// ---------------------------------------------------------------------------

type FilaProps = {
  mes: Mes
  fila: Barra[]
  hoy: number | null
  alto?: number
  editable: boolean
  onBarra?: (b: Barra) => void
  onDiaVacio?: (dia: number) => void
  /** Barras que no se editan acá (derivadas de otra sección). */
  esDerivada?: (b: Barra) => boolean
  /** Tooltip propio. Sin esto se arma uno con el nombre y el rango de días,
   *  que en una barra de un solo día (un envío) no dice nada. */
  tituloDe?: (b: Barra) => string
}

export function FilaRejilla({
  mes, fila, hoy, alto = 30, editable, onBarra, onDiaVacio, esDerivada, tituloDe,
}: FilaProps) {
  const franja = useFranja(mes.dias)
  const ocupado = new Set<number>()
  fila.forEach(b => { for (let d = b.desde; d <= b.hasta; d++) ocupado.add(d) })

  return (
    <div
      className="grid shrink-0 border-b border-slate-200 dark:border-slate-700"
      style={{ ...franja, minHeight: alto }}
    >
      {Array.from({ length: mes.dias }, (_, i) => i + 1).map(d => {
        const libre = !ocupado.has(d)
        return (
          <div
            key={d}
            style={{ gridColumn: d, gridRow: 1 }}
            onClick={libre && editable && onDiaVacio ? () => onDiaVacio(d) : undefined}
            className={[
              'border-r border-slate-100 dark:border-slate-800',
              esFinde(mes.clave, d) ? 'bg-slate-50 dark:bg-slate-800/40' : '',
              d === hoy ? 'bg-sky-50 dark:bg-sky-950/40' : '',
              libre && editable && onDiaVacio ? 'cursor-cell hover:bg-emerald-50 dark:hover:bg-emerald-950/40' : '',
            ].join(' ')}
          />
        )
      })}

      {fila.map(b => {
        const derivada = esDerivada?.(b) ?? false
        // Una barra derivada no se edita acá, pero sigue siendo clicable: lleva
        // a donde sí se edita (el calendario de retail o la ficha de la acción).
        const clicable = !!onBarra && (editable || derivada)
        return (
          <button
            key={b.id}
            type="button"
            title={tituloDe
              ? tituloDe(b)
              : `${b.nombre} · ${b.desde} al ${b.hasta}${derivada ? ' · se edita en su origen' : ''}`}
            onClick={clicable ? () => onBarra!(b) : undefined}
            disabled={!clicable}
            style={{
              gridColumn: `${b.desde} / ${b.hasta + 1}`,
              gridRow: 1,
              backgroundColor: b.color ?? '#e2e8f0',
              color: textoSobre(b.color),
            }}
            className={[
              'relative z-10 m-[2px] overflow-hidden truncate rounded px-1.5 text-left text-[11px] font-medium leading-[26px]',
              'ring-1 ring-black/5',
              clicable ? 'cursor-pointer hover:ring-2 hover:ring-slate-900/30' : 'cursor-default',
              derivada ? 'border-l-[3px] border-l-slate-900/40' : '',
            ].join(' ')}
          >
            {b.nombre}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Etiqueta de banda — se queda pegada a la izquierda al scrollear
// ---------------------------------------------------------------------------

export function EtiquetaBanda({
  children, filas = 1, tono = 'normal', extra,
}: {
  children: React.ReactNode
  filas?: number
  tono?: 'normal' | 'rm' | 'grupo'
  extra?: React.ReactNode
}) {
  const fondo =
    tono === 'rm' ? 'bg-violet-50 text-violet-900 dark:bg-violet-950/40 dark:text-violet-200'
      : tono === 'grupo' ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
        : 'bg-white text-slate-700 dark:bg-slate-900 dark:text-slate-300'
  return (
    <div
      className={`sticky left-0 z-20 flex shrink-0 flex-col justify-center gap-0.5 border-b border-r border-slate-200 px-3 py-1 dark:border-slate-700 ${fondo}`}
      style={{ width: ANCHO_ETIQUETA, minHeight: filas * 30 }}
    >
      <div className="text-[11px] font-semibold leading-tight">{children}</div>
      {extra}
    </div>
  )
}

/** La franja de días sola, para el pie contador del header. */
export function useFranjaDias(dias: number) {
  return useFranja(dias)
}
