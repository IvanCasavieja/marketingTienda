import type { CenefaComponent, ComponentOverride } from "@/types/cenefas";

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
