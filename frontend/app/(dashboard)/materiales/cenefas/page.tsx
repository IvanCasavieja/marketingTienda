"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftRight, Presentation } from "lucide-react";
import { useTranslation } from "react-i18next";
import DestinoModal, { type CenefaDestino } from "@/components/cenefas/DestinoModal";
import RompePreciosPanel from "@/components/cenefas/rompeprecios/RompePreciosPanel";
import TininFloating from "@/components/cenefas/TininFloating";

// Host: primero pregunta a qué destino se va (modal), después renderiza el
// panel correspondiente. Los tres destinos comparten el mismo panel
// (RompePreciosPanel, parametrizado por category) desde que Redexpres pasó
// al sistema de variables unificado -- mismo flujo, plantillas/Excel
// separados por destino. Todos comparten PreviewStep.

function CenefasHost() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [destino, setDestino] = useState<CenefaDestino | null>(null);

  useEffect(() => {
    const param = searchParams.get("destino");
    if (param === "redexpres" || param === "rompe_precios" || param === "parrilla_y_vinos") setDestino(param);
  }, [searchParams]);

  function selectDestino(d: CenefaDestino) {
    setDestino(d);
    router.replace(`/materiales/cenefas?destino=${d}`);
  }

  function changeDestino() {
    setDestino(null);
    router.replace("/materiales/cenefas");
  }

  return (
    <div className="animate-fade-in w-full space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
            <Presentation size={22} className="text-emerald-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              {destino ? t(`cenefas.destino.${destino}.label`) : t("cenefas.title")}
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              {destino ? t(`cenefas.destino.${destino}.description`) : t("cenefas.subtitle")}
            </p>
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

      {destino === "redexpres" && <RompePreciosPanel category="redexpres" />}
      {destino === "rompe_precios" && <RompePreciosPanel category="rompe_precios" />}
      {destino === "parrilla_y_vinos" && <RompePreciosPanel category="parrilla_y_vinos" />}

      {destino === null && <DestinoModal onSelect={selectDestino} />}

      <TininFloating contexto={destino ?? undefined} />
    </div>
  );
}

export default function CenefasPage() {
  return (
    <Suspense fallback={null}>
      <CenefasHost />
    </Suspense>
  );
}
