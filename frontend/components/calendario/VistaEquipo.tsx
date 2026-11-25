'use client'

/**
 * La vista "Equipo": cuántas tareas abiertas tiene cada persona por semana,
 * para repartir sin desbordar a nadie (idea aprobada por Ivan, 15/11/2026).
 * La ven quienes reparten tareas (permiso calendario.tareas).
 */
import { useMemo, useState } from 'react'
import { ChevronDown, Users } from 'lucide-react'
import { CARGA_ALTA, CARGA_EXCESIVA, cargaDelEquipo, nivelDeCarga, type FilaDeCarga } from '@/lib/calendario/carga'
import { fechaCorta, hoyIso } from '@/lib/calendario/fechas'
import { useCalendario } from '@/lib/calendario/store'
import { mundoDe } from '@/lib/mundos'

const COLOR_CELDA: Record<ReturnType<typeof nivelDeCarga>, string> = {
  nada: 'bg-slate-50 text-slate-500 dark:bg-slate-800/50 dark:text-slate-400',
  normal: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-200',
  alta: 'bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-100',
  excesiva: 'bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-100',
}

export function VistaEquipo() {
  const barras = useCalendario(s => s.barras)
  const personas = useCalendario(s => s.personas)
  const mundo = useCalendario(s => s.mundo)
  const hoy = hoyIso()
  const { semanas, filas } = useMemo(() => cargaDelEquipo(Object.values(barras), hoy), [barras, hoy])
  const nombreDe = (id: number) => personas.find(p => p.id === id)?.nombre ?? `Persona ${id}`

  return (
    <section className="rounded-2xl border border-slate-300 bg-white p-4 shadow-card dark:border-slate-700 dark:bg-slate-900 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200">
          <Users className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-bold leading-tight text-slate-900 dark:text-slate-100">Carga del equipo</h2>
          <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
            Tareas abiertas de cada persona en {mundoDe(mundo)?.nombre ?? 'este mundo'}, por semana.
            Amarillo desde {CARGA_ALTA} en una semana, rojo desde {CARGA_EXCESIVA}.
          </p>
        </div>
      </div>

      {filas.length === 0 ? (
        <p className="mt-6 rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          Nadie tiene tareas abiertas en este mundo.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {filas.map(f => (
            <Persona key={f.personaId} fila={f} nombre={nombreDe(f.personaId)} semanas={semanas} />
          ))}
        </ul>
      )}
    </section>
  )
}

function Persona({ fila, nombre, semanas }: { fila: FilaDeCarga; nombre: string; semanas: { desde: string; hasta: string }[] }) {
  const [abierta, setAbierta] = useState(false)
  const abrirAccion = useCalendario(s => s.abrirAccion)
  const iniciales = nombre.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]?.toUpperCase()).join('')
  const celdas = [
    { titulo: 'Vencidas', corto: 'Vencidas', n: fila.vencidas, nivel: fila.vencidas > 0 ? 'excesiva' as const : 'nada' as const },
    ...semanas.map((s, i) => ({
      titulo: i === 0 ? 'Esta semana' : `Semana del ${fechaCorta(s.desde)}`,
      corto: i === 0 ? 'Esta sem.' : fechaCorta(s.desde),
      n: fila.porSemana[i], nivel: nivelDeCarga(fila.porSemana[i]),
    })),
    { titulo: 'Más adelante', corto: 'Después', n: fila.masAdelante, nivel: fila.masAdelante > 0 ? 'normal' as const : 'nada' as const },
    { titulo: 'Sin fecha', corto: 'Sin fecha', n: fila.sinFecha, nivel: fila.sinFecha > 0 ? 'normal' as const : 'nada' as const },
  ]

  return (
    <li className="rounded-xl border border-slate-300 p-3 dark:border-slate-700 sm:p-4">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
          {iniciales || '?'}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-slate-900 dark:text-slate-100">{nombre}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {fila.total === 1 ? '1 tarea abierta' : `${fila.total} tareas abiertas`}
            {fila.vencidas > 0 && <span className="font-semibold text-red-600 dark:text-red-300"> · {fila.vencidas === 1 ? '1 vencida' : `${fila.vencidas} vencidas`}</span>}
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-1.5 sm:grid-cols-7">
        {celdas.map(c => (
          <div key={c.titulo} className={`rounded-lg px-2 py-1.5 text-center ${COLOR_CELDA[c.nivel]}`} title={`${c.titulo}: ${c.n}`}>
            {/* En el teléfono el título largo no entra: va el corto ("16/11"). */}
            <p className="truncate text-[10px] font-medium uppercase tracking-wide opacity-80">
              <span className="sm:hidden">{c.corto}</span>
              <span className="hidden sm:inline">{c.titulo}</span>
            </p>
            <p className="text-lg font-bold tabular-nums leading-tight">{c.n}</p>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setAbierta(a => !a)}
        aria-expanded={abierta}
        className="mt-2 flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
      >
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${abierta ? 'rotate-180' : ''}`} />
        {abierta ? 'Ocultar tareas' : 'Ver tareas'}
      </button>
      {abierta && (
        <ul className="mt-2 divide-y divide-slate-200 text-sm dark:divide-slate-700">
          {fila.tareas.map(t => (
            <li key={t.id} className="flex items-baseline gap-2 py-1.5">
              <span className="w-12 shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">{t.vence ? fechaCorta(t.vence) : '—'}</span>
              <span className="min-w-0 flex-1 truncate text-slate-800 dark:text-slate-200">
                {t.titulo}
                {t.laHace && <span className="text-slate-500 dark:text-slate-400"> · la hace {t.laHace}</span>}
              </span>
              <button type="button" onClick={() => abrirAccion(t.accionId)} className="max-w-[40%] shrink-0 truncate text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300">
                {t.accion}
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
