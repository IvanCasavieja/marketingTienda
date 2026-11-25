// ---------------------------------------------------------------------------
// Volver a donde se estaba después de entrar (H-040 de la auditoría del
// 25/11/2026): el link del mail («/entregas?tarea=…») pedía entrar y, al
// entrar, iba al inicio en vez de abrir la tarea. El login recibe
// ?volver=<dirección> y, al entrar, va ahí.
//
// Solo direcciones de acá adentro: nunca otro sitio («//otro.com»,
// «https://…») ni las pantallas de entrar, así un link armado no manda a
// nadie afuera. Puro, sin imports: lo usa también lib/api.ts.
// ---------------------------------------------------------------------------

const DE_ENTRAR = /^\/(login|forgot-password|reset-password)(\/|\?|#|$)/

/** La dirección a la que volver, si es de acá adentro; si no, null. */
export function volverA(valor: string | null | undefined): string | null {
  if (!valor || valor.length > 2000) return null
  if (!valor.startsWith('/') || valor.startsWith('//') || valor.startsWith('/\\')) return null
  // Sin caracteres de control ni barras invertidas (algunos navegadores las leen como «/»).
  if (/[\u0000-\u001f\u007f\\]/.test(valor)) return null
  if (DE_ENTRAR.test(valor)) return null
  return valor
}

/** El login que, al entrar, vuelve a `dondeEstaba` («/entregas?tarea=…»).
 *  Si ya se está en el login, se queda como está (no pierde su ?volver). */
export function loginVolviendoA(dondeEstaba: string): string {
  if (/^\/login(\?|$)/.test(dondeEstaba)) return dondeEstaba
  const v = volverA(dondeEstaba)
  return v && v !== '/' ? `/login?volver=${encodeURIComponent(v)}` : '/login'
}

/** Lo que dice ?volver= en una búsqueda («?volver=%2Fentregas…»), ya validado. */
export function volverDeLaBusqueda(busqueda: string): string | null {
  try {
    return volverA(new URLSearchParams(busqueda).get('volver'))
  } catch {
    return null
  }
}
