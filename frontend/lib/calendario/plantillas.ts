// ---------------------------------------------------------------------------
// Plantillas de tareas y tareas que se mueven con su acción.
//
// Cada tipo de acción lleva casi siempre las mismas tareas: el brief a la
// agencia, las entregas, la aprobación, las cenefas a los locales, la foto de
// colocación y el retiro de lo que se colgó. Una plantilla las guarda con su
// vencimiento RELATIVO (N días antes o después del inicio o del fin de la
// acción) y al aplicarla se crean con la fecha ya calculada.
//
// La tarea guarda de dónde sale su fecha (`ancla` y `anclaDias`): si la acción
// se mueve, las que no están hechas se mueven solas. Si alguien cambia a mano
// el vencimiento, esa tarea se suelta y queda donde la pusieron.
//
// Las cuentas son las mismas que hace el servidor (backend/app/api/routes/
// calendario.py: vence_anclado, vencimientos_al_mover, poner_vence_a_mano,
// tareas_de_plantilla). Acá están para que la pantalla cambie al instante,
// sin esperar la respuesta; si las dos no coinciden, gana lo del servidor en
// la próxima revisión.
//
// Este archivo es puro (sin React ni '@/') a propósito: lo prueban las
// pruebas, que se compilan con tsc a secas.
// ---------------------------------------------------------------------------

import { esSinCategoria, mismaCategoria } from './categorias'
import { sumarDias } from './fechas'
import type { AnclaTarea, BarraGuardada, EstadoTarea, Plantilla, Tarea, TareaDePlantilla } from './tipos'

/** Hasta cuántos días antes o después se puede anclar una tarea. */
export const DIAS_DE_ANCLA = 365
/** Cuántas tareas lleva como mucho una plantilla (lo mismo que acepta el servidor). */
export const TAREAS_POR_PLANTILLA = 60

/** `dias` contados desde el inicio o el fin de la acción. Negativo = antes. */
export function venceAnclado(ancla: AnclaTarea, dias: number, desde: string, hasta: string): string {
  return sumarDias(ancla === 'inicio' ? desde : hasta, dias)
}

/** Las tareas de una acción que pasó a ir de `desde` a `hasta`: las ancladas
 *  que no están hechas, con la fecha nueva; lo hecho queda como registro. */
export function moverAncladas(tareas: Tarea[], desde: string, hasta: string): Tarea[] {
  return tareas.map(t => {
    if (!t.ancla || t.anclaDias == null || t.estado === 'hecha') return t
    const vence = venceAnclado(t.ancla, t.anclaDias, desde, hasta)
    return vence === t.vence ? t : { ...t, vence }
  })
}

export type CambiosDeTarea = Partial<Pick<Tarea, 'titulo' | 'descripcion' | 'estado' | 'asignadoA' | 'vence'>>

/**
 * Cómo queda una tarea con un cambio, igual que la deja el servidor:
 * - una fecha elegida a mano manda, y la tarea deja de moverse con la acción
 *   (volver a mandar la misma no es elegir otra);
 * - una hecha que se reabre no se movió mientras estuvo hecha: si sigue
 *   anclada, vuelve a la fecha que le toca con la acción como está hoy.
 */
export function conCambios(t: Tarea, cambios: CambiosDeTarea, desde: string, hasta: string): Tarea {
  const nueva: Tarea = { ...t, ...cambios }
  if ('vence' in cambios) {
    if ((cambios.vence ?? null) !== (t.vence ?? null)) {
      nueva.ancla = null
      nueva.anclaDias = null
    }
  } else if (cambios.estado && cambios.estado !== t.estado && t.estado === 'hecha' && t.ancla && t.anclaDias != null) {
    nueva.vence = venceAnclado(t.ancla, t.anclaDias, desde, hasta)
  }
  return nueva
}

/** "3 días antes del inicio", "el día que arranca", "1 día después del fin". */
export function textoDeAncla(ancla: AnclaTarea | null | undefined, dias: number): string {
  if (!ancla) return 'sin fecha'
  if (dias === 0) return ancla === 'inicio' ? 'el día que arranca' : 'el día que termina'
  const n = Math.abs(dias)
  return `${n} ${n === 1 ? 'día' : 'días'} ${dias < 0 ? 'antes' : 'después'} del ${ancla}`
}

/** Las tareas en el orden en que se muestran: cada una seguida de sus subtareas. */
export function enOrden<T extends { id: string; parentId: string | null }>(tareas: T[]): T[] {
  const ids = new Set(tareas.map(t => t.id))
  const out: T[] = []
  for (const t of tareas) {
    if (t.parentId && ids.has(t.parentId)) continue
    out.push(t, ...tareas.filter(h => h.parentId === t.id))
  }
  return out
}

/**
 * Las tareas que crea una plantilla en una acción, como las guarda el
 * servidor: las sueltas primero y las subtareas después (una subtarea no se
 * puede guardar antes que su tarea), cada una con su id nuevo y su fecha.
 * `ids` es lo que viaja: el id nuevo de cada tarea de la plantilla.
 */
export function tareasDesdePlantilla(
  plantilla: Plantilla,
  accion: Pick<BarraGuardada, 'desde' | 'hasta'>,
  nuevoId: () => string,
): { tareas: Tarea[]; ids: Record<string, string> } {
  const ids: Record<string, string> = {}
  for (const t of plantilla.tareas) ids[t.id] = nuevoId()
  const sueltas = plantilla.tareas.filter(t => !t.parentId)
  const subtareas = plantilla.tareas.filter(t => t.parentId)
  const tareas = [...sueltas, ...subtareas].map((t): Tarea => ({
    id: ids[t.id],
    parentId: t.parentId ? ids[t.parentId] ?? null : null,
    titulo: t.titulo,
    descripcion: t.descripcion ?? null,
    estado: 'pendiente' as EstadoTarea,
    asignadoA: t.asignadoA ?? null,
    vence: t.ancla ? venceAnclado(t.ancla, t.dias, accion.desde, accion.hasta) : null,
    ancla: t.ancla ?? null,
    anclaDias: t.ancla ? t.dias : null,
    plantillaId: plantilla.id,
    creadoPor: null,
    // Quién la hace y si es una pieza: el nombre "<Acción> - <Tipo>" lo arma
    // el servidor y llega en la próxima revisión.
    para: t.para ?? 'tienda',
    agencia: t.agencia ?? null,
    tipo: t.tipo ?? null,
  }))
  return { tareas, ids }
}

/**
 * Las plantillas que la ficha de una acción sugiere: las de su categoría.
 * Ninguna si la acción no tiene categoría, si no es del calendario comercial
 * (en un envío, la `banda` es el canal) o si ya se usó alguna de esa
 * categoría en esta acción: la sugerencia es para arrancar, no para insistir.
 */
export function plantillasSugeridas(plantillas: Plantilla[], accion: BarraGuardada): Plantilla[] {
  if (accion.seccion !== 'comercial' || esSinCategoria(accion.banda)) return []
  const deLaCategoria = plantillas.filter(p => mismaCategoria(p.categoria, accion.banda))
  const usadas = new Set((accion.tareas ?? []).map(t => t.plantillaId).filter(Boolean))
  return deLaCategoria.some(p => usadas.has(p.id)) ? [] : deLaCategoria
}

/** Las plantillas para elegir en una acción: primero las de su categoría,
 *  después las que sirven para cualquiera, después el resto. */
export function plantillasParaElegir(plantillas: Plantilla[], banda: string | null): Plantilla[] {
  const peso = (p: Plantilla) => (mismaCategoria(p.categoria, banda) ? 0 : p.categoria ? 2 : 1)
  return [...plantillas].sort((a, b) => peso(a) - peso(b) || a.nombre.localeCompare(b.nombre, 'es'))
}

/**
 * "Empezar con un ejemplo": una promo con cenefas en los locales, de punta a
 * punta, hasta el retiro. Se carga en el editor y se cambia lo que haga falta;
 * no se guarda solo. El retiro va anclado al fin: si la promo se alarga, el
 * retiro se corre con ella.
 */
export const EJEMPLO_DE_PLANTILLA: Omit<TareaDePlantilla, 'id'>[] = [
  { parentId: null, titulo: 'Brief a la agencia', descripcion: null, asignadoA: null, ancla: 'inicio', dias: -30 },
  { parentId: null, titulo: 'Primera entrega de la agencia', descripcion: null, asignadoA: null, ancla: 'inicio', dias: -21 },
  { parentId: null, titulo: 'Aprobación final de las piezas', descripcion: null, asignadoA: null, ancla: 'inicio', dias: -10 },
  { parentId: null, titulo: 'Cenefas y carteles a los locales', descripcion: null, asignadoA: null, ancla: 'inicio', dias: -3 },
  {
    parentId: null, titulo: 'Foto de la colocación en los locales', asignadoA: null, ancla: 'inicio', dias: 1,
    descripcion: 'Una foto por local, para confirmar que quedó todo colocado.',
  },
  {
    parentId: null, titulo: 'Retirar cenefas y carteles de la promo', asignadoA: null, ancla: 'fin', dias: 1,
    descripcion: 'Que no quede en los locales nada de una promo que ya terminó.',
  },
]

/** Lo que falta para poder guardar la plantilla, o null si está lista. */
export function problemaDePlantilla(p: { nombre: string; tareas: TareaDePlantilla[] }): string | null {
  if (!p.nombre.trim()) return 'Ponele un nombre a la plantilla.'
  if (p.tareas.length === 0) return 'Agregale al menos una tarea.'
  if (p.tareas.length > TAREAS_POR_PLANTILLA) return `Una plantilla lleva hasta ${TAREAS_POR_PLANTILLA} tareas.`
  if (p.tareas.some(t => !t.titulo.trim())) return 'Hay una tarea sin título.'
  if (p.tareas.some(t => t.para === 'fuera' && (!t.agencia?.trim() || t.asignadoA == null))) {
    return 'Una tarea la hace una agencia de afuera: escribí su nombre y elegí quién del equipo la carga.'
  }
  if (p.tareas.some(t => t.ancla && (!Number.isInteger(t.dias) || Math.abs(t.dias) > DIAS_DE_ANCLA))) {
    return `Los días van de 0 a ${DIAS_DE_ANCLA}.`
  }
  return null
}
