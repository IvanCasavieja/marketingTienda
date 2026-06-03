"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Brain, Settings, LogOut,
  BarChart3, ChevronRight, Presentation, Globe, Layers, Clock, ShieldCheck, HelpCircle,
} from "lucide-react";
import { clsx } from "clsx";
import { authApi, connectionsApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import { useTranslation } from "react-i18next";
import { LANGUAGES, setLanguage, type LangCode } from "@/lib/i18n";

const platforms = [
  { key: "meta",       name: "Meta Ads",   color: "#1877F2", initial: "M" },
  { key: "google_ads", name: "Google Ads", color: "#4285F4", initial: "G" },
  { key: "tiktok",     name: "TikTok Ads", color: "#FF0050", initial: "T" },
  { key: "dv360",      name: "DV360",      color: "#34A853", initial: "D" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { t, i18n } = useTranslation();
  const [connected, setConnected] = useState<Set<string>>(new Set());
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [showLangMenu, setShowLangMenu] = useState(false);

  const isMedios = !currentUser || currentUser.team_type === "medios" || currentUser.team_type === null;

  const navAll = [
    { href: "/dashboard",               label: t("common.dashboard"),  icon: LayoutDashboard, section: "Analytics",                  restricted: true },
    { href: "/campaigns",               label: t("common.campaigns"),  icon: Megaphone,        section: "Analytics",                  restricted: true },
    { href: "/analytics",               label: t("common.aiAnalysis"), icon: Brain,            section: "Analytics",                  restricted: true },
    { href: "/herramientas/cenefas",    label: "Generar cenefas",      icon: Presentation,     section: t("sidebar.herramientas"),    restricted: false },
    { href: "/herramientas/cenefas/v2", label: "Editor de plantillas", icon: Layers,           section: t("sidebar.herramientas"),    restricted: false },
    { href: "/herramientas/cenefas/v2/jobs", label: "Historial",       icon: Clock,            section: t("sidebar.herramientas"),    restricted: false },
    { href: "/settings",                label: t("common.connections"),icon: Settings,         section: t("sidebar.configuracion"),   restricted: false },
    { href: "/ayuda",                   label: "Guía de uso",          icon: HelpCircle,       section: t("sidebar.configuracion"),   restricted: false },
    ...(currentUser?.is_superuser
      ? [{ href: "/admin", label: "Administrador", icon: ShieldCheck, section: t("sidebar.configuracion"), restricted: false }]
      : []),
  ];

  const nav = navAll.filter((item) => isMedios || !item.restricted);

  useEffect(() => {
    connectionsApi.list()
      .then(({ data }) => {
        setConnected(new Set(data.filter((c: any) => c.is_active).map((c: any) => c.platform)));
      })
      .catch(() => {});
    authApi.me()
      .then(({ data }) => setCurrentUser(data))
      .catch(() => {});
  }, []);

  const tenantLabel = currentUser?.team_name ?? t("common.noTeam");
  const currentLang = LANGUAGES.find((l) => l.code === i18n.language) ?? LANGUAGES[0];

  return (
    <aside className="w-64 min-h-screen bg-navy-900 flex flex-col shrink-0">
      {/* Logo — click goes to home */}
      <Link href={isMedios ? "/dashboard" : "/herramientas/cenefas"} className="px-5 pt-6 pb-5 flex items-center gap-3 group">
        <div className="w-8 h-8 rounded-xl bg-brand-500 flex items-center justify-center shrink-0 group-hover:bg-brand-400 transition-colors">
          <BarChart3 size={16} className="text-white" />
        </div>
        <div>
          <p className="text-white font-bold text-sm leading-none">MKTG Platform</p>
          <p className="text-slate-500 text-[11px] mt-0.5 max-w-[180px] truncate" title={tenantLabel}>
            {tenantLabel}
          </p>
        </div>
      </Link>

      <div className="mx-4 h-px bg-white/5 mb-3" />

      {/* Main nav */}
      <nav className="px-3 flex-1 space-y-0.5">
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
              <Link href={href}
                className={clsx(
                  "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
                  active
                    ? "bg-brand-600 text-white shadow-glow"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                )}>
                <Icon size={17} className={active ? "text-white" : "text-slate-500 group-hover:text-slate-300"} />
                <span className="flex-1">{label}</span>
                {active && <ChevronRight size={14} className="text-white/60" />}
              </Link>
            </div>
          );
        })}

        {/* Platforms section */}
        <div className="mt-5 mb-2">
          <p className="px-3 mb-2 text-[10px] font-semibold text-slate-600 uppercase tracking-widest">
            {t("sidebar.plataformas")}
          </p>
          {platforms.map((p) => {
            const isConnected = connected.has(p.key);
            return (
              <div key={p.key}
                className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-slate-500">
                <div
                  className="w-5 h-5 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0"
                  style={{ backgroundColor: isConnected ? p.color : "#334155" }}>
                  {p.initial}
                </div>
                <span className={`text-xs ${isConnected ? "text-slate-300" : "text-slate-600"}`}>
                  {p.name}
                </span>
                <div className={`ml-auto w-1.5 h-1.5 rounded-full transition-colors ${
                  isConnected ? "bg-emerald-500" : "bg-slate-700"
                }`} />
              </div>
            );
          })}
        </div>
      </nav>

      <div className="mx-4 h-px bg-white/5 mb-3" />

      {/* Language selector */}
      <div className="px-3 pb-2 relative">
        <button
          onClick={() => setShowLangMenu((v) => !v)}
          className="flex items-center gap-2.5 w-full px-3 py-2 rounded-xl text-sm text-slate-500
                     hover:bg-white/5 hover:text-slate-300 transition-all duration-150">
          <Globe size={15} className="shrink-0" />
          <span className="flex-1 text-left text-xs">{currentLang.flag} {currentLang.label}</span>
        </button>
        {showLangMenu && (
          <div className="absolute bottom-full left-3 right-3 mb-1 bg-slate-800 border border-white/10 rounded-xl overflow-hidden shadow-lg z-50">
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                onClick={() => { setLanguage(lang.code as LangCode); setShowLangMenu(false); }}
                className={clsx(
                  "w-full flex items-center gap-2.5 px-3 py-2.5 text-sm transition-colors",
                  i18n.language === lang.code
                    ? "bg-brand-600 text-white"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                )}>
                <span>{lang.flag}</span>
                <span className="text-xs font-medium">{lang.label}</span>
              </button>
            ))}
          </div>
        )}
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
  );
}
