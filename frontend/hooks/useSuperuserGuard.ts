"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

// Los 3 rutas de /herramientas/cenefas/v2 (editor, generar, jobs) quedaron
// como herramientas de debug no listadas tras unificar la generación en
// RedExpressPanel/RompePreciosPanel + PreviewStep — solo superadmins.
// Devuelve true recién cuando ya se confirmó el acceso, para no flashear
// contenido antes de redirigir a un usuario sin permiso.
export function useSuperuserGuard(): boolean {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    authApi.me()
      .then(({ data }) => {
        if (data.is_superuser) setAllowed(true);
        else router.replace("/herramientas/cenefas");
      })
      .catch(() => router.replace("/herramientas/cenefas"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return allowed;
}
