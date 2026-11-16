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
    <section className="overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-card dark:border-slate-700 dark:bg-slate-900">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2.5 border-b border-slate-300 px-4 py-3 dark:border-slate-700 sm:px-5 sm:py-3.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/20">
          {icono}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 text-base font-bold text-slate-900 dark:text-slate-100">
            {titulo}
            {contador && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {contador}
              </span>
            )}
          </h2>
          <p className="hidden max-w-3xl text-[13px] leading-snug text-slate-500 dark:text-slate-400 sm:block">{bajada}</p>
        </div>
        {acciones}
      </header>
      {children}
    </section>
  )
}
