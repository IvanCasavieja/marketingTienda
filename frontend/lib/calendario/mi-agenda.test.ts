/**
 * Pruebas de Mi agenda (17/11/2026). Se corren con las demás:
 *
 *     npm run test:calendario
 *
 * Leer el link y entender el calendario se prueba en
 * backend/tests/test_mi_agenda.py. Acá: en qué día cae cada evento (en hora
 * de Uruguay, se mire desde donde se mire) y cómo se dice en la fila.
 */
import {
  barrasDeAgenda, cuandoSeLeyo, eventosPorDia, horarioDe, nombreDelDia, pareceLinkDeCalendario, tituloDelDia,
  type EventoAgenda,
} from './mi-agenda'

let fallos = 0
function ok(nombre: string, cond: boolean, detalle = '') {
  if (cond) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre}${detalle ? ' — ' + detalle : ''}`) }
}
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  ok(nombre, JSON.stringify(obtenido) === JSON.stringify(esperado),
    `obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`)
}

const ev = (titulo: string, inicio: string, fin: string, extra: Partial<EventoAgenda> = {}): EventoAgenda => ({
  uid: titulo, titulo, inicio, fin, todoElDia: !inicio.includes('T'), lugar: null, ...extra,
})

const daily = ev('Daily', '2026-11-18T13:00:00Z', '2026-11-18T13:15:00Z', { lugar: 'Sala 3' })
const comite = ev('Comité de precios', '2026-11-18T17:30:00Z', '2026-11-18T18:30:00Z')
const feria = ev('Feria del libro', '2026-11-29', '2026-12-02')
// 23:30 del 19 en Uruguay son las 02:30 UTC del 20: va el 19.
const tarde = ev('Llamada con Madrid', '2026-11-20T02:30:00Z', '2026-11-20T03:00:00Z')
const deOtroMes = ev('Reunión de octubre', '2026-10-30T13:00:00Z', '2026-10-30T14:00:00Z')

console.log('Mi agenda')
const porDia = eventosPorDia([comite, feria, daily, tarde, deOtroMes], '2026-11', 30)
igual('cada evento en su día, en hora de Uruguay', [...porDia.keys()].sort((a, b) => a - b), [18, 19, 29, 30])
igual('el mismo día, por hora', porDia.get(18)!.map(e => e.titulo), ['Daily', 'Comité de precios'])
igual('el de todo el día ocupa cada día que dura, hasta el fin de mes', [porDia.get(29)!.length, porDia.get(30)!.length], [1, 1])
igual('y sigue en diciembre', [...eventosPorDia([feria], '2026-12', 31).keys()], [1])
igual('lo de otro mes no entra', eventosPorDia([deOtroMes], '2026-11', 30).size, 0)
igual('primero los de todo el día', eventosPorDia([daily, ev('Feriado', '2026-11-18', '2026-11-19')], '2026-11', 30).get(18)!.map(e => e.titulo), ['Feriado', 'Daily'])

igual('la barra dice la hora, el primero y cuántos más', nombreDelDia(porDia.get(18)!), '10:00 Daily +1')
igual('uno solo, sin "+"', nombreDelDia(porDia.get(19)!), '23:30 Llamada con Madrid')
igual('todo el día, sin hora', nombreDelDia(porDia.get(29)!), 'Feria del libro')
igual('el tooltip, uno por renglón', tituloDelDia(porDia.get(18)!), '10:00 a 10:15 · Daily (Sala 3)\n14:30 a 15:30 · Comité de precios')
igual('todo el día de un solo día', horarioDe(ev('Feriado', '2026-11-18', '2026-11-19')), 'Todo el día')
igual('todo el día de varios días', horarioDe(feria), 'Todo el día, hasta el 1/12')
igual('sin duración, solo la hora', horarioDe(ev('Recordatorio', '2026-11-18T12:00:00Z', '2026-11-18T12:00:00Z')), '09:00')

const barras = barrasDeAgenda(porDia, '2026-11')
igual('una barra de un día por día con eventos', barras.map(b => [b.desde, b.hasta]), [[18, 18], [19, 19], [29, 29], [30, 30]])
igual('con la fecha real', [barras[0].inicio, barras[0].fin, barras[0].id], ['2026-11-18', '2026-11-18', 'agenda-2026-11-18'])
igual('con el nombre', barras[0].nombre, '10:00 Daily +1')
igual('angosta: cuántos hay', barrasDeAgenda(porDia, '2026-11', true).map(b => b.nombre), ['2', '1', '1', '1'])

const ahora = new Date('2026-11-18T15:00:00Z')
igual('recién', cuandoSeLeyo('2026-11-18T14:59:40Z', ahora), 'recién')
igual('hace minutos', cuandoSeLeyo('2026-11-18T14:48:00Z', ahora), 'hace 12 minutos')
igual('hoy, a qué hora', cuandoSeLeyo('2026-11-18T11:05:00Z', ahora), 'a las 08:05')
igual('otro día', cuandoSeLeyo('2026-11-16T11:05:00Z', ahora), 'el 16/11')
igual('nunca', cuandoSeLeyo(null, ahora), '')

ok('link de Outlook', pareceLinkDeCalendario('https://outlook.office365.com/owa/calendar/abc@x.com/123/calendar.ics'))
ok('link de Google', pareceLinkDeCalendario('  https://calendar.google.com/calendar/ical/x%40gmail.com/private-1/basic.ics '))
ok('webcal', pareceLinkDeCalendario('webcal://p01-caldav.icloud.com/published/2/abc'))
ok('http no', !pareceLinkDeCalendario('http://calendar.google.com/x.ics'))
ok('texto suelto no', !pareceLinkDeCalendario('mi calendario'))

if (fallos > 0) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien.')
