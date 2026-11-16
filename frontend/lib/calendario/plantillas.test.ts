/**
 * Pruebas de las plantillas de tareas. Se corren con las demás:
 *
 *     npm run test:calendario
 *
 * Lo que se fija acá es lo que la pantalla calcula sin esperar al servidor, y
 * que tiene que dar lo mismo que calcula él: la fecha de cada tarea, qué se
 * mueve cuando se mueve la acción, que lo manual se respeta y qué plantilla
 * se sugiere en cada acción.
 */
import {
  EJEMPLO_DE_PLANTILLA, conCambios, enOrden, moverAncladas, plantillasParaElegir, plantillasSugeridas,
  problemaDePlantilla, tareasDesdePlantilla, textoDeAncla, venceAnclado,
} from './plantillas'
import type { BarraGuardada, Plantilla, Tarea } from './tipos'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

// Una acción del 10 al 20 de diciembre.
const DESDE = '2026-12-10'
const HASTA = '2026-12-20'

const plantilla: Plantilla = {
  id: 'pl-1', nombre: 'Mega evento', categoria: 'MEGA EVENTO',
  tareas: EJEMPLO_DE_PLANTILLA.map((t, i) => ({ ...t, id: `t${i + 1}` })),
}
let n = 0
const ids = () => `ta-${++n}`

console.log('\nla cuenta')
igual('30 días antes del inicio', venceAnclado('inicio', -30, DESDE, HASTA), '2026-11-10')
igual('el día que arranca', venceAnclado('inicio', 0, DESDE, HASTA), '2026-12-10')
igual('1 día después del fin', venceAnclado('fin', 1, DESDE, HASTA), '2026-12-21')
igual('cruza de año', venceAnclado('fin', 15, DESDE, HASTA), '2027-01-04')

console.log('\naplicar la plantilla')
const { tareas, ids: mapa } = tareasDesdePlantilla(plantilla, { desde: DESDE, hasta: HASTA }, ids)
igual('las fechas del ejemplo', tareas.map(t => t.vence),
  ['2026-11-10', '2026-11-19', '2026-11-30', '2026-12-07', '2026-12-11', '2026-12-21'])
igual('el retiro queda anclado al fin', [tareas[5].ancla, tareas[5].anclaDias], ['fin', 1])
ok('cada tarea dice de qué plantilla vino', tareas.every(t => t.plantillaId === 'pl-1'))
igual('viaja el id nuevo de cada tarea de la plantilla', Object.keys(mapa), ['t1', 't2', 't3', 't4', 't5', 't6'])
const conSub = tareasDesdePlantilla({
  ...plantilla,
  tareas: [
    { id: 's', parentId: 'p', titulo: 'Header', descripcion: null, asignadoA: null, ancla: 'inicio', dias: -5 },
    { id: 'p', parentId: null, titulo: 'Piezas', descripcion: null, asignadoA: 7, ancla: null, dias: 0 },
  ],
}, { desde: DESDE, hasta: HASTA }, ids)
igual('la subtarea va después de su tarea', conSub.tareas.map(t => t.titulo), ['Piezas', 'Header'])
ok('y cuelga del id nuevo', conSub.tareas[1].parentId === conSub.tareas[0].id)
igual('sin ancla, sin fecha', [conSub.tareas[0].vence, conSub.tareas[0].ancla], [null, null])
igual('con su responsable', conSub.tareas[0].asignadoA, 7)

console.log('\nmover la acción')
const base: Tarea[] = tareas.map(t => ({ ...t }))
base[0] = { ...base[0], estado: 'hecha' }
base[3] = conCambios(base[3], { vence: '2026-12-05' }, DESDE, HASTA)
igual('la cambiada a mano se suelta', [base[3].vence, base[3].ancla, base[3].anclaDias], ['2026-12-05', null, null])
const movidas = moverAncladas(base, '2026-12-13', '2026-12-23')
igual('se mueven las ancladas no hechas', movidas.map(t => t.vence),
  ['2026-11-10', '2026-11-22', '2026-12-03', '2026-12-05', '2026-12-14', '2026-12-24'])
ok('lo que no cambia es el mismo objeto', moverAncladas(base, DESDE, HASTA)[1] === base[1])
const soloFin = moverAncladas(tareas, DESDE, '2026-12-24')
igual('si solo cambia el fin, solo el retiro', soloFin.map(t => t.vence),
  ['2026-11-10', '2026-11-19', '2026-11-30', '2026-12-07', '2026-12-11', '2026-12-25'])

console.log('\nlo manual se respeta')
const misma = conCambios(tareas[2], { vence: tareas[2].vence }, DESDE, HASTA)
igual('mandar la misma fecha no la suelta', misma.ancla, 'inicio')
const sinFecha = conCambios(tareas[2], { vence: null }, DESDE, HASTA)
igual('sacarle la fecha sí', [sinFecha.vence, sinFecha.ancla], [null, null])
const reabierta = conCambios({ ...tareas[0], estado: 'hecha' }, { estado: 'pendiente' }, '2026-12-13', '2026-12-23')
igual('al reabrir vuelve a su fecha con la acción de hoy', reabierta.vence, '2026-11-13')
const otroCambio = conCambios(tareas[0], { titulo: 'Brief' }, '2026-12-13', '2026-12-23')
igual('cambiar el título no toca la fecha', otroCambio.vence, '2026-11-10')

console.log('\nel texto')
igual('antes', textoDeAncla('inicio', -3), '3 días antes del inicio')
igual('uno solo', textoDeAncla('fin', 1), '1 día después del fin')
igual('cero en el inicio', textoDeAncla('inicio', 0), 'el día que arranca')
igual('cero en el fin', textoDeAncla('fin', 0), 'el día que termina')
igual('sin ancla', textoDeAncla(null, 0), 'sin fecha')

console.log('\nqué se sugiere')
const accion = (banda: string, extra: Partial<BarraGuardada> = {}): BarraGuardada => ({
  id: 'br-1', seccion: 'comercial', banda, carril: 0, nombre: 'Black Week', color: null,
  desde: DESDE, hasta: HASTA, tareas: [], ...extra,
})
const general: Plantilla = { id: 'pl-2', nombre: 'Básica', categoria: null, tareas: plantilla.tareas }
const otra: Plantilla = { id: 'pl-3', nombre: 'Especial', categoria: 'Especiales', tareas: plantilla.tareas }
const todas = [otra, general, plantilla]
igual('la de su categoría, sin importar mayúsculas', plantillasSugeridas(todas, accion('Mega evento')).map(p => p.id), ['pl-1'])
igual('sin categoría no se sugiere nada', plantillasSugeridas(todas, accion('Sin categoría')), [])
igual('en un envío tampoco', plantillasSugeridas(todas, accion('MEGA EVENTO', { seccion: 'envio' })), [])
igual('si ya se usó, no se insiste',
  plantillasSugeridas(todas, accion('MEGA EVENTO', { tareas: [{ ...tareas[0], plantillaId: 'pl-1' }] })), [])
igual('para elegir: la de su categoría, las generales y el resto',
  plantillasParaElegir(todas, 'MEGA EVENTO').map(p => p.id), ['pl-1', 'pl-2', 'pl-3'])

console.log('\nel orden en el editor')
igual('cada una seguida de sus subtareas', enOrden([
  { id: 'a', parentId: null }, { id: 'b', parentId: null }, { id: 'a1', parentId: 'a' }, { id: 'b1', parentId: 'b' },
]).map(t => t.id), ['a', 'a1', 'b', 'b1'])

console.log('\nlo que falta para guardar')
ok('el ejemplo con nombre está listo', problemaDePlantilla({ nombre: 'Promo', tareas: plantilla.tareas }) === null)
ok('sin nombre no', problemaDePlantilla({ nombre: '  ', tareas: plantilla.tareas }) !== null)
ok('sin tareas no', problemaDePlantilla({ nombre: 'Promo', tareas: [] }) !== null)
ok('una tarea sin título no', problemaDePlantilla({ nombre: 'Promo', tareas: [{ ...plantilla.tareas[0], titulo: ' ' }] }) !== null)
ok('más de un año no', problemaDePlantilla({ nombre: 'Promo', tareas: [{ ...plantilla.tareas[0], dias: -400 }] }) !== null)

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)
