/**
 * Pruebas de las categorías. Se corren con las demás:
 *
 *     npm run test:calendario
 *
 * La categoría de una acción es el texto de su fila del calendario, y ese
 * texto viene del Excel escrito de cualquier manera ("MEGA EVENTO", "Mailing
 * GRAL"). Lo que se fija acá es que se reconozca igual sin que importen
 * mayúsculas, tildes ni espacios: de eso depende qué cocarda se ve, qué acción
 * cuenta como "sin categoría" y que el selector de la ficha no pierda la que
 * la acción ya tiene.
 */
import {
  BANDAS_RETIRADAS, SIN_CATEGORIA, categoriasParaElegir, esBandaRetirada, esSinCategoria, nivelDeCategoria,
} from './categorias'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

console.log('\nsin categoría')
ok('sin nada cargado (null)', esSinCategoria(null))
ok('sin nada cargado (undefined)', esSinCategoria(undefined))
ok('con el texto vacío', esSinCategoria(''))
ok('"Sin categoría", como se guarda', esSinCategoria('Sin categoría') && esSinCategoria(SIN_CATEGORIA))
ok('en mayúsculas y sin tilde', esSinCategoria('SIN CATEGORIA'))
ok('con espacios de más', esSinCategoria(' sin  categoría '))
ok('"Sin mailing" es una categoría, no la falta de una', !esSinCategoria('Sin mailing'))
ok('"MEGA EVENTO" tampoco', !esSinCategoria('MEGA EVENTO'))

console.log('\ncuánto pesa cada categoría')
igual('"MEGA EVENTO" es la que más', nivelDeCategoria('MEGA EVENTO'), 'mega')
igual('"Mailing GRAL" es el evento general', nivelDeCategoria('Mailing GRAL'), 'general')
igual('"Especiales"', nivelDeCategoria('Especiales'), 'especial')
igual('todas las demás van en gris',
  ['Sin mailing', 'ACTIVIDADES TACTICAS', 'Campañas'].map(c => nivelDeCategoria(c)), ['comun', 'comun', 'comun'])
igual('sin categoría no tiene peso: no lleva cocarda',
  [SIN_CATEGORIA, 'SIN CATEGORIA', '', null, undefined].map(c => nivelDeCategoria(c)), ['sin', 'sin', 'sin', 'sin', 'sin'])
igual('no importan las mayúsculas',
  ['mega evento', 'Mega Evento', 'MAILING GRAL', 'mailing gral', 'ESPECIALES', 'especiales'].map(c => nivelDeCategoria(c)),
  ['mega', 'mega', 'general', 'general', 'especial', 'especial'])
igual('ni las tildes', ['MÉGA EVENTO', 'Mailing Grál', 'Espéciales'].map(c => nivelDeCategoria(c)), ['mega', 'general', 'especial'])
igual('ni los espacios de más',
  ['  MEGA   EVENTO ', 'Mailing  GRAL', ' Especiales'].map(c => nivelDeCategoria(c)), ['mega', 'general', 'especial'])
igual('parecerse no alcanza', ['MEGA', 'Mailing NF', 'Especial'].map(c => nivelDeCategoria(c)), ['comun', 'comun', 'comun'])

console.log('\nfilas retiradas')
igual('la única retirada es "TIENDA FARMA"', BANDAS_RETIRADAS, ['TIENDA FARMA'])
ok('"TIENDA FARMA" está retirada', esBandaRetirada('TIENDA FARMA'))
ok('escrita "Tienda Farma" también', esBandaRetirada('Tienda Farma'))
ok('"FARMA" sola no', !esBandaRetirada('FARMA'))
ok('"MEGA EVENTO" no', !esBandaRetirada('MEGA EVENTO'))

console.log('\nlo que se ofrece al elegir la categoría')
const delMundo = ['MEGA EVENTO', 'Mailing GRAL', 'Especiales', 'Sin mailing']
const base = [SIN_CATEGORIA, ...delMundo]
igual('"Sin categoría" primero, y después las del mundo en su orden', categoriasParaElegir(delMundo), base)
igual('la que tiene la acción, si ya no figura, se suma al final, una sola vez',
  categoriasParaElegir(delMundo, 'TIENDA FARMA'), [...base, 'TIENDA FARMA'])
igual('si la que tiene ya está en la lista, no se suma nada', categoriasParaElegir(delMundo, 'Especiales'), base)
igual('si no tiene categoría, tampoco',
  [SIN_CATEGORIA, 'SIN CATEGORIA', '', null, undefined].map(actual => categoriasParaElegir(delMundo, actual)),
  [base, base, base, base, base])
igual('un mundo que trae "Sin categoría" en su lista no la muestra dos veces',
  categoriasParaElegir([SIN_CATEGORIA, ...delMundo]), base)
igual('no toca la lista que recibe', delMundo, ['MEGA EVENTO', 'Mailing GRAL', 'Especiales', 'Sin mailing'])

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)
