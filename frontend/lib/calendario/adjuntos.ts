/**
 * Los archivos del pedido de una tarea (0089). Ivan (24/11/2026): "en el
 * brief de las tareas deberíamos poder adjuntar archivos, como el Excel por
 * ejemplo".
 *
 * Lo mismo que controla el servidor (backend/app/services/adjuntos.py), para
 * decirlo antes de mandar: qué tipos, cuánto pesa cada uno y cuántos por
 * tarea. El servidor además mira que adentro sea lo que dice la extensión.
 *
 * Puro (sin React ni la API): se prueba solo con `npm run test:adjuntos`.
 */
import { pesoLegible } from './zip'

/** Lo que viene del servidor por cada archivo. */
export type Adjunto = {
  id: string
  nombre: string
  /** El tipo (application/pdf, image/png…). */
  tipo: string
  tamano: number
  fecha: string | null
  /** Es de la tarea de la que cuelga esta (el Excel de «Nueva tarea» que ven sus piezas). */
  heredado: boolean
  /** De qué tarea viene, si es heredado (a una agencia no le llega). */
  deLaTarea: string | null
  puedoSacar: boolean
}

export const MAX_BYTES_ADJUNTO = 10 * 1024 * 1024
export const MAX_ADJUNTOS = 5

const EXTENSIONES: Record<string, ClaseDeArchivo> = {
  xlsx: 'excel', xls: 'excel', csv: 'csv', pdf: 'pdf', docx: 'word', doc: 'word',
  jpg: 'imagen', jpeg: 'imagen', png: 'imagen', webp: 'imagen', gif: 'imagen', zip: 'zip',
}

export type ClaseDeArchivo = 'excel' | 'csv' | 'pdf' | 'word' | 'imagen' | 'zip' | 'otro'

/** Para el `accept` del selector de archivos: el navegador muestra solo estos. */
export const ACEPTA_ADJUNTOS = Object.keys(EXTENSIONES).map(e => `.${e}`).join(',')

export const QUE_SE_PUEDE = 'Excel, CSV, PDF, Word, imágenes (JPG, PNG, WEBP o GIF) y ZIP'

export function extension(nombre: string): string {
  const i = nombre.lastIndexOf('.')
  return i >= 0 ? nombre.slice(i + 1).toLowerCase() : ''
}

/** Qué es, por la extensión: para el ícono. Pura. */
export function claseDeArchivo(nombre: string): ClaseDeArchivo {
  return EXTENSIONES[extension(nombre)] ?? 'otro'
}

/** Por qué no se puede adjuntar, o null si se puede. Pura. */
export function problemaConArchivo(nombre: string, tamano: number): string | null {
  if (!(extension(nombre) in EXTENSIONES)) return `«${nombre}»: ese tipo de archivo no se puede adjuntar. Se puede: ${QUE_SE_PUEDE}.`
  if (tamano <= 0) return `«${nombre}» está vacío.`
  if (tamano > MAX_BYTES_ADJUNTO) {
    return `«${nombre}» pesa ${pesoLegible(tamano)}: hasta ${pesoLegible(MAX_BYTES_ADJUNTO)} por archivo. Si es más grande, dejá el link en el detalle.`
  }
  return null
}

type ArchivoElegido = { name: string; size: number }

/**
 * Los archivos elegidos después de sumar `nuevos` a `actuales`: sin los que
 * no se pueden adjuntar, sin repetir uno que ya estaba (mismo nombre y
 * peso) y hasta completar MAX_ADJUNTOS contando los `yaGuardados` de la
 * tarea. Lo que quedó afuera va en `avisos`, para decírselo a la persona. Pura.
 */
export function sumarArchivos<T extends ArchivoElegido>(
  actuales: T[], nuevos: T[], yaGuardados = 0,
): { lista: T[]; avisos: string[] } {
  const lista = [...actuales]
  const avisos: string[] = []
  let sinLugar = 0
  for (const a of nuevos) {
    const problema = problemaConArchivo(a.name, a.size)
    if (problema) { avisos.push(problema); continue }
    if (lista.some(x => x.name === a.name && x.size === a.size)) continue
    if (yaGuardados + lista.length >= MAX_ADJUNTOS) { sinLugar++; continue }
    lista.push(a)
  }
  if (sinLugar > 0) {
    avisos.push(`Hasta ${MAX_ADJUNTOS} archivos por tarea: ${sinLugar === 1 ? 'uno quedó afuera' : `${sinLugar} quedaron afuera`}.`)
  }
  return { lista, avisos }
}

/** "1 archivo", "3 archivos". */
export function cuantosArchivos(n: number): string {
  return `${n} ${n === 1 ? 'archivo' : 'archivos'}`
}

/** El aviso de que cambiaron los archivos de una tarea (se subieron desde
 *  el formulario de alta, que ya se cerró): la ficha que los muestra los
 *  vuelve a pedir. */
export const EVENTO_ADJUNTOS = 'calendario:adjuntos'

export function avisarQueCambiaronAdjuntos(tareaId: string): void {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(EVENTO_ADJUNTOS, { detail: tareaId }))
}
