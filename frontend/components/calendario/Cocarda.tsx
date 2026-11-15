'use client'

import { ChevronDown, Star } from 'lucide-react'
import {
  SIN_CATEGORIA, esBandaRetirada, esSinCategoria, nivelDeCategoria, type NivelDeCategoria,
} from '@/lib/calendario/categorias'

/**
 * La cocarda de una acción: su categoría, con más o menos peso según cuánto
 * importa (pedido de Ivan, 12/11/2026: "esa cocarda visible de si es un mega
 * evento, si es un evento normal, si es un especial, para saber también lo
 * que es la importancia").
 *
 * Antes la tarjeta mostraba el tipo pintado con el color de la acción, y se
 * leía como un adorno. Ahora cada categoría se ve siempre igual y el color de
 * la acción queda solo en la franja de la tarjeta. La importancia es cantidad
 * de tinta y no un color nuevo: ámbar, rojo y verde ya quieren decir "falta
 * poco", "vencida" y "hecha".
 *
 * Dice lo mismo que la fila del calendario. Una acción sin categoría no lleva
 * cocarda.
 */

type Visible = Exclude<NivelDeCategoria, 'sin'>

const ESTILO: Record<Visible, string> = {
  mega: 'bg-slate-900 font-bold text-white dark:bg-white dark:text-slate-900',
  general: 'bg-brand-100 font-semibold text-brand-800 dark:bg-brand-900/60 dark:text-brand-100',
  especial: 'border border-brand-300 font-semibold text-brand-700 dark:border-brand-500 dark:text-brand-200',
  comun: 'bg-slate-100 font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300',
}

/** Sobre el color de la acción (el encabezado de la ficha), que puede ser
 *  cualquiera: fondo propio, para que se lea siempre. */
const ESTILO_SOBRE_COLOR: Record<Visible, string> = {
  mega: 'bg-slate-900 font-bold text-white',
  general: 'bg-white/90 font-bold text-slate-900',
  especial: 'bg-white/90 font-semibold text-slate-900',
  comun: 'bg-white/80 font-medium text-slate-800',
}

export function Cocarda({ banda, sobreColor = false, compacta = false, conFlecha = false }: {
  banda: string
  /** Va sobre el color de la acción y no sobre el fondo de la página. */
  sobreColor?: boolean
  /** Más chica, para ir al lado de un texto (Mis tareas). */
  compacta?: boolean
  /** Con una flechita: se puede tocar para cambiarla. */
  conFlecha?: boolean
}) {
  const nivel = nivelDeCategoria(banda)
  if (nivel === 'sin') return null
  return (
    <span
      title={banda}
      className={`inline-flex max-w-full items-center gap-1 rounded-full ${
        compacta ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
      } ${(sobreColor ? ESTILO_SOBRE_COLOR : ESTILO)[nivel]}`}
    >
      {nivel === 'mega' && <Star className="h-3.5 w-3.5 shrink-0 fill-amber-400 text-amber-400" aria-hidden />}
      <span className="truncate">{banda}</span>
      {conFlecha && <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />}
    </span>
  )
}

/**
 * La cocarda del encabezado de la ficha para quien puede editar: se toca y se
 * elige otra. Es el único lugar donde se pone o se cambia la categoría. Abajo
 * hay un select de verdad, invisible, así en el teléfono abre la lista del
 * sistema. El select lleva colores propios: la lista desplegada hereda los
 * suyos, y el encabezado puede tener el texto en blanco. Y en el teléfono va
 * con letra de 16px: con menos, el iPhone agranda la página al tocarlo.
 */
export function SelectorDeCategoria({ banda, opciones, onCambiar }: {
  banda: string
  opciones: string[]
  onCambiar: (banda: string) => void
}) {
  const sin = esSinCategoria(banda)
  return (
    <label
      title="Cambiar la categoría"
      className="relative inline-flex max-w-full cursor-pointer rounded-full focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-current"
    >
      {sin ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-current px-2.5 py-1 text-xs font-semibold opacity-80">
          {SIN_CATEGORIA} <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden />
        </span>
      ) : (
        <Cocarda banda={banda} sobreColor conFlecha />
      )}
      <select
        value={sin ? SIN_CATEGORIA : banda}
        onChange={e => onCambiar(e.target.value)}
        aria-label="Categoría de la acción"
        className="absolute inset-0 h-full w-full cursor-pointer bg-white text-base text-slate-900 opacity-0 sm:text-sm"
      >
        {opciones.map(c => (
          <option key={c} value={c}>{esBandaRetirada(c) ? `${c} (ya no se usa)` : c}</option>
        ))}
      </select>
    </label>
  )
}
