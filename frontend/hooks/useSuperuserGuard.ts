"use client";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";

// Los 3 rutas de /materiales/cenefas/v2 (editor, generar, jobs) quedaron
// como herramientas de debug no listadas tras unificar la generación en
// RedExpresPanel/RompePreciosPanel + PreviewStep — solo superadmins.
// Devuelve true recién cuando ya se confirmó el acceso, para no flashear
// contenido antes de redirigir a un usuario sin permiso.
export function useSuperuserGuard(): boolean {
  const { allowed } = usePermissionGuard({
    requireSuperuser: true,
    redirectTo: "/materiales/cenefas",
  });
  return allowed;
}
