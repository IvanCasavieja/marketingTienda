/**
 * Pruebas del zoom y las medidas de la rejilla.
 *
 * La primera es la que importa: el bug era que las columnas se declaraban
 * `minmax(${zoom}px, 1fr)`. El `1fr` las estira para llenar el contenedor, así
 * que el zoom solo funcionaba de un lado — al alejar, la rejilla se veía
 * idéntica porque el `1fr` repartía igual todo el ancho disponible.
 */
import {
  ANCHO_ETIQUETA, ZOOMS, ZOOM_MAX, ZOOM_MIN, ZOOM_POR_DEFECTO,
  anchoDias, anchoTotal, columnasDe, limitarZoom, porcentajeZoom,
  sePuedeAcercar, sePuedeAlejar, siguienteZoom, zoomParaAncho,
} from './rejilla'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

console.log('\ncolumnas: ancho fijo, nunca 1fr')
igual('30 días al zoom natural', columnasDe(30, 38), 'repeat(30, 38px)')
ok('no queda ni un fr', ZOOMS.every(z => !columnasDe(31, z).includes('fr')))
ok('no queda ningún minmax', ZOOMS.every(z => !columnasDe(31, z).includes('minmax')))

console.log('\ncada paso de zoom tiene que cambiar el ancho de verdad')
const anchos = ZOOMS.map(z => anchoDias(30, z))
igual('los 7 niveles dan 7 anchos distintos', new Set(anchos).size, ZOOMS.length)
ok('y siempre crecen', anchos.every((a, i) => i === 0 || a > anchos[i - 1]), anchos.join(' '))
// El bug viejo: en una pantalla de 1920 el contenedor daba ~1536px para 30 días,
// o sea 51px por columna, y todo zoom por debajo de eso se veía igual.
const anchoViejo = 1536
const comoSeVeiaAntes = ZOOMS.map(z => Math.max(anchoDias(30, z), anchoViejo))
ok('antes 5 de los 7 niveles se veían idénticos',
  new Set(comoSeVeiaAntes).size === 3, `antes daban ${new Set(comoSeVeiaAntes).size} anchos distintos`)

console.log('\nancho total')
igual('etiquetas + días', anchoTotal(30, 38), ANCHO_ETIQUETA + 30 * 38)
igual('mes de 31', anchoTotal(31, 20), ANCHO_ETIQUETA + 620)

console.log('\npasos de zoom')
igual('desde el natural, acercar', siguienteZoom(38, 1), 48)
igual('desde el natural, alejar', siguienteZoom(38, -1), 32)
igual('no se pasa del máximo', siguienteZoom(ZOOM_MAX, 1), ZOOM_MAX)
igual('no se pasa del mínimo', siguienteZoom(ZOOM_MIN, -1), ZOOM_MIN)
// Después de "ajustar al ancho" el zoom queda en un número que no está en la lista
igual('desde 41 (fuera de la lista), acercar da 48', siguienteZoom(41, 1), 48)
igual('desde 41, alejar da 38', siguienteZoom(41, -1), 38)
igual('desde 35, acercar da 38', siguienteZoom(35, 1), 38)
igual('desde 35, alejar da 32', siguienteZoom(35, -1), 32)
ok('alejar siempre achica', [20, 21, 35, 41, 55, 76, 90].every(z => siguienteZoom(z, -1) < z || z <= ZOOM_MIN))
ok('acercar siempre agranda', [10, 20, 35, 41, 55, 60].every(z => siguienteZoom(z, 1) > z))

console.log('\nbotones habilitados')
ok('en el máximo no se puede acercar', !sePuedeAcercar(ZOOM_MAX))
ok('en el mínimo no se puede alejar', !sePuedeAlejar(ZOOM_MIN))
ok('en el natural se puede para los dos lados', sePuedeAcercar(38) && sePuedeAlejar(38))

console.log('\najustar al ancho')
// caja de 1536px, 30 días: (1536 - 232) / 30 = 43.46 -> 43
igual('pantalla ancha, 30 días', zoomParaAncho(1536, 30), 43)
ok('y con eso entra sin scroll', anchoTotal(30, zoomParaAncho(1536, 30)) <= 1536,
  `da ${anchoTotal(30, zoomParaAncho(1536, 30))} contra 1536`)
// notebook 1366: caja util ~1302
igual('notebook de 1366, 31 días', zoomParaAncho(1302, 31), 34)
ok('entra sin scroll', anchoTotal(31, zoomParaAncho(1302, 31)) <= 1302)
ok('en pantalla chica cae al mínimo, no a negativo', zoomParaAncho(400, 31) === ZOOM_MIN)
ok('en pantalla enorme no se pasa del máximo', zoomParaAncho(5000, 28) === ZOOM_MAX)
ok('nunca devuelve algo fuera de rango',
  [300, 800, 1302, 1536, 1800, 4000].every(a => {
    const z = zoomParaAncho(a, 31)
    return z >= ZOOM_MIN && z <= ZOOM_MAX
  }))

console.log('\nlímites y porcentaje')
igual('recorta por abajo', limitarZoom(5), ZOOM_MIN)
igual('recorta por arriba', limitarZoom(999), ZOOM_MAX)
igual('redondea', limitarZoom(38.7), 39)
igual('el natural es 100%', porcentajeZoom(ZOOM_POR_DEFECTO), 100)
igual('el doble es 200%', porcentajeZoom(76), 200)
igual('el mínimo', porcentajeZoom(20), 53)

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)
