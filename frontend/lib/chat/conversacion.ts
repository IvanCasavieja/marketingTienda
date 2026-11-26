/**
 * La conversación con Don Tino, sin React: qué se le manda al servidor y
 * dónde se ve la burbuja. La usan el chat de Inicio y la burbuja de abajo a la
 * derecha (25/11/2026, Ivan: "siempre tenemos que tener a Don Tino presente
 * en las pestañas como una burbuja abajo a la derecha").
 *
 * Va sin imports de React ni de la API, así se prueba sola (test:chat).
 */

export type MensajeDonTino = { role: 'bot' | 'user'; text: string; ts: number; usage?: { total_tokens: number } }

/**
 * El historial que viaja con una pregunta: lo último de la conversación, sin
 * el saludo (el primer mensaje, que lo pone la pantalla y no el modelo) y sin
 * la pregunta nueva, que va aparte. Hasta 10 mensajes. Es lo mismo que hacía
 * Inicio antes de que el chat se compartiera con la burbuja.
 */
export function historialParaEnviar(mensajes: MensajeDonTino[]): { role: 'assistant' | 'user'; content: string }[] {
  return mensajes
    .filter((m, i) => !(i === 0 && m.role === 'bot'))
    .slice(-11, -1)
    .map(m => ({ role: m.role === 'bot' ? 'assistant' : 'user', content: m.text }))
}

/** De la persona, lo que decide si tiene burbuja. */
type QuienMira = { is_superuser?: boolean; permissions?: string[] | null; es_externo?: boolean }

/**
 * Si va la burbuja: a quien tiene Don Tino (el permiso `ai.don_tino`, o
 * superadmin), en todas las pantallas menos Inicio, donde el chat ya está
 * grande en el medio. Las cuentas de la agencia no tienen el permiso.
 */
export function muestraBurbuja(pathname: string, user: QuienMira | null | undefined): boolean {
  if (!user || user.es_externo) return false
  if (!user.is_superuser && !(user.permissions ?? []).includes('ai.don_tino')) return false
  if (PANTALLAS_CON_AYUDANTE.includes(pathname)) return false
  return pathname !== '/home'
}

/**
 * Las pantallas que tienen su propio ayudante (Tinín en Materiales, Doña Tina
 * en Precios y Analytics, Dog-Ti en Facturación). Ahí no va la burbuja de Don
 * Tino: quedaban dos burbujas, una arriba de la otra (Ivan, 25/11/2026: "está
 * quedando ambas mascotas, cuidado, eso está mal"). Una sola por pantalla.
 */
export const PANTALLAS_CON_AYUDANTE = ['/materiales/cenefas', '/materiales/convertidor', '/precios', '/analytics', '/facturacion']

/**
 * Dónde van los botones flotantes, abajo a la derecha. En el teléfono, arriba
 * de la barra de abajo (56 px más el borde) y del cartel amarillo del entorno
 * de pruebas (que va a 4rem del borde): así no tapan «Más» ni el cartel. Don
 * Tino va abajo; el ayudante de una pantalla (Tinín en Materiales, Doña Tina
 * en Precios y Analytics, Dog-Ti en Facturación) va arriba de él.
 *
 * El Equipo nocturno (25/11/2026) encontró que en el celular esos ayudantes,
 * a 1,25rem del borde, tapaban «Más»: tocabas «Más» y se abría el chat.
 */
export const LUGAR_DE_DON_TINO = 'bottom-[calc(5.75rem+env(safe-area-inset-bottom))] right-4 md:bottom-5 md:right-5'
// El ayudante de una pantalla va en el mismo lugar que Don Tino: nunca están
// los dos a la vez (PANTALLAS_CON_AYUDANTE).
export const LUGAR_DEL_AYUDANTE = LUGAR_DE_DON_TINO

/**
 * Lo que deja libre abajo la pantalla (el <main> del layout del dashboard)
 * cuando hay un botón flotante: así lo último de la página se puede correr
 * hasta arriba de él.
 *
 * El Equipo nocturno (26/11/2026, H-025) encontró la burbuja encima de
 * «Confirmar pedido» del local, de «Validar placas» y del «Enviar» de La
 * Triada, en la notebook y en el celular: la pantalla dejaba abajo el lugar
 * de la barra del teléfono (en la notebook, casi nada) y la burbuja flota más
 * arriba. Los números salen de LUGAR_DE_DON_TINO y del botón más alto (los
 * ayudantes miden 4rem; Don Tino, 3,5rem), con un poco de aire:
 *   - teléfono: 5,75rem + 4rem → 10,5rem;
 *   - notebook: 1,25rem + 4rem → 6rem.
 */
export const LUGAR_PARA_LA_BURBUJA = 'pb-[calc(10.5rem+env(safe-area-inset-bottom))] md:pb-24'
/** Sin botón flotante, lo de siempre: en el teléfono, el lugar de la barra de abajo. */
export const LUGAR_SIN_BURBUJA = 'pb-24 md:pb-5 lg:pb-6'

/** Cuál de los dos lleva esa pantalla: hay botón flotante si va la burbuja de
 *  Don Tino o si la pantalla tiene su propio ayudante. */
export function lugarDeAbajo(pathname: string, user: QuienMira | null | undefined): string {
  if (!user || user.es_externo) return LUGAR_SIN_BURBUJA
  const hayBotonFlotante = muestraBurbuja(pathname, user) || PANTALLAS_CON_AYUDANTE.includes(pathname)
  return hayBotonFlotante ? LUGAR_PARA_LA_BURBUJA : LUGAR_SIN_BURBUJA
}
