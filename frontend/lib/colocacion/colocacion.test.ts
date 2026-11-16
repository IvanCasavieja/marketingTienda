/**
 * Pruebas de la foto de colocación del lado del navegador:
 *
 *     npm run test:colocacion
 *
 * Lo que se fija es a qué tamaño se achica la foto antes de subirla (nunca se
 * agranda, el lado mayor queda en 1024) y cómo se le dice al local cuándo
 * vence y cuántas le quedan por subir.
 */
import { LADO_FOTO, LADO_MINIATURA, medidas } from './imagen'
import { cuandoVence, pendientesDelLocal } from './estados'

let fallos = 0
function igual<T>(nombre: string, obtenido: T, esperado: T) {
  const ok = JSON.stringify(obtenido) === JSON.stringify(esperado)
  if (ok) console.log(`  ok    ${nombre}`)
  else { fallos++; console.log(`  FALLA ${nombre} — obtenido ${JSON.stringify(obtenido)}, esperado ${JSON.stringify(esperado)}`) }
}

console.log('\nachicar la foto')
igual('una foto de 12 MP apaisada queda en 1024 de ancho', medidas(4032, 3024, LADO_FOTO), { ancho: 1024, alto: 768 })
igual('una vertical queda en 1024 de alto', medidas(3024, 4032, LADO_FOTO), { ancho: 768, alto: 1024 })
igual('una chica no se agranda', medidas(800, 600, LADO_FOTO), { ancho: 800, alto: 600 })
igual('la miniatura, en 240', medidas(4032, 3024, LADO_MINIATURA), { ancho: 240, alto: 180 })
igual('una panorámica angosta no queda en 0 px', medidas(20000, 10, LADO_MINIATURA), { ancho: 240, alto: 1 })
igual('sin medidas, nada', medidas(0, 0, LADO_FOTO), { ancho: 0, alto: 0 })

console.log('\ncuándo vence')
igual('hoy', cuandoVence('2026-11-15', '2026-11-15'), { texto: 'hoy (15/11)', urgente: true, vencida: false })
igual('mañana', cuandoVence('2026-11-16', '2026-11-15'), { texto: 'mañana (16/11)', urgente: true, vencida: false })
igual('en unos días', cuandoVence('2026-11-20', '2026-11-15'), { texto: 'en 5 días (20/11)', urgente: false, vencida: false })
igual('ya venció', cuandoVence('2026-11-14', '2026-11-15'), { texto: 'venció el 14/11', urgente: true, vencida: true })
igual('cruzando de mes', cuandoVence('2026-12-01', '2026-11-30'), { texto: 'mañana (01/12)', urgente: true, vencida: false })

console.log('\nlo que le queda al local')
igual('cuenta lo que tiene que hacer, no lo enviado ni lo aprobado',
  pendientesDelLocal([
    { visible: 'pendiente' }, { visible: 'devuelta' }, { visible: 'atrasada' }, { visible: 'enviada' }, { visible: 'aprobada' },
  ]), 3)

console.log(`\n${fallos === 0 ? 'TODO OK' : fallos + ' FALLAS'}\n`)
process.exit(fallos === 0 ? 0 : 1)
