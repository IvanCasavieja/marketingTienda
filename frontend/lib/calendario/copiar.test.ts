/**
 * Pruebas de "copiar a otra fecha". Se corren con las demás:
 *
 *     npm run test:calendario
 *
 * La copia la hace el servidor; lo que se fija acá es lo que la pantalla dice
 * antes de copiar: a qué fecha va "al año que viene", cómo queda el nombre
 * (la misma regla que el backend: ver backend/tests/test_calendario_copiar.py),
 * si choca con una acción del mismo nombre y qué se lleva.
 */
import { alAnioQueViene, chocaCon, diaDeLaSemana, enLista, nombreParaLaCopia, queSeCopia, rangoDeLaCopia } from './copiar'
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

function accion(b: Partial<BarraGuardada> = {}): BarraGuardada {
  return {
    id: 'br-2025', seccion: 'comercial', banda: 'MEGA EVENTO', carril: 0, nombre: 'Ciberlunes 2025',
    color: null, desde: '2025-12-01', hasta: '2025-12-02', piezas: [], avisos: [], tareas: [], ...b,
  }
}
function tarea(id: string, asignadoA: number | null = null): Tarea {
  return { id, parentId: null, titulo: id, descripcion: null, estado: 'hecha', asignadoA, vence: null, creadoPor: 1 }
}

console.log('\nla fecha')
igual('el Ciberlunes 2025 va al lunes 30/11/2026', alAnioQueViene('2025-12-01'), '2026-11-30')
igual('y cae el mismo día de la semana', diaDeLaSemana(alAnioQueViene('2025-12-01')), diaDeLaSemana('2025-12-01'))
igual('lunes es lunes', diaDeLaSemana('2025-12-01'), 'lunes')
igual('dura lo mismo que la original', rangoDeLaCopia(accion(), '2026-11-30'), { desde: '2026-11-30', hasta: '2026-12-01' })
igual('aunque cruce de mes', rangoDeLaCopia(accion({ desde: '2025-09-25', hasta: '2025-10-05' }), '2026-09-24'),
  { desde: '2026-09-24', hasta: '2026-10-04' })

console.log('\nel nombre')
igual('"Ciberlunes 2025" → "Ciberlunes 2026"',
  nombreParaLaCopia('Ciberlunes 2025', '2025-12-01', '2025-12-02', '2026-11-30'), 'Ciberlunes 2026')
igual('sin año, igual', nombreParaLaCopia('Día de la Madre', '2025-05-04', '2025-05-11', '2026-05-03'), 'Día de la Madre')
igual('si la copia arranca el mismo año, no cambia',
  nombreParaLaCopia('Ciberlunes 2025', '2025-12-01', '2025-12-02', '2025-12-08'), 'Ciberlunes 2025')
igual('una acción que cruza de año corre los dos',
  nombreParaLaCopia('Fin de año 2025-2026', '2025-12-26', '2026-01-02', '2026-12-25'), 'Fin de año 2026-2027')
igual('un año que no es el de la acción no se toca',
  nombreParaLaCopia('Previa Mundial 2030 · 2025', '2025-06-01', '2025-06-07', '2026-05-31'), 'Previa Mundial 2030 · 2026')
igual('cuatro dígitos dentro de un número más largo no son un año',
  nombreParaLaCopia('Cupón 20250 y SKU 120251', '2025-03-01', '2025-03-02', '2026-02-28'), 'Cupón 20250 y SKU 120251')
igual('el año al principio del nombre también',
  nombreParaLaCopia('2025 Hot Sale', '2025-05-11', '2025-05-13', '2026-05-10'), '2026 Hot Sale')
igual('copiar para atrás también corre el año',
  nombreParaLaCopia('Hot Sale 2026', '2026-05-11', '2026-05-13', '2025-05-12'), 'Hot Sale 2025')

console.log('\nsi choca con otra del mismo nombre')
const del2026 = accion({ id: 'br-2026', nombre: 'Ciberlunes 2026', desde: '2026-11-30', hasta: '2026-12-01' })
const todas = [accion(), del2026]
igual('ya hay un Ciberlunes 2026 en esas fechas', chocaCon(todas, 'comercial', 'Ciberlunes 2026', '2026-11-30', '2026-12-01')?.id, 'br-2026')
igual('sin importar mayúsculas, tildes ni espacios', chocaCon(todas, 'comercial', '  ciberlunes   2026', '2026-12-01', '2026-12-03')?.id, 'br-2026')
igual('en otras fechas no choca', chocaCon(todas, 'comercial', 'Ciberlunes 2026', '2026-12-02', '2026-12-03'), null)
igual('con otro nombre no choca', chocaCon(todas, 'comercial', 'Black Friday 2026', '2026-11-30', '2026-12-01'), null)
igual('un envío suelto con el mismo nombre no es la misma acción',
  chocaCon(todas, 'envio', 'Ciberlunes 2026', '2026-11-30', '2026-11-30'), null)

console.log('\nqué se lleva')
const completa = accion({
  piezas: [{ id: 'p', area: 'email', formato: 'Mailing digital', estado: 'publicado' }],
  tareas: [tarea('a', 5), tarea('b', 9), tarea('c')],
  avisos: [
    { id: 'x', diasAntes: 10, destinatarios: [5, 9], creadoPor: 1 },
    { id: 'y', diasAntes: 3, destinatarios: [9], creadoPor: 1 },
  ],
})
igual('con permiso de tareas, todo; se saca a quien ya no ve el calendario',
  queSeCopia(completa, new Set([5]), true),
  { piezas: 1, tareas: 3, tareasSinPermiso: 0, sinResponsable: 1, avisos: 1, destinatariosQuitados: 2, avisosSinNadie: 1 })
igual('sin permiso de tareas, el resto, y se dice cuántas quedan afuera',
  queSeCopia(completa, new Set([5, 9]), false),
  { piezas: 1, tareas: 0, tareasSinPermiso: 3, sinResponsable: 0, avisos: 2, destinatariosQuitados: 0, avisosSinNadie: 0 })
igual('sin la lista de personas no se adivina a quién se saca',
  queSeCopia(completa, null, true),
  { piezas: 1, tareas: 3, tareasSinPermiso: 0, sinResponsable: 0, avisos: 2, destinatariosQuitados: 0, avisosSinNadie: 0 })

console.log('\nlistas')
igual('una', enLista(['3 piezas']), '3 piezas')
igual('tres', enLista(['3 piezas', '2 tareas', '1 aviso']), '3 piezas, 2 tareas y 1 aviso')

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)
