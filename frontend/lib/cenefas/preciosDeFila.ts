// ---------------------------------------------------------------------------
// Los dos precios de una fila del Convertidor, listos para mostrar.
//
// Sirven para corroborar una fila SIN salir del modal que la está tocando:
// en «Unificar categorías» (varios SKU que van a compartir UN precio) y en las
// sugerencias de descripción de Tinín (Ivan, 07/10/2026: "en todas las
// sugerencias de descripciones nuevas que genera Tinín tenés que traer el
// precio regular y el precio oferta para confirmar").
//
// `precioRegular` es el anterior (el tachado) y `precioOferta` el vigente. El
// símbolo sale de `unidadMoneda`, nunca escrito a mano: una fila en dólares
// tiene que mostrar U$S. Los precios ya vienen partidos en entero y decimal
// (ej. "1.234" + ",50"), así que acá solo se pegan.
// ---------------------------------------------------------------------------

export interface FilaConPrecios {
  unidadMoneda?: string;
  precioRegular: string;
  decimalPrecioRegular: string;
  precioOferta: string;
  decimalPrecioOferta: string;
}

/** `{ anterior: "$118", oferta: "$98,33" }`; vacío el que la fila no trae. */
export function preciosDeFila(r: FilaConPrecios): { anterior: string; oferta: string } {
  const simbolo = r.unidadMoneda || "$";
  const armar = (entero: string, decimal: string) =>
    entero ? `${simbolo}${entero}${decimal || ""}` : "";
  return {
    anterior: armar(r.precioRegular, r.decimalPrecioRegular),
    oferta:   armar(r.precioOferta,  r.decimalPrecioOferta),
  };
}
