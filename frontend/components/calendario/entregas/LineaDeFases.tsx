'use client'

import { Check } from 'lucide-react'
import { estadoDeFase, type ResumenEntrega } from '@/lib/calendario/entregas'

const CIRCULO = {
  hecha: 'bg-emerald-500 text-white',
  actual: 'bg-brand-600 text-white ring-4 ring-brand-100 dark:ring-brand-500/25',
  cambios: 'bg-rose-500 text-white ring-4 ring-rose-100 dark:ring-rose-500/25',
  pendiente: 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
} as const

const TEXTO = {
  hecha: 'text-emerald-700 dark:text-emerald-300',
  actual: 'text-brand-700 dark:text-brand-200',
  cambios: 'text-rose-700 dark:text-rose-300',
  pendiente: 'text-slate-500 dark:text-slate-400',
} as const

/**
 * La línea de fases: "Boceto ✓ en 2 rondas → Arte final en revisión, ronda 1
 * → Adaptaciones pendiente". Una mirada alcanza para saber dónde está la
 * pieza. Con muchas fases se desplaza de costado (en el teléfono entran tres).
 */
export function LineaDeFases({ resumen }: { resumen: ResumenEntrega }) {
  return (
    <ol className="flex gap-0 overflow-x-auto pb-1" aria-label="Fases de la entrega">
      {resumen.fases.map((f, i) => {
        const { texto, tono } = estadoDeFase(f, resumen)
        const ultima = i === resumen.fases.length - 1
        return (
          <li key={f.id} className="relative flex min-w-[6.5rem] flex-1 flex-col items-center px-1 text-center" aria-current={tono === 'actual' || tono === 'cambios' ? 'step' : undefined}>
            {!ultima && (
              <span
                aria-hidden
                className={`absolute left-1/2 top-4 h-0.5 w-full ${f.estado === 'aprobada' ? 'bg-emerald-400' : 'bg-slate-200 dark:bg-slate-700'}`}
              />
            )}
            <span className={`relative z-[1] flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${CIRCULO[tono]}`}>
              {tono === 'hecha' ? <Check className="h-4 w-4" strokeWidth={3} /> : i + 1}
            </span>
            <span className="mt-1.5 max-w-full truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{f.nombre}</span>
            <span className={`text-xs font-medium leading-tight ${TEXTO[tono]}`}>{texto}</span>
          </li>
        )
      })}
    </ol>
  )
}

/** La versión chica, para la tarea en la ficha y las tarjetas: una barrita
 *  por fase, del color de cómo está. */
export function FasesCompactas({ resumen }: { resumen: ResumenEntrega }) {
  return (
    <span className="flex items-center gap-1" aria-hidden>
      {resumen.fases.map(f => {
        const { tono } = estadoDeFase(f, resumen)
        return (
          <span
            key={f.id}
            className={`h-1.5 w-6 rounded-full ${
              tono === 'hecha' ? 'bg-emerald-500' : tono === 'actual' ? 'bg-brand-500' : tono === 'cambios' ? 'bg-rose-500' : 'bg-slate-200 dark:bg-slate-700'
            }`}
          />
        )
      })}
    </span>
  )
}

/** "Fase 2 de 3 · Arte final" */
export function faseActualTexto(resumen: ResumenEntrega): string {
  const i = resumen.fases.findIndex(f => f.id === resumen.faseActual)
  if (i === -1) return `${resumen.fases.length === 1 ? '1 fase' : `${resumen.fases.length} fases`} aprobadas`
  return `Fase ${i + 1} de ${resumen.fases.length} · ${resumen.fases[i].nombre}`
}
