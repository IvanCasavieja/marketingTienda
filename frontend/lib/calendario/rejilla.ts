// ---------------------------------------------------------------------------
// Medidas de la rejilla. Puro, sin React, para poder probarlo.
// ---------------------------------------------------------------------------

/** Ancho de la columna de etiquetas, la que queda fija a la izquierda. */
export const ANCHO_ETIQUETA = 232

/**
 * La misma columna en el teléfono. Con 232px no quedaba lugar para los días
 * (en una pantalla de 390 se veían tres). La pantalla la toma de la variable
 * CSS --ancho-etiqueta, que cambia con el ancho (ver globals.css).
 */
export const ANCHO_ETIQUETA_TELEFONO = 136

/**
 * En el teléfono el mes no entra entero a un tamaño que se pueda leer. En vez
 * de achicarlo al mínimo (los días quedaban de 20px, sin número), se muestra
 * una semana a un tamaño cómodo y se corre con el dedo.
 */
export const ZOOM_TELEFONO = 32

/** Anchos de columna disponibles, en px por día. El 38 es el natural. */
// 96 y 120: para leer el nombre entero de las acciones de un día (pedido
// del 16/11/2026). El zoom es de cada persona: se guarda en su navegador.
export const ZOOMS = [20, 26, 32, 38, 48, 60, 76, 96, 120]
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
export function zoomParaAncho(anchoDisponible: number, dias: number, anchoEtiqueta = ANCHO_ETIQUETA): number {
  if (dias <= 0) return ZOOM_POR_DEFECTO
  return limitarZoom(Math.floor((anchoDisponible - anchoEtiqueta) / dias))
}

/** El porcentaje que muestra el control, relativo al tamaño natural. */
export function porcentajeZoom(zoom: number): number {
  return Math.round((zoom / ZOOM_POR_DEFECTO) * 100)
}

/**
 * Los renglones de una categoría que se dibujan en un mes. Uno que quedó vacío
 * (su acción es de otro mes, o se movió) no ocupa lugar; si están todos vacíos
 * queda uno, para poder cargar ahí. `carril` es el renglón de verdad: al crear
 * tocando un día libre se usa ese, y no la posición en la pantalla (pedido del
 * 16/11/2026: "aprovechar más el espacio de este calendario").
 */
export function renglonesVisibles<T>(filas: T[][]): { fila: T[]; carril: number }[] {
  const conAlgo = filas.map((fila, carril) => ({ fila, carril })).filter(r => r.fila.length > 0)
  return conAlgo.length > 0 ? conAlgo : [{ fila: filas[0] ?? [], carril: 0 }]
}

/**
 * El día que la persona marcó (una fecha 'YYYY-MM-DD'), como número de día del
 * mes que se mira. Si es de otro mes, null: no hay columna que pintar.
 */
export function diaMarcadoEn(clave: string, marcado: string | null): number | null {
  if (!marcado || marcado.slice(0, 7) !== clave) return null
  const dia = Number(marcado.slice(8, 10))
  return Number.isInteger(dia) && dia >= 1 ? dia : null
}
