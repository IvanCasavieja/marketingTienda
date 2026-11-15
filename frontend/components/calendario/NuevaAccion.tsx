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
      className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 sm:w-auto"
    >
      <Plus className="h-4 w-4" /> Nueva acción
    </button>
  )
}
