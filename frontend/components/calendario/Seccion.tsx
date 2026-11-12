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
    <section className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-card">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/40 px-4 py-3.5 sm:px-5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-slate-100 dark:text-slate-900">
          {icono}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">{titulo}</h2>
          <p className="hidden text-[13px] text-slate-500 dark:text-slate-400 sm:block">{bajada}</p>
        </div>
        {contador && (
          <span className="rounded-full bg-slate-100 dark:bg-slate-900 px-3 py-1 text-xs font-semibold text-slate-600 dark:text-slate-400">
            {contador}
          </span>
        )}
        {acciones}
      </header>
      {children}
    </section>
  )
}
