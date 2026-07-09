"use client";
import { useEffect, useState } from "react";
import { metricsApi } from "@/lib/api";
import { format, subDays } from "date-fns";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Activity, Users, Percent, DollarSign } from "lucide-react";
import { SkeletonCard } from "@/components/ui/SkeletonCard";
import { toast } from "sonner";
import { fNum, fMoney } from "@/lib/format";
import { useTranslation } from "react-i18next";

interface FunnelTotals {
  sessions: number;
  users: number;
  page_views: number;
  view_item: number;
  add_to_cart: number;
  begin_checkout: number;
  purchase: number;
  revenue: number;
  engagement_rate: number;
  avg_session_duration_sec: number;
}

interface ChannelRow extends FunnelTotals {
  channel: string;
}

interface DailyPoint {
  date: string;
  sessions: number;
  revenue: number;
}

interface Ga4FunnelResponse {
  totals: FunnelTotals;
  by_channel: ChannelRow[];
  daily: DailyPoint[];
}

const PERIODS = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

const CHANNEL_COLORS: Record<string, string> = {
  "Organic Search": "#22C55E",
  "Direct":         "#6366F1",
  "Paid Social":    "#EC4899",
  "Paid Search":    "#F59E0B",
  "Email":          "#06B6D4",
  "Referral":       "#8B5CF6",
};

interface KPIProps { label: string; value: string; sub: string; icon: React.ReactNode; gradient: string; }
function KPICard({ label, value, sub, icon, gradient }: KPIProps) {
  return (
    <div className="card card-hover p-5 animate-slide-up">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center shadow-sm`}>
          {icon}
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-0.5">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>
    </div>
  );
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

export default function CanalesPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<Ga4FunnelResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);

  useEffect(() => { load(period); }, [period]);

  async function load(days: number) {
    setLoading(true);
    const today = format(new Date(), "yyyy-MM-dd");
    const from = format(subDays(new Date(), days), "yyyy-MM-dd");
    try {
      const res = await metricsApi.getGa4Funnel(from, today);
      setData(res.data);
    } catch {
      toast.error(t("canales.loadError"));
    } finally {
      setLoading(false);
    }
  }

  const totals = data?.totals;
  const conversionRate = totals && totals.sessions > 0 ? (totals.purchase / totals.sessions) * 100 : 0;

  const funnelStages = totals ? [
    { label: t("canales.stageSessions"),      value: totals.sessions },
    { label: t("canales.stagePageViews"),     value: totals.page_views },
    { label: t("canales.stageViewItem"),      value: totals.view_item },
    { label: t("canales.stageAddToCart"),     value: totals.add_to_cart },
    { label: t("canales.stageBeginCheckout"), value: totals.begin_checkout },
    { label: t("canales.stagePurchase"),      value: totals.purchase },
  ] : [];
  const funnelMax = funnelStages[0]?.value ?? 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">{t("canales.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("canales.subtitle")}</p>
        </div>
        <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-xl p-1">
          {PERIODS.map(({ label, days }) => (
            <button key={days} onClick={() => setPeriod(days)}
              className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                period === days
                  ? "bg-white dark:bg-slate-700 shadow-sm text-slate-800 dark:text-slate-100"
                  : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
              }`}>
              {label}
            </button>
          ))}
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
              icon={<Activity size={18} className="text-white" />}
              gradient="from-brand-500 to-brand-600" />
            <KPICard label={t("canales.kpiUsers")} value={fNum(totals.users)}
              sub={t("canales.allChannels")}
              icon={<Users size={18} className="text-white" />}
              gradient="from-slate-600 to-slate-700" />
            <KPICard label={t("canales.kpiConversionRate")} value={`${conversionRate.toFixed(2)}%`}
              sub={t("canales.kpiPurchases", { n: fNum(totals.purchase) })}
              icon={<Percent size={18} className="text-white" />}
              gradient="from-emerald-500 to-emerald-600" />
            <KPICard label={t("canales.kpiRevenue")} value={fMoney(totals.revenue)}
              sub={t("canales.allChannels")}
              icon={<DollarSign size={18} className="text-white" />}
              gradient="from-amber-500 to-orange-500" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="card p-6">
              <div className="mb-4">
                <p className="section-title">{t("canales.funnelTitle")}</p>
                <p className="section-sub mt-0.5">{t("canales.funnelSub")}</p>
              </div>
              <div className="space-y-2.5">
                {funnelStages.map((stage, i) => (
                  <FunnelBar key={stage.label} label={stage.label} value={stage.value} max={funnelMax}
                    pctOfPrev={i === 0 ? null : (funnelStages[i-1].value > 0 ? (stage.value / funnelStages[i-1].value) * 100 : 0)} />
                ))}
              </div>
            </div>

            <div className="card p-6">
              <div className="mb-4">
                <p className="section-title">{t("canales.trendTitle")}</p>
                <p className="section-sub mt-0.5">{t("canales.trendSub")}</p>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={data?.daily ?? []}>
                  <defs>
                    <linearGradient id="sessionsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                    tickFormatter={(d) => format(new Date(d + "T00:00:00"), "d MMM")} minTickGap={30} />
                  <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                  <Tooltip
                    labelFormatter={(d) => format(new Date(d + "T00:00:00"), "d MMM yyyy")}
                    formatter={(v: any) => [fNum(Number(v)), t("canales.stageSessions")]}
                    contentStyle={{ borderRadius: 12, border: "1px solid #f1f5f9", fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="sessions" stroke="#6366f1" strokeWidth={2} fill="url(#sessionsGradient)" />
                </AreaChart>
              </ResponsiveContainer>
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
                    return (
                      <tr key={ch.channel} className="table-tr">
                        <td className="table-td">
                          <span className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-300">
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: CHANNEL_COLORS[ch.channel] || "#6366f1" }} />
                            {ch.channel}
                          </span>
                        </td>
                        <td className="table-td">{fNum(ch.sessions)}</td>
                        <td className="table-td">{chConvRate.toFixed(2)}%</td>
                        <td className="table-td">{(ch.engagement_rate * 100).toFixed(0)}%</td>
                        <td className="table-td font-semibold">{fMoney(ch.revenue)}</td>
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
