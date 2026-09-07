/**
 * "Bold automático (MARCAS)": las palabras EN MAYÚSCULAS de una descripción
 * se imprimen en negrita, porque son la marca ("FOREST", "BUDWEISER",
 * "VALLE DEL SOL").
 *
 * Espejo EXACTO de split_caps() en backend/app/services/cenefas/formatters.py.
 * Si cambia una, tiene que cambiar la otra: el PPTX exportado ya salía bien
 * --el backend parte el texto en runs y le pone negrita al de mayúsculas--
 * pero el preview dibujaba todo con un solo peso y la marca se veía igual que
 * el resto (visto el 07/09/2026). Este archivo existe para que el preview
 * muestre lo mismo que se va a imprimir.
 *
 * El rango es [A-Z] a secas, igual que el backend: una Ñ o una vocal con
 * tilde no cuentan como mayúscula acá. Es a propósito, para que las dos
 * implementaciones coincidan carácter por carácter.
 */

const PATRON = /([A-Z]{2,}[A-Z0-9\-/]*(?:\s+[A-Z]{2,}[A-Z0-9\-/]*)*)/;
const COMPLETO = /^[A-Z]{2,}[A-Z0-9\-/]*(?:\s+[A-Z]{2,}[A-Z0-9\-/]*)*$/;

/** [texto, va en negrita] — mismos tramos que devuelve split_caps. */
export function tramosSmartBold(texto: string): [string, boolean][] {
  if (!texto) return [];
  // String.split con grupo de captura intercala las capturas en el resultado,
  // igual que re.split de Python.
  return texto
    .split(PATRON)
    .filter((p) => p)
    .map((p) => [p, COMPLETO.test(p)] as [string, boolean]);
}

/** true si hay al menos un tramo en mayúsculas que valga la pena resaltar. */
export function tieneMarca(texto: string): boolean {
  return tramosSmartBold(texto).some(([, b]) => b);
}

/**
 * Máscara por carácter de UN renglón ya cortado.
 *
 * Se calcula por renglón y no sobre el texto entero a propósito: Konva
 * descarta el espacio donde corta cada línea, así que los índices de un
 * renglón NO coinciden con los del texto original -- se corren uno por cada
 * salto, y con la máscara global la "F" de "FOREST" quedaba sin negrita y el
 * espacio siguiente sí. Por renglón no hay corrimiento posible.
 *
 * Da el mismo resultado que la detección global: el corte por palabra nunca
 * puede convertir una palabra de 2+ mayúsculas en uná de menos, y si parte
 * "VALLE DEL SOL" en dos renglones, cada mitad sigue siendo mayúsculas.
 *
 * Se indexa por punto de código (Array.from) porque Konva recorre el renglón
 * con su propio separador de grafemas, no por índice de char de JS.
 */
export function mascaraNegrita(linea: string): boolean[] {
  const m: boolean[] = [];
  for (const [t, b] of tramosSmartBold(linea)) {
    for (let i = 0; i < Array.from(t).length; i++) m.push(b);
  }
  return m;
}
