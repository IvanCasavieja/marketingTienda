"use client";
import { useEffect, useRef, useState } from "react";
import { metricsApi } from "@/lib/api";
import { PlatformSummary, PLATFORM_LABELS } from "@/types";
import { format, subDays, subYears } from "date-fns";
import { es, enUS, ptBR } from "date-fns/locale";
import type { Locale } from "date-fns";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import {
  DollarSign, MousePointerClick, ShoppingCart,
  TrendingUp, ArrowUpRight, ArrowDownRight, RefreshCw, AlertTriangle,
} from "lucide-react";
import { SkeletonCard, SkeletonRow } from "@/components/ui/SkeletonCard";
import { toast } from "sonner";
import PlatformBadge from "@/components/ui/PlatformBadge";
import { fNum, fMoney } from "@/lib/format";
import { useTranslation } from "react-i18next";

const COLORS: Record<string, string> = {
  meta:       "#1877F2",
  google_ads: "#4285F4",
  tiktok:     "#FF0050",
  dv360:      "#34A853",
  sfmc:       "#00A1E0",
};

const PERIODS = [
  { label: "7D",  days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

const DF_LOCALES: Record<string, Locale> = { es, en: enUS, pt: ptBR };

type CompareMode = "prev_period" | "prev_year";

function getCompareDates(days: number, mode: CompareMode) {
  if (mode === "prev_year") {
    return {
      from: format(subYears(subDays(new Date(), days), 1), "yyyy-MM-dd"),
      to:   format(subYears(new Date(), 1), "yyyy-MM-dd"),
    };
  }
  return {
    from: format(subDays(new Date(), days * 2), "yyyy-MM-dd"),
    to:   format(subDays(new Date(), days + 1), "yyyy-MM-dd"),
  };
}

function getCompareLabel(days: number, mode: CompareMode, locale: Locale): string {
  const { from, to } = getCompareDates(days, mode);
  const f = format(new Date(from + "T00:00:00"), "d MMM", { locale });
  const t = format(new Date(to   + "T00:00:00"), "d MMM", { locale });
  return `vs. ${f} – ${t}`;
}

interface KPIProps {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  trend?: number;
  gradient: string;
}

function KPICard({ label, value, sub, icon, trend, gradient }: KPIProps) {
  const up = trend !== undefined ? trend >= 0 : null;
  return (
    <div className="card card-hover p-5 animate-slide-up">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center shadow-sm`}>
          {icon}
        </div>
        {trend !== undefined && (
          <span className={`flex items-center gap-0.5 text-xs font-semibold px-2 py-0.5 rounded-full
            ${up ? "text-emerald-600 bg-emerald-50" : "text-red-500 bg-red-50"}`}>
            {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>
      <p className="text-2xl font-bold text-slate-900 mb-0.5">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-100 shadow-card-hover rounded-xl px-3.5 py-2.5">
      <p className="text-xs font-semibold text-slate-700 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="text-sm font-bold" style={{ color: p.fill || p.stroke }}>
          {p.name === "roas" ? `${p.value.toFixed(2)}x` : fMoney(p.value)}
        </p>
      ))}
    </div>
  );
};

function pctChange(curr: number, prev: number): number | undefined {
  if (prev === 0) return undefined;
  return ((curr - prev) / prev) * 100;
}

export default function DashboardPage() {
  const { t, i18n } = useTranslation();
  const [summary, setSummary]         = useState<PlatformSummary[]>([]);
  const [prevSummary, setPrevSummary] = useState<PlatformSummary[]>([]);
  const [loading, setLoading]         = useState(true);
  const [syncing, setSyncing]         = useState(false);
  const [period, setPeriod]           = useState(30);
  const [compareMode, setCompareMode] = useState<CompareMode>("prev_period");
  const [mounted, setMounted]         = useState(false);
  const [lastSyncDate, setLastSyncDate]   = useState<string | null>(null);
  const [autoSyncStatus, setAutoSyncStatus] = useState<{
    last_run: string | null; next_run: string | null; interval_hours: number; active: boolean;
  } | null>(null);
  const lastAutoRunRef = useRef<string | null>(null);

  const dfLocale = DF_LOCALES[i18n.language] ?? es;

  useEffect(() => { setMounted(true); }, []);

  const dayLabel = mounted ? format(new Date(), "EEEE d 'de' MMMM", { locale: dfLocale }) : "";

  useEffect(() => { loadData(period, compareMode); }, [period, compareMode]);

  // Cargar estado del auto-sync y detectar nuevos syncs automáticamente
  useEffect(() => {
    function fetchAutoSync() {
      metricsApi.getAutoSyncStatus()
        .then(({ data }) => {
          setAutoSyncStatus(data);
          // Si el auto-sync corrió y tenemos datos nuevos, recargar métricas
          if (data.last_run && data.last_run !== lastAutoRunRef.current) {
            if (lastAutoRunRef.current !== null) {
              // Hubo un sync nuevo mientras estaba abierto — recargar datos
              loadData(period, compareMode);
            }
            lastAutoRunRef.current = data.last_run;
          }
        })
        .catch(() => {});
    }

    fetchAutoSync();
    const interval = setInterval(fetchAutoSync, 5 * 60 * 1000); // cada 5 min
    return () => clearInterval(interval);
  }, [period, compareMode]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData(days: number, mode: CompareMode) {
    setLoading(true);
    const today = format(new Date(), "yyyy-MM-dd");
    const from  = format(subDays(new Date(), days), "yyyy-MM-dd");
    const cmp   = getCompareDates(days, mode);
    try {
      const [curr, prev] = await Promise.all([
        metricsApi.getSummary(from, today),
        metricsApi.getSummary(cmp.from, cmp.to),
      ]);
      setSummary(curr.data);
      setPrevSummary(prev.data);
      // Mostrar la fecha más reciente encontrada en los datos
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
    const from  = format(subDays(new Date(), period), "yyyy-MM-dd");
    const platforms = ["meta", "google_ads", "tiktok", "dv360"];
    const results = await Promise.allSettled(platforms.map((p) => metricsApi.sync(p, from, today)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed    = results.filter((r) => r.status === "rejected").length;
    if (succeeded > 0) toast.success(t("dashboard.syncSuccess", { n: succeeded }));
    if (failed > 0 && succeeded === 0) toast.error(t("dashboard.syncError"));
    await loadData(period, compareMode);
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

  const chartData = summary.map((s) => ({
    name:  PLATFORM_LABELS[s.platform] || s.platform,
    spend: s.spend,
    roas:  s.avg_roas,
    fill:  COLORS[s.platform] || "#6366f1",
  }));

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-1 capitalize">{dayLabel}</p>
          <h1 className="text-2xl font-bold text-slate-900">{t("dashboard.title")}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t("dashboard.subtitle")}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex flex-col items-end gap-1.5">
            {/* Frescura de datos + estado auto-sync */}
            <div className="flex items-center gap-3 text-[11px] text-slate-400">
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
            <div className="flex items-center gap-2">
              <div className="flex gap-1 bg-slate-100 rounded-xl p-1">
                {PERIODS.map(({ label, days }) => (
                  <button key={days} onClick={() => setPeriod(days)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                      period === days
                        ? "bg-white shadow-sm text-slate-800"
                        : "text-slate-500 hover:text-slate-700"
                    }`}>
                    {label}
                  </button>
                ))}
              </div>
              <select value={compareMode} onChange={(e) => setCompareMode(e.target.value as CompareMode)}
                className="text-xs text-slate-500 bg-transparent border-none outline-none cursor-pointer hover:text-slate-700">
                <option value="prev_period">{t("dashboard.prevPeriod")}</option>
                <option value="prev_year">{t("dashboard.prevYear")}</option>
              </select>
            </div>
            <p className="text-xs text-slate-400" suppressHydrationWarning>
              {getCompareLabel(period, compareMode, dfLocale)}
            </p>
          </div>
          <button onClick={syncAll} disabled={syncing} className="btn-secondary">
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
            sub={t("dashboard.lastNDays", { n: period })}
            trend={pctChange(totals.spend, prevTotals.spend)}
            icon={<DollarSign size={18} className="text-white" />}
            gradient="from-brand-500 to-brand-600" />
          <KPICard label={t("dashboard.totalClicks")} value={fNum(totals.clicks)}
            sub={t("dashboard.allPlatforms")}
            trend={pctChange(totals.clicks, prevTotals.clicks)}
            icon={<MousePointerClick size={18} className="text-white" />}
            gradient="from-slate-600 to-slate-700" />
          <KPICard label={t("dashboard.conversions")} value={fNum(totals.conversions)}
            sub={`CPA: $${cpa.toFixed(2)}`}
            trend={pctChange(totals.conversions, prevTotals.conversions)}
            icon={<ShoppingCart size={18} className="text-white" />}
            gradient="from-emerald-500 to-emerald-600" />
          <KPICard label={t("dashboard.globalRoas")} value={`${globalRoas.toFixed(2)}x`}
            sub={t("dashboard.revenueInversion")}
            trend={pctChange(globalRoas, prevRoas)}
            icon={<TrendingUp size={18} className="text-white" />}
            gradient="from-amber-500 to-orange-500" />
        </div>
      )}

      {/* Empty state — sin datos, guiar al usuario */}
      {!loading && summary.length === 0 && (
        <div className="card p-6 flex flex-col items-center gap-3 text-center border-dashed">
          <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
            <RefreshCw size={20} className="text-slate-400" />
          </div>
          <div>
            <p className="font-semibold text-slate-700">Sin datos para este período</p>
            <p className="text-sm text-slate-500 mt-1 max-w-sm">
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
          <div className="mb-5">
            <p className="section-title">{t("dashboard.investmentByPlatform")}</p>
            <p className="section-sub mt-0.5">{t("dashboard.totalSpendNDays", { n: period })}</p>
          </div>
          {loading ? (
            <div className="h-52 skeleton rounded-xl" />
          ) : chartData.length === 0 ? (
            <div className="h-52 flex items-center justify-center text-slate-400 text-sm">
              {t("dashboard.noDataSync")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                  tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="spend" radius={[6, 6, 0, 0]} name={t("dashboard.tableHeaders.investment")}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} fillOpacity={0.9} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card p-6">
          <div className="mb-5">
            <p className="section-title">{t("dashboard.roas")}</p>
            <p className="section-sub mt-0.5">{t("dashboard.revenueSlash")}</p>
          </div>
          {loading ? (
            <div className="h-52 skeleton rounded-xl" />
          ) : chartData.length === 0 ? (
            <div className="h-52 flex items-center justify-center text-slate-400 text-sm">
              {t("dashboard.noDataSync")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                  tickFormatter={(v) => `${v.toFixed(1)}x`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="roas" radius={[6, 6, 0, 0]} name="roas">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.roas >= 2 ? "#10b981" : entry.roas >= 1 ? "#f59e0b" : "#ef4444"} fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Platform table */}
      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-50 flex items-center justify-between">
          <p className="section-title">{t("dashboard.performanceByPlatform")}</p>
          <span className="text-xs text-slate-400">{t("dashboard.lastNDaysShort", { n: period })}</span>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-50">
              {[
                t("dashboard.tableHeaders.platform"),
                t("dashboard.tableHeaders.investment"),
                t("dashboard.tableHeaders.clicks"),
                t("dashboard.tableHeaders.ctr"),
                t("dashboard.tableHeaders.conversions"),
                t("dashboard.tableHeaders.roas"),
              ].map((h) => (
                <th key={h} className="table-th">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
            ) : summary.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-10 text-center text-sm text-slate-400">
                  {t("dashboard.noDataFull")}
                </td>
              </tr>
            ) : (
              summary.map((s) => (
                <tr key={s.platform} className="table-tr">
                  <td className="table-td"><PlatformBadge platform={s.platform} /></td>
                  <td className="table-td font-semibold">{fMoney(s.spend)}</td>
                  <td className="table-td">{fNum(s.clicks)}</td>
                  <td className="table-td">{s.avg_ctr.toFixed(2)}%</td>
                  <td className="table-td">{fNum(s.conversions)}</td>
                  <td className="table-td">
                    <span className={`font-bold ${s.avg_roas >= 2 ? "text-emerald-600" : s.avg_roas >= 1 ? "text-amber-500" : "text-red-500"}`}>
                      {s.avg_roas.toFixed(2)}x
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
