"use client";
import { Store, PartyPopper } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CenefaDestino } from "@/components/cenefas/DestinoModal";

// Mismo patrón que DestinoModal.tsx (Cenefas) — el Convertidor arma un Excel
// distinto según a qué destino va (columnas de Redexpres vs Rompe Precios),
// así que necesita elegir destino antes de subir el archivo.

interface ConvertidorDestinoModalProps {
  onSelect: (destino: CenefaDestino) => void;
}

export default function ConvertidorDestinoModal({ onSelect }: ConvertidorDestinoModalProps) {
  const { t } = useTranslation();

  const DESTINOS: { id: CenefaDestino; icon: React.ElementType; color: string }[] = [
    { id: "rompe_precios", icon: PartyPopper, color: "text-rose-500 bg-rose-500/10" },
    { id: "redexpres",    icon: Store,       color: "text-emerald-500 bg-emerald-500/10" },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 w-full max-w-lg p-6 space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">{t("convertidor.destino.title")}</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("convertidor.destino.subtitle")}</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {DESTINOS.map(({ id, icon: Icon, color }) => (
            <button
              key={id}
              onClick={() => onSelect(id)}
              className="flex flex-col items-start gap-3 p-4 rounded-xl border-2 border-slate-200 dark:border-slate-700 hover:border-brand-400 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-all text-left"
            >
              <span className={`w-10 h-10 rounded-xl flex items-center justify-center ${color}`}>
                <Icon size={20} />
              </span>
              <span>
                <span className="block text-sm font-semibold text-slate-800 dark:text-slate-100">
                  {t(`convertidor.destino.${id}.label`)}
                </span>
                <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {t(`convertidor.destino.${id}.description`)}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
