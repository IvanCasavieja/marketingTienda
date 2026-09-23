'use client'

import type { ReactNode } from 'react'

export function Seccion({
  icono, titulo, bajada, contador, acciones, children,
}: {
  icono: ReactNode
  titulo: string
  bajada: string
  contador?: string
  acciones?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-800/40 px-4 py-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900">
          {icono}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{titulo}</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">{bajada}</p>
        </div>
        {contador && (
          <span className="rounded-full bg-white dark:bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-slate-500 dark:text-slate-400 ring-1 ring-slate-200 dark:ring-slate-700">
            {contador}
          </span>
        )}
        {acciones}
      </header>
      {children}
    </section>
  )
}
