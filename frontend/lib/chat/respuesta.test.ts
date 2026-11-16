/**
 * Pruebas de cómo se muestra y se copia lo que contesta Don Tino:
 *
 *     npm run test:chat
 *
 * Lo que se fija: solo se tocan los links de la propia app (los que abren una
 * acción del calendario), el markdown del estado para gerencia se ve con sus
 * títulos y viñetas, y lo que se copia sirve para pegar en un mail.
 */
import { htmlParaCopiar, prepararMarkdown, rutaInterna, textoParaCopiar } from './respuesta'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const ORIGEN = 'https://core.tiendainglesa.com.uy'

console.log('\nlinks que se pueden tocar')
igual('una acción del calendario', rutaInterna('/calendario?accion=br-123', ORIGEN), '/calendario?accion=br-123')
igual('una dirección completa de este sitio', rutaInterna(`${ORIGEN}/calendario?accion=br-1`, ORIGEN), '/calendario?accion=br-1')
igual('sin saber el sitio, una ruta igual anda', rutaInterna('/mis-tareas', null), '/mis-tareas')
igual('otro sitio, no', rutaInterna('https://otro.com/x', ORIGEN), null)
igual('"//otro.sitio" no es una ruta', rutaInterna('//otro.com/x', ORIGEN), null)
igual('"/\\otro.sitio" tampoco', rutaInterna('/\\otro.com/x', ORIGEN), null)
igual('con un tab adentro tampoco', rutaInterna('/\t/otro.com', ORIGEN), null)
igual('javascript:, nunca', rutaInterna('javascript:alert(1)', ORIGEN), null)
igual('data:, nunca', rutaInterna('data:text/html,hola', ORIGEN), null)
igual('vacío', rutaInterna('', ORIGEN), null)

console.log('\nmarkdown del estado para gerencia')
const gerencia = '**Resumen**\n- Ciberlunes viene bien.\n**Riesgos**\n- Cenefas sin aprobar.'
igual('cada título arranca un bloque aparte', prepararMarkdown(gerencia),
  '**Resumen**  \n- Ciberlunes viene bien.\n\n**Riesgos**  \n- Cenefas sin aprobar.')
igual('un salto simple queda como salto', prepararMarkdown('Hola\nchau'), 'Hola  \nchau')
igual('un párrafo aparte sigue aparte', prepararMarkdown('Hola\n\nchau'), 'Hola\n\nchau')

console.log('\nlo que se copia')
const respuesta = '**Resumen**\n- [Ciberlunes](/calendario?accion=br-1) arranca el 28/11.\n- Ver [la guía](https://otro.com/guia).'
igual('texto: sin asteriscos, el link de la app queda en el nombre', textoParaCopiar(respuesta, ORIGEN),
  'Resumen\n• Ciberlunes arranca el 28/11.\n• Ver la guía (https://otro.com/guia).')
igual('html: negritas y viñetas, sin links ni etiquetas del modelo', htmlParaCopiar(respuesta + '\n<script>x</script>', ORIGEN),
  '<p><b>Resumen</b></p><ul><li>Ciberlunes arranca el 28/11.</li><li>Ver la guía (https://otro.com/guia).</li></ul>'
  + '<p>&lt;script&gt;x&lt;/script&gt;</p>')

console.log(fallos ? `\n${fallos} prueba(s) fallaron\n` : '\nTodo bien\n')
if (fallos) process.exit(1)
