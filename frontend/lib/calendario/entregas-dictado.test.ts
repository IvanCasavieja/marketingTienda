/**
 * Pruebas del brief dictado dentro de las entregas. Se corren con las demás:
 *
 *     npm run test:calendario
 */
import { briefDesdeDictado, TIPO_PARA_DICTADO } from './entregas-dictado'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

console.log('entregas-dictado')
const cenefa = briefDesdeDictado('cenefa', {}, {
  campos: [
    { clave: 'medidas', etiqueta: 'Medidas', valor: '30 x 10 cm' },
    { clave: 'cantidad', etiqueta: 'Cantidad', valor: '200' },
    { clave: 'precio_mecanica', etiqueta: 'Precio / mecánica', valor: '2x1 en vinos' },
    { clave: 'vigencia', etiqueta: 'Vigencia', valor: 'del 28/11 al 30/11' },
    { clave: 'legales', etiqueta: 'Legales', valor: null },
    { clave: 'locales', etiqueta: 'Locales', valor: '40 locales' },
  ],
  notas: 'Que se vea el logo nuevo',
})
igual('lo que encaja va a su campo', [cenefa.medidas, cenefa.cantidad, cenefa.precio], ['30 x 10 cm', '200', '2x1 en vinos'])
igual('las fechas dichas en texto y lo que no tiene campo van al detalle', cenefa.detalle,
  'Vigencia: del 28/11 al 30/11\nLocales: 40 locales\nQue se vea el logo nuevo')
ok('lo que no se dijo no se inventa', !('legales' in cenefa))

const pisando = briefDesdeDictado('cenefa', { medidas: 'A4', detalle: 'Ojo con el color' }, {
  campos: [{ clave: 'medidas', etiqueta: 'Medidas', valor: '30 x 10 cm' }, { clave: 'cantidad', etiqueta: 'Cantidad', valor: 'cinco por local' }],
  notas: null,
})
igual('lo que ya se había escrito no se pisa: lo dictado va al detalle', [pisando.medidas, pisando.detalle],
  ['A4', 'Ojo con el color\nMedidas: 30 x 10 cm\nCantidad: cinco por local'])

const banner = briefDesdeDictado('banner', {}, {
  campos: [{ clave: 'link', etiqueta: 'Link', valor: 'la landing de vinos' }, { clave: 'medidas', etiqueta: 'Medidas', valor: '1920 x 600 px' }],
  notas: null,
})
igual('un link que no es una dirección va al detalle', [banner.link, banner.medidas, banner.detalle],
  [undefined, '1920 x 600 px', 'Link: la landing de vinos'])
igual('el banner se llama distinto en el dictado', TIPO_PARA_DICTADO.banner, 'banner_web')

const redes = briefDesdeDictado('redes', {}, {
  campos: [{ clave: 'formato', etiqueta: 'Formato', valor: 'reel' }, { clave: 'copy', etiqueta: 'Copy', valor: '¡Llegó el Ciberlunes!' }],
  notas: null,
})
igual('las opciones se reconocen sin importar mayúsculas', [redes.formato, redes.copy], ['Reel', '¡Llegó el Ciberlunes!'])

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\nentregas-dictado: todo bien')
