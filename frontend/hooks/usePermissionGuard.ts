"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";

interface PermissionGuardOptions {
  /** Permiso puntual requerido (ver require_permission en el backend). Si se
   * omite, alcanza con estar logueado (salvo requireSuperuser). */
  permission?: string;
  requireSuperuser?: boolean;
  /** Si se pasa, redirige automáticamente ante acceso denegado. Si se omite,
   * el caller decide qué mostrar — útil para denegación inline en vez de
   * sacar al usuario de la página. */
  redirectTo?: string;
}

/** Gating de acceso client-side unificado — reemplaza los chequeos sueltos
 * que había por página (useSuperuserGuard, hasPerm duplicado en Sidebar y
 * ayuda, guard inline de admin/page.tsx), cada uno con su propia forma de
 * pedir /auth/me y decidir qué hacer ante un "no". `checked` pasa a true
 * recién cuando ya sabemos si hay acceso o no (evita flashear contenido antes
 * de redirigir); `allowed` es la respuesta en sí. */
export function usePermissionGuard(options: PermissionGuardOptions = {}) {
  const { permission, requireSuperuser, redirectTo } = options;
  const router = useRouter();
  const { user, loading } = useCurrentUser();

  const checked = !loading;
  const allowed =
    checked &&
    !!user &&
    (requireSuperuser ? user.is_superuser : !permission || hasPermission(user, permission));

  useEffect(() => {
    if (checked && !allowed && redirectTo) {
      router.replace(redirectTo);
    }
  }, [checked, allowed, redirectTo, router]);

  return { allowed, checked, user };
}
