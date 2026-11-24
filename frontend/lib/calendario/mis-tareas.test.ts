/**
 * Pruebas de Mis tareas (24/11/2026). Se corren con las demás:
 *
 *     npm run test:calendario
 *
 * Que la pantalla no diga «Estás al día» ni «No tenés nada pendiente» cuando
 * no pudo traer todo, y que sin fallas diga lo mismo que antes.
 */
import { avisosDeFalla, resumenDeEncabezado, vacioQueSeMuestra } from './mis-tareas'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const sinFallas = { falloTareas: false, falloEntregas: false }

console.log('Mis tareas: sin fallas, igual que antes')
igual('sin tareas asignadas', vacioQueSeMuestra({ ...sinFallas, cantidadDelMundo: 0, cantidadAbiertas: 0, hayEntregasArriba: false }), 'sinAsignar')
igual('todas hechas', vacioQueSeMuestra({ ...sinFallas, cantidadDelMundo: 3, cantidadAbiertas: 0, hayEntregasArriba: false }), 'alDia')
igual('con abiertas no va cartel', vacioQueSeMuestra({ ...sinFallas, cantidadDelMundo: 3, cantidadAbiertas: 1, hayEntregasArriba: false }), null)
igual('con piezas arriba no va cartel', vacioQueSeMuestra({ ...sinFallas, cantidadDelMundo: 0, cantidadAbiertas: 0, hayEntregasArriba: true }), null)
igual('resumen con tareas y piezas',
  resumenDeEncabezado({ ...sinFallas, pendientes: 1, paraRevisar: 2, nombreMundo: 'Tienda Inglesa' }),
  'Tenés 1 tarea pendiente y 2 piezas para revisar en Tienda Inglesa.')
igual('resumen en plural, sin mundo',
  resumenDeEncabezado({ ...sinFallas, pendientes: 4, paraRevisar: 0, nombreMundo: null }),
  'Tenés 4 tareas pendientes.')
igual('resumen sin nada',
  resumenDeEncabezado({ ...sinFallas, pendientes: 0, paraRevisar: 0, nombreMundo: 'Redexpres' }),
  'No tenés nada pendiente en Redexpres.')
igual('sin fallas no hay avisos', avisosDeFalla(sinFallas), [])

console.log('Mis tareas: con fallas')
igual('falló tareas y no hay ninguna: sin cartel',
  vacioQueSeMuestra({ falloTareas: true, falloEntregas: false, cantidadDelMundo: 0, cantidadAbiertas: 0, hayEntregasArriba: false }), null)
const resumenFalloTareas = resumenDeEncabezado({ falloTareas: true, falloEntregas: false, pendientes: 0, paraRevisar: 0, nombreMundo: 'Tienda Inglesa' })
ok('falló tareas: no dice «No tenés nada pendiente»', !resumenFalloTareas.includes('No tenés nada pendiente'), resumenFalloTareas)
igual('falló entregas y nada pendiente: sin «Estás al día»',
  vacioQueSeMuestra({ falloTareas: false, falloEntregas: true, cantidadDelMundo: 2, cantidadAbiertas: 0, hayEntregasArriba: false }), null)
const resumenFalloEntregas = resumenDeEncabezado({ falloTareas: false, falloEntregas: true, pendientes: 0, paraRevisar: 0, nombreMundo: null })
ok('falló entregas: no dice «No tenés nada pendiente»', !resumenFalloEntregas.includes('No tenés nada pendiente'), resumenFalloEntregas)
igual('dos fallas, dos avisos en orden', avisosDeFalla({ falloTareas: true, falloEntregas: true }),
  ['No se pudieron traer tus tareas.', 'No se pudieron traer las piezas para revisar.'])
igual('solo entregas', avisosDeFalla({ falloTareas: false, falloEntregas: true }), ['No se pudieron traer las piezas para revisar.'])
igual('una falla con 3 pendientes de antes: los sigue contando',
  resumenDeEncabezado({ falloTareas: true, falloEntregas: false, pendientes: 3, paraRevisar: 0, nombreMundo: 'Tienda Express' }),
  'Tenés 3 tareas pendientes en Tienda Express.')

if (fallos > 0) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien.')
