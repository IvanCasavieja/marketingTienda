/**
 * Pruebas del lector de ZIP del formulario de entrega. Se corren con las
 * demás:
 *
 *     npm run test:calendario
 */
import * as zlib from 'zlib'
import { abrirEntrada, esBasura, leerIndiceZip, nombreCorto, tipoDeImagen, ZipRaro, MAX_ARCHIVOS_ZIP } from './zip'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}
async function falla(nombre: string, f: () => unknown, parte: string) {
  try {
    await f()
    ok(nombre, false, 'no falló')
  } catch (e) {
    const m = e instanceof Error ? e.message : String(e)
    ok(nombre, m.includes(parte), `dijo «${m}»`)
  }
}

type Archivo = { nombre: string | Uint8Array; datos?: Uint8Array; comprimir?: boolean; utf8?: boolean }

/** Un ZIP de verdad, armado a mano (sin CRC: el lector no lo mira). */
function armarZip(archivos: Archivo[]): ArrayBuffer {
  const locales: Buffer[] = []
  const centrales: Buffer[] = []
  let offset = 0
  for (const a of archivos) {
    const nombre = typeof a.nombre === 'string' ? Buffer.from(a.nombre, 'utf8') : Buffer.from(a.nombre)
    const crudo = Buffer.from(a.datos ?? new Uint8Array())
    const datos = a.comprimir ? zlib.deflateRawSync(crudo) : crudo
    const marcas = a.utf8 ? 0x800 : 0
    const metodo = a.comprimir ? 8 : 0
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(marcas, 6)
    local.writeUInt16LE(metodo, 8); local.writeUInt32LE(datos.length, 18); local.writeUInt32LE(crudo.length, 22)
    local.writeUInt16LE(nombre.length, 26)
    const central = Buffer.alloc(46)
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6)
    central.writeUInt16LE(marcas, 8); central.writeUInt16LE(metodo, 10); central.writeUInt32LE(datos.length, 20)
    central.writeUInt32LE(crudo.length, 24); central.writeUInt16LE(nombre.length, 28); central.writeUInt32LE(offset, 42)
    locales.push(local, nombre, datos)
    centrales.push(central, nombre)
    offset += local.length + nombre.length + datos.length
  }
  const indice = Buffer.concat(centrales)
  const fin = Buffer.alloc(22)
  fin.writeUInt32LE(0x06054b50, 0); fin.writeUInt16LE(archivos.length, 8); fin.writeUInt16LE(archivos.length, 10)
  fin.writeUInt32LE(indice.length, 12); fin.writeUInt32LE(offset, 16)
  const todo = Buffer.concat([...locales, indice, fin])
  return todo.buffer.slice(todo.byteOffset, todo.byteOffset + todo.length) as ArrayBuffer
}

const bytes = (...n: number[]) => new Uint8Array(n)
const muchasA = new Uint8Array(5000).fill(97)

async function main() {
  console.log('zip')
  const zip = armarZip([
    { nombre: 'piezas/' },
    { nombre: 'piezas/feed.jpg', datos: bytes(1, 2, 3) },
    { nombre: 'piezas/story.png', datos: muchasA, comprimir: true },
    { nombre: '__MACOSX/piezas/._feed.jpg', datos: bytes(9) },
    { nombre: 'piezas/folleto.pdf', datos: bytes(4) },
    { nombre: 'piezas/fuente.psd', datos: bytes(5) },
    { nombre: 'Diseño ñandú.webp', datos: bytes(6), utf8: true },
    // Windows en castellano, sin la marca de UTF-8: «Caña.jpg» en la 850.
    { nombre: bytes(0x43, 0x61, 0xa4, 0x61, 0x2e, 0x6a, 0x70, 0x67), datos: bytes(7) },
  ])
  const entradas = leerIndiceZip(zip)
  igual('sin carpetas ni basura, cada una con su lugar en el índice',
    entradas.map(e => [e.indice, e.nombre, e.clase]),
    [[1, 'piezas/feed.jpg', 'imagen'], [2, 'piezas/story.png', 'imagen'], [4, 'piezas/folleto.pdf', 'pdf'],
      [5, 'piezas/fuente.psd', 'otro'], [6, 'Diseño ñandú.webp', 'imagen'], [7, 'Caña.jpg', 'imagen']])

  igual('abre lo guardado sin comprimir', Array.from(await abrirEntrada(zip, entradas[0])), [1, 2, 3])
  const abierta = await abrirEntrada(zip, entradas[1])
  ok('abre lo comprimido', abierta.length === 5000 && abierta.every(b => b === 97))
  await falla('corta si se infla más que el tope', () => abrirEntrada(zip, entradas[1], 100), 'demasiado grande')

  await falla('no es un ZIP', () => leerIndiceZip(new Uint8Array(100).buffer), 'no es un ZIP')
  await falla('una ruta con «..» no va', () => leerIndiceZip(armarZip([{ nombre: '../afuera.jpg', datos: bytes(1) }])), 'rutas que no van')
  await falla('demasiados archivos',
    () => leerIndiceZip(armarZip(Array.from({ length: MAX_ARCHIVOS_ZIP + 1 }, (_, i) => ({ nombre: `p${i}.jpg`, datos: bytes(1) })))),
    'demasiados archivos')
  ok('la basura no cuenta para el tope de archivos',
    leerIndiceZip(armarZip([
      ...Array.from({ length: MAX_ARCHIVOS_ZIP }, (_, i) => ({ nombre: `p${i}.jpg`, datos: bytes(1) })),
      { nombre: '.DS_Store', datos: bytes(1) }, { nombre: 'Thumbs.db', datos: bytes(1) },
    ])).length === MAX_ARCHIVOS_ZIP)

  const cifrada = { ...entradas[0], cifrado: true }
  await falla('con contraseña no se abre', () => abrirEntrada(zip, cifrada), 'contraseña')
  const rara = { ...entradas[0], metodo: 12 }
  try { await abrirEntrada(zip, rara); ok('otra compresión: ZipRaro', false) } catch (e) { ok('otra compresión: ZipRaro', e instanceof ZipRaro) }

  ok('basura de macOS y Windows', esBasura('__MACOSX/x.jpg') && esBasura('a/._x.jpg') && esBasura('a/Thumbs.db') && !esBasura('a/x.jpg'))
  igual('el tipo por la extensión', ['a.PNG', 'b.webp', 'c.jpeg', 'd.jpg'].map(tipoDeImagen),
    ['image/png', 'image/webp', 'image/jpeg', 'image/jpeg'])
  igual('el nombre sin la carpeta', [nombreCorto('piezas/feed.jpg'), nombreCorto('feed.jpg')], ['feed.jpg', 'feed.jpg'])

  if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
  console.log('\nzip: todo bien')
}

main().catch(e => { console.error(e); process.exit(1) })
