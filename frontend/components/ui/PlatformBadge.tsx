import { PLATFORM_LABELS } from "@/types";
import { useTranslation } from "react-i18next";

const STYLES: Record<string, string> = {
  meta:       "bg-blue-50 text-blue-700 border-blue-100",
  google_ads: "bg-indigo-50 text-indigo-700 border-indigo-100",
  tiktok:     "bg-rose-50 text-rose-600 border-rose-100",
  dv360:      "bg-emerald-50 text-emerald-700 border-emerald-100",
  sfmc:       "bg-cyan-50 text-cyan-700 border-cyan-100",
};

const DOTS: Record<string, string> = {
  meta:       "bg-blue-500",
  google_ads: "bg-indigo-500",
  tiktok:     "bg-rose-500",
  dv360:      "bg-emerald-500",
  sfmc:       "bg-cyan-500",
};

export default function PlatformBadge({ platform }: { platform: string }) {
  const { t } = useTranslation();
  // Integración con Meta Ads pausada (ver metrics_service.py): lo que se ve
  // en pantalla para esta plataforma es un fixture fijo, no datos en vivo —
  // este chip evita que se confunda con cifras reales.
  const isMetaFixture = platform === "meta";

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${STYLES[platform] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${DOTS[platform] || "bg-slate-400"}`} />
      {PLATFORM_LABELS[platform] || platform}
      {isMetaFixture && (
        <span
          title={t("common.metaFixtureTooltip")}
          className="ml-0.5 px-1 py-px rounded text-[9px] font-bold tracking-wide bg-amber-100 text-amber-700 border border-amber-200"
        >
          {t("common.metaFixtureLabel")}
        </span>
      )}
    </span>
  );
}
