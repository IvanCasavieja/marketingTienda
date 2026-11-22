/**
 * El control de la IA antes de entregar (Ivan, 20/11/2026: "que a la agencia,
 * cuando va a subir los archivos, la IA le diga 'che, pará, acá faltan estas
 * cositas de los cambios'").
 *
 * Al tocar "Entregar" con imágenes, el navegador manda primero esas mismas a
 * POST /calendario/tareas/{id}/control-previo. Si la IA ve algo que falta (o
 * que no se ve claro), se le muestra a quien entrega, que elige "Corregir" o
 * "Mandar igual"; si no, se manda solo. Nunca traba: si la IA no está o
 * tarda, se manda igual. A la agencia le llega solo lo de lo pedido (ver
 * app/services/revision_ia.py, controlar_antes_de_entregar).
 *
 * Hasta el 21/11/2026 era solo en una ronda que volvía con cambios. Ivan: "No
 * lo hace en la primera entrega, eso está mal. La primera entrega debería
 * compararse contra lo pedido inicialmente". Ahora se pregunta siempre que
 * haya imágenes: en la primera ronda de la fase la IA mira el pedido inicial
 * (`inicial`), en las que vuelven, los cambios pedidos. Si no hay nada que
 * controlar, el servidor contesta 'sin-pedido' sin llamar a la IA.
 *
 * Desde la prueba de Ivan del 21/11/2026 quien aprueba ve lo que dijo la IA
 * de cada cosa pedida, con el mismo diseño
 * (components/calendario/entregas/LoQueVioLaIA.tsx), más lo que ve hecho. Si
 * la agencia entregó las imágenes que controló, la revisión sale de este
 * control: es lo mismo que vio ella.
 */

export type VeredictoIA = 'hecho' | 'falta' | 'dudoso'

export type CambioControlado = {
  numero: number
  /** Lo que se pidió en la marca (o el punto del pedido inicial). */
  texto: string
  veredicto: VeredictoIA
  /** Lo que vio la IA, en una frase. */
  nota: string
}

export type ControlPrevio = {
  estado: 'sin-pedido' | 'listo' | 'no-disponible'
  cambios: CambioControlado[]
  controlId: string | null
  /** Si lo controlado es el pedido inicial (la primera entrega de la fase). */
  inicial?: boolean
}

export const ETIQUETA_DEL_VEREDICTO: Record<VeredictoIA, string> = {
  hecho: 'Hecho',
  falta: 'Falta',
  dudoso: 'No se ve claro',
}

/** Si antes de mandar hay que preguntarle a la IA: siempre que haya imágenes
 *  para mirar, también en la primera entrega (21/11/2026). Si no hay nada
 *  que controlar, el servidor contesta 'sin-pedido' y se manda. Pura. */
export function hayQueControlar(imagenes: number): boolean {
  return imagenes > 0
}

/** Lo que dice la pantalla mientras la IA mira: en la primera entrega de la
 *  fase, si cumple el pedido inicial; en una ronda que volvió, si se hicieron
 *  los cambios pedidos. Si ve algo, el aviso es el mismo en los dos casos
 *  desde el 21/11/2026 («Antes de mandar, revisá esto» y «Lo que vio la
 *  IA»): antes cada caso tenía su «Ojo: parece que falta algo…». Pura. */
export function textosDelControl(inicial: boolean): { mirando: string } {
  return inicial
    ? { mirando: 'La IA está mirando si la pieza cumple lo que se pidió…' }
    : { mirando: 'La IA está mirando si se hicieron los cambios que se pidieron…' }
}

/** Lo que falta primero, después lo que no se ve claro y al final lo hecho,
 *  cada grupo en el orden de las marcas (o de los puntos). Pura. */
export function enOrden(cambios: readonly CambioControlado[]): CambioControlado[] {
  const peso = (c: CambioControlado) => (c.veredicto === 'falta' ? 0 : c.veredicto === 'dudoso' ? 1 : 2)
  return [...cambios].sort((a, b) => peso(a) - peso(b) || a.numero - b.numero)
}

/** Lo que hay que avisarle a quien entrega antes de mandar: lo que falta
 *  primero y después lo que no se ve claro, cada grupo en el orden de las
 *  marcas. Vacío = se manda solo. Pura. */
export function paraAvisar(control: ControlPrevio | null | undefined): CambioControlado[] {
  if (!control || control.estado !== 'listo') return []
  return enOrden(control.cambios).filter(c => c.veredicto === 'falta' || c.veredicto === 'dudoso')
}

/** Si son exactamente las mismas imágenes (los mismos archivos preparados, en
 *  el mismo orden) que ya miró la IA: si quien entrega tocó "Corregir" y
 *  vuelve a entregar sin cambiar nada, se manda sin volver a preguntar. Pura. */
export function mismasImagenes(a: readonly Blob[], b: readonly Blob[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i])
}
