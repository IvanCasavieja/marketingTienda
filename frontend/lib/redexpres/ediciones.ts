/**
 * Lo que el local escribió en la planilla de Redexpres y todavía no se
 * guardó, fila por fila: { local: { columna: valor } }.
 *
 * Arreglo del 24/11/2026 (lo encontró el Equipo nocturno; Ivan dio el OK):
 * el guardado automático sale 800 ms después de la última tecla, pero leía
 * lo escrito ANTES de esa tecla. Si el local cambiaba una sola celda no se
 * guardaba nada, y si escribía "12" se guardaba "1". Ahora las pantallas
 * guardan lo último (lo llevan en un useRef) y, cuando el servidor contesta,
 * sacan de pendientes solo lo que se mandó: lo que se siguió escribiendo
 * mientras se guardaba queda para el próximo guardado.
 *
 * Va sin imports a propósito (estructura.ts trae React y la API): así se
 * prueba sola.
 */

export type Ediciones = Record<string, Record<string, string>>

/** Las ediciones con ese valor nuevo en esa celda. No cambia la original. Pura. */
export function conEdicion(ediciones: Ediciones, local: string, columna: string, valor: string): Ediciones {
  const fila = Object.prototype.hasOwnProperty.call(ediciones, local) ? ediciones[local] : {}
  return { ...ediciones, [local]: { ...fila, [columna]: valor } }
}

/**
 * Las ediciones después de guardar `enviadas` de ese local: sale cada celda
 * que todavía vale lo que se mandó; la que cambió mientras se guardaba queda
 * pendiente. Si la fila queda vacía, sale entera. Pura.
 */
export function sinLoGuardado(ediciones: Ediciones, local: string, enviadas: Record<string, string>): Ediciones {
  if (!Object.prototype.hasOwnProperty.call(ediciones, local)) return ediciones
  const quedan: Record<string, string> = {}
  for (const [columna, valor] of Object.entries(ediciones[local])) {
    const mandada = Object.prototype.hasOwnProperty.call(enviadas, columna) ? enviadas[columna] : undefined
    if (mandada !== valor) quedan[columna] = valor
  }
  const next = { ...ediciones }
  if (Object.keys(quedan).length > 0) next[local] = quedan
  else delete next[local]
  return next
}
