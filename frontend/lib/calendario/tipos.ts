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

import type { ResumenEntrega } from './entregas'

/** 'envio' = un envio suelto: un mailing, WhatsApp o push sin accion detras. */
export type Seccion = 'comercial' | 'retail' | 'header' | 'envio'

/** Una barra tal como la guarda el servidor. */
export type BarraGuardada = {
  id: string
  /** De qué negocio es: clave de lib/mundos.ts. */
  mundo?: string
  seccion: Seccion
  /** El tipo de accion ("MEGA EVENTO"), el formato de RM ("CARRUSEL"), la
   *  posicion del header ("pos-3") o el canal de un envio suelto ("email"). */
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
  /** En las acciones y en los envios sueltos. */
  avisos?: Aviso[]
  /** En las acciones y en los envios sueltos: lo que se le asigno a cada persona. */
  tareas?: Tarea[]
  /** Solo en los envios sueltos: lo que en un envio de una accion lleva su
   *  pieza. "Mailing digital", la hora 'HH:MM' en que sale y el estado. */
  formato?: string | null
  hora?: string
  estado?: EstadoPieza
  /** Solo en las acciones: si se les pidió la foto de colocación a los
   *  locales, a cuántos y hasta cuándo. El resto (estados, fotos) lo trae el
   *  tablero aparte: las fotos no viajan con el calendario. */
  fotos?: { pedido: number; locales: number; limite: string }
}

/** Las secciones que tienen ficha (se abre al tocarlas) y avisos. */
export const SECCIONES_CON_FICHA: Seccion[] = ['comercial', 'envio']

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
// Tareas
// ---------------------------------------------------------------------------

export type EstadoTarea = 'pendiente' | 'en-proceso' | 'hecha'

/**
 * Lo que quien lidera le asigna a una persona dentro de una accion (pedido de
 * Ivan, 12/11/2026). Una tarea puede colgar de otra: tarea, subtarea y
 * sub-subtarea, y no mas hondo.
 */
export type Tarea = {
  id: string
  parentId: string | null
  titulo: string
  descripcion: string | null
  estado: EstadoTarea
  /** Id de usuario de la plataforma, o null si todavia no es de nadie. */
  asignadoA: number | null
  /** 'YYYY-MM-DD' */
  vence: string | null
  creadoPor: number | null
  /** Solo en las que vinieron de una plantilla y nadie les cambió la fecha a
   *  mano: `vence` sale de contar `anclaDias` desde el inicio o el fin de la
   *  acción, y si la acción se mueve, se mueve con ella. */
  ancla?: AnclaTarea | null
  anclaDias?: number | null
  /** De qué plantilla vino. */
  plantillaId?: string | null
  /** Quién la hace (16/11/2026): Tienda (por defecto), una agencia de la
   *  plataforma o una de afuera (`agencia` es su nombre). */
  para?: 'tienda' | 'agencia' | 'fuera'
  agencia?: string | null
  /** Si es una pieza: su tipo (Banners, Cenefas…), lo tildado y los datos de más. */
  tipo?: string | null
  opciones?: string[]
  detalles?: Record<string, string | number>
  /** Si lleva entregas por fases (15/11/2026): en qué fase va y a quién le
   *  toca. Solo el resumen; la historia y las imágenes se piden al abrirla. */
  entrega?: ResumenEntrega
}

/** Desde dónde se cuenta el vencimiento de una tarea de plantilla. */
export type AnclaTarea = 'inicio' | 'fin'

/** Una tarea de una plantilla: su vencimiento es relativo a la acción. */
export type TareaDePlantilla = {
  id: string
  /** Otra tarea de la misma plantilla: subtareas de un nivel nomás. */
  parentId: string | null
  titulo: string
  descripcion: string | null
  /** Una persona fija, o null: la tarea se crea sin asignar. */
  asignadoA: number | null
  /** null = la tarea se crea sin fecha. */
  ancla: AnclaTarea | null
  /** Días desde el ancla. Negativo = antes. */
  dias: number
  /** Quién la hace: si es una agencia, al aplicar la plantilla nace su tarjeta. */
  para?: 'tienda' | 'agencia' | 'fuera'
  agencia?: string | null
  /** El tipo de pieza: la tarjeta se llama "<Acción> - <Tipo>". */
  tipo?: string | null
  opciones?: string[]
}

/**
 * Las tareas que lleva casi siempre un tipo de acción, con sus vencimientos
 * relativos (pedido del 15/11/2026). Cada mundo tiene las suyas. Con
 * categoría, la ficha de una acción de esa categoría la sugiere.
 */
export type Plantilla = {
  id: string
  mundo?: string
  nombre: string
  /** La `banda` de las acciones a las que va ("MEGA EVENTO"). null = cualquiera. */
  categoria: string | null
  tareas: TareaDePlantilla[]
}

export const NIVELES_DE_TAREA = 3

export const ETIQUETA_ESTADO_TAREA: Record<EstadoTarea, string> = {
  pendiente: 'Pendiente',
  'en-proceso': 'En proceso',
  hecha: 'Hecha',
}

/** A que profundidad esta una tarea: 1 si no cuelga de nada. */
export function nivelDeTarea(tarea: Tarea, todas: Tarea[]): number {
  let nivel = 1
  let padre = tarea.parentId
  while (padre && nivel <= NIVELES_DE_TAREA) {
    nivel++
    padre = todas.find(t => t.id === padre)?.parentId ?? null
  }
  return nivel
}

/** La tarea y todo lo que cuelga de ella. */
export function conDescendientes(id: string, todas: Tarea[]): Set<string> {
  const ids = new Set([id])
  let crecio = true
  while (crecio) {
    crecio = false
    for (const t of todas) {
      if (t.parentId && ids.has(t.parentId) && !ids.has(t.id)) { ids.add(t.id); crecio = true }
    }
  }
  return ids
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
  /** Lanzar (18/11/2026): lo trae sola cada accion de Redexpres y le llega a
   *  todo el equipo del mundo, ademas de `destinatarios`. Cierre y los de los
   *  Super FDS se sacaron el 20/11/2026 (el Cierre lo crea Valentina a mano). */
  control?: ControlDeAviso
}

export type ControlDeAviso = 'lanzar'

/** Como se llama cada control en la ficha y en la campanita. */
export const NOMBRE_DEL_CONTROL: Record<ControlDeAviso, string> = {
  lanzar: 'Lanzar',
}

/** Las anticipaciones que se ofrecen, de la mas larga a la mas corta. */
export const ANTICIPACIONES_DE_AVISO = [60, 50, 40, 30, 20, 10] as const

/** Alguien de la plataforma que puede recibir un aviso. */
/** Alguien a quien se le puede asignar una tarea o mandar un aviso. Una cuenta
 *  externa (la agencia) viene marcada con su empresa: se le asignan tareas,
 *  pero no recibe avisos ni aprueba (el servidor lo rechaza). */
export type Persona = { id: number; nombre: string; externo?: boolean; empresa?: string | null }

/** Cómo se la nombra en una lista: "Ana (Agencia Pampa)" si es de afuera. */
export function nombreConEmpresa(p: Persona): string {
  return p.externo && p.empresa ? `${p.nombre} (${p.empresa})` : p.nombre
}

/** Las personas que pueden recibir un aviso o aprobar: las del equipo. */
export function delEquipo(personas: Persona[]): Persona[] {
  return personas.filter(p => !p.externo)
}

/**
 * Quiénes pueden llevar una tarea, según quién la hace (19/11/2026): una de
 * Tienda (o lo de una agencia de afuera, que carga alguien del equipo) la
 * lleva alguien de Tienda. Elegir ahí a «Fer (Diseñadores)» convertía la
 * tarea interna en una pieza de la agencia; ahora el servidor lo rechaza.
 * Las cuentas de las agencias (Publicis, Another Monday, Diseñadores: son
 * agencias externas) se ofrecen solo en las piezas de una agencia.
 */
export function asignablesPara(personas: Persona[], para: Tarea['para']): Persona[] {
  return para === 'agencia' ? personas : delEquipo(personas)
}

/**
 * Cómo se compara el nombre de una agencia (19/11/2026): sin espacios de
 * más, sin mayúsculas, sin tildes y con la ñ como n. «Disenadores» y
 * «diseñadores » son Diseñadores. Es la misma cuenta que hace el servidor
 * (backend/app/core/externos.py, clave_de_empresa).
 */
export function claveDeEmpresa(texto: string | null | undefined): string {
  return (texto ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .split(/\s+/).filter(Boolean).join(' ')
}

export function mismaEmpresa(a: string | null | undefined, b: string | null | undefined): boolean {
  const clave = claveDeEmpresa(a)
  return clave !== '' && clave === claveDeEmpresa(b)
}

/** Los nombres de agencia, cada uno una sola vez (manda cómo se escribió el
 *  primero) y en orden alfabético. */
export function agenciasSinRepetir(nombres: (string | null | undefined)[]): string[] {
  const vistas = new Map<string, string>()
  for (const n of nombres) {
    const clave = claveDeEmpresa(n)
    if (clave && !vistas.has(clave)) vistas.set(clave, (n ?? '').split(/\s+/).filter(Boolean).join(' '))
  }
  return [...vistas.values()].sort((a, b) => a.localeCompare(b, 'es'))
}

/**
 * Lo que muestra el selector de agencia del panel de usuarios para lo que se
 * eligió o escribió (`valor`):
 * - `opciones`: las agencias que ya existen (GET /admin/agencias) y, si no
 *   está entre ellas, la que la cuenta ya tiene (`actual`). Al editar una
 *   cuenta la lista viene sin ella (?menos=<id>): si es la única de su
 *   agencia, esa agencia no viene, y tiene que seguir apareciendo elegida.
 * - `elegida`: la opción que es `valor` (sin tildes ni mayúsculas), o null.
 * - `yaExiste`: si lo escrito es una agencia que ya existe sin contar esta
 *   cuenta, el nombre con el que la guarda el servidor; null si la guarda
 *   como se escribió. Antes se comparaba también con la de la propia cuenta,
 *   y al corregirle cómo se escribe a la única de una agencia el panel decía
 *   «Ya existe: se guarda como» el nombre viejo, y el servidor guardaba el
 *   nuevo (revisión del 19/11/2026).
 */
export function agenciaElegida(
  agencias: string[] | null, valor: string, actual?: string | null,
): { opciones: string[] | null; elegida: string | null; yaExiste: string | null } {
  const yaExiste = agencias?.find(a => mismaEmpresa(a, valor)) ?? null
  const propia = (actual ?? '').split(/\s+/).filter(Boolean).join(' ')
  const opciones = agencias && propia && !agencias.some(a => mismaEmpresa(a, propia)) ? [...agencias, propia] : agencias
  return { opciones, elegida: opciones?.find(a => mismaEmpresa(a, valor)) ?? null, yaExiste }
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

/** Los formatos de un canal ("Mailing digital", "Recordatorio"...), los mismos
 *  que ofrece la ficha de una accion. */
export function formatosDeCanal(area: string): string[] {
  return CATALOGO_PIEZAS.find(a => a.area === area)?.formatos ?? []
}

/** "Email", "WhatsApp", "Push". */
export function tituloDeCanal(area: string): string {
  return CANALES_DE_ENVIO.find(c => c.area === area)?.titulo ?? area
}

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
  /** true si es un envio suelto: no sale de ninguna accion. `accionId` es
   *  entonces el id del propio envio, que tiene su ficha. */
  suelto: boolean
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
