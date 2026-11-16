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
import { mundoEfectivo, mundosDe, useMundoElegido, type SeccionDeMundo } from "@/lib/mundos";
import { SEGUNDOS_ENTRE_REVISIONES, useCalendario } from "@/lib/calendario/store";
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

    void (async () => {
      // La búsqueda (en lo que ya hay, en el servidor, en otro mundo) está en
      // el store: la usa también "Copiar a otra fecha".
      if (!(await useCalendario.getState().irAAccion(pedida))) {
        toast.error("Esa acción ya no está en el calendario, o es de un mundo al que no tenés acceso.");
      }
      router.replace("/calendario");
    })();
  }, [pedida, router]);

  return null;
}

/**
 * Mientras llega el calendario: la forma de la barra de arriba y de la
 * rejilla, en gris. Se ve dónde va a estar cada cosa en vez de un texto solo.
 */
function EsqueletoCalendario({ texto }: { texto: string }) {
  return (
    <div role="status" aria-label={texto} className="animate-fade-in">
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-card dark:border-slate-800 dark:bg-slate-900 sm:px-5">
        <div className="flex items-center gap-3">
          <div className="skeleton hidden h-10 w-10 rounded-xl sm:block" />
          <div className="hidden space-y-2 sm:block">
            <div className="skeleton h-3 w-20 rounded-md" />
            <div className="skeleton h-4 w-32 rounded-md" />
          </div>
          <div className="skeleton mx-auto h-9 w-56 rounded-xl sm:mr-0" />
        </div>
        <div className="mt-4 flex gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
          {[14, 24, 18, 24].map((w, i) => <div key={i} className="skeleton h-8 rounded-full" style={{ width: `${w * 4}px` }} />)}
          <div className="skeleton ml-auto hidden h-9 w-48 rounded-xl sm:block" />
        </div>
      </div>
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-3 border-b border-slate-200 p-4 dark:border-slate-800">
          <div className="skeleton h-9 w-9 rounded-xl" />
          <div className="skeleton h-4 w-44 rounded-md" />
        </div>
        {[0, 1, 2, 3, 4, 5].map(i => (
          <div key={i} className="flex h-[38px] items-center gap-4 border-b border-slate-100 px-4 last:border-0 dark:border-slate-800">
            <div className="skeleton h-3 w-24 shrink-0 rounded-md sm:w-40" />
            <div className="skeleton h-6 rounded-lg" style={{ width: `${[38, 22, 55, 30, 44, 18][i]}%`, marginLeft: `${[4, 30, 12, 40, 8, 50][i]}%` }} />
          </div>
        ))}
      </div>
      <span className="sr-only">{texto}</span>
    </div>
  );
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
  // De qué mundo es lo cargado en el store (la copia del navegador puede ser
  // de otro). Hasta que coincide con el elegido no se muestra nada: ni un
  // instante de lo de otro mundo, y una acción pedida por la URL (la
  // campanita, "Mis tareas") no se abre desde la copia vieja para cerrarse
  // enseguida cuando el store pasa al mundo elegido.
  const mundoCargado = useCalendario(s => s.mundo);

  // Primero la copia del navegador, para no arrancar en blanco (localStorage
  // no existe hasta que monta el cliente, por eso persist va con
  // skipHydration); enseguida lo del servidor, que es lo que ve el resto del
  // equipo, y pisa lo local.
  const [listo, setListo] = useState(false);
  useEffect(() => {
    // Arranca en la vista Calendario también en el teléfono: desde el
    // rediseño del 15/11/2026 se usa bien en pantallas angostas (antes la
    // primera vez abría en la Lista). Después manda lo que la persona elija.
    useCalendario.persist.rehydrate();
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

  if (!allowed || !listo || !mundo || mundoCargado !== mundo.clave) {
    return <EsqueletoCalendario texto={t("calendario.loading")} />;
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
