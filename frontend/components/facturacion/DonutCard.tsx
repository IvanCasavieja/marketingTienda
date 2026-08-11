"use client";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { fMoney } from "@/lib/format";

// Único componente nuevo reutilizable de Facturación (se usa 3 veces: torta
// general, presupuesto y canjes) -- replica el patrón exacto de la torta
// "Inversión por objetivo de funnel" en dashboard/page.tsx (Pie con
// innerRadius/outerRadius/paddingAngle/strokeWidth, leyenda armada a mano,
// sin <Legend> de recharts).

export interface DonutDatum {
  key: string;
  label: string;
  value: number;
  color: string;
}

interface DonutCardProps {
  title: string;
  subtitle: string;
  data: DonutDatum[];
  loading?: boolean;
  emptyLabel?: string;
  valueFormatter?: (v: number) => string;
  /** Contenido extra dentro de la misma card, debajo del gráfico -- lo usa
   * la torta de presupuesto para el ledger de entradas/salidas. */
  children?: React.ReactNode;
}

export default function DonutCard({ title, subtitle, data, loading, emptyLabel, valueFormatter = fMoney, children }: DonutCardProps) {
  const total = data.reduce((acc, d) => acc + d.value, 0);
  const visible = data.filter((d) => d.value > 0);

  return (
    <div className="card p-6 h-full">
      <div className="mb-4">
        <p className="section-title">{title}</p>
        <p className="section-sub mt-0.5">{subtitle}</p>
      </div>
      {loading ? (
        <div className="h-52 skeleton rounded-xl" />
      ) : visible.length === 0 ? (
        <div className="h-52 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm text-center px-4">
          {emptyLabel}
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row items-center gap-6">
          <div className="w-full sm:w-44 h-[190px] shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={visible}
                  dataKey="value"
                  nameKey="label"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={2}
                  strokeWidth={0}
                >
                  {visible.map((entry) => (
                    <Cell key={entry.key} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, _name, item: any) => [
                    valueFormatter(value), item.payload.label,
                  ]}
                  contentStyle={{ borderRadius: 12, border: "1px solid #f1f5f9", fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="flex-1 w-full space-y-2.5">
            {visible.map((d) => (
              <div key={d.key} className="flex items-center gap-3">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1 truncate">{d.label}</span>
                <span className="text-xs text-slate-400 w-12 shrink-0 text-right">
                  {total > 0 ? `${((d.value / total) * 100).toFixed(0)}%` : "—"}
                </span>
                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200 w-24 shrink-0 text-right">
                  {valueFormatter(d.value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      {!loading && children}
    </div>
  );
}
