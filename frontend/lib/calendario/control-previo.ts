/**
 * El control de la IA antes de entregar (Ivan, 20/11/2026: "que a la agencia,
 * cuando va a subir los archivos, la IA le diga 'che, pará, acá faltan estas
 * cositas de los cambios'").
 *
 * Al tocar "Entregar" con imágenes, el navegador manda primero esas mismas a
 * POST /calendario/tareas/{id}/control-previo. Si la IA ve algo que falta (o
 * que no se ve claro), se le muestra a quien entrega, que elige "Corregir" o
 * "Mandar igual"; si no, se manda solo. Nunca traba: si la IA no está o
 * tarda, se manda igual (ver app/services/revision_ia.py,
 * controlar_antes_de_entregar).
 *
 * Hasta el 21/11/2026 era solo en una ronda que volvía con cambios. Ivan: "No
 * lo hace en la primera entrega, eso está mal. La primera entrega debería
 * compararse contra lo pedido inicialmente". Ahora se pregunta siempre que
 * haya imágenes: en la primera ronda de la fase la IA mira el pedido inicial
 * (`inicial`), en las que vuelven, los cambios pedidos. Si no hay imágenes
 * (o ahora no se podría entregar), el servidor contesta 'sin-pedido' sin
 * llamar a la IA.
 *
 * Desde la prueba de Ivan del 21/11/2026 quien aprueba ve lo que dijo la IA
 * de cada cosa pedida, con el mismo diseño
 * (components/calendario/entregas/LoQueVioLaIA.tsx), más lo que ve hecho. Si
 * la agencia entregó las imágenes que controló, la revisión sale de este
 * control: es lo mismo que vio ella.
 *
 * Y desde el 24/11/2026, también lo que la IA encontró en la pieza (las
 * observaciones: ortografía, otra campaña u otro mundo, legales, precio,
 * QR), lo mismo que ve quien aprueba. Ivan: "la IA sigue encontrando cosas
 * del lado de Tienda que no encuentra del lado de la agencia (...) la acción
 * era TiendaChecks y le mandaron una placa de Ciberofertas". El servidor
 * mira la pieza aunque no haya nada pedido.
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

/** Algo que la IA encontró en la pieza (24/11/2026): lo mismo que ve quien
 *  aprueba. `imagen`: el número de la imagen (1, 2...) en el orden en que se
 *  va a entregar, o null si no la ubicó en una; `x`, `y` (0 a 1), dónde. */
export type ObservacionDelControl = {
  id: string | null
  tipo: string
  texto: string
  gravedad: 'importante' | 'a_revisar'
  imagen: number | null
  x: number | null
  y: number | null
}

export type ControlPrevio = {
  estado: 'sin-pedido' | 'listo' | 'no-disponible'
  cambios: CambioControlado[]
  controlId: string | null
  /** Si lo controlado es el pedido inicial (la primera entrega de la fase). */
  inicial?: boolean
  /** Lo que encontró en la pieza (24/11/2026). Vacío si no encontró nada. */
  observaciones?: ObservacionDelControl[]
}

export const ETIQUETA_DEL_VEREDICTO: Record<VeredictoIA, string> = {
  hecho: 'Hecho',
  falta: 'Falta',
  dudoso: 'No se ve claro',
}

/** Si antes de mandar hay que preguntarle a la IA: siempre que haya imágenes
 *  para mirar, también en la primera entrega (21/11/2026) y aunque no se
 *  haya pedido nada (24/11/2026: mira la pieza). Pura. */
export function hayQueControlar(imagenes: number): boolean {
  return imagenes > 0
}

/** Lo que dice la pantalla mientras la IA mira: la pieza (desde el
 *  24/11/2026, siempre) y, en la primera entrega de la fase, lo que se pidió;
 *  en una ronda que volvió, si se hicieron los cambios pedidos. Si ve algo,
 *  el aviso es el mismo en los dos casos desde el 21/11/2026 («Antes de
 *  mandar, revisá esto»): antes cada caso tenía su «Ojo: parece que falta
 *  algo…». Pura. */
export function textosDelControl(inicial: boolean): { mirando: string } {
  return inicial
    ? { mirando: 'La IA está mirando la pieza y lo que se pidió…' }
    : { mirando: 'La IA está mirando la pieza y si se hicieron los cambios que se pidieron…' }
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

/** Lo que encontró la IA en la pieza, para avisarle a quien entrega antes de
 *  mandar (24/11/2026): las importantes primero, cada grupo en el orden en
 *  que las dio la IA (el mismo que ve quien aprueba). Lo que no tenga texto
 *  no se muestra. Vacío = no hay nada que avisar de la pieza. Pura. */
export function observacionesParaAvisar(control: ControlPrevio | null | undefined): ObservacionDelControl[] {
  if (!control || control.estado !== 'listo' || !Array.isArray(control.observaciones)) return []
  const validas = control.observaciones.filter(o => !!o && typeof o.texto === 'string' && o.texto.trim() !== '')
  const peso = (o: ObservacionDelControl) => (o.gravedad === 'importante' ? 0 : 1)
  return validas.map((o, i) => ({ o, i })).sort((a, b) => peso(a.o) - peso(b.o) || a.i - b.i).map(x => x.o)
}

/** Si la IA dijo dónde está, sobre una de las imágenes que se van a entregar. Pura. */
export function conLugar(o: ObservacionDelControl, imagenes: number): boolean {
  return o.imagen != null && o.imagen >= 1 && o.imagen <= imagenes && o.x != null && o.y != null
}

/** Si son exactamente las mismas imágenes (los mismos archivos preparados, en
 *  el mismo orden) que ya miró la IA: si quien entrega tocó "Corregir" y
 *  vuelve a entregar sin cambiar nada, se manda sin volver a preguntar. Pura. */
export function mismasImagenes(a: readonly Blob[], b: readonly Blob[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i])
}
