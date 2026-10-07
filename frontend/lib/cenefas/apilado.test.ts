/**
 * Pruebas del orden de apilado del canvas.
 *
 * El caso que importa es el real: en "Marcas Exclusivas-202608-A4" la línea
 * del tachado (z 6) va debajo del cuadro del precio regular (z 8) y su caja
 * cae entera adentro de ese cuadro. Con el orden del archivo, el precio
 * recibía todos los clicks y la línea no se podía mover.
 */
import { esLineaSuelta, ordenDeApilado } from './apilado'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const fondo   = { id: 'fondo',  z_index: 0, type: 'image' }
const oferta  = { id: 'oferta', z_index: 1, type: 'text' }
const linea   = { id: 'linea',  z_index: 6, type: 'shape', style: { geometry: 'line', flip_v: true } }
const descr   = { id: 'descr',  z_index: 7, type: 'text' }
const regular = { id: 'regular', z_index: 8, type: 'text' }
const unidad  = { id: 'unidad', z_index: 9, type: 'text' }
const cuadroConFondo = { id: 'cocarda', z_index: 3, type: 'shape', style: { background_color: '#ff0000' } }

console.log('\nqué es una línea suelta')
ok('un shape con geometry line lo es', esLineaSuelta(linea))
ok('un shape con relleno no lo es', !esLineaSuelta(cuadroConFondo))
ok('un texto no lo es', !esLineaSuelta(regular))
ok('sin style no revienta', !esLineaSuelta({ z_index: 0, type: 'shape' }))
ok('style null no revienta', !esLineaSuelta({ z_index: 0, type: 'shape', style: null }))

console.log('\nla línea del tachado queda arriba del cuadro del precio regular')
const desordenados = [regular, linea, unidad, fondo, descr, oferta]
igual('orden: por z_index y la línea al final',
  ordenDeApilado(desordenados).map((c) => c.id),
  ['fondo', 'oferta', 'descr', 'regular', 'unidad', 'linea'])
ok('la línea va después del precio regular aunque su z_index sea menor',
  ordenDeApilado(desordenados).findIndex((c) => c.id === 'linea') >
  ordenDeApilado(desordenados).findIndex((c) => c.id === 'regular'))

console.log('\nsin líneas, el orden es el de siempre')
igual('solo z_index', ordenDeApilado([unidad, fondo, cuadroConFondo, oferta]).map((c) => c.id),
  ['fondo', 'oferta', 'cocarda', 'unidad'])
ok('un cuadro con relleno NO sube: sigue en su z_index',
  ordenDeApilado([unidad, cuadroConFondo]).map((c) => c.id).join() === 'cocarda,unidad')

console.log('\nvarias líneas (3xA4): entre ellas, por z_index')
const l1 = { id: 'l1', z_index: 20, type: 'shape', style: { geometry: 'line' } }
const l2 = { id: 'l2', z_index: 5,  type: 'shape', style: { geometry: 'line' } }
igual('las tres al final y ordenadas', ordenDeApilado([l1, regular, l2, linea]).map((c) => c.id),
  ['regular', 'l2', 'linea', 'l1'])

console.log('\nno toca lo que recibe')
const original = [regular, linea, fondo]
const copia = [...original]
ordenDeApilado(original)
igual('la lista queda igual', original.map((c) => c.id), copia.map((c) => c.id))
ok('los objetos son los mismos (no clona)', ordenDeApilado(original)[0] === fondo)

console.log(fallos ? `\n${fallos} prueba(s) fallaron` : '\ntodo ok')
if (fallos) process.exit(1)
