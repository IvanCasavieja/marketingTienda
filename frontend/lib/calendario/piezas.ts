// ---------------------------------------------------------------------------
// Las piezas del pedido que faltan en una entrega (21/11/2026).
//
// Ivan: "la IA a veces encuentra un problema y a veces no. Si yo pido 4
// banners y me pasan uno, puede ser que lo primero que estén haciendo sea
// pasarme un KV para que yo apruebe, pero cuando son todos los banners ahí es
// donde tiene que analizar y decir 'che, pará, acá faltan también los banners
// X o Y'. Y quizás estaría bueno que le des el espacio a la agencia ahí de
// escribir por qué no los manda."
//
// Que falte una pieza lo dice la plataforma sola, sin la IA, y siempre igual:
// el servidor manda lo pedido, una pieza por medida (tarea.piezas, ver
// piezas_del_pedido en backend/app/services/tipos_de_tarea.py), y acá se lo
// compara con las medidas ORIGINALES de lo que se entrega: las imágenes
// sueltas (antes de achicarlas a 1600) y las del ZIP, todas, también las que
// no entran en las 4 de la ronda (su tamaño se lee del encabezado, sin abrir
// la imagen entera: medidasDeImagen). Las páginas de un PDF no cuentan.
//
// Si falta algo, el formulario de entrega lo avisa antes de mandar (con lo
// que vea la IA, si vio algo) y deja escribir por qué; lo que falta y el
// porqué viajan con la ronda y los ven quien aprueba y la agencia. Cómo se
// muestra, abajo (los chips, desde el 21/11/2026).
//
// Este archivo es puro (sin React ni '@/') a propósito: se prueba con
// piezas.test.ts.
// ---------------------------------------------------------------------------

/** Una pieza del pedido. `proporcion`: de esa pieza importa solo la
 *  proporción (redes: 4:5), y `ancho`/`alto` son esa proporción. */
export type Pieza = { nombre: string; ancho: number; alto: number; proporcion: boolean }

/** El tamaño de una imagen, en px. */
export type Medidas = { ancho: number; alto: number }

/** Cuánto puede variar la proporción de una imagen para cubrir una pieza: 2 %. */
export const TOLERANCIA_PROPORCION = 0.02

/** «Header (mobile) 640×260»; las de proporción, solo el nombre: «Redes 4:5». */
export function textoDePieza(p: Pieza): string {
  return p.proporcion ? p.nombre : `${p.nombre} ${p.ancho}×${p.alto}`
}

/** Si una imagen sirve para esa pieza: la misma proporción (±2 %) y no más
 *  chica que la medida pedida (una @2x vale). De las de proporción, solo la
 *  proporción. Pura. */
export function cubre(imagen: Medidas, pieza: Pieza): boolean {
  if (!(imagen.ancho > 0 && imagen.alto > 0 && pieza.ancho > 0 && pieza.alto > 0)) return false
  const relacion = (imagen.ancho / imagen.alto) / (pieza.ancho / pieza.alto)
  if (Math.abs(relacion - 1) > TOLERANCIA_PROPORCION) return false
  return pieza.proporcion || (imagen.ancho >= pieza.ancho && imagen.alto >= pieza.alto)
}

/**
 * Las piezas del pedido que no cubre ninguna imagen, en el orden del pedido.
 * Cada imagen cubre una sola pieza: dos piezas iguales (Foto receta y Foto
 * producto, las dos de 1200×900) piden dos imágenes. Se reparten de la mejor
 * manera posible (el emparejamiento más grande, con caminos de aumento): una
 * imagen grande que sirve para dos piezas se deja para la que la otra imagen
 * no alcanza. Si dos piezas se disputan la misma imagen, se la queda la que
 * está más arriba en el pedido. Pura.
 */
export function piezasQueFaltan(piezas: readonly Pieza[], imagenes: readonly Medidas[]): Pieza[] {
  // Para cada imagen, a qué pieza quedó asignada (-1: a ninguna).
  const de = imagenes.map(() => -1)
  const sirve = piezas.map(p => imagenes.map(im => cubre(im, p)))
  const asignar = (p: number, vistas: boolean[]): boolean => {
    for (let i = 0; i < imagenes.length; i++) {
      if (vistas[i] || !sirve[p][i]) continue
      vistas[i] = true
      if (de[i] === -1 || asignar(de[i], vistas)) {
        de[i] = p
        return true
      }
    }
    return false
  }
  return piezas.filter((_, p) => !asignar(p, imagenes.map(() => false)))
}

/**
 * Lo que falta en una entrega, si se puede saber. `imagenes`: las medidas de
 * todo lo que se entrega, null en una que no se pudo medir; null entero si
 * no se puede saber qué hay (un ZIP que acá no se lee). Sin imágenes (solo
 * un link, o un ZIP con solo PDF) o con alguna sin medir no se dice nada:
 * la plataforma avisa solo lo que puede ver, para no decir que falta algo
 * que capaz está. Pura.
 */
export function faltanEnLaEntrega(
  piezas: readonly Pieza[] | null | undefined, imagenes: readonly (Medidas | null)[] | null,
): Pieza[] {
  if (!piezas?.length || !imagenes?.length || imagenes.some(m => m == null)) return []
  return piezasQueFaltan(piezas, imagenes as Medidas[])
}

// ---------------------------------------------------------------------------
// Cómo se muestra (21/11/2026)
// ---------------------------------------------------------------------------
// Ivan: "las correcciones de la IA están súper mezcladas, no tiene un formato
// bonito de ver ni nada". Antes, lo que faltaba iba en un renglón con todas
// las piezas seguidas por comas («Faltan estas piezas del pedido: Header
// (web) 1920×416, Slider fila (normal) (mobile) 640×260, …»), que con diez
// piezas era un párrafo y en la ficha se salía de la pantalla. Ahora cada
// pieza es un chip: en el aviso antes de mandar, con el nombre arriba y la
// medida abajo; en la ficha y al revisar, solo el nombre (es lo que viaja con
// la ronda). Si son muchas, se ven las primeras.

/** La medida de una pieza, abajo de su nombre en el aviso: «1920×416». De las
 *  de proporción importa solo eso, y ya está en el nombre («Redes 4:5»):
 *  «cualquier tamaño». Pura. */
export function medidaDePieza(p: Pieza): string {
  return p.proporcion ? 'cualquier tamaño' : `${p.ancho}×${p.alto}`
}

/** Cuántas piezas se ven de entrada (Ivan: "si son más de 6, se ven 6 y «Ver
 *  las otras 4»"). */
export const PIEZAS_A_LA_VISTA = 6

/**
 * Las primeras de una lista larga y cuántas quedan para «Ver las otras N».
 * Se corta solo si quedan afuera al menos dos: un botón para mostrar una sola
 * ocupa lo mismo que mostrarla, así que con 7 se ven las 7. Pura.
 */
export function primeras<T>(lista: readonly T[], tope = PIEZAS_A_LA_VISTA): { vistas: T[]; resto: number } {
  if (lista.length <= tope + 1) return { vistas: [...lista], resto: 0 }
  return { vistas: lista.slice(0, tope), resto: lista.length - tope }
}

/** El subtítulo de las piezas en el aviso antes de mandar: «Piezas que
 *  faltan», y al lado, en gris, la cantidad. Pura. */
export function tituloDeLasPiezas(faltan: readonly Pieza[]): string {
  return faltan.length === 1 ? 'Pieza que falta' : 'Piezas que faltan'
}

/** Lo que faltaba en una ronda, en su ficha y al revisarla. */
export type LoQueFaltaba = {
  /** «Faltan 10 piezas del pedido». */
  titulo: string
  /** Los nombres, como viajaron con la ronda («Header (web)»). */
  piezas: string[]
  /** Quién lo dice: «La agencia» o, si la hace alguien de Tienda, su nombre. */
  quien: string
  /** Por qué no iba todo, como lo escribió (null si no escribió nada). */
  porQue: string | null
}

/** Lo que faltaba en una ronda: el título con la cantidad, las piezas y, en
 *  otro renglón, por qué («La agencia dice: «Es el KV, para aprobarlo
 *  antes»»). `quien`: quién la entregó. Null si no faltaba nada (o es una
 *  ronda de antes del 21/11/2026). Pura. */
export function loQueFaltaba(
  faltan: readonly string[] | null | undefined, porQue: string | null | undefined, quien = 'La agencia',
): LoQueFaltaba | null {
  if (!faltan?.length) return null
  const n = faltan.length
  return {
    titulo: `${n === 1 ? 'Falta 1 pieza' : `Faltan ${n} piezas`} del pedido`,
    piezas: [...faltan],
    quien,
    porQue: (porQue ?? '').trim() || null,
  }
}

// ---------------------------------------------------------------------------
// El tamaño de una imagen, del encabezado (JPG, PNG y WebP)
// ---------------------------------------------------------------------------
// Para las imágenes del ZIP que no se abren enteras (las que no entran en las
// 4 de la ronda): alcanza con los primeros bytes. 'faltan-bytes': lo que hay
// se corta antes de llegar al tamaño (hay que leer más); null: no es una
// imagen que se entienda.

const u16be = (b: Uint8Array, i: number) => (b[i] << 8) | b[i + 1]
const u32be = (b: Uint8Array, i: number) => ((b[i] << 24) >>> 0) + (b[i + 1] << 16) + (b[i + 2] << 8) + b[i + 3]
const u16le = (b: Uint8Array, i: number) => b[i] | (b[i + 1] << 8)
const u24le = (b: Uint8Array, i: number) => b[i] | (b[i + 1] << 8) | (b[i + 2] << 16)
const ascii = (b: Uint8Array, i: number, n: number) => String.fromCharCode(...Array.from(b.subarray(i, i + n)))

/** Si los primeros bytes son los de `firma` (lo que hay alcanza para comparar). */
function empiezaCon(b: Uint8Array, firma: readonly number[]): boolean {
  return firma.every((x, i) => i >= b.length || b[i] === x)
}

const FIRMA_PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]

/** El ancho y el alto de una imagen JPG, PNG o WebP, leyendo solo su
 *  encabezado. En un JPG se mira además la orientación de la foto (EXIF):
 *  si va de costado, ancho y alto se dan vuelta, como la muestra el
 *  navegador. Pura. */
export function medidasDeImagen(b: Uint8Array): Medidas | 'faltan-bytes' | null {
  if (b.length < 2) return 'faltan-bytes'
  if (b[0] === 0xff && b[1] === 0xd8) return medidasDeJpeg(b)
  if (empiezaCon(b, FIRMA_PNG)) {
    if (b.length < 24) return 'faltan-bytes'
    if (ascii(b, 12, 4) !== 'IHDR') return null
    return medidasValidas(u32be(b, 16), u32be(b, 20))
  }
  if (empiezaCon(b, [0x52, 0x49, 0x46, 0x46])) return medidasDeWebp(b)
  return null
}

function medidasValidas(ancho: number, alto: number): Medidas | null {
  return ancho > 0 && alto > 0 ? { ancho, alto } : null
}

function medidasDeWebp(b: Uint8Array): Medidas | 'faltan-bytes' | null {
  if (b.length < 30) return 'faltan-bytes'
  if (ascii(b, 8, 4) !== 'WEBP') return null
  const trozo = ascii(b, 12, 4)
  if (trozo === 'VP8 ') {
    // Con pérdida: después de la marca 9d 01 2a, 14 bits de ancho y 14 de alto.
    if (b[23] !== 0x9d || b[24] !== 0x01 || b[25] !== 0x2a) return null
    return medidasValidas(u16le(b, 26) & 0x3fff, u16le(b, 28) & 0x3fff)
  }
  if (trozo === 'VP8L') {
    // Sin pérdida: la firma 0x2f y, en 28 bits, ancho-1 y alto-1.
    if (b[20] !== 0x2f) return null
    const bits = (b[21] | (b[22] << 8) | (b[23] << 16) | (b[24] << 24)) >>> 0
    return medidasValidas((bits & 0x3fff) + 1, ((bits >>> 14) & 0x3fff) + 1)
  }
  if (trozo === 'VP8X') {
    // Extendido (con transparencia o animación): el lienzo, ancho-1 y alto-1 en 24 bits.
    return medidasValidas(u24le(b, 24) + 1, u24le(b, 27) + 1)
  }
  return null
}

// Los SOF del JPG (donde está el tamaño): C0 a CF, menos C4 (DHT), C8 y CC (DAC).
const ES_SOF = (m: number) => m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc

function medidasDeJpeg(b: Uint8Array): Medidas | 'faltan-bytes' | null {
  let girada = false
  let i = 2
  for (;;) {
    if (i + 4 > b.length) return 'faltan-bytes'
    if (b[i] !== 0xff) return null
    const marca = b[i + 1]
    // Bytes de relleno (0xFF de más) y marcas sin largo.
    if (marca === 0xff) { i += 1; continue }
    if ((marca >= 0xd0 && marca <= 0xd7) || marca === 0x01) { i += 2; continue }
    // Fin de la imagen, o empiezan los datos, sin haber dicho el tamaño.
    if (marca === 0xd9 || marca === 0xda) return null
    const largo = u16be(b, i + 2)
    if (largo < 2) return null
    if (ES_SOF(marca)) {
      if (i + 9 > b.length) return 'faltan-bytes'
      const alto = u16be(b, i + 5)
      const ancho = u16be(b, i + 7)
      return girada ? medidasValidas(alto, ancho) : medidasValidas(ancho, alto)
    }
    if (marca === 0xe1) {
      if (i + 2 + largo > b.length) return 'faltan-bytes'
      girada = vaDeCostado(b.subarray(i + 4, i + 2 + largo)) || girada
    }
    i += 2 + largo
  }
}

/** Si el EXIF de un JPG dice que la foto va de costado (orientación 5 a 8:
 *  el navegador la muestra con el ancho y el alto dados vuelta). */
function vaDeCostado(app1: Uint8Array): boolean {
  if (app1.length < 14 || ascii(app1, 0, 6) !== 'Exif\0\0') return false
  const t = app1.subarray(6)
  const chica = ascii(t, 0, 2) === 'II'
  if (!chica && ascii(t, 0, 2) !== 'MM') return false
  const u16 = (i: number) => (chica ? u16le(t, i) : u16be(t, i))
  const u32 = (i: number) => (chica ? ((t[i] | (t[i + 1] << 8) | (t[i + 2] << 16) | (t[i + 3] << 24)) >>> 0) : u32be(t, i))
  if (u16(2) !== 42) return false
  const ifd = u32(4)
  if (ifd + 2 > t.length) return false
  const n = u16(ifd)
  for (let k = 0; k < n; k++) {
    const e = ifd + 2 + k * 12
    if (e + 12 > t.length) return false
    // 0x0112: la orientación (un SHORT, en los primeros dos bytes del valor).
    if (u16(e) === 0x0112) return u16(e + 8) >= 5 && u16(e + 8) <= 8
  }
  return false
}
