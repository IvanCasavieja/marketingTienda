"use client";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import type { FacturacionMovimiento } from "@/lib/api";
import { fMoneyExact } from "@/lib/format";

// Movimientos cronológicos tipo cuenta de débito, debajo de la torta de
// presupuesto. El signo +/- y el label "Entrada"/"Salida" van siempre
// visibles junto al color -- nunca codificar el tipo solo con color (rojo/
// verde es el par clásico de confusión para daltonismo, ver plan).

interface LedgerListProps {
  movimientos: FacturacionMovimiento[];
  total: number;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

export default function LedgerList({ movimientos, total, onLoadMore, loadingMore }: LedgerListProps) {
  const { t } = useTranslation();

  if (movimientos.length === 0) {
    return (
      <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 text-sm text-slate-400 dark:text-slate-500 text-center py-4">
        {t("facturacion.ledger.empty")}
      </div>
    );
  }

  return (
    <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800">
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">{t("facturacion.ledger.title")}</p>
      <div className="space-y-1.5 max-h-72 overflow-y-auto">
        {movimientos.map((m) => {
          const esEntrada = m.tipo === "entrada";
          return (
            <div key={m.id} className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/60">
              <span
                className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 ${
                  esEntrada
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                    : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400"
                }`}
              >
                {esEntrada ? t("facturacion.entrada") : t("facturacion.salida")}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-slate-700 dark:text-slate-300 truncate">{m.concepto}</p>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">
                  {m.proveedor_marca ? `${m.proveedor_marca} · ` : ""}{m.fecha}
                </p>
              </div>
              <span className={`text-sm font-semibold shrink-0 ${esEntrada ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                {esEntrada ? "+" : "−"}{fMoneyExact(m.monto)}
              </span>
            </div>
          );
        })}
      </div>
      {movimientos.length < total && (
        <button
          onClick={onLoadMore}
          disabled={loadingMore}
          className="mt-3 w-full flex items-center justify-center gap-2 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 disabled:opacity-50 py-1.5"
        >
          {loadingMore && <Loader2 size={12} className="animate-spin" />}
          {t("facturacion.ledger.loadMore")}
        </button>
      )}
    </div>
  );
}
