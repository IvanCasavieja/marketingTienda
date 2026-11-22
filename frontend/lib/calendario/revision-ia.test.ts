/**
 * Pruebas de cómo se muestra lo que encontró la IA en una pieza. Se corren
 * con las demás:
 *
 *     npm run test:calendario
 */
import {
  VEREDICTO_IA, archivoDe, cambiosPorMarca, marcaDesdeObservacion, ordenarObservaciones, puntosParaMostrar,
  textoConArchivo, textoRevisados, tieneLugar, tituloRevisionIA,
  type CambioPedidoIA, type ObservacionIA, type PuntosPedidosIA, type RevisionIA,
} from './revision-ia'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

function obs(id: string, extra: Partial<ObservacionIA> = {}): ObservacionIA {
  return {
    id, tipo: 'ortografia', texto: `texto ${id}`, gravedad: 'importante', imagenId: 'im-1', x: 0.3, y: 0.1,
    estado: 'nueva', numero: null, por: null, porNombre: null, ...extra,
  }
}

console.log('revision-ia')
igual('el título cuenta lo que encontró', [
  tituloRevisionIA([]), tituloRevisionIA([obs('a')]), tituloRevisionIA([obs('a'), obs('b'), obs('c')]),
], ['La IA no encontró nada para marcar', 'La IA encontró 1 cosa para mirar', 'La IA encontró 3 cosas para mirar'])

igual('abiertas primero (las importantes antes), después las marcas y al final las descartadas',
  ordenarObservaciones([
    obs('descartada', { estado: 'descartada' }),
    obs('dudosa', { gravedad: 'a_revisar' }),
    obs('marca', { estado: 'marca', numero: 2 }),
    obs('importante1'),
    obs('importante2'),
  ]).map(o => o.id),
  ['importante1', 'importante2', 'dudosa', 'marca', 'descartada'])

const imagenes = [{ id: 'im-1' }, { id: 'im-2' }]
ok('con imagen de la versión y punto, tiene lugar', tieneLugar(obs('a'), imagenes))
ok('sin punto no tiene lugar', !tieneLugar(obs('a', { x: null, y: null }), imagenes))
ok('con una imagen que no es de esta versión no tiene lugar', !tieneLugar(obs('a', { imagenId: 'im-9' }), imagenes))

igual('la marca va donde dijo la IA, con su texto',
  marcaDesdeObservacion(obs('a', { imagenId: 'im-2', x: 0.25, y: 0.75 }), imagenes, 'im-1'),
  { imagenId: 'im-2', x: 0.25, y: 0.75, texto: 'texto a' })
igual('sin lugar, va al medio de su imagen',
  marcaDesdeObservacion(obs('a', { imagenId: 'im-2', x: null, y: null }), imagenes, 'im-1'),
  { imagenId: 'im-2', x: 0.5, y: 0.5, texto: 'texto a' })
igual('sin imagen, al medio de la que se está mirando',
  marcaDesdeObservacion(obs('a', { imagenId: null, x: null, y: null }), imagenes, 'im-2'),
  { imagenId: 'im-2', x: 0.5, y: 0.5, texto: 'texto a' })

// Lo del ZIP y el link (19/11/2026).
const delZip = obs('z', { imagenId: null, x: null, y: null, archivo: 'piezas/feed.jpg', origen: 'zip', pagina: null })
const delPdf = obs('p', { imagenId: null, x: null, y: null, archivo: 'folleto.pdf', origen: 'link', pagina: 2 })
igual('el archivo de lo que vino en el ZIP o el link', [archivoDe(delZip), archivoDe(delPdf), archivoDe(obs('a'))],
  ['«piezas/feed.jpg»', '«folleto.pdf», página 2', null])
igual('una observación de antes (sin archivo) no cambia', textoConArchivo(obs('a')), 'texto a')
igual('la marca de un archivo del ZIP dice cuál es, al medio de la que se mira',
  marcaDesdeObservacion(delPdf, imagenes, 'im-1'),
  { imagenId: 'im-1', x: 0.5, y: 0.5, texto: 'En «folleto.pdf», página 2: texto p' })
igual('lo que miró además, en una línea', [
  textoRevisados([{ nombre: 'a.jpg', origen: 'zip', paginas: null }]),
  textoRevisados([{ nombre: 'a.jpg', origen: 'zip', paginas: null }, { nombre: 'b.pdf', origen: 'zip', paginas: 3 }]),
  textoRevisados(['1', '2', '3', '4', '5', '6'].map(n => ({ nombre: `${n}.jpg`, origen: 'zip' as const, paginas: null }))),
], ['«a.jpg»', '«a.jpg» y «b.pdf» (3 páginas)', '«1.jpg», «2.jpg», «3.jpg», «4.jpg» y 2 más'])

// Lo que dice la IA de cada marca de la ronda anterior (19/11/2026).
const hecho: CambioPedidoIA = { marcaId: 'mk-1', numero: 1, veredicto: 'hecho', nota: 'El -40% ahora es más grande.' }
const falta: CambioPedidoIA = { marcaId: 'mk-2', numero: 2, veredicto: 'falta', nota: 'Sigue diciendo «Valido», sin tilde.' }
const lista = (cambiosPedidos?: unknown[]): RevisionIA =>
  ({ estado: 'lista', observaciones: [], cambiosPedidos: cambiosPedidos as CambioPedidoIA[] | undefined })
igual('lo de cada marca, por su id', [...cambiosPorMarca(lista([hecho, falta])).entries()],
  [['mk-1', hecho], ['mk-2', falta]])
igual('lo que dice, como se ve al lado de la marca', [VEREDICTO_IA.hecho, VEREDICTO_IA.falta, VEREDICTO_IA.dudoso],
  ['IA: hecho', 'IA: falta', 'IA: dudoso'])
ok('mientras la IA mira, nada', cambiosPorMarca({ estado: 'pendiente', observaciones: [], cambiosPedidos: [hecho] }).size === 0)
ok('si no se pudo revisar, nada', cambiosPorMarca({ estado: 'nada', observaciones: [] }).size === 0)
ok('sin revisión, nada', cambiosPorMarca(null).size === 0 && cambiosPorMarca(undefined).size === 0)
ok('una revisión de antes (sin la lista), nada', cambiosPorMarca(lista()).size === 0)
igual('lo que no tiene la forma esperada no se muestra, y una marca repetida vale la primera',
  [...cambiosPorMarca(lista([
    null, { marcaId: 'mk-1', numero: 1, veredicto: 'corregido', nota: '' }, { numero: 3, veredicto: 'hecho', nota: '' },
    { marcaId: 'toString', numero: 4, veredicto: 'constructor', nota: '' }, falta,
    { ...falta, veredicto: 'hecho' },
  ])).entries()],
  [['mk-2', falta]])

// Sin observaciones, pero con «IA: falta» al lado de una marca de la ronda
// anterior: el título no puede decir «no encontró nada» (revisión del
// 19/11/2026). Como en el panel: cuenta lo que se muestra al lado de las marcas.
const conCambios = (r: RevisionIA) => cambiosPorMarca(r).size > 0
igual('con lo de la ronda anterior, sin observaciones dice que no hay nada nuevo', [
  tituloRevisionIA([], conCambios(lista([falta]))),
  tituloRevisionIA([], conCambios(lista([]))),
  tituloRevisionIA([], conCambios(lista())),
  tituloRevisionIA([obs('a')], conCambios(lista([falta]))),
], [
  'La IA no encontró nada nuevo para marcar', 'La IA no encontró nada para marcar',
  'La IA no encontró nada para marcar', 'La IA encontró 1 cosa para mirar',
])

// Lo que se pidió sin marcas (21/11/2026, la prueba de Ivan con Publicis): el
// pedido inicial o lo escrito en el comentario, como lo vio la agencia.
const cta = { numero: 1, texto: 'CTA: Ver ofertas', veredicto: 'falta' as const, nota: 'En las dos piezas el botón dice «Ver oferta».' }
const menu = { numero: 2, texto: 'En el banner menú quiero CTA ver más', veredicto: 'dudoso' as const, nota: 'No se ve ningún banner de menú.' }
const fondo = { numero: 3, texto: 'Fondo rojo', veredicto: 'hecho' as const, nota: 'Se ve rojo.' }
const conPuntos = (puntosPedidos: unknown, estado: RevisionIA['estado'] = 'lista'): RevisionIA =>
  ({ estado, observaciones: [], puntosPedidos: puntosPedidos as PuntosPedidosIA | null })
igual('los puntos del pedido inicial, lo que falta primero y lo hecho al final',
  puntosParaMostrar(conPuntos({ inicial: true, puntos: [fondo, menu, cta] })), { inicial: true, puntos: [cta, menu, fondo] })
igual('los del comentario no son del pedido inicial',
  puntosParaMostrar(conPuntos({ inicial: false, puntos: [cta] })), { inicial: false, puntos: [cta] })
igual('mientras la IA mira, o si no se pudo, nada', [
  puntosParaMostrar(conPuntos({ inicial: true, puntos: [cta] }, 'pendiente')),
  puntosParaMostrar(conPuntos({ inicial: true, puntos: [cta] }, 'nada')),
], [null, null])
igual('sin puntos (se controlaron marcas), de antes o sin revisión: nada', [
  puntosParaMostrar(conPuntos(null)), puntosParaMostrar(conPuntos(undefined)), puntosParaMostrar(lista([falta])),
  puntosParaMostrar(null), puntosParaMostrar(conPuntos({ inicial: true, puntos: [] })),
  puntosParaMostrar(conPuntos({ inicial: true, puntos: 'raro' })),
], [null, null, null, null, null, null])
igual('lo que no tiene la forma esperada no se muestra', puntosParaMostrar(conPuntos({ inicial: true, puntos: [
  null, { ...cta, veredicto: 'no_aplica' }, { ...cta, veredicto: 'toString' }, { ...cta, texto: '  ' }, { ...cta, numero: '1' },
  { ...cta, nota: null }, menu,
] })), { inicial: true, puntos: [menu] })
// Con los puntos, el título del panel tampoco dice «no encontró nada».
igual('con puntos y sin observaciones, «nada nuevo»',
  tituloRevisionIA([], puntosParaMostrar(conPuntos({ inicial: true, puntos: [cta] })) != null),
  'La IA no encontró nada nuevo para marcar')

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\nrevision-ia: todo bien')
