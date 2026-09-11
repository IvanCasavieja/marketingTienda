import type { CenefaComponent, CenefaTemplate, ComponentOverride } from "@/types/cenefas";

// ---------------------------------------------------------------------------
// Acumulación de lo ajustado en un cuadro mientras se revisa una cenefa.
//
// Compartido entre PreviewStep.tsx (una cenefa) y LotePreviewStep.tsx (un
// lote): las dos pantallas mandan lo mismo al mismo endpoint, y cuando cada
// una armaba su override por su cuenta se desincronizaron -- la de lote
// aprendió a mandar `segments` y la de una sola no, o al revés, sin que nada
// lo delatara hasta que un cambio no salía en el archivo.
//
// La lista de campos es espejo de `_con_override` en backend/app/services/
// cenefas/jobs.py. Los dos lados se mueven juntos: agregar un campo acá sin
// agregarlo allá es exactamente el bug que esto viene a cerrar.
// ---------------------------------------------------------------------------

/**
 * Todo lo que un override puede llevar. Solo se usa para `afectaAlArchivo`:
 * el copiado va campo por campo en `acumularOverride`, para que el compilador
 * pueda verificarlo.
 *
 * `eliminado` no está: no es un campo del cuadro sino su baja, y viaja aparte
 * (ver `overrideEliminado`).
 */
const CAMPOS_DEL_OVERRIDE = [
  "base_bounds", "style", "segments",
  "variable", "static_value", "transform", "vinculado_a", "image_data", "image_ext",
] as const;

/**
 * Suma un cambio del canvas/panel a lo que ya se venía acumulando de ESE
 * cuadro. Nunca pisa lo acumulado con lo que este update no trae.
 *
 * La diferencia entre "no lo toqué" y "lo apagué" se decide con `in`, no con
 * la veracidad del valor: apagar el texto compuesto manda
 * `segments: undefined`, y `updates.segments ? ... : {}` lo leía como "no vino
 * nada" -- el cuadro volvía a modo simple en pantalla y salía compuesto en el
 * PPTX. Se normaliza a `null` porque `JSON.stringify` borra las claves
 * `undefined` y el override llegaría al backend sin el campo, con el mismo
 * resultado.
 */
export function acumularOverride(
  previo: ComponentOverride,
  updates: Partial<CenefaComponent>,
): ComponentOverride {
  const siguiente: ComponentOverride = { ...previo };

  if ("base_bounds" in updates && updates.base_bounds) {
    siguiente.base_bounds = updates.base_bounds;
  }
  if ("style" in updates && updates.style) {
    siguiente.style = { ...previo.style, ...updates.style };
  }
  if ("segments" in updates) {
    siguiente.segments = updates.segments ?? null;
  }
  // Campo por campo y no por índice dinámico: así el compilador verifica que
  // cada uno existe en las dos puntas (CenefaComponent y ComponentOverride) y
  // avisa si mañana se renombra uno. `?? null` por lo mismo que `segments`:
  // borrar la variable de un cuadro (volverlo texto fijo) manda `undefined`,
  // y sin normalizar JSON.stringify borra la clave y el cambio se pierde.
  if ("variable"     in updates) siguiente.variable     = updates.variable     ?? null;
  if ("static_value" in updates) siguiente.static_value = updates.static_value ?? null;
  if ("transform"    in updates) siguiente.transform    = updates.transform;
  if ("vinculado_a"  in updates) siguiente.vinculado_a  = updates.vinculado_a  ?? null;
  if ("image_data"   in updates) siguiente.image_data   = updates.image_data   ?? null;
  if ("image_ext"    in updates) siguiente.image_ext    = updates.image_ext    ?? null;
  return siguiente;
}

/**
 * ¿Este update cambia algo que de verdad viaja al backend?
 *
 * Sirve para no marcar la cenefa como "tiene cambios pendientes" --y disparar
 * el modal de guardado-- por un cambio que el motor de render ni mira. Hoy el
 * único caso es `z_index`: ordena el canvas y el panel de reglas, pero el
 * renderer no lo lee (el orden de dibujo sale del PPTX fuente).
 */
export function afectaAlArchivo(updates: Partial<CenefaComponent>): boolean {
  return CAMPOS_DEL_OVERRIDE.some((campo) => campo in updates);
}

/**
 * Saca cuadros de la plantilla que se está revisando (botón "Eliminar" del
 * panel en el preview). Compartido por PreviewStep y LotePreviewStep.
 *
 * Además de sacarlos de la lista, anota su forma del PPTX fuente en
 * `formas_eliminadas`: el render parte de ese archivo, así que sin anotarla la
 * forma se seguiría imprimiendo, y "Guardar en la plantilla" la traería de
 * vuelta en la próxima corrida. También suelta las relaciones (`vinculado_a`)
 * que apuntaban a ellos y borra sus reglas. Es el espejo de lo que hace
 * aplicar_overrides en backend/app/services/cenefas/jobs.py con el override
 * `eliminado`.
 *
 * `liberados` son los cuadros que quedaron sin relación: su cambio también
 * tiene que viajar como override.
 */
export function sacarCuadros(
  def: CenefaTemplate,
  ids: string[],
): { def: CenefaTemplate; liberados: string[]; reglasCambiaron: boolean } {
  const borrar = new Set(ids);
  const formas = [...(def.formas_eliminadas ?? [])];
  for (const c of def.components) {
    const forma = c._source_shape_id;
    if (borrar.has(c.id) && forma != null && !formas.includes(forma)) formas.push(forma);
  }
  const liberados: string[] = [];
  const components = def.components
    .filter((c) => !borrar.has(c.id))
    .map((c) => {
      if (!c.vinculado_a || !borrar.has(c.vinculado_a)) return c;
      liberados.push(c.id);
      return { ...c, vinculado_a: null };
    });
  const reglas = def.rules ?? [];
  const rules = reglas.filter((r) => !borrar.has(r.target_component_id));
  return {
    def: { ...def, components, rules, formas_eliminadas: formas },
    liberados,
    reglasCambiaron: rules.length !== reglas.length,
  };
}

/** El override que le avisa al backend que el cuadro se eliminó (ver `sacarCuadros`). */
export function overrideEliminado(id: string): ComponentOverride {
  return { id, eliminado: true };
}
