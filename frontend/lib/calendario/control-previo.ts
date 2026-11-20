/**
 * El control de la IA antes de entregar (Ivan, 20/11/2026: "que a la agencia,
 * cuando va a subir los archivos, la IA le diga 'che, pará, acá faltan estas
 * cositas de los cambios'").
 *
 * En una ronda que vuelve después de un pedido de cambios, al tocar
 * "Entregar" el navegador manda primero las mismas imágenes a
 * POST /calendario/tareas/{id}/control-previo. Si la IA ve algo que falta (o
 * que no se ve claro), se le muestra a quien entrega, que elige "Corregir" o
 * "Mandar igual"; si no, se manda solo. Nunca traba: si la IA no está o
 * tarda, se manda igual. A la agencia le llega solo lo de los cambios
 * pedidos (ver app/services/revision_ia.py, controlar_antes_de_entregar).
 */

export type VeredictoIA = 'hecho' | 'falta' | 'dudoso'

export type CambioControlado = {
  numero: number
  /** Lo que se pidió en la marca. */
  texto: string
  veredicto: VeredictoIA
  /** Lo que vio la IA, en una frase. */
  nota: string
}

export type ControlPrevio = {
  estado: 'sin-pedido' | 'listo' | 'no-disponible'
  cambios: CambioControlado[]
  controlId: string | null
}

export const ETIQUETA_DEL_VEREDICTO: Record<VeredictoIA, string> = {
  hecho: 'Hecho',
  falta: 'Falta',
  dudoso: 'No se ve claro',
}

/** Si antes de mandar hay que preguntarle a la IA: solo en una ronda que
 *  volvió con cambios y con imágenes para mirar. Pura. */
export function hayQueControlar(volvioConCambios: boolean, imagenes: number): boolean {
  return volvioConCambios && imagenes > 0
}

/** Lo que hay que avisarle a quien entrega antes de mandar: lo que falta
 *  primero y después lo que no se ve claro, cada grupo en el orden de las
 *  marcas. Vacío = se manda solo. Pura. */
export function paraAvisar(control: ControlPrevio | null | undefined): CambioControlado[] {
  if (!control || control.estado !== 'listo') return []
  const marcas = [...control.cambios].sort((a, b) => a.numero - b.numero)
  return [
    ...marcas.filter(c => c.veredicto === 'falta'),
    ...marcas.filter(c => c.veredicto === 'dudoso'),
  ]
}

/** Si son exactamente las mismas imágenes (los mismos archivos preparados, en
 *  el mismo orden) que ya miró la IA: si quien entrega tocó "Corregir" y
 *  vuelve a entregar sin cambiar nada, se manda sin volver a preguntar. Pura. */
export function mismasImagenes(a: readonly Blob[], b: readonly Blob[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i])
}
