"use client";
import { FileSpreadsheet } from "lucide-react";
import { useTranslation } from "react-i18next";
import ConvertidorPanel from "@/components/cenefas/convertidor/ConvertidorPanel";

export default function ConvertidorPage() {
  const { t } = useTranslation();

  return (
    <div className="animate-fade-in w-full space-y-6">
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-2xl bg-amber-500/10 flex items-center justify-center shrink-0">
          <FileSpreadsheet size={22} className="text-amber-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("convertidor.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("convertidor.subtitle")}</p>
        </div>
      </div>

      <ConvertidorPanel />
    </div>
  );
}
