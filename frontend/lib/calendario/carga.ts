/**
 * La carga del equipo (idea aprobada por Ivan, 15/11/2026): antes de repartir
 * el trabajo de un mega evento, ver quién ya está desbordado esa semana.
 *
 * Cuenta las tareas abiertas (no hechas) de cada persona en el mundo que se
 * mira, por semana (de lunes a domingo): las vencidas, las de las próximas
 * semanas, las de más adelante y las que no tienen fecha. Sale de lo que el
 * calendario ya tiene cargado.
 */
import { sumarDias } from './fechas'
import type { BarraGuardada } from './tipos'

export type TareaDeLaCarga = { id: string; titulo: string; vence: string | null; accionId: string; accion: string }

export type FilaDeCarga = {
  personaId: number
  /** Todas las abiertas. */
  total: number
  vencidas: number
  /** Una por semana, en el orden de `semanas`. */
  porSemana: number[]
  masAdelante: number
  sinFecha: number
  tareas: TareaDeLaCarga[]
}

export type Semana = { desde: string; hasta: string }

/** A partir de cuántas tareas en una semana se ve en amarillo y en rojo. */
export const CARGA_ALTA = 3
export const CARGA_EXCESIVA = 5

function lunesDe(iso: string): string {
  const d = new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)))
  const dia = (d.getUTCDay() + 6) % 7 // lunes = 0
  return sumarDias(iso, -dia)
}

export function cargaDelEquipo(barras: Iterable<BarraGuardada>, hoy: string, cuantasSemanas = 4): { semanas: Semana[]; filas: FilaDeCarga[] } {
  const primerLunes = lunesDe(hoy)
  const semanas: Semana[] = Array.from({ length: cuantasSemanas }, (_, i) => {
    const desde = sumarDias(primerLunes, 7 * i)
    return { desde, hasta: sumarDias(desde, 6) }
  })
  const ultimoDia = semanas[semanas.length - 1].hasta
  const porPersona = new Map<number, FilaDeCarga>()

  for (const b of barras) {
    for (const t of b.tareas ?? []) {
      if (t.estado === 'hecha' || t.asignadoA == null) continue
      let fila = porPersona.get(t.asignadoA)
      if (!fila) {
        fila = { personaId: t.asignadoA, total: 0, vencidas: 0, porSemana: semanas.map(() => 0), masAdelante: 0, sinFecha: 0, tareas: [] }
        porPersona.set(t.asignadoA, fila)
      }
      fila.total++
      fila.tareas.push({ id: t.id, titulo: t.titulo, vence: t.vence, accionId: b.id, accion: b.nombre })
      if (!t.vence) fila.sinFecha++
      else if (t.vence < hoy) fila.vencidas++
      else if (t.vence > ultimoDia) fila.masAdelante++
      else fila.porSemana[semanas.findIndex(s => t.vence! >= s.desde && t.vence! <= s.hasta)]++
    }
  }

  const filas = [...porPersona.values()]
  for (const f of filas) {
    // Las que vencen antes, primero; las sin fecha, al final.
    f.tareas.sort((a, b) => (a.vence ?? '9999').localeCompare(b.vence ?? '9999') || a.titulo.localeCompare(b.titulo))
  }
  // Los más cargados arriba: primero lo vencido, después lo de esta semana.
  filas.sort((a, b) => b.vencidas - a.vencidas || b.porSemana[0] - a.porSemana[0] || b.total - a.total || a.personaId - b.personaId)
  return { semanas, filas }
}

export function nivelDeCarga(n: number): 'nada' | 'normal' | 'alta' | 'excesiva' {
  if (n <= 0) return 'nada'
  if (n >= CARGA_EXCESIVA) return 'excesiva'
  if (n >= CARGA_ALTA) return 'alta'
  return 'normal'
}
