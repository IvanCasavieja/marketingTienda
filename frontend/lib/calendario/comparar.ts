/**
 * «Comparar con la ronda N» en el Revisor: qué imagen de la ronda anterior
 * se ve al lado de la de ahora.
 *
 * Arreglo del 24/11/2026 (Ivan: "cuando se cargan varios archivos, queda el
 * cambio de imagen de la ronda 2 en el lugar de la ronda 1"): la tira de
 * miniaturas que cambia la imagen de ahora quedaba abajo de las dos columnas,
 * debajo de «Antes», y parecía de la ronda anterior. Ahora cada columna
 * tiene su tira: la de ahora debajo de «Ahora» y, si la anterior tenía
 * varias, la suya debajo de «Antes». Y si la de ahora no tiene pareja (la
 * ronda 2 trae una imagen 3 y la 1 tenía dos), antes se mostraba la primera
 * sin decir nada: ahora se dice («La ronda 1 no tenía imagen 3»).
 *
 * Va sin imports a propósito: así se prueba sola (comparar.test.ts).
 */

export type ImagenOrdenada = { id: string; orden: number }

export type ImagenParaComparar = {
  /** La imagen de la ronda anterior que se ve (null si no tenía ninguna). */
  id: string | null
  /** Su número en esa ronda (1, 2...), el de su miniatura. */
  numero: number | null
  /** Si es la primera porque la de ahora no tiene pareja (y nadie eligió otra). */
  sinPareja: boolean
}

/**
 * La de la ronda anterior que va al lado de la de ahora: la que eligió la
 * persona en la tira de «Antes» (si sigue estando); si no, la del mismo
 * lugar (`orden`) que la de ahora; si no hay, la primera, avisando que no
 * tiene pareja. Pura.
 */
export function imagenParaComparar(
  anteriores: readonly ImagenOrdenada[], ordenActiva: number, elegida: string | null,
): ImagenParaComparar {
  const numeroDe = (id: string) => anteriores.findIndex(i => i.id === id) + 1
  if (elegida && anteriores.some(i => i.id === elegida)) return { id: elegida, numero: numeroDe(elegida), sinPareja: false }
  const pareja = anteriores.find(i => i.orden === ordenActiva)
  if (pareja) return { id: pareja.id, numero: numeroDe(pareja.id), sinPareja: false }
  const primera = anteriores[0]
  return primera ? { id: primera.id, numero: 1, sinPareja: true } : { id: null, numero: null, sinPareja: false }
}
