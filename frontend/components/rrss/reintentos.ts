// Cuando el servidor se cae o se reinicia a mitad de una validación, el navegador
// no ve un error del servidor: ve un corte sin respuesta (o un "CORS" falso, porque
// la respuesta de error la genera el proxy de Render y no lleva los encabezados de la
// app). Sin reintentos, cada placa pendiente fallaba en el acto y en segundos las 30
// quedaban marcadas como error.
//
// Las esperas se pueden cambiar por variable de entorno (para las pruebas); en uso
// normal son las de abajo: suman ~84 s, lo que tarda Render en levantar de nuevo.
const ESPERAS_MS: number[] = (process.env.NEXT_PUBLIC_RRSS_REINTENTOS_MS ?? "4000,10000,25000,45000")
  .split(",")
  .map((n) => Number(n))
  .filter((n) => Number.isFinite(n) && n >= 0);

/** ¿Vale la pena reintentar? Sin respuesta (red caída, servidor reiniciándose, corte
 *  del proxy) y los códigos de "ahora no puedo", sí. Un 400/403/etc. es una respuesta
 *  real del servidor y repetir el mismo pedido no la cambia. */
export function esTransitorio(e: unknown): boolean {
  const respuesta = (e as { response?: { status?: number } } | null)?.response;
  if (!respuesta) return true;
  return [408, 425, 429, 502, 503, 504].includes(respuesta.status ?? 0);
}

export async function conReintentos<T>(fn: () => Promise<T>, alReintentar?: (intento: number) => void): Promise<T> {
  for (let intento = 0; ; intento++) {
    try {
      return await fn();
    } catch (e) {
      if (!esTransitorio(e) || intento >= ESPERAS_MS.length) throw e;
      alReintentar?.(intento + 1);
      await new Promise((ok) => setTimeout(ok, ESPERAS_MS[intento]));
    }
  }
}
