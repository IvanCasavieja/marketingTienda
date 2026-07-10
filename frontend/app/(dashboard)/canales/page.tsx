"use client";
import { useEffect, useMemo, useState } from "react";
import { metricsApi } from "@/lib/api";
import { Ga4ChannelRow, Ga4FunnelResponse } from "@/types";
import { format, subDays } from "date-fns";
import { es, enUS, ptBR } from "date-fns/locale";
import type { Locale } from "date-fns";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Activity, Users, Percent, DollarSign, UserPlus, ShoppingCart, Receipt, Calendar, ChevronDown } from "lucide-react";
import { SkeletonCard } from "@/components/ui/SkeletonCard";
import KPICard from "@/components/ui/KPICard";
import DeltaBadge from "@/components/ui/DeltaBadge";
import { toast } from "sonner";
import { fNum, fMoney } from "@/lib/format";
import { useTranslation } from "react-i18next";
import { CompareMode, getCompareDates, getCompareLabel } from "@/lib/period";

const PERIODS = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

const DF_LOCALES: Record<string, Locale> = { es, en: enUS, pt: ptBR };

const CHANNEL_COLORS: Record<string, string> = {
  "Organic Search": "#22C55E",
  "Direct":         "#6366F1",
  "Paid Social":    "#EC4899",
  "Paid Search":    "#F59E0B",
  "Email":          "#06B6D4",
  "Referral":       "#8B5CF6",
};

type TrendMetricKey = "sessions" | "purchase" | "revenue" | "avg_order_value" | "users";

const TREND_METRICS: { key: TrendMetricKey; label: string }[] = [
  { key: "sessions",        label: "Sesiones" },
  { key: "purchase",        label: "Transacciones" },
  { key: "revenue",         label: "Ingresos" },
  { key: "avg_order_value", label: "Ticket promedio" },
  { key: "users",           label: "Usuarios" },
];

function formatTrendValue(key: TrendMetricKey, v: number): string {
  return key === "revenue" || key === "avg_order_value" ? fMoney(v) : fNum(v);
}

function FunnelBar({ label, value, max, pctOfPrev }: { label: string; value: number; max: number; pctOfPrev: number | null }) {
  const widthPct = max > 0 ? Math.max((value / max) * 100, 4) : 4;
  return (
    <div className="flex items-center gap-3">
      <div className="w-32 shrink-0 text-xs text-slate-500 dark:text-slate-400 text-right">{label}</div>
      <div className="flex-1 h-8 bg-slate-50 dark:bg-slate-800/60 rounded-lg overflow-hidden">
        <div
          className="h-full rounded-lg bg-gradient-to-r from-brand-500 to-brand-400 flex items-center justify-end px-3 transition-all duration-500"
          style={{ width: `${widthPct}%` }}
        >
          <span className="text-white text-xs font-semibold whitespace-nowrap">{fNum(value)}</span>
        </div>
      </div>
      <div className="w-14 shrink-0 text-xs font-medium text-slate-400">
        {pctOfPrev !== null ? `${pctOfPrev.toFixed(0)}%` : ""}
      </div>
    </div>
  );
}

function buildFunnelStages(totals: Ga4FunnelResponse["totals"] | undefined, t: (k: string) => string) {
  if (!totals) return [];
  return [
    { label: t("canales.stageSessions"),      value: totals.sessions },
    { label: t("canales.stagePageViews"),     value: totals.page_views },
    { label: t("canales.stageViewItem"),      value: totals.view_item },
    { label: t("canales.stageAddToCart"),     value: totals.add_to_cart },
    { label: t("canales.stageBeginCheckout"), value: totals.begin_checkout },
    { label: t("canales.stagePurchase"),      value: totals.purchase },
  ];
}

export default function CanalesPage() {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<Ga4FunnelResponse | null>(null);
  const [cmpData, setCmpData] = useState<Ga4FunnelResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);
  const [isCustom, setIsCustom] = useState(false);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [comparing, setComparing] = useState(false);
  const [compareMode, setCompareMode] = useState<CompareMode>("prev_period");
  const [cmpFrom, setCmpFrom] = useState("");
  const [cmpTo, setCmpTo] = useState("");
  const [trendMetric, setTrendMetric] = useState<TrendMetricKey>("sessions");
  const [mounted, setMounted] = useState(false);

  const dfLocale = DF_LOCALES[i18n.language] ?? es;

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (isCustom && customFrom && customTo) {
      load(customFrom, customTo);
    } else if (!isCustom) {
      const today = format(new Date(), "yyyy-MM-dd");
      const from  = format(subDays(new Date(), period), "yyyy-MM-dd");
      load(from, today);
    }
  }, [period, isCustom, customFrom, customTo, comparing, compareMode, cmpFrom, cmpTo]); // eslint-disable-line react-hooks/exhaustive-deps

  async function load(from: string, to: string) {
    setLoading(true);
    try {
      const reqs = [metricsApi.getGa4Funnel(from, to)];
      let cmpRange: { from: string; to: string } | null = null;
      if (comparing) {
        if (compareMode === "custom") {
          if (cmpFrom && cmpTo) cmpRange = { from: cmpFrom, to: cmpTo };
        } else {
          cmpRange = getCompareDates(0, compareMode, from, to);
        }
      }
      if (cmpRange) reqs.push(metricsApi.getGa4Funnel(cmpRange.from, cmpRange.to));
      const [curr, cmp] = await Promise.all(reqs);
      setData(curr.data);
      setCmpData(cmp ? cmp.data : null);
    } catch {
      toast.error(t("canales.loadError"));
    } finally {
      setLoading(false);
    }
  }

  const totals = data?.totals;
  const cmpTotals = cmpData?.totals;
  const conversionRate = totals && totals.sessions > 0 ? (totals.purchase / totals.sessions) * 100 : 0;
  const cmpConversionRate = cmpTotals && cmpTotals.sessions > 0 ? (cmpTotals.purchase / cmpTotals.sessions) * 100 : 0;

  const funnelStages = useMemo(() => buildFunnelStages(totals, t), [totals, t]);
  const cmpFunnelStages = useMemo(() => buildFunnelStages(cmpTotals, t), [cmpTotals, t]);
  const funnelMax = funnelStages[0]?.value ?? 0;
  const cmpFunnelMax = cmpFunnelStages[0]?.value ?? 0;

  const cmpByChannel = useMemo(() => {
    const map: Record<string, Ga4ChannelRow> = {};
    (cmpData?.by_channel ?? []).forEach((c) => { map[c.channel] = c; });
    return map;
  }, [cmpData]);

  interface TrendPoint { date?: string; idx?: number; curr: number; cmp?: number; }

  const trendChartData: TrendPoint[] = useMemo(() => {
    const currDaily = data?.daily ?? [];
    if (!comparing || !cmpData) {
      return currDaily.map((d) => ({ date: d.date, curr: d[trendMetric] }));
    }
    const cmpDaily = cmpData.daily;
    const len = Math.max(currDaily.length, cmpDaily.length);
    return Array.from({ length: len }, (_, i) => ({
      idx: i + 1,
      date: currDaily[i]?.date,
      curr: currDaily[i]?.[trendMetric] ?? 0,
      cmp: cmpDaily[i]?.[trendMetric] ?? 0,
    }));
  }, [data, cmpData, comparing, trendMetric]);

  const compareLabel = compareMode === "custom"
    ? (cmpFrom && cmpTo ? `vs. ${cmpFrom} → ${cmpTo}` : "")
    : getCompareLabel(period, compareMode, dfLocale, isCustom ? customFrom : undefined, isCustom ? customTo : undefined);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">{t("canales.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("canales.subtitle")}</p>
        </div>
        <div className="flex flex-col gap-1.5 items-start sm:items-end">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1">
              {PERIODS.map(({ label, days }) => (
                <button key={days} onClick={() => { setPeriod(days); setIsCustom(false); }}
                  className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                    !isCustom && period === days
                      ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
                      : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                  }`}>
                  {label}
                </button>
              ))}
              <button
                onClick={() => {
                  setIsCustom(true);
                  if (!customFrom) setCustomFrom(format(subDays(new Date(), 30), "yyyy-MM-dd"));
                  if (!customTo)   setCustomTo(format(new Date(), "yyyy-MM-dd"));
                }}
                className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 flex items-center gap-1 ${
                  isCustom
                    ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
                    : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                }`}>
                <Calendar size={11} />
                Personalizado
              </button>
            </div>
            <button onClick={() => setComparing((c) => !c)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 ${
                comparing ? "bg-brand-600 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}>
              Comparar
            </button>
            {comparing && (
              <div className="relative">
                <select
                  value={compareMode}
                  onChange={(e) => setCompareMode(e.target.value as CompareMode)}
                  className="appearance-none pl-3 pr-7 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer outline-none transition-all shadow-card"
                >
                  <option value="prev_period">{t("dashboard.prevPeriod")}</option>
                  <option value="prev_year">{t("dashboard.prevYear")}</option>
                  <option value="custom">Personalizado</option>
                </select>
                <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              </div>
            )}
          </div>

          {isCustom && (
            <div className="flex items-center gap-2 flex-wrap">
              <input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500" />
              <span className="text-slate-400 text-xs">→</span>
              <input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500" />
            </div>
          )}

          {comparing && compareMode === "custom" && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-400 text-xs">vs.</span>
              <input type="date" value={cmpFrom} onChange={(e) => setCmpFrom(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg text-xs border border-dashed border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500" />
              <span className="text-slate-400 text-xs">→</span>
              <input type="date" value={cmpTo} onChange={(e) => setCmpTo(e.target.value)}
                className="px-2.5 py-1.5 rounded-lg text-xs border border-dashed border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500" />
            </div>
          )}

          {comparing && compareMode !== "custom" && (
            <p className="text-xs text-slate-400" suppressHydrationWarning>
              {mounted && compareLabel}
            </p>
          )}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map((i) => <SkeletonCard key={i} className="h-36" />)}
        </div>
      ) : !totals || totals.sessions === 0 ? (
        <div className="card p-6 flex flex-col items-center gap-3 text-center border-dashed">
          <p className="text-sm text-slate-500 dark:text-slate-400">{t("canales.noData")}</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard label={t("canales.kpiSessions")} value={fNum(totals.sessions)}
              sub={t("canales.kpiUsersOf", { n: fNum(totals.users) })}
              curr={comparing && cmpTotals ? totals.sessions : undefined} prev={comparing && cmpTotals ? cmpTotals.sessions : undefined}
              icon={<Activity size={18} className="text-white" />}
              gradient="from-brand-500 to-brand-600" />
            <KPICard label={t("canales.kpiUsers")} value={fNum(totals.users)}
              sub={t("canales.allChannels")}
              curr={comparing && cmpTotals ? totals.users : undefined} prev={comparing && cmpTotals ? cmpTotals.users : undefined}
              icon={<Users size={18} className="text-white" />}
              gradient="from-slate-600 to-slate-700" />
            <KPICard label="Compradores nuevos" value={fNum(totals.new_buyers)}
              sub={t("canales.allChannels")}
              curr={comparing && cmpTotals ? totals.new_buyers : undefined} prev={comparing && cmpTotals ? cmpTotals.new_buyers : undefined}
              icon={<UserPlus size={18} className="text-white" />}
              gradient="from-teal-500 to-teal-600" />
            <KPICard label="Transacciones" value={fNum(totals.purchase)}
              sub={t("canales.allChannels")}
              curr={comparing && cmpTotals ? totals.purchase : undefined} prev={comparing && cmpTotals ? cmpTotals.purchase : undefined}
              icon={<ShoppingCart size={18} className="text-white" />}
              gradient="from-indigo-500 to-indigo-600" />
            <KPICard label={t("canales.kpiRevenue")} value={fMoney(totals.revenue)}
              sub={t("canales.allChannels")}
              curr={comparing && cmpTotals ? totals.revenue : undefined} prev={comparing && cmpTotals ? cmpTotals.revenue : undefined}
              icon={<DollarSign size={18} className="text-white" />}
              gradient="from-amber-500 to-orange-500" />
            <KPICard label={t("canales.kpiConversionRate")} value={`${conversionRate.toFixed(2)}%`}
              sub={t("canales.kpiPurchases", { n: fNum(totals.purchase) })}
              curr={comparing && cmpTotals ? conversionRate : undefined} prev={comparing && cmpTotals ? cmpConversionRate : undefined}
              icon={<Percent size={18} className="text-white" />}
              gradient="from-emerald-500 to-emerald-600" />
            <KPICard label="Ticket promedio" value={fMoney(totals.avg_order_value)}
              sub={t("canales.allChannels")}
              curr={comparing && cmpTotals ? totals.avg_order_value : undefined} prev={comparing && cmpTotals ? cmpTotals.avg_order_value : undefined}
              icon={<Receipt size={18} className="text-white" />}
              gradient="from-rose-500 to-rose-600" />
          </div>

          {/* Métricas de engagement — más blandas, no son el foco principal */}
          <div className="grid grid-cols-2 gap-4">
            <div className="card p-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 dark:text-slate-400">Engagement rate</p>
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{(totals.engagement_rate * 100).toFixed(1)}%</p>
              </div>
              {comparing && cmpTotals && <DeltaBadge curr={totals.engagement_rate} prev={cmpTotals.engagement_rate} variant="pill" />}
            </div>
            <div className="card p-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 dark:text-slate-400">Duración promedio de sesión</p>
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{Math.round(totals.avg_session_duration_sec)}s</p>
              </div>
              {comparing && cmpTotals && <DeltaBadge curr={totals.avg_session_duration_sec} prev={cmpTotals.avg_session_duration_sec} variant="pill" />}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="card p-6">
              <div className="mb-4">
                <p className="section-title">{t("canales.funnelTitle")}</p>
                <p className="section-sub mt-0.5">{t("canales.funnelSub")}</p>
              </div>
              <div className={comparing && cmpTotals ? "grid grid-cols-1 md:grid-cols-2 gap-6" : ""}>
                <div>
                  {comparing && cmpTotals && <p className="text-[11px] font-semibold text-slate-400 mb-2 uppercase tracking-wide">Actual</p>}
                  <div className="space-y-2.5">
                    {funnelStages.map((stage, i) => (
                      <FunnelBar key={stage.label} label={stage.label} value={stage.value} max={funnelMax}
                        pctOfPrev={i === 0 ? null : (funnelStages[i-1].value > 0 ? (stage.value / funnelStages[i-1].value) * 100 : 0)} />
                    ))}
                  </div>
                </div>
                {comparing && cmpTotals && (
                  <div>
                    <p className="text-[11px] font-semibold text-slate-400 mb-2 uppercase tracking-wide">Comparación</p>
                    <div className="space-y-2.5">
                      {cmpFunnelStages.map((stage, i) => (
                        <FunnelBar key={stage.label} label={stage.label} value={stage.value} max={cmpFunnelMax}
                          pctOfPrev={i === 0 ? null : (cmpFunnelStages[i-1].value > 0 ? (stage.value / cmpFunnelStages[i-1].value) * 100 : 0)} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {comparing && cmpTotals && (
                <div className="mt-5 pt-4 border-t border-slate-50 dark:border-slate-800">
                  <p className="text-[11px] font-semibold text-slate-400 mb-2 uppercase tracking-wide">Variación por escalón</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {funnelStages.map((stage, i) => (
                      <div key={stage.label} className="flex items-center justify-between text-xs bg-slate-50 dark:bg-slate-800/60 rounded-lg px-3 py-2">
                        <span className="text-slate-500 dark:text-slate-400">{stage.label}</span>
                        <DeltaBadge curr={stage.value} prev={cmpFunnelStages[i]?.value ?? 0} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="card p-6">
              <div className="mb-4 flex items-start justify-between flex-wrap gap-2">
                <div>
                  <p className="section-title">{t("canales.trendTitle")}</p>
                  <p className="section-sub mt-0.5">{t("canales.trendSub")}</p>
                </div>
                <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
                  {TREND_METRICS.map(({ key, label }) => (
                    <button key={key} onClick={() => setTrendMetric(key)}
                      className={`px-2 py-1 rounded-md text-[10.5px] font-semibold transition-all duration-150 ${
                        trendMetric === key
                          ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
                          : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                      }`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              {comparing && cmpTotals ? (
                <>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                      <span className="w-2.5 h-0.5 bg-brand-500 inline-block" /> Actual
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-600">
                      <span className="w-2.5 h-0.5 bg-slate-400 inline-block" /> Comparación
                    </span>
                  </div>
                  <ResponsiveContainer width="100%" height={230}>
                    <LineChart data={trendChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                      <XAxis dataKey="idx" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                        tickFormatter={(i) => `Día ${i}`} minTickGap={30} />
                      <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                      <Tooltip
                        formatter={(v: any) => formatTrendValue(trendMetric, Number(v))}
                        labelFormatter={(i) => `Día ${i}`}
                        contentStyle={{ borderRadius: 12, border: "1px solid #f1f5f9", fontSize: 12 }}
                      />
                      <Line type="monotone" dataKey="curr" name="Actual" stroke="#6366f1" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="cmp" name="Comparación" stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 3" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={trendChartData}>
                    <defs>
                      <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                      tickFormatter={(d) => d ? format(new Date(d + "T00:00:00"), "d MMM") : ""} minTickGap={30} />
                    <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                    <Tooltip
                      labelFormatter={(d) => d ? format(new Date(d + "T00:00:00"), "d MMM yyyy") : ""}
                      formatter={(v: any) => [formatTrendValue(trendMetric, Number(v)), TREND_METRICS.find((m) => m.key === trendMetric)?.label]}
                      contentStyle={{ borderRadius: 12, border: "1px solid #f1f5f9", fontSize: 12 }}
                    />
                    <Area type="monotone" dataKey="curr" stroke="#6366f1" strokeWidth={2} fill="url(#trendGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="px-4 sm:px-6 py-4 border-b border-slate-50 dark:border-slate-800">
              <p className="section-title">{t("canales.channelsTitle")}</p>
              <p className="section-sub mt-0.5">{t("canales.channelsSub")}</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px]">
                <thead>
                  <tr className="border-b border-slate-50 dark:border-slate-800">
                    {[
                      t("canales.tableHeaders.channel"),
                      t("canales.tableHeaders.sessions"),
                      t("canales.tableHeaders.conversionRate"),
                      t("canales.tableHeaders.engagement"),
                      t("canales.tableHeaders.revenue"),
                    ].map((h) => <th key={h} className="table-th">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data?.by_channel.map((ch) => {
                    const chConvRate = ch.sessions > 0 ? (ch.purchase / ch.sessions) * 100 : 0;
                    const cmpCh = cmpByChannel[ch.channel];
                    return (
                      <tr key={ch.channel} className="table-tr">
                        <td className="table-td">
                          <span className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-300">
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: CHANNEL_COLORS[ch.channel] || "#6366f1" }} />
                            {ch.channel}
                          </span>
                        </td>
                        <td className="table-td">
                          {fNum(ch.sessions)}
                          {comparing && cmpCh && <DeltaBadge curr={ch.sessions} prev={cmpCh.sessions} />}
                        </td>
                        <td className="table-td">{chConvRate.toFixed(2)}%</td>
                        <td className="table-td">{(ch.engagement_rate * 100).toFixed(0)}%</td>
                        <td className="table-td font-semibold">
                          {fMoney(ch.revenue)}
                          {comparing && cmpCh && <DeltaBadge curr={ch.revenue} prev={cmpCh.revenue} />}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
