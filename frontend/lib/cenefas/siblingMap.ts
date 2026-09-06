import type { CenefaComponent } from "@/types/cenefas";

// ---------------------------------------------------------------------------
// Vinculación por variable entre bandas de una plantilla multi-producto
// (3xA4/6xA4/A5/pinchos) — mover/achicar/agrandar la caja de una variable en
// una banda replica el mismo cambio en las demás. Compartido entre Canvas.tsx
// (arrastre/resize con el mouse) y PropertiesPanel.tsx (edición numérica del
// panel) -- las dos vías tienen que vincular exactamente igual, si no un
// cuadro editado a mano en el panel queda desalineado del resto aunque el
// arrastre con el mouse sí lo hubiera vinculado.
// ---------------------------------------------------------------------------

// Identidad de "qué variable imprime este cuadro", para emparejar la MISMA
// caja entre bandas. Sin variable (texto fijo, o sin match) nunca vincula --
// su key es única por componente.
export function keyOfComponent(c: CenefaComponent): string {
  if (c.variable) return c.variable;
  const vars = (c.segments ?? [])
    .filter((s) => s.type === "variable")
    .map((s) => s.value);
  return vars.length ? vars.join("+") : `_id_${c.id}`;
}

// Mapa componente -> ids de sus "hermanos" (misma variable, en OTRAS
// bandas). Nunca vincula dos apariciones de la misma variable DENTRO de una
// banda (ej. "unidad" repetida dos veces en un solo cartel de la A4 de
// Preciazos, confirmado intencional). Si el multiset de keys no es idéntico
// en todas las bandas, esa key queda sin vincular -- nunca se adivina un
// emparejamiento que no cierra parejo.
export function buildSiblingMap(
  components: CenefaComponent[], slotBands: string[][] | null | undefined,
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  if (!slotBands || slotBands.length < 2) return map;

  const byId = new Map(components.map((c) => [c.id, c]));
  const porBanda: Map<string, string[]>[] = slotBands.map((ids) => {
    const g = new Map<string, string[]>();
    for (const id of ids) {
      const c = byId.get(id);
      if (!c) continue;
      const k = keyOfComponent(c);
      (g.get(k) ?? g.set(k, []).get(k)!).push(id);
    }
    return g;
  });

  const todasLasKeys = new Set<string>();
  porBanda.forEach((g) => g.forEach((_, k) => todasLasKeys.add(k)));

  for (const k of todasLasKeys) {
    if (k.startsWith("_id_")) continue; // sin variable: nunca vincula
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
