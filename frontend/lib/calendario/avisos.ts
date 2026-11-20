/**
 * Un aviso contado desde la fecha de un envío (Ivan, 20/11/2026: "que un aviso
 * se pueda programar según la fecha de un envío, no solo según el arranque de
 * la acción"). Lo mismo calcula el servidor (fecha_base en
 * backend/app/services/calendario_avisos.py).
 */
import { esPiezaDeEnvio, tituloDeCanal, type Aviso, type BarraGuardada, type Pieza } from './tipos'

/** Los envíos de la acción (email, WhatsApp, push), por fecha. Pura. */
export function enviosDe(accion: Pick<BarraGuardada, 'desde' | 'piezas'>): Pieza[] {
  return (accion.piezas ?? [])
    .filter(esPiezaDeEnvio)
    .sort((a, b) => (a.desde ?? accion.desde).localeCompare(b.desde ?? accion.desde) || a.id.localeCompare(b.id))
}

/** Desde qué fecha se cuentan los días: la del envío, o el inicio de la
 *  acción (también si al envío le sacaron la fecha: sale con la acción). Pura. */
export function fechaBase(accion: Pick<BarraGuardada, 'desde' | 'piezas'>, piezaId: string | null | undefined): string {
  if (!piezaId) return accion.desde
  return (accion.piezas ?? []).find(p => p.id === piezaId)?.desde ?? accion.desde
}

/** "Email · Mailing digital". Pura. */
export function nombreDeEnvio(p: Pieza): string {
  return `${tituloDeCanal(p.area)} · ${p.formato}`
}

/** De qué se cuenta un aviso, para leerlo en la lista. Pura. */
export function desdeQue(accion: Pick<BarraGuardada, 'piezas'>, aviso: Pick<Aviso, 'piezaId'>, esEnvioSuelto: boolean): string {
  const pieza = aviso.piezaId ? (accion.piezas ?? []).find(p => p.id === aviso.piezaId) : undefined
  if (pieza) return `antes del envío ${nombreDeEnvio(pieza)}`
  return esEnvioSuelto ? 'antes de que salga' : 'antes de que arranque'
}
