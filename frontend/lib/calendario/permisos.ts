"use client";
// ---------------------------------------------------------------------------
// Quién puede hacer qué en el calendario.
//
// Mientras el calendario vivió como app aparte, esto era un selector de
// "Trabajando como" con personas inventadas. Adentro de la plataforma sale del
// usuario logueado: los mismos permisos que exige el backend en role.py.
// ---------------------------------------------------------------------------

import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import type { CurrentUser } from "@/types";

export const PERMISOS_CALENDARIO = {
  /** Entrar al calendario. Es el que filtra el link del menú. */
  ver: "calendario.view",
  /** Crear, editar y borrar barras, y mover el estado de las piezas. */
  editar: "calendario.edit",
  /** Mover las posiciones que Retail Media tiene reservadas en el header. */
  retailMedia: "calendario.retail_media",
  /** Crear, asignar y borrar las tareas de cada acción. */
  tareas: "calendario.tareas",
  /** Crear tareas en una acción, también para una agencia (Banners, Mailing, Cenefas…).
   *  Desde el 17/11/2026 es un permiso aparte de `editar`. */
  pedidos: "calendario.pedidos",
} as const;

export function puedeVer(user: CurrentUser | null | undefined): boolean {
  return hasPermission(user, PERMISOS_CALENDARIO.ver);
}

export function puedeEditar(user: CurrentUser | null | undefined): boolean {
  return hasPermission(user, PERMISOS_CALENDARIO.editar);
}

export function puedeMoverRM(user: CurrentUser | null | undefined): boolean {
  return hasPermission(user, PERMISOS_CALENDARIO.retailMedia);
}

/**
 * Lo que necesita cada sección del calendario: si puede editar, si puede mover
 * las posiciones de Retail Media, y con qué nombre firmar la notificación que
 * se le manda a quien lleva Retail Media.
 */
export function usePermisosCalendario() {
  const { user } = useCurrentUser();
  return {
    user,
    editable: puedeEditar(user),
    moverRM: puedeMoverRM(user),
    /** Crea, asigna y borra tareas. Los demás solo mueven el estado de las suyas. */
    gestionaTareas: hasPermission(user, PERMISOS_CALENDARIO.tareas),
    /** Pide piezas y materiales. Quien gestiona tareas también puede. */
    pidePiezas: hasPermission(user, PERMISOS_CALENDARIO.tareas) || hasPermission(user, PERMISOS_CALENDARIO.pedidos),
    autor: user?.full_name || user?.email || "Alguien",
  };
}
