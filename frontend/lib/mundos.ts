'use client'
// ---------------------------------------------------------------------------
// Los mundos: cada negocio con su propio calendario.
//
// Pedido de Ivan (12/11/2026): "que sean dos mundos. Una persona cuando vaya a
// entrar, que pueda elegir... Una persona que tenga acceso a un solo mundo no
// va a pasar por esa selección, sino que va directamente al único que tiene".
//
// Las claves son las mismas que en backend/app/core/mundos.py: si se agrega un
// mundo, va en los dos lados. Qué mundos abre cada persona lo dice el servidor
// (`user.mundos`); acá está solo cómo se llama y cómo se ve cada uno.
// ---------------------------------------------------------------------------

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { CurrentUser } from '@/types'

/** El nombre de la plataforma. Está en un solo lugar para poder cambiarlo. */
export const MARCA = 'Core Tienda'
export const MARCA_BAJADA = 'Calendario y tareas'

export type SeccionDeMundo = 'comercial' | 'envios' | 'retail' | 'header'

export type Mundo = {
  clave: string
  nombre: string
  bajada: string
  /** El color con el que se reconoce: el borde de su tarjeta y su punto. */
  color: string
  /** Qué partes del calendario tiene. El header de la home y Retail Media son
   *  de la web de Tienda Inglesa; los demás no los tienen. */
  secciones: SeccionDeMundo[]
  /** Los tipos de acción con los que arranca. null = los del Excel de Tienda
   *  Inglesa (lib/calendario/catalogo.ts). Un tipo que no está acá igual se
   *  muestra si tiene alguna acción cargada. */
  bandas: string[] | null
}

const BANDAS_GENERICAS = ['Campañas', 'Promociones', 'Cartelería', 'Redes sociales', 'Otras acciones']

export const MUNDOS: Mundo[] = [
  {
    clave: 'tienda_inglesa', nombre: 'Tienda Inglesa', color: '#2563eb',
    bajada: 'Calendario comercial, envíos, Retail Media y headers de la home',
    secciones: ['comercial', 'envios', 'retail', 'header'], bandas: null,
  },
  {
    clave: 'tienda_express', nombre: 'Tienda Express', color: '#059669',
    bajada: 'Las acciones de Express, parte de Tienda Inglesa',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
  {
    clave: 'redexpres', nombre: 'Redexpres', color: '#dc2626',
    bajada: 'Las acciones y la cartelería de la red de locales',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
  {
    clave: 'tienda_viajes', nombre: 'Tienda Viajes', color: '#0891b2',
    bajada: 'Campañas y envíos de Tienda Viajes',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
  {
    clave: 'tienda_farma', nombre: 'Tienda Farma', color: '#7c3aed',
    bajada: 'Campañas y envíos de Tienda Farma',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
]

export const MUNDO_POR_DEFECTO = 'tienda_inglesa'

export function mundoDe(clave: string | null | undefined): Mundo | null {
  return MUNDOS.find(m => m.clave === clave) ?? null
}

/** Los mundos que puede abrir la persona, en el orden del selector. */
export function mundosDe(user: CurrentUser | null | undefined): Mundo[] {
  const propios = new Set(user?.mundos ?? [])
  return MUNDOS.filter(m => propios.has(m.clave))
}

/**
 * En qué mundo está parada la persona. El que eligió, si lo sigue teniendo; si
 * tiene uno solo, ese, sin preguntarle; si tiene varios y todavía no eligió,
 * null: hay que mandarla al selector.
 */
export function mundoEfectivo(user: CurrentUser | null | undefined, elegido: string | null): Mundo | null {
  const propios = mundosDe(user)
  const el = propios.find(m => m.clave === elegido)
  if (el) return el
  return propios.length === 1 ? propios[0] : null
}

type EstadoMundo = {
  /** El último mundo que eligió la persona en este navegador. */
  elegido: string | null
  elegir: (clave: string) => void
}

export const useMundoElegido = create<EstadoMundo>()(
  persist(
    set => ({ elegido: null, elegir: clave => set({ elegido: clave }) }),
    { name: 'core-tienda-mundo', storage: createJSONStorage(() => localStorage) },
  ),
)
