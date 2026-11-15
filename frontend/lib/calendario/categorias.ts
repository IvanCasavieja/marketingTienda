// ---------------------------------------------------------------------------
// La categoría de una acción.
//
// Pedido de Ivan (12/11/2026): "Para mí debería de ser nueva acción y punto.
// Nueva acción, y esa nueva acción adentro tener la categoría de mega evento,
// evento general, especial... Y figurar en diferentes listados [con] esa
// cocarda visible... para saber también lo que es la importancia".
//
// La categoría NO es un dato nuevo: es lo que hasta acá se llamaba "tipo de
// acción", la fila del calendario donde va la acción (`banda`). Lo que cambió
// es cuándo se elige. Antes era lo primero que se preguntaba al crear ("Nueva
// acción, ¿de qué tipo?"); ahora la acción se crea sola y la categoría es una
// cosa más de adentro: se pone después en su ficha, se cambia cuando haga
// falta, o no se pone nunca.
//
// Este archivo es puro (sin React ni '@/') a propósito: lo usan derivar.ts y
// las pruebas, que se compilan con tsc a secas.
// ---------------------------------------------------------------------------

/**
 * Lo que lleva en `banda` una acción a la que todavía no se le eligió
 * categoría. Es un texto legible y no un vacío porque `banda` se muestra tal
 * cual en varios lados y el servidor no la acepta vacía. El mismo texto está
 * en backend/app/services/calendario_avisos.py: si cambia, cambia en los dos.
 */
export const SIN_CATEGORIA = 'Sin categoría'

/** Para comparar nombres de categoría sin que importen mayúsculas, tildes ni
 *  espacios de más: el Excel trae "MEGA EVENTO" y "Mailing GRAL". */
function limpio(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim().toLowerCase()
}

export function esSinCategoria(banda: string | null | undefined): boolean {
  return !banda || limpio(banda) === limpio(SIN_CATEGORIA)
}

/**
 * Cuánto pesa una categoría: es lo que la cocarda tiene que decir de un
 * vistazo. Ivan nombró tres ("mega evento, evento general, especial"), que
 * son las tres primeras filas del calendario de Tienda Inglesa; todo lo demás
 * va en gris. NO se guarda: es solo cómo se ve. Para destacar una categoría
 * nueva alcanza con sumarla acá.
 */
export type NivelDeCategoria = 'mega' | 'general' | 'especial' | 'comun' | 'sin'

const DESTACADAS: Record<string, NivelDeCategoria> = {
  'mega evento': 'mega',
  'mailing gral': 'general',
  especiales: 'especial',
}

export function nivelDeCategoria(banda: string | null | undefined): NivelDeCategoria {
  if (!banda || esSinCategoria(banda)) return 'sin'
  return DESTACADAS[limpio(banda)] ?? 'comun'
}

/**
 * Filas del Excel que ya no son del calendario de Tienda Inglesa. Tienda
 * Farma tiene su propio mundo (pedido de Ivan, 12/11/2026: "ahí no debería
 * aparecer... debería de tener su propio calendario"). Una acción vieja que
 * siga en una de estas filas se sigue viendo en su mes (derivar.ts nunca
 * esconde un dato), pero ya no se le carga nada nuevo.
 */
export const BANDAS_RETIRADAS = ['TIENDA FARMA']

export function esBandaRetirada(banda: string): boolean {
  return BANDAS_RETIRADAS.some(r => limpio(r) === limpio(banda))
}

/**
 * Lo que se ofrece al elegir la categoría de una acción: "Sin categoría", las
 * del mundo en el orden del calendario y, si la acción está en una que ya no
 * figura (una fila retirada, una que vino del Excel con otro nombre), también
 * esa: si faltara, el selector mostraría otra y parecería que cambió sola.
 */
export function categoriasParaElegir(delMundo: string[], actual?: string | null): string[] {
  const out = [SIN_CATEGORIA, ...delMundo.filter(c => !esSinCategoria(c))]
  if (actual && !esSinCategoria(actual) && !out.includes(actual)) out.push(actual)
  return out
}
