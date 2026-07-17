"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftRight, FileSpreadsheet } from "lucide-react";
import { useTranslation } from "react-i18next";
import ConvertidorDestinoModal from "@/components/cenefas/convertidor/ConvertidorDestinoModal";
import type { CenefaDestino } from "@/components/cenefas/DestinoModal";
import ConvertidorPanel from "@/components/cenefas/convertidor/ConvertidorPanel";
import TininFloating from "@/components/cenefas/TininFloating";

// Mismo patrón que materiales/cenefas/page.tsx: primero pregunta a qué
// destino va el Excel (columnas de salida distintas), después renderiza el
// panel con ese destino ya elegido.

function ConvertidorHost() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [destino, setDestino] = useState<CenefaDestino | null>(null);

  useEffect(() => {
    const param = searchParams.get("destino");
    if (param === "redexpres" || param === "rompe_precios") setDestino(param);
  }, [searchParams]);

  function selectDestino(d: CenefaDestino) {
    setDestino(d);
    router.replace(`/materiales/convertidor?destino=${d}`);
  }

  function changeDestino() {
    setDestino(null);
    router.replace("/materiales/convertidor");
  }

  return (
    <div className="animate-fade-in w-full space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-amber-500/10 flex items-center justify-center shrink-0">
            <FileSpreadsheet size={22} className="text-amber-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("convertidor.title")}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("convertidor.subtitle")}</p>
          </div>
        </div>
        {destino !== null && (
          <button
            onClick={changeDestino}
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
          >
            <ArrowLeftRight size={13} /> {t("cenefas.destino.change")}
          </button>
        )}
      </div>

      {destino !== null && <ConvertidorPanel destino={destino} />}
      {destino === null && <ConvertidorDestinoModal onSelect={selectDestino} />}

      <TininFloating contexto="convertidor" />
    </div>
  );
}

export default function ConvertidorPage() {
  return (
    <Suspense fallback={null}>
      <ConvertidorHost />
    </Suspense>
  );
}
