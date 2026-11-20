// ---------------------------------------------------------------------------
// Qué permiso pide cada herramienta, para decir "No tenés acceso" en vez de
// mostrar una pantalla rota.
//
// Pedido de Ivan (20/11/2026). En el recorrido de toda la app (18/11) quien
// entraba escribiendo la dirección de una herramienta sin tener el permiso
// veía errores sueltos ("No se pudo cargar", 403 en cada recuadro). Ahora ve
// una sola pantalla que le dice qué herramienta es y que no la tiene.
//
// Es el mismo permiso con el que el menú muestra el link
// (components/layout/Sidebar.tsx), que a su vez es el que exige el servidor
// (require_permission): si se cambia uno, se cambia en los dos lados. El
// servidor sigue siendo el que de verdad cuida: esto es solo la pantalla.
//
// Lo que no está acá (el calendario, Mis tareas, el tablero, el perfil, la
// ayuda, el inicio) lo resuelve cada pantalla o el layout.
// ---------------------------------------------------------------------------

import type { CurrentUser } from '../types'

export type Requisito = {
  prefijo: string
  nombre: string
  /** Alcanza con tener UNO de estos permisos. */
  permisos: string[]
  /** Cuando no es cuestión de un permiso (Mi pedido: tener un local asignado). */
  cumple?: (user: CurrentUser) => boolean
}

export const REQUISITOS: Requisito[] = [
  // Gana el primero que coincide: lo más específico va antes.
  { prefijo: '/materiales/diccionario', nombre: 'El diccionario', permisos: ['cenefas.diccionario'] },
  { prefijo: '/materiales', nombre: 'Las cenefas', permisos: ['cenefas.view', 'cenefas.edit'] },
  { prefijo: '/redes-sociales', nombre: 'La validación de redes sociales', permisos: ['rrss.view', 'rrss.validate'] },
  { prefijo: '/dashboard', nombre: 'El dashboard de medios', permisos: ['analytics.view'] },
  { prefijo: '/canales', nombre: 'Analytics', permisos: ['analytics.view'] },
  { prefijo: '/campaigns', nombre: 'Las campañas de medios', permisos: ['analytics.view'] },
  { prefijo: '/analytics', nombre: 'El análisis con IA', permisos: ['ai.triada'] },
  { prefijo: '/settings', nombre: 'Las conexiones de medios', permisos: ['connections.view'] },
  { prefijo: '/redexpres/planilla', nombre: 'La planilla de pedidos', permisos: ['redexpres.view', 'redexpres.manage'] },
  {
    prefijo: '/redexpres/mi-pedido', nombre: 'Mi pedido', permisos: ['redexpres.manage'],
    cumple: user => (user.assigned_locales?.length ?? 0) > 0,
  },
  { prefijo: '/facturacion/cuentas', nombre: 'Las cuentas de Finanzas', permisos: ['facturacion.manage'] },
  { prefijo: '/facturacion', nombre: 'Finanzas', permisos: ['facturacion.view', 'facturacion.manage'] },
  { prefijo: '/precios', nombre: 'Los precios', permisos: ['precios.search'] },
  { prefijo: '/colocacion', nombre: 'La colocación', permisos: ['calendario.edit'] },
  { prefijo: '/admin', nombre: 'El panel de administración', permisos: ['platform.admin'] },
]

/** "No tenés acceso ___": al diccionario, a la planilla, a Finanzas. Pura. */
export function aLaHerramienta(nombre: string): string {
  const m = /^(El|La|Las|Los) (.+)$/.exec(nombre)
  if (!m) return `a ${nombre}`
  const articulo = m[1].toLowerCase()
  return articulo === 'el' ? `al ${m[2]}` : `a ${articulo} ${m[2]}`
}

/** Lo que pide esa pantalla, o null si no pide nada en particular. Pura. */
export function requisitoDe(pathname: string): Requisito | null {
  return REQUISITOS.find(r => pathname === r.prefijo || pathname.startsWith(r.prefijo + '/')) ?? null
}

/**
 * Si la persona puede abrir esa pantalla. Pura.
 *
 * Sin usuario (el /auth/me falló por la red) se deja pasar: cada pantalla
 * maneja su error, y decir "No tenés acceso" a quien sí lo tiene sería peor.
 */
export function puedeEntrar(pathname: string, user: CurrentUser | null | undefined): boolean {
  const req = requisitoDe(pathname)
  if (!req || !user) return true
  if (user.is_superuser) return true
  const propios = user.permissions ?? []
  return req.permisos.some(p => propios.includes(p)) || !!req.cumple?.(user)
}
