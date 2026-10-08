/**
 * La regla de los huérfanos, solo para la descripción (Ivan, 08/10/2026):
 * "nos pasa muchas veces que en las descripciones queda un renglón con una
 * letra únicamente, o dos letras, o tres letras... queda feo". Si con el
 * cuerpo que dejaron las reglas de tamaño y de ancho algún renglón queda con
 * 1 a 3 caracteres solos, se baja el cuerpo de a un paso hasta que se junten.
 *
 * Espejo de apply_sin_huerfanos (component_renderer.py). Allá se mide con las
 * métricas de la tipografía; acá con el canvas, que es con lo que se dibuja
 * el preview. El corte es el mismo voraz de siempre: agregar palabras hasta
 * que no entran más. Los números salen de reglasDeMedicion.ts (el único
 * lugar donde viven), nunca de acá.
 */
import type { CenefaComponent } from "@/types/cenefas";

/** Los renglones en que se parte el texto en una caja de ese ancho útil (px). */
export function renglonesDeTexto(
  texto: string,
  anchoUtilPx: number,
  medir: (t: string) => number,
): string[] {
  const palabras = texto.split(/\s+/).filter(Boolean);
  if (palabras.length === 0) return [texto];
  const renglones: string[] = [];
  let actual = "";
  for (const palabra of palabras) {
    const tentativa = actual ? `${actual} ${palabra}` : palabra;
    if (actual && medir(tentativa) > anchoUtilPx) {
      renglones.push(actual);
      actual = palabra;
    } else {
      actual = tentativa;
    }
  }
  renglones.push(actual);
  return renglones;
}

/** Un renglón con 1..maxCaracteres caracteres solos, en un texto de más de un renglón. */
export function tieneRenglonHuerfano(renglones: string[], maxCaracteres: number): boolean {
  if (renglones.length < 2) return false;
  return renglones.some((r) => {
    const n = r.replace(/\s+/g, "").length;
    return n > 0 && n <= maxCaracteres;
  });
}

/** El cuadro imprime la descripción y ninguna otra variable. */
export function esDescripcionPura(comp: CenefaComponent): boolean {
  if ((comp.type ?? "text") !== "text") return false;
  const vars = new Set<string>();
  for (const seg of comp.segments ?? []) if (seg.type === "variable" && seg.value) vars.add(seg.value);
  if (comp.variable) vars.add(comp.variable);
  return vars.size === 1 && vars.has("descripcion");
}

/**
 * El cuerpo con el que la descripción no deja huérfanos: el actual si no hay
 * ninguno; si no, bajando de a `pasoPt` hasta `bajadaMaxPt`. `medirConPt`
 * mide un texto en px al cuerpo pedido (el canvas con la fuente resuelta).
 */
export function ptSinHuerfanos(
  texto: string,
  anchoUtilPx: number,
  pt: number,
  medirConPt: (t: string, pt: number) => number,
  r: { maxCaracteres: number; pasoPt: number; bajadaMaxPt: number },
): number {
  if (!texto.includes(" ")) return pt;
  let nuevo = pt;
  let bajada = 0;
  while (tieneRenglonHuerfano(renglonesDeTexto(texto, anchoUtilPx, (t) => medirConPt(t, nuevo)), r.maxCaracteres)) {
    if (bajada >= r.bajadaMaxPt) break;
    nuevo -= r.pasoPt;
    bajada += r.pasoPt;
  }
  return nuevo;
}
