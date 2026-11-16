// ---------------------------------------------------------------------------
// Cómo se muestra (y se copia) lo que contesta Don Tino.
//
// El modelo contesta en markdown: negritas, listas y links como
// [Ciberlunes](/calendario?accion=br-123). Se muestra con react-markdown SIN
// HTML crudo (skipHtml) y los links se dejan tocar solo si son de la propia
// app: una ruta que empieza con "/" o una dirección completa de este mismo
// sitio. Cualquier otro queda como texto, con la dirección a la vista. Así,
// aunque el modelo (o un texto que alguien cargó en el calendario y le llegó
// al modelo) traiga un link raro, nadie lo toca sin verlo.
//
// Puro a propósito: se prueba con `npm run test:chat`.
// ---------------------------------------------------------------------------

/** La ruta de la app a la que lleva un link, o null si no es de la app. */
export function rutaInterna(href: string | null | undefined, origen: string | null): string | null {
  if (!href) return null
  // Se resuelve como lo resolvería el navegador, contra este sitio, y se mira
  // a qué sitio quedó apuntando. Así "//otro.sitio", "/\otro.sitio" o una
  // ruta con tabs adentro (que el navegador convierte en otro sitio) no pasan
  // por internas, y "javascript:" tampoco.
  const base = origen ?? 'https://app.invalid'
  try {
    const url = new URL(href.trim(), base)
    if (url.origin !== new URL(base).origin) return null
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null
    return url.pathname + url.search + url.hash
  } catch {
    // No es una dirección: queda como texto.
    return null
  }
}

/**
 * Ajusta el markdown del modelo para que se vea como lo escribió:
 * - un renglón que arranca en negrita ("**Riesgos**") es un título y arranca
 *   un bloque aparte. Sin el renglón en blanco, el markdown lo pegaba al
 *   último punto de la lista de arriba;
 * - un salto simple se respeta como salto (en markdown sería un espacio).
 */
export function prepararMarkdown(texto: string): string {
  return texto
    .replace(/\r\n?/g, '\n')
    .replace(/\n(?=\*\*)/g, '\n\n')
    .replace(/([^\n])\n(?=[^\n])/g, '$1  \n')
}

const LINK = /\[([^\]\n]+)\]\(([^)\s]+)\)/g

function sinLinks(texto: string, origen: string | null): string {
  // Un link de la app no sirve fuera de ella (en un mail): queda el nombre.
  // Uno de afuera conserva la dirección entre paréntesis.
  return texto.replace(LINK, (_, t: string, u: string) => (rutaInterna(u, origen) ? t : `${t} (${u})`))
}

/** Para pegar en un mail o un chat: sin asteriscos ni links de la app. */
export function textoParaCopiar(texto: string, origen: string | null): string {
  return sinLinks(texto.replace(/\r\n?/g, '\n'), origen)
    .replace(/\*\*([^*\n]+)\*\*/g, '$1')
    .replace(/^(\s*)[-*] /gm, '$1• ')
    .trim()
}

function escapar(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Lo mismo en HTML simple: al pegar en Outlook o Gmail quedan las negritas y las viñetas. */
export function htmlParaCopiar(texto: string, origen: string | null): string {
  const enLinea = (s: string) => escapar(sinLinks(s, origen)).replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
  let html = ''
  let enLista = false
  for (const renglon of texto.replace(/\r\n?/g, '\n').split('\n')) {
    const punto = renglon.match(/^\s*[-*] (.*)$/)
    if (punto) {
      if (!enLista) { html += '<ul>'; enLista = true }
      html += `<li>${enLinea(punto[1])}</li>`
      continue
    }
    if (enLista) { html += '</ul>'; enLista = false }
    if (renglon.trim()) html += `<p>${enLinea(renglon)}</p>`
  }
  if (enLista) html += '</ul>'
  return html
}
