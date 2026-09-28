"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { usePermissionGuard } from "@/hooks/usePermissionGuard";
import { BarraSuperior } from "@/components/calendario/BarraSuperior";
import { CalendarioComercial } from "@/components/calendario/CalendarioComercial";
import { CalendarioRetail } from "@/components/calendario/CalendarioRetail";
import { CalendarioEnvios } from "@/components/calendario/CalendarioEnvios";
import { HeaderHome } from "@/components/calendario/HeaderHome";
import { EditorBarra } from "@/components/calendario/EditorBarra";
import { PanelAccion } from "@/components/calendario/PanelAccion";
import { SEGUNDOS_ENTRE_REVISIONES, useCalendario } from "@/lib/calendario/store";
import { claveDe } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";

/**
 * `/calendario?accion=br-xxx` abre la ficha de esa acción, en su mes. Es a
 * donde lleva tocar un aviso en la campanita.
 */
function AbrirAccionDeLaUrl() {
  const params = useSearchParams();
  const router = useRouter();
  const pedida = params.get("accion");
  const hecha = useRef<string | null>(null);

  useEffect(() => {
    // Sin pedido se olvida el último: tocar dos veces el mismo aviso tiene que
    // abrir la ficha las dos veces.
    if (!pedida) { hecha.current = null; return; }
    if (hecha.current === pedida) return;
    hecha.current = pedida;

    const abrir = (id: string) => {
      const accion = useCalendario.getState().barras[id];
      if (!accion) return false;
      useCalendario.getState().irAMes(claveDe(accion.desde));
      useCalendario.getState().abrirAccion(accion.id);
      return true;
    };
    void (async () => {
      // Si no está en lo que ya hay, primero se pregunta al servidor: puede
      // ser una acción recién creada que todavía no llegó. Recién si tampoco
      // está ahí, la borraron.
      if (!abrir(pedida)) {
        await useCalendario.getState().sincronizar();
        if (!abrir(pedida)) toast.error("Esa acción ya no está en el calendario: la borraron.");
      }
      router.replace("/calendario");
    })();
  }, [pedida, router]);

  return null;
}

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
  }, []);

  // Lo que hacen los demás aparece solo: cada tanto se pregunta si cambió algo
  // (si no cambió, la respuesta es una línea), y también al volver a la
  // pestaña. Con la pestaña escondida no se pregunta.
  useEffect(() => {
    if (!allowed) return;
    const { sincronizar, traerPersonas } = useCalendario.getState();
    void sincronizar();
    void traerPersonas();
    const revisar = () => {
      if (document.visibilityState === "visible") void useCalendario.getState().sincronizar();
    };
    const intervalo = window.setInterval(revisar, SEGUNDOS_ENTRE_REVISIONES * 1000);
    document.addEventListener("visibilitychange", revisar);
    window.addEventListener("focus", revisar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", revisar);
      window.removeEventListener("focus", revisar);
    };
  }, [allowed]);

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
      <Suspense fallback={null}>
        <AbrirAccionDeLaUrl />
      </Suspense>
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
