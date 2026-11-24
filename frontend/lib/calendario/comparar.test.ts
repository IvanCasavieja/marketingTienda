/**
 * Qué imagen de la ronda anterior se ve al comparar (lib/calendario/comparar.ts).
 *
 *     npm run test:calendario
 */
import { imagenParaComparar } from './comparar'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const ronda1 = [{ id: 'a1', orden: 0 }, { id: 'a2', orden: 1 }]

console.log('Comparar con la ronda anterior')
igual('la del mismo lugar', imagenParaComparar(ronda1, 1, null), { id: 'a2', numero: 2, sinPareja: false })
igual('la ronda 2 trae una imagen 3 y la 1 tenía dos: la primera, avisando',
  imagenParaComparar(ronda1, 2, null), { id: 'a1', numero: 1, sinPareja: true })
igual('la que eligió la persona en la tira de «Antes»', imagenParaComparar(ronda1, 0, 'a2'),
  { id: 'a2', numero: 2, sinPareja: false })
igual('elegida sin pareja: ya no avisa', imagenParaComparar(ronda1, 2, 'a2'), { id: 'a2', numero: 2, sinPareja: false })
igual('una elegida que no es de esa ronda no cuenta', imagenParaComparar(ronda1, 0, 'zz'),
  { id: 'a1', numero: 1, sinPareja: false })
igual('la ronda anterior sin imágenes (vino con un link)', imagenParaComparar([], 0, null),
  { id: null, numero: null, sinPareja: false })
igual('el número es el de su miniatura, no el orden guardado',
  imagenParaComparar([{ id: 'b1', orden: 3 }, { id: 'b2', orden: 7 }], 7, null), { id: 'b2', numero: 2, sinPareja: false })

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
