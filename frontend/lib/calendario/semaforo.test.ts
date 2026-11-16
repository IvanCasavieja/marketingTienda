/**
 * Pruebas del semáforo de las acciones. Se corren con las demás:
 *
 *     npm run test:calendario
 */
import { semaforoDe } from './semaforo'
import type { Pieza, Tarea } from './tipos'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const HOY = '2026-11-16'
const pieza = (estado: Pieza['estado']): Pieza => ({ id: estado + Math.random(), area: 'fisico', formato: 'Cenefa', estado })
const tarea = (estado: Tarea['estado'], vence: string | null = null): Tarea => ({
  id: estado + Math.random(), parentId: null, titulo: 't', descripcion: null, estado, asignadoA: null, vence, creadoPor: null,
})
const accion = (desde: string, hasta: string, piezas: Pieza[] = [], tareas: Tarea[] = []) => ({ desde, hasta, piezas, tareas })

console.log('semaforo')
igual('sin piezas ni tareas no hay semáforo', semaforoDe(accion('2026-11-20', '2026-11-22'), HOY), null)
igual('una acción que ya terminó no tiene semáforo', semaforoDe(accion('2026-11-01', '2026-11-15', [pieza('pendiente')]), HOY), null)
igual('sin acción no hay semáforo', semaforoDe(undefined, HOY), null)
igual('todo aprobado y hecho: verde, todo listo',
  semaforoDe(accion('2026-11-18', '2026-11-20', [pieza('aprobado'), pieza('publicado')], [tarea('hecha')]), HOY),
  { color: 'verde', texto: 'Todo listo' })
igual('falta pero quedan 20 días: verde',
  semaforoDe(accion('2026-12-06', '2026-12-08', [pieza('pendiente')]), HOY)?.color, 'verde')
igual('falta y quedan 10 días: amarillo',
  semaforoDe(accion('2026-11-26', '2026-11-28', [pieza('en-proceso')]), HOY)?.color, 'amarillo')
igual('falta y quedan 3 días: rojo, con el detalle',
  semaforoDe(accion('2026-11-19', '2026-11-21', [pieza('pendiente'), pieza('pendiente')], [tarea('en-proceso')]), HOY),
  { color: 'rojo', texto: 'Arranca en 3 días: faltan 2 piezas y 1 tarea' })
igual('ya arrancó con algo pendiente: rojo',
  semaforoDe(accion('2026-11-14', '2026-11-20', [], [tarea('pendiente')]), HOY),
  { color: 'rojo', texto: 'Ya arrancó: falta 1 tarea' })
igual('arranca mañana',
  semaforoDe(accion('2026-11-17', '2026-11-17', [pieza('pendiente')]), HOY)?.texto, 'Arranca mañana: falta 1 pieza')
igual('una tarea vencida pone rojo aunque falte mucho',
  semaforoDe(accion('2026-12-20', '2026-12-22', [], [tarea('pendiente', '2026-11-10')]), HOY),
  { color: 'rojo', texto: 'Arranca en 34 días: falta 1 tarea (1 tarea vencida)' })
igual('una tarea hecha con fecha pasada no cuenta como vencida',
  semaforoDe(accion('2026-12-20', '2026-12-22', [pieza('pendiente')], [tarea('hecha', '2026-11-10')]), HOY)?.color, 'verde')

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\nsemaforo: todo bien')
