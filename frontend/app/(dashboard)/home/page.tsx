"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api";
import type { CurrentUser } from "@/types";
import {
  BarChart3, Presentation, ChevronRight,
  TrendingUp, Brain, Megaphone, Settings,
} from "lucide-react";

const modules = [
  {
    href: "/dashboard",
    title: "MKTG Platform",
    description: "Dashboard de inversión, campañas, análisis con IA y métricas cross-platform en tiempo real.",
    icon: BarChart3,
    color: "from-brand-500 to-brand-700",
    iconBg: "bg-brand-500/15",
    iconColor: "text-brand-400",
    features: [
      { icon: TrendingUp,    label: "Dashboard KPIs" },
      { icon: Megaphone,     label: "Campañas" },
      { icon: Brain,         label: "Análisis IA" },
      { icon: Settings,      label: "Conexiones" },
    ],
    tag: "Analytics",
    tagColor: "bg-brand-500/10 text-brand-400",
  },
  {
    href: "/herramientas/cenefas",
    title: "Generador de Cenefas",
    description: "Subí el Excel de productos y la plantilla PPTX para generar las cenefas de la semana automáticamente.",
    icon: Presentation,
    color: "from-emerald-500 to-emerald-700",
    iconBg: "bg-emerald-500/15",
    iconColor: "text-emerald-400",
    features: [
      { icon: Presentation, label: "Carga Excel" },
      { icon: Presentation, label: "Plantilla PPTX" },
      { icon: Presentation, label: "Descarga automática" },
      { icon: Presentation, label: "3 cenefas por slide" },
    ],
    tag: "PPTX",
    tagColor: "bg-emerald-500/10 text-emerald-400",
  },
];

export default function HomePage() {
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    authApi.me().then(({ data }) => setUser(data)).catch(() => {});
  }, []);

  const greeting = user?.full_name ? `Hola, ${user.full_name.split(" ")[0]}` : "Bienvenido";

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col justify-center max-w-4xl mx-auto px-4 py-12">
      {/* Header */}
      <div className="mb-10">
        <p className="text-xs font-semibold text-brand-400 uppercase tracking-widest mb-2">
          {user?.team_name ?? "MKTG Platform"}
        </p>
        <h1 className="text-3xl font-bold text-slate-900">{greeting} 👋</h1>
        <p className="text-slate-500 mt-1.5 text-base">¿Con qué módulo trabajás hoy?</p>
      </div>

      {/* Module cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {modules.map(({ href, title, description, icon: Icon, color, iconBg, iconColor, features, tag, tagColor }) => (
          <Link key={href} href={href}
            className="group relative card overflow-hidden flex flex-col gap-5 p-6 hover:border-slate-200 hover:shadow-card-hover transition-all duration-200">

            {/* Gradient accent top */}
            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${color} opacity-80 rounded-t-2xl`} />

            {/* Header */}
            <div className="flex items-start justify-between mt-1">
              <div className={`w-12 h-12 rounded-2xl ${iconBg} flex items-center justify-center`}>
                <Icon size={24} className={iconColor} />
              </div>
              <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${tagColor}`}>
                {tag}
              </span>
            </div>

            {/* Content */}
            <div>
              <h2 className="text-lg font-bold text-slate-900 mb-1.5">{title}</h2>
              <p className="text-sm text-slate-500 leading-relaxed">{description}</p>
            </div>

            {/* Feature pills */}
            <div className="flex flex-wrap gap-2">
              {features.map(({ label }) => (
                <span key={label} className="text-[11px] font-medium px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600">
                  {label}
                </span>
              ))}
            </div>

            {/* CTA */}
            <div className={`flex items-center gap-1.5 text-sm font-semibold mt-auto ${iconColor} group-hover:gap-2.5 transition-all duration-150`}>
              Abrir módulo <ChevronRight size={15} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
