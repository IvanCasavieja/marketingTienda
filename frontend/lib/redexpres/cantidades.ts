/**
 * Las cantidades que el local escribe en Mi pedido (y el equipo en la
 * planilla) son enteros desde 0 (H-085, 27/11/2026). Antes se podía escribir
 * «-5» o «2.5»: la casilla lo mostraba, el servidor lo rechazaba con 422 y
 * el local no sabía qué había pasado. Ahora se limpia al escribir y se avisa.
 *
 * Va sin imports a propósito, como ediciones.ts: así se prueba sola.
 */

/** Qué se corrigió: el signo (o letras como la «e»), los decimales o el tope. */
export type AvisoCantidad = 'signo' | 'decimal' | 'maximo' | null

/**
 * El valor escrito, como entero desde 0 y sin pasar el tope. «-5» da «5»,
 * «2.5» o «2,5» da «2», «99» con tope 20 da «20». Si se corrigieron varias
 * cosas, el aviso es la primera (signo, decimal, tope). Pura.
 */
export function limpiarCantidad(valor: string, max?: number): { valor: string; aviso: AvisoCantidad } {
  let aviso: AvisoCantidad = null
  let limpio = valor.trim()
  // Lo que no es dígito ni separador decimal (el «-», el «+», la «e» del
  // formato científico que acepta type=number) se saca.
  const sinSigno = limpio.replace(/[^0-9.,]/g, '')
  if (sinSigno !== limpio) aviso = 'signo'
  limpio = sinSigno
  // Desde el primer separador decimal en adelante, afuera: no hay medio afiche.
  const corte = limpio.search(/[.,]/)
  if (corte >= 0) {
    limpio = limpio.slice(0, corte)
    aviso = aviso ?? 'decimal'
  }
  if (max !== undefined && limpio !== '' && parseInt(limpio, 10) > max) {
    limpio = String(max)
    aviso = aviso ?? 'maximo'
  }
  return { valor: limpio, aviso }
}

/** Teclas que en una casilla de cantidad no tienen sentido (Safari en iOS manda "" con un «-» a medio escribir). */
export const TECLAS_NO_CANTIDAD = new Set(['-', '+', 'e', 'E', '.', ','])

/**
 * Qué hacer con una tecla en una casilla de cantidad. `cortado` dice si en
 * esta casilla ya se tocó «.» o «,»: desde ahí, los dígitos que siguen son
 * decimales y se ignoran (si no, «2.5» tecleado quedaba «25»). Borrar vuelve
 * a dejar escribir; salir de la casilla también (lo hace la pantalla). Pura.
 */
export function teclaEnCantidad(cortado: boolean, tecla: string): { bloquear: boolean; avisar: boolean; cortado: boolean } {
  if (tecla === '.' || tecla === ',') return { bloquear: true, avisar: true, cortado: true }
  if (TECLAS_NO_CANTIDAD.has(tecla)) return { bloquear: true, avisar: true, cortado }
  if (tecla === 'Backspace' || tecla === 'Delete') return { bloquear: false, avisar: false, cortado: false }
  if (cortado && /^[0-9]$/.test(tecla)) return { bloquear: true, avisar: false, cortado: true }
  return { bloquear: false, avisar: false, cortado }
}
