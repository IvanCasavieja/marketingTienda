// ---------------------------------------------------------------------------
// Borrar una tarea o una acción: lo entregado no se borra nunca.
//
// Las imágenes y los ZIP que manda la agencia son el histórico de las piezas
// (Ivan, 19/11/2026: no se borran nunca). Borrar una tarea, o la acción
// entera, se los llevaba sin avisar (H-001, 26/11/2026). El servidor ya no lo
// deja: DELETE /calendario/tareas/{id} y /calendario/barras/{id} contestan
// 409 y dicen por qué (por_que_no_se_borra, en
// backend/app/services/entregas.py). Acá está lo que la pantalla necesita
// para decirlo ANTES, con lo que ya tiene cargado, en vez de ofrecer un
// «Sí, borrar» que el servidor después rechaza.
// ---------------------------------------------------------------------------

import type { BarraGuardada, Tarea } from './tipos'

/** Si en la tarea ya se entregó algo: una ronda en cualquiera de sus fases,
 *  aunque sea solo un link. Es la misma regla del servidor (alguna versión).
 *  No alcanza con `entrega.ronda`: es la de la fase en curso, y una fase
 *  nueva arranca en 0 aunque la anterior tenga todo lo entregado. */
export function tieneEntregas(tarea: Pick<Tarea, 'entrega'>): boolean {
  return (tarea.entrega?.fases ?? []).some(f => f.rondas > 0)
}

/** Cuántas tareas de la acción ya tienen algo entregado. */
export function tareasConEntregas(barra: Pick<BarraGuardada, 'tareas'>): number {
  return (barra.tareas ?? []).filter(tieneEntregas).length
}
