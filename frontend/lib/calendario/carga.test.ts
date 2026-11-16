/**
 * Pruebas de la carga del equipo. Se corren con las demás:
 *
 *     npm run test:calendario
 */
import { cargaDelEquipo, nivelDeCarga } from './carga'
import type { BarraGuardada, Tarea } from './tipos'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

let n = 0
const t = (asignadoA: number | null, vence: string | null, estado: Tarea['estado'] = 'pendiente'): Tarea =>
  ({ id: `t${++n}`, parentId: null, titulo: `Tarea ${n}`, descripcion: null, estado, asignadoA, vence, creadoPor: null })
const accion = (nombre: string, tareas: Tarea[]): BarraGuardada =>
  ({ id: nombre, seccion: 'comercial', banda: 'MEGA EVENTO', carril: 0, nombre, color: null, desde: '2026-12-01', hasta: '2026-12-03', tareas })

console.log('carga')
// Hoy es lunes 16/11/2026: semanas 16-22, 23-29, 30/11-6/12, 7-13/12.
const HOY = '2026-11-16'
const { semanas, filas } = cargaDelEquipo([
  accion('Ciberlunes', [t(1, '2026-11-10'), t(1, '2026-11-18'), t(1, '2026-11-22'), t(1, '2026-11-25'), t(1, null), t(1, '2027-01-10'), t(1, '2026-11-17', 'hecha')]),
  accion('Navidad', [t(2, '2026-11-20'), t(2, '2026-12-13'), t(null, '2026-11-18')]),
], HOY)
igual('cuatro semanas de lunes a domingo', semanas.map(s => `${s.desde}..${s.hasta}`),
  ['2026-11-16..2026-11-22', '2026-11-23..2026-11-29', '2026-11-30..2026-12-06', '2026-12-07..2026-12-13'])
igual('los más cargados arriba (primero lo vencido)', filas.map(f => f.personaId), [1, 2])
const ana = filas[0]
igual('las hechas no cuentan', ana.total, 6)
igual('vencidas, por semana, más adelante y sin fecha',
  [ana.vencidas, ana.porSemana, ana.masAdelante, ana.sinFecha], [1, [2, 1, 0, 0], 1, 1])
igual('el domingo entra en su semana y el domingo de la última también', filas[1].porSemana, [1, 0, 0, 1])
igual('la lista de tareas va por fecha, las sin fecha al final', ana.tareas.map(x => x.vence), ['2026-11-10', '2026-11-18', '2026-11-22', '2026-11-25', '2027-01-10', null])
igual('una tarea sin asignar no es de nadie', filas.length, 2)
const domingo = cargaDelEquipo([], '2026-11-22').semanas[0]
igual('un domingo pertenece a la semana que empezó el lunes', [domingo.desde, domingo.hasta], ['2026-11-16', '2026-11-22'])
igual('niveles', [0, 1, 3, 5].map(nivelDeCarga), ['nada', 'normal', 'alta', 'excesiva'])

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\ncarga: todo bien')
