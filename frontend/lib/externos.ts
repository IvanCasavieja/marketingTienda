// ---------------------------------------------------------------------------
// Las cuentas externas: la agencia (o un diseñador de afuera) adentro de Core
// Tienda, con la vista limitada.
//
// Pedido de Ivan (15/11/2026): "que la agencia en un futuro tenga acceso a la
// plataforma… limitar también las vistas…". Y el 16/11: la agencia entra
// directo a su tablero de tarjetas; el calendario lo ve solo si un admin se
// lo habilita (su alcance, ver lib/alcance.ts).
//
// Lo que de verdad cuida es el servidor (backend/app/core/externos.py): solo
// le manda lo de su ventana y lo suyo, y lo demás le contesta 403. Acá está lo
// de la pantalla: a dónde entra, qué menú ve y el aviso de qué parte del
// calendario está mirando. Esconder un botón no protege nada: es para que no
// vea botones que no le sirven.
// ---------------------------------------------------------------------------

import type { CurrentUser } from '../types'
import { veCalendario } from './alcance'

export function esExterno(user: CurrentUser | null | undefined): boolean {
  return !!user?.es_externo
}

/** Las pantallas de una cuenta externa (16/11/2026): su tablero de tarjetas
 *  y, si un admin le habilitó el calendario (su alcance no es "No lo ve"), el
 *  calendario. Las demás la mandan a su tablero (y el servidor igual no le
 *  contestaría). */
export const RUTAS_DE_EXTERNOS = ['/entregas', '/perfil', '/mundos']
export const RUTAS_DEL_CALENDARIO = ['/calendario', '/mis-tareas']

/** A dónde entra: a su trabajo, el tablero (que ya muestra solo lo suyo). */
export const INICIO_DE_EXTERNOS = '/entregas'

function enAlguna(pathname: string, rutas: string[]): boolean {
  return rutas.some(r => pathname === r || pathname.startsWith(r + '/'))
}

export function rutaDeExterno(pathname: string, user?: CurrentUser | null): boolean {
  return enAlguna(pathname, RUTAS_DE_EXTERNOS) || (veCalendario(user) && enAlguna(pathname, RUTAS_DEL_CALENDARIO))
}

/** Si es una pantalla del calendario que esta persona no tiene (su alcance
 *  es "No lo ve"), sea del equipo o de afuera. */
export function calendarioVedado(pathname: string, user: CurrentUser | null | undefined): boolean {
  return !!user && !veCalendario(user) && enAlguna(pathname, RUTAS_DEL_CALENDARIO)
}

const FECHA = new Intl.DateTimeFormat('es-UY', { day: 'numeric', month: 'long', timeZone: 'UTC' })

/** "del 8 de noviembre al 7 de diciembre". Las fechas vienen ISO, sin hora:
 *  se leen en UTC para que no se corran un día por la zona del navegador. */
export function ventanaEnPalabras(ventana: { desde: string; hasta: string } | null | undefined): string | null {
  if (!ventana) return null
  const desde = new Date(`${ventana.desde}T00:00:00Z`)
  const hasta = new Date(`${ventana.hasta}T00:00:00Z`)
  if (Number.isNaN(desde.getTime()) || Number.isNaN(hasta.getTime())) return null
  return `del ${FECHA.format(desde)} al ${FECHA.format(hasta)}`
}
