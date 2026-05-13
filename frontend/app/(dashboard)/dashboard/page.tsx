"use client";
import { useEffect, useState } from "react";
import { metricsApi } from "@/lib/api";
import { PlatformSummary, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import { es } from "date-fns/locale";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import {
  DollarSign, MousePointerClick, ShoppingCart,
  TrendingUp, ArrowUpRight, ArrowDownRight, RefreshCw,
} from "lucide-react";
import { SkeletonCard, SkeletonRow } from "@/components/ui/SkeletonCard";
import { toast } from "sonner";
import PlatformBadge from "@/components/ui/PlatformBadge";
import { fNum, fMoney } from "@/lib/format";
import { metricsApi as mApi } from "@/lib/api";

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
  const [summary, setSummary]         = useState<PlatformSummary[]>([]);
  const [prevSummary, setPrevSummary] = useState<PlatformSummary[]>([]);
  const [loading, setLoading]         = useState(true);
  const [syncing, setSyncing]         = useState(false);
  const [period, setPeriod]           = useState(30);

  const dayLabel = format(new Date(), "EEEE d 'de' MMMM", { locale: es });

  useEffect(() => { loadData(period); }, [period]);

  async function loadData(days: number) {
    setLoading(true);
    const today    = format(new Date(), "yyyy-MM-dd");
    const from     = format(subDays(new Date(), days), "yyyy-MM-dd");
    const prevTo   = format(subDays(new Date(), days + 1), "yyyy-MM-dd");
    const prevFrom = format(subDays(new Date(), days * 2), "yyyy-MM-dd");
    try {
      const [curr, prev] = await Promise.all([
        metricsApi.getSummary(from, today),
        metricsApi.getSummary(prevFrom, prevTo),
      ]);
      setSummary(curr.data);
      setPrevSummary(prev.data);
    } catch {
      // show empty state
    } finally {
      setLoading(false);
    }
  }

  async function syncAll() {
    setSyncing(true);
    const today = format(new Date(), "yyyy-MM-dd");
    const from  = format(subDays(new Date(), period), "yyyy-MM-dd");
    const platforms = ["meta", "google_ads", "tiktok", "dv360"];
    const results = await Promise.allSettled(platforms.map((p) => mApi.sync(p, from, today)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed    = results.filter((r) => r.status === "rejected").length;
    if (succeeded > 0) toast.success(`Sincronizadas ${succeeded} plataforma(s) correctamente`);
    if (failed > 0 && succeeded === 0) toast.error("No se pudo sincronizar ninguna plataforma");
    await loadData(period);
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
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Todas las plataformas</p>
        </div>
        <div className="flex items-center gap-3">
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
          <button onClick={syncAll} disabled={syncing} className="btn-secondary">
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            {syncing ? "Sincronizando..." : "Sync datos"}
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
          <KPICard label="Inversión total" value={fMoney(totals.spend)}
            sub={`últimos ${period} días`}
            trend={pctChange(totals.spend, prevTotals.spend)}
            icon={<DollarSign size={18} className="text-white" />}
            gradient="from-brand-500 to-brand-600" />
          <KPICard label="Clicks totales" value={fNum(totals.clicks)}
            sub="todas las plataformas"
            trend={pctChange(totals.clicks, prevTotals.clicks)}
            icon={<MousePointerClick size={18} className="text-white" />}
            gradient="from-slate-600 to-slate-700" />
          <KPICard label="Conversiones" value={fNum(totals.conversions)}
            sub={`CPA: $${cpa.toFixed(2)}`}
            trend={pctChange(totals.conversions, prevTotals.conversions)}
            icon={<ShoppingCart size={18} className="text-white" />}
            gradient="from-emerald-500 to-emerald-600" />
          <KPICard label="ROAS global" value={`${globalRoas.toFixed(2)}x`}
            sub="revenue / inversión"
            trend={pctChange(globalRoas, prevRoas)}
            icon={<TrendingUp size={18} className="text-white" />}
            gradient="from-amber-500 to-orange-500" />
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="card p-6">
          <div className="mb-5">
            <p className="section-title">Inversión por plataforma</p>
            <p className="section-sub mt-0.5">Gasto total en {period} días</p>
          </div>
          {loading ? (
            <div className="h-52 skeleton rounded-xl" />
          ) : chartData.length === 0 ? (
            <div className="h-52 flex items-center justify-center text-slate-400 text-sm">
              Sin datos · Sincronizá una plataforma
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                  tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="spend" radius={[6, 6, 0, 0]} name="Inversión">
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
            <p className="section-title">ROAS por plataforma</p>
            <p className="section-sub mt-0.5">Revenue / Inversión</p>
          </div>
          {loading ? (
            <div className="h-52 skeleton rounded-xl" />
          ) : chartData.length === 0 ? (
            <div className="h-52 flex items-center justify-center text-slate-400 text-sm">
              Sin datos · Sincronizá una plataforma
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
          <p className="section-title">Rendimiento por plataforma</p>
          <span className="text-xs text-slate-400">Últimos {period} días</span>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-50">
              {["Plataforma", "Inversión", "Clicks", "CTR", "Conversiones", "ROAS"].map((h) => (
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
                  Sin datos — sincronizá tus plataformas para ver métricas aquí
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
