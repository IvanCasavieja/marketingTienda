/**
 * Qué hacer con lo que contesta el servidor sobre una corrida de cenefas
 * (lib/cenefas/corrida.ts).
 *
 *     npm run test:cenefas
 *
 * El caso que importa es H-008 (26/11/2026): generar desde el editor terminaba
 * siempre en «Error en la generación — Error desconocido». La corrida no había
 * fallado: estaba lista para revisar ("preview") y la pantalla no lo entendía.
 */
import { CONSULTA_CADA_MS, CONSULTAS_FALLIDAS_TOLERADAS, queSigue } from './corrida'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const definicion = { name: 'Cenefa A4', components: [], rules: [], variables: [] }

console.log('\nmientras se arma la revisión')
igual('en cola: se espera', queSigue({ status: 'pending' }, 'revision'), { tipo: 'esperar' })
igual('leyendo el Excel: se espera', queSigue({ status: 'running' }, 'revision'), { tipo: 'esperar' })
igual('lista para revisar NO es un error (H-008): se muestra',
  queSigue({ status: 'preview', template_def: definicion }, 'revision'), { tipo: 'lista' })
igual('lista pero sin nada que dibujar: no aparece sola, se corta',
  queSigue({ status: 'preview' }, 'revision'), { tipo: 'error', motivo: null })
igual('falló: con el motivo que manda el servidor',
  queSigue({ status: 'error', validation_report: { error: 'Template 123 no encontrado' } }, 'revision'),
  { tipo: 'error', motivo: 'Template 123 no encontrado' })
igual('ya generada (nadie más la confirma acá): se corta, no se espera para siempre',
  queSigue({ status: 'done' }, 'revision'), { tipo: 'error', motivo: null })

console.log('\nmientras se genera el archivo (ya confirmada)')
igual('generando: se espera', queSigue({ status: 'running' }, 'archivo'), { tipo: 'esperar' })
igual('generada: se baja', queSigue({ status: 'done' }, 'archivo'), { tipo: 'lista' })
igual('falló el render: con el motivo',
  queSigue({ status: 'error', validation_report: { error: 'La generación del archivo superó el límite de 600s.' } }, 'archivo'),
  { tipo: 'error', motivo: 'La generación del archivo superó el límite de 600s.' })
igual('de vuelta en revisión: no cambia sola, se corta',
  queSigue({ status: 'preview', template_def: definicion }, 'archivo'), { tipo: 'error', motivo: null })

console.log('\nun estado que la pantalla no conoce corta la espera')
igual('en la revisión', queSigue({ status: 'cancelada' }, 'revision'), { tipo: 'error', motivo: null })
igual('en el archivo', queSigue({ status: 'cancelada' }, 'archivo'), { tipo: 'error', motivo: null })

console.log('\nel motivo del error')
igual('sin informe: sin motivo (la pantalla pone su texto)', queSigue({ status: 'error' }, 'archivo'),
  { tipo: 'error', motivo: null })
igual('informe nulo', queSigue({ status: 'error', validation_report: null }, 'archivo'), { tipo: 'error', motivo: null })
igual('motivo en blanco', queSigue({ status: 'error', validation_report: { error: '   ' } }, 'archivo'),
  { tipo: 'error', motivo: null })
igual('motivo que no es texto', queSigue({ status: 'error', validation_report: { error: 42 } }, 'archivo'),
  { tipo: 'error', motivo: null })
igual('se recorta', queSigue({ status: 'error', validation_report: { error: '  Excel vacío \n' } }, 'archivo'),
  { tipo: 'error', motivo: 'Excel vacío' })

console.log('\nlas consultas que fallan mientras se arma la revisión')
// Un corte de unos segundos no tiene que tirar la corrida, pero un servidor que
// no contesta nunca no puede dejar la pantalla girando sin decir nada.
const aguante = CONSULTAS_FALLIDAS_TOLERADAS * CONSULTA_CADA_MS
igual('un corte de unos segundos se aguanta', aguante >= 10_000, true)
igual('un servidor que no contesta se avisa antes del minuto', aguante <= 60_000, true)

console.log(fallos ? `\n${fallos} prueba(s) fallaron` : '\ntodo ok')
if (fallos) process.exit(1)
