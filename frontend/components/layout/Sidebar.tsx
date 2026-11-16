"use client";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Brain, Settings, LogOut,
  ChevronRight, Presentation, Globe, ShieldCheck, HelpCircle, X, Tag,
  Sun, Moon, ClipboardList, Bell, BellOff, Star, Activity, TrendingUp, TrendingDown, AlertTriangle, Check,
  FileSpreadsheet, BookOpen, Receipt, Landmark, ScanSearch, CalendarDays, CalendarClock,
  ListChecks, Wrench, ChevronDown, ArrowLeftRight, MessageCircle, Camera,
} from "lucide-react";
import { clsx } from "clsx";
import { ES, GB, BR } from "country-flag-icons/react/3x2";
import { authApi, watchlistApi, type Notificacion } from "@/lib/api";
import { useTranslation } from "react-i18next";
import { LANGUAGES, setLanguage, type LangCode } from "@/lib/i18n";
import { useTheme } from "@/hooks/useTheme";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import { toast } from "sonner";
import { MARCA, MARCA_BAJADA, inicioDe, mundoEfectivo, mundosDe, rutaEnMundo, useMundoElegido } from "@/lib/mundos";
import { useCalendario } from "@/lib/calendario/store";
import { useAvisos } from "@/store/avisos";
import { useLocalesDelMundo, usePendientesDeFotos } from "@/lib/colocacion/store";

/** Al cerrar sesión, lo de esta persona no queda en el navegador: la copia del
 *  calendario (con sus tareas) y el mundo que eligió. Antes quien entraba
 *  después en la misma computadora veía "el último que usaste" de otro. */
function olvidarDatosDelNavegador() {
  try {
    void useCalendario.persist.clearStorage();
    void useMundoElegido.persist.clearStorage();
  } catch {
    // Sin acceso al almacenamiento no hay nada guardado que borrar.
  }
}

// Los flags de country-flag-icons devuelven emoji de bandera regional, que
// Windows no renderiza como imagen (muestra el codigo de pais en texto) —
// estos SVG se ven iguales en todos los sistemas operativos.
const FLAG_ICONS: Record<string, typeof ES> = { ES, GB, BR };

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

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
function resolverDestino(n: Notificacion): string | null {
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
  if (n.origen_tipo === "calendario_tarea" && n.origen_ref) {
    return `/calendario?accion=${encodeURIComponent(n.origen_ref.split(":")[0])}`;
  }
  // Al local: le pidieron una foto o se la devolvieron. Va a su pantalla, no
  // al calendario (que no ve).
  if (n.origen_tipo === "colocacion_pedido" || n.origen_tipo === "colocacion_devuelta") return "/fotos";
  // A promo: mandaron todos. Abre la acción en el tablero de fotos.
  if (n.origen_tipo === "colocacion_completa" && n.origen_ref) {
    return `/calendario?accion=${encodeURIComponent(n.origen_ref.split(":")[0])}&pestana=fotos`;
  }
  return null;
}

/** Botón chico del pie del menú: idioma, tema, salir. Solo ícono, con nombre. */
const BOTON_PIE =
  "flex h-11 flex-1 items-center justify-center gap-1.5 rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 active:scale-95 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-100 md:h-10";

export default function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const { user: currentUser } = useCurrentUser();
  const [showLangMenu, setShowLangMenu] = useState(false);
  // El número vive en un lugar compartido: la barra de abajo del teléfono también lo muestra.
  const notifCount = useAvisos((s) => s.noLeidos);
  const setNotifCount = useAvisos((s) => s.setNoLeidos);
  const [showNotifMenu, setShowNotifMenu] = useState(false);
  const [notificaciones, setNotificaciones] = useState<Notificacion[] | null>(null);
  const notifWrapRef = useRef<HTMLDivElement>(null);
  const campanitaRef = useRef<HTMLButtonElement>(null);
  const langWrapRef = useRef<HTMLDivElement>(null);

  const hasPerm = (p: string) => hasPermission(currentUser, p);

  // El núcleo de la plataforma es el calendario y las tareas (pedido de Ivan,
  // 12/11/2026: "nuestro core va a ser la calendarización", y todo lo demás
  // "van a pasar a ser herramientas secundarias"). Por eso el menú tiene dos
  // partes: arriba el núcleo, siempre a la vista, y abajo las herramientas,
  // que se pliegan.
  //
  // perm: undefined = visible para cualquier usuario logueado. Cada valor
  // corresponde 1:1 a un permiso realmente exigido por el backend (ver
  // require_permission en las rutas) — si no lo tiene, ni se muestra el link.
  //
  // Las fotos de colocación también van arriba: para un local es lo que le
  // piden ("Fotos para subir", con cuántas le faltan); para quien edita el
  // calendario, el resumen de todas ("Colocación"), solo en un mundo que
  // tiene locales con usuario.
  const elegido = useMundoElegido((st) => st.elegido);
  const mundo = mundoEfectivo(currentUser, elegido);
  const variosMundos = mundosDe(currentUser).length > 1;
  const esLocal = (currentUser?.assigned_locales?.length ?? 0) > 0;
  const puedeEditar = hasPerm("calendario.edit");
  const fotosPendientes = usePendientesDeFotos((s) => s.pendientes) ?? 0;
  const localesDelMundo = useLocalesDelMundo((s) => (mundo ? s.porMundo[mundo.clave] : undefined));
  const nucleo: { href: string; label: string; icon: typeof CalendarDays; perm?: string; numero?: number }[] = [
    ...(esLocal ? [{ href: "/fotos", label: t("sidebar.fotosParaSubir", "Fotos para subir"), icon: Camera, numero: fotosPendientes }] : []),
    { href: "/calendario", label: t("sidebar.calendario"), icon: CalendarDays, perm: "calendario.view" },
    { href: "/mis-tareas", label: t("sidebar.misTareas", "Mis tareas"), icon: ListChecks, perm: "calendario.view" },
    ...((localesDelMundo?.length ?? 0) > 0
      ? [{ href: "/colocacion", label: t("sidebar.colocacion", "Colocación"), icon: Camera, perm: "calendario.edit" }]
      : []),
  ].filter((item) => !item.perm || hasPerm(item.perm));
  // Las herramientas se pliegan solo para quien tiene el núcleo del
  // calendario. Un local (con "Fotos para subir" arriba) las sigue viendo
  // abiertas, como siempre: ahí está "Mi pedido".
  const plegable = hasPerm("calendario.view");

  // El orden de esta lista ES el orden de las herramientas (cada sección sale
  // donde aparece su primer link). Lo fijó Ivan el 23/09/2026: cenefas,
  // validación de RRSS, medios, redexpres, facturación y después el resto.
  const herramientasAll = [
    { href: "/materiales/cenefas",      label: t("sidebar.cenefas"),   icon: Presentation,    section: t("sidebar.materiales"),     perm: "cenefas.view" },
    { href: "/materiales/convertidor",  label: t("sidebar.convertidor"), icon: FileSpreadsheet, section: t("sidebar.materiales"),   perm: "cenefas.view" },
    { href: "/materiales/diccionario",  label: t("sidebar.diccionario"), icon: BookOpen,      section: t("sidebar.materiales"),     perm: "cenefas.diccionario" },
    { href: "/redes-sociales/validacion", label: t("sidebar.validacionRrss"), icon: ScanSearch, section: t("sidebar.redesSociales"), perm: "rrss.view" },
    { href: "/dashboard",               label: t("common.dashboard"),  icon: LayoutDashboard, section: t("sidebar.medios"),         perm: "analytics.view" },
    { href: "/canales",                 label: t("sidebar.analyticsGa4"), icon: Activity,     section: t("sidebar.medios"),         perm: "analytics.view" },
    { href: "/campaigns",               label: t("common.campaigns"),  icon: Megaphone,       section: t("sidebar.medios"),         perm: "analytics.view" },
    { href: "/analytics",               label: t("common.aiAnalysis"), icon: Brain,           section: t("sidebar.medios"),         perm: "ai.triada" },
    { href: "/settings",                label: t("common.connections"),icon: Settings,        section: t("sidebar.medios"),         perm: "connections.view" },
    { href: "/redexpres/planilla",      label: t("sidebar.planillaPedidos"), icon: ClipboardList, section: t("sidebar.redexpres"),  perm: "redexpres.view" },
    // Sin perm: el acceso no es por permiso sino por tener una sucursal
    // asignada (LocalAsignacion) — por eso se filtra acá, no vía hasPerm().
    // Los superadmins también entran (ven un selector de sucursal en la página).
    ...((currentUser?.assigned_locales?.length ?? 0) > 0 || currentUser?.is_superuser
      ? [{ href: "/redexpres/mi-pedido", label: t("sidebar.miPedido"), icon: ClipboardList, section: t("sidebar.redexpres") }]
      : []),
    { href: "/facturacion",             label: t("sidebar.facturacionDashboard"), icon: Receipt, section: t("sidebar.facturacion"), perm: "facturacion.view" },
    { href: "/facturacion/cuentas",     label: t("sidebar.facturacionCuentas"), icon: Landmark, section: t("sidebar.facturacion"),  perm: "facturacion.manage" },
    { href: "/precios",                 label: t("sidebar.buscarPrecios"), icon: Tag,          section: t("sidebar.comercial"),     perm: "precios.search" },
    { href: "/precios/listas",          label: t("sidebar.listasMonitoreo"), icon: Star,       section: t("sidebar.comercial"),     perm: "precios.search" },
    ...(hasPermission(currentUser, "platform.admin")
      ? [{ href: "/admin", label: t("sidebar.administrador"), icon: ShieldCheck, section: t("sidebar.configuracion") }]
      : []),
    { href: "/home",                    label: t("sidebar.asistente", "Don Tino, el asistente"), icon: MessageCircle, section: t("sidebar.guia"), perm: "ai.don_tino" },
    { href: "/ayuda",                   label: t("sidebar.guiaUso"),   icon: HelpCircle,      section: t("sidebar.guia") },
  ];

  // El mundo va primero (se calcula arriba): decide qué herramientas existen.
  // Después el permiso decide cuáles de esas puede usar la persona.
  const nav = herramientasAll.filter((item) =>
    (!item.perm || hasPerm(item.perm)) && (!mundo || rutaEnMundo(item.href, mundo.clave)));

  // Las herramientas arrancan plegadas, salvo que se esté parado en una. Lo
  // que la persona elija se recuerda en este navegador.
  const enHerramienta = nav.some((n) => pathname === n.href || pathname.startsWith(n.href + "/"));
  const [herramientasAbiertas, setHerramientasAbiertas] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const guardado = localStorage.getItem("core-tienda-herramientas");
    return guardado === null ? !plegable : guardado === "1";
  });
  const verHerramientas = herramientasAbiertas || enHerramienta || !plegable;
  function alternarHerramientas() {
    const abiertas = !verHerramientas;
    setHerramientasAbiertas(abiertas);
    localStorage.setItem("core-tienda-herramientas", abiertas ? "1" : "0");
  }


  // Lo de las fotos de colocación: a un local, cuántas le faltan subir (se
  // pregunta al entrar y cada 2 minutos con la pestaña a la vista); a quien
  // edita el calendario, si el mundo tiene locales (una vez por mundo).
  useEffect(() => {
    if (!esLocal) return;
    const contar = () => {
      if (document.visibilityState === "visible") void usePendientesDeFotos.getState().contar();
    };
    contar();
    const intervalo = window.setInterval(contar, 120_000);
    document.addEventListener("visibilitychange", contar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", contar);
    };
  }, [esLocal]);
  const claveMundo = mundo?.clave;
  useEffect(() => {
    if (claveMundo && puedeEditar) useLocalesDelMundo.getState().pedir(claveMundo);
  }, [claveMundo, puedeEditar]);

  // El número de la campanita se pregunta al entrar, cada minuto con la
  // pestaña a la vista y al volver a ella. Antes solo al entrar: una tarea
  // asignada no aparecía hasta recargar la página (pruebas del 15/11/2026).
  useEffect(() => {
    const contar = () => {
      if (document.visibilityState !== "visible") return;
      watchlistApi.notificacionesNoLeidasCount()
        .then(({ data }) => setNotifCount(data.count))
        .catch(() => {});
    };
    contar();
    const intervalo = window.setInterval(contar, 60_000);
    document.addEventListener("visibilitychange", contar);
    window.addEventListener("focus", contar);
    return () => {
      window.clearInterval(intervalo);
      document.removeEventListener("visibilitychange", contar);
      window.removeEventListener("focus", contar);
    };
  }, [setNotifCount]);

  // Cerrar el dropdown de notificaciones al hacer clic fuera, y con Escape
  // (que además devuelve el foco a la campanita, para seguir con el teclado).
  useEffect(() => {
    if (!showNotifMenu) return;
    function handler(e: MouseEvent) {
      if (notifWrapRef.current && !notifWrapRef.current.contains(e.target as Node)) {
        setShowNotifMenu(false);
      }
    }
    function tecla(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setShowNotifMenu(false);
      campanitaRef.current?.focus();
    }
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", tecla);
    };
  }, [showNotifMenu]);

  // El de idioma también se cierra al tocar afuera o con Escape.
  useEffect(() => {
    if (!showLangMenu) return;
    function handler(e: MouseEvent) {
      if (langWrapRef.current && !langWrapRef.current.contains(e.target as Node)) setShowLangMenu(false);
    }
    function tecla(e: KeyboardEvent) { if (e.key === "Escape") setShowLangMenu(false); }
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", tecla);
    };
  }, [showLangMenu]);

  // En el teléfono el menú es un cajón encima de la página: Escape lo cierra
  // (si no hay un desplegable abierto, que se cierra primero).
  useEffect(() => {
    if (!isOpen) return;
    function tecla(e: KeyboardEvent) {
      if (e.key === "Escape" && !showNotifMenu && !showLangMenu) onClose?.();
    }
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [isOpen, onClose, showNotifMenu, showLangMenu]);

  async function abrirNotificaciones() {
    const yaAbierto = showNotifMenu;
    setShowNotifMenu((v) => !v);
    if (yaAbierto) return;
    try {
      const { data } = await watchlistApi.notificaciones();
      setNotificaciones(data);
    } catch {
      setNotificaciones([]);
    }
  }

  // La barra de abajo del teléfono pide abrir la lista (el menú ya se abrió
  // desde el layout): se escucha el pedido y se abre con lo último.
  useEffect(() => useAvisos.subscribe((ahora, antes) => {
    if (ahora.pedidoDeAbrir === antes.pedidoDeAbrir) return;
    setShowNotifMenu(true);
    watchlistApi.notificaciones()
      .then(({ data }) => setNotificaciones(data))
      .catch(() => setNotificaciones([]));
  }), []);

  async function marcarTodasLeidas() {
    try {
      await watchlistApi.marcarTodasLeidas();
      setNotifCount(0);
      setNotificaciones((prev) => prev?.map((n) => ({ ...n, leida: true })) ?? null);
    } catch {
      toast.error(t("sidebar.notificacionesError"));
    }
  }

  // Marca una sola notificación como leída, sin navegar — cubre "leer una por
  // una" como acción independiente del click que navega a la sección.
  async function marcarUnaLeida(n: Notificacion, e?: ReactMouseEvent) {
    e?.stopPropagation();
    if (n.leida) return;
    setNotificaciones((prev) => prev?.map((x) => (x.id === n.id ? { ...x, leida: true } : x)) ?? null);
    setNotifCount((c) => Math.max(0, c - 1));
    try {
      await watchlistApi.marcarLeida(n.id);
    } catch {
      // no revertimos el estado optimista por un fallo de red puntual — la
      // próxima carga de la lista se resincroniza sola
    }
  }

  function irANotificacion(n: Notificacion) {
    marcarUnaLeida(n);
    const destino = resolverDestino(n);
    setShowNotifMenu(false);
    // En el teléfono el menú es un cajón: si no se cierra, queda abierto
    // debajo de la ficha que abre el aviso y aparece al cerrarla.
    if (destino) onClose?.();
    if (destino) router.push(destino);
  }

  /** Con el teclado, Enter o espacio sobre un aviso hacen lo mismo que el clic. */
  function teclaEnNotificacion(e: ReactKeyboardEvent, n: Notificacion) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      irANotificacion(n);
    }
  }

  // Close sidebar on nav in mobile
  function handleNavClick() {
    if (onClose) onClose();
  }

  const { theme, toggle: toggleTheme } = useTheme();
  const currentLang = LANGUAGES.find((l) => l.code === i18n.language) ?? LANGUAGES[0];
  const CurrentFlag = FLAG_ICONS[currentLang.country];
  const iniciales = (currentUser?.full_name ?? "")
    .split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";

  return (
    <>
      {/* Mobile backdrop: aparece y se va con un fundido, no de golpe */}
      <div
        className={clsx(
          "velo z-40 transition-opacity duration-300 md:hidden",
          isOpen ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
        aria-hidden
      />

      <aside className={clsx(
        // Claro en tema claro (pedido de Ivan, 12/11/2026: "necesitamos
        // aclarar. No oscurecer más"); el navy de antes queda para el oscuro.
        "w-72 md:w-64 flex flex-col shrink-0 z-50 border-r border-slate-200 bg-white dark:border-white/5 dark:bg-navy-900",
        // Desktop: always visible, relative positioning
        "md:relative md:translate-x-0 md:min-h-screen md:visible",
        // Mobile: fixed overlay, slides in/out. Cerrado queda invisible, así
        // el teclado no recorre links que no se ven.
        "fixed inset-y-0 left-0",
        isOpen ? "hoja-abierta translate-x-0 shadow-panel md:shadow-none" : "hoja-cerrada -translate-x-full md:translate-x-0"
      )}>
        {/* Logo. La X del teléfono va al lado, no adentro del link. */}
        <div className="flex items-center gap-1 px-3 pb-3 pt-4 md:pb-4 md:pt-5">
          <Link href={inicioDe(currentUser)} onClick={handleNavClick} className="group flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2 py-1">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shrink-0 shadow-sm shadow-brand-600/30 transition-transform group-hover:scale-105 group-active:scale-95">
              <CalendarDays size={18} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-slate-900 dark:text-white font-bold text-[15px] leading-none">{MARCA}</p>
              <p className="text-slate-500 dark:text-slate-400 text-xs mt-1 truncate">{MARCA_BAJADA}</p>
            </div>
          </Link>
          {/* Close button — mobile only */}
          <button
            type="button"
            onClick={onClose}
            aria-label={t("sidebar.cerrarMenu", "Cerrar menú")}
            className="boton-icono md:hidden"
          >
            <X size={20} />
          </button>
        </div>

        {/* En qué mundo se está. Con más de uno, es también el botón para cambiar. */}
        {mundo && (
          variosMundos ? (
            <Link
              href="/mundos"
              onClick={handleNavClick}
              title={t("sidebar.cambiarMundo", "Cambiar de mundo")}
              className="group relative mx-3 mb-3 flex items-center gap-3 overflow-hidden rounded-xl border border-slate-200 bg-white py-2.5 pl-4 pr-3 shadow-card transition hover:border-slate-300 hover:shadow-card-hover active:scale-[.99] dark:border-white/10 dark:bg-white/[.04] dark:hover:border-white/20"
            >
              <span className="absolute inset-y-0 left-0 w-1" style={{ backgroundColor: mundo.color }} aria-hidden />
              <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-slate-100 dark:ring-white/5" style={{ backgroundColor: mundo.color }} />
              <span className="min-w-0 flex-1">
                <span className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{t("sidebar.mundo", "Mundo")}</span>
                <span className="block truncate text-sm font-bold text-slate-900 dark:text-slate-100">{mundo.nombre}</span>
              </span>
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition group-hover:bg-slate-100 group-hover:text-slate-700 dark:group-hover:bg-white/10 dark:group-hover:text-slate-200">
                <ArrowLeftRight size={15} />
              </span>
            </Link>
          ) : (
            <div className="relative mx-3 mb-3 flex items-center gap-3 overflow-hidden rounded-xl bg-slate-50 py-2.5 pl-4 pr-3 dark:bg-white/5">
              <span className="absolute inset-y-0 left-0 w-1" style={{ backgroundColor: mundo.color }} aria-hidden />
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: mundo.color }} />
              <span className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">{mundo.nombre}</span>
            </div>
          )
        )}

        {/* Main nav */}
        <nav className="px-3 flex-1 overflow-y-auto pb-2" aria-label={MARCA}>
          {/* El núcleo: calendario y tareas */}
          <div className="space-y-1 pt-1">
            {nucleo.map(({ href, label, icon: Icon, numero }) => {
              const active = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link key={href} href={href} onClick={handleNavClick}
                  aria-current={active ? "page" : undefined}
                  className={clsx(
                    "group flex items-center gap-3 px-3 py-3 rounded-xl text-[15px] font-semibold transition-all duration-150 active:scale-[.98]",
                    active
                      ? "bg-brand-600 text-white shadow-md shadow-brand-600/25"
                      : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
                  )}>
                  <Icon size={19} className={active ? "text-white" : "text-brand-600 dark:text-brand-400"} />
                  <span className="flex-1 truncate">{label}</span>
                  {!!numero && (
                    <span className={clsx(
                      "flex h-6 min-w-[24px] items-center justify-center rounded-full px-1.5 text-xs font-bold tabular-nums",
                      active ? "bg-white/25 text-white" : "bg-rose-500 text-white"
                    )}>
                      {numero > 9 ? "9+" : numero}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>

          {/* Las herramientas: todo lo demás, plegable */}
          {nav.length > 0 && (
            <>
              {plegable && (
                <button
                  type="button"
                  onClick={alternarHerramientas}
                  aria-expanded={verHerramientas}
                  className="mt-4 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-200"
                >
                  <Wrench size={14} />
                  <span className="flex-1 text-left">{t("sidebar.herramientas", "Herramientas")}</span>
                  <ChevronDown size={15} className={clsx("transition-transform duration-200", verHerramientas ? "" : "-rotate-90")} />
                </button>
              )}
              {verHerramientas && (
                <div className="space-y-0.5 animate-fade-in">
                  {nav.map(({ href, label, icon: Icon, section }, i) => {
                    const active = pathname === href ||
                      (pathname.startsWith(href + "/") && !nav.some(n => n.href !== href && pathname.startsWith(n.href)));
                    const prevSection = i > 0 ? nav[i - 1].section : undefined;
                    const showLabel = section !== prevSection;
                    return (
                      <div key={href}>
                        {showLabel && (
                          <p className="px-3 pt-3 pb-1 text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                            {section}
                          </p>
                        )}
                        <Link href={href} onClick={handleNavClick}
                          aria-current={active ? "page" : undefined}
                          className={clsx(
                            "group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150",
                            active
                              ? "bg-brand-50 text-brand-700 dark:bg-brand-600 dark:text-white"
                              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-200"
                          )}>
                          <Icon size={16} className={active ? "text-brand-600 dark:text-white" : "text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300"} />
                          <span className="flex-1 truncate">{label}</span>
                          {active && <ChevronRight size={14} className="text-brand-400 dark:text-white/60 shrink-0" />}
                        </Link>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </nav>

        {/* Perfil + notificaciones */}
        <div className="border-t border-slate-200 px-3 pt-3 dark:border-white/5">
          <div ref={notifWrapRef} className="relative flex items-center gap-1.5">
            <Link
              href="/perfil"
              onClick={handleNavClick}
              className="group flex items-center gap-2.5 flex-1 min-w-0 px-2 py-1.5 rounded-xl
                         text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-slate-100 transition-all duration-150"
            >
              <span className="w-8 h-8 rounded-full bg-brand-100 text-brand-700 dark:bg-brand-600/30 dark:text-brand-200 flex items-center justify-center text-[11px] font-bold shrink-0 dark:group-hover:bg-brand-600/50">
                {iniciales}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-semibold">{currentUser?.full_name ?? t("sidebar.miPerfil")}</span>
                <span className="block truncate text-[11px] text-slate-500 dark:text-slate-400">{t("sidebar.miPerfil")}</span>
              </span>
            </Link>
            <button
              ref={campanitaRef}
              type="button"
              onClick={abrirNotificaciones}
              aria-label={t("sidebar.notificaciones")}
              title={t("sidebar.notificaciones")}
              aria-expanded={showNotifMenu}
              aria-haspopup="dialog"
              className={clsx(
                "relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-all duration-150 active:scale-95 md:h-10 md:w-10",
                showNotifMenu
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-200"
              )}
            >
              <Bell size={18} />
              {notifCount > 0 && (
                <span className="absolute right-1 top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white ring-2 ring-white dark:ring-navy-900">
                  {notifCount > 9 ? "9+" : notifCount}
                </span>
              )}
            </button>

            {showNotifMenu && (
              <div
                role="dialog"
                aria-label={t("sidebar.notificaciones")}
                className={clsx(
                  "z-50 flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-pop dark:border-white/10 dark:bg-slate-900",
                  // En el teléfono es una hoja abajo de todo, ancha; en la
                  // notebook sale de la campanita hacia arriba.
                  "fixed inset-x-3 bottom-3 max-h-[75dvh] animate-sheet-up",
                  "md:absolute md:inset-x-auto md:bottom-full md:left-0 md:mb-2 md:max-h-[min(32rem,calc(100vh-6rem))] md:w-[22rem] md:origin-bottom-left md:animate-scale-in"
                )}
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-slate-100 px-4 py-3 dark:border-white/5">
                  <p className="text-sm font-bold text-slate-900 dark:text-slate-100">{t("sidebar.notificaciones")}</p>
                  {notifCount > 0 && (
                    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-bold text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
                      {notifCount}
                    </span>
                  )}
                  {notifCount > 0 && (
                    <button
                      type="button"
                      onClick={marcarTodasLeidas}
                      className="-mr-2 ml-auto whitespace-nowrap rounded-lg px-2 py-1.5 text-xs font-semibold text-brand-600 transition hover:bg-brand-50 hover:text-brand-700 dark:text-brand-300 dark:hover:bg-brand-500/10"
                    >
                      {t("sidebar.marcarTodasLeidas")}
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
                      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-white/5 dark:text-slate-500">
                        <BellOff size={18} />
                      </span>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">{t("sidebar.sinNotificaciones")}</p>
                    </div>
                  )}
                  {notificaciones?.map((n) => {
                    const destino = resolverDestino(n);
                    return (
                      <div
                        key={n.id}
                        role={destino ? "button" : undefined}
                        tabIndex={destino ? 0 : undefined}
                        onClick={() => irANotificacion(n)}
                        onKeyDown={(e) => teclaEnNotificacion(e, n)}
                        className={clsx(
                          "relative flex items-start gap-3 border-b border-slate-100 px-4 py-3 transition-colors last:border-0 dark:border-white/5",
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
                          {n.created_at && (
                            <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                              {cuandoFue(n.created_at, i18n.language)}
                            </p>
                          )}
                        </div>
                        {!n.leida ? (
                          <button
                            type="button"
                            onClick={(e) => marcarUnaLeida(n, e)}
                            title={t("sidebar.marcarLeida")}
                            aria-label={t("sidebar.marcarLeida")}
                            className="group/leida -mr-2 -mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition hover:bg-brand-100 dark:hover:bg-brand-500/20"
                          >
                            <span className="h-3.5 w-3.5 rounded-full border-2 border-brand-400 transition group-hover/leida:bg-brand-400" />
                          </button>
                        ) : (
                          <Check size={14} className="mt-0.5 shrink-0 text-slate-300 dark:text-slate-600" aria-hidden />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Idioma, tema y salir: una fila de botones con ícono */}
        <div className="flex items-center gap-1 px-3 pb-4 pt-2 md:pb-5">
          <div ref={langWrapRef} className="relative flex flex-1">
            <button
              type="button"
              onClick={() => setShowLangMenu((v) => !v)}
              aria-label={`${t("common.language")}: ${currentLang.label}`}
              title={`${t("common.language")}: ${currentLang.label}`}
              aria-expanded={showLangMenu}
              className={BOTON_PIE}
            >
              <Globe size={16} className="shrink-0" />
              <CurrentFlag className="w-4 h-auto rounded-[2px] shrink-0" />
            </button>
            {showLangMenu && (
              <div className="absolute bottom-full left-0 mb-2 w-44 origin-bottom-left animate-scale-in overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-pop dark:border-white/10 dark:bg-slate-900 z-50">
                {LANGUAGES.map((lang) => {
                  const Flag = FLAG_ICONS[lang.country];
                  const actual = i18n.language === lang.code;
                  return (
                  <button
                    key={lang.code}
                    type="button"
                    onClick={() => { setLanguage(lang.code as LangCode); setShowLangMenu(false); }}
                    aria-current={actual ? "true" : undefined}
                    className={clsx(
                      "w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors",
                      actual
                        ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-slate-100"
                    )}>
                    <Flag className="w-4 h-auto rounded-[2px] shrink-0" />
                    <span className="flex-1 text-left text-xs font-medium">{lang.label}</span>
                    {actual && <Check size={14} aria-hidden />}
                  </button>
                  );
                })}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={toggleTheme}
            className={BOTON_PIE}
            aria-label={theme === "dark" ? t("sidebar.toggleToLight") : t("sidebar.toggleToDark")}
            title={theme === "dark" ? t("sidebar.lightMode") : t("sidebar.darkMode")}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>

          <button
            type="button"
            onClick={() => authApi.logout().finally(() => { olvidarDatosDelNavegador(); window.location.href = "/login"; })}
            aria-label={t("common.logout")}
            title={t("common.logout")}
            className={clsx(BOTON_PIE, "hover:!bg-rose-50 hover:!text-rose-600 dark:hover:!bg-rose-500/10 dark:hover:!text-rose-300")}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
    </>
  );
}
