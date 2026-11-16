'use client'
// ---------------------------------------------------------------------------
// Lo de la foto de colocación que comparten varias partes de la pantalla.
//
// - Qué locales tiene cada mundo: lo usan el menú (para mostrar "Colocación")
//   y la ficha de una acción (para mostrar la pestaña Fotos). Se pregunta una
//   vez por mundo: en un mundo sin locales con usuario (Tienda Inglesa, hoy)
//   no aparece nada, y cuando los den de alta aparece solo.
// - Cuántas fotos le quedan por subir al local que entró: el número del menú
//   y de la barra de abajo del teléfono. Lo actualiza la pantalla "Fotos para
//   subir" cada vez que sube o saca una.
// ---------------------------------------------------------------------------

import { create } from 'zustand'
import { colocacionApi } from '../api'
import { pendientesDelLocal } from './estados'

type EstadoLocales = {
  /** mundo → los locales a los que se les puede pedir. Sin clave: todavía no se preguntó. */
  porMundo: Record<string, string[]>
  pidiendo: Record<string, boolean>
  pedir: (mundo: string) => void
}

export const useLocalesDelMundo = create<EstadoLocales>((set, get) => ({
  porMundo: {},
  pidiendo: {},
  pedir: mundo => {
    if (get().porMundo[mundo] || get().pidiendo[mundo]) return
    set(s => ({ pidiendo: { ...s.pidiendo, [mundo]: true } }))
    colocacionApi.disponibles(mundo)
      .then(({ data }) => set(s => ({ porMundo: { ...s.porMundo, [mundo]: data.locales } })))
      // Sin respuesta (o sin permiso) no se muestra nada: se vuelve a probar la próxima vez.
      .catch(() => {})
      .finally(() => set(s => ({ pidiendo: { ...s.pidiendo, [mundo]: false } })))
  },
}))

type EstadoPendientes = {
  /** null = todavía no se sabe. */
  pendientes: number | null
  poner: (n: number) => void
  contar: () => Promise<void>
}

export const usePendientesDeFotos = create<EstadoPendientes>(set => ({
  pendientes: null,
  poner: n => set({ pendientes: n }),
  contar: async () => {
    try {
      const { data } = await colocacionApi.misFotos()
      set({ pendientes: pendientesDelLocal(data.pedidos) })
    } catch {
      // Sin conexión el número queda como estaba.
    }
  },
}))
