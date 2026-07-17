"use client";
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Brain, Settings, LogOut,
  BarChart3, ChevronRight, Presentation, Globe, ShieldCheck, HelpCircle, X, Tag,
  Sun, Moon, ClipboardList, Bell, Star, Activity, TrendingUp, TrendingDown, AlertTriangle, Check,
  FileSpreadsheet, BookOpen,
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

// Los flags de country-flag-icons devuelven emoji de bandera regional, que
// Windows no renderiza como imagen (muestra el codigo de pais en texto) —
// estos SVG se ven iguales en todos los sistemas operativos.
const FLAG_ICONS: Record<string, typeof ES> = { ES, GB, BR };

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

// Subida de precio = malo para quien monitorea (rojo); bajada = bueno (verde).
// Alertas de campaña ("Medios") comparten un solo ícono de advertencia — la
// distinción de causa ya está en el mensaje mismo. El fondo de color (chip)
// usa el mismo lenguaje "*-500 a opacidad moderada" que el resto de la app
// para que el color se lea bien sobre el navy oscuro fijo del sidebar.
function notifIcon(tipo: string) {
  switch (tipo) {
    case "precio_baja":
      return (
        <span className="w-6 h-6 rounded-full bg-emerald-100 dark:bg-emerald-500/15 flex items-center justify-center shrink-0">
          <TrendingDown size={13} className="text-emerald-600 dark:text-emerald-400" />
        </span>
      );
    case "precio_sube":
      return (
        <span className="w-6 h-6 rounded-full bg-red-100 dark:bg-red-500/15 flex items-center justify-center shrink-0">
          <TrendingUp size={13} className="text-red-600 dark:text-red-400" />
        </span>
      );
    case "roas_baja":
    case "gasto_sube":
    case "conversiones_baja":
    case "sin_conversiones":
      return (
        <span className="w-6 h-6 rounded-full bg-amber-100 dark:bg-amber-500/15 flex items-center justify-center shrink-0">
          <AlertTriangle size={13} className="text-amber-600 dark:text-amber-400" />
        </span>
      );
    default:
      return (
        <span className="w-6 h-6 rounded-full bg-slate-100 dark:bg-slate-500/15 flex items-center justify-center shrink-0">
          <Bell size={13} className="text-slate-500 dark:text-slate-400" />
        </span>
      );
  }
}

// A dónde navegar al clickear una notificación — se deriva de los campos que
// ya existen (watchlist_item_id, origen_tipo), sin necesidad de un campo
// nuevo. Cualquier tipo futuro no mapeado no navega, en vez de adivinar.
function resolverDestino(n: Notificacion): string | null {
  if (n.watchlist_item_id != null) return "/precios/listas";
  if (n.origen_tipo === "campaign_alert") return "/campaigns";
  return null;
}

export default function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const { user: currentUser } = useCurrentUser();
  const [showLangMenu, setShowLangMenu] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const [showNotifMenu, setShowNotifMenu] = useState(false);
  const [notificaciones, setNotificaciones] = useState<Notificacion[] | null>(null);
  const notifWrapRef = useRef<HTMLDivElement>(null);

  const hasPerm = (p: string) => hasPermission(currentUser, p);

  // perm: undefined = visible para cualquier usuario logueado.
  // Cada valor corresponde 1:1 a un permiso realmente exigido por el backend
  // (ver require_permission en las rutas) — si no lo tiene, ni se muestra el link.
  const navAll = [
    { href: "/dashboard",               label: t("common.dashboard"),  icon: LayoutDashboard, section: t("sidebar.medios"),         perm: "analytics.view" },
    { href: "/canales",                 label: t("sidebar.analyticsGa4"), icon: Activity,      section: t("sidebar.medios"),         perm: "analytics.view" },
    { href: "/campaigns",               label: t("common.campaigns"),  icon: Megaphone,        section: t("sidebar.medios"),         perm: "analytics.view" },
    { href: "/analytics",               label: t("common.aiAnalysis"), icon: Brain,            section: t("sidebar.medios"),         perm: "ai.use" },
    { href: "/settings",                label: t("common.connections"),icon: Settings,         section: t("sidebar.medios"),         perm: "connections.view" },
    { href: "/materiales/cenefas",    label: t("sidebar.cenefas"),  icon: Presentation, section: t("sidebar.materiales"), perm: "cenefas.view" },
    { href: "/materiales/convertidor", label: t("sidebar.convertidor"), icon: FileSpreadsheet, section: t("sidebar.materiales"), perm: "cenefas.view" },
    { href: "/materiales/diccionario", label: t("sidebar.diccionario"), icon: BookOpen, section: t("sidebar.materiales"), perm: "cenefas.view" },
    { href: "/precios",                 label: t("sidebar.buscarPrecios"), icon: Tag,           section: t("sidebar.comercial"),     perm: "precios.search" },
    { href: "/precios/listas",          label: t("sidebar.listasMonitoreo"), icon: Star,        section: t("sidebar.comercial"),     perm: "precios.search" },
    { href: "/redexpres/planilla", label: t("sidebar.planillaPedidos"), icon: ClipboardList, section: t("sidebar.redexpres"), perm: "redexpres.view" },
    // Sin perm: el acceso no es por permiso sino por tener una sucursal
    // asignada (LocalAsignacion) — por eso se filtra acá, no vía hasPerm().
    // Los superadmins también entran (ven un selector de sucursal en la página).
    ...((currentUser?.assigned_locales?.length ?? 0) > 0 || currentUser?.is_superuser
      ? [{ href: "/redexpres/mi-pedido", label: t("sidebar.miPedido"), icon: ClipboardList, section: t("sidebar.redexpres") }]
      : []),
    ...(currentUser?.is_superuser
      ? [{ href: "/admin", label: t("sidebar.administrador"), icon: ShieldCheck, section: t("sidebar.configuracion") }]
      : []),
    { href: "/ayuda",                   label: t("sidebar.guiaUso"),   icon: HelpCircle,       section: t("sidebar.guia") },
  ];

  const nav = navAll.filter((item) => !item.perm || hasPerm(item.perm));

  useEffect(() => {
    watchlistApi.notificacionesNoLeidasCount()
      .then(({ data }) => setNotifCount(data.count))
      .catch(() => {});
  }, []);

  // Cerrar el dropdown de notificaciones al hacer clic fuera
  useEffect(() => {
    if (!showNotifMenu) return;
    function handler(e: MouseEvent) {
      if (notifWrapRef.current && !notifWrapRef.current.contains(e.target as Node)) {
        setShowNotifMenu(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showNotifMenu]);

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
    if (destino) router.push(destino);
  }

  // Close sidebar on nav in mobile
  function handleNavClick() {
    if (onClose) onClose();
  }

  const { theme, toggle: toggleTheme } = useTheme();
  const tenantLabel = "MKTG Platform";
  const currentLang = LANGUAGES.find((l) => l.code === i18n.language) ?? LANGUAGES[0];
  const CurrentFlag = FLAG_ICONS[currentLang.country];

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={onClose}
        />
      )}

      <aside className={clsx(
        "w-64 bg-navy-900 flex flex-col shrink-0 z-50",
        // Desktop: always visible, relative positioning
        "md:relative md:translate-x-0 md:min-h-screen",
        // Mobile: fixed overlay, slides in/out
        "fixed inset-y-0 left-0 transition-transform duration-300 ease-in-out",
        isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      )}>
        {/* Logo */}
        <Link href="/home" onClick={handleNavClick} className="px-5 pt-6 pb-5 flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-xl bg-brand-500 flex items-center justify-center shrink-0 group-hover:bg-brand-400 transition-colors">
            <BarChart3 size={16} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white font-bold text-sm leading-none">MKTG Platform</p>
            <p className="text-slate-500 text-[11px] mt-0.5 truncate" title={tenantLabel}>
              {tenantLabel}
            </p>
          </div>
          {/* Close button — mobile only */}
          <button
            onClick={(e) => { e.preventDefault(); onClose?.(); }}
            className="md:hidden p-1 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <X size={16} />
          </button>
        </Link>

        <div className="mx-4 h-px bg-white/5 mb-3" />

        {/* Main nav */}
        <nav className="px-3 flex-1 space-y-0.5 overflow-y-auto">
          {nav.map(({ href, label, icon: Icon, section }, i) => {
            const active = pathname === href ||
              (pathname.startsWith(href + "/") && !nav.some(n => n.href !== href && pathname.startsWith(n.href)));
            const prevSection = i > 0 ? nav[i - 1].section : undefined;
            const showLabel = section !== prevSection;
            return (
              <div key={href}>
                {showLabel && (
                  <p className="px-3 pt-4 pb-1.5 text-[10px] font-semibold text-slate-600 uppercase tracking-widest">
                    {section}
                  </p>
                )}
                <Link href={href} onClick={handleNavClick}
                  className={clsx(
                    "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
                    active
                      ? "bg-brand-600 text-white shadow-glow"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  )}>
                  <Icon size={17} className={active ? "text-white" : "text-slate-500 group-hover:text-slate-300"} />
                  <span className="flex-1 truncate">{label}</span>
                  {active && <ChevronRight size={14} className="text-white/60 shrink-0" />}
                </Link>
              </div>
            );
          })}
        </nav>

        <div className="mx-4 h-px bg-white/5 mb-3" />

        {/* Perfil + notificaciones */}
        <div className="px-3 pb-2 flex items-center gap-1.5 relative">
          <Link
            href="/perfil"
            onClick={handleNavClick}
            className="group flex items-center gap-2.5 flex-1 min-w-0 px-3 py-2 rounded-xl
                       text-slate-400 hover:bg-white/5 hover:text-slate-200 transition-all duration-150"
          >
            <div className="w-6 h-6 rounded-full bg-brand-600/30 text-brand-300 flex items-center justify-center text-[11px] font-bold shrink-0 group-hover:bg-brand-600/50">
              {currentUser?.full_name?.charAt(0).toUpperCase() ?? "?"}
            </div>
            <span className="flex-1 min-w-0 truncate text-xs font-medium">
              {currentUser?.full_name ?? t("sidebar.miPerfil")}
            </span>
          </Link>
          <div ref={notifWrapRef} className="contents">
          <button
            onClick={abrirNotificaciones}
            aria-label={t("sidebar.notificaciones")}
            title={t("sidebar.notificaciones")}
            className="relative p-2 rounded-xl text-slate-500 hover:bg-white/5 hover:text-slate-300 transition-all duration-150 shrink-0"
          >
            <Bell size={16} />
            {notifCount > 0 && (
              <span className="absolute top-0.5 right-0.5 min-w-[14px] h-[14px] px-0.5 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center leading-none">
                {notifCount > 9 ? "9+" : notifCount}
              </span>
            )}
          </button>

          {showNotifMenu && (
            <div className="absolute bottom-full left-8 mb-2 w-80 max-w-[calc(100vw-3rem)] bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 rounded-xl shadow-lg z-50 overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 dark:border-white/5">
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{t("sidebar.notificaciones")}</p>
                {notifCount > 0 && (
                  <button onClick={marcarTodasLeidas} className="text-[11px] text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300 font-medium">
                    {t("sidebar.marcarTodasLeidas")}
                  </button>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notificaciones === null && (
                  <p className="text-xs text-slate-500 text-center py-6">{t("common.loading")}</p>
                )}
                {notificaciones?.length === 0 && (
                  <p className="text-xs text-slate-500 text-center py-6">{t("sidebar.sinNotificaciones")}</p>
                )}
                {notificaciones?.map((n) => {
                  const destino = resolverDestino(n);
                  return (
                    <div
                      key={n.id}
                      onClick={() => irANotificacion(n)}
                      className={clsx(
                        "px-5 py-3.5 border-b border-slate-100 dark:border-white/5 last:border-0 flex items-start gap-3 transition-colors",
                        destino ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5" : "cursor-default",
                        !n.leida && "bg-brand-50/60 dark:bg-brand-500/[0.06]"
                      )}
                    >
                      {notifIcon(n.tipo)}
                      <div className="min-w-0 flex-1">
                        <p className={clsx("text-xs leading-snug", n.leida ? "text-slate-500 dark:text-slate-400" : "text-slate-800 dark:text-slate-200")}>
                          {n.mensaje}
                        </p>
                        {n.created_at && (
                          <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1.5">
                            {new Date(n.created_at).toLocaleDateString(i18n.language, { day: "2-digit", month: "2-digit", year: "numeric" })}
                          </p>
                        )}
                      </div>
                      {!n.leida ? (
                        <button
                          onClick={(e) => marcarUnaLeida(n, e)}
                          title={t("sidebar.marcarLeida")}
                          className="shrink-0 mt-0.5 w-4 h-4 rounded-full border border-brand-400/60 hover:bg-brand-500/20 hover:border-brand-400 transition-colors"
                        />
                      ) : (
                        <Check size={13} className="shrink-0 mt-0.5 text-slate-400 dark:text-slate-600" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          </div>
        </div>

        {/* Language selector */}
        <div className="px-3 pb-2 relative">
          <button
            onClick={() => setShowLangMenu((v) => !v)}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-xl text-sm text-slate-500
                       hover:bg-white/5 hover:text-slate-300 transition-all duration-150">
            <Globe size={15} className="shrink-0" />
            <span className="flex-1 flex items-center gap-1.5 text-left text-xs">
              <CurrentFlag className="w-4 h-auto rounded-[2px] shrink-0" />
              {currentLang.label}
            </span>
          </button>
          {showLangMenu && (
            <div className="absolute bottom-full left-3 right-3 mb-1 bg-slate-800 border border-white/10 rounded-xl overflow-hidden shadow-lg z-50">
              {LANGUAGES.map((lang) => {
                const Flag = FLAG_ICONS[lang.country];
                return (
                <button
                  key={lang.code}
                  onClick={() => { setLanguage(lang.code as LangCode); setShowLangMenu(false); }}
                  className={clsx(
                    "w-full flex items-center gap-2.5 px-3 py-2.5 text-sm transition-colors",
                    i18n.language === lang.code
                      ? "bg-brand-600 text-white"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  )}>
                  <Flag className="w-4 h-auto rounded-[2px] shrink-0" />
                  <span className="text-xs font-medium">{lang.label}</span>
                </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Theme toggle */}
        <div className="px-3 pb-1">
          <button
            onClick={toggleTheme}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm text-slate-500
                       hover:bg-white/5 hover:text-slate-300 transition-all duration-150"
            aria-label={theme === "dark" ? t("sidebar.toggleToLight") : t("sidebar.toggleToDark")}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            {theme === "dark" ? t("sidebar.lightMode") : t("sidebar.darkMode")}
          </button>
        </div>

        {/* Logout */}
        <div className="px-3 pb-5">
          <button
            onClick={() => authApi.logout().finally(() => { window.location.href = "/login"; })}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm text-slate-500
                       hover:bg-white/5 hover:text-slate-300 transition-all duration-150">
            <LogOut size={16} />
            {t("common.logout")}
          </button>
        </div>
      </aside>
    </>
  );
}
