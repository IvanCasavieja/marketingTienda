"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Brain, Settings, LogOut,
  BarChart3, ChevronRight, Wrench,
} from "lucide-react";
import { clsx } from "clsx";
import { authApi, connectionsApi } from "@/lib/api";
import type { CurrentUser } from "@/types";

const nav = [
  { href: "/dashboard",    label: "Dashboard",   icon: LayoutDashboard, section: "MKTG Platform" },
  { href: "/campaigns",    label: "Campañas",    icon: Megaphone,       section: "MKTG Platform" },
  { href: "/analytics",    label: "Análisis IA", icon: Brain,           section: "MKTG Platform" },
  { href: "/herramientas", label: "Herramientas",icon: Wrench,          section: "Herramientas"  },
  { href: "/settings",     label: "Conexiones",  icon: Settings,        section: "Configuración" },
];

const platforms = [
  { key: "meta",       name: "Meta Ads",   color: "#1877F2", initial: "M" },
  { key: "google_ads", name: "Google Ads", color: "#4285F4", initial: "G" },
  { key: "tiktok",     name: "TikTok Ads", color: "#FF0050", initial: "T" },
  { key: "dv360",      name: "DV360",      color: "#34A853", initial: "D" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [connected, setConnected] = useState<Set<string>>(new Set());
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);

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

  const tenantLabel = currentUser?.team_name ?? "Sin equipo asignado";

  return (
    <aside className="w-64 min-h-screen bg-navy-900 flex flex-col shrink-0">
      {/* Logo — click goes to home */}
      <Link href="/home" className="px-5 pt-6 pb-5 flex items-center gap-3 group">
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
          const active = pathname === href || pathname.startsWith(href + "/");
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
            Plataformas
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
      <div className="px-3 pb-5">
        <button
          onClick={() => { localStorage.clear(); window.location.href = "/login"; }}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm text-slate-500
                     hover:bg-white/5 hover:text-slate-300 transition-all duration-150">
          <LogOut size={16} />
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
