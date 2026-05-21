"use client";
import Link from "next/link";
import { FilePresentation, ChevronRight } from "lucide-react";

const tools = [
  {
    href: "/herramientas/cenefas",
    title: "Generador de Cenefas",
    description: "Cargá el Excel de productos y la plantilla PPTX para generar las cenefas automáticamente.",
    icon: FilePresentation,
    tag: "PPTX",
  },
];

export default function HerramientasPage() {
  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="section-title">Herramientas</h1>
        <p className="section-sub mt-1">Generadores y utilidades para el equipo de marketing.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {tools.map(({ href, title, description, icon: Icon, tag }) => (
          <Link key={href} href={href}
            className="card group flex flex-col gap-4 hover:border-brand-500 transition-colors duration-150">
            <div className="flex items-start justify-between">
              <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
                <Icon size={20} className="text-brand-400" />
              </div>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-400 uppercase tracking-wider">
                {tag}
              </span>
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-100">{title}</p>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
            </div>
            <div className="flex items-center gap-1 text-xs text-brand-400 font-medium mt-auto">
              Abrir herramienta <ChevronRight size={13} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
