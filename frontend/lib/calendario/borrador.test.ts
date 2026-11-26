/**
 * Lo que se estaba cargando para entregar, guardado en el navegador
 * (lib/calendario/borrador.ts, H-039 de la auditoría del 25/11/2026).
 *
 *     npm run test:calendario
 */
import { VIDA_DEL_BORRADOR_MS, armarBorrador, borradorVigente, claveDeBorrador } from './borrador'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

const AHORA = Date.UTC(2026, 10, 26, 15, 0)
const imagen = (nombre: string, deZip?: number) => ({
  grande: new Blob(['grande']), mini: new Blob(['mini']), vista: `blob:${nombre}`, nombre, ancho: 1920, alto: 416,
  ...(deZip != null ? { deZip } : {}),
})
const vacio = { versionId: 've-1', comentario: '', link: '', porQue: '', imagenes: [], zip: null }
const entrega = { fase: 'fa-1', ronda: 0 }

console.log('Qué se guarda')
igual('sin nada cargado, nada', armarBorrador(vacio, entrega, AHORA), null)
igual('espacios solos tampoco', armarBorrador({ ...vacio, comentario: '   ' }, entrega, AHORA), null)
igual('un ZIP solo tampoco: no se guarda y no queda nada que devolver',
  armarBorrador({ ...vacio, zip: 'piezas.zip', imagenes: [imagen('de-adentro.jpg', 3)] }, entrega, AHORA), null)
const conTodo = armarBorrador({
  ...vacio, comentario: 'Va la primera, ojo con el ñandú', link: 'https://drive.example.com/x', porQue: 'El mobile mañana',
  imagenes: [imagen('header.jpg'), imagen('de-adentro.jpg', 3)], zip: 'piezas.zip',
}, entrega, AHORA)
igual('la nota, el link y el porqué, tal cual se escribieron',
  conTodo && [conTodo.comentario, conTodo.link, conTodo.porQue],
  ['Va la primera, ojo con el ñandú', 'https://drive.example.com/x', 'El mobile mañana'])
igual('las imágenes sueltas sí; las que salieron del ZIP no (el ZIP se vuelve a elegir)',
  conTodo?.imagenes.map(im => im.nombre), ['header.jpg'])
igual('sin la vista (es de esta página: al volver se arma otra)', conTodo?.imagenes.some(im => 'vista' in im), false)
igual('el nombre del ZIP, para pedir que lo vuelva a elegir', conTodo?.zip, 'piezas.zip')
igual('de qué entrega es, con qué versión y cuándo', conTodo && [conTodo.fase, conTodo.ronda, conTodo.versionId, conTodo.guardado],
  ['fa-1', 0, 've-1', AHORA])

console.log('Cuándo vuelve')
const guardado = { fase: 'fa-1', ronda: 0, versionId: 've-1', guardado: AHORA }
igual('la misma entrega, un rato después: vuelve',
  borradorVigente(guardado, { fase: 'fa-1', ronda: 0, versiones: [] }, AHORA + 60_000), true)
igual('ya llegó al servidor (la versión está en la tarjeta): no',
  borradorVigente(guardado, { fase: 'fa-1', ronda: 1, versiones: ['ve-1'] }, AHORA + 60_000), false)
igual('la misma versión aunque la ronda no haya cambiado: no',
  borradorVigente(guardado, { fase: 'fa-1', ronda: 0, versiones: ['ve-1'] }, AHORA + 60_000), false)
igual('mientras tanto alguien entregó otra (otra ronda): no',
  borradorVigente(guardado, { fase: 'fa-1', ronda: 1, versiones: ['ve-otra'] }, AHORA + 60_000), false)
igual('otra fase: no', borradorVigente(guardado, { fase: 'fa-2', ronda: 0, versiones: [] }, AHORA + 60_000), false)
igual('de hace más de un día: no',
  borradorVigente(guardado, { fase: 'fa-1', ronda: 0, versiones: [] }, AHORA + VIDA_DEL_BORRADOR_MS), false)
igual('con la hora de la compu atrasada (guardado «en el futuro»): no',
  borradorVigente(guardado, { fase: 'fa-1', ronda: 0, versiones: [] }, AHORA - 60_000), false)

console.log('De quién es')
igual('de una persona y una tarjeta', claveDeBorrador(7, 'ta-1'), '7:ta-1')
igual('otra persona en la misma compu no ve el de otra', claveDeBorrador(8, 'ta-1') === claveDeBorrador(7, 'ta-1'), false)

if (fallos) {
  console.log(`\n${fallos} prueba(s) fallaron`)
  process.exit(1)
}
console.log('\nTodo bien')
