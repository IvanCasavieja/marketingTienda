// ---------------------------------------------------------------------------
// Las cuentas externas: la agencia (o un diseñador de afuera) adentro de Core
// Tienda, con la vista limitada.
//
// Pedido de Ivan (15/11/2026): "que la agencia en un futuro tenga acceso a la
// plataforma… limitar también las vistas… que solamente puedan ver el
// calendario actual, no lo que viene dentro de 2 o 3 meses".
//
// Lo que de verdad cuida es el servidor (backend/app/core/externos.py): solo
// le manda lo de su ventana y lo suyo, y lo demás le contesta 403. Acá está lo
// de la pantalla: a dónde entra, qué menú ve y el aviso de qué parte del
// calendario está mirando. Esconder un botón no protege nada: es para que no
// vea botones que no le sirven.
// ---------------------------------------------------------------------------

import type { CurrentUser } from '../types'

export function esExterno(user: CurrentUser | null | undefined): boolean {
  return !!user?.es_externo
}

/** Las pantallas de una cuenta externa. Las demás la mandan a su inicio (y el
 *  servidor igual no le contestaría). */
export const RUTAS_DE_EXTERNOS = ['/entregas', '/mis-tareas', '/calendario', '/perfil', '/mundos']

/** A dónde entra: a su trabajo, el tablero de entregas (que ya muestra solo lo suyo). */
export const INICIO_DE_EXTERNOS = '/entregas'

export function rutaDeExterno(pathname: string): boolean {
  return RUTAS_DE_EXTERNOS.some(r => pathname === r || pathname.startsWith(r + '/'))
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
