// ---------------------------------------------------------------------------
// Lo que se estaba cargando para entregar, guardado en el navegador (H-039 de
// la auditoría del 25/11/2026: «atrás» o recargar en medio de una entrega
// borraba todo). «Atrás» y recargar ya preguntan antes de salir; esto es para
// cuando igual se sale: recargar sin querer, el iPhone (que al recargar no
// pregunta), la sesión que venció. Al volver a entregar esa tarjeta, está lo
// que se había cargado.
//
// Va solo en este navegador: la nota, el link, el porqué y las imágenes
// sueltas ya achicadas. El ZIP no (puede pesar 40 MB): se pide elegirlo de
// nuevo, y con él vuelven las imágenes que salían de adentro. Es de una
// persona y una tarjeta, dura un día y se borra al mandar, al descartar y al
// cerrar sesión. Acá las reglas, puras; el guardado está en
// components/calendario/entregas/borradores.ts.
// ---------------------------------------------------------------------------

/** Un día: después, lo guardado ya no se ofrece (y se borra). */
export const VIDA_DEL_BORRADOR_MS = 24 * 60 * 60 * 1000

/** Una imagen suelta, ya achicada. Su vista (la URL de la miniatura) es de la
 *  página que la armó: al volver se arma otra. */
export type ImagenGuardada = { grande: Blob; mini: Blob; nombre: string; ancho: number; alto: number }

export type BorradorDeEntrega = {
  /** La fase y su última ronda al guardarlo: se estaba entregando la siguiente. */
  fase: string | null
  ronda: number
  /** El id de la versión: si llegó al servidor, ya se mandó (y reintentar con
   *  el mismo no la duplica). */
  versionId: string
  /** Cuándo se guardó (ms). */
  guardado: number
  comentario: string
  link: string
  porQue: string
  imagenes: ImagenGuardada[]
  /** El nombre del ZIP que se había elegido: hay que volver a elegirlo. */
  zip: string | null
}

/** De una persona y una tarjeta: quien entra después en la misma compu no
 *  ve lo de otro. */
export function claveDeBorrador(usuarioId: number, tareaId: string): string {
  return `${usuarioId}:${tareaId}`
}

/** Lo que se guarda de lo cargado en el formulario, o null si no hay nada que
 *  valga la pena devolver (un ZIP solo no: no se guarda). */
export function armarBorrador(
  cargado: {
    versionId: string; comentario: string; link: string; porQue: string; zip: string | null
    imagenes: (ImagenGuardada & { deZip?: number })[]
  },
  entrega: { fase: string | null; ronda: number },
  ahora: number,
): BorradorDeEntrega | null {
  const imagenes = cargado.imagenes
    .filter(im => im.deZip == null)
    .map(({ grande, mini, nombre, ancho, alto }) => ({ grande, mini, nombre, ancho, alto }))
  const hayTexto = [cargado.comentario, cargado.link, cargado.porQue].some(t => t.trim() !== '')
  if (!hayTexto && imagenes.length === 0) return null
  return {
    fase: entrega.fase, ronda: entrega.ronda, versionId: cargado.versionId, guardado: ahora,
    comentario: cargado.comentario, link: cargado.link, porQue: cargado.porQue, imagenes, zip: cargado.zip,
  }
}

/** Si lo guardado sirve para la entrega que se está por hacer: la misma (misma
 *  fase y misma ronda: nadie entregó otra mientras tanto), que no se haya
 *  mandado ya y de hace menos de un día. Si no, se descarta. */
export function borradorVigente(
  b: Pick<BorradorDeEntrega, 'fase' | 'ronda' | 'versionId' | 'guardado'>,
  entrega: { fase: string | null; ronda: number; versiones: string[] },
  ahora: number,
): boolean {
  const edad = ahora - b.guardado
  return b.fase === entrega.fase && b.ronda === entrega.ronda && !entrega.versiones.includes(b.versionId)
    && edad >= 0 && edad < VIDA_DEL_BORRADOR_MS
}
