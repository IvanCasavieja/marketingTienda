/**
 * Las tarjetas sin acción (24/11/2026): lo que se pide desde Tableros, por
 * fuera del calendario. En el servidor cuelgan de una acción de sistema por
 * mundo, `sin-accion-<mundo>`, que nunca se muestra (ver
 * backend/app/services/sin_accion.py). Acá, lo que necesita saber la pantalla
 * para no ofrecer abrir una acción que no existe.
 *
 * Va sin imports a propósito: así se prueba sola.
 */

export const PREFIJO_SIN_ACCION = 'sin-accion-'

/** Si ese id es el de la acción de sistema de las tarjetas sin acción. Pura. */
export function esSinAccion(accionId: string | null | undefined): boolean {
  return !!accionId && accionId.startsWith(PREFIJO_SIN_ACCION)
}

/**
 * A dónde lleva un aviso de tarea ("acción:tarea") de una tarjeta sin acción:
 * a la tarjeta, en Tableros (no hay ficha de acción que abrir). null si es de
 * una acción común. Lo mismo que avisos_por_mail.destino en el servidor. Pura.
 */
export function destinoDeAvisoSinAccion(origenRef: string | null | undefined): string | null {
  const [accion, tarea] = (origenRef ?? '').split(':')
  if (!esSinAccion(accion) || !tarea) return null
  return `/entregas?tarea=${encodeURIComponent(tarea)}`
}
