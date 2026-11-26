/**
 * Qué hacer con lo que contesta el servidor sobre una corrida de cenefas (un
 * job del motor), en las dos esperas de PreviewStep: mientras se arma la
 * revisión y, ya confirmada, mientras se genera el archivo.
 *
 * Desde el 14/07/2026 el motor genera en dos tiempos: la corrida queda en
 * "preview" --los datos del Excel listos para revisar en el lienzo-- y el PPTX
 * recién se arma cuando alguien confirma. La pantalla de Generar del editor
 * (/materiales/cenefas/v2/generar) nunca se enteró: leía "preview" como un
 * error sin motivo («Error en la generación — Error desconocido»), seguía
 * consultando cada 2 s para siempre y nadie confirmaba la corrida, que quedaba
 * «Esperando confirmación» en el Historial (H-008, 26/11/2026).
 *
 * La regla: en cada espera hay solo dos estados que todavía pueden cambiar
 * solos (en cola y generando). Cualquier otro termina la espera, con lo que se
 * esperaba o con un error que trae el motivo cuando el servidor lo manda.
 * Seguir esperando un estado que no va a cambiar es quedarse girando sin fin.
 *
 * Sin imports a propósito: la prueba lo compila suelto (npm run test:cenefas).
 */

/** Las dos esperas: la revisión (antes de confirmar) y el archivo (después). */
export type EtapaDeCorrida = "revision" | "archivo";

/** Lo que importa de la respuesta de GET /tools/cenefas/v2/jobs/{id}. */
export interface CorridaConsultada {
  status: string;
  template_def?: unknown;
  validation_report?: { error?: unknown } | null;
}

export type QueSigue =
  | { tipo: "esperar" }
  /** Llegó lo que se esperaba: la revisión para mostrar, o el archivo para bajar. */
  | { tipo: "lista" }
  /** `motivo` es el texto del servidor; sin él, la pantalla pone el suyo. */
  | { tipo: "error"; motivo: string | null };

/** Cada cuánto se pregunta por la corrida mientras se arma la revisión. */
export const CONSULTA_CADA_MS = 1500;

/**
 * Cuántas consultas seguidas pueden fallar mientras se arma la revisión antes
 * de avisar. Un corte de unos segundos --el servidor que se reinicia, el
 * wifi-- no tiene que tirar la corrida: se reintenta. Pero si el servidor no
 * contesta nunca, la pantalla no puede quedar girando sin decir nada. Después
 * de confirmar manda el límite de intentos de PreviewStep, que cuenta también
 * las que fallan: mientras se arma el archivo el servidor puede tardar en
 * contestar, y cortar antes sería dar por perdida una cenefa que sale.
 */
export const CONSULTAS_FALLIDAS_TOLERADAS = 20;

export function queSigue(corrida: CorridaConsultada, etapa: EtapaDeCorrida): QueSigue {
  switch (corrida.status) {
    case "pending":
    case "running":
      return { tipo: "esperar" };
    case "error":
      return { tipo: "error", motivo: motivoDelError(corrida) };
    case "preview":
      // Sin la definición no hay nada que dibujar, y no va a aparecer sola: el
      // servidor guarda los datos ANTES de pasar la corrida a "preview".
      if (etapa === "revision" && corrida.template_def) return { tipo: "lista" };
      break;
    case "done":
      if (etapa === "archivo") return { tipo: "lista" };
      break;
  }
  return { tipo: "error", motivo: null };
}

/** El motivo que mandó el servidor (validation_report.error), si mandó uno. */
function motivoDelError(corrida: CorridaConsultada): string | null {
  const motivo = corrida.validation_report?.error;
  return typeof motivo === "string" && motivo.trim() ? motivo.trim() : null;
}
