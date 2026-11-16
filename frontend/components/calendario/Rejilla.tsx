'use client'

import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { textoSobre } from '@/lib/calendario/colores'
import { esFinde, nombreMes, rangoLargo } from '@/lib/calendario/fechas'
import {
  ANCHO_ETIQUETA, MINIMO_CON_DOW, MINIMO_CON_NUMERO,
  anchoDias, columnasDe,
} from '@/lib/calendario/rejilla'
import { useCalendario } from '@/lib/calendario/store'
import type { Barra, Mes } from '@/lib/calendario/tipos'
import { CLASE_SEMAFORO, type Semaforo } from '@/lib/calendario/semaforo'

export { ANCHO_ETIQUETA }

/**
 * El ancho de la columna de etiquetas, como lo usa la pantalla: la variable
 * CSS --ancho-etiqueta (232px en la notebook, 136px en el teléfono; ver
 * globals.css). El número de rejilla.ts queda de respaldo.
 */
export const ESTILO_ETIQUETA = `var(--ancho-etiqueta, ${ANCHO_ETIQUETA}px)`

/**
 * Alto de cada renglón. Era 30, con la letra en 11px: en una notebook había
 * que acercarse a la pantalla para leer el nombre de una acción (pedido de
 * Ivan, 12/11/2026: "tarjetas más grandes", pensadas para las notebooks y no
 * para un monitor de 27 pulgadas).
 */
export const ALTO_FILA = 38

/** Ancho total de la rejilla al zoom actual: etiquetas + días. */
export function useAnchoTotal(dias: number): string {
  const zoom = useCalendario(s => s.zoom)
  return `calc(${ESTILO_ETIQUETA} + ${anchoDias(dias, zoom)}px)`
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
        className="sticky left-0 z-40 flex shrink-0 items-end border-r border-slate-300 bg-white px-3 pb-2 pt-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 sm:px-4"
        style={{ width: ESTILO_ETIQUETA }}
        data-etiqueta
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
              title={esHoy ? `Hoy, ${mes.dow[String(d)]} ${d}` : `${mes.dow[String(d)]} ${d}`}
              data-hoy={esHoy || undefined}
              className={[
                'flex flex-col items-center overflow-hidden border-r border-slate-200 px-0.5 pb-1.5 pt-2 dark:border-slate-700',
                finde ? 'bg-slate-100 dark:bg-slate-800/50' : '',
                esHoy ? 'bg-brand-50 dark:bg-brand-500/10' : '',
              ].join(' ')}
            >
              {conDow && (
                <div className={[
                  'text-[10px] font-semibold uppercase leading-none',
                  esHoy ? 'text-brand-600 dark:text-brand-300' : 'text-slate-500 dark:text-slate-400',
                ].join(' ')}>
                  {mes.dow[String(d)]}
                </div>
              )}
              {/* Hoy va en un círculo lleno: es lo primero que se busca */}
              <div
                className={[
                  conDow ? 'mt-1' : '',
                  'flex h-[22px] min-w-[22px] items-center justify-center rounded-full px-0.5 text-[13px] font-semibold leading-none tabular-nums',
                  esHoy ? 'bg-brand-600 text-white shadow-sm shadow-brand-600/40'
                    : finde ? 'text-slate-500 dark:text-slate-400'
                      : 'text-slate-700 dark:text-slate-300',
                ].join(' ')}
              >
                {conNumero || esHoy || d === 1 || d % 5 === 0 ? d : ''}
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
  /** Un dato corto pegado a la derecha de la barra: "2/5" tareas hechas. */
  detalleDe?: (b: Barra) => string | null
  /** El semáforo de la acción (verde, amarillo o rojo), como un puntito antes del nombre. */
  semaforoDe?: (b: Barra) => Semaforo | null
  /** Hay otra fila de la misma categoría abajo: el borde va fino y suave; el
   *  que cierra la categoría va de 2 px, como el de su etiqueta, para que se
   *  vea dónde termina una y empieza la otra (pedido del 16/11/2026). */
  interna?: boolean
}

/** "Fiesta · del 25 de setiembre al 5 de octubre · sigue en octubre" */
function tituloPorDefecto(b: Barra, derivada: boolean): string {
  const partes = [b.nombre, rangoLargo(b.inicio, b.fin)]
  if (b.vieneDeAntes) partes.push(`viene de ${nombreMes(b.inicio.slice(0, 7))}`)
  if (b.sigueDespues) partes.push(`sigue en ${nombreMes(b.fin.slice(0, 7))}`)
  if (derivada) partes.push('se edita en su origen')
  return partes.join(' · ')
}

// Las clases de cada celda de día se arman una vez por tipo de día, no una
// vez por celda: en un mes con todas las categorías son más de mil celdas.
const CELDA = 'relative border-r border-slate-200 dark:border-slate-700'
const CELDA_FINDE = 'bg-slate-100/70 dark:bg-slate-800/60'
// Hoy: un tinte y una línea de la marca que cruza todas las filas.
const CELDA_HOY = "bg-brand-50/70 dark:bg-brand-500/[.07] before:absolute before:inset-y-0 before:left-1/2 before:w-0.5 before:-translate-x-1/2 before:bg-brand-500/50 before:content-['']"
// Un día libre donde se puede cargar algo muestra un + al pasar.
const CELDA_LIBRE = "cursor-cell transition-colors hover:bg-brand-50 dark:hover:bg-brand-500/10 after:absolute after:inset-0 after:flex after:items-center after:justify-center after:text-base after:font-semibold after:text-brand-500 after:opacity-0 after:transition-opacity after:content-['+'] hover:after:opacity-100"

export function FilaRejilla({
  mes, fila, hoy, alto = ALTO_FILA, editable, onBarra, onDiaVacio, esDerivada, tituloDe, detalleDe, semaforoDe, interna = false,
}: FilaProps) {
  const franja = useFranja(mes.dias)
  const zoom = useCalendario(s => s.zoom)
  const ocupado = new Set<number>()
  fila.forEach(b => { for (let d = b.desde; d <= b.hasta; d++) ocupado.add(d) })

  return (
    <div
      className={`grid shrink-0 ${interna ? 'border-b border-slate-200 dark:border-slate-700/80' : 'border-b-2 border-slate-300 dark:border-slate-600'}`}
      style={{ ...franja, minHeight: alto }}
    >
      {Array.from({ length: mes.dias }, (_, i) => i + 1).map(d => {
        const libre = !ocupado.has(d)
        const seCarga = libre && editable && !!onDiaVacio
        return (
          <div
            key={d}
            style={{ gridColumn: d, gridRow: 1 }}
            onClick={seCarga ? () => onDiaVacio!(d) : undefined}
            className={[
              CELDA,
              esFinde(mes.clave, d) ? CELDA_FINDE : '',
              d === hoy ? CELDA_HOY : '',
              seCarga ? CELDA_LIBRE : '',
            ].join(' ')}
          />
        )
      })}

      {fila.map(b => {
        const derivada = esDerivada?.(b) ?? false
        // Una barra derivada no se edita acá, pero sigue siendo clicable: lleva
        // a donde sí se edita (el calendario de retail o la ficha de la acción).
        const clicable = !!onBarra && (editable || derivada)
        // El dato extra solo entra en una barra con lugar: en una angosta le
        // comía el nombre ("Ci… 0/1").
        const detalle = (b.hasta - b.desde + 1) * zoom >= 130 ? detalleDe?.(b) : null
        const semaforo = semaforoDe?.(b) ?? null
        const titulo = tituloDe ? tituloDe(b) : tituloPorDefecto(b, derivada)
        return (
          <button
            key={b.id}
            type="button"
            title={semaforo ? `${titulo}
${semaforo.texto}` : titulo}
            onClick={clicable ? () => onBarra!(b) : undefined}
            disabled={!clicable}
            style={{
              gridColumn: `${b.desde} / ${b.hasta + 1}`,
              gridRow: 1,
              backgroundColor: b.color ?? '#e2e8f0',
              color: textoSobre(b.color),
            }}
            className={[
              'relative z-10 my-[3px] flex items-center gap-1 overflow-hidden rounded-lg px-2 text-left text-[13px] font-semibold leading-8',
              'shadow-sm ring-1 ring-inset ring-black/[.06] transition duration-150 ease-suave',
              // Una barra que viene del mes anterior o sigue en el próximo
              // llega al borde sin redondear y con una flecha: se ve que no
              // termina acá.
              b.vieneDeAntes ? 'ml-0 rounded-l-none pl-0.5' : 'ml-[2px]',
              b.sigueDespues ? 'mr-0 rounded-r-none pr-0.5' : 'mr-[2px]',
              clicable
                ? 'cursor-pointer hover:z-20 hover:-translate-y-px hover:shadow-md hover:ring-black/15 active:translate-y-0 active:shadow-sm focus-visible:z-20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 dark:focus-visible:ring-offset-slate-900'
                : 'cursor-default',
              derivada ? 'border-l-[3px] border-l-slate-900/40' : '',
            ].join(' ')}
          >
            {b.vieneDeAntes && <ChevronLeft className="h-3 w-3 shrink-0 opacity-60" aria-hidden />}
            {semaforo && (
              <span
                className={`h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white/80 ${CLASE_SEMAFORO[semaforo.color]}`}
                role="img"
                aria-label={semaforo.texto}
              />
            )}
            <span className="min-w-0 flex-1 truncate">{b.nombre}</span>
            {detalle && (
              <span className="shrink-0 rounded-md bg-black/10 px-1.5 text-[10px] font-bold leading-[18px] tabular-nums">{detalle}</span>
            )}
            {b.sigueDespues && <ChevronRight className="h-3 w-3 shrink-0 opacity-60" aria-hidden />}
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
  children, filas = 1, tono = 'normal', extra, onAgregar, tituloAgregar, titulo,
}: {
  children: React.ReactNode
  filas?: number
  tono?: 'normal' | 'rm' | 'grupo' | 'destacada'
  extra?: React.ReactNode
  /** Botón + para crear algo en esta banda aunque todos sus renglones estén
   *  ocupados ese día: va al primer renglón libre, o a uno nuevo. */
  onAgregar?: () => void
  tituloAgregar?: string
  /** El nombre entero, para el tooltip, cuando `children` no es un texto. */
  titulo?: string
}) {
  const fondo =
    tono === 'rm' ? 'bg-violet-50 text-violet-900 dark:bg-[#1e1638] dark:text-violet-200'
      : tono === 'grupo' ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
        : tono === 'destacada' ? 'bg-white text-slate-900 dark:bg-slate-900 dark:text-white'
          : 'bg-white text-slate-700 dark:bg-slate-900 dark:text-slate-300'
  return (
    <div
      className={`group/etiqueta sticky left-0 z-20 flex shrink-0 flex-col justify-center gap-0.5 border-b-2 border-r border-slate-300 py-1 pl-2.5 pr-1 dark:border-slate-600 sm:pl-4 sm:pr-1.5 ${fondo}`}
      style={{ width: ESTILO_ETIQUETA, minHeight: filas * ALTO_FILA }}
    >
      <div className="flex items-center gap-0.5 sm:gap-1">
        <div
          className={`line-clamp-2 min-w-0 flex-1 break-words text-xs leading-tight sm:text-[12.5px] ${tono === 'destacada' ? 'font-bold' : 'font-semibold'}`}
          title={titulo ?? (typeof children === 'string' ? children : undefined)}
        >
          {children}
        </div>
        {onAgregar && (
          <button
            type="button"
            onClick={onAgregar}
            title={tituloAgregar}
            aria-label={tituloAgregar}
            className="flex h-8 w-7 shrink-0 items-center justify-center rounded-lg text-slate-500 sm:w-8 transition hover:bg-brand-50 hover:text-brand-700 active:scale-90 group-hover/etiqueta:text-slate-600 dark:text-slate-400 dark:hover:bg-brand-500/15 dark:hover:text-brand-200 dark:group-hover/etiqueta:text-slate-300"
          >
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>
      {extra}
    </div>
  )
}

/** La franja de días sola, para el pie contador del header. */
export function useFranjaDias(dias: number) {
  return useFranja(dias)
}
