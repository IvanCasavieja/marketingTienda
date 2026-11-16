/**
 * Choques entre acciones del mismo mundo (idea aprobada por Ivan, 15/11/2026):
 * avisar antes de que dos cosas grandes se pisen.
 *
 * - Dos mega eventos con días en común: compiten por la misma atención (y por
 *   los mismos lugares de la tienda y de la web).
 * - Dos envíos por el mismo canal el mismo día (dos mailings, dos WhatsApp):
 *   le llegan juntos a la misma gente. Cuenta tanto un envío suelto como la
 *   pieza de envío de una acción.
 *
 * Solo avisa: no bloquea nada. Sale de lo que el calendario ya tiene cargado
 * (las barras de un mundo).
 */
import { nivelDeCategoria } from './categorias'
import { fechaDeEnvio } from './derivar'
import { fechaCorta, rangoLargo } from './fechas'
import { esPiezaDeEnvio, tituloDeCanal, type BarraGuardada } from './tipos'

export type Choque = {
  tipo: 'mega' | 'envio'
  /** La otra acción, para poder abrirla. */
  otraId: string
  texto: string
}

function seSuperponen(a: { desde: string; hasta: string }, b: { desde: string; hasta: string }): boolean {
  return a.desde <= b.hasta && b.desde <= a.hasta
}

/** Los envíos de una acción o de un envío suelto: por qué canal y qué día salen. */
function enviosDe(b: BarraGuardada): { canal: string; dia: string }[] {
  if (b.seccion === 'envio') return [{ canal: b.banda, dia: b.desde }]
  if (b.seccion !== 'comercial') return []
  return (b.piezas ?? []).filter(esPiezaDeEnvio).map(p => ({ canal: p.area, dia: fechaDeEnvio(p, b.desde) }))
}

export function choquesDe(accion: BarraGuardada, todas: Iterable<BarraGuardada>): Choque[] {
  const out: Choque[] = []
  const vistos = new Set<string>()
  const agregar = (c: Choque) => {
    const clave = `${c.tipo}|${c.otraId}|${c.texto}`
    if (!vistos.has(clave)) { vistos.add(clave); out.push(c) }
  }
  const esMega = accion.seccion === 'comercial' && nivelDeCategoria(accion.banda) === 'mega'
  const mios = enviosDe(accion)

  for (const otra of todas) {
    if (otra.id === accion.id) continue
    if (accion.mundo && otra.mundo && accion.mundo !== otra.mundo) continue

    if (esMega && otra.seccion === 'comercial' && nivelDeCategoria(otra.banda) === 'mega' && seSuperponen(accion, otra)) {
      agregar({
        tipo: 'mega', otraId: otra.id,
        texto: `Se superpone con otro mega evento: ${otra.nombre} (${rangoLargo(otra.desde, otra.hasta)})`,
      })
    }
    for (const suyo of enviosDe(otra)) {
      for (const mio of mios) {
        if (mio.canal === suyo.canal && mio.dia === suyo.dia) {
          agregar({
            tipo: 'envio', otraId: otra.id,
            texto: `El ${fechaCorta(mio.dia)} sale otro envío por ${tituloDeCanal(mio.canal)}: ${otra.nombre}`,
          })
        }
      }
    }
  }
  return out
}
