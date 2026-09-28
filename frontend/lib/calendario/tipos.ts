// ---------------------------------------------------------------------------
// Modelo del calendario.
//
// Lo que se guarda es una lista de barras con fechas reales (`BarraGuardada`):
// una accion, una campana de Retail Media o un banner cargado a mano en el
// header. Una barra puede cruzar de mes: "del 25/09 al 05/10" es UNA barra.
//
// Lo que se dibuja es el mes (`Mes`): bandas (tipo de accion / formato /
// posicion de header), cada una con N filas donde se acuestan barras que
// ocupan un rango de dias de ESE mes. El mes no se guarda: se arma cada vez con
// las barras que lo tocan (ver construirMes en derivar.ts).
// ---------------------------------------------------------------------------

export type Seccion = 'comercial' | 'retail' | 'header'

/** Una barra tal como la guarda el servidor. */
export type BarraGuardada = {
  id: string
  seccion: Seccion
  /** El tipo de accion ("MEGA EVENTO"), el formato de RM ("CARRUSEL") o la
   *  posicion del header ("pos-3"). */
  banda: string
  /** En que renglon de su banda va. Se conserva para que una accion que cruza
   *  de mes quede a la misma altura en los dos. */
  carril: number
  nombre: string
  color: string | null
  /** 'YYYY-MM-DD' */
  desde: string
  /** 'YYYY-MM-DD', inclusive */
  hasta: string
  /** Solo en la seccion comercial. */
  piezas?: Pieza[]
  /** Solo en la seccion comercial. */
  avisos?: Aviso[]
}

/** Una barra vista dentro de un mes: lo que dibuja la rejilla. */
export type Barra = {
  id: string
  nombre: string
  /** Dia del mes donde arranca (1..31). Si viene de un mes anterior, 1. */
  desde: number
  /** Dia del mes donde termina, inclusive. Si sigue en el mes que viene, el ultimo. */
  hasta: number
  color: string | null
  /** Solo en la seccion header: de donde salio la barra. */
  origen?: OrigenHeader
  /** Solo en la seccion comercial: que piezas lleva la accion. */
  piezas?: Pieza[]
  /** Las fechas reales, 'YYYY-MM-DD'. */
  inicio: string
  fin: string
  /** Arranca antes de este mes. */
  vieneDeAntes: boolean
  /** Sigue despues de este mes. */
  sigueDespues: boolean
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
  /** Vigencia propia, 'YYYY-MM-DD'. Si falta, la pieza dura lo mismo que la
   *  accion. En las piezas de envio (email, whatsapp, push) `desde` ES la
   *  fecha de envio: salen un dia, no duran un rango. */
  desde?: string
  hasta?: string
  /** 'HH:MM'. Solo en las piezas de envio: a que hora sale. */
  hora?: string
  estado: EstadoPieza
  /** Marca de que la pieza quedo cargada en SharePoint. */
  enSharePoint?: boolean
}

// ---------------------------------------------------------------------------
// Avisos
// ---------------------------------------------------------------------------

/**
 * Un aviso configurado a mano en la ficha de una accion. No hay ninguno por
 * defecto (pedido de Ivan, 28/09/2026): "cuando nos llegue una notificacion,
 * es porque alguien la configuro y porque realmente vale la pena".
 *
 * Se guarda la anticipacion y no la fecha: si la accion se corre, el aviso se
 * corre con ella.
 */
export type Aviso = {
  id: string
  /** Cuantos dias antes de que arranque la accion. */
  diasAntes: number
  /** Ids de usuario de la plataforma. */
  destinatarios: number[]
  creadoPor: number | null
}

/** Las anticipaciones que se ofrecen, de la mas larga a la mas corta. */
export const ANTICIPACIONES_DE_AVISO = [60, 50, 40, 30, 20, 10] as const

/** Alguien de la plataforma que puede recibir un aviso. */
export type Persona = { id: number; nombre: string }

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

/**
 * Los canales que se envian en una fecha y una hora, no que duran un rango:
 * el mailing, el WhatsApp y el push. Con esto se arma el cronograma de envios,
 * que es una vista de las piezas que ya estan cargadas en cada accion -- no se
 * cargan dos veces.
 */
export const CANALES_DE_ENVIO: { area: AreaPieza; titulo: string }[] = [
  { area: 'email', titulo: 'Email' },
  { area: 'whatsapp', titulo: 'WhatsApp' },
  { area: 'push', titulo: 'Push' },
]

const AREAS_DE_ENVIO = new Set<AreaPieza>(CANALES_DE_ENVIO.map(c => c.area))

export function esPiezaDeEnvio(p: Pieza): boolean {
  return AREAS_DE_ENVIO.has(p.area)
}

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
 * marketing de la estructura web de cada accion. `manual` es la valvula de
 * escape para lo que todavia no tiene origen.
 */
export type OrigenHeader =
  | { tipo: 'retail'; barraId: string }
  | { tipo: 'accion'; accionId: string }
  | { tipo: 'manual' }

/** Una banda es una fila del Excel: "Mailing GRAL", "HOME SLIDER", "Posicion 4". */
export type Banda = {
  /** Lo que las barras guardan en `banda`: el nombre, o 'pos-N' en el header. */
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
  /** Dias de ESTE mes (recortados si el pedido cruza de mes). */
  desde: number
  hasta: number
  /** Las fechas reales del pedido. */
  inicio: string
  fin: string
  /** Fechas del pedido en las que el header ya estaba completo. */
  diasLlenos: string[]
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
  /** Que posiciones ocupa Retail Media este mes. Por defecto [4,5,6]. */
  posicionesRM: number[]
  /** Headers pedidos por acciones que no entraron. El sistema avisa, no decide. */
  sinLugar: HeaderSinLugar[]
  /** Los envíos (mailing, WhatsApp, push) que salen este mes, de TODAS las
   *  acciones: un recordatorio puede salir en un mes que su acción no toca. */
  envios: Envio[]
}

/** Un envio, ya ubicado en su dia. */
export type Envio = {
  /** id de la barra que se dibuja */
  id: string
  accionId: string
  accion: string
  /** "Mailing digital", "Recordatorio", "Envio masivo", "Push app" */
  formato: string
  /** El area de la pieza: email, whatsapp o push. */
  area: AreaPieza
  dia: number
  /** 'HH:MM' si la pieza la tiene cargada */
  hora?: string
  color: string | null
  /** true si la pieza no trae fecha propia y toma el arranque de la accion */
  heredaLaFecha: boolean
}

// --- Datos crudos que vienen del import de Excel -------------------------
// Desde el 28/09/2026 de acá solo se usan los nombres de las bandas (ver
// catalogo.ts): las barras de ejemplo ya estan en la base.
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
