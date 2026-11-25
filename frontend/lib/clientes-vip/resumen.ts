// ---------------------------------------------------------------------------
// Clientes VIP: el resumen que arma el navegador con el archivo del mes.
//
// Ivan (25/11/2026): "cargar el excel que pesa 500mb espero no sea necesario".
// No lo es: el CSV (una fila por línea de ticket, 14 millones de filas en
// 2026) se lee acá de a pedazos y se sube solo una fila por cliente y por mes
// (~120.000 por año) y los totales del mes por categoría, sucursal, canal y
// marca propia. El archivo nunca sale de la PC. Lo usa lector.worker.ts; el
// servidor lo recibe en backend/app/api/routes/clientes_vip.py.
//
// Supone lo que muestran los archivos: separado por ";", las filas de un
// mismo ticket vienen juntas (así se cuentan los tickets sin guardarlos) y los
// números con punto decimal (si viene coma, también se lee).
// ---------------------------------------------------------------------------

/** [id_cliente, "AAAA-MM", venta, margen, unidades, tickets, dias, venta_ecommerce,
 *  venta_smart, venta_marca_propia, sucursal, categorias] — el orden que espera el servidor. */
export type FilaResumen = [number, string, number, number, number, number, number, number, number, number, string | null, string | null]

export type Dimension = 'categoria' | 'sucursal' | 'canal' | 'marca_propia'

export type TotalDelMes = {
  mes: string; dimension: Dimension; valor: string
  venta: number; margen: number; unidades: number; tickets: number; clientes: number
}

export type Resumen = {
  filas: FilaResumen[]
  dimensiones: TotalDelMes[]
  meses: string[]
  filasArchivo: number
  descartadas: number
  clientes: number
  venta: number
}

export const COLUMNAS = [
  'id_cliente', 'id_ticket', 'fecha', 'sucursal', 'canal', 'categoria', 'marca_propia', 'unidades',
  'venta_neta_sin_iva', 'margen_neto_sin_iva',
] as const

type Columna = (typeof COLUMNAS)[number]

const CANALES = ['Tienda Inglesa', 'E-commerce', 'Smart', 'Sin clasificar'] as const
const MAX_CATEGORIAS = 64

type Acum = {
  cliente: number; mes: string
  venta: number; margen: number; unidades: number; tickets: number; dias: number
  canal: Float64Array // venta por canal (CANALES; lo que no está, en "Sin clasificar")
  mp: Float64Array // venta: [marca propia, otras marcas, sin dato]
  sucursal: Map<string, number>
  categoria: Float32Array
}

type AcumDim = { venta: number; margen: number; unidades: number; tickets: number; ultimoTicket: string }

export class ArchivoInvalido extends Error {}

export function numero(texto: string | undefined): number {
  if (!texto) return 0
  let t = texto.trim()
  if (t.includes(',') && !t.includes('.')) t = t.replace(',', '.')
  const n = Number(t)
  return Number.isFinite(n) ? n : 0
}

/** "2026-03-14…" o "14/03/2026" → "2026-03"; null si no es una fecha. */
export function mesDe(fecha: string | undefined): string | null {
  const f = (fecha ?? '').trim()
  let m = /^(\d{4})-(\d{2})/.exec(f)
  if (m) return `${m[1]}-${m[2]}`
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(f)
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}`
  return null
}

function diaDe(fecha: string): number {
  const m = /^\d{4}-\d{2}-(\d{2})/.exec(fecha) ?? /^(\d{1,2})\//.exec(fecha)
  const d = m ? Number(m[1]) : 0
  return d >= 1 && d <= 31 ? d : 0
}

function contarBits(n: number): number {
  let c = 0
  for (let x = n >>> 0; x; x &= x - 1) c++
  return c
}

function canalDe(texto: string): number {
  const i = (CANALES as readonly string[]).indexOf(texto.trim())
  return i >= 0 ? i : 3
}

function marcaPropia(texto: string): 0 | 1 | 2 {
  const t = texto.trim().toLowerCase()
  if (t === 'si' || t === 'sí' || t === 's' || t === 'true' || t === '1') return 0
  if (t === 'no' || t === 'n' || t === 'false' || t === '0') return 1
  return 2
}

const NOMBRE_MP = ['Marca propia', 'Otras marcas', 'Sin dato']

export class Resumidor {
  private idx: Record<Columna, number> | null = null
  private resto = ''
  private ultimoTicket = ''
  private porClienteMes = new Map<string, Acum>()
  private dims = new Map<string, AcumDim>()
  private categorias: string[] = []
  private idxCategoria = new Map<string, number>()
  filasArchivo = 0
  descartadas = 0

  /** Cada CSV trae su propia primera fila con los nombres de las columnas. */
  nuevoArchivo(): void {
    if (this.resto) this.linea(this.resto)
    this.resto = ''
    this.idx = null
  }

  agregarTexto(texto: string): void {
    const todo = this.resto + texto
    const lineas = todo.split('\n')
    this.resto = lineas.pop() ?? ''
    for (const l of lineas) this.linea(l)
  }

  private cabecera(linea: string): void {
    const nombres = linea.replace(/^﻿/, '').split(';').map(c => c.trim().toLowerCase())
    const faltan = COLUMNAS.filter(c => !nombres.includes(c))
    if (faltan.length) {
      throw new ArchivoInvalido(
        `Al archivo le faltan columnas: ${faltan.join(', ')}. Tiene que ser el CSV de compras de los clientes VIP, separado por punto y coma.`,
      )
    }
    this.idx = Object.fromEntries(COLUMNAS.map(c => [c, nombres.indexOf(c)])) as Record<Columna, number>
  }

  private indiceCategoria(nombre: string): number {
    let i = this.idxCategoria.get(nombre)
    if (i === undefined) {
      if (this.categorias.length >= MAX_CATEGORIAS - 1) {
        i = MAX_CATEGORIAS - 1
        this.categorias[i] = 'Otras'
      } else {
        i = this.categorias.length
        this.categorias.push(nombre)
      }
      this.idxCategoria.set(nombre, i)
    }
    return i
  }

  private sumarDim(mes: string, dim: Dimension, valor: string, ticket: string, venta: number, margen: number, unidades: number) {
    const clave = `${mes}|${dim}|${valor}`
    let a = this.dims.get(clave)
    if (!a) {
      a = { venta: 0, margen: 0, unidades: 0, tickets: 0, ultimoTicket: '' }
      this.dims.set(clave, a)
    }
    a.venta += venta
    a.margen += margen
    a.unidades += unidades
    if (a.ultimoTicket !== ticket) {
      a.tickets++
      a.ultimoTicket = ticket
    }
  }

  private linea(cruda: string): void {
    const l = cruda.endsWith('\r') ? cruda.slice(0, -1) : cruda
    if (!l.trim()) return
    if (!this.idx) return this.cabecera(l)
    const i = this.idx
    const c = l.split(';')
    this.filasArchivo++
    const cliente = Number(c[i.id_cliente])
    const fecha = c[i.fecha] ?? ''
    const mes = mesDe(fecha)
    if (!Number.isInteger(cliente) || cliente <= 0 || !mes) {
      this.descartadas++
      return
    }
    const ticket = c[i.id_ticket] ?? ''
    const venta = numero(c[i.venta_neta_sin_iva])
    const margen = numero(c[i.margen_neto_sin_iva])
    const unidades = numero(c[i.unidades])
    const sucursal = (c[i.sucursal] ?? '').trim() || 'Sin sucursal'
    const categoria = ((c[i.categoria] ?? '').trim() || 'Sin categoría').replace(/=/g, '-')
    const canal = canalDe(c[i.canal] ?? '')
    const mp = marcaPropia(c[i.marca_propia] ?? '')

    const clave = `${cliente}|${mes}`
    let a = this.porClienteMes.get(clave)
    if (!a) {
      a = {
        cliente, mes, venta: 0, margen: 0, unidades: 0, tickets: 0, dias: 0,
        canal: new Float64Array(CANALES.length), mp: new Float64Array(3),
        sucursal: new Map(), categoria: new Float32Array(MAX_CATEGORIAS),
      }
      this.porClienteMes.set(clave, a)
    }
    a.venta += venta
    a.margen += margen
    a.unidades += unidades
    if (ticket !== this.ultimoTicket) {
      a.tickets++
      this.ultimoTicket = ticket
    }
    const dia = diaDe(fecha)
    if (dia) a.dias |= 1 << (dia - 1)
    a.canal[canal] += venta
    a.mp[mp] += venta
    a.sucursal.set(sucursal, (a.sucursal.get(sucursal) ?? 0) + venta)
    a.categoria[this.indiceCategoria(categoria)] += venta

    this.sumarDim(mes, 'categoria', this.categorias[this.indiceCategoria(categoria)], ticket, venta, margen, unidades)
    this.sumarDim(mes, 'sucursal', sucursal, ticket, venta, margen, unidades)
    this.sumarDim(mes, 'canal', CANALES[canal], ticket, venta, margen, unidades)
    this.sumarDim(mes, 'marca_propia', NOMBRE_MP[mp], ticket, venta, margen, unidades)
  }

  terminar(): Resumen {
    this.nuevoArchivo()
    if (!this.filasArchivo) throw new ArchivoInvalido('El archivo no tiene filas de compras.')
    const filas: FilaResumen[] = []
    const clientesPorDim = new Map<string, number>()
    const sumarCliente = (clave: string) => clientesPorDim.set(clave, (clientesPorDim.get(clave) ?? 0) + 1)
    const clientes = new Set<number>()
    let ventaTotal = 0

    for (const a of this.porClienteMes.values()) {
      clientes.add(a.cliente)
      ventaTotal += a.venta
      let sucursal: string | null = null
      let mejor = -Infinity
      for (const [s, v] of a.sucursal) {
        if (v > 0) sumarCliente(`${a.mes}|sucursal|${s}`)
        if (v > mejor) { mejor = v; sucursal = s }
      }
      const cats: [string, number][] = []
      a.categoria.forEach((v, k) => {
        if (v > 0 && this.categorias[k] !== undefined) cats.push([this.categorias[k], v])
      })
      for (const [nombre] of cats) sumarCliente(`${a.mes}|categoria|${nombre}`)
      a.canal.forEach((v, k) => { if (v > 0) sumarCliente(`${a.mes}|canal|${CANALES[k]}`) })
      a.mp.forEach((v, k) => { if (v > 0) sumarCliente(`${a.mes}|marca_propia|${NOMBRE_MP[k]}`) })
      cats.sort((x, y) => y[1] - x[1])
      const top = cats.slice(0, 3).map(([n, v]) => `${n.slice(0, 60)}=${Math.round(v)}`).join(';')
      filas.push([
        a.cliente, a.mes, Math.round(a.venta), Math.round(a.margen), Math.round(a.unidades), a.tickets,
        contarBits(a.dias), Math.round(a.canal[1]), Math.round(a.canal[2]), Math.round(a.mp[0]),
        sucursal ? sucursal.slice(0, 80) : null, top || null,
      ])
    }

    const dimensiones: TotalDelMes[] = []
    for (const [clave, d] of this.dims) {
      const [mes, dimension, ...resto] = clave.split('|')
      dimensiones.push({
        mes, dimension: dimension as Dimension, valor: resto.join('|').slice(0, 120),
        venta: Math.round(d.venta), margen: Math.round(d.margen), unidades: Math.round(d.unidades),
        tickets: d.tickets, clientes: clientesPorDim.get(clave) ?? 0,
      })
    }
    const meses = [...new Set(filas.map(f => f[1]))].sort()
    return { filas, dimensiones, meses, filasArchivo: this.filasArchivo, descartadas: this.descartadas,
             clientes: clientes.size, venta: Math.round(ventaTotal) }
  }
}
