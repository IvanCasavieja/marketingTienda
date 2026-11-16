'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { textoSobre } from '@/lib/calendario/colores'
import { esFinde, isoDe, nombreMes, rangoLargo } from '@/lib/calendario/fechas'
import {
  ANCHO_ETIQUETA, MINIMO_CON_DOW, MINIMO_CON_NUMERO,
  anchoDias, columnasDe, diaMarcadoEn,
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
 *
 * Son 40 y no 38: un renglón con una acción ya medía 40 (la barra de 32, sus
 * 3 + 3 de aire y los 2 de la línea), y uno vacío quedaba en 38. Con la
 * etiqueta de 42 no se notaba; ahora que la etiqueta mide lo que su renglón,
 * todos tienen que medir lo mismo.
 */
export const ALTO_FILA = 40

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
  // Tocar un día marca su columna entera, como en un Excel (pedido del
  // 16/11/2026); tocarlo de nuevo, o Esc, la desmarca.
  const marcado = useCalendario(s => diaMarcadoEn(mes.clave, s.diaMarcado))
  const marcarDia = useCalendario(s => s.marcarDia)

  return (
    <>
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
          const esMarcado = d === marcado
          const dia = `${esHoy ? 'Hoy, ' : ''}${mes.dow[String(d)]} ${d}`
          return (
            <button
              key={d}
              type="button"
              onClick={() => marcarDia(isoDe(mes.clave, d))}
              aria-pressed={esMarcado}
              style={{ gridColumn: d, gridRow: 1 }}
              title={esMarcado ? `${dia} · marcado. Tocá de nuevo para desmarcarlo` : `${dia} · tocá para marcar la columna`}
              data-hoy={esHoy || undefined}
              className={[
                'flex cursor-pointer flex-col items-center overflow-hidden border-r border-slate-200 px-0.5 pb-1.5 pt-2 transition-colors dark:border-slate-700',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500',
                // Un solo fondo por día: el marcado le gana a hoy y al fin de semana.
                esMarcado ? 'bg-amber-300 dark:bg-amber-400'
                  : esHoy ? 'bg-brand-50 hover:bg-amber-100 dark:bg-brand-500/10 dark:hover:bg-amber-400/25'
                    : finde ? 'bg-slate-100 hover:bg-amber-100 dark:bg-slate-800/50 dark:hover:bg-amber-400/25'
                      : 'hover:bg-amber-100 dark:hover:bg-amber-400/25',
              ].join(' ')}
            >
              {conDow && (
                <span className={[
                  'block text-[10px] font-semibold uppercase leading-none',
                  esMarcado ? 'font-bold text-slate-900'
                    : esHoy ? 'text-brand-600 dark:text-brand-300' : 'text-slate-500 dark:text-slate-400',
                ].join(' ')}>
                  {mes.dow[String(d)]}
                </span>
              )}
              {/* Hoy va en un círculo lleno: es lo primero que se busca */}
              <span
                className={[
                  conDow ? 'mt-1' : '',
                  'flex h-[22px] min-w-[22px] items-center justify-center rounded-full px-0.5 text-[13px] font-semibold leading-none tabular-nums',
                  esHoy ? 'bg-brand-600 text-white shadow-sm shadow-brand-600/40'
                    : esMarcado ? 'font-bold text-slate-900'
                      : finde ? 'text-slate-500 dark:text-slate-400'
                        : 'text-slate-700 dark:text-slate-300',
                ].join(' ')}
              >
                {conNumero || esHoy || esMarcado || d === 1 || d % 5 === 0 ? d : ''}
              </span>
            </button>
          )
        })}
      </div>
    </div>
    {/* Hermana de la cabecera y no hija: la cabecera es sticky, y adentro de
        ella la franja mediría solo el alto de la cabecera. */}
    <MarcaDeColumna mes={mes} dia={marcado} />
    </>
  )
}

/**
 * La columna del día marcado: una franja de punta a punta con sus dos líneas.
 * Va por encima de las celdas y por DEBAJO de las barras (z-5 contra z-10),
 * como el relleno de una columna elegida en Excel: encima les lavaba el color
 * y las líneas les cruzaban el nombre. Es una sola caja por sección: marcar
 * un día no vuelve a dibujar ninguna fila. Se apoya en el marco de la sección
 * (ver MarcoScroll).
 */
function MarcaDeColumna({ mes, dia }: { mes: Mes; dia: number | null }) {
  const zoom = useCalendario(s => s.zoom)
  if (dia == null || dia > mes.dias) return null
  return (
    <div
      aria-hidden
      data-columna-marcada={dia}
      className="pointer-events-none absolute inset-y-0 z-[5] border-x-2 border-amber-500 bg-amber-300/40 dark:border-amber-400 dark:bg-amber-300/25"
      style={{ left: `calc(${ESTILO_ETIQUETA} + ${(dia - 1) * zoom}px)`, width: zoom }}
    />
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
  // La barra de esta fila cuyo nombre no entra y que tiene el mouse (o el
  // foco) encima: se le muestra el fantasma con el nombre completo.
  const [fantasma, setFantasma] = useState<string | null>(null)
  const ocupado = new Set<number>()
  fila.forEach(b => { for (let d = b.desde; d <= b.hasta; d++) ocupado.add(d) })

  return (
    <div
      // `grow`: si la etiqueta de la categoría es más alta que sus renglones
      // (un nombre en dos líneas), el renglón llega hasta abajo. Sin esto
      // quedaba una franja blanca entre la fila y la línea de la categoría.
      className={`grid shrink-0 grow ${interna ? 'border-b border-slate-200 dark:border-slate-700/80' : 'border-b-2 border-slate-300 dark:border-slate-600'}`}
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
        const fondo = b.color ?? '#e2e8f0'
        // Si el nombre no entra, al pasar el mouse (o con el foco) aparece
        // encima la barra entera, "como un fantasma" (pedido del 16/11/2026).
        // En el teléfono no: ahí tocar ya abre la ficha con todo.
        const mirarSiNoEntra = (caja: HTMLElement) => {
          const nombre = caja.querySelector<HTMLElement>('[data-nombre]')
          if (nombre && nombre.scrollWidth > nombre.clientWidth + 1) setFantasma(b.id)
        }
        // Cerca del fin de mes se abre hacia la izquierda: no se sale del calendario.
        const haciaLaIzquierda = b.desde > mes.dias - 7
        return (
          <div
            key={b.id}
            style={{ gridColumn: `${b.desde} / ${b.hasta + 1}`, gridRow: 1 }}
            className={[
              'relative my-[3px] min-w-0',
              fantasma === b.id ? 'z-40' : 'z-10',
              b.vieneDeAntes ? 'ml-0' : 'ml-[2px]',
              b.sigueDespues ? 'mr-0' : 'mr-[2px]',
            ].join(' ')}
            onPointerEnter={e => { if (e.pointerType === 'mouse') mirarSiNoEntra(e.currentTarget) }}
            onPointerLeave={() => setFantasma(f => (f === b.id ? null : f))}
            onFocus={e => mirarSiNoEntra(e.currentTarget)}
            onBlur={() => setFantasma(f => (f === b.id ? null : f))}
          >
          <button
            type="button"
            title={semaforo ? `${titulo}\n${semaforo.texto}` : titulo}
            onClick={clicable ? () => onBarra!(b) : undefined}
            disabled={!clicable}
            style={{ backgroundColor: fondo, color: textoSobre(b.color) }}
            className={[
              'relative flex h-full w-full items-center gap-1 overflow-hidden rounded-lg px-2 text-left text-[13px] font-semibold leading-8',
              'shadow-sm ring-1 ring-inset ring-black/[.06] transition duration-150 ease-suave',
              // Una barra que viene del mes anterior o sigue en el próximo
              // llega al borde sin redondear y con una flecha: se ve que no
              // termina acá.
              b.vieneDeAntes ? 'rounded-l-none pl-0.5' : '',
              b.sigueDespues ? 'rounded-r-none pr-0.5' : '',
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
            <span data-nombre className="min-w-0 flex-1 truncate">{b.nombre}</span>
            {detalle && (
              <span className="shrink-0 rounded-md bg-black/10 px-1.5 text-[10px] font-bold leading-[18px] tabular-nums">{detalle}</span>
            )}
            {b.sigueDespues && <ChevronRight className="h-3 w-3 shrink-0 opacity-60" aria-hidden />}
          </button>
          {fantasma === b.id && (
            <span
              aria-hidden
              style={{ backgroundColor: fondo, color: textoSobre(b.color) }}
              className={[
                'pointer-events-none absolute top-0 z-30 flex h-full w-max min-w-full max-w-[min(420px,80vw)] animate-fade-in items-center gap-1.5',
                'rounded-lg px-2.5 text-[13px] font-semibold leading-8 shadow-lg ring-1 ring-black/20',
                haciaLaIzquierda ? 'right-0' : 'left-0',
              ].join(' ')}
            >
              {semaforo && <span className={`h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white/80 ${CLASE_SEMAFORO[semaforo.color]}`} />}
              <span className="truncate">{b.nombre}</span>
              {detalleDe?.(b) && (
                <span className="shrink-0 rounded-md bg-black/10 px-1.5 text-[10px] font-bold leading-[18px] tabular-nums">{detalleDe(b)}</span>
              )}
            </span>
          )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Etiqueta de banda — se queda pegada a la izquierda al scrollear
// ---------------------------------------------------------------------------

export function EtiquetaBanda({
  children, filas = 1, tono = 'normal', extra, onAgregar, tituloAgregar, titulo, clave,
}: {
  children: React.ReactNode
  filas?: number
  tono?: 'normal' | 'rm' | 'grupo' | 'destacada'
  /** Una línea chica debajo del nombre ("2 envíos"). Con `leading-none`, para
   *  que la etiqueta de un renglón no pase de ALTO_FILA. */
  extra?: React.ReactNode
  /** `seccion:categoría`. Con esto, tocar la etiqueta marca su fila entera,
   *  como el número de fila de un Excel (va con <Renglones clave=...>). */
  clave?: string
  /** Botón + para crear algo en esta banda aunque todos sus renglones estén
   *  ocupados ese día: va al primer renglón libre, o a uno nuevo. */
  onAgregar?: () => void
  tituloAgregar?: string
  /** El nombre entero, para el tooltip, cuando `children` no es un texto. */
  titulo?: string
}) {
  const marcada = useCalendario(s => clave != null && s.filaMarcada === clave)
  const marcarFila = useCalendario(s => s.marcarFila)
  // El fondo es opaco también en oscuro: la etiqueta queda pegada a la
  // izquierda y las barras pasan por debajo al correr el mes.
  const fondo =
    marcada ? 'bg-amber-200 text-slate-900 shadow-[inset_4px_0_0_0_#f59e0b,inset_0_2px_0_0_#f59e0b] dark:bg-[#4a4128] dark:text-amber-50'
      : tono === 'rm' ? 'bg-violet-50 text-violet-900 dark:bg-[#1e1638] dark:text-violet-200'
        : tono === 'grupo' ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
          : tono === 'destacada' ? 'bg-white text-slate-900 dark:bg-slate-900 dark:text-white'
            : 'bg-white text-slate-700 dark:bg-slate-900 dark:text-slate-300'
  const nombre = titulo ?? (typeof children === 'string' ? children : undefined)
  // El nombre y su línea chica van juntos, al lado del +: así la etiqueta de
  // un renglón mide lo mismo que el renglón (antes la línea chica iba abajo
  // de todo y la etiqueta quedaba más alta que la fila).
  const cuerpo = (
    <>
      <span className={`line-clamp-2 break-words text-xs leading-tight sm:text-[12.5px] ${tono === 'destacada' ? 'font-bold' : 'font-semibold'}`}>
        {children}
      </span>
      {extra}
    </>
  )
  const CAJA = 'flex min-w-0 flex-1 flex-col justify-center gap-0.5 py-0.5 pl-2.5 text-left sm:pl-4'
  return (
    <div
      className={[
        'group/etiqueta sticky left-0 z-20 flex shrink-0 items-stretch gap-0.5 border-b-2 border-r border-slate-300 pr-1 dark:border-slate-600 sm:gap-1 sm:pr-1.5',
        marcada ? 'border-b-amber-500 dark:border-b-amber-400' : '',
        fondo,
      ].join(' ')}
      style={{ width: ESTILO_ETIQUETA, minHeight: filas * ALTO_FILA }}
      data-fila-marcada={marcada || undefined}
    >
      {clave ? (
        <button
          type="button"
          onClick={() => marcarFila(clave)}
          aria-pressed={marcada}
          title={[nombre, marcada ? 'fila marcada. Tocá de nuevo para desmarcarla' : 'tocá para marcar la fila'].filter(Boolean).join(' · ')}
          className={`${CAJA} cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500`}
        >
          {cuerpo}
        </button>
      ) : (
        <div className={CAJA} title={nombre}>{cuerpo}</div>
      )}
      {onAgregar && (
        <button
          type="button"
          onClick={onAgregar}
          title={tituloAgregar}
          aria-label={tituloAgregar}
          className={[
            'flex h-8 w-7 shrink-0 items-center justify-center self-center rounded-lg transition active:scale-90 sm:w-8',
            marcada
              ? 'text-slate-700 hover:bg-amber-300 hover:text-slate-900 dark:text-amber-100 dark:hover:bg-amber-400/30'
              : 'text-slate-500 hover:bg-brand-50 hover:text-brand-700 group-hover/etiqueta:text-slate-600 dark:text-slate-400 dark:hover:bg-brand-500/15 dark:hover:text-brand-200 dark:group-hover/etiqueta:text-slate-300',
          ].join(' ')}
        >
          <Plus className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

/**
 * Los renglones de una categoría, a la derecha de su etiqueta. Llenan el alto
 * de la etiqueta (ver `grow` en FilaRejilla) y, si la fila está marcada, llevan
 * la franja con sus dos líneas, igual que la columna de un día (por debajo
 * de las barras, que siguen con su color).
 */
export function Renglones({ clave, children }: { clave?: string; children: React.ReactNode }) {
  const marcada = useCalendario(s => clave != null && s.filaMarcada === clave)
  return (
    <div className="relative flex flex-1 flex-col">
      {children}
      {marcada && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-[5] border-y-2 border-amber-500 bg-amber-300/40 dark:border-amber-400 dark:bg-amber-300/25"
        />
      )}
    </div>
  )
}

/** La franja de días sola, para el pie contador del header. */
export function useFranjaDias(dias: number) {
  return useFranja(dias)
}
