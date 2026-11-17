// ---------------------------------------------------------------------------
// Hasta dónde ve el calendario cada persona (16/11/2026, migración 0070).
//
// Ivan: el calendario lo ve mucha gente y lo quiere empezar a cerrar. Cada
// usuario tiene un alcance que elige un admin en el panel: No lo ve / 1 mes /
// 2 meses / 12 meses / Todo. La agencia arranca en "No lo ve"; el equipo, en
// "Todo". N meses = el mes actual y los N−1 siguientes, más los últimos 7
// días del mes anterior.
//
// Lo que de verdad recorta es el servidor (backend/app/core/alcance.py): acá
// está lo de la pantalla (qué menú se ve, a dónde se entra y cómo se dice).
//
// Este archivo es puro (sin React ni '@/') a propósito: lo prueban las
// pruebas, que se compilan con tsc a secas.
// ---------------------------------------------------------------------------

import type { CurrentUser } from '../types'

export type Alcance = 'nada' | '1m' | '2m' | '12m' | 'todo'

export const ALCANCES: { valor: Alcance; nombre: string; bajada: string }[] = [
  { valor: 'nada', nombre: 'No lo ve', bajada: 'Solo su tablero de tarjetas' },
  { valor: '1m', nombre: '1 mes', bajada: 'El mes actual' },
  { valor: '2m', nombre: '2 meses', bajada: 'El actual y el que viene' },
  { valor: '12m', nombre: '12 meses', bajada: 'El actual y los 11 que siguen' },
  { valor: 'todo', nombre: 'Todo', bajada: 'Sin límite' },
]

export function esAlcance(v: unknown): v is Alcance {
  return ALCANCES.some(a => a.valor === v)
}

/** El alcance de alguien. Si el servidor no lo dijo (una sesión vieja), el
 *  de su tipo de cuenta: una externa, nada; una del equipo, todo. */
export function alcanceDe(user: Pick<CurrentUser, 'es_externo' | 'calendario_alcance'> | null | undefined): Alcance {
  const v = user?.calendario_alcance
  if (esAlcance(v)) return v
  return user?.es_externo ? 'nada' : 'todo'
}

/** Si tiene el calendario (y Mis tareas) en el menú. */
export function veCalendario(user: Pick<CurrentUser, 'es_externo' | 'calendario_alcance'> | null | undefined): boolean {
  return alcanceDe(user) !== 'nada'
}

export function nombreDeAlcance(a: Alcance): string {
  return ALCANCES.find(x => x.valor === a)?.nombre ?? a
}
