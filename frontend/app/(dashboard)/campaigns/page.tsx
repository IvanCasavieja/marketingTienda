"use client";
import { useEffect, useState, useMemo, useRef } from "react";
import { metricsApi } from "@/lib/api";
import { CampaignMetric, PLATFORM_LABELS } from "@/types";
import { format, subDays, subYears } from "date-fns";
import { RefreshCw, Search, TrendingUp, TrendingDown, Minus, Download } from "lucide-react";
import { toast } from "sonner";
import PlatformBadge from "@/components/ui/PlatformBadge";
import { SkeletonRow } from "@/components/ui/SkeletonCard";
import { fNum, fMoney, fMoneyExact } from "@/lib/format";
import { useTranslation } from "react-i18next";

const PLATFORMS = ["meta", "google_ads", "tiktok", "dv360"] as const;
// Meta Ads: sync manual pausado — conexión eliminada (2026-07-06), la data
// que se ve en pantalla es un fixture fijo. Reactivar agregando "meta" acá
// de nuevo una vez restablecida la conexión real (ver metrics_service.py).
const SYNC_PLATFORMS = PLATFORMS.filter((p) => p !== "meta");

type SortKey = "spend" | "clicks" | "ctr" | "roas" | "conversions" | "cpa";
type SortDir = "asc" | "desc";

function RoasBadge({ roas }: { roas: number }) {
  if (roas >= 3)   return <span className="badge badge-green flex items-center gap-1"><TrendingUp size={10} />{roas.toFixed(2)}x</span>;
  if (roas >= 1.5) return <span className="badge badge-yellow flex items-center gap-1"><Minus size={10} />{roas.toFixed(2)}x</span>;
  return             <span className="badge badge-red flex items-center gap-1"><TrendingDown size={10} />{roas.toFixed(2)}x</span>;
}

export default function CampaignsPage() {
  const { t } = useTranslation();
  const [metrics, setMetrics]           = useState<CampaignMetric[]>([]);
  const [loading, setLoading]           = useState(true);
  const [syncing, setSyncing]           = useState<string | null>(null);
  const [filterPlatform, setFilter]     = useState("all");
  const [search, setSearch]             = useState("");
  const [sortKey, setSortKey]           = useState<SortKey>("spend");
  const [sortDir, setSortDir]           = useState<SortDir>("desc");
  const [dateFrom, setDateFrom]         = useState("");
  const [dateTo, setDateTo]             = useState("");
  const [comparing, setComparing]       = useState(false);
  const [cmpFrom, setCmpFrom]           = useState("");
  const [cmpTo, setCmpTo]               = useState("");
  const [cmpMetrics, setCmpMetrics]     = useState<CampaignMetric[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; key: string } | null>(null);

  async function loadMetrics() {
    setLoading(true);
    const pf = filterPlatform !== "all" ? filterPlatform : undefined;
    try {
      const reqs = [metricsApi.getMetrics(dateFrom, dateTo, pf)];
      if (comparing) reqs.push(metricsApi.getMetrics(cmpFrom, cmpTo, pf));
      const [main, cmp] = await Promise.all(reqs);
      setMetrics(main.data);
      setCmpMetrics(cmp ? cmp.data : []);
    } catch {
      toast.error(t("campaigns.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const today = format(new Date(), "yyyy-MM-dd");
    const d30   = format(subDays(new Date(), 30), "yyyy-MM-dd");
    const d60   = format(subDays(new Date(), 60), "yyyy-MM-dd");
    const d31   = format(subDays(new Date(), 31), "yyyy-MM-dd");
    setDateFrom(d30);
    setDateTo(today);
    setCmpFrom(d60);
    setCmpTo(d31);
  }, []);

  useEffect(() => {
    if (!dateFrom || !dateTo) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => loadMetrics(), 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [dateFrom, dateTo, filterPlatform, comparing, cmpFrom, cmpTo]);

  async function syncPlatform(platform: string) {
    setSyncing(platform);
    try {
      const { data } = await metricsApi.sync(platform, dateFrom, dateTo);
      toast.success(t("campaigns.syncSuccess", { platform: PLATFORM_LABELS[platform], n: data.records_saved }));
      await loadMetrics();
    } catch {
      toast.error(t("campaigns.syncError", { platform: PLATFORM_LABELS[platform] }));
    } finally {
      setSyncing(null);
    }
  }

  function exportCSV() {
    const headers = [
      t("campaigns.tableHeaders.platform"),
      t("campaigns.tableHeaders.campaign"),
      t("campaigns.tableHeaders.date"),
      t("campaigns.tableHeaders.investment"),
      t("campaigns.tableHeaders.clicks"),
      "CTR%",
      t("campaigns.tableHeaders.conv"),
      t("campaigns.tableHeaders.roas"),
    ];
    const rows = displayed.map((m) => [
      m.platform, m.campaign_name, m.date,
      m.spend.toFixed(2), m.clicks, m.ctr.toFixed(2), m.conversions, m.roas.toFixed(2),
    ]);
    const csv = [headers, ...rows].map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `campanas_${dateFrom}_${dateTo}.csv`; a.click();
    URL.revokeObjectURL(url);
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  }

  const displayed = useMemo(() => {
    let rows = [...metrics];
    if (search) rows = rows.filter((m) => m.campaign_name.toLowerCase().includes(search.toLowerCase()));
    rows.sort((a, b) => {
      const getVal = (m: CampaignMetric) =>
        sortKey === "cpa"
          ? (m.conversions > 0 ? m.spend / m.conversions : Infinity)
          : m[sortKey as keyof CampaignMetric] as number;
      return sortDir === "desc" ? getVal(b) - getVal(a) : getVal(a) - getVal(b);
    });
    return rows;
  }, [metrics, search, sortKey, sortDir]);

  const totals = useMemo(() => displayed.reduce(
    (acc, m) => ({
      spend: acc.spend + m.spend,
      clicks: acc.clicks + m.clicks,
      conversions: acc.conversions + m.conversions,
      impressions: acc.impressions + m.impressions,
    }),
    { spend: 0, clicks: 0, conversions: 0, impressions: 0 }
  ), [displayed]);

  const currentByCampaign = useMemo(() => {
    const map: Record<string, { spend: number; clicks: number; conversions: number }> = {};
    metrics.forEach((m) => {
      const key = `${m.platform}::${m.campaign_name}`;
      if (!map[key]) map[key] = { spend: 0, clicks: 0, conversions: 0 };
      map[key].spend += m.spend;
      map[key].clicks += m.clicks;
      map[key].conversions += m.conversions;
    });
    return map;
  }, [metrics]);

  const cmpByCampaign = useMemo(() => {
    const map: Record<string, { spend: number; clicks: number; conversions: number }> = {};
    cmpMetrics.forEach((m) => {
      const key = `${m.platform}::${m.campaign_name}`;
      if (!map[key]) map[key] = { spend: 0, clicks: 0, conversions: 0 };
      map[key].spend += m.spend;
      map[key].clicks += m.clicks;
      map[key].conversions += m.conversions;
    });
    return map;
  }, [cmpMetrics]);

  const cmpTotals = useMemo(() => cmpMetrics.reduce(
    (acc, m) => ({
      spend: acc.spend + m.spend,
      clicks: acc.clicks + m.clicks,
      conversions: acc.conversions + m.conversions,
      impressions: acc.impressions + m.impressions,
    }),
    { spend: 0, clicks: 0, conversions: 0, impressions: 0 }
  ), [cmpMetrics]);

  function pct(curr: number, prev: number) {
    if (prev === 0) return null;
    return ((curr - prev) / prev) * 100;
  }

  function DeltaBadge({ curr, prev }: { curr: number; prev: number }) {
    const delta = pct(curr, prev);
    if (delta === null) return null;
    const up = delta >= 0;
    return (
      <span className={`text-[10px] font-semibold ${up ? "text-emerald-600" : "text-red-500"}`}>
        {up ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
      </span>
    );
  }


  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">{t("campaigns.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("campaigns.subtitle")}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {SYNC_PLATFORMS.map((p) => (
            <button key={p} onClick={() => syncPlatform(p)} disabled={!!syncing}
              className="btn-secondary text-xs py-2 px-3">
              <RefreshCw size={12} className={syncing === p ? "animate-spin" : ""} />
              {PLATFORM_LABELS[p]}
            </button>
          ))}
          {displayed.length > 0 && (
            <button onClick={exportCSV} className="btn-secondary text-xs py-2 px-3">
              <Download size={12} /> {t("campaigns.exportCsv")}
            </button>
          )}
        </div>
      </div>

      {/* Summary row */}
      {!loading && displayed.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
            {[
              { label: t("campaigns.totalInvestment"), curr: totals.spend,       prev: cmpTotals.spend,       fmt: fMoney },
              { label: t("campaigns.clicks"),          curr: totals.clicks,      prev: cmpTotals.clicks,      fmt: fNum },
              { label: t("campaigns.conversions"),     curr: totals.conversions, prev: cmpTotals.conversions, fmt: fNum },
              {
                label: "CPA promedio",
                curr: totals.conversions > 0 ? totals.spend / totals.conversions : 0,
                prev: cmpTotals.conversions > 0 ? cmpTotals.spend / cmpTotals.conversions : 0,
                fmt: (v: number) => v > 0 ? `$${v.toFixed(2)}` : "—",
              },
            ].map(({ label, curr, prev, fmt }) => (
              <div key={label} className="card p-4">
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">{label}</p>
                <div className="flex items-end gap-2">
                  <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{fmt(curr)}</p>
                  {comparing && cmpTotals.spend > 0 && <DeltaBadge curr={curr} prev={prev} />}
                </div>
                {comparing && cmpTotals.spend > 0 && (
                  <p className="text-xs text-slate-400 mt-0.5">{fmt(prev)} {t("campaigns.prevPeriod")}</p>
                )}
                {comparing && cmpTotals.spend === 0 && (
                  <p className="text-xs text-slate-300 dark:text-slate-600 mt-0.5">Sin datos del período anterior</p>
                )}
              </div>
            ))}
          </div>
        </>
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
                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}>
              {p === "all" ? t("common.allPlatforms") : PLATFORM_LABELS[p]}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder={t("campaigns.searchPlaceholder")} className="input pl-8 py-2 text-xs" />
        </div>

        {/* Sort */}
        <div className="flex items-center gap-1">
          <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="input py-2 text-xs pr-8">
            <option value="spend">{t("campaigns.sortOptions.investment")}</option>
            <option value="clicks">{t("campaigns.sortOptions.clicks")}</option>
            <option value="ctr">{t("campaigns.sortOptions.ctr")}</option>
            <option value="conversions">{t("campaigns.sortOptions.conversions")}</option>
            <option value="roas">{t("campaigns.sortOptions.roas")}</option>
            <option value="cpa">CPA</option>
          </select>
          <button onClick={() => setSortDir(d => d === "desc" ? "asc" : "desc")}
            className="input py-2 px-3 text-xs font-medium hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            {sortDir === "desc" ? "↓" : "↑"}
          </button>
        </div>

        {/* Date range */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex gap-1">
              {[{l:"7D",d:7},{l:"30D",d:30},{l:"90D",d:90}].map(({l,d}) => (
                <button key={d}
                  onClick={() => { setDateFrom(format(subDays(new Date(), d), "yyyy-MM-dd")); setDateTo(format(new Date(), "yyyy-MM-dd")); }}
                  className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
                  {l}
                </button>
              ))}
            </div>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
              className="input py-2 text-xs w-36" />
            <span className="text-slate-400 text-xs">→</span>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
              className="input py-2 text-xs w-36" />
            <button onClick={() => setComparing(c => !c)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 ${
                comparing ? "bg-brand-600 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}>
              {t("campaigns.compare")}
            </button>
          </div>
          {comparing && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-slate-400 w-[calc(3*2.5rem+0.5rem)]">vs.</span>
              <input type="date" value={cmpFrom} onChange={(e) => setCmpFrom(e.target.value)}
                className="input py-2 text-xs w-36 border-dashed" />
              <span className="text-slate-400 text-xs">→</span>
              <input type="date" value={cmpTo} onChange={(e) => setCmpTo(e.target.value)}
                className="input py-2 text-xs w-36 border-dashed" />
              <button onClick={() => { setCmpFrom(format(subYears(new Date(dateFrom), 1), "yyyy-MM-dd")); setCmpTo(format(subYears(new Date(dateTo), 1), "yyyy-MM-dd")); }}
                className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors">
                {t("campaigns.prevYear")}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden flex flex-col">
        <div className="overflow-x-auto overflow-y-auto max-h-[calc(100svh-22rem)]">
        <table className="w-full min-w-[640px]">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
              <th className="table-th">{t("campaigns.tableHeaders.platform")}</th>
              <th className="table-th">{t("campaigns.tableHeaders.campaign")}</th>
              <th className="table-th">{t("campaigns.tableHeaders.date")}</th>
              <th className="table-th">{t("campaigns.tableHeaders.investment")}</th>
              <th className="table-th">{t("campaigns.tableHeaders.clicks")}</th>
              <th className="table-th">{t("campaigns.tableHeaders.ctr")}</th>
              <th className="table-th">CPM</th>
              <th className="table-th">{t("campaigns.tableHeaders.conv")}</th>
              <th className="table-th">CPA</th>
              <th className="table-th">{t("campaigns.tableHeaders.roas")}</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
              : displayed.length === 0
              ? (
                <tr>
                  <td colSpan={10} className="px-6 py-14 text-center">
                    <p className="text-sm text-slate-400">{t("campaigns.noData")}</p>
                    <p className="text-xs text-slate-300 mt-1">{t("campaigns.noDataSub")}</p>
                  </td>
                </tr>
              )
              : displayed.map((m, i) => {
                const cpa = m.conversions > 0 ? m.spend / m.conversions : null;
                return (
                  <tr key={i} className="table-tr"
                    onMouseMove={comparing && cmpMetrics.length > 0 ? (e) => {
                      const cmpKey = `${m.platform}::${m.campaign_name}`;
                      if (cmpByCampaign[cmpKey]) setTooltipPos({ x: e.clientX, y: e.clientY, key: cmpKey });
                    } : undefined}
                    onMouseLeave={comparing && cmpMetrics.length > 0 ? () => setTooltipPos(null) : undefined}
                  >
                    <td className="table-td"><PlatformBadge platform={m.platform} /></td>
                    <td className="table-td max-w-[200px]">
                      <span className="truncate block font-medium text-slate-800 dark:text-slate-200" title={m.campaign_name}>
                        {m.campaign_name}
                      </span>
                    </td>
                    <td className="table-td text-slate-400 text-xs">{m.date}</td>
                    <td className="table-td font-semibold">{fMoneyExact(m.spend)}</td>
                    <td className="table-td">{fNum(m.clicks)}</td>
                    <td className="table-td">
                      <span className={`text-xs font-medium ${m.ctr > 3 ? "text-emerald-600" : m.ctr > 1 ? "text-slate-600 dark:text-slate-400" : "text-red-500"}`}>
                        {m.ctr.toFixed(2)}%
                      </span>
                    </td>
                    <td className="table-td text-slate-500 dark:text-slate-400 text-xs">
                      {m.cpm > 0 ? `$${m.cpm.toFixed(2)}` : "—"}
                    </td>
                    <td className="table-td">{m.conversions}</td>
                    <td className="table-td text-slate-600 dark:text-slate-400 text-xs font-medium">
                      {cpa !== null ? `$${cpa.toFixed(2)}` : "—"}
                    </td>
                    <td className="table-td"><RoasBadge roas={m.roas} /></td>
                  </tr>
                );
              })}
          </tbody>
        </table>
        </div>

        {!loading && displayed.length > 0 && (
          <div className="px-4 py-3 border-t border-slate-50 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/50">
            <p className="text-xs text-slate-400">
              {t("campaigns.footer", { n: displayed.length, spend: fMoneyExact(totals.spend) })}
            </p>
          </div>
        )}
      </div>
      {/* Comparison hover tooltip */}
      {tooltipPos && currentByCampaign[tooltipPos.key] && cmpByCampaign[tooltipPos.key] && (
        <div
          className="fixed z-50 pointer-events-none bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 rounded-xl shadow-xl p-3.5 w-60 text-xs"
          style={{
            left: Math.min(tooltipPos.x + 16, window.innerWidth - 256),
            top: Math.max(tooltipPos.y - 130, 8),
          }}
        >
          <p className="font-semibold text-slate-700 dark:text-slate-300 mb-2 truncate text-[11px]"
            title={tooltipPos.key.split("::")[1]}>
            {tooltipPos.key.split("::")[1]}
          </p>
          {(
            [
              { label: "Inversión", curr: currentByCampaign[tooltipPos.key].spend,       prev: cmpByCampaign[tooltipPos.key].spend,       fmt: (v: number) => `$${v.toFixed(2)}` },
              { label: "Clicks",    curr: currentByCampaign[tooltipPos.key].clicks,       prev: cmpByCampaign[tooltipPos.key].clicks,       fmt: fNum },
              { label: "Conv.",     curr: currentByCampaign[tooltipPos.key].conversions,  prev: cmpByCampaign[tooltipPos.key].conversions,  fmt: fNum },
            ] as Array<{ label: string; curr: number; prev: number; fmt: (v: number) => string }>
          ).map(({ label, curr, prev, fmt }) => {
            const delta = prev > 0 ? ((curr - prev) / prev) * 100 : null;
            return (
              <div key={label} className="flex items-center justify-between mb-1.5">
                <span className="text-slate-400 w-14 shrink-0">{label}</span>
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-slate-400 text-[10px]">{fmt(prev)}</span>
                  <span className="text-slate-300">→</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">{fmt(curr)}</span>
                  {delta !== null && (
                    <span className={`text-[10px] font-bold shrink-0 ${delta >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                      {delta >= 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
            );
          })}
          <p className="text-[10px] text-slate-400 mt-2 pt-2 border-t border-slate-100 dark:border-slate-700">
            Total campaña · período anterior → actual
          </p>
        </div>
      )}
    </div>
  );
}
