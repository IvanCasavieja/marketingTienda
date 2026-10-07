// ---------------------------------------------------------------------------
// Orden de apilado de los cuadros en el canvas del editor.
//
// Konva le da el click (y el arrastre) al nodo que está MÁS ARRIBA bajo el
// mouse. Los cuadros se apilan por `z_index`, el orden del archivo, y eso
// alcanza para todo menos para una cosa: la línea suelta del tachado del
// precio regular (Exclusivos TI, ver `geometry: "line"` en types/cenefas.ts).
// En el PPTX el conector va DEBAJO del cuadro del precio y su caja entera
// cae adentro de ese cuadro, así que cada click sobre la línea lo recibía el
// precio: se la veía, pero no había forma de agarrarla ni de moverla (Ivan,
// 07/10/2026: "no es un objeto movible, debería ser un bloque más").
//
// Acá se decide el orden con el que el canvas AGREGA los grupos: el de
// `z_index`, con las líneas sueltas al final, o sea arriba de todo. Es solo
// para el canvas: el `z_index` guardado no cambia y el exportador sigue
// moviendo el conector real del archivo por `_source_shape_id`. Una línea es
// finita y su caja es chica, así que arriba de todo no tapa nada que importe.
// ---------------------------------------------------------------------------

export interface Apilable {
  z_index: number;
  type: string;
  // Lo único que se mira del estilo es `geometry`; cualquier otro estilo
  // (un relleno, una fuente) pasa de largo.
  style?: { geometry?: string } | Record<string, unknown> | null;
}

/** Línea suelta del diseño (el tachado del precio regular). */
export function esLineaSuelta(comp: Apilable): boolean {
  return comp.type === "shape" && comp.style?.geometry === "line";
}

/**
 * Los cuadros en el orden en que el canvas los apila, del fondo hacia arriba:
 * por `z_index` y, al final, las líneas sueltas (entre ellas, también por
 * `z_index`). No muta la lista que recibe.
 */
export function ordenDeApilado<T extends Apilable>(comps: readonly T[]): T[] {
  const porZ = [...comps].sort((a, b) => a.z_index - b.z_index);
  return [...porZ.filter((c) => !esLineaSuelta(c)), ...porZ.filter(esLineaSuelta)];
}
