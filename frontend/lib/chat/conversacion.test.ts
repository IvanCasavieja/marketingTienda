/**
 * La conversación con Don Tino y su burbuja (lib/chat/conversacion.ts).
 *
 *     npm run test:chat
 */
import { historialParaEnviar, muestraBurbuja, type MensajeDonTino } from './conversacion'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const m = (role: 'bot' | 'user', text: string): MensajeDonTino => ({ role, text, ts: 0 })

console.log('Lo que viaja con cada pregunta')
igual('sin el saludo ni la pregunta nueva', historialParaEnviar([m('bot', 'Hola'), m('user', 'a'), m('bot', 'b'), m('user', 'c')]),
  [{ role: 'user', content: 'a' }, { role: 'assistant', content: 'b' }])
igual('la primera pregunta va sola', historialParaEnviar([m('bot', 'Hola'), m('user', 'a')]), [])
const larga = [m('bot', 'Hola'), ...Array.from({ length: 30 }, (_, i) => m(i % 2 ? 'bot' : 'user', `${i}`))]
igual('hasta 10 mensajes, los últimos', historialParaEnviar(larga).map(x => x.content),
  ['19', '20', '21', '22', '23', '24', '25', '26', '27', '28'])

console.log('Dónde va la burbuja')
const equipo = { is_superuser: false, permissions: ['calendario.view', 'ai.don_tino'] }
igual('en el calendario, sí', muestraBurbuja('/calendario', equipo), true)
igual('en Inicio no (ahí el chat está grande)', muestraBurbuja('/home', equipo), false)
igual('sin el permiso, no', muestraBurbuja('/calendario', { is_superuser: false, permissions: ['calendario.view'] }), false)
igual('superadmin, sí', muestraBurbuja('/precios', { is_superuser: true, permissions: [] }), true)
igual('la agencia, no', muestraBurbuja('/entregas', { ...equipo, es_externo: true }), false)
igual('sin usuario, no', muestraBurbuja('/calendario', null), false)

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\nconversacion: todo bien')
