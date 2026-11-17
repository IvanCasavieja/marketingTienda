/**
 * Mi agenda: el calendario de cada persona (Outlook, Google) en una fila
 * arriba del calendario de Core Tienda. Pedido de Ivan (17/11/2026): "que la
 * gente pueda importar su propio calendario a la aplicación y que se vaya
 * actualizando con los eventos que vayan agregando". Solo la ve su dueño.
 *
 * El servidor lee el link y manda los eventos ya expandidos (las reuniones
 * que se repiten, una por vez). Ver backend/app/services/agenda_externa.py.
 * Acá: en qué día cae cada uno, en hora de Uruguay, y cómo se dice.
 */
import { isoDe, sumarDias } from './fechas'
import type { Barra } from './tipos'

export type EventoAgenda = {
  uid: string
  titulo: string
  /** Con hora: ISO en UTC ("2026-11-18T13:00:00Z"). Todo el día: 'YYYY-MM-DD'. */
  inicio: string
  /** Igual que `inicio`. En uno de todo el día, el día siguiente al último (como en el ICS). */
  fin: string
  todoElDia: boolean
  lugar: string | null
}

export type MiAgenda = {
  conectada: boolean
  /** Cuándo se leyó el link por última vez (ISO). */
  leidaEl: string | null
  /** Si la última lectura falló, por qué (se muestran los eventos de antes). */
  error: string | null
  eventos: EventoAgenda[]
}

/** Un color propio, tranquilo: que no se confunda con una acción. */
export const COLOR_AGENDA = '#c7d2fe'

const ZONA = 'America/Montevideo'
const FECHA = new Intl.DateTimeFormat('en-CA', { timeZone: ZONA, year: 'numeric', month: '2-digit', day: '2-digit' })
const HORA = new Intl.DateTimeFormat('es-UY', { timeZone: ZONA, hour: '2-digit', minute: '2-digit', hour12: false })

/** 'YYYY-MM-DD' de un momento, en Uruguay. */
function diaUruguay(iso: string): string {
  return FECHA.format(new Date(iso))
}

/** "10:00", en Uruguay. Vacío en uno de todo el día. */
export function horaDe(e: EventoAgenda): string {
  return e.todoElDia ? '' : HORA.format(new Date(e.inicio))
}

/** "10:00 a 10:30", "Todo el día" o "Hasta el 27/11" si sigue varios días. */
export function horarioDe(e: EventoAgenda): string {
  if (e.todoElDia) {
    const ultimo = sumarDias(e.fin, -1)
    if (ultimo <= e.inicio) return 'Todo el día'
    const [, m, d] = ultimo.split('-')
    return `Todo el día, hasta el ${Number(d)}/${Number(m)}`
  }
  const fin = HORA.format(new Date(e.fin))
  const inicio = horaDe(e)
  return fin === inicio ? inicio : `${inicio} a ${fin}`
}

/** Los días ('YYYY-MM-DD') que ocupa un evento. Uno con hora, el día en que
 *  empieza (una reunión que pasa la medianoche no se repite al otro día). */
function diasDe(e: EventoAgenda): string[] {
  if (!e.todoElDia) return [diaUruguay(e.inicio)]
  const dias: string[] = []
  const ultimo = sumarDias(e.fin, -1)
  for (let d = e.inicio; d <= ultimo && dias.length < 62; d = sumarDias(d, 1)) dias.push(d)
  return dias.length ? dias : [e.inicio]
}

/** Primero los de todo el día y después por hora. */
function orden(a: EventoAgenda, b: EventoAgenda): number {
  if (a.todoElDia !== b.todoElDia) return a.todoElDia ? -1 : 1
  return a.inicio < b.inicio ? -1 : a.inicio > b.inicio ? 1 : a.titulo.localeCompare(b.titulo)
}

/** Los eventos de cada día del mes `clave` ('YYYY-MM'), ya ordenados. Puro. */
export function eventosPorDia(eventos: EventoAgenda[], clave: string, dias: number): Map<number, EventoAgenda[]> {
  const primero = isoDe(clave, 1)
  const ultimo = isoDe(clave, dias)
  const porDia = new Map<number, EventoAgenda[]>()
  for (const e of eventos) {
    for (const d of diasDe(e)) {
      if (d < primero || d > ultimo) continue
      const n = Number(d.slice(8, 10))
      const lista = porDia.get(n) ?? []
      lista.push(e)
      porDia.set(n, lista)
    }
  }
  porDia.forEach(lista => lista.sort(orden))
  return porDia
}

/** Lo que dice la barra de un día: "10:00 Daily +2". Puro. */
export function nombreDelDia(lista: EventoAgenda[]): string {
  const [primero] = lista
  if (!primero) return ''
  const hora = horaDe(primero)
  const resto = lista.length > 1 ? ` +${lista.length - 1}` : ''
  return `${hora ? hora + ' ' : ''}${primero.titulo}${resto}`
}

/** El tooltip de la barra: un evento por renglón. Puro. */
export function tituloDelDia(lista: EventoAgenda[]): string {
  return lista.map(e => `${horarioDe(e)} · ${e.titulo}${e.lugar ? ` (${e.lugar})` : ''}`).join('\n')
}

/** Desde cuántos px por día entra "10:00 Daily": más angosto, la barra dice
 *  solo cuántos eventos hay (con el zoom chico decía "1."). */
export const ANCHO_PARA_EL_NOMBRE = 100

/** Una barra de un día por cada día con eventos, para la rejilla. `corta`: en
 *  vez del nombre, cuántos hay (el detalle, en el tooltip y al tocarla). Puro. */
export function barrasDeAgenda(porDia: Map<number, EventoAgenda[]>, clave: string, corta = false): Barra[] {
  return [...porDia.keys()].sort((a, b) => a - b).map(dia => {
    const iso = isoDe(clave, dia)
    const lista = porDia.get(dia)!
    return {
      id: `agenda-${iso}`, nombre: corta ? String(lista.length) : nombreDelDia(lista), desde: dia, hasta: dia, color: COLOR_AGENDA,
      inicio: iso, fin: iso, vieneDeAntes: false, sigueDespues: false,
    }
  })
}

/** "hace 5 minutos", "a las 10:32" o "el 16/11". */
export function cuandoSeLeyo(leidaEl: string | null, ahora: Date = new Date()): string {
  if (!leidaEl) return ''
  const minutos = Math.round((ahora.getTime() - new Date(leidaEl).getTime()) / 60000)
  if (minutos < 1) return 'recién'
  if (minutos < 60) return minutos === 1 ? 'hace 1 minuto' : `hace ${minutos} minutos`
  if (diaUruguay(leidaEl) === diaUruguay(ahora.toISOString())) return `a las ${HORA.format(new Date(leidaEl))}`
  const [, m, d] = diaUruguay(leidaEl).split('-')
  return `el ${Number(d)}/${Number(m)}`
}

/** Si lo que pegaron parece un link de calendario (lo de verdad lo decide el servidor). */
export function pareceLinkDeCalendario(texto: string): boolean {
  return /^(https|webcal):\/\/[^\s/]+\.[^\s]+$/i.test(texto.trim())
}
