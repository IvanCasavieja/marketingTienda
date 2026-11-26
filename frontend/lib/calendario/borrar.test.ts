/**
 * Lo entregado no se borra (lib/calendario/borrar.ts, H-001). Se corren con
 * las demás:
 *
 *     npm run test:calendario
 *
 * Es lo que la pantalla mira antes de ofrecer «Sí, borrar» o «Sí, eliminar»:
 * la misma regla que el servidor (backend/tests/test_borrar_no_pierde_entregas.py).
 */
import { tareasConEntregas, tieneEntregas } from './borrar'
import type { ResumenEntrega } from './entregas'
import type { Tarea } from './tipos'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  if (JSON.stringify(obtenido) === JSON.stringify(esperado)) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

/** Una tarjeta con sus fases: cuántas rondas se entregaron en cada una. */
function tarjeta(rondasPorFase: number[], ronda = 0): ResumenEntrega {
  return {
    tipoPieza: 'banner', momento: 'produccion', ronda, faseActual: null, aprobadorDeTurno: null, aprobadores: [],
    fases: rondasPorFase.map((rondas, i) => ({ id: `fa-${i}`, nombre: `Entrega ${i + 1}`, estado: 'en-curso', rondas })),
  }
}
function tarea(id: string, entrega?: ResumenEntrega): Tarea {
  return { id, parentId: null, titulo: id, descripcion: null, estado: 'pendiente', asignadoA: null, vence: null, creadoPor: 1, entrega }
}

console.log('\nuna tarea')
igual('sin tarjeta no tiene entregas', tieneEntregas(tarea('ta-1')), false)
igual('con la tarjeta recién nacida tampoco', tieneEntregas(tarea('ta-2', tarjeta([0]))), false)
igual('con una ronda entregada sí', tieneEntregas(tarea('ta-3', tarjeta([1], 1))), true)
igual('devuelta y en la Entrega 2 (ronda 0): la 1 sigue entregada',
  tieneEntregas(tarea('ta-4', tarjeta([2, 0], 0))), true)

console.log('\nuna acción')
igual('cuenta solo las tareas con algo entregado', tareasConEntregas({
  tareas: [tarea('ta-1'), tarea('ta-2', tarjeta([0])), tarea('ta-3', tarjeta([1], 1)), tarea('ta-4', tarjeta([2, 0]))],
}), 2)
igual('sin tareas, ninguna', tareasConEntregas({}), 0)

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
