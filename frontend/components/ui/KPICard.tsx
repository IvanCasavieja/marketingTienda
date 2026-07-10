"use client";
import DeltaBadge from "@/components/ui/DeltaBadge";

interface KPICardProps {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  curr?: number;
  prev?: number;
  gradient: string;
}

/** Tarjeta de KPI con badge de variación % opcional (curr/prev) — reusada por
 * dashboard/page.tsx y canales/page.tsx. */
export default function KPICard({ label, value, sub, icon, curr, prev, gradient }: KPICardProps) {
  return (
    <div className="card card-hover p-5 animate-slide-up">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center shadow-sm`}>
          {icon}
        </div>
        {curr !== undefined && prev !== undefined && <DeltaBadge curr={curr} prev={prev} variant="pill" />}
      </div>
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-0.5">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>
    </div>
  );
}
