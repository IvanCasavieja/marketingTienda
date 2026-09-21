import type { RrssEstado, RrssFila, RrssImagen } from "@/lib/api";

export interface Segmento {
  texto: string;
  distinto: boolean;
}

/**
 * Diferencia carácter a carácter entre lo que dice la placa y lo que dice el
 * mailing, para resaltar EXACTAMENTE qué cambia. La validación es estricta
 * ("100g" no es "100 g", "kg" no es "Kg"), y sin esto la persona tendría que
 * comparar las dos cadenas a ojo para ver dónde está la diferencia.
 *
 * LCS sobre caracteres: los textos son de decenas de caracteres, no hace falta
 * nada más sofisticado. Un espacio que sobra o falta se marca con un segmento
 * propio, así se ve aunque sea invisible.
 */
export function diferenciar(placa: string, mailing: string): { placa: Segmento[]; mailing: Segmento[] } {
  const a = Array.from(placa);
  const b = Array.from(mailing);
  const n = a.length;
  const m = b.length;
  // largos[i][j] = LCS de a[i..] y b[j..]
  const largos: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      largos[i][j] = a[i] === b[j] ? largos[i + 1][j + 1] + 1 : Math.max(largos[i + 1][j], largos[i][j + 1]);
    }
  }
  const segA: Segmento[] = [];
  const segB: Segmento[] = [];
  const push = (seg: Segmento[], c: string, distinto: boolean) => {
    const ultimo = seg[seg.length - 1];
    if (ultimo && ultimo.distinto === distinto) ultimo.texto += c;
    else seg.push({ texto: c, distinto });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push(segA, a[i], false);
      push(segB, b[j], false);
      i++;
      j++;
    } else if (largos[i + 1][j] >= largos[i][j + 1]) {
      push(segA, a[i++], true);
    } else {
      push(segB, b[j++], true);
    }
  }
  while (i < n) push(segA, a[i++], true);
  while (j < m) push(segB, b[j++], true);
  return { placa: segA, mailing: segB };
}

export const ESTILO_ESTADO: Record<RrssEstado | "pendiente" | "analizando", { punto: string; badge: string }> = {
  ok: { punto: "bg-emerald-500", badge: "badge-green" },
  avisos: { punto: "bg-amber-500", badge: "badge-yellow" },
  diferencias: { punto: "bg-red-500", badge: "badge-red" },
  sin_match: { punto: "bg-violet-500", badge: "badge-blue" },
  error: { punto: "bg-slate-500", badge: "badge-slate" },
  pendiente: { punto: "bg-slate-300 dark:bg-slate-600", badge: "badge-slate" },
  analizando: { punto: "bg-brand-500 animate-pulse", badge: "badge-blue" },
};

/** Filas que hay que mostrar como "encontré esto" (error o aviso). */
export function filasConProblema(img: RrssImagen): RrssFila[] {
  return img.filas.filter((f) => f.severidad === "error" || f.severidad === "aviso");
}

/** Ordena los formatos como se muestran: cuadrado, 4:5, vertical, y lo raro al final. */
export function ordenFormato(f: string): number {
  const i = ["1:1", "4:5", "9:16"].indexOf(f);
  return i === -1 ? 99 : i;
}

export function etiquetaImagen(img: RrssImagen): string {
  return img.nombre_archivo.replace(/\.[a-z0-9]+$/i, "");
}
