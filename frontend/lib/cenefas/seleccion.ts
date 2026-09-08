// ---------------------------------------------------------------------------
// Selección múltiple de cuadros — Ctrl/Cmd + click, como en PowerPoint.
//
// Compartido entre el store del editor completo (store/editor.ts) y las
// pantallas que manejan la selección en estado local (LotePreviewStep.tsx,
// PreviewStep.tsx). Igual que con siblingMap.ts: si cada vía implementara la
// regla por su cuenta, la selección se comportaría distinto según por dónde
// se entró al mismo editor.
//
// La selección tiene DOS partes y las dos importan:
//
//   ids     todo lo seleccionado. Es lo que miran las acciones en lote (por
//           ahora, las reglas).
//   primary el cuadro primario, el último tocado. Es lo que miran el panel de
//           propiedades y el Transformer del canvas, que trabajan sobre un
//           cuadro a la vez.
//
// El primario siempre pertenece a `ids` (o es null si no hay nada
// seleccionado): una selección con cuadros pero sin primario dejaría al panel
// de propiedades vacío con cosas marcadas en pantalla.
// ---------------------------------------------------------------------------

export interface Seleccion {
  ids: string[];
  primary: string | null;
}

/** Click pelado: reemplaza la selección por un solo cuadro (o la vacía). */
export function seleccionUnica(id: string | null): Seleccion {
  return { ids: id ? [id] : [], primary: id };
}

/**
 * Ctrl/Cmd + click: suma el cuadro si no estaba, lo saca si ya estaba.
 *
 * Al sacar el primario, el rol pasa al último que queda seleccionado — nunca
 * queda una selección con cuadros y sin primario.
 */
export function alternarSeleccion(actual: Seleccion, id: string): Seleccion {
  const yaEstaba = actual.ids.includes(id);
  const ids = yaEstaba ? actual.ids.filter((x) => x !== id) : [...actual.ids, id];
  if (!yaEstaba) return { ids, primary: id };
  return {
    ids,
    primary: actual.primary === id ? ids[ids.length - 1] ?? null : actual.primary,
  };
}
