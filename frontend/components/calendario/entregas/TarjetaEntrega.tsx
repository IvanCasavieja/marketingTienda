'use client'

import { CalendarClock, FileImage, UserRound } from 'lucide-react'
import { proximoPaso, tipoDePieza, type Tarjeta } from '@/lib/calendario/entregas'
import { fechaCorta } from '@/lib/calendario/fechas'
import { useVistaEntregas } from '@/store/entregas'
import { FasesCompactas, faseActualTexto } from './LineaDeFases'
import { Miniatura } from './ImagenConMarcas'

/**
 * Una tarjeta del tablero (y de "Mis tareas"): qué pieza es, de qué acción,
 * en qué fase y ronda va y —lo importante— a quién le toca. Tocarla abre la
 * tarea con sus entregas.
 */
export function TarjetaEntrega({ tarjeta, usuarioId, hoy, orden = 0 }: {
  tarjeta: Tarjeta
  usuarioId: number | null
  hoy: string
  orden?: number
}) {
  const abrir = useVistaEntregas(s => s.abrir)
  const r = tarjeta.entrega
  const nombreDe = (id: number | null) => (id != null && id === r.aprobadorDeTurno ? tarjeta.turno : tarjeta.responsable) ?? 'alguien'
  const paso = proximoPaso(r, tarjeta.asignadoA, usuarioId, nombreDe)
  const vencida = tarjeta.vence && tarjeta.vence < hoy && r.momento !== 'aprobada'
  const meToca = paso.aQuien === 'vos'

  return (
    <li style={{ animationDelay: `${Math.min(orden, 8) * 30}ms` }} className="animate-rise">
      <button
        type="button"
        onClick={() => abrir(tarjeta.tareaId, paso.accion === 'revisar' ? 'revisar' : paso.accion === 'entregar' ? 'entregar' : 'ver')}
        className={`group flex w-full flex-col gap-2.5 rounded-2xl border bg-white p-3 text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-card-hover active:scale-[.99] dark:bg-slate-900 ${
          meToca ? 'border-brand-300 ring-1 ring-brand-200 dark:border-brand-500/50 dark:ring-brand-500/20' : 'border-slate-200 dark:border-slate-800'
        }`}
      >
        <div className="flex items-start gap-3">
          {tarjeta.miniatura ? (
            <Miniatura imagenId={tarjeta.miniatura} etiqueta={`La última versión de ${tarjeta.titulo}`} className="h-14 w-14" />
          ) : (
            <span className="flex h-14 w-14 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
              <FileImage className="h-5 w-5" />
              <span className="text-[9px] font-bold uppercase">{tipoDePieza(r.tipoPieza).nombre}</span>
            </span>
          )}
          <span className="min-w-0 flex-1">
            <span className="line-clamp-2 text-[15px] font-semibold leading-snug text-slate-900 dark:text-slate-100">{tarjeta.titulo}</span>
            <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <span className="h-2 w-2 shrink-0 rounded-sm ring-1 ring-inset ring-black/10" style={{ backgroundColor: tarjeta.accion.color ?? '#cbd5e1' }} />
              <span className="truncate">{tarjeta.accion.nombre}</span>
            </span>
          </span>
        </div>

        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <FasesCompactas resumen={r} />
          <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{faseActualTexto(r)}</span>
        </span>

        <span className={`rounded-lg px-2 py-1.5 text-xs font-semibold leading-snug ${
          meToca ? 'bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-brand-100' : 'bg-slate-50 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300'
        }`}>
          {paso.texto}
        </span>

        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          <span className="flex min-w-0 items-center gap-1"><UserRound className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{tarjeta.responsable ?? 'Sin responsable'}</span></span>
          {tarjeta.vence && (
            <span className={`flex items-center gap-1 ${vencida ? 'font-semibold text-rose-600 dark:text-rose-300' : ''}`}>
              <CalendarClock className="h-3.5 w-3.5" /> {vencida ? 'Venció' : 'Vence'} {fechaCorta(tarjeta.vence)}
            </span>
          )}
        </span>
      </button>
    </li>
  )
}
