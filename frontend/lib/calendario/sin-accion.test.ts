/**
 * Las tarjetas sin acción (lib/calendario/sin-accion.ts).
 *
 *     npm run test:calendario
 */
import { destinoDeAvisoSinAccion, esSinAccion } from './sin-accion'

let fallos = 0
function ok(nombre: string, cond: boolean) {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}`) }
}

console.log('Sin acción')
ok('la de Tienda Inglesa', esSinAccion('sin-accion-tienda_inglesa'))
ok('una acción común no', !esSinAccion('br-ciberlunes'))
ok('sin id no', !esSinAccion(null) && !esSinAccion(''))
ok('el aviso lleva a la tarjeta', destinoDeAvisoSinAccion('sin-accion-redexpres:ta-123') === '/entregas?tarea=ta-123')
ok('el de una acción común no cambia', destinoDeAvisoSinAccion('br-1:ta-123') === null)
ok('sin tarea no hay a dónde', destinoDeAvisoSinAccion('sin-accion-redexpres') === null)

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
