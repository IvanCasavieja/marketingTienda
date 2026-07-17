"use client";
import Link from "next/link";
import { Presentation, Layers, FileSpreadsheet, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function MaterialesPage() {
  const { t } = useTranslation();

  const tools = [
    {
      href:        "/materiales/cenefas",
      title:       t("materiales.cenefas.title"),
      description: t("materiales.cenefas.description"),
      icon:        Presentation,
      tag:         t("materiales.cenefas.tag"),
      tagColor:    "bg-slate-500/10 text-slate-400",
    },
    {
      href:        "/materiales/cenefas/v2",
      title:       t("materiales.editor.title"),
      description: t("materiales.editor.description"),
      icon:        Layers,
      tag:         t("materiales.editor.tag"),
      tagColor:    "bg-brand-500/10 text-brand-400",
    },
    {
      href:        "/materiales/convertidor",
      title:       t("materiales.convertidor.title"),
      description: t("materiales.convertidor.description"),
      icon:        FileSpreadsheet,
      tag:         t("materiales.convertidor.tag"),
      tagColor:    "bg-amber-500/10 text-amber-400",
    },
  ];

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="section-title">{t("materiales.title")}</h1>
        <p className="section-sub mt-1">{t("materiales.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {tools.map(({ href, title, description, icon: Icon, tag, tagColor }) => (
          <Link key={href} href={href}
            className="card group flex flex-col gap-4 hover:border-brand-500 transition-colors duration-150">
            <div className="flex items-start justify-between">
              <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center shrink-0">
                <Icon size={20} className="text-brand-400" />
              </div>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider ${tagColor}`}>
                {tag}
              </span>
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-100">{title}</p>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
            </div>
            <div className="flex items-center gap-1 text-xs text-brand-400 font-medium mt-auto">
              {t("materiales.openTool")} <ChevronRight size={13} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
