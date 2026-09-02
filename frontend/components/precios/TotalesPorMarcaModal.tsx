"use client";
import { PackageCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useEscapeKey } from "@/hooks/useEscapeKey";

interface Props {
  conteoPorMarca: Record<string, number>;
  totalReal: number;
  falloParcial: boolean;
  onContinuar: () => void;
}

export default function TotalesPorMarcaModal({ conteoPorMarca, totalReal, falloParcial, onContinuar }: Props) {
  const { t } = useTranslation();
  useEscapeKey(onContinuar);

  const marcas = Object.entries(conteoPorMarca).sort((a, b) => b[1] - a[1]);
  // El total mostrado es SIEMPRE la cantidad real de productos que vas a ver
  // al tocar Continuar, nunca la suma de conteoPorMarca -- si Doña Tina no
  // pudo clasificar algunas tandas (falloParcial), esa suma queda por debajo
  // de la realidad y decir "0 relevantes" con resultados de sobra es peor
  // que no decir nada.
  const total = totalReal;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onContinuar}>
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-md max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-1.5 px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <PackageCheck size={15} className="text-brand-500" />
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {t("precios.donaTina.modalTitle")}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-2">
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
            {t("precios.donaTina.modalSubtitle", { total })}
          </p>
          {marcas.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-4">
              {t(falloParcial ? "precios.donaTina.falloParcial" : "precios.donaTina.sinMarcas")}
            </p>
          )}
          {marcas.length > 0 && falloParcial && (
            <p className="text-xs text-amber-600 dark:text-amber-400 -mt-1 mb-2">
              {t("precios.donaTina.falloParcial")}
            </p>
          )}
          {marcas.map(([marca, count]) => (
            <div
              key={marca}
              className="flex items-center justify-between text-sm px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/60"
            >
              <span className="text-slate-700 dark:text-slate-200 font-medium">{marca}</span>
              <span className="text-slate-500 dark:text-slate-400 text-xs">{count}</span>
            </div>
          ))}
        </div>

        <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800">
          <button onClick={onContinuar} className="btn-primary w-full text-xs">
            {t("precios.donaTina.continuar")}
          </button>
        </div>
      </div>
    </div>
  );
}
