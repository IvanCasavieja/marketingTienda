/**
 * El semáforo de una acción (pedido de Ivan, 15/11/2026): de un vistazo, en el
 * calendario, cuáles van bien y cuáles están en riesgo.
 *
 * Mira lo que falta (piezas sin aprobar y tareas sin hacer) contra los días que
 * quedan para que arranque. No necesita nada del servidor: sale de lo que el
 * calendario ya tiene cargado.
 *
 * - rojo: falta algo y arranca en 3 días o menos (o ya arrancó), o hay una
 *   tarea vencida.
 * - amarillo: falta algo y arranca en 10 días o menos.
 * - verde: está todo listo, o falta pero queda tiempo.
 * - sin semáforo: la acción no tiene piezas ni tareas (no hay qué medir) o ya
 *   terminó (es historia).
 */
import type { Pieza, Tarea } from './tipos'

export type ColorSemaforo = 'verde' | 'amarillo' | 'rojo'

export type Semaforo = {
  color: ColorSemaforo
  /** Para el título al pasar el mouse y la ficha: "Arranca en 2 días: faltan 3 piezas y 1 tarea". */
  texto: string
}

export const DIAS_ROJO = 3
export const DIAS_AMARILLO = 10

const PIEZA_LISTA = new Set(['aprobado', 'publicado'])

function diasEntre(desde: string, hasta: string): number {
  const [a, b] = [desde, hasta].map(s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)))
  return Math.round((b - a) / 86_400_000)
}

function cuenta(n: number, uno: string, varios: string): string {
  return `${n} ${n === 1 ? uno : varios}`
}

export function semaforoDe(
  accion: { desde: string; hasta: string; piezas?: Pieza[]; tareas?: Tarea[] } | undefined,
  hoy: string,
): Semaforo | null {
  if (!accion || accion.hasta < hoy) return null
  const piezas = accion.piezas ?? []
  const tareas = accion.tareas ?? []
  if (piezas.length === 0 && tareas.length === 0) return null

  const piezasFaltan = piezas.filter(p => !PIEZA_LISTA.has(p.estado)).length
  const tareasFaltan = tareas.filter(t => t.estado !== 'hecha').length
  const vencidas = tareas.filter(t => t.estado !== 'hecha' && !!t.vence && t.vence < hoy).length
  const dias = diasEntre(hoy, accion.desde)

  const falta = [
    piezasFaltan ? cuenta(piezasFaltan, 'pieza', 'piezas') : '',
    tareasFaltan ? cuenta(tareasFaltan, 'tarea', 'tareas') : '',
  ].filter(Boolean).join(' y ')

  if (!falta) return { color: 'verde', texto: 'Todo listo' }

  const cuando = dias < 0 ? 'Ya arrancó' : dias === 0 ? 'Arranca hoy' : dias === 1 ? 'Arranca mañana' : `Arranca en ${dias} días`
  const verbo = piezasFaltan + tareasFaltan === 1 ? 'falta' : 'faltan'
  const texto = `${cuando}: ${verbo} ${falta}` +
    (vencidas ? ` (${cuenta(vencidas, 'tarea vencida', 'tareas vencidas')})` : '')

  if (vencidas > 0 || dias <= DIAS_ROJO) return { color: 'rojo', texto }
  if (dias <= DIAS_AMARILLO) return { color: 'amarillo', texto }
  return { color: 'verde', texto }
}

/** Las clases del puntito, iguales en la rejilla, la lista y la ficha. */
export const CLASE_SEMAFORO: Record<ColorSemaforo, string> = {
  verde: 'bg-emerald-500',
  amarillo: 'bg-amber-400',
  rojo: 'bg-red-500',
}
