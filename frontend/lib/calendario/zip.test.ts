/**
 * Pruebas del lector de ZIP del formulario de entrega. Se corren con las
 * demás:
 *
 *     npm run test:calendario
 */
import * as zlib from 'zlib'
import {
  abrirEntrada, avisoZipSinGuardar, detalleDelZip, esBasura, leerIndiceZip, nombreCorto, pendientesDelZip, pesoLegible,
  tipoDeImagen, zipSumaImagenes, zipYaResueltas, ZipRaro, MAX_ARCHIVOS_ZIP, type EstadoDelZip,
} from './zip'

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

  // -------------------------------------------------------------------------
  // El ZIP en el formulario (19/11/2026): viaja siempre, el servidor lo guarda
  // tal cual y pasa a la ronda lo que acá no se pudo mostrar (las páginas de
  // los PDF). Un ZIP con solo el folleto en PDF alcanza para entregar.
  // -------------------------------------------------------------------------
  console.log('\nel ZIP en el formulario')
  const soloPdf = leerIndiceZip(armarZip([{ nombre: 'folleto.pdf', datos: bytes(1) }, { nombre: 'leeme.txt', datos: bytes(2) }]))
  const estado = (e: EstadoDelZip['entradas'], tomadas: number[] = [], sacadas: number[] = []): EstadoDelZip => ({ entradas: e, tomadas, sacadas })

  igual('un ZIP con solo un PDF: el servidor saca sus páginas', pendientesDelZip(estado(soloPdf)), { imagenes: 0, pdfs: 1 })
  ok('y alcanza para entregar si queda lugar en la ronda', zipSumaImagenes(estado(soloPdf), 4))
  ok('sin lugar en la ronda, no suma nada', !zipSumaImagenes(estado(soloPdf), 0))
  // Con su máximo: entran las páginas que caben en los lugares libres, no el folleto entero.
  igual('lo que se dice debajo del nombre', detalleDelZip(estado(soloPdf), 5 * 1024 * 1024, false, 4),
    '5 MB · se agregan hasta 4 páginas o imágenes del ZIP al entregar')
  igual('con dos lugares, hasta dos', detalleDelZip(estado(soloPdf), 5 * 1024 * 1024, false, 2),
    '5 MB · se agregan hasta 2 páginas o imágenes del ZIP al entregar')
  igual('sin lugar no se promete nada: queda para revisar', detalleDelZip(estado(soloPdf), 5 * 1024 * 1024, false, 0),
    '5 MB · 1 archivo más para revisar')
  igual('mientras se abre', detalleDelZip(estado(soloPdf), 5 * 1024 * 1024, true, 4), '5 MB · abriéndolo…')

  // piezas/feed.jpg (1), piezas/story.png (2), folleto.pdf (4), fuente.psd (5), ñandú.webp (6), Caña.jpg (7).
  igual('se tomaron tres, Caña.jpg no se pudo sacar acá: con un lugar, el servidor pone la página del PDF (va antes en el ZIP)',
    detalleDelZip(estado(entradas, [1, 2, 6]), 12.34 * 1024 * 1024, false, 1),
    '12,3 MB · se tomaron 3 imágenes de adentro · se agrega 1 página o imagen del ZIP al entregar')
  igual('lo que queda: la que no se pudo sacar y el PDF', pendientesDelZip(estado(entradas, [1, 2, 6])), { imagenes: 1, pdfs: 1 })
  igual('sin lugar, lo demás queda para revisar', detalleDelZip(estado(entradas, [1, 2, 6, 7]), 300 * 1024, false, 0),
    '300 KB · se tomaron 4 imágenes de adentro · 1 archivo más para revisar')
  const soloImagenes = leerIndiceZip(armarZip([{ nombre: 'a.jpg', datos: bytes(1) }, { nombre: 'b.jpg', datos: bytes(1) }]))
  igual('imágenes que el navegador no pudo abrir: las agrega el servidor (sin PDF, como mucho las que quedan)',
    detalleDelZip(estado(soloImagenes), 2048, false, 4), '2 KB · se agregan hasta 2 páginas o imágenes del ZIP al entregar')
  igual('...y si ya se tomó alguna, la que queda',
    detalleDelZip(estado(soloImagenes, [0]), 2048, false, 3), '2 KB · se tomó 1 imagen de adentro · se agrega 1 página o imagen del ZIP al entregar')
  igual('un ZIP que acá no se lee lo abre el servidor: hasta los lugares libres',
    detalleDelZip(estado(null), 1024 * 1024, false, 4), '1 MB · se agregan hasta 4 páginas o imágenes del ZIP al entregar')
  ok('...y puede alcanzar para entregar (si no sale nada, avisa el servidor)', zipSumaImagenes(estado(null), 4))

  // Lo que la persona saca de la ronda no vuelve, y no se mira dos veces.
  ok('si sacó las dos imágenes del ZIP, no queda nada para ver', !zipSumaImagenes(estado(soloImagenes, [], [0, 1]), 4))
  igual('lo resuelto acá va al servidor: las tomadas y las sacadas, sin repetir',
    zipYaResueltas(estado(entradas, [6, 1], [2, 1])), [1, 2, 6])
  const conClave = leerIndiceZip(armarZip([{ nombre: 'secreto.jpg', datos: bytes(1) }])).map(e => ({ ...e, cifrado: true }))
  ok('una imagen con contraseña no cuenta (allá tampoco se abre)', !zipSumaImagenes(estado(conClave), 4))

  igual('el peso, para leer', [12.34, 12, 1].map(n => pesoLegible(n * 1024 * 1024)).concat(pesoLegible(350 * 1024), pesoLegible(10)),
    ['12,3 MB', '12 MB', '1 MB', '350 KB', '1 KB'])

  // Sin lugar (el tope de los ZIP o la base) el ZIP no se guarda (la entrega queda igual): qué hacer.
  igual('sin guardar, con el link', avisoZipSinGuardar(true, false),
    'El ZIP no se guardó porque no había lugar en la base: el original queda en el link.')
  igual('sin guardar, al equipo', avisoZipSinGuardar(false, false),
    'El ZIP no se guardó porque no había lugar en la base: pedile el link a quien la hace.')
  igual('sin guardar, a quien la hizo', avisoZipSinGuardar(false, true),
    'El ZIP no se guardó porque no había lugar en la base: pasá el link al original en los comentarios.')

  if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
  console.log('\nzip: todo bien')
}

main().catch(e => { console.error(e); process.exit(1) })
