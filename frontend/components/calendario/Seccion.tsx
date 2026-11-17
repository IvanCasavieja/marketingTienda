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
    // overflow-clip y no overflow-hidden: recorta las esquinas igual, pero no
    // es un contenedor de scroll, así la fila de los días (sticky) se queda
    // arriba al bajar la página (ver MarcoScroll).
    <section className="overflow-clip rounded-2xl border border-slate-300 bg-white shadow-card dark:border-slate-700 dark:bg-slate-900">
      {/* Compacto (pedido del 16/11/2026, "aprovechar más el espacio"): el
          título y su explicación van en una sola línea cuando hay lugar, y la
          explicación se corta con puntos (entera, al pasar el mouse). */}
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-slate-300 px-4 py-2 dark:border-slate-700 sm:px-5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-inset ring-brand-100 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/20">
          {icono}
        </span>
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3">
          <h2 className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 text-base font-bold text-slate-900 dark:text-slate-100">
            {titulo}
            {contador && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {contador}
              </span>
            )}
          </h2>
          <p title={bajada} className="hidden min-w-0 flex-1 basis-72 truncate text-[13px] leading-snug text-slate-500 dark:text-slate-400 sm:block">{bajada}</p>
        </div>
        {acciones}
      </header>
      {children}
    </section>
  )
}
