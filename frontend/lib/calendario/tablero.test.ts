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
  modoAlTocar, opcionesDeQuien, ordenar, queHaceMover, quienLaHaceTexto, rotuloDePieza, seMovioElDedo,
  sePuedeSoltar, textoDeFecha,
} from './tablero'
import { diaEnUruguay } from './fechas'
import type { Tarjeta } from './entregas'

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

// Tocar una tarjeta nueva muestra lo que se pidió antes de entregar.
igual('nueva, sin nada entregado: se abre mirando', modoAlTocar('entregar', { ronda: 0, momento: 'produccion' }), 'ver')
igual('volvió con cambios: directo a entregar', modoAlTocar('entregar', { ronda: 1, momento: 'cambios' }), 'entregar')
igual('a revisar: directo a revisar', modoAlTocar('revisar', { ronda: 1, momento: 'revision' }), 'revisar')
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

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
