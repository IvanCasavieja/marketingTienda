// Lo que devuelve /clientes-vip (backend/app/services/clientes_vip.py).

export const SEGMENTOS = ['Creciendo', 'Estable', 'Nuevo', 'Bajando', 'En riesgo', 'Perdido'] as const
export type Segmento = (typeof SEGMENTOS)[number]

/** Qué quiere decir cada segmento, en una línea (lo mismo que `perfil` en el servidor). */
export const QUE_ES: Record<Segmento, string> = {
  Creciendo: 'Sus últimos 3 meses subieron más de 10% contra los 3 de antes',
  Estable: 'Compra parecido a los meses anteriores',
  Nuevo: 'Empezó a comprar en los últimos 3 meses',
  Bajando: 'Sus últimos 3 meses bajaron entre 10% y 40%',
  'En riesgo': 'No compró el último mes, o sus compras cayeron más de 40%',
  Perdido: 'No compra hace 3 meses o más',
}

export type KpiMes = {
  mes: string; venta: number; margen: number; clientes: number; tickets: number; unidades: number
  venta_ecommerce: number; venta_smart: number; venta_marca_propia: number
  ticket_promedio: number; frecuencia: number
}

export type FilaDimension = {
  valor: string; venta_mes: number; clientes_mes: number; venta_3m: number; venta_3m_antes: number
  margen_3m: number | null; contra_3m_antes: number | null; contra_anio_anterior: number | null
}

export type SegmentoResumen = {
  segmento: Segmento; clientes: number; venta_3m: number; venta_3m_antes: number; venta_esperada: number
}

export type Prediccion = {
  mes: string; venta: number; desde: number; hasta: number; margen_error: number
  contra_este_mes: number | null; contra_anio_anterior: number | null; como: string
}

export type Informe = {
  id: number; mes: string; analisis: string; prediccion: Prediccion | Record<string, never>
  con_ia: boolean; enviado_a: number; fecha: string | null
}

export type Carga = {
  id: number; archivo: string; meses: string[]; filas_archivo: number; filas: number; clientes: number
  venta: number; estado: 'cargando' | 'lista'; subido_por: string | null; fecha: string | null
}

export type Tablero = {
  ultimo_mes: string | null
  meses: KpiMes[]
  dimensiones: Record<'categoria' | 'sucursal' | 'canal' | 'marca_propia', FilaDimension[]>
  segmentos: SegmentoResumen[]
  prediccion: Prediccion | null
  informe: Informe | null
  cargas: Carga[]
  clientes: number
}

export type ClienteVip = {
  id_cliente: number; segmento: Segmento; riesgo: number; venta_esperada: number; venta_12m: number
  venta_3m: number; venta_3m_antes: number; margen_12m: number; tickets_12m: number; meses_con_compra: number
  ultimo_mes: string | null; sucursal: string | null; categoria: string | null; parte_ecommerce: number
}

export type MesDeCliente = {
  mes: string; venta: number; margen: number; unidades: number; tickets: number; dias: number
  venta_ecommerce: number; venta_smart: number; venta_marca_propia: number; sucursal: string | null
  categorias: { nombre: string; venta: number }[]
}

const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

/** "2026-10" → "oct 26" */
export function mesCorto(mes: string): string {
  const [a, m] = mes.split('-')
  return `${MESES_CORTOS[Number(m) - 1]} ${a.slice(2)}`
}

/** "2026-10" → "octubre 2026" */
export function mesLargo(mes: string): string {
  const [a, m] = mes.split('-')
  return `${MESES[Number(m) - 1]} ${a}`
}

/** Plata en corto: $ 280,4 M · $ 45.300 */
export function plata(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `$ ${(n / 1_000_000).toLocaleString('es-UY', { maximumFractionDigits: 1 })} M`
  return `$ ${Math.round(n).toLocaleString('es-UY')}`
}

export function numero(n: number | null | undefined, decimales = 0): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  return n.toLocaleString('es-UY', { maximumFractionDigits: decimales, minimumFractionDigits: decimales })
}

/** Los meses de `desde` a `hasta` ("AAAA-MM"), los dos incluidos. */
export function mesesEntre(desde: string, hasta: string): string[] {
  const salida: string[] = []
  let [a, m] = desde.split('-').map(Number)
  const [ah, mh] = hasta.split('-').map(Number)
  while (a < ah || (a === ah && m <= mh)) {
    salida.push(`${a}-${String(m).padStart(2, '0')}`)
    m++
    if (m > 12) { m = 1; a++ }
  }
  return salida
}

export function variacion(ahora: number | null | undefined, antes: number | null | undefined): number | null {
  if (!ahora || !antes) return null
  return Math.round(1000 * (ahora / antes - 1)) / 10
}
