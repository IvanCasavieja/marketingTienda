// ---------------------------------------------------------------------------
// Lógica de dominio pura: armar un mes con las barras que lo tocan, bajar lo
// que corresponde al calendario de headers y contar la ocupación. Sin React ni
// zustand a propósito, así se puede testear sin levantar nada.
//
// Desde el 28/09/2026 lo que se guarda son barras con fechas reales, y una
// barra puede cruzar de mes. El mes es una VISTA: se arma acá cada vez, con lo
// que cae adentro recortado a sus días, y la barra avisa si viene de antes o
// sigue después (vieneDeAntes / sigueDespues).
// ---------------------------------------------------------------------------

import { BANDAS_COMERCIAL, BANDAS_RETAIL, idPosicion, type BandaCatalogo } from './catalogo'
import {
  claveDe, diaDe, diasDelMes, dowDelMes, fechasDe, isoDe, primerDiaDe, ultimoDiaDe,
} from './fechas'
import {
  CANALES_DE_ENVIO, REGLAS_HEADER, esPiezaDeEnvio, esPiezaHeader,
  type Banda, type Barra, type BarraGuardada, type Envio, type HeaderSinLugar, type Mes,
  type OrigenHeader, type Pieza, type Seccion,
} from './tipos'

let seq = 0
/** Un id que no choca con el de otra persona creando algo en el mismo momento. */
export const nuevoId = (p: string) =>
  `${p}-${Date.now().toString(36)}-${(seq++).toString(36)}${Math.random().toString(36).slice(2, 6)}`

/** Las posiciones de Retail Media de un mes: las guardadas, o 4, 5 y 6. */
export function posicionesDe(posicionesRM: Record<string, number[]>, clave: string): number[] {
  return posicionesRM[clave] ?? [...REGLAS_HEADER.rmPorDefecto]
}

// ---------------------------------------------------------------------------
// Renglones
// ---------------------------------------------------------------------------

function libre(fila: Barra[], desde: number, hasta: number): boolean {
  return !fila.some(b => b.desde <= hasta && desde <= b.hasta)
}

/**
 * En qué renglón de su banda va una barra nueva (o una que cambió de fechas).
 *
 * Mira TODAS las barras de la banda que se cruzan con sus fechas, no solo las
 * del mes que se está mirando: una acción que cruza de mes tiene que caer en un
 * renglón libre en los dos. Si el renglón donde se hizo clic está libre, va
 * ahí; si no, al primero que esté libre en todo su rango.
 */
export function carrilLibre(
  barras: BarraGuardada[],
  seccion: Seccion,
  banda: string,
  desde: string,
  hasta: string,
  preferido: number,
  excluir?: string,
): number {
  const ocupados = new Set(
    barras
      .filter(b => b.seccion === seccion && b.banda === banda && b.id !== excluir
        && b.desde <= hasta && desde <= b.hasta)
      .map(b => b.carril),
  )
  if (!ocupados.has(preferido)) return preferido
  let i = 0
  while (ocupados.has(i)) i++
  return i
}

// ---------------------------------------------------------------------------
// El header de la home, en fechas reales
// ---------------------------------------------------------------------------

/** Un banner puesto en una posición del header, con fechas reales. */
export type TramoHeader = {
  id: string
  nombre: string
  color: string | null
  desde: string
  hasta: string
  posicion: number
  origen: OrigenHeader
}

export type HeaderDerivado = {
  tramos: TramoHeader[]
  sinLugar: { accionId: string; nombre: string; inicio: string; fin: string; diasLlenos: string[] }[]
}

/**
 * Baja al header todo lo que le corresponde, mirando TODAS las fechas y no un
 * mes solo:
 *
 *  - Lo cargado a mano queda en su posición.
 *  - Retail Media: cada renglón del formato HOME SLIDER cae en la posición que
 *    RM tenga reservada ese mes (por defecto 4, 5 y 6). Si RM se mueve de
 *    posición a mitad de una campaña que cruza de mes, la campaña cambia de
 *    posición el día 1.
 *  - Marketing: cada acción con pieza `Header` baja a la primera posición que
 *    esté libre y no sea de RM en TODO su rango. Así una acción que cruza de
 *    mes queda en la misma posición en los dos.
 *
 * Lo que no entra no se descarta ni le saca el lugar a nadie: se junta en
 * `sinLugar` para que el sistema avise. Qué se baja lo decide una persona
 * mirando la venta, no esto.
 */
export function derivarHeaders(
  barras: BarraGuardada[],
  posicionesRM: Record<string, number[]>,
): HeaderDerivado {
  const ocupado = new Map<string, Set<number>>()
  const ocupar = (f: string, pos: number) => {
    let s = ocupado.get(f)
    if (!s) ocupado.set(f, (s = new Set()))
    s.add(pos)
  }
  const tramos: TramoHeader[] = []

  // --- Lo cargado a mano ---
  for (const b of barras) {
    if (b.seccion !== 'header') continue
    const pos = Number(b.banda.replace('pos-', ''))
    if (!(pos >= 1 && pos <= REGLAS_HEADER.tope)) continue
    tramos.push({ id: b.id, nombre: b.nombre, color: b.color, desde: b.desde, hasta: b.hasta, posicion: pos, origen: { tipo: 'manual' } })
    for (const f of fechasDe(b.desde, b.hasta)) ocupar(f, pos)
  }

  // --- Retail Media ---
  for (const b of barras) {
    if (b.seccion !== 'retail' || b.banda !== REGLAS_HEADER.formatoHeader) continue
    let actual: TramoHeader | null = null
    let n = 0
    for (const f of fechasDe(b.desde, b.hasta)) {
      const pos = posicionesDe(posicionesRM, claveDe(f))[b.carril]
      if (!pos) { actual = null; continue }
      ocupar(f, pos)
      if (actual && actual.posicion === pos) { actual.hasta = f; continue }
      actual = {
        id: n === 0 ? `rm-${b.id}` : `rm-${b.id}-${n}`,
        nombre: b.nombre, color: b.color, desde: f, hasta: f, posicion: pos,
        origen: { tipo: 'retail', barraId: b.id },
      }
      n++
      tramos.push(actual)
    }
  }

  // --- Acciones de marketing ---
  const sinLugar: HeaderDerivado['sinLugar'] = []
  const pedidos = barras
    .filter(b => b.seccion === 'comercial')
    .flatMap(accion =>
      (accion.piezas ?? []).filter(esPiezaHeader).map(p => ({
        accion,
        desde: p.desde ?? accion.desde,
        hasta: p.hasta ?? accion.hasta,
      })),
    )
    .filter(p => p.desde <= p.hasta)
    .sort((a, b) => a.desde.localeCompare(b.desde) || a.accion.nombre.localeCompare(b.accion.nombre))

  for (const pedido of pedidos) {
    const fechas = fechasDe(pedido.desde, pedido.hasta)
    let pos = 0
    for (let n = 1; n <= REGLAS_HEADER.tope && !pos; n++) {
      if (fechas.every(f => !posicionesDe(posicionesRM, claveDe(f)).includes(n) && !ocupado.get(f)?.has(n))) pos = n
    }
    if (pos) {
      for (const f of fechas) ocupar(f, pos)
      tramos.push({
        id: `ac-${pedido.accion.id}`,
        nombre: pedido.accion.nombre, color: pedido.accion.color,
        desde: pedido.desde, hasta: pedido.hasta, posicion: pos,
        origen: { tipo: 'accion', accionId: pedido.accion.id },
      })
    } else {
      sinLugar.push({
        accionId: pedido.accion.id,
        nombre: pedido.accion.nombre,
        inicio: pedido.desde,
        fin: pedido.hasta,
        diasLlenos: fechas.filter(f => (ocupado.get(f)?.size ?? 0) >= REGLAS_HEADER.tope),
      })
    }
  }

  return { tramos, sinLugar }
}

// ---------------------------------------------------------------------------
// El mes
// ---------------------------------------------------------------------------

/** Una barra con fechas reales, vista dentro del mes `clave`. */
function vistaEn(
  clave: string,
  b: { id: string; nombre: string; color: string | null; desde: string; hasta: string },
  extra: Partial<Barra> = {},
): Barra {
  const ini = primerDiaDe(clave)
  const fin = ultimoDiaDe(clave)
  return {
    id: b.id,
    nombre: b.nombre,
    color: b.color,
    desde: b.desde < ini ? 1 : diaDe(b.desde),
    hasta: b.hasta > fin ? diasDelMes(clave) : diaDe(b.hasta),
    inicio: b.desde,
    fin: b.hasta,
    vieneDeAntes: b.desde < ini,
    sigueDespues: b.hasta > fin,
    ...extra,
  }
}

/**
 * Reparte las barras de una banda en renglones. Cada barra va en su `carril`;
 * si ahí choca con otra (dos personas crearon a la vez en el mismo renglón),
 * baja al siguiente libre en vez de dibujarse encima.
 */
function acomodar(clave: string, barras: BarraGuardada[]): Barra[][] {
  const orden = [...barras].sort((a, b) =>
    a.carril - b.carril || a.desde.localeCompare(b.desde) || a.id.localeCompare(b.id))
  const filas: Barra[][] = []
  for (const b of orden) {
    const v = vistaEn(clave, b, b.seccion === 'comercial' ? { piezas: b.piezas ?? [] } : {})
    let i = Math.max(0, b.carril)
    for (;;) {
      if (!filas[i]) filas[i] = []
      if (libre(filas[i], v.desde, v.hasta)) break
      i++
    }
    filas[i].push(v)
  }
  for (let i = 0; i < filas.length; i++) {
    filas[i] = (filas[i] ?? []).sort((a, b) => a.desde - b.desde)
  }
  return filas.length ? filas : [[]]
}

function bandasDe(clave: string, catalogo: BandaCatalogo[], barras: BarraGuardada[]): Banda[] {
  const porBanda = new Map<string, BarraGuardada[]>()
  for (const b of barras) {
    const lista = porBanda.get(b.banda)
    if (lista) lista.push(b)
    else porBanda.set(b.banda, [b])
  }
  // Una barra de una banda que no está en el catálogo igual se muestra: nunca
  // se esconde un dato porque el catálogo quedó corto.
  const nombres = [
    ...catalogo,
    ...[...porBanda.keys()].filter(n => !catalogo.some(c => c.nombre === n)).map(nombre => ({ nombre })),
  ]
  return nombres.map(c => ({
    id: c.nombre,
    nombre: c.nombre,
    grupo: (c as BandaCatalogo).grupo,
    filas: acomodar(clave, porBanda.get(c.nombre) ?? []),
  }))
}

/**
 * El mes `clave`, armado con las barras que lo tocan. `header` es lo que
 * devuelve derivarHeaders para las mismas barras: se pasa aparte porque se
 * calcula una vez para todos los meses.
 */
export function construirMes(
  clave: string,
  barras: BarraGuardada[],
  posicionesRM: Record<string, number[]> = {},
  header: HeaderDerivado = derivarHeaders(barras, posicionesRM),
): Mes {
  const ini = primerDiaDe(clave)
  const fin = ultimoDiaDe(clave)
  const toca = (desde: string, hasta: string) => desde <= fin && hasta >= ini
  const delMes = barras.filter(b => toca(b.desde, b.hasta))

  const posiciones: Banda[] = Array.from({ length: REGLAS_HEADER.tope }, (_, i) => ({
    id: idPosicion(i + 1),
    nombre: `Posición ${i + 1}`,
    filas: [
      header.tramos
        .filter(t => t.posicion === i + 1 && toca(t.desde, t.hasta))
        .sort((a, b) => a.desde.localeCompare(b.desde))
        .map(t => vistaEn(clave, t, { origen: t.origen })),
    ],
  }))

  const sinLugar: HeaderSinLugar[] = header.sinLugar
    .filter(s => toca(s.inicio, s.fin))
    .map(s => {
      const v = vistaEn(clave, { id: s.accionId, nombre: s.nombre, color: null, desde: s.inicio, hasta: s.fin })
      return { ...s, desde: v.desde, hasta: v.hasta }
    })

  return {
    clave,
    dias: diasDelMes(clave),
    dow: dowDelMes(clave),
    comercial: bandasDe(clave, BANDAS_COMERCIAL, delMes.filter(b => b.seccion === 'comercial')),
    retail: bandasDe(clave, BANDAS_RETAIL, delMes.filter(b => b.seccion === 'retail')),
    header: posiciones,
    posicionesRM: posicionesDe(posicionesRM, clave),
    sinLugar,
    envios: enviosQueSalen(clave, barras),
  }
}

/**
 * Los envíos que salen en el mes `clave`, mirando TODAS las acciones y no solo
 * las que tocan el mes: una acción del 5 al 10/10 con un recordatorio el 30/09
 * tiene que mostrar ese recordatorio en setiembre.
 */
function enviosQueSalen(clave: string, barras: BarraGuardada[]): Envio[] {
  const out: Envio[] = []
  for (const accion of barras) {
    if (accion.seccion !== 'comercial') continue
    for (const pieza of accion.piezas ?? []) {
      if (!esPiezaDeEnvio(pieza)) continue
      const fecha = fechaDeEnvio(pieza, accion.desde)
      if (claveDe(fecha) !== clave) continue
      out.push({
        id: `env-${pieza.id}`,
        accionId: accion.id,
        accion: accion.nombre,
        formato: pieza.formato,
        area: pieza.area,
        dia: diaDe(fecha),
        hora: pieza.hora,
        color: accion.color,
        heredaLaFecha: pieza.desde == null,
      })
    }
  }
  return out
}

/**
 * construirMes con memoria: mientras no cambien las barras ni las posiciones,
 * todas las pantallas reciben EL MISMO objeto. Sin esto, cada sección armaba
 * su propio mes y React no tenía cómo saber que no había cambiado nada.
 */
const memoria: {
  barras: Record<string, BarraGuardada> | null
  posiciones: Record<string, number[]> | null
  lista: BarraGuardada[]
  header: HeaderDerivado | null
  meses: Map<string, Mes>
} = { barras: null, posiciones: null, lista: [], header: null, meses: new Map() }

function alDia(barras: Record<string, BarraGuardada>, posicionesRM: Record<string, number[]>) {
  if (memoria.barras !== barras || memoria.posiciones !== posicionesRM) {
    memoria.barras = barras
    memoria.posiciones = posicionesRM
    memoria.lista = Object.values(barras)
    memoria.header = null
    memoria.meses = new Map()
  }
  memoria.header ??= derivarHeaders(memoria.lista, posicionesRM)
  return memoria.header
}

export function vistaDelMes(
  clave: string,
  barras: Record<string, BarraGuardada>,
  posicionesRM: Record<string, number[]>,
): Mes {
  const header = alDia(barras, posicionesRM)
  const hecho = memoria.meses.get(clave)
  if (hecho) return hecho
  const mes = construirMes(clave, memoria.lista, posicionesRM, header)
  memoria.meses.set(clave, mes)
  return mes
}

/** El header de todas las fechas, con la misma memoria que vistaDelMes. */
export function headerDerivado(
  barras: Record<string, BarraGuardada>,
  posicionesRM: Record<string, number[]>,
): HeaderDerivado {
  return alDia(barras, posicionesRM)
}

/** Todas las acciones del calendario comercial del mes, planas. */
export function accionesDe(mes: Mes): Barra[] {
  return mes.comercial.flatMap(b => b.filas.flat())
}

// ---------------------------------------------------------------------------
// Conteo de ocupación del header, día por día
// ---------------------------------------------------------------------------

export type EstadoDia = 'ok' | 'tolerable' | 'excedido'
export type OcupacionDia = { dia: number; cantidad: number; estado: EstadoDia }

export function ocupacionHeader(mes: Mes): OcupacionDia[] {
  return Array.from({ length: mes.dias }, (_, i) => {
    const dia = i + 1
    const cantidad = mes.header.reduce(
      (n, pos) => n + (pos.filas[0].some(b => b.desde <= dia && dia <= b.hasta) ? 1 : 0), 0)
    const estado: EstadoDia =
      cantidad > REGLAS_HEADER.tolerable ? 'excedido'
        : cantidad > REGLAS_HEADER.ideal ? 'tolerable'
          : 'ok'
    return { dia, cantidad, estado }
  })
}

// ---------------------------------------------------------------------------
// Cronograma de envios: mailing, WhatsApp y push
// ---------------------------------------------------------------------------

export type { Envio }

/** El día en que sale una pieza de envío: el suyo, o el que arranca su acción. */
export function fechaDeEnvio(pieza: Pieza, inicioAccion: string): string {
  return pieza.desde ?? inicioAccion
}

/**
 * El cronograma de envios del mes, un carril por canal.
 *
 * NO es una carga nueva: sale de las piezas que ya tiene cada accion en su
 * ficha (Email, WhatsApp, Push). Lo unico que agrega el cronograma es verlas
 * en el tiempo. Una pieza sin fecha propia cae el dia en que arranca su
 * accion, y se marca, para que se note que hay que ponerle la fecha.
 *
 * Un envío cae en el mes de SU fecha: una acción del 25/09 al 05/10 con un
 * mailing el 02/10 muestra el mailing en octubre, no en setiembre. Los arma
 * construirMes mirando todas las acciones (ver enviosQueSalen).
 */
export function enviosDelMes(mes: Mes): { area: string; titulo: string; envios: Envio[] }[] {
  const porArea = new Map<string, Envio[]>(CANALES_DE_ENVIO.map(c => [c.area, []]))
  for (const envio of mes.envios) porArea.get(envio.area)?.push(envio)

  return CANALES_DE_ENVIO.map(c => ({
    area: c.area,
    titulo: c.titulo,
    envios: (porArea.get(c.area) ?? []).sort(
      (a, b) => a.dia - b.dia || (a.hora ?? '').localeCompare(b.hora ?? '') || a.accion.localeCompare(b.accion)),
  }))
}

/** Los envios de un canal, repartidos en filas para que no se pisen dos el mismo dia. */
export function filasDeEnvios(envios: Envio[], clave = '2000-01'): Barra[][] {
  const filas: Barra[][] = []
  for (const e of envios) {
    const fecha = isoDe(clave, e.dia)
    const barra: Barra = {
      id: e.id,
      nombre: e.hora ? `${e.hora} ${e.accion}` : e.accion,
      desde: e.dia,
      hasta: e.dia,
      color: e.color,
      origen: { tipo: 'accion', accionId: e.accionId },
      inicio: fecha,
      fin: fecha,
      vieneDeAntes: false,
      sigueDespues: false,
    }
    const fila = filas.find(f => !f.some(b => b.desde === e.dia))
    if (fila) fila.push(barra)
    else filas.push([barra])
  }
  return filas.length ? filas : [[]]
}

// ---------------------------------------------------------------------------
// Que hay en el header un dia dado
// ---------------------------------------------------------------------------

/** Una posicion del header, mirada en una fecha concreta. */
export type PosicionEnFecha = {
  /** 1..10 */
  numero: number
  nombre: string
  /** true si esa posicion es de Retail Media */
  esRM: boolean
  /** La barra que la ocupa ese dia, si hay alguna. */
  barra: Barra | null
}

export function headerEnFecha(mes: Mes, dia: number): PosicionEnFecha[] {
  return mes.header.map((pos, i) => ({
    numero: i + 1,
    nombre: pos.nombre,
    esRM: mes.posicionesRM.includes(i + 1),
    barra: pos.filas[0].find(b => b.desde <= dia && dia <= b.hasta) ?? null,
  }))
}

