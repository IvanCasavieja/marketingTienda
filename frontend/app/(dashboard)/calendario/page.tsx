"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { BarraSuperior } from "@/components/calendario/BarraSuperior";
import { CalendarioComercial } from "@/components/calendario/CalendarioComercial";
import { CalendarioRetail } from "@/components/calendario/CalendarioRetail";
import { HeaderHome } from "@/components/calendario/HeaderHome";
import { EditorBarra } from "@/components/calendario/EditorBarra";
import { PanelAccion } from "@/components/calendario/PanelAccion";
import { useCalendario } from "@/lib/calendario/store";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";

export default function CalendarioPage() {
  const { t } = useTranslation();
  const { allowed, checked } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });

  // Lo guardado vive en localStorage, que no existe hasta que monta el
  // cliente: el store se rehidrata a mano (persist va con skipHydration).
  // Cuando el calendario guarde contra el backend, este gate sobra.
  const [listo, setListo] = useState(false);
  useEffect(() => {
    useCalendario.persist.rehydrate();
    setListo(true);
  }, []);

  if (checked && !allowed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="font-medium text-slate-600 dark:text-slate-400">{t("calendario.accessDenied")}</p>
      </div>
    );
  }

  if (!allowed || !listo) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400 dark:text-slate-500">
        {t("calendario.loading")}
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <BarraSuperior />
      {/* El id lo usa el boton "que entre el mes entero": mide la caja real
          de una seccion para calcular el zoom. */}
      <div id="calendario" className="space-y-5">
        <CalendarioComercial />
        <CalendarioRetail />
        <HeaderHome />
      </div>
      <EditorBarra />
      <PanelAccion />
    </div>
  );
}
