"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import {
  BarChart3, Presentation, ChevronRight,
  TrendingUp, Brain, Megaphone, Settings,
} from "lucide-react";

const shortcuts = [
  {
    href: "/dashboard",
    title: "MKTG Platform",
    description: "Dashboard de inversión, campañas, análisis con IA y métricas cross-platform en tiempo real.",
    icon: BarChart3,
    color: "from-brand-500 to-brand-700",
    iconBg: "bg-brand-500/10",
    iconColor: "text-brand-500",
    features: [
      { icon: TrendingUp, label: "Dashboard KPIs" },
      { icon: Megaphone,  label: "Campañas" },
      { icon: Brain,      label: "Análisis IA" },
      { icon: Settings,   label: "Conexiones" },
    ],
    tag: "Analytics",
    tagColor: "bg-brand-500/10 text-brand-500",
  },
  {
    href: "/herramientas/cenefas",
    title: "Generador de Cenefas",
    description: "Subí el Excel de productos y la plantilla PPTX para generar las cenefas de la semana automáticamente.",
    icon: Presentation,
    color: "from-emerald-500 to-emerald-700",
    iconBg: "bg-emerald-500/10",
    iconColor: "text-emerald-500",
    features: [
      { icon: Presentation, label: "Carga Excel" },
      { icon: Presentation, label: "Plantilla PPTX" },
      { icon: Presentation, label: "Descarga automática" },
      { icon: Presentation, label: "3 cenefas por slide" },
    ],
    tag: "PPTX",
    tagColor: "bg-emerald-500/10 text-emerald-600",
  },
];

export default function HomePage() {
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    authApi.me().then(({ data }) => setUser(data)).catch(() => {});
  }, []);

  const firstName = user?.full_name?.split(" ")[0] ?? "";
  const greeting  = firstName ? `Hola, ${firstName}` : "Bienvenido";

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col justify-center max-w-4xl mx-auto px-4 py-12">
      {/* Header */}
      <div className="mb-10">
        <p className="text-xs font-semibold text-brand-500 uppercase tracking-widest mb-2">
          {user?.team_name ?? "MKTG Platform"}
        </p>
        <h1 className="text-3xl font-bold text-slate-900">{greeting} 👋</h1>
        <p className="text-slate-500 mt-1.5 text-base">¿Con qué trabajás hoy?</p>
      </div>

      {/* Shortcuts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {shortcuts.map(({ href, title, description, icon: Icon, color, iconBg, iconColor, features, tag, tagColor }) => (
          <Link key={href} href={href}
            className="group relative card overflow-hidden flex flex-col gap-5 p-6 hover:border-slate-200 hover:shadow-card-hover transition-all duration-200">

            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${color} opacity-70 rounded-t-2xl`} />

            <div className="flex items-start justify-between mt-1">
              <div className={`w-11 h-11 rounded-2xl ${iconBg} flex items-center justify-center`}>
                <Icon size={22} className={iconColor} />
              </div>
              <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${tagColor}`}>
                {tag}
              </span>
            </div>

            <div>
              <h2 className="text-base font-bold text-slate-900 mb-1">{title}</h2>
              <p className="text-sm text-slate-500 leading-relaxed">{description}</p>
            </div>

            <div className="flex flex-wrap gap-2">
              {features.map(({ label }) => (
                <span key={label} className="text-[11px] font-medium px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600">
                  {label}
                </span>
              ))}
            </div>

            <div className={`flex items-center gap-1.5 text-sm font-semibold mt-auto ${iconColor} group-hover:gap-2.5 transition-all duration-150`}>
              Abrir <ChevronRight size={15} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
