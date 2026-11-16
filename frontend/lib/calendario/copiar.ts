// ---------------------------------------------------------------------------
// Copiar una acción a otra fecha ("copiar del año pasado").
//
// Pedido de Ivan (15/11/2026): las acciones se repiten cada año y el
// Ciberlunes 2026 tiene que nacer del 2025 con todo lo que tenía. La copia la
// hace el servidor (POST /calendario/barras/{id}/copiar, ver
// backend/app/services/calendario_copia.py); acá está lo que la pantalla
// necesita saber ANTES de copiar, para mostrarlo: a qué fecha va, cómo queda
// el nombre, si choca con otra y qué se lleva.
// ---------------------------------------------------------------------------

import { diasEntre, sumarDias } from './fechas'
import type { BarraGuardada } from './tipos'

/** 52 semanas: la copia cae el mismo día de la semana que la original (el
 *  Ciberlunes es lunes los dos años). 365 lo corría un día. */
export const DIAS_AL_ANIO_QUE_VIENE = 364

export function alAnioQueViene(desde: string): string {
  return sumarDias(desde, DIAS_AL_ANIO_QUE_VIENE)
}

/** Dónde termina la copia si arranca en `desde`: dura lo mismo que la original. */
export function rangoDeLaCopia(origen: Pick<BarraGuardada, 'desde' | 'hasta'>, desde: string) {
  return { desde, hasta: sumarDias(desde, diasEntre(origen.desde, origen.hasta)) }
}

// Cuatro dígitos sueltos, con lo que tienen adelante (que no sea un dígito)
// aparte. Sin "lookbehind" a propósito: un Safari de iPhone anterior al 16.4
// no lo entiende y no cargaría el calendario.
const ANIO = /(^|\D)(\d{4})(?!\d)/g

/**
 * El nombre de la copia: si arranca en otro año que la original, los años
 * del nombre se corren lo mismo ("Ciberlunes 2025" → "Ciberlunes 2026").
 * Solo los que tienen que ver con las fechas de la acción (de un año antes de
 * que arranque a uno después de que termine): el "Mundial 2030" de una acción
 * de 2025 queda como está.
 *
 * Es la misma regla que `nombre_para_la_copia` del backend: si cambia una,
 * cambia la otra.
 */
export function nombreParaLaCopia(nombre: string, desde: string, hasta: string, desdeNueva: string): string {
  const anioDesde = Number(desde.slice(0, 4))
  const anioHasta = Number(hasta.slice(0, 4))
  const salto = Number(desdeNueva.slice(0, 4)) - anioDesde
  if (salto === 0) return nombre
  return nombre.replace(ANIO, (todo, antes: string, m: string) => {
    const anio = Number(m)
    if (anio < anioDesde - 1 || anio > anioHasta + 1) return todo
    const nuevo = anio + salto
    return nuevo >= 2000 && nuevo <= 2100 ? `${antes}${nuevo}` : todo
  })
}

/** Para comparar nombres sin que importen mayúsculas, tildes ni espacios de más. */
function clave(nombre: string): string {
  return nombre.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()
}

/**
 * Una acción del mismo nombre que ya está en esas fechas: copiar ahí la
 * duplicaría (alguien ya copió el Ciberlunes de este año, o se eligió una
 * fecha que pisa a la original). No frena la copia: se avisa y se decide.
 */
export function chocaCon(
  barras: BarraGuardada[], seccion: BarraGuardada['seccion'], nombre: string, desde: string, hasta: string,
): BarraGuardada | null {
  const buscado = clave(nombre)
  if (!buscado) return null
  return barras.find(b =>
    b.seccion === seccion && clave(b.nombre) === buscado && b.desde <= hasta && desde <= b.hasta,
  ) ?? null
}

export type ResumenDeCopia = {
  piezas: number
  /** Las que se copian: 0 si la persona no puede cargar tareas. */
  tareas: number
  /** Las que NO se copian porque la persona no puede cargar tareas. */
  tareasSinPermiso: number
  /** Tareas que se copian sin responsable: esa persona ya no ve el mundo. */
  sinResponsable: number
  avisos: number
  /** Personas que salen de algún aviso porque ya no ven el mundo. */
  destinatariosQuitados: number
  /** Avisos que no se copian porque se quedan sin nadie. */
  avisosSinNadie: number
}

/**
 * Lo que se va a llevar la copia, para decirlo antes de copiar. `queVen` son
 * los ids de quienes pueden abrir este calendario (la lista de personas del
 * mundo); sin ella (todavía no llegó) no se adivina a quién se saca, y el
 * servidor lo dice después.
 */
export function queSeCopia(accion: BarraGuardada, queVen: Set<number> | null, cargaTareas: boolean): ResumenDeCopia {
  const tareas = accion.tareas ?? []
  const copiadas = cargaTareas ? tareas : []
  let destinatariosQuitados = 0
  let avisosSinNadie = 0
  for (const a of accion.avisos ?? []) {
    const quedan = queVen ? a.destinatarios.filter(u => queVen.has(u)).length : a.destinatarios.length
    destinatariosQuitados += a.destinatarios.length - quedan
    if (quedan === 0) avisosSinNadie++
  }
  return {
    piezas: (accion.piezas ?? []).length,
    tareas: copiadas.length,
    tareasSinPermiso: cargaTareas ? 0 : tareas.length,
    sinResponsable: queVen ? copiadas.filter(t => t.asignadoA != null && !queVen.has(t.asignadoA)).length : 0,
    avisos: (accion.avisos ?? []).length - avisosSinNadie,
    destinatariosQuitados,
    avisosSinNadie,
  }
}

const DIAS_DE_LA_SEMANA = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado']

/** 'lunes', para decir "cae lunes, como la original". */
export function diaDeLaSemana(iso: string): string {
  const [a, m, d] = iso.split('-').map(Number)
  return DIAS_DE_LA_SEMANA[new Date(Date.UTC(a, m - 1, d)).getUTCDay()]
}

/** "1 tarea", "3 tareas". */
export function cuantas(n: number, una: string, varias: string): string {
  return `${n} ${n === 1 ? una : varias}`
}

/** "a, b y c". */
export function enLista(cosas: string[]): string {
  if (cosas.length <= 1) return cosas[0] ?? ''
  return `${cosas.slice(0, -1).join(', ')} y ${cosas[cosas.length - 1]}`
}
