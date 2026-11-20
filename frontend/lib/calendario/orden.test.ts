/**
 * Ordenar las tareas arrastrándolas (lib/calendario/orden.ts).
 *
 *     npm run test:calendario
 */
import { conOrden, correrUnLugar, moverEntreHermanas } from './orden'
import type { Tarea } from './tipos'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const ids = ['a', 'b', 'c', 'd']
console.log('Mover entre hermanas')
igual('la última, antes de la primera', moverEntreHermanas(ids, 'd', 'a', true), ['d', 'a', 'b', 'c'])
igual('la primera, después de la tercera', moverEntreHermanas(ids, 'a', 'c', false), ['b', 'c', 'a', 'd'])
igual('después de la última', moverEntreHermanas(ids, 'b', 'd', false), ['a', 'c', 'd', 'b'])
igual('sobre sí misma, nada', moverEntreHermanas(ids, 'b', 'b', true), ids)
igual('una que no es hermana, nada', moverEntreHermanas(ids, 'x', 'a', true), ids)

console.log('Con el teclado')
igual('una para arriba', correrUnLugar(ids, 'c', -1), ['a', 'c', 'b', 'd'])
igual('una para abajo', correrUnLugar(ids, 'a', 1), ['b', 'a', 'c', 'd'])
igual('la primera no sube más', correrUnLugar(ids, 'a', -1), ids)
igual('la última no baja más', correrUnLugar(ids, 'd', 1), ids)

console.log('La lista de la acción')
const t = (id: string, parentId: string | null = null) => ({ id, parentId, titulo: id }) as unknown as Tarea
// Raíces a, b, c; b tiene las hijas b1 y b2 (van detrás, en el orden de alta).
const tareas = [t('a'), t('b'), t('c'), t('b1', 'b'), t('b2', 'b')]
igual('las raíces cambian de lugar entre ellas; las hijas, quietas',
  conOrden(tareas, ['c', 'a', 'b']).map(x => x.id), ['c', 'a', 'b', 'b1', 'b2'])
igual('las hijas, entre ellas', conOrden(tareas, ['b2', 'b1']).map(x => x.id), ['a', 'b', 'c', 'b2', 'b1'])
igual('una que borraron mientras tanto no rompe nada',
  conOrden(tareas, ['c', 'zz', 'a']).map(x => x.id), ['c', 'b', 'a', 'b1', 'b2'])

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
