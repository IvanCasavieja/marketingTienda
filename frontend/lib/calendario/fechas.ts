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
