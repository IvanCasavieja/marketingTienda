/**
 * Ordenar las tareas de una acción arrastrándolas (Ivan, 20/11/2026: "ordenar
 * las tareas arrastrando"). Se ordenan entre hermanas: las que cuelgan de lo
 * mismo. El servidor hace lo mismo (repartir_orden en
 * backend/app/api/routes/calendario.py).
 */
import type { Tarea } from './tipos'

/** El orden nuevo de unas hermanas: `id` pasa antes o después de `destino`. Pura. */
export function moverEntreHermanas(ids: string[], id: string, destino: string, antes: boolean): string[] {
  if (id === destino || !ids.includes(id) || !ids.includes(destino)) return ids
  const sin = ids.filter(x => x !== id)
  const i = sin.indexOf(destino) + (antes ? 0 : 1)
  return [...sin.slice(0, i), id, ...sin.slice(i)]
}

/** Correr una tarea un lugar para arriba (-1) o para abajo (+1), con el teclado. Pura. */
export function correrUnLugar(ids: string[], id: string, paso: -1 | 1): string[] {
  const i = ids.indexOf(id)
  const j = i + paso
  if (i < 0 || j < 0 || j >= ids.length) return ids
  return moverEntreHermanas(ids, id, ids[j], paso < 0)
}

/**
 * Las tareas de la acción con esas hermanas en el orden nuevo: cada una ocupa
 * el lugar de otra de ellas y las demás no se mueven. Una que ya no está (la
 * borraron) se ignora. Pura.
 */
export function conOrden(tareas: Tarea[], ids: string[]): Tarea[] {
  const porId = new Map(tareas.map(t => [t.id, t]))
  const enOrden = ids.map(id => porId.get(id)).filter((t): t is Tarea => !!t)
  const elegidas = new Set(enOrden.map(t => t.id))
  let k = 0
  return tareas.map(t => (elegidas.has(t.id) ? enOrden[k++] : t))
}
