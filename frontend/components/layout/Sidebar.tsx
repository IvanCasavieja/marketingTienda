"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Brain, Settings, LogOut,
  BarChart3, ChevronRight,
} from "lucide-react";
import { clsx } from "clsx";

const nav = [
  { href: "/dashboard",  label: "Dashboard",    icon: LayoutDashboard, desc: "Resumen general" },
  { href: "/campaigns",  label: "Campañas",      icon: Megaphone,       desc: "Todas las plataformas" },
  { href: "/analytics",  label: "Análisis IA",   icon: Brain,           desc: "Insights con Claude" },
  { href: "/settings",   label: "Conexiones",    icon: Settings,        desc: "APIs y plataformas" },
];

const platforms = [
  { name: "Meta Ads",    color: "#1877F2", initial: "M" },
  { name: "Google Ads",  color: "#4285F4", initial: "G" },
  { name: "TikTok Ads",  color: "#FF0050", initial: "T" },
  { name: "DV360",       color: "#34A853", initial: "D" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 min-h-screen bg-navy-900 flex flex-col shrink-0">
      {/* Logo */}
      <div className="px-5 pt-6 pb-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-brand-500 flex items-center justify-center shrink-0">
            <BarChart3 size={16} className="text-white" />
          </div>
          <div>
            <p className="text-white font-bold text-sm leading-none">MKTG Platform</p>
            <p className="text-slate-500 text-[11px] mt-0.5">Marketing Intelligence</p>
          </div>
        </div>
      </div>

      <div className="mx-4 h-px bg-white/5 mb-3" />

      {/* Main nav */}
      <nav className="px-3 space-y-0.5 flex-1">
        <p className="px-3 mb-2 text-[10px] font-semibold text-slate-600 uppercase tracking-widest">
          Menú
        </p>
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
                active
                  ? "bg-brand-600 text-white shadow-glow"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
              )}
            >
              <Icon size={17} className={active ? "text-white" : "text-slate-500 group-hover:text-slate-300"} />
              <span className="flex-1">{label}</span>
              {active && <ChevronRight size={14} className="text-white/60" />}
            </Link>
          );
        })}

        {/* Platforms section */}
        <div className="mt-5 mb-2">
          <p className="px-3 mb-2 text-[10px] font-semibold text-slate-600 uppercase tracking-widest">
            Plataformas
          </p>
          {platforms.map((p) => (
            <div
              key={p.name}
              className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-slate-500"
            >
              <div
                className="w-5 h-5 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0"
                style={{ backgroundColor: p.color }}
              >
                {p.initial}
              </div>
              <span className="text-slate-400 text-xs">{p.name}</span>
              <div className="ml-auto w-1.5 h-1.5 rounded-full bg-emerald-500" />
            </div>
          ))}
        </div>
      </nav>

      {/* Bottom */}
      <div className="mx-4 h-px bg-white/5 mb-3" />
      <div className="px-3 pb-5">
        <button
          onClick={() => { localStorage.clear(); window.location.href = "/login"; }}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm text-slate-500
                     hover:bg-white/5 hover:text-slate-300 transition-all duration-150"
        >
          <LogOut size={16} />
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
