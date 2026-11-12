"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Globe2, ShieldAlert } from "lucide-react";
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
import { VistaLista } from "@/components/calendario/VistaLista";
import { calendarioApi } from "@/lib/api";
import { mundoEfectivo, mundosDe, useMundoElegido, type SeccionDeMundo } from "@/lib/mundos";
import { SEGUNDOS_ENTRE_REVISIONES, useCalendario } from "@/lib/calendario/store";
import { claveDe } from "@/lib/calendario/fechas";
import { PERMISOS_CALENDARIO } from "@/lib/calendario/permisos";

/**
 * `/calendario?accion=br-xxx` abre la ficha de esa acción, en su mes. Es a
 * donde lleva tocar un aviso en la campanita o una tarea de "Mis tareas".
 *
 * La acción puede ser de otro mundo que el que se está mirando: si no está en
 * lo cargado, se le pregunta al servidor en cuál está y se pasa a ese.
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
        try {
          const { data } = await calendarioApi.ubicar(pedida);
          if (data.mundo !== useCalendario.getState().mundo) {
            useMundoElegido.getState().elegir(data.mundo);
            useCalendario.getState().usarMundo(data.mundo);
          }
        } catch {
          // No está, o es de un mundo que la persona no abre: se avisa abajo.
        }
        await useCalendario.getState().sincronizar();
        if (!abrir(pedida)) toast.error("Esa acción ya no está en el calendario, o es de un mundo al que no tenés acceso.");
      }
      router.replace("/calendario");
    })();
  }, [pedida, router]);

  return null;
}

export default function CalendarioPage() {
  const { t } = useTranslation();
  const { allowed, checked, user } = usePermissionGuard({ permission: PERMISOS_CALENDARIO.ver });
  const router = useRouter();
  const elegido = useMundoElegido(s => s.elegido);
  const mundo = mundoEfectivo(user, elegido);
  const cantidadDeMundos = mundosDe(user).length;
  const vista = useCalendario(s => s.vista);
  const filtro = useCalendario(s => s.filtro);

  // Primero la copia del navegador, para no arrancar en blanco (localStorage
  // no existe hasta que monta el cliente, por eso persist va con
  // skipHydration); enseguida lo del servidor, que es lo que ve el resto del
  // equipo, y pisa lo local.
  const [listo, setListo] = useState(false);
  useEffect(() => {
    // La primera vez en una pantalla angosta (un teléfono) arranca en la
    // lista de tarjetas: la línea de tiempo necesita ancho. Después manda lo
    // que la persona elija.
    const primeraVez = localStorage.getItem("calendario-mktg-v3") === null;
    useCalendario.persist.rehydrate();
    if (primeraVez && window.innerWidth < 768) useCalendario.getState().setVista("lista");
    setListo(true);
  }, []);

  // Con varios mundos y ninguno elegido, primero se elige.
  useEffect(() => {
    if (allowed && !mundo && cantidadDeMundos > 1) router.replace("/mundos");
  }, [allowed, mundo, cantidadDeMundos, router]);

  // Lo que hacen los demás aparece solo: cada tanto se pregunta si cambió algo
  // (si no cambió, la respuesta es una línea), y también al volver a la
  // pestaña. Con la pestaña escondida no se pregunta.
  const claveMundo = mundo?.clave;
  useEffect(() => {
    if (!allowed || !listo || !claveMundo) return;
    const { sincronizar, traerPersonas, usarMundo } = useCalendario.getState();
    // Si lo guardado en el navegador era de otro mundo, se tira y se trae este.
    usarMundo(claveMundo);
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
  }, [allowed, listo, claveMundo]);

  if (checked && !allowed) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <ShieldAlert size={40} className="text-rose-400" />
        <p className="font-medium text-slate-600 dark:text-slate-400">{t("calendario.accessDenied")}</p>
      </div>
    );
  }

  if (allowed && user && cantidadDeMundos === 0) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-20 text-center">
        <Globe2 size={40} className="text-slate-300" />
        <p className="text-lg font-semibold text-slate-800 dark:text-slate-200">Todavía no tenés ningún calendario asignado</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Pedile a quien administra la plataforma que te dé acceso al de Tienda Inglesa, Redexpres o el que te corresponda.
        </p>
      </div>
    );
  }

  if (!allowed || !listo || !mundo) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400 dark:text-slate-500">
        {t("calendario.loading")}
      </div>
    );
  }

  /** Si esa parte del calendario existe en este mundo y no está filtrada. */
  const ve = (seccion: SeccionDeMundo) =>
    mundo.secciones.includes(seccion) && (filtro === "todo" || filtro === seccion);

  return (
    // El id y el fondo son para la pantalla completa: al pedirla, el navegador
    // saca este nodo del flujo y lo pinta contra negro, así que el fondo y el
    // scroll tienen que estar puestos acá y no heredarse del dashboard.
    <div
      id="calendario-pantalla"
      className="animate-fade-in bg-slate-50 dark:bg-slate-950 [&:fullscreen]:overflow-auto [&:fullscreen]:p-6"
    >
      <Suspense fallback={null}>
        <AbrirAccionDeLaUrl />
      </Suspense>
      <BarraSuperior />
      {/* El id lo usa el boton "que entre el mes entero": mide la caja real
          de una seccion para calcular el zoom. */}
      {vista === "lista" ? (
        <VistaLista />
      ) : (
        <div id="calendario" className="space-y-5">
          {ve("comercial") && <CalendarioComercial />}
          {ve("envios") && <CalendarioEnvios />}
          {ve("retail") && <CalendarioRetail />}
          {ve("header") && <HeaderHome />}
        </div>
      )}
      <EditorBarra />
      <PanelAccion />
    </div>
  );
}
