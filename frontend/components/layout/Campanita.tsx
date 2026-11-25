"use client";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import {
  AlertTriangle, Bell, BellOff, CalendarClock, CalendarDays, Camera, Check, CheckCheck, Layers, ListChecks, TrendingDown, TrendingUp,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { watchlistApi, type Notificacion } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { alcanceDe } from "@/lib/alcance";
import { destinoDeAvisoSinAccion } from "@/lib/calendario/sin-accion";
import type { CurrentUser } from "@/types";
import { useAvisos } from "@/store/avisos";

/** El círculo de color con el ícono de cada aviso. */
function Chip({ tono, children }: { tono: string; children: React.ReactNode }) {
  return (
    <span className={clsx("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", tono)}>
      {children}
    </span>
  );
}

// Subida de precio = malo para quien monitorea (rojo); bajada = bueno (verde).
// Alertas de campaña ("Medios") comparten un solo ícono de advertencia — la
// distinción de causa ya está en el mensaje mismo. Los avisos del calendario
// van en el color de la marca, con el ícono de lo que son: una tarea o una
// fecha que se acerca.
function notifIcon(tipo: string) {
  switch (tipo) {
    case "precio_baja":
      return <Chip tono="bg-emerald-100 dark:bg-emerald-500/15"><TrendingDown size={15} className="text-emerald-600 dark:text-emerald-400" /></Chip>;
    case "precio_sube":
      return <Chip tono="bg-red-100 dark:bg-red-500/15"><TrendingUp size={15} className="text-red-600 dark:text-red-400" /></Chip>;
    case "roas_baja":
    case "gasto_sube":
    case "conversiones_baja":
    case "sin_conversiones":
      return <Chip tono="bg-amber-100 dark:bg-amber-500/15"><AlertTriangle size={15} className="text-amber-600 dark:text-amber-400" /></Chip>;
    case "calendario_tarea":
      return <Chip tono="bg-brand-100 dark:bg-brand-500/20"><ListChecks size={15} className="text-brand-600 dark:text-brand-300" /></Chip>;
    case "calendario_entrega":
      return <Chip tono="bg-amber-100 dark:bg-amber-500/15"><Layers size={15} className="text-amber-700 dark:text-amber-300" /></Chip>;
    case "calendario_aviso":
    case "calendario_accion":
      return <Chip tono="bg-brand-100 dark:bg-brand-500/20"><CalendarClock size={15} className="text-brand-600 dark:text-brand-300" /></Chip>;
    case "calendario_header":
      return <Chip tono="bg-violet-100 dark:bg-violet-500/20"><CalendarDays size={15} className="text-violet-600 dark:text-violet-300" /></Chip>;
    // La foto de colocación: te la pidieron, o mandaron todos (promo); si te
    // la devolvieron, en ámbar, como lo que hay que arreglar.
    case "colocacion_pedido":
    case "colocacion_completa":
      return <Chip tono="bg-sky-100 dark:bg-sky-500/20"><Camera size={15} className="text-sky-600 dark:text-sky-300" /></Chip>;
    case "colocacion_devuelta":
      return <Chip tono="bg-amber-100 dark:bg-amber-500/15"><Camera size={15} className="text-amber-600 dark:text-amber-400" /></Chip>;
    default:
      return <Chip tono="bg-slate-100 dark:bg-slate-500/15"><Bell size={15} className="text-slate-500 dark:text-slate-400" /></Chip>;
  }
}

/** "hace 5 minutos", "ayer", "hace 3 días"; pasada una semana, la fecha. */
function cuandoFue(iso: string, idioma: string): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return "";
  const segundos = Math.min(0, (fecha.getTime() - Date.now()) / 1000);
  const abs = Math.abs(segundos);
  try {
    const rtf = new Intl.RelativeTimeFormat(idioma, { numeric: "auto" });
    if (abs < 60) return rtf.format(0, "second");
    if (abs < 3600) return rtf.format(Math.round(segundos / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(segundos / 3600), "hour");
    if (abs < 7 * 86400) return rtf.format(Math.round(segundos / 86400), "day");
  } catch {
    // Un navegador sin RelativeTimeFormat muestra la fecha, como antes.
  }
  return fecha.toLocaleDateString(idioma, { day: "2-digit", month: "2-digit", year: "numeric" });
}

// A dónde navegar al clickear una notificación — se deriva de los campos que
// ya existen (watchlist_item_id, origen_tipo), sin necesidad de un campo
// nuevo. Cualquier tipo futuro no mapeado no navega, en vez de adivinar.
function resolverDestino(n: Notificacion, user?: CurrentUser | null): string | null {
  if (n.watchlist_item_id != null) return "/precios/listas";
  if (n.origen_tipo === "campaign_alert") return "/campaigns";
  // Los avisos del calendario abren la ficha de su acción. Los configurados a
  // mano llevan la acción primero ("br-xxx:av-yyy:2026-10-09"); los
  // automáticos de antes del 28/09/2026, en el medio ("2026-09:br-xxx:t-10").
  if (n.origen_tipo === "calendario_aviso" && n.origen_ref) {
    return `/calendario?accion=${encodeURIComponent(n.origen_ref.split(":")[0])}`;
  }
  if (n.origen_tipo === "calendario_accion" && n.origen_ref) {
    const accion = n.origen_ref.split(":")[1];
    return accion ? `/calendario?accion=${encodeURIComponent(accion)}` : "/calendario";
  }
  if (n.origen_tipo === "calendario_header") return "/calendario";
  // Una tarea asignada (o terminada) abre la ficha de su acción, que puede
  // ser de otro mundo: la página del calendario se encarga de pasar a ese.
  // A quien ve el calendario recortado, la acción puede quedarle afuera (una
  // tarea suya en mayo, con "1 mes"): la ficha no abría y el aviso decía "Esa
  // acción ya no está", como si se la hubieran borrado. Va a Mis tareas, que
  // la muestra siempre (con link si la acción está a la vista).
  if (n.origen_tipo === "calendario_tarea" && n.origen_ref) {
    // Una tarjeta sin acción (24/11/2026): no hay ficha de acción, va a la tarjeta.
    const sinAccion = destinoDeAvisoSinAccion(n.origen_ref);
    if (sinAccion) return sinAccion;
    if (alcanceDe(user) !== "todo") return "/mis-tareas";
    return `/calendario?accion=${encodeURIComponent(n.origen_ref.split(":")[0])}`;
  }
  // Al local: le pidieron una foto o se la devolvieron. Va a su pantalla, no
  // al calendario (que no ve).
  if (n.origen_tipo === "colocacion_pedido" || n.origen_tipo === "colocacion_devuelta") return "/fotos";
  // A promo: mandaron todos. Abre la acción en el tablero de fotos.
  if (n.origen_tipo === "colocacion_completa" && n.origen_ref) {
    return `/calendario?accion=${encodeURIComponent(n.origen_ref.split(":")[0])}&pestana=fotos`;
  }
  // Una entrega (llegó una versión, la aprobaron, volvió con cambios) abre
  // las entregas de su tarea, sobre el tablero: "acción:tarea:versión:evento".
  if (n.origen_tipo === "calendario_entrega" && n.origen_ref) {
    const tarea = n.origen_ref.split(":")[1];
    return tarea ? `/entregas?tarea=${encodeURIComponent(tarea)}` : "/entregas";
  }
  return null;
}

/**
 * La campanita, arriba a la derecha (Ivan, 18/11/2026: "el ícono de notis
 * debe ser más visible, pasa a ser algo importante en la web, debería estar
 * arriba a la derecha"). Antes vivía al pie del menú lateral.
 *
 * Marcar como leída sin entrar (Ivan, 19/11/2026: "en las notificaciones
 * tendría que haber un botoncito que te diga marcar como leída (…) si no
 * tenés que entrar sí o sí a la notificación para leerla. También otro
 * botón que diga marcar todas como leídas"). Antes cada aviso tenía un
 * circulito que no se entendía como botón, y "Marcar todas" dependía del
 * número que trae el menú cada minuto: ahora cada aviso sin leer lleva un
 * botón con texto, y "Marcar todas como leídas" está siempre que haya
 * alguna sin leer en la lista.
 *
 * El número lo pregunta el menú al servidor (cada minuto y al volver a la
 * pestaña) y lo comparte en `useAvisos`; la barra de abajo del teléfono
 * también lo muestra y pide abrir la lista con `pedirAbrir`. La lista se
 * dibuja en un portal: en el teléfono es una hoja abajo de todo, y en la
 * notebook cae debajo de la campanita.
 */
export function Campanita({ onNavegar }: { onNavegar?: () => void }) {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const { user: currentUser } = useCurrentUser();
  const notifCount = useAvisos((s) => s.noLeidos);
  const setNotifCount = useAvisos((s) => s.setNoLeidos);
  const [abierto, setAbierto] = useState(false);
  const [notificaciones, setNotificaciones] = useState<Notificacion[] | null>(null);
  const campanitaRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  function traer() {
    watchlistApi.notificaciones()
      .then(({ data }) => setNotificaciones(data))
      .catch(() => setNotificaciones([]));
  }

  function alternar() {
    const yaAbierto = abierto;
    setAbierto(!yaAbierto);
    if (!yaAbierto) traer();
  }

  // La barra de abajo del teléfono pide abrir la lista.
  useEffect(() => useAvisos.subscribe((ahora, antes) => {
    if (ahora.pedidoDeAbrir === antes.pedidoDeAbrir) return;
    setAbierto(true);
    traer();
  }), []);

  // Se cierra al tocar afuera, y con Escape (que además devuelve el foco a la
  // campanita, para seguir con el teclado).
  useEffect(() => {
    if (!abierto) return;
    function afuera(e: MouseEvent) {
      const t = e.target as Node;
      if (panelRef.current?.contains(t) || campanitaRef.current?.contains(t)) return;
      setAbierto(false);
    }
    function tecla(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setAbierto(false);
      campanitaRef.current?.focus();
    }
    document.addEventListener("mousedown", afuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", afuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto]);

  async function marcarTodasLeidas() {
    try {
      await watchlistApi.marcarTodasLeidas();
      setNotifCount(0);
      setNotificaciones((prev) => prev?.map((n) => ({ ...n, leida: true })) ?? null);
    } catch {
      toast.error(t("sidebar.notificacionesError"));
    }
  }

  // Marca una sola como leída, sin navegar.
  async function marcarUnaLeida(n: Notificacion, e?: ReactMouseEvent) {
    e?.stopPropagation();
    if (n.leida) return;
    setNotificaciones((prev) => prev?.map((x) => (x.id === n.id ? { ...x, leida: true } : x)) ?? null);
    setNotifCount((c) => Math.max(0, c - 1));
    try {
      await watchlistApi.marcarLeida(n.id);
    } catch {
      // no se revierte por un fallo de red puntual: la próxima carga se resincroniza
    }
  }

  function irANotificacion(n: Notificacion) {
    marcarUnaLeida(n);
    const destino = resolverDestino(n, currentUser);
    setAbierto(false);
    if (destino) {
      onNavegar?.();
      router.push(destino);
    }
  }

  /** Con el teclado, Enter o espacio sobre un aviso hacen lo mismo que el clic. */
  function teclaEnNotificacion(e: ReactKeyboardEvent, n: Notificacion) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      irANotificacion(n);
    }
  }

  // Hay algo sin leer: el número del menú (cuenta todos) o la lista. La lista
  // trae solo los 50 más nuevos: si lo sin leer es más viejo, sin el número
  // el botón desaparecía y el número quedaba sin poder sacarse.
  const haySinLeer = notifCount > 0 || !!notificaciones?.some((n) => !n.leida);

  const panel = (
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t("sidebar.notificaciones")}
      className={clsx(
        "z-[70] flex flex-col overflow-hidden rounded-2xl border border-slate-300 bg-white shadow-pop dark:border-white/10 dark:bg-slate-900",
        // En el teléfono, una hoja abajo de todo; en la notebook, debajo de la campanita.
        "fixed inset-x-3 bottom-3 max-h-[75dvh] animate-sheet-up",
        "md:inset-x-auto md:bottom-auto md:right-4 md:top-[3.6rem] md:max-h-[min(34rem,calc(100vh-5rem))] md:w-[26rem] md:origin-top-right md:animate-scale-in"
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-slate-200 px-4 py-3 dark:border-white/5">
        <p className="text-sm font-bold text-slate-900 dark:text-slate-100">{t("sidebar.notificaciones")}</p>
        {notifCount > 0 && (
          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
            {notifCount}
          </span>
        )}
        {haySinLeer && (
          <button
            type="button"
            onClick={marcarTodasLeidas}
            className="-mr-2 ml-auto flex min-h-[40px] items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 text-xs font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10 md:min-h-[36px]"
          >
            <CheckCheck size={15} aria-hidden /> {t("sidebar.marcarTodasLeidas")}
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {notificaciones === null && (
          <div className="space-y-1 p-2" aria-label={t("common.loading")}>
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-start gap-3 px-2 py-2.5">
                <div className="skeleton h-8 w-8 shrink-0 rounded-full" />
                <div className="flex-1 space-y-2 pt-1">
                  <div className="skeleton h-3 w-11/12 rounded-md" />
                  <div className="skeleton h-3 w-2/3 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        )}
        {notificaciones?.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-slate-400">
              <BellOff size={18} />
            </span>
            <p className="text-sm font-medium text-slate-600 dark:text-slate-300">{t("sidebar.sinNotificaciones")}</p>
          </div>
        )}
        {notificaciones?.map((n) => {
          const destino = resolverDestino(n, currentUser);
          return (
            <div
              key={n.id}
              role={destino ? "button" : undefined}
              tabIndex={destino ? 0 : undefined}
              onClick={() => irANotificacion(n)}
              onKeyDown={(e) => teclaEnNotificacion(e, n)}
              className={clsx(
                "relative flex items-start gap-3 border-b border-slate-200 px-4 py-3 transition-colors last:border-0 dark:border-white/5",
                destino ? "cursor-pointer hover:bg-slate-50 focus-visible:bg-slate-50 dark:hover:bg-white/5 dark:focus-visible:bg-white/5" : "cursor-default",
                !n.leida && "bg-brand-50/50 dark:bg-brand-500/[0.07]"
              )}
            >
              {!n.leida && <span className="absolute inset-y-3 left-0 w-[3px] rounded-r-full bg-brand-500" aria-hidden />}
              {notifIcon(n.tipo)}
              <div className="min-w-0 flex-1">
                <p className={clsx(
                  "text-[13px] leading-snug",
                  n.leida ? "text-slate-500 dark:text-slate-400" : "font-medium text-slate-900 dark:text-slate-100"
                )}>
                  {n.mensaje}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500 dark:text-slate-400">
                  {n.created_at && <span>{cuandoFue(n.created_at, i18n.language)}</span>}
                  {/* El botón, con texto, para que se entienda: 40 px de alto
                      en el teléfono para el dedo. Marca sin entrar al aviso. */}
                  {!n.leida && (
                    <button
                      type="button"
                      onClick={(e) => marcarUnaLeida(n, e)}
                      // Enter y espacio son de este botón (no abren el aviso);
                      // Escape sigue de largo y cierra la campanita.
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation(); }}
                      title={t("sidebar.marcarLeida")}
                      className="-my-2 flex min-h-[40px] items-center gap-1 rounded-lg px-1.5 text-xs font-semibold text-brand-700 transition hover:bg-brand-50 dark:text-brand-200 dark:hover:bg-brand-500/10 md:min-h-[32px]"
                    >
                      <Check size={14} strokeWidth={3} aria-hidden /> {t("sidebar.marcarLeida")}
                    </button>
                  )}
                </p>
              </div>
              {n.leida && <Check size={14} className="mt-0.5 shrink-0 text-slate-300 dark:text-slate-600" aria-hidden />}
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <>
      <button
        ref={campanitaRef}
        type="button"
        onClick={alternar}
        aria-label={notifCount > 0 ? `${t("sidebar.notificaciones")}: ${notifCount}` : t("sidebar.notificaciones")}
        title={t("sidebar.notificaciones")}
        aria-expanded={abierto}
        aria-haspopup="dialog"
        className={clsx(
          "relative flex h-10 items-center gap-2 rounded-xl border px-3 text-sm font-semibold shadow-sm transition active:scale-95",
          abierto
            ? "border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-500/40 dark:bg-brand-500/15 dark:text-brand-200"
            : notifCount > 0
              ? "border-brand-200 bg-white text-brand-700 hover:bg-brand-50 dark:border-brand-500/30 dark:bg-slate-900 dark:text-brand-200 dark:hover:bg-brand-500/10"
              : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:border-white/10 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-white/5"
        )}
      >
        <Bell size={18} />
        <span>{t("sidebar.notificaciones")}</span>
        {notifCount > 0 && (
          <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-rose-500 px-1.5 text-[11px] font-bold leading-none text-white">
            {notifCount > 99 ? "99+" : notifCount}
          </span>
        )}
      </button>
      {abierto && typeof document !== "undefined" && createPortal(panel, document.body)}
    </>
  );
}
