// ---------------------------------------------------------------------------
// Medidas de la rejilla. Puro, sin React, para poder probarlo.
// ---------------------------------------------------------------------------

/** Ancho de la columna de etiquetas, la que queda fija a la izquierda. */
export const ANCHO_ETIQUETA = 232

/** Anchos de columna disponibles, en px por día. El 38 es el natural. */
export const ZOOMS = [20, 26, 32, 38, 48, 60, 76]
export const ZOOM_MIN = ZOOMS[0]
export const ZOOM_MAX = ZOOMS[ZOOMS.length - 1]
export const ZOOM_POR_DEFECTO = 38

/** Debajo de este ancho no entra la inicial del día de la semana. */
export const MINIMO_CON_DOW = 30
/** Ni el número de todos los días: pasan a verse de a 5. */
export const MINIMO_CON_NUMERO = 26

export function limitarZoom(px: number): number {
  return Math.min(Math.max(Math.round(px), ZOOM_MIN), ZOOM_MAX)
}

/**
 * Columnas de ancho FIJO, no `minmax(px, 1fr)`.
 *
 * Con `1fr` las columnas se estiran para llenar el contenedor, así que el zoom
 * solo se notaba al agrandar: al achicar, el `1fr` volvía a repartir todo el
 * ancho disponible y la rejilla se veía idéntica. Con px fijos el zoom manda
 * en las dos direcciones y lo que sobra queda en blanco a la derecha.
 */
export function columnasDe(dias: number, zoom: number): string {
  return `repeat(${dias}, ${zoom}px)`
}

/** Ancho de la franja de días sola, sin la columna de etiquetas. */
export function anchoDias(dias: number, zoom: number): number {
  return dias * zoom
}

/** Ancho total de la rejilla: etiquetas + días. */
export function anchoTotal(dias: number, zoom: number): number {
  return ANCHO_ETIQUETA + anchoDias(dias, zoom)
}

/**
 * El paso siguiente de zoom en la dirección pedida. Busca el valor
 * estrictamente mayor o menor, así también funciona cuando el zoom quedó en un
 * número que no está en la lista — que es lo que pasa después de "ajustar".
 */
export function siguienteZoom(actual: number, direccion: 1 | -1): number {
  if (direccion === 1) return ZOOMS.find(z => z > actual) ?? ZOOM_MAX
  for (let i = ZOOMS.length - 1; i >= 0; i--) if (ZOOMS[i] < actual) return ZOOMS[i]
  return ZOOM_MIN
}

export function sePuedeAcercar(zoom: number): boolean { return zoom < ZOOM_MAX }
export function sePuedeAlejar(zoom: number): boolean { return zoom > ZOOM_MIN }

/**
 * Zoom para que el mes entero entre en `anchoDisponible`, que es el ancho real
 * de la caja de una sección — medido del DOM, no calculado a ojo desde
 * `window.innerWidth`, que ignoraba el `max-w` del contenedor y se pasaba.
 */
export function zoomParaAncho(anchoDisponible: number, dias: number): number {
  if (dias <= 0) return ZOOM_POR_DEFECTO
  return limitarZoom(Math.floor((anchoDisponible - ANCHO_ETIQUETA) / dias))
}

/** El porcentaje que muestra el control, relativo al tamaño natural. */
export function porcentajeZoom(zoom: number): number {
  return Math.round((zoom / ZOOM_POR_DEFECTO) * 100)
}
