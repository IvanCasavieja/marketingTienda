// ---------------------------------------------------------------------------
// Modelo del calendario. Es el mismo para las tres secciones: un calendario es
// una lista de bandas (tipo de accion / formato / posicion de header) y cada
// banda tiene N filas donde se acuestan barras que ocupan un rango de dias.
// ---------------------------------------------------------------------------

export type Seccion = 'comercial' | 'retail' | 'header'

/** Una barra: una accion, una campana vendida o un banner en el header. */
export type Barra = {
  id: string
  nombre: string
  /** Dia del mes donde arranca (1..31). */
  desde: number
  /** Dia del mes donde termina, inclusive. */
  hasta: number
  color: string | null
  /** Solo en la seccion header: de donde salio la barra. */
  origen?: OrigenHeader
  /** Solo en la seccion comercial: que piezas lleva la accion. */
  piezas?: Pieza[]
}

// ---------------------------------------------------------------------------
// Estructura de una accion: que piezas lleva, agrupadas por area
// ---------------------------------------------------------------------------

export type AreaPieza = 'web-home' | 'web-landing' | 'fisico' | 'email' | 'whatsapp' | 'push'

export type EstadoPieza = 'pendiente' | 'en-proceso' | 'aprobado' | 'publicado'

export type Pieza = {
  id: string
  area: AreaPieza
  formato: string
  /** Vigencia propia. Si falta, la pieza dura lo mismo que la accion. */
  desde?: number
  hasta?: number
  estado: EstadoPieza
  /** Marca de que la pieza quedo cargada en SharePoint. */
  enSharePoint?: boolean
}

/**
 * El catalogo de lo que puede llevar una accion. El area `web-home` es la
 * unica que toca el calendario de headers: una pieza `Header` de ahi baja
 * sola a una posicion libre de marketing.
 */
export const CATALOGO_PIEZAS: { area: AreaPieza; titulo: string; formatos: string[] }[] = [
  {
    area: 'web-home',
    titulo: 'Web · Home',
    formatos: ['Header', 'Carrusel', 'Slider', 'Banner doble', 'Banner triple', 'Banner cuádruple', 'Banner de categoría', 'Fino fijo'],
  },
  {
    area: 'web-landing',
    titulo: 'Web · Landing de la acción',
    formatos: ['Header de landing', 'Carrusel', 'Banner de categoría', 'Grilla de productos', 'Bases y condiciones'],
  },
  {
    area: 'fisico',
    titulo: 'Físico',
    formatos: ['Mailing impreso', 'Cenefas', 'Carpas', 'Pasillos laterales', 'Galería y/o estacionamiento', 'Destacados'],
  },
  { area: 'email', titulo: 'Email', formatos: ['Mailing digital', 'Recordatorio'] },
  { area: 'whatsapp', titulo: 'WhatsApp', formatos: ['Envío masivo'] },
  { area: 'push', titulo: 'Push', formatos: ['Push app'] },
]

/** La pieza que ocupa una posicion del header de la home. */
export const PIEZA_HEADER = { area: 'web-home' as AreaPieza, formato: 'Header' }

export function esPiezaHeader(p: Pieza): boolean {
  return p.area === PIEZA_HEADER.area && p.formato === PIEZA_HEADER.formato
}

export const ETIQUETA_ESTADO: Record<EstadoPieza, string> = {
  pendiente: 'Pendiente',
  'en-proceso': 'En proceso',
  aprobado: 'Aprobado',
  publicado: 'Publicado',
}

/**
 * Las barras del header no se cargan a mano en su mayoria: se derivan. Las de
 * Retail Media salen del calendario de retail (formato HOME SLIDER) y las de
 * marketing van a salir de la estructura web de cada accion. `manual` es la
 * valvula de escape para lo que todavia no tiene origen.
 */
export type OrigenHeader =
  | { tipo: 'retail'; bandaId: string; filaIdx: number }
  | { tipo: 'accion'; accionId: string }
  | { tipo: 'manual' }

/** Una banda es una fila del Excel: "Mailing GRAL", "HOME SLIDER", "Posicion 4". */
export type Banda = {
  id: string
  nombre: string
  /** Solo retail: eComm / Express. Agrupa bandas bajo un encabezado. */
  grupo?: string
  /** Cada fila es un carril independiente donde no se pueden pisar dos barras. */
  filas: Barra[][]
}

/** Un header que pidio una accion pero que no entro en ninguna posicion. */
export type HeaderSinLugar = {
  accionId: string
  nombre: string
  desde: number
  hasta: number
  /** Dias del rango en los que el header ya estaba completo. */
  diasLlenos: number[]
}

export type Mes = {
  /** 'YYYY-MM' */
  clave: string
  dias: number
  /** dia -> inicial del dia de la semana (L M M J V S D) */
  dow: Record<string, string>
  comercial: Banda[]
  retail: Banda[]
  /** Las 10 posiciones del header, de la 1 a la 10. */
  header: Banda[]
  /** Que posiciones ocupa hoy Retail Media. Por defecto [4,5,6]. */
  posicionesRM: number[]
  /** Headers pedidos por acciones que no entraron. El sistema avisa, no decide. */
  sinLugar: HeaderSinLugar[]
  /** Alguien lo editó a mano: no se rehace cuando se reimportan los Excel. */
  tocado?: boolean
}

// --- Datos crudos que vienen del import de Excel -------------------------
export type SeedBarra = { nombre: string; desde: number; hasta: number; color: string | null }
export type SeedBanda = { nombre: string; grupo?: string; filas: SeedBarra[][] }
export type SeedMes = {
  dias: number
  dow: Record<string, string>
  comercial: SeedBanda[]
  retail: SeedBanda[]
}

// --- Roles y permisos ----------------------------------------------------
// Viven en ./permisos.ts, que lee el usuario logueado de la plataforma. Este
// archivo queda puro a proposito: es el modelo del dominio, no sabe de auth.

// --- Notificaciones (espejo de backend/app/models/notificacion.py) -------
export type Notificacion = {
  id: string
  /** Se mapea a Notificacion.tipo */
  tipo: string
  mensaje: string
  leida: boolean
  origen_tipo: string
  origen_ref: string
  destinatario: string
  created_at: string
}

// --- Reglas del header ---------------------------------------------------
export const REGLAS_HEADER = {
  ideal: 7,
  tolerable: 8,
  tope: 10,
  /** Posiciones que Retail Media tiene vendidas por defecto. */
  rmPorDefecto: [4, 5, 6],
  /** Formato del calendario de retail que se publica en el header. */
  formatoHeader: 'HOME SLIDER (Retail Media)',
} as const
