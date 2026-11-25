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

/**
 * Si va la burbuja: a quien tiene Don Tino (el permiso `ai.don_tino`, o
 * superadmin), en todas las pantallas menos Inicio, donde el chat ya está
 * grande en el medio. Las cuentas de la agencia no tienen el permiso.
 */
export function muestraBurbuja(
  pathname: string,
  user: { is_superuser?: boolean; permissions?: string[] | null; es_externo?: boolean } | null | undefined,
): boolean {
  if (!user || user.es_externo) return false
  if (!user.is_superuser && !(user.permissions ?? []).includes('ai.don_tino')) return false
  return pathname !== '/home'
}

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
export const LUGAR_DEL_AYUDANTE = 'bottom-[calc(10rem+env(safe-area-inset-bottom))] right-4 md:bottom-[6.25rem] md:right-5'
