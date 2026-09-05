"use client";
import { useEffect, useRef, useState } from "react";
import { metricsApi } from "@/lib/api";
import { PlatformSummary, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import { es, enUS, ptBR } from "date-fns/locale";
import type { Locale } from "date-fns";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie,
} from "recharts";
import {
  DollarSign, MousePointerClick, ShoppingCart,
  TrendingUp, RefreshCw, AlertTriangle, ChevronDown, Calendar,
} from "lucide-react";
import { SkeletonCard, SkeletonRow } from "@/components/ui/SkeletonCard";
import { toast } from "sonner";
import PlatformBadge from "@/components/ui/PlatformBadge";
import DeltaBadge from "@/components/ui/DeltaBadge";
import KPICard from "@/components/ui/KPICard";
import { fNum, fMoney } from "@/lib/format";
import { useTranslation } from "react-i18next";
import { CompareMode, getCompareDates, getCompareLabel } from "@/lib/period";

const COLORS: Record<string, string> = {
  meta:             "#1877F2",
  google_ads:       "#4285F4",
  tiktok:           "#FF0050",
  dv360:            "#34A853",
  sfmc:             "#00A1E0",
  google_analytics: "#FF9900",
};

const OBJECTIVE_COLORS: Record<string, string> = {
  branding:   "#6366f1",
  traffic:    "#f59e0b",
  conversion: "#10b981",
  unknown:    "#94a3b8",
};

const OBJECTIVE_LABELS: Record<string, string> = {
  branding:   "Branding",
  traffic:    "Tráfico",
  conversion: "Conversión",
  unknown:    "Sin clasificar",
};

interface ObjectiveBucket {
  objective: string;
  spend: number;
  revenue: number;
  conversions: number;
  pct: number;
  roas: number;
}

const PERIODS = [
  { label: "7D",  days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

const DF_LOCALES: Record<string, Locale> = { es, en: enUS, pt: ptBR };

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 shadow-card-hover rounded-xl px-3.5 py-2.5 min-w-[148px]">
      <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">{label}</p>
      {payload.map((p: any) => {
        const isPrev = p.dataKey === "prevSpend" || p.dataKey === "prevRoas";
        const isRoas = p.dataKey === "roas" || p.dataKey === "prevRoas";
        const val = isRoas ? `${Number(p.value).toFixed(2)}x` : fMoney(p.value);
        return (
          <div key={p.dataKey} className="flex items-center justify-between gap-3 text-xs mb-0.5">
            <span className="text-slate-400">{isPrev ? "Anterior" : "Actual"}</span>
            <span className="font-bold" style={{ color: isPrev ? `${p.fill}70` : p.fill }}>{val}</span>
          </div>
        );
      })}
    </div>
  );
};

export default function DashboardPage() {
  const { t, i18n } = useTranslation();
  const [summary, setSummary]         = useState<PlatformSummary[]>([]);
  const [prevSummary, setPrevSummary] = useState<PlatformSummary[]>([]);
  const [byObjective, setByObjective] = useState<ObjectiveBucket[]>([]);
  const [loading, setLoading]         = useState(true);
  const [syncing, setSyncing]         = useState(false);
  const [period, setPeriod]           = useState(30);
  const [isCustom, setIsCustom]       = useState(false);
  const [customFrom, setCustomFrom]   = useState("");
  const [customTo, setCustomTo]       = useState("");
  const [compareMode, setCompareMode] = useState<CompareMode>("prev_period");
  const [cmpFrom, setCmpFrom]         = useState("");
  const [cmpTo, setCmpTo]             = useState("");
  const [mounted, setMounted]         = useState(false);
  const [lastSyncDate, setLastSyncDate]   = useState<string | null>(null);
  const [autoSyncStatus, setAutoSyncStatus] = useState<{
    last_run: string | null; next_run: string | null; interval_hours: number; active: boolean;
  } | null>(null);
  const lastAutoRunRef = useRef<string | null>(null);

  const dfLocale = DF_LOCALES[i18n.language] ?? es;

  useEffect(() => { setMounted(true); }, []);

  const dayLabel = mounted ? format(new Date(), "EEEE d 'de' MMMM", { locale: dfLocale }) : "";

  useEffect(() => {
    if (compareMode === "custom" && !(cmpFrom && cmpTo)) return;
    if (isCustom && customFrom && customTo) {
      loadDataCustom(customFrom, customTo, compareMode);
    } else if (!isCustom) {
      loadData(period, compareMode);
    }
  }, [period, compareMode, isCustom, customFrom, customTo, cmpFrom, cmpTo]);

  useEffect(() => {
    function fetchAutoSync() {
      metricsApi.getAutoSyncStatus()
        .then(({ data }) => {
          setAutoSyncStatus(data);
          if (data.last_run && data.last_run !== lastAutoRunRef.current) {
            if (lastAutoRunRef.current !== null) {
              if (isCustom && customFrom && customTo) loadDataCustom(customFrom, customTo, compareMode);
              else loadData(period, compareMode);
            }
            lastAutoRunRef.current = data.last_run;
          }
        })
        .catch(() => {});
    }
    fetchAutoSync();
    const interval = setInterval(fetchAutoSync, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [period, compareMode, isCustom, customFrom, customTo]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData(days: number, mode: CompareMode) {
    setLoading(true);
    const today = format(new Date(), "yyyy-MM-dd");
    const from  = format(subDays(new Date(), days), "yyyy-MM-dd");
    const cmp   = mode === "custom" ? { from: cmpFrom, to: cmpTo } : getCompareDates(days, mode);
    try {
      const [curr, prev, objective] = await Promise.all([
        metricsApi.getSummary(from, today),
        metricsApi.getSummary(cmp.from, cmp.to),
        metricsApi.getSpendByObjective(from, today),
      ]);
      setSummary(curr.data);
      setPrevSummary(prev.data);
      setByObjective(objective.data.by_objective);
      const maxDate = curr.data.reduce((max: string | null, s: any) => {
        if (!s.last_date) return max;
        return !max || s.last_date > max ? s.last_date : max;
      }, null);
      setLastSyncDate(maxDate);
    } catch {
      toast.error(t("dashboard.loadError"));
    } finally {
      setLoading(false);
    }
  }

  async function loadDataCustom(from: string, to: string, mode: CompareMode) {
    setLoading(true);
    const cmp = getCompareDates(0, mode, from, to);
    try {
      const [curr, prev, objective] = await Promise.all([
        metricsApi.getSummary(from, to),
        metricsApi.getSummary(cmp.from, cmp.to),
        metricsApi.getSpendByObjective(from, to),
      ]);
      setSummary(curr.data);
      setPrevSummary(prev.data);
      setByObjective(objective.data.by_objective);
      const maxDate = curr.data.reduce((max: string | null, s: any) => {
        if (!s.last_date) return max;
        return !max || s.last_date > max ? s.last_date : max;
      }, null);
      setLastSyncDate(maxDate);
    } catch {
      toast.error(t("dashboard.loadError"));
    } finally {
      setLoading(false);
    }
  }

  async function syncAll() {
    setSyncing(true);
    const today = format(new Date(), "yyyy-MM-dd");
    const from  = isCustom && customFrom ? customFrom : format(subDays(new Date(), period), "yyyy-MM-dd");
    // Meta Ads excluido — conexión pausada (2026-07-06), la data mostrada es un
    // fixture fijo. Ver nota de reactivación en backend/app/services/metrics_service.py
    const platformList = ["google_ads", "tiktok", "dv360"];
    const results = await Promise.allSettled(platformList.map((p) => metricsApi.sync(p, from, today)));

    let synced = 0;
    results.forEach((r, i) => {
      if (r.status === "fulfilled") {
        const { records_saved, status } = r.value.data;
        if (status !== "skipped" && records_saved > 0) synced++;
      } else {
        const detail: string =
          r.reason?.response?.data?.detail ??
          `Error al sincronizar ${platformList[i]}`;
        toast.error(detail, { duration: 8000 });
      }
    });

    if (synced > 0) toast.success(t("dashboard.syncSuccess", { n: synced }));
    if (isCustom && customFrom && customTo) await loadDataCustom(customFrom, customTo, compareMode);
    else await loadData(period, compareMode);
    setSyncing(false);
  }

  const totals = summary.reduce(
    (acc, s) => ({
      spend:       acc.spend + s.spend,
      clicks:      acc.clicks + s.clicks,
      impressions: acc.impressions + s.impressions,
      conversions: acc.conversions + s.conversions,
      revenue:     acc.revenue + s.revenue,
    }),
    { spend: 0, clicks: 0, impressions: 0, conversions: 0, revenue: 0 }
  );

  const prevTotals = prevSummary.reduce(
    (acc, s) => ({
      spend:       acc.spend + s.spend,
      clicks:      acc.clicks + s.clicks,
      conversions: acc.conversions + s.conversions,
      revenue:     acc.revenue + s.revenue,
    }),
    { spend: 0, clicks: 0, conversions: 0, revenue: 0 }
  );

  const globalRoas = totals.spend > 0 ? totals.revenue / totals.spend : 0;
  const prevRoas   = prevTotals.spend > 0 ? prevTotals.revenue / prevTotals.spend : 0;
  const cpa        = totals.conversions > 0 ? totals.spend / totals.conversions : 0;

  const alerts: string[] = [];
  if (!loading && totals.spend > 0) {
    if (globalRoas < 1 && globalRoas > 0) alerts.push(t("dashboard.alerts.lowRoas", { roas: globalRoas.toFixed(2) }));
    const spendChange = prevTotals.spend > 0 ? (totals.spend - prevTotals.spend) / prevTotals.spend * 100 : 0;
    if (spendChange > 50) alerts.push(t("dashboard.alerts.highSpend", { pct: spendChange.toFixed(0) }));
    if (totals.clicks > 0 && totals.conversions === 0) alerts.push(t("dashboard.alerts.noConversions"));
    summary.forEach((s) => {
      if (s.avg_roas < 0.5 && s.spend > 0) alerts.push(t("dashboard.alerts.platformLowRoas", { platform: PLATFORM_LABELS[s.platform] || s.platform, roas: s.avg_roas.toFixed(2) }));
    });
  }

  // Mapa de prevSummary por plataforma para comparación en tabla y gráficos
  const prevByPlatform = prevSummary.reduce<Record<string, PlatformSummary>>((acc, s) => {
    acc[s.platform] = s;
    return acc;
  }, {});

  const chartData = summary.map((s) => {
    const prev = prevByPlatform[s.platform];
    return {
      name:      PLATFORM_LABELS[s.platform] || s.platform,
      spend:     s.spend,
      prevSpend: prev?.spend ?? 0,
      roas:      s.avg_roas,
      prevRoas:  prev?.avg_roas ?? 0,
      fill:      COLORS[s.platform] || "#6366f1",
    };
  });

  const periodLabel = isCustom && customFrom && customTo
    ? `${customFrom} → ${customTo}`
    : `${period}D`;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-1 capitalize">{dayLabel}</p>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">{t("dashboard.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("dashboard.subtitle")}</p>
        </div>
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex flex-col gap-1.5">
            {/* Frescura de datos + estado auto-sync */}
            <div className="flex items-center gap-3 text-[11px] text-slate-400 flex-wrap">
              {lastSyncDate && (
                <span>
                  Datos hasta <span className="font-medium text-slate-500">{lastSyncDate}</span>
                </span>
              )}
              {autoSyncStatus?.active && (
                <span className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  {autoSyncStatus.last_run
                    ? `Auto-sync · cada ${autoSyncStatus.interval_hours}h`
                    : "Auto-sync activo"}
                </span>
              )}
            </div>

            {/* Selector de período */}
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
              <div className="relative">
                <select
                  value={compareMode}
                  onChange={(e) => setCompareMode(e.target.value as CompareMode)}
                  className="appearance-none pl-3 pr-7 py-1.5 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer outline-none transition-all shadow-card"
                >
                  <option value="prev_period">{t("dashboard.prevPeriod")}</option>
                  <option value="prev_year">{t("dashboard.prevYear")}</option>
                  <option value="custom">{t("canales.custom")}</option>
                </select>
                <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Inputs de fecha personalizada */}
            {isCustom && (
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                />
                <span className="text-slate-400 text-xs">→</span>
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg text-xs border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                />
              </div>
            )}

            {/* Inputs de fecha personalizada para la comparación */}
            {compareMode === "custom" && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-slate-400 text-xs">vs.</span>
                <input
                  type="date"
                  value={cmpFrom}
                  onChange={(e) => setCmpFrom(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg text-xs border border-dashed border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                />
                <span className="text-slate-400 text-xs">→</span>
                <input
                  type="date"
                  value={cmpTo}
                  onChange={(e) => setCmpTo(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg text-xs border border-dashed border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                />
              </div>
            )}

            <p className="text-xs text-slate-400" suppressHydrationWarning>
              {mounted && compareMode !== "custom" && getCompareLabel(period, compareMode, dfLocale, isCustom ? customFrom : undefined, isCustom ? customTo : undefined)}
            </p>
          </div>
          <button onClick={syncAll} disabled={syncing} className="btn-secondary text-xs sm:text-sm">
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            {syncing ? t("dashboard.syncing") : t("dashboard.syncAll")}
          </button>
        </div>
      </div>

      {/* KPIs */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map((i) => <SkeletonCard key={i} className="h-36" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard label={t("dashboard.totalInvestment")} value={fMoney(totals.spend)}
            sub={t("dashboard.lastNDays", { n: periodLabel })}
            curr={totals.spend} prev={prevTotals.spend}
            icon={<DollarSign size={18} className="text-white" />}
            gradient="from-brand-500 to-brand-600" />
          <KPICard label={t("dashboard.totalClicks")} value={fNum(totals.clicks)}
            sub={t("dashboard.allPlatforms")}
            curr={totals.clicks} prev={prevTotals.clicks}
            icon={<MousePointerClick size={18} className="text-white" />}
            gradient="from-slate-600 to-slate-700" />
          <KPICard label={t("dashboard.conversions")} value={fNum(totals.conversions)}
            sub={`CPA: $${cpa.toFixed(2)}`}
            curr={totals.conversions} prev={prevTotals.conversions}
            icon={<ShoppingCart size={18} className="text-white" />}
            gradient="from-emerald-500 to-emerald-600" />
          <KPICard label={t("dashboard.globalRoas")} value={`${globalRoas.toFixed(2)}x`}
            sub={t("dashboard.revenueInversion")}
            curr={globalRoas} prev={prevRoas}
            icon={<TrendingUp size={18} className="text-white" />}
            gradient="from-amber-500 to-orange-500" />
        </div>
      )}

      {/* Empty state */}
      {!loading && summary.length === 0 && (
        <div className="card p-6 flex flex-col items-center gap-3 text-center border-dashed">
          <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
            <RefreshCw size={20} className="text-slate-400" />
          </div>
          <div>
            <p className="font-semibold text-slate-700 dark:text-slate-300">Sin datos para este período</p>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-sm">
              Conectá una plataforma publicitaria y sincronizá para ver tus métricas acá.
            </p>
          </div>
          <div className="flex gap-3">
            <a href="/settings"
              className="text-xs font-medium text-brand-600 hover:text-brand-700 border border-brand-200 hover:border-brand-300 px-4 py-2 rounded-lg transition-colors">
              Configurar conexiones
            </a>
            <button onClick={syncAll} disabled={syncing}
              className="text-xs font-medium text-white bg-brand-600 hover:bg-brand-700 px-4 py-2 rounded-lg transition-colors disabled:opacity-50">
              Sincronizar ahora
            </button>
          </div>
        </div>
      )}

      {/* Anomaly alerts */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((alert, i) => (
            <div key={i} className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
              <AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />
              <p className="text-sm text-amber-800">{alert}</p>
            </div>
          ))}
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="card p-6">
          <div className="mb-4">
            <p className="section-title">{t("dashboard.investmentByPlatform")}</p>
            <p className="section-sub mt-0.5">{t("dashboard.totalSpendNDays", { n: periodLabel })}</p>
            {prevSummary.length > 0 && (
              <div className="flex items-center gap-3 mt-1.5">
                <span className="flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                  <span className="w-2.5 h-2.5 rounded-sm bg-slate-500 inline-block opacity-90" />
                  Actual
                </span>
                <span className="flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-600">
                  <span className="w-2.5 h-2.5 rounded-sm bg-slate-400 inline-block opacity-40" />
                  Anterior
                </span>
              </div>
            )}
          </div>
          {loading ? (
            <div className="h-52 skeleton rounded-xl" />
          ) : chartData.length === 0 ? (
            <div className="h-52 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">
              {t("dashboard.noDataSync")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} barSize={28} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                  tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="prevSpend" radius={[4, 4, 0, 0]} name="Período anterior">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} fillOpacity={0.3} />
                  ))}
                </Bar>
                <Bar dataKey="spend" radius={[6, 6, 0, 0]} name="Período actual">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} fillOpacity={0.9} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card p-6">
          <div className="mb-4">
            <p className="section-title">{t("dashboard.roas")}</p>
            <p className="section-sub mt-0.5">{t("dashboard.revenueSlash")}</p>
            {prevSummary.length > 0 && (
              <div className="flex items-center gap-3 mt-1.5">
                <span className="flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                  <span className="w-2.5 h-2.5 rounded-sm bg-slate-500 inline-block opacity-90" />
                  Actual
                </span>
                <span className="flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-600">
                  <span className="w-2.5 h-2.5 rounded-sm bg-slate-400 inline-block opacity-40" />
                  Anterior
                </span>
              </div>
            )}
          </div>
          {loading ? (
            <div className="h-52 skeleton rounded-xl" />
          ) : chartData.length === 0 ? (
            <div className="h-52 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">
              {t("dashboard.noDataSync")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} barSize={28} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                  tickFormatter={(v) => `${v.toFixed(1)}x`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="prevRoas" radius={[4, 4, 0, 0]} name="Período anterior">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} fillOpacity={0.3} />
                  ))}
                </Bar>
                <Bar dataKey="roas" radius={[6, 6, 0, 0]} name="Período actual">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} fillOpacity={0.9} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Inversión por objetivo de funnel */}
      <div className="card p-6">
        <div className="mb-4">
          <p className="section-title">Inversión por objetivo de funnel</p>
          <p className="section-sub mt-0.5">Branding vs. tráfico vs. conversión — {periodLabel}</p>
        </div>
        {loading ? (
          <div className="h-52 skeleton rounded-xl" />
        ) : byObjective.length === 0 ? (
          <div className="h-52 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">
            {t("dashboard.noDataSync")}
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-center gap-6">
            <div className="w-full sm:w-52 h-[200px] shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={byObjective}
                    dataKey="spend"
                    nameKey="objective"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={2}
                    strokeWidth={0}
                  >
                    {byObjective.map((entry) => (
                      <Cell key={entry.objective} fill={OBJECTIVE_COLORS[entry.objective] ?? "#94a3b8"} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, _name, item: any) => [
                      fMoney(value), OBJECTIVE_LABELS[item.payload.objective] ?? item.payload.objective,
                    ]}
                    contentStyle={{ borderRadius: 12, border: "1px solid #f1f5f9", fontSize: 12 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="flex-1 w-full space-y-2.5">
              {byObjective.map((b) => (
                <div key={b.objective} className="flex items-center gap-3">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: OBJECTIVE_COLORS[b.objective] ?? "#94a3b8" }} />
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300 w-28 shrink-0">
                    {OBJECTIVE_LABELS[b.objective] ?? b.objective}
                  </span>
                  <span className="text-xs text-slate-400 w-14 shrink-0">{b.pct.toFixed(1)}%</span>
                  <span className="text-sm font-semibold text-slate-800 dark:text-slate-200 flex-1 text-right">{fMoney(b.spend)}</span>
                  <span className={`text-xs font-bold w-16 text-right ${b.roas >= 2 ? "text-emerald-600" : b.roas >= 1 ? "text-amber-500" : "text-red-500"}`}>
                    {b.roas.toFixed(2)}x
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Platform table */}
      <div className="card overflow-hidden">
        <div className="px-4 sm:px-6 py-4 border-b border-slate-50 dark:border-slate-800 flex items-center justify-between">
          <p className="section-title">{t("dashboard.performanceByPlatform")}</p>
          <span className="text-xs text-slate-400 dark:text-slate-500">{periodLabel}</span>
        </div>
        <div className="overflow-x-auto">
        <table className="w-full min-w-[600px]">
          <thead>
            <tr className="border-b border-slate-50">
              {[
                t("dashboard.tableHeaders.platform"),
                t("dashboard.tableHeaders.investment"),
                t("dashboard.tableHeaders.clicks"),
                t("dashboard.tableHeaders.ctr"),
                t("dashboard.tableHeaders.conversions"),
                "CPA",
                t("dashboard.tableHeaders.roas"),
              ].map((h) => (
                <th key={h} className="table-th">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} colSpan={7} />)
            ) : summary.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-10 text-center text-sm text-slate-400 dark:text-slate-500">
                  {t("dashboard.noDataFull")}
                </td>
              </tr>
            ) : (
              summary.map((s) => {
                const prev = prevByPlatform[s.platform];
                const cpaVal = s.conversions > 0 ? s.spend / s.conversions : null;
                const prevCpa = prev && prev.conversions > 0 ? prev.spend / prev.conversions : 0;
                return (
                  <tr key={s.platform} className="table-tr">
                    <td className="table-td"><PlatformBadge platform={s.platform} /></td>
                    <td className="table-td font-semibold">
                      {fMoney(s.spend)}
                      {prev && <DeltaBadge curr={s.spend} prev={prev.spend} />}
                    </td>
                    <td className="table-td">
                      {fNum(s.clicks)}
                      {prev && <DeltaBadge curr={s.clicks} prev={prev.clicks} />}
                    </td>
                    <td className="table-td">{s.avg_ctr.toFixed(2)}%</td>
                    <td className="table-td">
                      {fNum(s.conversions)}
                      {prev && <DeltaBadge curr={s.conversions} prev={prev.conversions} />}
                    </td>
                    <td className="table-td text-slate-600 dark:text-slate-400">
                      {cpaVal !== null ? `$${cpaVal.toFixed(2)}` : "—"}
                      {prev && cpaVal !== null && prevCpa > 0 && (
                        <DeltaBadge curr={cpaVal} prev={prevCpa} />
                      )}
                    </td>
                    <td className="table-td">
                      <span className={`font-bold ${s.avg_roas >= 2 ? "text-emerald-600" : s.avg_roas >= 1 ? "text-amber-500" : "text-red-500"}`}>
                        {s.avg_roas.toFixed(2)}x
                      </span>
                      {prev && <DeltaBadge curr={s.avg_roas} prev={prev.avg_roas} />}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}
