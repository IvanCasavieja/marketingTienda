/**
 * El guardado de la planilla de Redexpres (lib/redexpres/ediciones.ts) y en
 * qué situación está el pedido del mes (lib/redexpres/estado.ts).
 *
 * Y que las cantidades sean enteros desde 0 (lib/redexpres/cantidades.ts).
 *
 *     npm run test:redexpres
 */
import { conEdicion, sinLoGuardado, type Ediciones } from './ediciones'
import { estadoDelPedido, mesExiste } from './estado'
import { limpiarCantidad, teclaEnCantidad } from './cantidades'

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

console.log('Cantidades: enteros desde 0')
igual('"-5" da "5" y avisa el signo', limpiarCantidad('-5'), { valor: '5', aviso: 'signo' })
igual('"+3" da "3" y avisa el signo', limpiarCantidad('+3'), { valor: '3', aviso: 'signo' })
igual('"2.5" da "2" y avisa el decimal', limpiarCantidad('2.5'), { valor: '2', aviso: 'decimal' })
igual('"2,5" da "2" y avisa el decimal', limpiarCantidad('2,5'), { valor: '2', aviso: 'decimal' })
igual('"99" con tope 20 da "20" y avisa el tope', limpiarCantidad('99', 20), { valor: '20', aviso: 'maximo' })
igual('"20" con tope 20 queda igual', limpiarCantidad('20', 20), { valor: '20', aviso: null })
igual('"" queda "" sin aviso', limpiarCantidad(''), { valor: '', aviso: null })
igual('"-" solo queda "" y avisa el signo', limpiarCantidad('-'), { valor: '', aviso: 'signo' })
igual('"1e3" saca la "e"', limpiarCantidad('1e3'), { valor: '13', aviso: 'signo' })
igual('"-99.7" con tope 20 da "20" y avisa primero el signo', limpiarCantidad('-99.7', 20), { valor: '20', aviso: 'signo' })
igual('"12" sin tope queda igual', limpiarCantidad('12'), { valor: '12', aviso: null })

console.log('Cantidades tecleadas')
function teclear(teclas: string[]): string {
  let valor = '', cortado = false
  for (const k of teclas) {
    const r = teclaEnCantidad(cortado, k)
    cortado = r.cortado
    if (r.bloquear) continue
    if (k === 'Backspace') valor = valor.slice(0, -1)
    else if (k.length === 1) valor += k
  }
  return valor
}
igual('"2.5" tecleado da "2", no "25"', teclear(['2', '.', '5']), '2')
igual('"2,75" tecleado da "2"', teclear(['2', ',', '7', '5']), '2')
igual('"-5" tecleado da "5"', teclear(['-', '5']), '5')
igual('después del "." borrar deja escribir de nuevo', teclear(['2', '.', '5', 'Backspace', '3']), '3')
igual('el "." avisa', teclaEnCantidad(false, '.').avisar, true)
igual('Tab y flechas no se bloquean después del "."', teclaEnCantidad(true, 'Tab').bloquear, false)
igual('"3.", Ctrl+A y 8: el 8 vale', teclaEnCantidad(teclaEnCantidad(teclaEnCantidad(true, 'Control').cortado, 'a').cortado, '8').bloquear, false)
igual('"4.", flecha izquierda y 1: el 1 vale', teclaEnCantidad(teclaEnCantidad(true, 'ArrowLeft').cortado, '1').bloquear, false)
igual('"5.", Inicio y 1: el 1 vale', teclaEnCantidad(teclaEnCantidad(true, 'Home').cortado, '1').bloquear, false)
igual('después del "." un "-" sigue bloqueado y la racha sigue', teclaEnCantidad(true, '-'), { bloquear: true, avisar: true, cortado: true })

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
