/**
 * Pruebas de los choques entre acciones. Se corren con las demás:
 *
 *     npm run test:calendario
 */
import { choquesDe } from './choques'
import type { BarraGuardada, Pieza } from './tipos'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

let n = 0
function accion(nombre: string, desde: string, hasta: string, extra: Partial<BarraGuardada> = {}): BarraGuardada {
  return { id: `a${++n}`, mundo: 'tienda_inglesa', seccion: 'comercial', banda: 'MEGA EVENTO', carril: 0, nombre, color: null, desde, hasta, ...extra }
}
const mailing = (desde?: string): Pieza => ({ id: `p${++n}`, area: 'email', formato: 'Mailing', estado: 'pendiente', ...(desde ? { desde } : {}) })

console.log('choques')
const black = accion('Black Week', '2026-11-23', '2026-11-29')
const ciber = accion('Ciberlunes', '2026-11-28', '2026-11-30')
const vino = accion('Semana del Vino', '2026-11-28', '2026-11-30', { banda: 'Especiales' })
igual('dos mega eventos que se pisan', choquesDe(black, [black, ciber, vino]).map(c => c.texto),
  ['Se superpone con otro mega evento: Ciberlunes (del 28 de noviembre al 30 de noviembre de 2026)'])
igual('una acción común no choca con un mega', choquesDe(vino, [black, ciber, vino]), [])
igual('mega eventos que no se tocan no chocan',
  choquesDe(accion('A', '2026-12-01', '2026-12-03'), [accion('B', '2026-12-04', '2026-12-06')]), [])
igual('otro mundo no cuenta',
  choquesDe(black, [accion('Black Express', '2026-11-23', '2026-11-29', { mundo: 'tienda_express' })]), [])

const conMail = accion('Promo Hogar', '2026-12-02', '2026-12-05', { banda: 'Especiales', piezas: [mailing()] })
const suelto = accion('Newsletter', '2026-12-02', '2026-12-02', { seccion: 'envio', banda: 'email' })
const otroDia = accion('Promo Bebés', '2026-12-01', '2026-12-04', { banda: 'Especiales', piezas: [mailing('2026-12-03')] })
const textos = choquesDe(conMail, [conMail, suelto, otroDia]).map(c => c.texto)
ok('un mailing de la acción el mismo día que un envío suelto choca', textos.length === 1 && textos[0].startsWith('El 02/12 sale otro envío por'), JSON.stringify(textos))
igual('desde el envío suelto se ve el mismo choque', choquesDe(suelto, [conMail, suelto, otroDia]).map(c => c.otraId), [conMail.id])
igual('un mailing con fecha propia otro día no choca', choquesDe(otroDia, [conMail, suelto, otroDia]), [])

if (fallos) { console.log(`\n${fallos} prueba(s) fallaron`); process.exit(1) }
console.log('\nchoques: todo bien')
