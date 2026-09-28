const MESES_ES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','setiembre','octubre','noviembre','diciembre']

export function nombreMes(clave: string): string {
  const [a, m] = clave.split('-').map(Number)
  return `${MESES_ES[m - 1]} ${a}`
}

export function diasDelMes(clave: string): number {
  const [a, m] = clave.split('-').map(Number)
  return new Date(a, m, 0).getDate()
}

/** Inicial del dia de la semana en espanol, como lo escribe el Excel. */
export function dowDelMes(clave: string): Record<string, string> {
  const [a, m] = clave.split('-').map(Number)
  const letras = ['D', 'L', 'M', 'M', 'J', 'V', 'S']
  const out: Record<string, string> = {}
  for (let d = 1; d <= diasDelMes(clave); d++) out[String(d)] = letras[new Date(a, m - 1, d).getDay()]
  return out
}

export function esFinde(clave: string, dia: number): boolean {
  const [a, m] = clave.split('-').map(Number)
  const g = new Date(a, m - 1, dia).getDay()
  return g === 0 || g === 6
}

export function mesSiguiente(clave: string, paso: number): string {
  const [a, m] = clave.split('-').map(Number)
  const d = new Date(a, m - 1 + paso, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** Hoy, o null si hoy no cae dentro del mes que se esta mirando. */
export function diaDeHoy(clave: string): number | null {
  const hoy = new Date()
  const c = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`
  return c === clave ? hoy.getDate() : null
}

// ---------------------------------------------------------------------------
// Fechas reales, 'YYYY-MM-DD'
// ---------------------------------------------------------------------------
// Desde el 28/09/2026 una barra no es "del dia X al Y de su mes" sino de una
// fecha a otra, y puede cruzar de mes. Se manejan como texto ISO: se comparan
// con < y > sin convertir, y las cuentas se hacen en UTC para que un cambio de
// hora no corra un dia.

/** La fecha del dia `dia` del mes `clave`. */
export function isoDe(clave: string, dia: number): string {
  return `${clave}-${String(dia).padStart(2, '0')}`
}

/** El mes ('YYYY-MM') de una fecha. */
export function claveDe(iso: string): string {
  return iso.slice(0, 7)
}

/** El dia del mes de una fecha. */
export function diaDe(iso: string): number {
  return Number(iso.slice(8, 10))
}

export function primerDiaDe(clave: string): string {
  return isoDe(clave, 1)
}

export function ultimoDiaDe(clave: string): string {
  return isoDe(clave, diasDelMes(clave))
}

function aUTC(iso: string): number {
  const [a, m, d] = iso.split('-').map(Number)
  return Date.UTC(a, m - 1, d)
}

function deUTC(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

export function sumarDias(iso: string, n: number): string {
  return deUTC(aUTC(iso) + n * 86_400_000)
}

/** Cuantos dias van de `desde` a `hasta` (0 si son el mismo). */
export function diasEntre(desde: string, hasta: string): number {
  return Math.round((aUTC(hasta) - aUTC(desde)) / 86_400_000)
}

/** Todas las fechas de `desde` a `hasta`, inclusive. */
export function fechasDe(desde: string, hasta: string): string[] {
  const out: string[] = []
  for (let f = desde; f <= hasta; f = sumarDias(f, 1)) out.push(f)
  return out
}

/** '25/09' */
export function fechaCorta(iso: string): string {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
}

/** '25 de setiembre', con el año si no es el de `referencia`. */
export function fechaLarga(iso: string, referencia?: string): string {
  const [a, m, d] = iso.split('-').map(Number)
  const anio = referencia && referencia.slice(0, 4) === iso.slice(0, 4) ? '' : ` de ${a}`
  return `${d} de ${MESES_ES[m - 1]}${anio}`
}

/** 'del 25 de setiembre al 5 de octubre de 2026' */
export function rangoLargo(desde: string, hasta: string): string {
  if (desde === hasta) return `el ${fechaLarga(desde)}`
  const mismoAnio = desde.slice(0, 4) === hasta.slice(0, 4)
  return `del ${fechaLarga(desde, mismoAnio ? hasta : undefined)} al ${fechaLarga(hasta)}`
}

/** Hoy, en la hora de la computadora. */
export function hoyIso(): string {
  const h = new Date()
  return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, '0')}-${String(h.getDate()).padStart(2, '0')}`
}
