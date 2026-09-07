import type { CenefaComponent } from "@/types/cenefas";

// ---------------------------------------------------------------------------
// Vinculación entre bandas de una plantilla multi-producto (3xA4/6xA4/A5/
// pinchos) — mover/achicar/agrandar una caja en una banda replica el mismo
// cambio en las demás. Compartido entre Canvas.tsx (arrastre/resize con el
// mouse) y PropertiesPanel.tsx (edición numérica del panel) -- las dos vías
// tienen que vincular exactamente igual, si no un cuadro editado a mano en el
// panel queda desalineado del resto aunque el arrastre sí lo hubiera vinculado.
// ---------------------------------------------------------------------------

/**
 * Identidad de "qué cuadro es este", para emparejar EL MISMO cuadro entre
 * bandas.
 *
 * Con variable, la identidad es la variable. Sin variable, la identidad es el
 * TEXTO FIJO: el "$" del diseño no imprime ninguna variable y hasta el
 * 07/09/2026 caía en `_id_<id>`, o sea que nunca vinculaba con nada -- había
 * que acomodar el símbolo de pesos de a uno, cenefa por cenefa. Un cuadro fijo
 * es igual de repetible que uno con variable: en la 6xA4 hay seis "$" de
 * precioOferta y seis de precioRegular, uno por banda, siempre en la misma
 * posición relativa.
 *
 * Cuando el mismo texto aparece más de una vez por banda (justamente el caso
 * del "$": dos por banda) esta key sola no alcanza para saber cuál es cuál.
 * Eso lo desempata `buildSiblingMap` por posición relativa dentro de la banda,
 * que es lo único consistente entre bandas.
 */
export function keyOfComponent(c: CenefaComponent): string {
  if (c.variable) return c.variable;
  const vars = (c.segments ?? [])
    .filter((s) => s.type === "variable")
    .map((s) => s.value);
  if (vars.length) return vars.join("+");

  // Texto fijo del diseño. Solo cuadros de texto con contenido: uno vacío no
  // tiene con qué identificarse y emparejarlo sería adivinar.
  if (c.type === "text") {
    const fijo = (c.static_value ?? "").trim();
    if (fijo) return `_fijo_${fijo}`;
  }
  return `_id_${c.id}`;
}

function origenDeBanda(comps: CenefaComponent[]): { x: number; y: number } {
  let x = Infinity, y = Infinity;
  for (const c of comps) {
    const b = c.base_bounds;
    if (!b) continue;
    if (b.x < x) x = b.x;
    if (b.y < y) y = b.y;
  }
  return { x: Number.isFinite(x) ? x : 0, y: Number.isFinite(y) ? y : 0 };
}

/**
 * Mapa componente -> ids de sus "hermanos" (el mismo cuadro, en OTRAS bandas).
 *
 * Nunca vincula dos apariciones dentro de UNA MISMA banda (ej. "unidad"
 * repetida dos veces en un solo cartel de la A4 de Preciazos, confirmado
 * intencional). Si el multiset de keys no es idéntico en todas las bandas, esa
 * key queda sin vincular -- nunca se adivina un emparejamiento que no cierra
 * parejo.
 *
 * Cuando una key aparece N veces por banda, las N se emparejan por POSICIÓN
 * RELATIVA al origen de su banda (primero por y, después por x). Antes se
 * emparejaban por el orden en que venían los ids, que no tiene por qué ser el
 * mismo en todas las bandas: si en una banda el importer devolvía los dos "$"
 * en un orden y en la siguiente al revés, el de arriba de una quedaba
 * hermanado con el de abajo de la otra y moverlo desparramaba el cartel.
 */
export function buildSiblingMap(
  components: CenefaComponent[], slotBands: string[][] | null | undefined,
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  if (!slotBands || slotBands.length < 2) return map;

  const byId = new Map(components.map((c) => [c.id, c]));
  const porBanda: Map<string, string[]>[] = slotBands.map((ids) => {
    const comps = ids
      .map((id) => byId.get(id))
      .filter((c): c is CenefaComponent => !!c && !!c.base_bounds);
    const origen = origenDeBanda(comps);

    const conPos = new Map<string, { id: string; ry: number; rx: number }[]>();
    for (const c of comps) {
      const k = keyOfComponent(c);
      const lista = conPos.get(k) ?? conPos.set(k, []).get(k)!;
      lista.push({ id: c.id, ry: c.base_bounds.y - origen.y, rx: c.base_bounds.x - origen.x });
    }

    const g = new Map<string, string[]>();
    for (const [k, lista] of conPos) {
      lista.sort((a, b) => (a.ry - b.ry) || (a.rx - b.rx));
      g.set(k, lista.map((e) => e.id));
    }
    return g;
  });

  const todasLasKeys = new Set<string>();
  porBanda.forEach((g) => g.forEach((_, k) => todasLasKeys.add(k)));

  for (const k of todasLasKeys) {
    if (k.startsWith("_id_")) continue; // sin identidad: nunca vincula
    const counts = porBanda.map((g) => (g.get(k) ?? []).length);
    if (counts[0] === 0 || counts.some((n) => n !== counts[0])) continue;
    for (let occ = 0; occ < counts[0]; occ++) {
      const idsEnEstaOcurrencia = porBanda.map((g) => g.get(k)![occ]);
      for (const id of idsEnEstaOcurrencia) {
        map.set(id, idsEnEstaOcurrencia.filter((otro) => otro !== id));
      }
    }
  }
  return map;
}
