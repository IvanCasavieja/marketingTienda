// ---------------------------------------------------------------------------
// Lógica de dominio pura: construir un mes, bajar lo que corresponde al
// calendario de headers y contar la ocupación. Sin React ni zustand a propósito
// — es lo único que hay que portar en serio a MKTG Platform, y así se puede
// testear sin levantar nada.
// ---------------------------------------------------------------------------

import { SEED } from './seed'
import { colorPorDefecto } from './colores'
import { diasDelMes, dowDelMes } from './fechas'
import {
  CANALES_DE_ENVIO, REGLAS_HEADER, esPiezaDeEnvio, esPiezaHeader,
  type Banda, type Barra, type HeaderSinLugar, type Mes,
  type OrigenHeader, type Pieza, type SeedBanda,
} from './tipos'

let seq = 0
export const nuevoId = (p: string) => `${p}-${Date.now().toString(36)}-${(seq++).toString(36)}`

export function bandasDesdeSeed(seed: SeedBanda[]): Banda[] {
  return seed.map(b => ({
    id: nuevoId('bnd'),
    nombre: b.nombre,
    grupo: b.grupo,
    filas: b.filas.map(fila =>
      fila.map(x => ({
        id: nuevoId('br'),
        nombre: x.nombre,
        desde: x.desde,
        hasta: x.hasta,
        color: x.color ?? colorPorDefecto(x.nombre),
        piezas: [] as Pieza[],
      })),
    ),
  }))
}

export function headerVacio(): Banda[] {
  return Array.from({ length: REGLAS_HEADER.tope }, (_, i) => ({
    id: `pos-${i + 1}`,
    nombre: `Posición ${i + 1}`,
    filas: [[]] as Barra[][],
  }))
}

export function construirMes(clave: string): Mes {
  const seed = SEED[clave]
  return derivarHeader({
    clave,
    dias: seed?.dias ?? diasDelMes(clave),
    dow: seed?.dow ?? dowDelMes(clave),
    comercial: seed ? bandasDesdeSeed(seed.comercial) : [],
    retail: seed ? bandasDesdeSeed(seed.retail) : [],
    header: headerVacio(),
    posicionesRM: [...REGLAS_HEADER.rmPorDefecto],
    sinLugar: [],
  })
}

/** Todas las acciones del calendario comercial, planas. */
export function accionesDe(mes: Mes): Barra[] {
  return mes.comercial.flatMap(b => b.filas.flat())
}

function libre(fila: Barra[], desde: number, hasta: number): boolean {
  return !fila.some(b => b.desde <= hasta && desde <= b.hasta)
}

/**
 * Baja al calendario de headers todo lo que le corresponde:
 *
 *  - Retail Media: las filas del formato HOME SLIDER caen en las posiciones
 *    que RM tenga reservadas (por defecto 4, 5 y 6), en orden.
 *  - Marketing: cada acción que en su estructura web tenga una pieza `Header`
 *    de home baja a la primera posición de marketing libre en todo su rango.
 *
 * Lo que no entra no se descarta ni le saca el lugar a nadie: se junta en
 * `sinLugar` para que el sistema avise. Qué se baja lo decide una persona
 * mirando la venta, no esto.
 */
export function derivarHeader(mes: Mes): Mes {
  // Arranca de cero, conservando solo lo cargado a mano
  const header = mes.header.map(pos => ({
    ...pos,
    filas: [pos.filas[0].filter(b => b.origen?.tipo === 'manual' || !b.origen)] as Barra[][],
  }))

  // --- Retail Media ---
  const banda = mes.retail.find(b => b.nombre === REGLAS_HEADER.formatoHeader)
  if (banda) {
    banda.filas.forEach((fila, idx) => {
      const posNum = mes.posicionesRM[idx]
      const destino = posNum ? header[posNum - 1] : undefined
      if (!destino) return
      const origen: OrigenHeader = { tipo: 'retail', bandaId: banda.id, filaIdx: idx }
      destino.filas[0] = [
        ...destino.filas[0],
        ...fila.map(b => ({ ...b, id: `rm-${b.id}`, origen })),
      ].sort((a, b) => a.desde - b.desde)
    })
  }

  // --- Acciones de marketing ---
  const posicionesMkt = header.map((_, i) => i + 1).filter(n => !mes.posicionesRM.includes(n))
  const sinLugar: HeaderSinLugar[] = []

  const pedidos = accionesDe(mes)
    .flatMap(accion =>
      (accion.piezas ?? [])
        .filter(esPiezaHeader)
        .map(p => ({
          accion,
          desde: p.desde ?? accion.desde,
          hasta: p.hasta ?? accion.hasta,
        })),
    )
    .sort((a, b) => a.desde - b.desde || a.accion.nombre.localeCompare(b.accion.nombre))

  for (const pedido of pedidos) {
    const pos = posicionesMkt.find(n => libre(header[n - 1].filas[0], pedido.desde, pedido.hasta))
    if (pos) {
      const barra: Barra = {
        id: `ac-${pedido.accion.id}`,
        nombre: pedido.accion.nombre,
        desde: pedido.desde,
        hasta: pedido.hasta,
        color: pedido.accion.color,
        origen: { tipo: 'accion', accionId: pedido.accion.id },
      }
      header[pos - 1].filas[0] = [...header[pos - 1].filas[0], barra].sort((a, b) => a.desde - b.desde)
    } else {
      const diasLlenos: number[] = []
      for (let d = pedido.desde; d <= pedido.hasta; d++) {
        const ocupadas = header.filter(p => p.filas[0].some(b => b.desde <= d && d <= b.hasta)).length
        if (ocupadas >= REGLAS_HEADER.tope) diasLlenos.push(d)
      }
      sinLugar.push({
        accionId: pedido.accion.id,
        nombre: pedido.accion.nombre,
        desde: pedido.desde,
        hasta: pedido.hasta,
        diasLlenos,
      })
    }
  }

  return { ...mes, header, sinLugar }
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

/** Un envio, ya ubicado en su dia. */
export type Envio = {
  /** id de la barra que se dibuja */
  id: string
  accionId: string
  accion: string
  /** "Mailing digital", "Recordatorio", "Envio masivo", "Push app" */
  formato: string
  dia: number
  /** 'HH:MM' si la pieza la tiene cargada */
  hora?: string
  color: string | null
  /** true si la pieza no trae fecha propia y toma el arranque de la accion */
  heredaLaFecha: boolean
}

/**
 * El cronograma de envios del mes, un carril por canal.
 *
 * NO es una carga nueva: sale de las piezas que ya tiene cada accion en su
 * ficha (Email, WhatsApp, Push). Lo unico que agrega el cronograma es verlas
 * en el tiempo. Una pieza sin fecha propia cae el dia en que arranca su
 * accion, y se marca, para que se note que hay que ponerle la fecha.
 */
export function enviosDelMes(mes: Mes): { area: string; titulo: string; envios: Envio[] }[] {
  const porArea = new Map<string, Envio[]>(CANALES_DE_ENVIO.map(c => [c.area, []]))

  for (const accion of accionesDe(mes)) {
    for (const pieza of accion.piezas ?? []) {
      if (!esPiezaDeEnvio(pieza)) continue
      const carril = porArea.get(pieza.area)
      if (!carril) continue
      const heredaLaFecha = pieza.desde == null
      const dia = Math.min(Math.max(pieza.desde ?? accion.desde, 1), mes.dias)
      carril.push({
        id: `env-${pieza.id}`,
        accionId: accion.id,
        accion: accion.nombre,
        formato: pieza.formato,
        dia,
        hora: pieza.hora,
        color: accion.color,
        heredaLaFecha,
      })
    }
  }

  return CANALES_DE_ENVIO.map(c => ({
    area: c.area,
    titulo: c.titulo,
    envios: (porArea.get(c.area) ?? []).sort(
      (a, b) => a.dia - b.dia || (a.hora ?? '').localeCompare(b.hora ?? '') || a.accion.localeCompare(b.accion)),
  }))
}

/** Los envios de un canal, repartidos en filas para que no se pisen dos el mismo dia. */
export function filasDeEnvios(envios: Envio[]): Barra[][] {
  const filas: Barra[][] = []
  for (const e of envios) {
    const barra: Barra = {
      id: e.id,
      nombre: e.hora ? `${e.hora} ${e.accion}` : e.accion,
      desde: e.dia,
      hasta: e.dia,
      color: e.color,
      origen: { tipo: 'accion', accionId: e.accionId },
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
