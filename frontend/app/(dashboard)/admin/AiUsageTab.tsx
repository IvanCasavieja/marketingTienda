"use client";
import { useEffect, useMemo, useState } from "react";
import { format, subDays } from "date-fns";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { DollarSign, Cpu, ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import { toast } from "sonner";
import { adminApi, type AiUsageSummary } from "@/lib/api";
import { SkeletonCard } from "@/components/ui/SkeletonCard";

const PERIODS = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

// Mismo criterio que PLATFORM_COLORS/OBJECTIVE_COLORS en el resto de la app:
// color fijo por categoría conocida, nunca generado/ciclado.
const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "#D97757",
  openai:    "#10A37F",
  groq:      "#F55036",
};
const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Claude (Anthropic)",
  openai:    "ChatGPT (OpenAI)",
  groq:      "Llama (Groq)",
};

const FEATURE_COLORS: Record<string, string> = {
  debate:            "#6366f1",
  don_tino_home:     "#f59e0b",
  don_tino_precios:  "#10b981",
};
const FEATURE_LABELS: Record<string, string> = {
  debate:            "La Triada (debate)",
  don_tino_home:     "Don Tino (home)",
  don_tino_precios:  "Don Tino (precios)",
};

// Los formatters de lib/format.ts están pensados para montos en pesos — acá
// los costos de IA suelen ser centavos de dólar, necesitan más precisión.
function fUsd(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

function BreakdownBar({ label, color, value, max }: { label: string; color: string; value: number; max: number }) {
  const widthPct = max > 0 ? Math.max((value / max) * 100, 3) : 3;
  return (
    <div className="flex items-center gap-3">
      <div className="w-36 shrink-0 text-xs text-slate-500 dark:text-slate-400 truncate" title={label}>{label}</div>
      <div className="flex-1 h-6 bg-slate-50 dark:bg-slate-800/60 rounded-lg overflow-hidden">
        <div className="h-full rounded-lg flex items-center justify-end px-2 transition-all duration-500"
          style={{ width: `${widthPct}%`, background: color }}>
        </div>
      </div>
      <div className="w-20 shrink-0 text-xs font-semibold text-slate-700 dark:text-slate-300 text-right">{fUsd(value)}</div>
    </div>
  );
}

export default function AiUsageTab() {
  const [data, setData] = useState<AiUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);

  useEffect(() => { load(period); }, [period]); // eslint-disable-line react-hooks/exhaustive-deps

  async function load(days: number) {
    setLoading(true);
    const today = format(new Date(), "yyyy-MM-dd");
    const from  = format(subDays(new Date(), days), "yyyy-MM-dd");
    try {
      const { data } = await adminApi.aiUsageSummary(from, today);
      setData(data);
    } catch {
      toast.error("No se pudo cargar el uso de IA.");
    } finally {
      setLoading(false);
    }
  }

  const maxProvider = useMemo(() => Math.max(0, ...(data?.by_provider ?? []).map((p) => p.cost_usd)), [data]);
  const maxFeature  = useMemo(() => Math.max(0, ...(data?.by_feature  ?? []).map((f) => f.cost_usd)), [data]);

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} className="h-28" />)}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs text-slate-400">{data.date_from} → {data.date_to}</p>
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

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card p-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-600 flex items-center justify-center shadow-sm mb-3">
            <DollarSign size={18} className="text-white" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{fUsd(data.total_cost_usd)}</p>
          <p className="text-xs text-slate-500 mt-0.5">Costo estimado total</p>
        </div>
        <div className="card p-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center shadow-sm mb-3">
            <ArrowDownToLine size={18} className="text-white" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{data.total_input_tokens.toLocaleString("es-UY")}</p>
          <p className="text-xs text-slate-500 mt-0.5">Tokens de entrada</p>
        </div>
        <div className="card p-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center shadow-sm mb-3">
            <ArrowUpFromLine size={18} className="text-white" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{data.total_output_tokens.toLocaleString("es-UY")}</p>
          <p className="text-xs text-slate-500 mt-0.5">Tokens de salida</p>
        </div>
      </div>

      <div className="card p-6">
        <div className="mb-4">
          <p className="section-title">Costo diario</p>
          <p className="section-sub mt-0.5">Estimado, en USD</p>
        </div>
        {data.daily.length === 0 ? (
          <div className="h-52 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">
            Sin uso de IA registrado en este período.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.daily}>
              <defs>
                <linearGradient id="aiCostGradient" x1="0" y1="0" x2="0" y2="1">
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
                formatter={(v: any) => [fUsd(Number(v)), "Costo"]}
                contentStyle={{ borderRadius: 12, border: "1px solid #f1f5f9", fontSize: 12 }}
              />
              <Area type="monotone" dataKey="cost_usd" stroke="#6366f1" strokeWidth={2} fill="url(#aiCostGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="card p-6">
          <div className="mb-4">
            <p className="section-title">Costo por proveedor</p>
          </div>
          {data.by_provider.length === 0 ? (
            <p className="text-sm text-slate-400">Sin datos.</p>
          ) : (
            <div className="space-y-3">
              {data.by_provider.map((p) => (
                <BreakdownBar key={p.provider} label={PROVIDER_LABELS[p.provider] ?? p.provider}
                  color={PROVIDER_COLORS[p.provider] ?? "#94a3b8"} value={p.cost_usd} max={maxProvider} />
              ))}
            </div>
          )}
        </div>

        <div className="card p-6">
          <div className="mb-4">
            <p className="section-title">Costo por feature</p>
          </div>
          {data.by_feature.length === 0 ? (
            <p className="text-sm text-slate-400">Sin datos.</p>
          ) : (
            <div className="space-y-3">
              {data.by_feature.map((f) => (
                <BreakdownBar key={f.feature} label={FEATURE_LABELS[f.feature] ?? f.feature}
                  color={FEATURE_COLORS[f.feature] ?? "#94a3b8"} value={f.cost_usd} max={maxFeature} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="px-4 sm:px-6 py-4 border-b border-slate-50 dark:border-slate-800 flex items-center gap-2">
          <Cpu size={15} className="text-slate-400" />
          <p className="section-title">Top usuarios por costo</p>
        </div>
        {data.by_user.length === 0 ? (
          <p className="text-sm text-slate-400 px-6 py-6">Sin datos.</p>
        ) : (
          <div className="divide-y divide-slate-50 dark:divide-slate-800">
            {data.by_user.map((u, i) => (
              <div key={u.user_id ?? i} className="flex items-center justify-between px-5 py-2.5">
                <span className="text-sm text-slate-700 dark:text-slate-300">{u.user_email ?? "Usuario eliminado"}</span>
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{fUsd(u.cost_usd)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
