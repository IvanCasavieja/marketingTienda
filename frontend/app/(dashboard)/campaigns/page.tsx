"use client";
import { useEffect, useState, useMemo } from "react";
import { metricsApi } from "@/lib/api";
import { CampaignMetric, PLATFORM_LABELS } from "@/types";
import { format, subDays } from "date-fns";
import { RefreshCw, Search, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { toast } from "sonner";
import PlatformBadge from "@/components/ui/PlatformBadge";
import { SkeletonRow } from "@/components/ui/SkeletonCard";
import { fNum, fMoney } from "@/lib/format";

const PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"] as const;

type SortKey = "spend" | "clicks" | "ctr" | "roas" | "conversions";
type SortDir = "asc" | "desc";

function RoasBadge({ roas }: { roas: number }) {
  if (roas >= 3)   return <span className="badge badge-green flex items-center gap-1"><TrendingUp size={10} />{roas.toFixed(2)}x</span>;
  if (roas >= 1.5) return <span className="badge badge-yellow flex items-center gap-1"><Minus size={10} />{roas.toFixed(2)}x</span>;
  return             <span className="badge badge-red flex items-center gap-1"><TrendingDown size={10} />{roas.toFixed(2)}x</span>;
}

export default function CampaignsPage() {
  const [metrics, setMetrics]           = useState<CampaignMetric[]>([]);
  const [loading, setLoading]           = useState(true);
  const [syncing, setSyncing]           = useState<string | null>(null);
  const [filterPlatform, setFilter]     = useState("all");
  const [search, setSearch]             = useState("");
  const [sortKey, setSortKey]           = useState<SortKey>("spend");
  const [sortDir, setSortDir]           = useState<SortDir>("desc");
  const [dateFrom, setDateFrom]         = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [dateTo, setDateTo]             = useState(format(new Date(), "yyyy-MM-dd"));

  async function loadMetrics() {
    setLoading(true);
    const pf = filterPlatform !== "all" ? filterPlatform : undefined;
    try {
      const { data } = await metricsApi.getMetrics(dateFrom, dateTo, pf);
      setMetrics(data);
    } catch {
      toast.error("Error cargando métricas");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadMetrics(); }, [dateFrom, dateTo, filterPlatform]);

  async function syncPlatform(platform: string) {
    setSyncing(platform);
    try {
      const { data } = await metricsApi.sync(platform, dateFrom, dateTo);
      toast.success(`${PLATFORM_LABELS[platform]}: ${data.records_saved} registros sincronizados`);
      await loadMetrics();
    } catch {
      toast.error(`Error al sincronizar ${PLATFORM_LABELS[platform]}`);
    } finally {
      setSyncing(null);
    }
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  }

  const displayed = useMemo(() => {
    let rows = [...metrics];
    if (search) rows = rows.filter((m) => m.campaign_name.toLowerCase().includes(search.toLowerCase()));
    rows.sort((a, b) => sortDir === "desc" ? b[sortKey] - a[sortKey] : a[sortKey] - b[sortKey]);
    return rows;
  }, [metrics, search, sortKey, sortDir]);

  const totals = useMemo(() => displayed.reduce(
    (acc, m) => ({ spend: acc.spend + m.spend, clicks: acc.clicks + m.clicks, conversions: acc.conversions + m.conversions }),
    { spend: 0, clicks: 0, conversions: 0 }
  ), [displayed]);


  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Campañas</h1>
          <p className="text-sm text-slate-500 mt-0.5">Métricas por campaña · todas las plataformas</p>
        </div>
        <div className="flex gap-2">
          {PLATFORMS.map((p) => (
            <button key={p} onClick={() => syncPlatform(p)} disabled={!!syncing}
              className="btn-secondary text-xs py-2 px-3">
              <RefreshCw size={12} className={syncing === p ? "animate-spin" : ""} />
              {PLATFORM_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {/* Summary row */}
      {!loading && displayed.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Inversión total",  value: fMoney(totals.spend) },
            { label: "Clicks",           value: fNum(totals.clicks) },
            { label: "Conversiones",     value: fNum(totals.conversions) },
          ].map(({ label, value }) => (
            <div key={label} className="card p-4">
              <p className="text-xs text-slate-500 mb-1">{label}</p>
              <p className="text-xl font-bold text-slate-900">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="card p-4 flex flex-wrap gap-3 items-center">
        {/* Platform filter */}
        <div className="flex gap-1.5 flex-wrap">
          {["all", ...PLATFORMS].map((p) => (
            <button key={p} onClick={() => setFilter(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 ${
                filterPlatform === p
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}>
              {p === "all" ? "Todas" : PLATFORM_LABELS[p]}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar campaña..." className="input pl-8 py-2 text-xs" />
        </div>

        {/* Sort */}
        <div className="flex items-center gap-2">
          <select
            value={`${sortKey}-${sortDir}`}
            onChange={(e) => {
              const [k, d] = e.target.value.split("-") as [SortKey, SortDir];
              setSortKey(k);
              setSortDir(d);
            }}
            className="input py-2 text-xs pr-8"
          >
            <option value="spend-desc">Inversión ↓</option>
            <option value="spend-asc">Inversión ↑</option>
            <option value="clicks-desc">Clicks ↓</option>
            <option value="clicks-asc">Clicks ↑</option>
            <option value="ctr-desc">CTR ↓</option>
            <option value="ctr-asc">CTR ↑</option>
            <option value="conversions-desc">Conv. ↓</option>
            <option value="conversions-asc">Conv. ↑</option>
            <option value="roas-desc">ROAS ↓</option>
            <option value="roas-asc">ROAS ↑</option>
          </select>
        </div>

        {/* Date range */}
        <div className="flex items-center gap-2">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="input py-2 text-xs w-36" />
          <span className="text-slate-400 text-xs">→</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="input py-2 text-xs w-36" />
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/50">
              <th className="table-th">Plataforma</th>
              <th className="table-th">Campaña</th>
              <th className="table-th">Fecha</th>
              <th className="table-th">Inversión</th>
              <th className="table-th">Clicks</th>
              <th className="table-th">CTR</th>
              <th className="table-th">Conv.</th>
              <th className="table-th">ROAS</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
              : displayed.length === 0
              ? (
                <tr>
                  <td colSpan={8} className="px-6 py-14 text-center">
                    <p className="text-sm text-slate-400">Sin datos para este rango</p>
                    <p className="text-xs text-slate-300 mt-1">Sincronizá una plataforma o ajustá las fechas</p>
                  </td>
                </tr>
              )
              : displayed.map((m, i) => (
                <tr key={i} className="table-tr">
                  <td className="table-td"><PlatformBadge platform={m.platform} /></td>
                  <td className="table-td max-w-[220px]">
                    <span className="truncate block font-medium text-slate-800" title={m.campaign_name}>
                      {m.campaign_name}
                    </span>
                  </td>
                  <td className="table-td text-slate-400 text-xs">{m.date}</td>
                  <td className="table-td font-semibold">${m.spend.toLocaleString('es-UY')}</td>
                  <td className="table-td">{fNum(m.clicks)}</td>
                  <td className="table-td">
                    <span className={`text-xs font-medium ${m.ctr > 3 ? "text-emerald-600" : m.ctr > 1 ? "text-slate-600" : "text-red-500"}`}>
                      {m.ctr.toFixed(2)}%
                    </span>
                  </td>
                  <td className="table-td">{m.conversions}</td>
                  <td className="table-td"><RoasBadge roas={m.roas} /></td>
                </tr>
              ))}
          </tbody>
        </table>

        {!loading && displayed.length > 0 && (
          <div className="px-4 py-3 border-t border-slate-50 bg-slate-50/30">
            <p className="text-xs text-slate-400">
              {displayed.length} campañas · ${totals.spend.toLocaleString('es-UY')} de inversión total
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
