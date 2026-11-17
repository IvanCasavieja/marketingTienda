// ---------------------------------------------------------------------------
// El tablero de tarjetas estilo Trello (16/11/2026).
//
// Ivan: "La agencia tiene que tener otro tipo de entrada… una vista estilo
// Trello, que es a lo que están acostumbrados: Ingresado, En proceso,
// Esperando feedback, Finalizado, Archivado. Podemos ir arrastrando las
// tarjetas de un lado a otro."
//
// Las reglas (qué columna, quién mueve qué) las decide el servidor:
// backend/app/services/entregas.py (columna_de, movimiento). Cada tarjeta trae
// `puedo.mover`: a qué columnas la puede llevar quien mira. Acá están los
// nombres, los colores, cómo se dice la fecha y el orden de cada columna.
//
// Este archivo es puro (sin React ni '@/') a propósito: lo prueban las
// pruebas, que se compilan con tsc a secas.
// ---------------------------------------------------------------------------

import type { Columna, QuienLaHace, Tarjeta } from './entregas'

export type DefColumna = {
  clave: Columna
  titulo: string
  bajada: string
  /** El punto del título y el borde de arriba de la columna. */
  punto: string
  /** El fondo suave de la columna, en claro y en oscuro. */
  fondo: string
  /** Cuando se arrastra encima y se puede soltar. */
  destino: string
}

export const COLUMNAS_DEL_TABLERO: DefColumna[] = [
  {
    clave: 'ingresado', titulo: 'Ingresado', bajada: 'Nueva: todavía no se arrancó',
    punto: 'bg-slate-500', fondo: 'bg-slate-100 dark:bg-slate-900/70', destino: 'ring-slate-400',
  },
  {
    clave: 'en-proceso', titulo: 'En proceso', bajada: 'La están trabajando',
    punto: 'bg-sky-500', fondo: 'bg-sky-50 dark:bg-sky-950/40', destino: 'ring-sky-400',
  },
  {
    clave: 'esperando', titulo: 'Esperando feedback', bajada: 'Entregada: le toca al equipo',
    punto: 'bg-amber-500', fondo: 'bg-amber-50 dark:bg-amber-950/30', destino: 'ring-amber-400',
  },
  {
    clave: 'finalizado', titulo: 'Finalizado', bajada: 'Aprobada',
    punto: 'bg-emerald-500', fondo: 'bg-emerald-50 dark:bg-emerald-950/30', destino: 'ring-emerald-400',
  },
  {
    clave: 'archivado', titulo: 'Archivado', bajada: 'Pasa sola a los 10 días',
    punto: 'bg-slate-400', fondo: 'bg-slate-100/70 dark:bg-slate-900/50', destino: 'ring-slate-400',
  },
]

export function defColumna(c: Columna): DefColumna {
  return COLUMNAS_DEL_TABLERO.find(x => x.clave === c) ?? COLUMNAS_DEL_TABLERO[0]
}

/** Lo que pasa al soltar una tarjeta en otra columna, dicho para el botón de
 *  "Mover a…" (y para el aviso de por qué no se puede). */
export function queHaceMover(desde: Columna, a: Columna): string {
  if (a === 'esperando') return 'Entregar los materiales'
  if (desde === 'esperando' && a === 'en-proceso') return 'Pedir cambios'
  if (desde === 'esperando' && a === 'finalizado') return 'Aprobar'
  if (desde === 'ingresado' && a === 'en-proceso') return 'Arrancar'
  if (desde === 'en-proceso' && a === 'ingresado') return 'Volver a Ingresado'
  if (a === 'archivado') return 'Archivar'
  if (desde === 'archivado') return 'Sacar del archivo'
  return defColumna(a).titulo
}

function fechaCorta(iso: string): string {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
}

/**
 * "Para el 25/11 · 3 días antes del Ciberlunes" (o "· el día que arranca el
 * Ciberlunes"). Vencida si la fecha ya pasó y la tarjeta todavía no se
 * finalizó: se pinta en rojo. Sin fecha, null.
 */
export function textoDeFecha(
  t: Pick<Tarjeta, 'vence' | 'ancla' | 'anclaDias' | 'columna'> & { accion: { nombre: string } },
  hoy: string,
): { texto: string; vencida: boolean } | null {
  if (!t.vence) return null
  const terminada = t.columna === 'finalizado' || t.columna === 'archivado'
  const vencida = !terminada && t.vence < hoy
  let texto = `Para el ${fechaCorta(t.vence)}`
  if (t.ancla && t.anclaDias != null) {
    const n = Math.abs(t.anclaDias)
    const momento = t.ancla === 'inicio' ? 'arranca' : 'termina'
    const relativo = t.anclaDias === 0
      ? `el día que ${momento}`
      : `${n} ${n === 1 ? 'día' : 'días'} ${t.anclaDias < 0 ? 'antes' : 'después'} ${t.ancla === 'inicio' ? 'del inicio de' : 'del fin de'}`
    texto += ` · ${relativo} ${t.accion.nombre}`
  }
  return { texto, vencida }
}

/** "Agencia Pampa", "Estudio X (lo carga Lucía)", "Ana (Tienda)". */
export function quienLaHaceTexto(h: QuienLaHace | null | undefined): string | null {
  if (!h || !h.nombre) return null
  if (h.tipo === 'fuera') return h.carga ? `${h.nombre} · lo carga ${h.carga}` : h.nombre
  if (h.tipo === 'tienda') return `${h.nombre} (Tienda)`
  return h.nombre
}

/** La clave y el nombre de "quién la hace" para el filtro del equipo. Todo
 *  lo de Tienda va junto ("Diseño de Tienda"); cada agencia, aparte. */
export function grupoDeQuien(h: QuienLaHace | null | undefined): { clave: string; nombre: string } {
  if (!h || h.tipo === 'tienda' || !h.nombre) return { clave: 'tienda', nombre: 'Diseño de Tienda' }
  const nombre = h.tipo === 'fuera' ? `${h.nombre} (de afuera)` : h.nombre
  return { clave: `${h.tipo}:${h.nombre.toLocaleLowerCase('es')}`, nombre }
}

/** Las opciones del filtro "¿Quién la hace?", con cuántas tarjetas tiene cada una. */
export function opcionesDeQuien(tarjetas: Pick<Tarjeta, 'hace'>[]): { clave: string; nombre: string; cuantas: number }[] {
  const por = new Map<string, { clave: string; nombre: string; cuantas: number }>()
  for (const t of tarjetas) {
    const g = grupoDeQuien(t.hace)
    const actual = por.get(g.clave)
    if (actual) actual.cuantas++
    else por.set(g.clave, { ...g, cuantas: 1 })
  }
  return [...por.values()].sort((a, b) => b.cuantas - a.cuantas || a.nombre.localeCompare(b.nombre, 'es'))
}

export function deQuien(t: Pick<Tarjeta, 'hace'>, clave: string | null): boolean {
  return !clave || grupoDeQuien(t.hace).clave === clave
}

/**
 * El orden de una columna: lo que le toca a quien mira, primero; después lo
 * que vence antes. En Archivado, lo archivado más reciente arriba.
 */
export function ordenar(lista: Tarjeta[], columna: Columna, meToca: (t: Tarjeta) => boolean): Tarjeta[] {
  if (columna === 'archivado') {
    return [...lista].sort((a, b) => (b.archivadaEl ?? '').localeCompare(a.archivadaEl ?? '') || a.titulo.localeCompare(b.titulo, 'es'))
  }
  return [...lista].sort((a, b) =>
    Number(meToca(b)) - Number(meToca(a))
    || (a.vence ?? '9999').localeCompare(b.vence ?? '9999')
    || a.titulo.localeCompare(b.titulo, 'es'))
}

/** Si el arrastre se soltó sobre una columna a la que se puede llevar. */
export function sePuedeSoltar(t: Pick<Tarjeta, 'columna' | 'puedo'>, a: Columna | null): boolean {
  return !!a && a !== t.columna && !!t.puedo?.mover.includes(a)
}

/** Cuánto hay que mantener apretado en el teléfono para que arranque el
 *  arrastre (antes de eso, mover el dedo es hacer scroll). */
export const MS_PARA_ARRASTRAR_CON_EL_DEDO = 280
/** Cuánto se tiene que mover el mouse para que sea un arrastre y no un clic. */
export const PX_PARA_ARRASTRAR = 6
