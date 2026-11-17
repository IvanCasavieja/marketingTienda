'use client'
// ---------------------------------------------------------------------------
// Si el menú del costado está oculto, en pantallas grandes.
//
// Pedido de Ivan (17/11/2026): "me gustaría que el menú del costado tenga un
// botón para ocultarse y que también tengamos el botón para mostrarlo, así
// cuando no lo precisamos no tenerlo ahí". Es una comodidad de cada persona
// en su navegador, como el mundo elegido: se guarda en localStorage. En el
// teléfono el menú ya es una hoja que se abre y se cierra, y esto no lo toca.
// ---------------------------------------------------------------------------

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type EstadoMenuLateral = {
  oculto: boolean
  ocultar: () => void
  mostrar: () => void
}

export const useMenuLateral = create<EstadoMenuLateral>()(
  persist(
    set => ({
      oculto: false,
      ocultar: () => set({ oculto: true }),
      mostrar: () => set({ oculto: false }),
    }),
    { name: 'core-menu-lateral', storage: createJSONStorage(() => localStorage) },
  ),
)
