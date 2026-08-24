"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeftRight, BarChart3, Brain, Presentation } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaDestino } from "@/types/cenefas";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import DestinoModal from "@/components/cenefas/DestinoModal";
import CenefaPanel from "@/components/cenefas/CenefaPanel";
import { tomarExcelConvertido } from "@/lib/cenefaHandoff";
import TininFloating from "@/components/cenefas/TininFloating";

// Host: primero pregunta a qué mundo se va, después renderiza el panel.
//
// Antes había un panel por destino (RedExpresPanel / RompePreciosPanel), con
// dos sistemas de plantillas y dos motores de render. Desde 08/2026 hay uno
// solo (CenefaPanel) y los mundos son datos: se crean desde el selector.

function CenefasHost() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useCurrentUser();

  const [destinos, setDestinos] = useState<CenefaDestino[]>([]);
  const [loading, setLoading] = useState(true);
  const [destino, setDestino] = useState<string | null>(null);
  const [excelConvertido, setExcelConvertido] = useState<File | null>(null);

  const puedeEditar = !!user && hasPermission(user, "cenefas.edit");

  useEffect(() => {
    cenefasV2Api.listDestinos()
      .then(({ data }) => setDestinos(data))
      .catch(() => toast.error(t("cenefas.destino.errorCargar")))
      .finally(() => setLoading(false));
  }, [t]);

  useEffect(() => {
    setExcelConvertido(tomarExcelConvertido());
  }, []);

  useEffect(() => {
    const param = searchParams.get("destino");
    if (param) setDestino(param);
  }, [searchParams]);

  const destinoActual = useMemo(
    () => destinos.find((d) => d.slug === destino) ?? null,
    [destinos, destino],
  );

  function selectDestino(slug: string) {
    setDestino(slug);
    router.replace(`/materiales/cenefas?destino=${slug}`);
  }

  function changeDestino() {
    setDestino(null);
    router.replace("/materiales/cenefas");
  }

  // Un ?destino= que ya no existe (mundo borrado, link viejo) vuelve al
  // selector en vez de renderizar un panel sin plantillas y sin nombre.
  const destinoValido = destino !== null && (loading || destinoActual !== null);

  return (
    <div className="animate-fade-in w-full space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
            <Presentation size={22} className="text-emerald-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              {destinoActual ? destinoActual.nombre : t("cenefas.title")}
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              {destinoActual ? destinoActual.descripcion : t("cenefas.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          {/* Cuantas cenefas se hicieron y cuanto vale ese trabajo. */}
          <Link
            href="/materiales/cenefas/v2/informe"
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
          >
            <BarChart3 size={13} /> {t("cenefas.informe.link")}
          </Link>
          {/* Lo que el modulo fue aprendiendo, esperando aprobacion. */}
          <Link
            href="/materiales/cenefas/v2/conocimiento"
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
          >
            <Brain size={13} /> {t("cenefas.conocimiento.link")}
          </Link>
          {destinoValido && (
            <button
              onClick={changeDestino}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
            >
              <ArrowLeftRight size={13} /> {t("cenefas.destino.change")}
            </button>
          )}
        </div>
      </div>

      {destinoValido && destinoActual ? (
        <CenefaPanel
          key={destinoActual.slug}
          category={destinoActual.slug}
          categoryLabel={destinoActual.nombre}
          excelInicial={excelConvertido}
        />
      ) : (
        <DestinoModal
          destinos={destinos}
          loading={loading}
          puedeEditar={puedeEditar}
          onSelect={selectDestino}
          onCreated={(d) => { setDestinos((prev) => [...prev, d]); }}
          onDeleted={(slug) => setDestinos((prev) => prev.filter((d) => d.slug !== slug))}
        />
      )}

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
