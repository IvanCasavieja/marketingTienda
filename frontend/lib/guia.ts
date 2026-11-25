/**
 * La guía de uso (/ayuda) que manda el servidor (GET /guia).
 *
 * Pedido de Ivan (25/11/2026): "hay que actualizar la guía de uso y fijarse que
 * Don Tino pueda manejar toda la app". El texto vive en un solo lugar,
 * backend/app/services/guia.py, y de ahí salen la pantalla y lo que sabe Don
 * Tino. El servidor manda solo las secciones que la persona puede usar (el
 * equipo, una agencia o un local de Redexpres).
 *
 * Va sin imports a propósito: así se prueba sola (guia.test.ts).
 */

export type ParteDeGuia = { titulo: string; puntos: string[]; numerada: boolean }

export type SeccionDeGuia = {
  clave: string
  titulo: string
  /** Un nombre de ícono de lucide-react (la pantalla lo traduce). */
  icono: string
  ruta: string | null
  resumen: string
  partes: ParteDeGuia[]
}

export type TrozoDeTexto = { texto: string; negrita: boolean }

/**
 * Un renglón de la guía partido en trozos con y sin **negrita** (lo único
 * que usa el texto). Un `**` suelto queda como texto. Pura.
 */
export function trozos(texto: string): TrozoDeTexto[] {
  const out: TrozoDeTexto[] = []
  const re = /\*\*(.+?)\*\*/g
  let desde = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(texto)) !== null) {
    if (m.index > desde) out.push({ texto: texto.slice(desde, m.index), negrita: false })
    out.push({ texto: m[1], negrita: true })
    desde = m.index + m[0].length
  }
  if (desde < texto.length) out.push({ texto: texto.slice(desde), negrita: false })
  return out
}

/** Las secciones con lo que dice la búsqueda (título, resumen o algún punto),
 *  sin tildes ni mayúsculas. Vacía = todas. Pura. */
export function filtrarGuia(secciones: SeccionDeGuia[], busqueda: string): SeccionDeGuia[] {
  const limpio = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  const q = limpio(busqueda.trim())
  if (!q) return secciones
  return secciones.filter(s =>
    [s.titulo, s.resumen, ...s.partes.flatMap(p => [p.titulo, ...p.puntos])].some(t => limpio(t).includes(q)))
}
