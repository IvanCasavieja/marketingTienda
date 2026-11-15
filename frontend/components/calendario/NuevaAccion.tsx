'use client'

import { Plus } from 'lucide-react'
import { SIN_CATEGORIA } from '@/lib/calendario/categorias'
import { useCalendario } from '@/lib/calendario/store'

/**
 * Crear una acción: "nueva acción y punto" (pedido de Ivan, 12/11/2026). No se
 * pregunta de qué tipo es antes de crearla: nace sin categoría, se abre su
 * ficha y la categoría se le pone después, adentro. Está en la lista y en el
 * calendario, para que crear sea lo mismo en las dos vistas.
 */
export function NuevaAccion({ diaInicial }: { diaInicial: string }) {
  const abrirEditor = useCalendario(s => s.abrirEditor)
  return (
    <button
      type="button"
      onClick={() => abrirEditor({ seccion: 'comercial', banda: SIN_CATEGORIA, carril: 0, barra: null, fechaInicial: diaInicial })}
      className="group flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm shadow-brand-600/25 transition hover:bg-brand-700 hover:shadow-md hover:shadow-brand-600/25 active:scale-[.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 sm:min-h-[40px] sm:w-auto"
    >
      <Plus className="h-4 w-4 transition-transform duration-200 group-hover:rotate-90" /> Nueva acción
    </button>
  )
}
