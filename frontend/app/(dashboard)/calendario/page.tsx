"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { BarraSuperior } from "@/components/calendario/BarraSuperior";
import { CalendarioComercial } from "@/components/calendario/CalendarioComercial";
import { CalendarioRetail } from "@/components/calendario/CalendarioRetail";
import { CalendarioEnvios } from "@/components/calendario/CalendarioEnvios";
import { HeaderHome } from "@/components/calendario/HeaderHome";
import { EditorBarra } from "@/components/calendario/EditorBarra";
import { PanelAccion } from "@/components/calendario/PanelAccion";
import { useCalendario } from "@/lib/calendario/store";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";

export default function CalendarioPage() {
  const { t } = useTranslation();
  const { allowed, checked } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });

  // Primero la copia del navegador, para no arrancar en blanco (localStorage
  // no existe hasta que monta el cliente, por eso persist va con
  // skipHydration); enseguida lo del servidor, que es lo que ve el resto del
  // equipo, y pisa lo local.
  const [listo, setListo] = useState(false);
  useEffect(() => {
    useCalendario.persist.rehydrate();
    setListo(true);
    useCalendario.getState().traerDelServidor();
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
    // El id y el fondo son para la pantalla completa: al pedirla, el navegador
    // saca este nodo del flujo y lo pinta contra negro, así que el fondo y el
    // scroll tienen que estar puestos acá y no heredarse del dashboard.
    <div
      id="calendario-pantalla"
      className="animate-fade-in"
    >
      <BarraSuperior />
      {/* El id lo usa el boton "que entre el mes entero": mide la caja real
          de una seccion para calcular el zoom. */}
      <div id="calendario" className="space-y-5">
        <CalendarioComercial />
        <CalendarioEnvios />
        <CalendarioRetail />
        <HeaderHome />
      </div>
      <EditorBarra />
      <PanelAccion />
    </div>
  );
}
