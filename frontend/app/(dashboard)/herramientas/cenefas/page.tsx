"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Presentation } from "lucide-react";
import { useTranslation } from "react-i18next";
import DestinoModal, { type CenefaDestino } from "@/components/cenefas/DestinoModal";
import RedExpressPanel from "@/components/cenefas/redexpress/RedExpressPanel";
import RompePreciosPanel from "@/components/cenefas/rompeprecios/RompePreciosPanel";

// Host: primero pregunta a qué destino se va (modal), después renderiza el
// panel correspondiente. RedExpress y Rompe Precios son flujos completamente
// distintos (plantillas, variables, UI) que solo comparten PreviewStep.

function CenefasHost() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [destino, setDestino] = useState<CenefaDestino | null>(null);

  useEffect(() => {
    const param = searchParams.get("destino");
    if (param === "redexpress" || param === "rompe_precios") setDestino(param);
  }, [searchParams]);

  function selectDestino(d: CenefaDestino) {
    setDestino(d);
    router.replace(`/herramientas/cenefas?destino=${d}`);
  }

  return (
    <div className="animate-fade-in w-full space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
          <Presentation size={22} className="text-emerald-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {destino === "rompe_precios" ? t("cenefas.destino.rompe_precios.label") : t("cenefas.title")}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            {destino === "rompe_precios" ? t("cenefas.destino.rompe_precios.description") : t("cenefas.subtitle")}
          </p>
        </div>
      </div>

      {destino === "redexpress" && <RedExpressPanel />}
      {destino === "rompe_precios" && <RompePreciosPanel />}

      {destino === null && <DestinoModal onSelect={selectDestino} />}
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
