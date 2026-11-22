/**
 * El control de la IA antes de entregar (lib/calendario/control-previo.ts).
 *
 *     npm run test:calendario
 */
import { enOrden, hayQueControlar, mismasImagenes, paraAvisar, textosDelControl, type ControlPrevio } from './control-previo'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

console.log('Cuándo se pregunta')
// Desde el 21/11/2026 también en la primera entrega (Ivan: "No lo hace en la
// primera entrega, eso está mal"): siempre que haya imágenes. Si no hay nada
// que controlar, el servidor contesta 'sin-pedido' y se manda.
igual('con imágenes, sí (la primera entrega o una ronda que volvió)', hayQueControlar(2), true)
igual('solo con un link, no (no hay imágenes que mirar)', hayQueControlar(0), false)

console.log('Qué dice la pantalla')
igual('en la primera entrega, mientras mira: el pedido', textosDelControl(true).mirando,
  'La IA está mirando si la pieza cumple lo que se pidió…')
igual('en una ronda que volvió, mientras mira: los cambios (como antes)', textosDelControl(false).mirando,
  'La IA está mirando si se hicieron los cambios que se pidieron…')
// Desde el 21/11/2026 el aviso es uno solo («Antes de mandar, revisá esto»):
// ya no hay un «Ojo: parece que falta algo…» para cada caso.
igual('solo el texto de mientras mira', Object.keys(textosDelControl(true)), ['mirando'])

console.log('Qué se le avisa')
const control = (cambios: ControlPrevio['cambios'], estado: ControlPrevio['estado'] = 'listo'): ControlPrevio =>
  ({ estado, cambios, controlId: 'cp-1' })
const c = (numero: number, veredicto: 'hecho' | 'falta' | 'dudoso') => ({ numero, texto: `Marca ${numero}`, veredicto, nota: '' })
igual('lo que falta primero, después lo dudoso, en el orden de las marcas',
  paraAvisar(control([c(3, 'dudoso'), c(2, 'falta'), c(1, 'hecho'), c(4, 'falta')])).map(x => x.numero), [2, 4, 3])
igual('todo hecho: nada (se manda solo)', paraAvisar(control([c(1, 'hecho'), c(2, 'hecho')])), [])
igual('sin pedido: nada', paraAvisar(control([], 'sin-pedido')), [])
igual('si la IA no estuvo: nada (se manda igual)', paraAvisar(control([c(1, 'falta')], 'no-disponible')), [])
igual('del pedido inicial: igual, punto por punto',
  paraAvisar({ ...control([c(1, 'hecho'), c(2, 'falta'), c(3, 'dudoso')]), inicial: true }).map(x => x.numero), [2, 3])
igual('sin respuesta: nada', paraAvisar(null), [])
igual('un veredicto que no se conoce no se avisa', paraAvisar(control([
  c(1, 'falta'), { numero: 2, texto: 'x', veredicto: 'no_aplica' as 'falta', nota: '' }])).map(x => x.numero), [1])
// Quien aprueba ve todo, en el mismo orden que el aviso y con lo hecho al final (21/11/2026).
igual('en orden: lo que falta, lo dudoso y lo hecho, cada grupo por número',
  enOrden([c(3, 'hecho'), c(4, 'dudoso'), c(2, 'falta'), c(1, 'hecho'), c(5, 'falta')]).map(x => `${x.numero}${x.veredicto[0]}`),
  ['2f', '5f', '4d', '1h', '3h'])
const entrada = [c(2, 'hecho'), c(1, 'falta')]
enOrden(entrada)
igual('no toca la lista de entrada', entrada.map(x => x.numero), [2, 1])

console.log('Las mismas imágenes')
const a = new Blob(['a']), b = new Blob(['b'])
igual('las mismas, en el mismo orden', mismasImagenes([a, b], [a, b]), true)
igual('en otro orden, no', mismasImagenes([a, b], [b, a]), false)
igual('una más, no', mismasImagenes([a], [a, b]), false)
igual('otra igual por dentro pero preparada de nuevo, no', mismasImagenes([a], [new Blob(['a'])]), false)

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
