"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Brain, Settings, LogOut,
  ChevronRight, Presentation, Globe, ShieldCheck, HelpCircle, X, Tag,
  Sun, Moon, ClipboardList, Star, Activity, Check,
  FileSpreadsheet, BookOpen, Receipt, Landmark, ScanSearch, CalendarDays,
  ListChecks, Wrench, ChevronDown, ArrowLeftRight, MessageCircle, Camera, Layers, PanelLeftClose, PanelLeftOpen, Crown,
} from "lucide-react";
import { clsx } from "clsx";
import { ES, GB, BR } from "country-flag-icons/react/3x2";
import { authApi, watchlistApi } from "@/lib/api";
import { useTranslation } from "react-i18next";
import { LANGUAGES, setLanguage, type LangCode } from "@/lib/i18n";
import { useTheme } from "@/hooks/useTheme";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import { esExterno } from "@/lib/externos";
import { veCalendario } from "@/lib/alcance";
import { MARCA, MARCA_BAJADA, inicioDe, mundoEfectivo, mundosDe, rutaEnMundo, useMundoElegido } from "@/lib/mundos";
import { useCalendario } from "@/lib/calendario/store";
import { useAvisos } from "@/store/avisos";
import { useMenuLateral } from "@/store/menuLateral";
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

/** Botón chico del pie del menú: idioma, tema, salir. Solo ícono, con nombre. */
const BOTON_PIE =
  "flex h-11 flex-1 items-center justify-center gap-1.5 rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 active:scale-95 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-100 md:h-10";

export default function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const { user: currentUser } = useCurrentUser();
  const [showLangMenu, setShowLangMenu] = useState(false);
  // En pantallas grandes se puede ocultar (17/11/2026); lo vuelve a mostrar
  // el botón de la franja que queda en su lugar (ver el layout del dashboard).
  const menuOculto = useMenuLateral((s) => s.oculto);
  const ocultarMenu = useMenuLateral((s) => s.ocultar);
  const mostrarMenu = useMenuLateral((s) => s.mostrar);
  // Se desliza (17/11/2026: "que deslice despacio, ahí es como que oculta y
  // muestra de una"): el ancho va de 256 a 48 px y el contenido se desvanece.
  // Mientras se achica, y hasta que termina de abrirse, recorta lo que
  // sobresale; abierto no recorta, porque la lista de avisos se abre por
  // encima de la página y es más ancha que el menú.
  const [recortar, setRecortar] = useState(menuOculto);
  // Ocultar es solo de pantallas grandes: en una ventana angosta el menú es
  // la hoja de siempre y su contenido se tiene que poder usar aunque haya
  // quedado "oculto" de antes.
  const [esAncha, setEsAncha] = useState(() => window.matchMedia("(min-width: 768px)").matches);
  useEffect(() => {
    const consulta = window.matchMedia("(min-width: 768px)");
    const alCambiar = () => setEsAncha(consulta.matches);
    consulta.addEventListener("change", alCambiar);
    return () => consulta.removeEventListener("change", alCambiar);
  }, []);
  // Oculto, el contenido no se recorre con el teclado ni lo lee un lector de
  // pantalla. `inert` va a mano: React 18 no conoce el atributo y lo tiraba.
  const contenidoRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = contenidoRef.current;
    if (!el) return;
    if (menuOculto && esAncha) el.setAttribute("inert", "");
    else el.removeAttribute("inert");
  }, [menuOculto, esAncha]);
  function ocultarDeslizando() {
    setRecortar(true);
    ocultarMenu();
  }
  // El número vive en un lugar compartido: lo muestran la campanita (arriba a
  // la derecha, ver Campanita.tsx) y la barra de abajo del teléfono.
  const setNotifCount = useAvisos((s) => s.setNoLeidos);
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
  // Una cuenta externa (la agencia, lib/externos.ts) tiene un menú chiquito
  // (16/11/2026): su tablero y, si un admin le habilitó el calendario (su
  // alcance, lib/alcance.ts), el calendario. Nada de las herramientas
  // internas: el servidor igual se las niega.
  const externo = esExterno(currentUser);
  const conCalendario = veCalendario(currentUser);
  // En el mundo Redexpres la Planilla de pedidos es el trabajo de todos los
  // días del equipo: va arriba, con el calendario, y sale de Herramientas
  // para no estar dos veces (H-021). En los otros mundos queda donde estaba.
  const planillaArriba = !externo && mundo?.clave === "redexpres" && hasPerm("redexpres.view");
  const nucleo: { href: string; label: string; icon: typeof CalendarDays; perm?: string; numero?: number }[] = externo ? [
    { href: "/entregas", label: t("sidebar.miTablero", "Mi tablero"), icon: Layers, perm: "calendario.view" },
    ...(conCalendario ? [{ href: "/calendario", label: t("sidebar.calendario"), icon: CalendarDays, perm: "calendario.view" }] : []),
    // La guía de uso, con lo suyo (25/11/2026: la manda el servidor recortada).
    { href: "/ayuda", label: t("sidebar.guiaUso"), icon: HelpCircle, perm: "calendario.view" },
  ].filter((item) => hasPerm(item.perm)) : [
    ...(esLocal ? [{ href: "/fotos", label: t("sidebar.fotosParaSubir", "Fotos para subir"), icon: Camera, numero: fotosPendientes }] : []),
    // Quien no ve el calendario (su alcance es "No lo ve") no lo tiene en el
    // menú. Sus tareas sí, siempre: lo que le asignan le tiene que llegar.
    ...(conCalendario ? [{ href: "/calendario", label: t("sidebar.calendario"), icon: CalendarDays, perm: "calendario.view" }] : []),
    { href: "/mis-tareas", label: t("sidebar.misTareas", "Mis tareas"), icon: ListChecks, perm: "calendario.view" },
    // Las piezas con la agencia, como un tablero de Trello (16/11/2026).
    { href: "/entregas", label: t("sidebar.tablero", "Tablero"), icon: Layers, perm: "calendario.view" },
    // Colocación muestra el nombre y las fechas de las acciones: es calendario.
    ...(conCalendario && (localesDelMundo?.length ?? 0) > 0
      ? [{ href: "/colocacion", label: t("sidebar.colocacion", "Colocación"), icon: Camera, perm: "calendario.edit" }]
      : []),
    ...(planillaArriba
      ? [{ href: "/redexpres/planilla", label: t("sidebar.planillaPedidos"), icon: ClipboardList, perm: "redexpres.view" }]
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
    ...(!planillaArriba
      ? [{ href: "/redexpres/planilla", label: t("sidebar.planillaPedidos"), icon: ClipboardList, section: t("sidebar.redexpres"), perm: "redexpres.view" }]
      : []),
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
    // Datos confidenciales: solo con el permiso propio, que no trae ningún rol (0091).
    { href: "/clientes-vip",            label: t("sidebar.clientesVip", "Clientes VIP"), icon: Crown, section: t("sidebar.comercial"), perm: "clientes_vip.view" },
    ...(hasPermission(currentUser, "platform.admin")
      ? [{ href: "/admin", label: t("sidebar.administrador"), icon: ShieldCheck, section: t("sidebar.configuracion") }]
      : []),
    { href: "/home",                    label: t("sidebar.asistente", "Don Tino, el asistente"), icon: MessageCircle, section: t("sidebar.guia"), perm: "ai.don_tino" },
    { href: "/ayuda",                   label: t("sidebar.guiaUso"),   icon: HelpCircle,      section: t("sidebar.guia") },
  ];

  // El mundo va primero (se calcula arriba): decide qué herramientas existen.
  // Después el permiso decide cuáles de esas puede usar la persona.
  const nav = externo ? [] : herramientasAll.filter((item) =>
    (!item.perm || hasPerm(item.perm)) && (!mundo || rutaEnMundo(item.href, mundo.clave)));

  // Las herramientas arrancan plegadas, salvo que se esté parado en una. Lo
  // que la persona elija se recuerda en este navegador.
  const enHerramienta = nav.some((n) => pathname === n.href || pathname.startsWith(n.href + "/"));
  const [herramientasAbiertas, setHerramientasAbiertas] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const guardado = localStorage.getItem("core-tienda-herramientas");
    return guardado === null ? !plegable : guardado === "1";
  });
  // Parado en una herramienta arrancan abiertas (se ve dónde se está), pero
  // el botón igual las cierra (Ivan, 24/11/2026: "el botón Herramientas no
  // cierra, presionarlo no sirve de nada"; antes quedaban abiertas a la
  // fuerza). Cerrarlas vale para esa página: en otra herramienta vuelven a
  // arrancar abiertas.
  const [cerradasEn, setCerradasEn] = useState<string | null>(null);
  const verHerramientas = !plegable || (enHerramienta ? cerradasEn !== pathname : herramientasAbiertas);
  function alternarHerramientas() {
    const abiertas = !verHerramientas;
    if (enHerramienta) setCerradasEn(abiertas ? null : pathname);
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
      if (e.key === "Escape" && !showLangMenu) onClose?.();
    }
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [isOpen, onClose, showLangMenu]);

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
        "w-72 flex flex-col shrink-0 z-50 border-r border-slate-300 bg-white dark:border-white/5 dark:bg-navy-900",
        // Desktop: se desliza entre abierto (256 px) y la franja (48 px).
        menuOculto ? "md:w-12" : "md:w-64",
        "md:transition-[width] md:duration-500 md:ease-[cubic-bezier(.32,.72,0,1)] motion-reduce:transition-none",
        recortar && "md:overflow-hidden",
        // Desktop: always visible, relative positioning
        "md:relative md:translate-x-0 md:min-h-screen md:visible",
        // Mobile: fixed overlay, slides in/out. Cerrado queda invisible, así
        // el teclado no recorre links que no se ven.
        "fixed inset-y-0 left-0",
        isOpen ? "hoja-abierta translate-x-0 shadow-panel md:shadow-none" : "hoja-cerrada -translate-x-full md:translate-x-0",
      )}
        onTransitionEnd={(e) => {
          if (e.target === e.currentTarget && e.propertyName === "width" && !menuOculto) setRecortar(false);
        }}
      >
        {/* Oculto (pantallas grandes): el botón para volver a mostrarlo, que
            aparece cuando el menú ya se está cerrando. */}
        <button
          type="button"
          onClick={mostrarMenu}
          aria-label={t("sidebar.mostrarMenu", "Mostrar menú")}
          title={t("sidebar.mostrarMenu", "Mostrar menú")}
          tabIndex={menuOculto ? 0 : -1}
          aria-hidden={!menuOculto}
          className={clsx(
            "boton-icono absolute left-1 top-5 z-10 hidden md:flex",
            "transition-opacity duration-300 motion-reduce:transition-none",
            menuOculto ? "opacity-100 delay-200" : "pointer-events-none opacity-0"
          )}
        >
          <PanelLeftOpen size={18} />
        </button>
        {/* El contenido, con su ancho fijo: al achicarse el menú se corre y se
            desvanece en vez de aplastarse. Oculto, el teclado no lo recorre. */}
        <div
          ref={contenidoRef}
          className={clsx(
            "flex min-h-0 flex-1 flex-col md:w-64 md:shrink-0",
            "md:transition-[opacity,transform] md:duration-300 motion-reduce:transition-none",
            menuOculto ? "md:pointer-events-none md:-translate-x-6 md:opacity-0" : "md:translate-x-0 md:opacity-100 md:delay-150"
          )}
        >
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
          {/* Ocultar el menú — pantallas grandes */}
          <button
            type="button"
            onClick={ocultarDeslizando}
            aria-label={t("sidebar.ocultarMenu", "Ocultar menú")}
            title={t("sidebar.ocultarMenu", "Ocultar menú")}
            className="boton-icono hidden md:flex"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        {/* En qué mundo se está. Con más de uno, es también el botón para cambiar. */}
        {mundo && (
          variosMundos ? (
            <Link
              href="/mundos"
              onClick={handleNavClick}
              title={t("sidebar.cambiarMundo", "Cambiar de mundo")}
              className="group relative mx-3 mb-3 flex items-center gap-3 overflow-hidden rounded-xl border border-slate-300 bg-white py-2.5 pl-4 pr-3 shadow-card transition hover:border-slate-300 hover:shadow-card-hover active:scale-[.99] dark:border-white/10 dark:bg-white/[.04] dark:hover:border-white/20"
            >
              <span className="absolute inset-y-0 left-0 w-1" style={{ backgroundColor: mundo.color }} aria-hidden />
              <span className="h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-slate-100 dark:ring-white/5" style={{ backgroundColor: mundo.color }} />
              <span className="min-w-0 flex-1">
                <span className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{t("sidebar.mundo", "Mundo")}</span>
                <span className="block truncate text-sm font-bold text-slate-900 dark:text-slate-100">{mundo.nombre}</span>
              </span>
              {/* Con texto y no solo el ícono (18/11/2026): Ivan buscaba cómo
                  volver a la selección de mundos. */}
              <span className="flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 text-xs font-semibold text-slate-600 transition group-hover:bg-brand-50 group-hover:text-brand-700 dark:bg-white/10 dark:text-slate-300 dark:group-hover:bg-brand-500/15 dark:group-hover:text-brand-200">
                <ArrowLeftRight size={14} />
                {t("sidebar.cambiar", "Cambiar")}
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
                          <p className="px-3 pt-3 pb-1 text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-widest">
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
                          <Icon size={16} className={active ? "text-brand-600 dark:text-white" : "text-slate-500 group-hover:text-slate-600 dark:text-slate-400 dark:group-hover:text-slate-300"} />
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

        {/* Perfil (la campanita está arriba a la derecha desde el 18/11/2026) */}
        <div className="border-t border-slate-300 px-3 pt-3 dark:border-white/5">
          <div className="relative flex items-center gap-1.5">
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
                <span className="block truncate text-[11px] text-slate-500 dark:text-slate-400">
                  {externo && currentUser?.empresa ? currentUser.empresa : t("sidebar.miPerfil")}
                </span>
              </span>
            </Link>
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
              <div className="absolute bottom-full left-0 mb-2 w-44 origin-bottom-left animate-scale-in overflow-hidden rounded-xl border border-slate-300 bg-white p-1 shadow-pop dark:border-white/10 dark:bg-slate-900 z-50">
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
        </div>
      </aside>
    </>
  );
}
