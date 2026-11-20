/**
 * Un aviso contado desde la fecha de un envío (lib/calendario/avisos.ts).
 *
 *     npm run test:calendario
 */
import { desdeQue, enviosDe, fechaBase, nombreDeEnvio } from './avisos'
import type { Pieza } from './tipos'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const pieza = (id: string, area: Pieza['area'], desde?: string): Pieza =>
  ({ id, area, formato: area === 'email' ? 'Mailing digital' : 'Recordatorio', desde, estado: 'pendiente' })
const accion = {
  desde: '2026-11-22',
  piezas: [
    pieza('push', 'push', '2026-11-28'),
    pieza('web', 'web-home'),
    pieza('mail', 'email', '2026-11-25'),
    pieza('wa', 'whatsapp'),
  ],
}

console.log('Los envíos de la acción')
igual('solo email, WhatsApp y push, por fecha (sin fecha = con la acción)',
  enviosDe(accion).map(p => p.id), ['wa', 'mail', 'push'])
igual('una acción sin piezas', enviosDe({ desde: '2026-11-22' }), [])

console.log('Desde qué fecha')
igual('sin envío, desde que arranca', fechaBase(accion, null), '2026-11-22')
igual('con envío, desde que sale', fechaBase(accion, 'mail'), '2026-11-25')
igual('un envío sin fecha sale con la acción', fechaBase(accion, 'wa'), '2026-11-22')
igual('un envío que ya no está, desde que arranca', fechaBase(accion, 'borrado'), '2026-11-22')

console.log('Cómo se lee')
igual('el nombre', nombreDeEnvio(accion.piezas[2]), 'Email · Mailing digital')
igual('de un envío', desdeQue(accion, { piezaId: 'mail' }, false), 'antes del envío Email · Mailing digital')
igual('de la acción', desdeQue(accion, {}, false), 'antes de que arranque')
igual('de un envío suelto', desdeQue(accion, {}, true), 'antes de que salga')

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
