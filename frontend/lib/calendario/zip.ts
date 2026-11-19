// ---------------------------------------------------------------------------
// La carpeta comprimida (ZIP) que entrega la agencia (19/11/2026).
//
// Ivan: "Normalmente nos pasan link de WeTransfer o link de Smash o una
// carpeta comprimida directamente". Al elegir el ZIP en el formulario de
// entrega se leen acá, en el navegador, las imágenes de adentro (las
// primeras, hasta el tope de la ronda): quedan como las imágenes de la ronda,
// para que quien aprueba las vea y las marque como siempre. El ZIP entero
// viaja igual al servidor, que no lo guarda: la IA revisa lo que no entró
// (las otras imágenes y los PDF), y se le dice qué archivos ya van como
// imágenes para que no los mire dos veces (por su lugar en el índice, que es
// el mismo que ve el servidor con zipfile.infolist()).
//
// Sin librerías: el índice del ZIP se lee a mano y lo comprimido se abre con
// DecompressionStream('deflate-raw'), que traen los navegadores y Node. Si el
// navegador no lo trae, o el ZIP es raro (ZIP64, cifrado), no se toma ninguna
// imagen y el ZIP va igual.
//
// Los frenos son los mismos del servidor (backend/app/services/materiales.py),
// para avisar antes de subir 40 MB que después se rechazan.
// ---------------------------------------------------------------------------

export const MAX_ARCHIVOS_ZIP = 60
export const MAX_BYTES_DESCOMPRIMIDO = 200 * 1024 * 1024
/** Lo que se abre de cada imagen de adentro (el índice puede mentir). */
export const MAX_BYTES_ENTRADA = 40 * 1024 * 1024
const EXTENSIONES_IMAGEN = ['.jpg', '.jpeg', '.png', '.webp']

export type ClaseZip = 'imagen' | 'pdf' | 'otro'

export type EntradaZip = {
  /** Su lugar en el índice del ZIP, contando todo (también carpetas y basura). */
  indice: number
  /** La ruta adentro del ZIP, con «/». */
  nombre: string
  clase: ClaseZip
  metodo: number
  comprimido: number
  tamano: number
  /** Dónde empieza su encabezado local. */
  desde: number
  cifrado: boolean
}

/** El ZIP no se puede leer acá (ZIP64): no es un error para la persona, el ZIP va igual. */
export class ZipRaro extends Error {}

// Los nombres sin la marca de UTF-8 vienen en la página de códigos de DOS
// (en Windows en castellano, la 850). Solo hacen falta las letras nuestras:
// el resto queda como «_». Es para mostrar; el servidor los lee por su cuenta.
const CP850: Record<number, string> = {
  0x81: 'ü', 0x82: 'é', 0x90: 'É', 0x9a: 'Ü', 0xa0: 'á', 0xa1: 'í', 0xa2: 'ó', 0xa3: 'ú', 0xa4: 'ñ', 0xa5: 'Ñ',
  0xa6: 'ª', 0xa7: 'º', 0xa8: '¿', 0xad: '¡', 0xb5: 'Á', 0xd6: 'Í', 0xe0: 'Ó', 0xe9: 'Ú',
}

function decodificarNombre(bytes: Uint8Array, utf8: boolean): string {
  if (!utf8) {
    // Sin la marca, igual puede ser UTF-8 (lo hace macOS): se prueba primero.
    try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes) } catch { /* sigue abajo */ }
    return Array.from(bytes, b => (b < 0x80 ? String.fromCharCode(b) : CP850[b] ?? '_')).join('')
  }
  return new TextDecoder('utf-8').decode(bytes)
}

function claseDe(nombre: string): ClaseZip {
  const bajo = nombre.toLowerCase()
  if (EXTENSIONES_IMAGEN.some(e => bajo.endsWith(e))) return 'imagen'
  if (bajo.endsWith('.pdf')) return 'pdf'
  return 'otro'
}

/** Lo que agregan macOS y Windows solos: no se lista ni se cuenta. */
export function esBasura(nombre: string): boolean {
  const base = nombre.split('/').pop() ?? ''
  return nombre.toLowerCase().startsWith('__macosx/') || base.startsWith('._')
    || ['.ds_store', 'thumbs.db', 'desktop.ini'].includes(base.toLowerCase())
}

function rutaInsegura(nombre: string): boolean {
  return nombre.startsWith('/') || /^[a-z]:/i.test(nombre) || nombre.split('/').includes('..')
}

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`

/**
 * El índice del ZIP: las entradas que importan (sin carpetas ni basura del
 * sistema), en su orden. Error con el mensaje para la persona si el ZIP no
 * sirve (los mismos frenos que el servidor); ZipRaro si no se puede leer acá.
 */
export function leerIndiceZip(buf: ArrayBuffer): EntradaZip[] {
  const v = new DataView(buf)
  // El final del índice: firma 0x06054b50, 22 bytes más un comentario de hasta 64 KB.
  let fin = -1
  for (let i = v.byteLength - 22; i >= Math.max(0, v.byteLength - 22 - 0xffff); i--) {
    if (v.getUint32(i, true) === 0x06054b50) { fin = i; break }
  }
  if (fin < 0) throw new Error('El archivo no es un ZIP (o está dañado)')
  const cantidad = v.getUint16(fin + 10, true)
  const desde = v.getUint32(fin + 16, true)
  if (cantidad === 0xffff || desde === 0xffffffff) throw new ZipRaro('ZIP64')
  const entradas: EntradaZip[] = []
  let total = 0
  let p = desde
  for (let indice = 0; indice < cantidad; indice++) {
    if (p + 46 > v.byteLength || v.getUint32(p, true) !== 0x02014b50) throw new Error('El archivo no es un ZIP (o está dañado)')
    const marcas = v.getUint16(p + 8, true)
    const metodo = v.getUint16(p + 10, true)
    const comprimido = v.getUint32(p + 20, true)
    const tamano = v.getUint32(p + 24, true)
    const largoNombre = v.getUint16(p + 28, true)
    const largoExtra = v.getUint16(p + 30, true)
    const largoComentario = v.getUint16(p + 32, true)
    const local = v.getUint32(p + 42, true)
    if (p + 46 + largoNombre > v.byteLength) throw new Error('El archivo no es un ZIP (o está dañado)')
    if (comprimido === 0xffffffff || tamano === 0xffffffff || local === 0xffffffff) throw new ZipRaro('ZIP64')
    const nombre = decodificarNombre(new Uint8Array(buf, p + 46, largoNombre), (marcas & 0x800) !== 0).replace(/\\/g, '/')
    p += 46 + largoNombre + largoExtra + largoComentario
    if (nombre.endsWith('/')) continue
    if (rutaInsegura(nombre)) throw new Error('El ZIP tiene rutas que no van (con «..» o absolutas): no se puede abrir')
    if (esBasura(nombre)) continue
    if (entradas.length >= MAX_ARCHIVOS_ZIP) throw new Error(`El ZIP tiene demasiados archivos adentro (máximo ${MAX_ARCHIVOS_ZIP})`)
    total += tamano
    if (total > MAX_BYTES_DESCOMPRIMIDO) throw new Error(`Descomprimido, el ZIP pasa de ${mb(MAX_BYTES_DESCOMPRIMIDO)}: es demasiado`)
    entradas.push({ indice, nombre, clase: claseDe(nombre), metodo, comprimido, tamano, desde: local, cifrado: (marcas & 1) !== 0 })
  }
  return entradas
}

/** Los bytes de un archivo de adentro, cortando en `tope` (una bomba zip miente en el índice). */
export async function abrirEntrada(buf: ArrayBuffer, e: EntradaZip, tope = MAX_BYTES_ENTRADA): Promise<Uint8Array<ArrayBuffer>> {
  if (e.cifrado) throw new Error(`«${e.nombre}» tiene contraseña`)
  const v = new DataView(buf)
  if (e.desde + 30 > v.byteLength || v.getUint32(e.desde, true) !== 0x04034b50) throw new Error(`«${e.nombre}» está dañado`)
  const inicio = e.desde + 30 + v.getUint16(e.desde + 26, true) + v.getUint16(e.desde + 28, true)
  if (inicio + e.comprimido > v.byteLength) throw new Error(`«${e.nombre}» está dañado`)
  const datos = new Uint8Array(buf, inicio, e.comprimido)
  if (e.metodo === 0) {
    if (datos.byteLength > tope) throw new Error(`«${e.nombre}» es demasiado grande`)
    return datos.slice()
  }
  if (e.metodo !== 8 || typeof DecompressionStream === 'undefined') throw new ZipRaro(`«${e.nombre}» no se puede abrir acá`)
  const lector = new Blob([datos]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader()
  const partes: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await lector.read()
    if (done) break
    total += value.byteLength
    if (total > tope) {
      await lector.cancel()
      throw new Error(`«${e.nombre}» es demasiado grande`)
    }
    partes.push(value)
  }
  const salida = new Uint8Array(total)
  let p = 0
  for (const parte of partes) { salida.set(parte, p); p += parte.byteLength }
  return salida
}

/** El tipo de imagen por la extensión, para armar el File que se achica. */
export function tipoDeImagen(nombre: string): string {
  const bajo = nombre.toLowerCase()
  if (bajo.endsWith('.png')) return 'image/png'
  if (bajo.endsWith('.webp')) return 'image/webp'
  return 'image/jpeg'
}

/** "piezas/feed.jpg" -> "feed.jpg". */
export function nombreCorto(nombre: string): string {
  return nombre.split('/').pop() || nombre
}
