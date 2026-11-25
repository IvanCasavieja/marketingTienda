/**
 * El guardado de la planilla de Redexpres (lib/redexpres/ediciones.ts) y en
 * qué situación está el pedido del mes (lib/redexpres/estado.ts).
 *
 *     npm run test:redexpres
 */
import { conEdicion, sinLoGuardado, type Ediciones } from './ediciones'
import { estadoDelPedido, mesExiste } from './estado'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

console.log('Escribir')
let e: Ediciones = {}
e = conEdicion(e, 'Pocitos', 'cenefas', '1')
e = conEdicion(e, 'Pocitos', 'cenefas', '12')
igual('"12" queda "12", no "1"', e, { Pocitos: { cenefas: '12' } })
const antes: Ediciones = { Centro: { afiches: '3' } }
const despues = conEdicion(antes, 'Centro', 'cenefas', '5')
igual('no cambia la original', antes, { Centro: { afiches: '3' } })
igual('suma la celda a la fila', despues, { Centro: { afiches: '3', cenefas: '5' } })
igual('un local con nombre raro no rompe nada', conEdicion({}, '__proto__', 'x', '1')['__proto__'], { x: '1' })

console.log('Después de guardar')
igual('lo que se mandó sale, y la fila vacía también', sinLoGuardado({ Pocitos: { cenefas: '12' } }, 'Pocitos', { cenefas: '12' }), {})
igual('lo que cambió mientras se guardaba queda pendiente',
  sinLoGuardado({ Pocitos: { cenefas: '123' } }, 'Pocitos', { cenefas: '12' }), { Pocitos: { cenefas: '123' } })
igual('una celda nueva escrita mientras se guardaba queda',
  sinLoGuardado({ Pocitos: { cenefas: '12', afiches: '4' } }, 'Pocitos', { cenefas: '12' }), { Pocitos: { afiches: '4' } })
igual('las otras filas no se tocan',
  sinLoGuardado({ Pocitos: { cenefas: '12' }, Centro: { afiches: '3' } }, 'Pocitos', { cenefas: '12' }), { Centro: { afiches: '3' } })
const igualito: Ediciones = { Centro: { afiches: '3' } }
igual('un local sin pendientes devuelve lo mismo', sinLoGuardado(igualito, 'Pocitos', { a: '1' }) === igualito, true)

console.log('Estado del pedido')
const dic26 = { year: 2026, month: 12 }
const dic27 = { year: 2027, month: 12 }
igual('sin meses abiertos: sinMeses', estadoDelPedido([], null), 'sinMeses')
igual('sin meses aunque haya uno elegido: sinMeses', estadoDelPedido([], dic26), 'sinMeses')
igual('el mismo mes de otro año: mesNoAbierto', estadoDelPedido([dic26], dic27), 'mesNoAbierto')
igual('ninguno elegido con meses: mesNoAbierto', estadoDelPedido([dic26], null), 'mesNoAbierto')
igual('fila confirmada: confirmado', estadoDelPedido([dic26], dic26, { confirmado: true }), 'confirmado')
igual('fila sin confirmar: abierto', estadoDelPedido([dic26], dic26, { confirmado: false }), 'abierto')
igual('todavía sin fila: abierto', estadoDelPedido([dic26], dic26, undefined), 'abierto')
igual('mesExiste distingue el año', [mesExiste([dic26], dic26), mesExiste([dic26], dic27)], [true, false])

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
