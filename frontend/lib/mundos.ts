'use client'
// ---------------------------------------------------------------------------
// Los mundos: cada negocio, con toda la plataforma para él solo.
//
// Pedido de Ivan (12/11/2026): "Los mundos tienen que ser de toda la
// plataforma. La persona que entra a ese mundo va a ver todo hecho para ese
// mundo". Quien tiene acceso a varios elige al entrar; quien tiene uno solo
// "va directamente al único mundo al que tiene acceso".
//
// Entrar a un mundo cambia tres cosas:
//   1. Qué herramientas hay en el menú (RUTAS_DE_MUNDO, acá abajo): la
//      planilla de pedidos es solo de Redexpres; los medios y las finanzas
//      están en todos.
//   2. Lo que se guarda separado por negocio: el calendario y sus tareas, y
//      los tipos de cenefa. Eso lo cuida también el servidor.
//   3. Nada más. Los permisos valen igual que siempre: el mundo dice DE QUÉ
//      negocio, el permiso dice QUÉ se puede hacer.
//
// Las claves son las mismas que en backend/app/core/mundos.py: si se agrega un
// mundo, va en los dos lados. A qué mundos entra cada persona lo dice el
// servidor (`user.mundos`); acá está cómo se llama, cómo se ve y qué trae.
// ---------------------------------------------------------------------------

import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { CurrentUser } from '../types'
import { INICIO_DE_EXTERNOS } from './externos'
import { veCalendario } from './alcance'

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
  /** Filas que dejaron de usarse: hasta qué mes ('YYYY-MM') se siguen viendo.
   *  Después no aparecen, y no se ofrecen para acciones nuevas. */
  bandasRetiradas?: Record<string, string>
}

const BANDAS_GENERICAS = ['Campañas', 'Promociones', 'Cartelería', 'Redes sociales', 'Otras acciones']
/** Las filas del Excel de Redexpres ("PAC 2026 Tareas"), en su orden (Ivan,
 *  18/11/2026: "lo ideal es que el calendario de Redex sea idéntico a esto").
 *  Las acciones de 2026 las cargó la migración 0076. */
export const BANDAS_REDEXPRES = [
  'MAILING - 16 PAG EL PAIS', 'MAILING - 40 PAG EL PAIS', 'ESPECIAL - CM', 'TÁCTICO (x LOCAL) CM',
  'Super FDS', 'BOMBAS', 'DIAS EXPRES',
]

export const MUNDOS: Mundo[] = [
  {
    clave: 'tienda_inglesa', nombre: 'Tienda Inglesa', color: '#2563eb',
    bajada: 'El calendario, las tareas y todas las herramientas de Tienda Inglesa',
    secciones: ['comercial', 'envios', 'retail', 'header'], bandas: null,
  },
  {
    // Para la empresa es parte de Tienda Inglesa; acá va aparte porque tiene
    // su propia web y va a tener acciones solo suyas.
    clave: 'tienda_express', nombre: 'Tienda Express', color: '#059669',
    bajada: 'El calendario y las tareas de Tienda Express',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
  {
    clave: 'redexpres', nombre: 'Redexpres', color: '#dc2626',
    bajada: 'El calendario, las tareas, las cenefas y los pedidos de la red de locales',
    secciones: ['comercial', 'envios'], bandas: BANDAS_REDEXPRES,
    // Ivan (20/11/2026): "FDS no va a existir más (...) la línea de FDS no
    // debería existir más a partir de diciembre".
    bandasRetiradas: { 'Super FDS': '2026-11' },
  },
  {
    clave: 'tienda_viajes', nombre: 'Tienda Viajes', color: '#0891b2',
    bajada: 'El calendario y las tareas de Tienda Viajes',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
  {
    clave: 'tienda_farma', nombre: 'Tienda Farma', color: '#7c3aed',
    bajada: 'El calendario y las tareas de Tienda Farma',
    secciones: ['comercial', 'envios'], bandas: BANDAS_GENERICAS,
  },
]

export const MUNDO_POR_DEFECTO = 'tienda_inglesa'

export function mundoDe(clave: string | null | undefined): Mundo | null {
  return MUNDOS.find(m => m.clave === clave) ?? null
}

/** Los mundos a los que entra la persona, en el orden del selector. */
export function mundosDe(user: CurrentUser | null | undefined): Mundo[] {
  if (!user) return []
  // Un servidor de antes de los mundos no manda la lista. Vercel y Render
  // despliegan cada uno por su lado: si este front sale primero, todos
  // quedarían "sin ningún calendario asignado" hasta que llegue el backend.
  // Mientras tanto, lo de siempre: Tienda Inglesa (lo mismo que hace el
  // servidor con quien no tiene ninguno).
  if (!Array.isArray(user.mundos)) return MUNDOS.filter(m => m.clave === MUNDO_POR_DEFECTO)
  const propios = new Set(user.mundos)
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

// ---------------------------------------------------------------------------
// Qué herramientas tiene cada mundo
// ---------------------------------------------------------------------------
//
// Cada herramienta es de los mundos donde tiene sentido. Lo que no está en
// esta lista (el calendario, Mis tareas, el perfil, la ayuda, Don Tino, el
// panel de administración, los medios y las finanzas) está en todos.
//
// Ivan (20/11/2026): "medios para todos, finanzas para todos, planilla de
// pedidos solo Redexpres". Los medios (dashboard, Analytics, campañas, el
// análisis con IA y las conexiones) y Finanzas son los mismos datos en todos
// los mundos: no se separan por negocio.
//
// Es una lista corta a propósito: para sumarle una herramienta a un mundo
// alcanza con agregar su clave acá, y aparece en su menú.

const SOLO_TIENDA_INGLESA = ['tienda_inglesa']

export const RUTAS_DE_MUNDO: { prefijo: string; nombre: string; mundos: string[] }[] = [
  // El orden importa: gana la primera que coincide, así que lo más específico va antes.
  { prefijo: '/materiales/diccionario', nombre: 'El diccionario', mundos: SOLO_TIENDA_INGLESA },
  // Las cenefas se hacen para Tienda Inglesa y para Redexpres. Cuáles se ven
  // en cada mundo lo decide el tipo de cenefa (cenefa_destinos.mundo).
  { prefijo: '/materiales', nombre: 'Las cenefas', mundos: ['tienda_inglesa', 'redexpres'] },
  { prefijo: '/redes-sociales', nombre: 'La validación de redes sociales', mundos: SOLO_TIENDA_INGLESA },
  { prefijo: '/redexpres', nombre: 'Los pedidos de Redexpres', mundos: ['redexpres'] },
  { prefijo: '/precios', nombre: 'Los precios', mundos: SOLO_TIENDA_INGLESA },
]

/** La herramienta a la que pertenece una ruta, o null si es de todos los mundos. */
export function herramientaDe(pathname: string) {
  return RUTAS_DE_MUNDO.find(r => pathname === r.prefijo || pathname.startsWith(r.prefijo + '/')) ?? null
}

/** Si esa pantalla existe en ese mundo. */
export function rutaEnMundo(pathname: string, mundo: string): boolean {
  const herramienta = herramientaDe(pathname)
  return !herramienta || herramienta.mundos.includes(mundo)
}

/** A dónde va la persona al entrar: una cuenta externa (la agencia), a su
 *  trabajo (lib/externos.ts); al calendario si lo puede ver; si no, a donde
 *  entraba antes (los logins de sucursal, por ejemplo). */
export function inicioDe(user: CurrentUser | null | undefined): string {
  if (user?.es_externo) return INICIO_DE_EXTERNOS
  const ve = !!user && (user.is_superuser || (user.permissions ?? []).includes('calendario.view'))
  // Quien tiene el calendario pero su alcance es "No lo ve" (0070) entra a su tablero.
  if (ve && !veCalendario(user)) return INICIO_DE_EXTERNOS
  return ve ? '/calendario' : '/home'
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
