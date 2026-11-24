/**
 * Mis tareas: qué se dice arriba y qué cartel de vacío se muestra.
 *
 * Si no se pudieron traer las tareas o las piezas para revisar, la pantalla no
 * puede decir «Estás al día» ni «No tenés nada pendiente»: sería mentirle a
 * quien la mira. En ese caso se avisa qué faltó y se cuenta solo lo que hay.
 * Lógica pura, sin React, para poder probarla (mis-tareas.test.ts).
 */

export type FallosDeCarga = {
  /** No se pudo traer la lista de tareas (calendarioApi.misTareas). */
  falloTareas: boolean
  /** No se pudieron traer las piezas para revisar (entregasApi.misEntregas). */
  falloEntregas: boolean
}

export type VacioDeMisTareas = 'sinAsignar' | 'alDia'

/**
 * El cartel de vacío que corresponde, o null si no va ninguno. Con cualquier
 * falla no va ninguno: no sabemos si de verdad no hay nada.
 */
export function vacioQueSeMuestra({
  falloTareas, falloEntregas, cantidadDelMundo, cantidadAbiertas, hayEntregasArriba,
}: FallosDeCarga & {
  /** Tareas de este mundo, hechas o no. */
  cantidadDelMundo: number
  /** Tareas de este mundo que se muestran en la lista (sin hacer o recién tildadas). */
  cantidadAbiertas: number
  /** Hay piezas para revisar o devueltas con cambios en la parte de arriba. */
  hayEntregasArriba: boolean
}): VacioDeMisTareas | null {
  if (falloTareas || falloEntregas) return null
  if (hayEntregasArriba) return null
  if (cantidadDelMundo === 0) return 'sinAsignar'
  if (cantidadAbiertas === 0) return 'alDia'
  return null
}

/** La línea de abajo del título: cuánto hay pendiente y para revisar. */
export function resumenDeEncabezado({
  falloTareas, falloEntregas, pendientes, paraRevisar, nombreMundo,
}: FallosDeCarga & {
  pendientes: number
  paraRevisar: number
  nombreMundo?: string | null
}): string {
  const enMundo = nombreMundo ? ` en ${nombreMundo}` : ''
  if (pendientes === 0 && paraRevisar === 0) {
    // Con una falla no se puede asegurar que no haya nada: el aviso de abajo
    // dice qué faltó.
    if (falloTareas || falloEntregas) return `No se pudo traer todo lo que tenés${enMundo}.`
    return `No tenés nada pendiente${enMundo}.`
  }
  const partes = [
    pendientes > 0 ? (pendientes === 1 ? '1 tarea pendiente' : `${pendientes} tareas pendientes`) : '',
    paraRevisar > 0 ? (paraRevisar === 1 ? '1 pieza para revisar' : `${paraRevisar} piezas para revisar`) : '',
  ].filter(Boolean)
  return `Tenés ${partes.join(' y ')}${enMundo}.`
}

/** Un renglón por cada cosa que no se pudo traer, en el orden de la pantalla. */
export function avisosDeFalla({ falloTareas, falloEntregas }: FallosDeCarga): string[] {
  const avisos: string[] = []
  if (falloTareas) avisos.push('No se pudieron traer tus tareas.')
  if (falloEntregas) avisos.push('No se pudieron traer las piezas para revisar.')
  return avisos
}
