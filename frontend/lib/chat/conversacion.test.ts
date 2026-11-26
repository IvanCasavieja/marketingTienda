/**
 * La conversación con Don Tino y su burbuja (lib/chat/conversacion.ts).
 *
 *     npm run test:chat
 */
import {
  LUGAR_DE_DON_TINO, LUGAR_PARA_LA_BURBUJA, LUGAR_SIN_BURBUJA, historialParaEnviar, lugarDeAbajo, muestraBurbuja,
  type MensajeDonTino,
} from './conversacion'

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
igual('superadmin, sí', muestraBurbuja('/calendario', { is_superuser: true, permissions: [] }), true)
// Una sola burbuja por pantalla (25/11/2026): donde hay ayudante propio, va ese.
for (const p of ['/precios', '/materiales/cenefas', '/materiales/convertidor', '/facturacion', '/analytics']) {
  igual(`en ${p} va su ayudante, no Don Tino`, muestraBurbuja(p, equipo), false)
}
igual('en una subpantalla sin ayudante, Don Tino sí', muestraBurbuja('/materiales/cenefas/v2/generar', equipo), true)
igual('la agencia, no', muestraBurbuja('/entregas', { ...equipo, es_externo: true }), false)
igual('sin usuario, no', muestraBurbuja('/calendario', null), false)

// H-025 (26/11/2026): la burbuja tapaba «Confirmar pedido» del local,
// «Validar placas» y el «Enviar» de La Triada. Donde hay un botón flotante,
// la pantalla deja lugar abajo para que lo último quede arriba de él.
console.log('La pantalla le deja lugar a la burbuja')
const local = { is_superuser: false, permissions: ['ai.don_tino'] }
const enMiPedido = lugarDeAbajo('/redexpres/mi-pedido', local)
igual('en Mi pedido del local (Don Tino), deja lugar', enMiPedido, LUGAR_PARA_LA_BURBUJA)
igual('en Validación de RRSS, también', lugarDeAbajo('/redes-sociales/validacion', equipo), LUGAR_PARA_LA_BURBUJA)
igual('en La Triada, con el ayudante de la pantalla, también', lugarDeAbajo('/analytics', equipo), LUGAR_PARA_LA_BURBUJA)
igual('en Inicio, sin burbuja, lo de siempre', lugarDeAbajo('/home', equipo), LUGAR_SIN_BURBUJA)
igual('la agencia, sin burbuja, lo de siempre', lugarDeAbajo('/entregas', { ...equipo, es_externo: true }), LUGAR_SIN_BURBUJA)

// Y que alcance: lo que queda libre abajo tiene que llegar más arriba que el
// botón flotante más alto (los ayudantes miden 4rem, w-16; Don Tino, 3,5rem).
// Si alguien sube la burbuja sin agrandar el lugar, esto avisa.
/** Lo que dice una clase de Tailwind, en rem: «pb-24» → 6, «md:bottom-5» → 1.25,
 *  «bottom-[calc(5.75rem+env(safe-area-inset-bottom))]» → 5.75. */
function rem(clases: string, prefijo: string): number {
  const valor = clases.split(' ').find(c => c.startsWith(prefijo))?.slice(prefijo.length) ?? ''
  const aMano = /^\[calc\(([\d.]+)rem\+env\(safe-area-inset-bottom\)\)\]$/.exec(valor)
  return aMano ? Number(aMano[1]) : Number(valor) / 4
}
const ALTO_DEL_AYUDANTE = 4
const aireArriba = (enPantalla: string, enBurbuja: string) =>
  rem(enMiPedido, enPantalla) - (rem(LUGAR_DE_DON_TINO, enBurbuja) + ALTO_DEL_AYUDANTE)
igual('en el celular, «Confirmar pedido» puede quedar arriba de la burbuja', aireArriba('pb-', 'bottom-') >= 0.5, true)
igual('en la notebook, también', aireArriba('md:pb-', 'md:bottom-') >= 0.5, true)

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\nconversacion: todo bien')
