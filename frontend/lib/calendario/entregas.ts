'use client'
// ---------------------------------------------------------------------------
// Entregas por fases con rondas de corrección.
//
// Pedido de Ivan (15/11/2026): "Una tarea tiene fase 1, fase 2, fase 3…; se
// entrega, se aprueba o vuelve con correcciones, la agencia devuelve con las
// correcciones aplicadas, puede volver otra vez, hasta que se aprueba". Como
// las tarjetas de Trello con la agencia, pero adentro de la tarea.
//
// Ivan dice que COR (la referencia) "es espantoso y poco intuitivo, la gente
// se traba". Por eso todo lo de acá apunta a una sola cosa: que el próximo
// paso esté siempre a la vista ("Te toca: revisar la ronda 2 de Arte final")
// y que haya pocos botones.
//
// Las reglas (a quién le toca, cuándo se aprueba) las decide el servidor:
// backend/app/services/entregas.py. Acá están los nombres, el formulario del
// pedido según el tipo de pieza y la compresión de las imágenes.
// ---------------------------------------------------------------------------

export type TipoPieza = 'cenefa' | 'mailing' | 'banner' | 'redes' | 'otro'
/** Las columnas del tablero: le toca a la agencia, a un aprobador, volvió, terminó. */
export type MomentoEntrega = 'produccion' | 'revision' | 'cambios' | 'aprobada'
export type EstadoFase = 'pendiente' | 'en-curso' | 'aprobada'
export type EstadoVersion = 'revision' | 'aprobada' | 'cambios'
export type TipoDecision = 'aprobada' | 'aprobada-con-cambios' | 'cambios'

/** Las columnas del tablero estilo Trello (16/11/2026). La calcula el
 *  servidor (backend/app/services/entregas.py: columna_de). */
export type Columna = 'ingresado' | 'en-proceso' | 'esperando' | 'finalizado' | 'archivado'

/** Quién hace la tarjeta: una agencia de la plataforma, una de afuera (con
 *  quién del equipo carga sus entregas) o alguien de Tienda. */
export type QuienLaHace = { tipo: 'agencia' | 'fuera' | 'tienda'; nombre: string | null; carga?: string | null }

/** Lo que viaja con cada tarea en /calendario/datos: sin imágenes ni historia. */
export type ResumenEntrega = {
  tipoPieza: TipoPieza
  momento: MomentoEntrega
  /** En qué columna del tablero está. */
  columna?: Columna
  /** La última ronda de la fase actual (0 = todavía no se entregó nada). */
  ronda: number
  faseActual: string | null
  aprobadorDeTurno: number | null
  aprobadores: number[]
  /** `motivo`: lo que hay que cambiar, si la fase la abrió una devolución. */
  fases: { id: string; nombre: string; estado: EstadoFase; rondas: number; motivo?: string | null }[]
}

export type Marca = {
  id: string
  numero: number
  imagenId: string
  /** De 0 a 1, relativos al ancho y al alto de la imagen. */
  x: number
  y: number
  texto: string
  /** 'cambio' sale de "Pedir cambios"; 'ajuste', de "Aprobado con cambios". */
  tipo: 'cambio' | 'ajuste'
  autor: number | null
  corregida: boolean
  corregidaEn: string | null
}

export type Decision = {
  aprobador: number | null
  decididoPor: number | null
  orden: number
  decision: TipoDecision
  comentario: string | null
  /** Solo para el equipo. A una cuenta externa (la agencia) no le llega ni la clave. */
  notaInterna?: string | null
  fecha: string | null
}

export type ImagenDeVersion = { id: string; orden: number; purgada: boolean }

export type Version = {
  id: string
  faseId: string
  ronda: number
  estado: EstadoVersion
  subidaPor: number | null
  fecha: string | null
  decididaEl: string | null
  comentario: string | null
  link: string | null
  corregidas: string[]
  imagenes: ImagenDeVersion[]
  decisiones: Decision[]
  marcas: Marca[]
}

export type FaseDetalle = {
  id: string
  orden: number
  nombre: string
  estado: EstadoFase
  aprobadaEl: string | null
  /** Si la abrió una devolución después de aprobada (17/11/2026): lo que hay
   *  que cambiar y quién lo pidió. */
  motivo?: string | null
  abiertaPor?: number | null
  versiones: Version[]
}

export type AccionDeTarjeta = {
  id: string; mundo: string; nombre: string; color: string | null; desde: string; hasta: string
}

export type DetalleEntregas = {
  tarea: {
    id: string; titulo: string; descripcion: string | null; estado: string
    asignadoA: number | null; vence: string | null; creadoPor: number | null
    ancla?: 'inicio' | 'fin' | null; anclaDias?: number | null
    /** El tipo de tarea (Banners, Cenefas…), lo tildado y los datos de más. */
    tipo?: string | null; opciones?: string[]; detalles?: Record<string, string | number>
    /** Lo pedido con sus medidas: "Banners: Header (web 1920×416 · mobile 640×260)". */
    pedido?: string | null
    quienLaHace?: QuienLaHace
  }
  accion: AccionDeTarjeta & { seccion: string }
  tipoPieza: TipoPieza
  brief: Record<string, string | number>
  aprobadores: number[]
  resumen: ResumenEntrega
  fases: FaseDetalle[]
  /** id (como texto) -> nombre */
  personas: Record<string, string>
  columna?: Columna
  puedo: {
    entregar: boolean; decidir: boolean; comoRespaldo: boolean; configurar: boolean; tildarMarcas: boolean
    /** Devolver una pieza ya aprobada con un texto: abre la Entrega siguiente. */
    devolver?: boolean
    /** Si ve lo que encontró la IA (aprobadores y quien gestiona; nunca quien entrega). */
    verRevisionIA?: boolean
    /** A qué columnas del tablero la puede llevar. */
    mover?: Columna[]
  }
  limites: { imagenes: number; bytesImagen: number; marcas: number }
  /** La conversación de la tarjeta, al costado como en Trello (17/11/2026). */
  comentarios?: ComentarioDeTarjeta[]
}

export type ComentarioDeTarjeta = {
  id: string
  autor: number | null
  autorNombre: string | null
  texto: string
  fecha: string | null
  /** Si lo escribió quien mira. */
  mio: boolean
}

/** Una tarjeta del tablero, de "Mis tareas" o del buscador. Liviana: la
 *  miniatura va por id (se pide cuando la tarjeta se ve) y nada de historia. */
export type Tarjeta = {
  tareaId: string
  titulo: string
  estado: string
  columna: Columna
  /** En proceso porque volvió con cambios (se ve en la tarjeta). */
  volvioConCambios: boolean
  /** Se archivó sin aprobarse (se canceló): no se entrega ni se revisa. */
  cancelada?: boolean
  vence: string | null
  ancla?: 'inicio' | 'fin' | null
  anclaDias?: number | null
  tipo?: string | null
  opciones?: string[]
  asignadoA: number | null
  responsable: string | null
  turno: string | null
  hace?: QuienLaHace
  accion: AccionDeTarjeta
  entrega: ResumenEntrega
  miniatura: string | null
  puedo?: { entregar: boolean; decidir: boolean; mover: Columna[] }
  archivadaEl?: string | null
  actualizada: string | null
}

export type GrupoDeMetricas = {
  clave: string | number | null
  nombre?: string
  fases: number
  rondasPromedio: number | null
  aLaPrimera: number | null
}

export type Metricas = {
  fases: number
  rondasPromedio: number | null
  aLaPrimera: number | null
  porTipo: GrupoDeMetricas[]
  porResponsable: GrupoDeMetricas[]
  porMundo: GrupoDeMetricas[]
  dias: number
}

// ---------------------------------------------------------------------------
// El pedido a la agencia (brief), según el tipo de pieza
// ---------------------------------------------------------------------------
// Es el mismo formulario que valida el servidor (CAMPOS_DEL_BRIEF en
// backend/app/services/entregas.py): si cambia, cambia en los dos.

export type CampoBrief = {
  clave: string
  etiqueta: string
  tipo: 'texto' | 'numero' | 'fecha' | 'url' | 'largo' | 'opciones'
  opciones?: string[]
  placeholder?: string
  /** Lo que ocupa en la grilla de dos columnas de la notebook. */
  entero?: boolean
}

/** El texto libre: está en todos los tipos. Lo va a poder llenar el dictado por voz. */
export const CAMPO_DETALLE: CampoBrief = {
  clave: 'detalle', etiqueta: 'Qué se necesita (texto libre)', tipo: 'largo', entero: true,
  placeholder: 'Contale a la agencia lo que no entra en los otros campos: tono, referencias, qué no puede faltar…',
}

export const TIPOS_DE_PIEZA: { tipo: TipoPieza; nombre: string; fases: string[]; campos: CampoBrief[] }[] = [
  {
    tipo: 'cenefa', nombre: 'Cenefa', fases: ['Boceto', 'Arte final'],
    campos: [
      { clave: 'medidas', etiqueta: 'Medidas', tipo: 'texto', placeholder: 'Ej: A4 apaisada, 3xA4' },
      { clave: 'cantidad', etiqueta: 'Cantidad', tipo: 'numero', placeholder: 'Ej: 120' },
      { clave: 'precio', etiqueta: 'Precio', tipo: 'texto', placeholder: 'Ej: $ 199 o 2x1' },
      { clave: 'vigenciaDesde', etiqueta: 'Vigencia desde', tipo: 'fecha' },
      { clave: 'vigenciaHasta', etiqueta: 'Vigencia hasta', tipo: 'fecha' },
      { clave: 'legales', etiqueta: 'Legales', tipo: 'largo', entero: true, placeholder: 'Ej: Válido hasta agotar stock. No acumulable.' },
    ],
  },
  {
    tipo: 'mailing', nombre: 'Email marketing (EMM)', fases: ['Boceto', 'Arte final'],
    campos: [
      { clave: 'asunto', etiqueta: 'Asunto', tipo: 'texto', entero: true, placeholder: 'Ej: ¡Llegó la Navidad a Tienda Inglesa!' },
      { clave: 'segmento', etiqueta: 'Segmento', tipo: 'texto', placeholder: 'Ej: Clientes Club con compras en 2026' },
      { clave: 'fechaEnvio', etiqueta: 'Fecha de envío', tipo: 'fecha' },
      { clave: 'llamado', etiqueta: 'Llamado a la acción', tipo: 'texto', entero: true, placeholder: 'Ej: Comprá online' },
    ],
  },
  {
    tipo: 'banner', nombre: 'Banner web', fases: ['Boceto', 'Arte final', 'Adaptaciones'],
    campos: [
      { clave: 'medidas', etiqueta: 'Medidas', tipo: 'texto', placeholder: 'Ej: 1920x480 y 768x768' },
      { clave: 'link', etiqueta: 'Link de destino', tipo: 'url', placeholder: 'https://www.tiendainglesa.com.uy/…' },
      { clave: 'desde', etiqueta: 'Desde', tipo: 'fecha' },
      { clave: 'hasta', etiqueta: 'Hasta', tipo: 'fecha' },
    ],
  },
  {
    tipo: 'redes', nombre: 'Redes', fases: ['Boceto', 'Arte final', 'Adaptaciones'],
    campos: [
      { clave: 'formato', etiqueta: 'Formato', tipo: 'opciones', opciones: ['Post', 'Story', 'Reel', 'Carrusel'] },
      { clave: 'fecha', etiqueta: 'Fecha de publicación', tipo: 'fecha' },
      { clave: 'copy', etiqueta: 'Copy', tipo: 'largo', entero: true, placeholder: 'El texto que acompaña la publicación' },
    ],
  },
  { tipo: 'otro', nombre: 'Otro', fases: ['Boceto', 'Arte final'], campos: [] },
]

export function tipoDePieza(tipo: string | null | undefined) {
  return TIPOS_DE_PIEZA.find(t => t.tipo === tipo) ?? TIPOS_DE_PIEZA[TIPOS_DE_PIEZA.length - 1]
}

/** Todos los campos del formulario de un tipo, con el texto libre al final. */
export function camposDe(tipo: TipoPieza): CampoBrief[] {
  return [...tipoDePieza(tipo).campos, CAMPO_DETALLE]
}

// ---------------------------------------------------------------------------
// Cómo se dice
// ---------------------------------------------------------------------------

export const COLUMNAS: { momento: MomentoEntrega; titulo: string; bajada: string }[] = [
  { momento: 'produccion', titulo: 'En producción', bajada: 'Le toca a la agencia' },
  { momento: 'revision', titulo: 'Para revisar', bajada: 'Le toca a un aprobador' },
  { momento: 'cambios', titulo: 'Con cambios', bajada: 'Volvió a la agencia' },
  { momento: 'aprobada', titulo: 'Aprobadas', bajada: 'Últimos 30 días' },
]

export const TONO_MOMENTO: Record<MomentoEntrega, string> = {
  produccion: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-200',
  revision: 'bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200',
  cambios: 'bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-200',
  aprobada: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200',
}

export const ETIQUETA_DECISION: Record<TipoDecision, string> = {
  aprobada: 'Aprobó',
  'aprobada-con-cambios': 'Aprobó con cambios',
  cambios: 'Pidió cambios',
}

/** "Fase 1 · Boceto": el estado de cada fase en una línea corta. */
export function estadoDeFase(
  fase: ResumenEntrega['fases'][number], resumen: ResumenEntrega,
): { texto: string; tono: 'hecha' | 'actual' | 'cambios' | 'pendiente' } {
  if (fase.estado === 'aprobada') {
    return { texto: fase.rondas === 1 ? 'Aprobada a la primera' : `Aprobada en ${fase.rondas} rondas`, tono: 'hecha' }
  }
  if (fase.estado === 'pendiente') return { texto: 'Pendiente', tono: 'pendiente' }
  if (resumen.momento === 'revision') return { texto: `En revisión · ronda ${resumen.ronda}`, tono: 'actual' }
  if (resumen.momento === 'cambios') return { texto: `Con cambios · ronda ${resumen.ronda}`, tono: 'cambios' }
  return { texto: resumen.ronda === 0 ? 'En producción' : `En producción · ronda ${resumen.ronda + 1}`, tono: 'actual' }
}

/**
 * El próximo paso en la vista de UNA entrega, donde el servidor dice si la
 * persona puede decidir. Si la cadena dice que le toca pero la versión la
 * subió ella, no es su turno: nadie aprueba lo que entregó (17/11/2026: antes
 * decía "Te toca: revisar" y no aparecía ningún botón). Las listas (tablero,
 * ficha, Mis tareas) no tienen ese dato y muestran el turno de la cadena.
 */
export function pasoEnLaVista(paso: ProximoPaso, puedeDecidir: boolean, laSubioYo: boolean): ProximoPaso {
  if (paso.accion === 'revisar' && !puedeDecidir && laSubioYo) {
    return {
      texto: 'La entregaste vos: la revisa otra persona del equipo (nadie aprueba lo que entregó)',
      accion: null, aQuien: 'otro',
    }
  }
  return paso
}

export type ProximoPaso = {
  /** "Te toca: revisar la ronda 2 de Arte final" */
  texto: string
  /** Lo que hace el botón principal, si es la persona que mira la que tiene que hacer algo. */
  accion: 'entregar' | 'revisar' | null
  /** Si le toca a quien mira (se destaca), a otra persona o a nadie. */
  aQuien: 'vos' | 'otro' | 'nadie'
}

/**
 * El próximo paso, dicho para quien mira. Es lo primero que se ve en la
 * tarea, en el tablero y en "Mis tareas": la respuesta a "¿y ahora qué?".
 */
export function proximoPaso(
  resumen: ResumenEntrega,
  responsableId: number | null,
  usuarioId: number | null,
  nombreDe: (id: number | null) => string,
  puedeDecidir = false,
  /** Para las tarjetas de una agencia (16/11/2026): si quien mira la entrega
   *  (es de la agencia de la tarjeta) y cómo se nombra a quien la hace. */
  quien: { entregoYo?: boolean; hace?: QuienLaHace | null } = {},
): ProximoPaso {
  const fase = resumen.fases.find(f => f.id === resumen.faseActual)
  if (resumen.momento === 'aprobada' || !fase) {
    return {
      texto: resumen.fases.length === 1 ? 'Finalizada: se aprobó la entrega' : 'Aprobada: todas las fases quedaron aprobadas',
      accion: null, aQuien: 'nadie',
    }
  }
  // Con una sola fase (la "Entrega" con la que nacen las tarjetas) no se
  // nombra la fase: "entregar Entrega" no se entiende.
  const unaSola = resumen.fases.length === 1
  const deFase = unaSola ? '' : ` de ${fase.nombre}`
  if (resumen.momento === 'revision') {
    const que = `revisar la ronda ${resumen.ronda}${deFase}`
    if (puedeDecidir || (usuarioId != null && resumen.aprobadorDeTurno === usuarioId)) {
      return { texto: `Te toca: ${que}`, accion: 'revisar', aQuien: 'vos' }
    }
    return {
      texto: resumen.aprobadorDeTurno != null ? `Le toca a ${nombreDe(resumen.aprobadorDeTurno)}: ${que}` : `Falta que alguien la revise: ${que}`,
      accion: null, aQuien: 'otro',
    }
  }
  const ronda = resumen.ronda + 1
  const que = resumen.momento === 'cambios'
    ? `corregir y entregar la ronda ${ronda}${deFase}`
    : ronda === 1 ? (unaSola ? 'entregar' : `entregar ${fase.nombre}`) : `entregar la ronda ${ronda}${deFase}`
  const soyYo = quien.entregoYo ?? (usuarioId != null && responsableId === usuarioId)
  if (soyYo) return { texto: `Te toca: ${que}`, accion: 'entregar', aQuien: 'vos' }
  // Una agencia (de la plataforma o de afuera) se nombra por la agencia.
  if (quien.hace && quien.hace.tipo !== 'tienda' && quien.hace.nombre) {
    return { texto: `Le toca a ${quien.hace.nombre}: ${que}`, accion: null, aQuien: 'otro' }
  }
  if (responsableId == null) return { texto: `Falta asignar quién entrega: ${que}`, accion: null, aQuien: 'nadie' }
  return { texto: `Le toca a ${nombreDe(responsableId)}: ${que}`, accion: null, aQuien: 'otro' }
}

/** La versión con la que se compara una: la ronda anterior de la misma fase
 *  o, si es la primera, la aprobada de la fase anterior (Boceto → Arte final). */
export function versionAnterior(fases: FaseDetalle[], version: Version): Version | null {
  const i = fases.findIndex(f => f.id === version.faseId)
  if (i === -1) return null
  const misma = fases[i].versiones.filter(v => v.ronda < version.ronda).sort((a, b) => b.ronda - a.ronda)[0]
  if (misma) return misma
  for (let j = i - 1; j >= 0; j--) {
    const aprobada = fases[j].versiones.find(v => v.estado === 'aprobada')
    if (aprobada) return aprobada
  }
  return null
}

/** Las marcas de la tarea que todavía no se corrigieron, de la más vieja a la más nueva. */
export function marcasPendientes(fases: FaseDetalle[]): (Marca & { ronda: number; fase: string })[] {
  return fases.flatMap(f => f.versiones.flatMap(v => v.marcas
    .filter(m => !m.corregida)
    .map(m => ({ ...m, ronda: v.ronda, fase: f.nombre }))))
}

/** "15/11 14:32" */
export function fechaYHora(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  return `${dd}/${mm} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** "1,6" — el promedio de rondas, con coma. */
export function numero(n: number | null, decimales = 1): string {
  if (n == null) return '—'
  return n.toFixed(decimales).replace('.', ',').replace(/,0+$/, '')
}

export function nuevoIdDeVersion(): string {
  const azar = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : Math.random().toString(36).slice(2, 18)
  return `ve-${azar}`
}

// ---------------------------------------------------------------------------
// Las imágenes: se comprimen en el navegador antes de subir
// ---------------------------------------------------------------------------
// La base es de 500 MB para TODA la plataforma (Supabase gratis, y no se va a
// pagar más): una foto del teléfono pesa 3-8 MB y acá sale en 50-250 KB.
// Lado mayor 1600 px (alcanza para ver un error de tilde en una cenefa) en
// JPEG 0,75, y una miniatura de 320 px para el tablero y la historia. Lo que
// pesa cada cosa, y cuándo se borra, está en backend/app/models/entregas.py.

export const LADO_MAYOR = 1600
export const CALIDAD = 0.75
export const LADO_MINIATURA = 320
/** El tope del servidor por imagen. Comprimida, una nunca llega ni cerca. */
export const MAX_BYTES_IMAGEN = 2 * 1024 * 1024

function cargar(archivo: Blob): Promise<HTMLImageElement> {
  return new Promise((resolver, rechazar) => {
    const url = URL.createObjectURL(archivo)
    const img = new Image()
    // El navegador ya endereza la foto según su EXIF (la del teléfono sale
    // de costado si no): dibujarla en el canvas la deja derecha.
    img.onload = () => { URL.revokeObjectURL(url); resolver(img) }
    img.onerror = () => { URL.revokeObjectURL(url); rechazar(new Error('No se pudo leer la imagen')) }
    img.src = url
  })
}

function aJpeg(img: HTMLImageElement, lado: number, calidad: number): Promise<Blob> {
  const escala = Math.min(1, lado / Math.max(img.naturalWidth, img.naturalHeight))
  const ancho = Math.max(1, Math.round(img.naturalWidth * escala))
  const alto = Math.max(1, Math.round(img.naturalHeight * escala))
  const canvas = document.createElement('canvas')
  canvas.width = ancho
  canvas.height = alto
  const ctx = canvas.getContext('2d')
  if (!ctx) return Promise.reject(new Error('Este navegador no puede preparar la imagen'))
  // Un PNG con transparencia saldría con el fondo negro en JPEG: va en blanco.
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, ancho, alto)
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(img, 0, 0, ancho, alto)
  return new Promise((resolver, rechazar) => {
    canvas.toBlob(b => (b ? resolver(b) : rechazar(new Error('No se pudo comprimir la imagen'))), 'image/jpeg', calidad)
  })
}

export type ImagenLista = { grande: Blob; mini: Blob; vista: string; nombre: string }

/** La imagen lista para subir: la grande y la miniatura, en JPEG. */
export async function prepararImagen(archivo: File): Promise<ImagenLista> {
  if (!archivo.type.startsWith('image/')) throw new Error(`«${archivo.name}» no es una imagen`)
  const img = await cargar(archivo)
  const [grande, mini] = await Promise.all([aJpeg(img, LADO_MAYOR, CALIDAD), aJpeg(img, LADO_MINIATURA, 0.75)])
  if (grande.size > MAX_BYTES_IMAGEN) throw new Error(`«${archivo.name}» sigue pesando demasiado después de achicarla`)
  return { grande, mini, vista: URL.createObjectURL(mini), nombre: archivo.name }
}
