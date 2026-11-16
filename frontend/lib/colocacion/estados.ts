// ---------------------------------------------------------------------------
// La foto de colocación: cómo se nombra y se pinta cada estado.
//
// El estado lo decide el servidor (backend/app/services/colocacion.py); acá
// solo se dice. Hay dos voces: la de promo, que revisa ("Por revisar"), y la
// del local, que sube ("Para subir", "Te la devolvieron").
// ---------------------------------------------------------------------------

import { diasEntre, fechaCorta } from '../calendario/fechas'

/** Lo guardado. "atrasada" no se guarda: la calcula el servidor con la fecha límite. */
export type EstadoColocacion = 'pendiente' | 'enviada' | 'aprobada' | 'devuelta'
export type EstadoVisibleColocacion = EstadoColocacion | 'atrasada'

/** Cómo lo ve promo en el tablero. */
export const ETIQUETA_PROMO: Record<EstadoVisibleColocacion, string> = {
  pendiente: 'Pendiente',
  enviada: 'Por revisar',
  aprobada: 'Aprobada',
  devuelta: 'Devuelta',
  atrasada: 'Atrasada',
}

/** Cómo lo ve el local, en su teléfono. */
export const ETIQUETA_LOCAL: Record<EstadoVisibleColocacion, string> = {
  pendiente: 'Para subir',
  enviada: 'Enviada · la están revisando',
  aprobada: 'Aprobada',
  devuelta: 'Te la devolvieron',
  atrasada: 'Atrasada',
}

/** El color de cada estado: pastilla clara con texto oscuro, y su versión oscura. */
export const TONO: Record<EstadoVisibleColocacion, string> = {
  pendiente: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  enviada: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-200',
  aprobada: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200',
  devuelta: 'bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200',
  atrasada: 'bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-200',
}

/** El punto de color, para la grilla y los filtros. */
export const PUNTO: Record<EstadoVisibleColocacion, string> = {
  pendiente: 'bg-slate-400',
  enviada: 'bg-sky-500',
  aprobada: 'bg-emerald-500',
  devuelta: 'bg-amber-500',
  atrasada: 'bg-rose-500',
}

/** El orden de los filtros del tablero: primero lo que hay que hacer. */
export const ORDEN_FILTROS: EstadoVisibleColocacion[] = ['enviada', 'atrasada', 'pendiente', 'devuelta', 'aprobada']

/** "hoy", "mañana", "en 3 días (20/11)" o "venció el 14/11". */
export function cuandoVence(limite: string, hoy: string): { texto: string; urgente: boolean; vencida: boolean } {
  const faltan = diasEntre(hoy, limite)
  if (faltan < 0) return { texto: `venció el ${fechaCorta(limite)}`, urgente: true, vencida: true }
  if (faltan === 0) return { texto: `hoy (${fechaCorta(limite)})`, urgente: true, vencida: false }
  if (faltan === 1) return { texto: `mañana (${fechaCorta(limite)})`, urgente: true, vencida: false }
  return { texto: `en ${faltan} días (${fechaCorta(limite)})`, urgente: false, vencida: false }
}

/** Cuántos le quedan por hacer al local: lo que no está enviado ni aprobado. */
export function pendientesDelLocal(pedidos: { visible: EstadoVisibleColocacion }[]): number {
  return pedidos.filter(p => p.visible === 'pendiente' || p.visible === 'devuelta' || p.visible === 'atrasada').length
}
