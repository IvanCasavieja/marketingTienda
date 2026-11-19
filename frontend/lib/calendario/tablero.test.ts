/**
 * Pruebas del tablero de tarjetas (16/11/2026). Se corren con las demás:
 *
 *     npm run test:calendario
 *
 * Lo que decide el servidor (la columna, quién mueve qué) se prueba en
 * backend/tests/test_tablero_agencia*.py. Acá, lo de la pantalla: cómo se
 * dice la fecha, el orden de cada columna, el filtro por quién la hace y
 * dónde se puede soltar una tarjeta.
 */
import {
  COLUMNAS_DEL_TABLERO, avisoDeAgenciasSinCuentas, conservarArchivadas, deQuien, filtroVigente, grupoDeQuien,
  modoAlTocar, opcionesDeQuien, ordenar, pestanasDeTableros, queHaceMover, quienLaHaceTexto, rotuloDePieza,
  seMovioElDedo, sePuedeSoltar, tableroDeTarjeta, textoDeFecha,
} from './tablero'
import { diaEnUruguay } from './fechas'
import { etiquetaDecision, fechaDia, pasoEnLaVista, proximoPaso, type ResumenEntrega, type Tarjeta } from './entregas'
import { descripcionDelPedido, detalleSinPedido, linkValido, pedidoEnLista, type TipoDeTarea } from './tipos-de-tarea'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const base: Tarjeta = {
  tareaId: 'ta-1', titulo: 'Ciberlunes - Banners', estado: 'pendiente', columna: 'ingresado', volvioConCambios: false,
  vence: '2026-11-27', ancla: 'inicio', anclaDias: -3, asignadoA: null, responsable: null, turno: null,
  hace: { tipo: 'agencia', nombre: 'Agencia Pampa' },
  accion: { id: 'br-1', mundo: 'tienda_inglesa', nombre: 'Ciberlunes', color: null, desde: '2026-11-30', hasta: '2026-12-01' },
  entrega: { tipoPieza: 'otro', momento: 'produccion', ronda: 0, faseActual: null, aprobadorDeTurno: null, aprobadores: [], fases: [] },
  miniatura: null, puedo: { entregar: true, decidir: false, mover: ['en-proceso', 'esperando'] }, actualizada: null,
}
const t = (extra: Partial<Tarjeta>): Tarjeta => ({ ...base, ...extra })

console.log('tablero')
igual('las cinco columnas, en orden', COLUMNAS_DEL_TABLERO.map(c => c.titulo),
  ['Ingresado', 'En proceso', 'Esperando feedback', 'Finalizado', 'Archivado'])

igual('la fecha dice de dónde sale', textoDeFecha(base, '2026-11-16'),
  { texto: 'Para el 27/11 · 3 días antes del inicio de Ciberlunes', vencida: false })
igual('el día que arranca', textoDeFecha(t({ anclaDias: 0 }), '2026-11-16')?.texto, 'Para el 27/11 · el día que arranca Ciberlunes')
igual('un día después del fin', textoDeFecha(t({ ancla: 'fin', anclaDias: 1 }), '2026-11-16')?.texto,
  'Para el 27/11 · 1 día después del fin de Ciberlunes')
igual('una fecha fija no dice de dónde sale', textoDeFecha(t({ ancla: null, anclaDias: null }), '2026-11-16')?.texto, 'Para el 27/11')
ok('vencida si pasó y no está terminada', textoDeFecha(base, '2026-11-28')!.vencida)
ok('una finalizada no se marca vencida', !textoDeFecha(t({ columna: 'finalizado' }), '2026-11-28')!.vencida)
igual('sin fecha, nada', textoDeFecha(t({ vence: null }), '2026-11-16'), null)

igual('qué hace cada movimiento', [
  queHaceMover('ingresado', 'en-proceso'), queHaceMover('en-proceso', 'esperando'), queHaceMover('esperando', 'en-proceso'),
  queHaceMover('esperando', 'finalizado'), queHaceMover('finalizado', 'archivado'), queHaceMover('archivado', 'finalizado'),
], ['Arrancar', 'Entregar los materiales', 'Pedir cambios', 'Aprobar', 'Archivar', 'Sacar del archivo'])
// Libre, como Trello (18/11/2026): quien no entrega ni decide la mueve a mano.
const nada = { entregar: false, decidir: false }
igual('el equipo la mueve a mano', [
  queHaceMover('en-proceso', 'esperando', nada), queHaceMover('esperando', 'en-proceso', nada),
  queHaceMover('esperando', 'finalizado', nada), queHaceMover('en-proceso', 'finalizado', nada),
  queHaceMover('en-proceso', 'esperando', { entregar: true, decidir: false }),
], ['Moverla a mano, sin entregar', 'Volverla a mano, sin decidir', 'Darla por terminada', 'Darla por terminada', 'Entregar los materiales'])

ok('se suelta donde el servidor dice', sePuedeSoltar(base, 'en-proceso') && sePuedeSoltar(base, 'esperando'))
ok('no donde no puede', !sePuedeSoltar(base, 'finalizado') && !sePuedeSoltar(base, 'ingresado') && !sePuedeSoltar(base, null))
ok('sin permisos, en ningún lado', !sePuedeSoltar(t({ puedo: undefined }), 'en-proceso'))

igual('quién la hace, dicho', [
  quienLaHaceTexto({ tipo: 'agencia', nombre: 'Agencia Pampa' }),
  quienLaHaceTexto({ tipo: 'fuera', nombre: 'Estudio X', carga: 'Lucía' }),
  quienLaHaceTexto({ tipo: 'tienda', nombre: 'Nao' }),
  quienLaHaceTexto(null),
], ['Agencia Pampa', 'Estudio X · lo carga Lucía', 'Nao (Tienda)', null])

const lista = [
  t({ tareaId: 'a', hace: { tipo: 'agencia', nombre: 'Agencia Pampa' } }),
  t({ tareaId: 'b', hace: { tipo: 'agencia', nombre: 'agencia pampa' } }),
  t({ tareaId: 'c', hace: { tipo: 'tienda', nombre: 'Nao' } }),
  t({ tareaId: 'd', hace: { tipo: 'tienda', nombre: 'Ana' } }),
  t({ tareaId: 'e', hace: { tipo: 'fuera', nombre: 'Estudio X', carga: 'Lucía' } }),
]
igual('el filtro agrupa por agencia y todo lo de Tienda junto', opcionesDeQuien(lista).map(o => [o.nombre, o.cuantas]),
  [['Agencia Pampa', 2], ['Diseño de Tienda', 2], ['Estudio X (de afuera)', 1]])
igual('filtrar por una agencia', lista.filter(x => deQuien(x, grupoDeQuien({ tipo: 'agencia', nombre: 'Agencia Pampa' }).clave)).map(x => x.tareaId), ['a', 'b'])
igual('sin filtro, todas', lista.filter(x => deQuien(x, null)).length, 5)

const columna = [
  t({ tareaId: 'tarde', vence: '2026-12-01', titulo: 'B' }),
  t({ tareaId: 'temprano', vence: '2026-11-20', titulo: 'C' }),
  t({ tareaId: 'mia', vence: '2026-12-20', titulo: 'A' }),
]
igual('lo mío primero, después lo que vence antes', ordenar(columna, 'en-proceso', x => x.tareaId === 'mia').map(x => x.tareaId),
  ['mia', 'temprano', 'tarde'])
igual('en Archivado, lo más reciente arriba', ordenar([
  t({ tareaId: 'vieja', archivadaEl: '2026-10-20' }), t({ tareaId: 'nueva', archivadaEl: '2026-11-10' }),
], 'archivado', () => false).map(x => x.tareaId), ['nueva', 'vieja'])

// --- Revisión del 16/11: arreglos de pantalla ---

// "Ver más" de Archivado no se borra con cada refresco.
const antes = [
  t({ tareaId: 'activa', columna: 'en-proceso' }),
  t({ tareaId: 'arch-1', columna: 'archivado' }),
  t({ tareaId: 'arch-21', columna: 'archivado' }),
  t({ tareaId: 'arch-22', columna: 'archivado' }),
  t({ tareaId: 'desarchivada', columna: 'archivado' }),
]
const llegan = [
  t({ tareaId: 'activa', columna: 'esperando' }),
  t({ tareaId: 'arch-1', columna: 'archivado' }),
  t({ tareaId: 'desarchivada', columna: 'finalizado' }),
]
const juntas = conservarArchivadas(antes, llegan)
igual('quedan las archivadas traídas con "Ver más"', juntas.map(x => x.tareaId),
  ['activa', 'arch-1', 'desarchivada', 'arch-21', 'arch-22'])
igual('lo que llegó manda (la desarchivada está en su columna nueva)',
  juntas.filter(x => x.tareaId === 'desarchivada').map(x => x.columna), ['finalizado'])
ok('sin nada de antes, es lo que llegó', conservarArchivadas([], llegan) === llegan)
ok('una activa de antes que no vino no se conserva',
  !conservarArchivadas([t({ tareaId: 'borrada', columna: 'en-proceso' })], llegan).some(x => x.tareaId === 'borrada'))

// El filtro "¿Quién la hace?" que quedó sin opción no deja el tablero vacío.
const opciones = [{ clave: 'tienda' }, { clave: 'agencia:pampa' }]
igual('el filtro elegido vale si está entre las opciones', filtroVigente('agencia:pampa', opciones), 'agencia:pampa')
igual('si la opción desapareció, sin filtro', filtroVigente('agencia:sur', opciones), null)
igual('con una sola opción (sin chips), sin filtro', filtroVigente('tienda', [{ clave: 'tienda' }]), null)
igual('sin filtro, sin filtro', filtroVigente(null, opciones), null)

// Tocar una tarjeta abre la tarjeta, siempre (Ivan, 19/11/2026): entregar y
// revisar salen de los botones de la ficha, no del toque.
igual('nueva, sin nada entregado: se abre mirando', modoAlTocar('entregar', { ronda: 0, momento: 'produccion' }), 'ver')
igual('volvió con cambios: también mirando (el botón "Entregar ronda 2" está en la ficha)', modoAlTocar('entregar', { ronda: 1, momento: 'cambios' }), 'ver')
igual('a revisar: también mirando (el botón "Revisar ahora" está en la ficha)', modoAlTocar('revisar', { ronda: 1, momento: 'revision' }), 'ver')
igual('nada que hacer: mirando', modoAlTocar(null, { ronda: 2, momento: 'revision' }), 'ver')

// El rótulo del tipo, entero y legible.
igual('rótulos cortos', ['cenefa', 'mailing', 'banner', 'redes', 'otro', null].map(rotuloDePieza),
  ['Cenefa', 'EMM', 'Banner', 'Redes', 'Otro', 'Otro'])

// El anillo de "soltá acá" tiene variante clara y oscura, y no queda en -400 en claro.
ok('cada destino se ve en claro y en oscuro', COLUMNAS_DEL_TABLERO.every(c => /\bring-\w+-(500|600)\b/.test(c.destino) && /dark:ring-/.test(c.destino)))

// Un toque largo sin mover el dedo no suelta la tarjeta.
ok('temblor del dedo: no se movió', !seMovioElDedo({ x: 100, y: 100 }, 104, 103))
ok('arrastre de verdad: se movió', seMovioElDedo({ x: 100, y: 100 }, 100, 140))
ok('sin arrastre empezado, no se movió', !seMovioElDedo(null, 300, 300))

// El aviso de la plantilla con agencias sin cuentas.
igual('sin agencias sin cuentas, nada', avisoDeAgenciasSinCuentas([]), null)
igual('una agencia', avisoDeAgenciasSinCuentas(['Publisis']),
  '«Publisis» no tiene ninguna cuenta: la agencia no va a ver esas tarjetas. Revisá el nombre en la plantilla.')
igual('varias, sin repetir', avisoDeAgenciasSinCuentas(['A', 'B', 'A', ' C ']),
  '«A», «B» y «C» no tienen ninguna cuenta: esas agencias no van a ver sus tarjetas. Revisá los nombres en la plantilla.')

// El día de Uruguay (UTC−3), no el de la computadora.
igual('a las 23 h de Uruguay sigue siendo ese día', diaEnUruguay(new Date('2026-11-17T02:30:00Z')), '2026-11-16')
igual('a la medianoche de Uruguay ya es el siguiente', diaEnUruguay(new Date('2026-11-17T03:00:00Z')), '2026-11-17')

// El próximo paso (17/11/2026). En las listas (tablero, ficha, Mis tareas)
// se muestra el turno de la cadena: ahí no se sabe quién subió la versión.
// En la vista de la entrega sí: a quien le toca por la cadena pero la subió,
// no se le dice "Te toca" (nadie aprueba lo que entregó). Antes decía "Te
// toca" y no aparecía ningún botón.
const enRevision: ResumenEntrega = {
  tipoPieza: 'banner', momento: 'revision', ronda: 1, faseActual: 'fa-1', aprobadorDeTurno: 7, aprobadores: [7],
  fases: [{ id: 'fa-1', nombre: 'Entrega', estado: 'en-curso', rondas: 1 }],
}
const nombreDe = () => 'Lucía'
igual('le toca y puede decidir: te toca revisar', proximoPaso(enRevision, 9, 7, nombreDe, true).accion, 'revisar')
const enLaLista = proximoPaso(enRevision, 7, 7, nombreDe, false)
igual('en la lista, a quien le toca por la cadena le dice revisar', enLaLista.accion, 'revisar')
igual('en la vista, si puede decidir, sigue igual', pasoEnLaVista(enLaLista, true, false).accion, 'revisar')
const laSubio = pasoEnLaVista(enLaLista, false, true)
igual('en la vista, si la subió y no puede decidir: no es su turno', [laSubio.accion, laSubio.aQuien], [null, 'otro'])
ok('y dice que la revisa otra persona', laSubio.texto.startsWith('La entregaste vos'), laSubio.texto)
// Devuelta después de aprobada: se abrió la Entrega 2 y le toca a quien entrega.
const devuelta: ResumenEntrega = {
  ...enRevision, momento: 'produccion', ronda: 0, faseActual: 'fa-2', aprobadorDeTurno: null,
  fases: [
    { id: 'fa-1', nombre: 'Entrega', estado: 'aprobada', rondas: 2 },
    { id: 'fa-2', nombre: 'Entrega 2', estado: 'en-curso', rondas: 0, motivo: 'Cambió el precio' },
  ],
}
igual('devuelta: le toca entregar la Entrega 2', proximoPaso(devuelta, 9, 9, nombreDe).texto, 'Te toca: entregar Entrega 2')
const aprobada: ResumenEntrega = { ...devuelta, momento: 'aprobada', faseActual: null, fases: devuelta.fases.map(f => ({ ...f, estado: 'aprobada' as const })) }
igual('aprobada otra vez: sin próximo paso', proximoPaso(aprobada, 9, 9, nombreDe).accion, null)

// Los tres tableros (17/11/2026): cada tarjeta va al de su agencia, escrita como sea.
const tableros = ['Publicis', 'Another Monday', 'Diseñadores']
const tarjetaDe = (hace: Tarjeta['hace']) => ({ ...base, hace })
igual('una de Publicis va a Publicis', tableroDeTarjeta(tarjetaDe({ tipo: 'agencia', nombre: '  publicis ' }), tableros), 'Publicis')
igual('Another Monday, con espacios de más', tableroDeTarjeta(tarjetaDe({ tipo: 'agencia', nombre: 'ANOTHER   monday' }), tableros), 'Another Monday')
igual('una de Tienda no es de ninguno', tableroDeTarjeta(tarjetaDe({ tipo: 'tienda', nombre: 'Fer' }), tableros), null)
igual('otra agencia no es de ninguno', tableroDeTarjeta(tarjetaDe({ tipo: 'agencia', nombre: 'Agencia Pampa' }), tableros), null)
igual('las pestañas: los tres siempre, y Otras si hay', pestanasDeTableros([
  tarjetaDe({ tipo: 'agencia', nombre: 'Publicis' }), tarjetaDe({ tipo: 'agencia', nombre: 'publicis' }),
  tarjetaDe({ tipo: 'agencia', nombre: 'Diseñadores' }), tarjetaDe({ tipo: 'tienda', nombre: 'Fer' }),
], tableros).map(p => `${p.nombre}:${p.cuantas}`), ['Publicis:2', 'Another Monday:0', 'Diseñadores:1', 'Otras:1'])
igual('sin otras, no hay pestaña Otras', pestanasDeTableros([tarjetaDe({ tipo: 'agencia', nombre: 'Publicis' })], tableros).length, 3)
// 19/11/2026: la empresa se escribía a mano. Una tarjeta guardada para
// «Disenadores» (sin ñ) o «DISEÑADORES » es de Diseñadores, no de «Otras».
igual('sin ñ, va a Diseñadores', tableroDeTarjeta(tarjetaDe({ tipo: 'agencia', nombre: 'Disenadores' }), tableros), 'Diseñadores')
igual('en mayúsculas y con espacios, también', tableroDeTarjeta(tarjetaDe({ tipo: 'agencia', nombre: ' DISEÑADORES ' }), tableros), 'Diseñadores')
igual('las dos escrituras suman en la misma pestaña', pestanasDeTableros([
  tarjetaDe({ tipo: 'agencia', nombre: 'Diseñadores' }), tarjetaDe({ tipo: 'agencia', nombre: 'Disenadores' }),
], tableros).map(p => `${p.nombre}:${p.cuantas}`), ['Publicis:0', 'Another Monday:0', 'Diseñadores:2'])
igual('y en el filtro «¿Quién la hace?» son una sola agencia',
  grupoDeQuien({ tipo: 'agencia', nombre: 'Disenadores' }).clave, grupoDeQuien({ tipo: 'agencia', nombre: 'Diseñadores' }).clave)

// La push (17/11/2026): título, link de destino y fecha y hora, leída como en el servidor.
const push: TipoDeTarea = {
  clave: 'push', nombre: 'Push', opciones: [], otras: false, medida: null, bajada: null, pieza: 'otro',
  campos: [
    { clave: 'titulo', nombre: 'Título de la push', tipo: 'texto', largo: 120 },
    { clave: 'link', nombre: 'Link de destino', tipo: 'link' },
    { clave: 'envio', nombre: 'Fecha y hora de envío', tipo: 'fechaHora' },
  ],
}
igual('la push se lee con la fecha en criollo', descripcionDelPedido(push, [], {
  titulo: 'Llegó el Ciberlunes', link: 'https://www.tiendainglesa.com.uy/ciber', envio: '2026-11-20T18:30',
}), 'Título de la push: Llegó el Ciberlunes\nLink de destino: https://www.tiendainglesa.com.uy/ciber\nFecha y hora de envío: 20/11/2026 18:30')
ok('un link con https vale', linkValido(' https://tiendainglesa.com.uy/x '))
ok('sin http no vale', !linkValido('tiendainglesa.com.uy'))
ok('javascript: no vale', !linkValido('javascript:alert(1)'))

// Lo que se pidió, como lista (18/11/2026): cada opción con su medida y los datos aparte.
const banners: TipoDeTarea = {
  clave: 'banner', nombre: 'Banners', otras: true, medida: null, bajada: null, pieza: 'banner',
  opciones: [{ nombre: 'Header', medida: 'web 1920×416 · mobile 640×260' }, { nombre: 'Carrito', medida: 'web 368×140' }],
  campos: [{ clave: 'cta', nombre: 'CTA', tipo: 'texto', largo: 60 }],
}
igual('cada opción con su medida', pedidoEnLista(banners, ['Header', 'Carrito', 'A mano'], { cta: 'Ver más' }), {
  tipo: 'Banners',
  items: [
    { nombre: 'Header', medida: 'web 1920×416 · mobile 640×260' },
    { nombre: 'Carrito', medida: 'web 368×140' },
    { nombre: 'A mano', medida: null },
  ],
  datos: [{ nombre: 'CTA', valor: 'Ver más' }],
})
igual('sin tipo, no hay lista', pedidoEnLista(null, ['Header'], {}), null)
igual('sin nada tildado ni datos, tampoco', pedidoEnLista(banners, [], {}), null)
igual('la push: solo datos', pedidoEnLista(push, [], { titulo: 'Hola' })?.datos, [{ nombre: 'Título de la push', valor: 'Hola' }])
const pedidoBanners = descripcionDelPedido(banners, ['Header'], { cta: 'Ver más' })
igual('el detalle sin el pedido repetido', detalleSinPedido(`${pedidoBanners}\nAdaptar kv a medidas`, pedidoBanners), 'Adaptar kv a medidas')
igual('si es solo el pedido, nada', detalleSinPedido(pedidoBanners, pedidoBanners), '')
igual('si no empieza con el pedido, entero', detalleSinPedido('Otra cosa', pedidoBanners), 'Otra cosa')
igual('sin pedido, entero', detalleSinPedido(' Algo ', null), 'Algo')

// Las decisiones, para leer (19/11/2026: se sacó «Aprobado con cambios»; una
// ronda vieja que la trae se lee como aprobada, que es lo que fue).
igual('cómo se lee cada decisión', [etiquetaDecision('aprobada'), etiquetaDecision('cambios'), etiquetaDecision('aprobada-con-cambios')],
  ['Aprobó', 'Pidió cambios', 'Aprobó'])
// El día de cada ronda, en el renglón cerrado.
igual('el día de una ronda', [fechaDia(null), fechaDia('x'), fechaDia('2026-11-19T12:00:00')], ['', '', '19/11'])

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
