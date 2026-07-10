"use client";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { pctChange } from "@/lib/period";

interface DeltaBadgeProps {
  curr: number;
  prev: number;
  variant?: "pill" | "compact";
}

/** Badge de variación % entre dos valores — variant "pill" (KPI cards, fondo
 * de color) o "compact" (▲/▼ chico, para celdas de tabla). Devuelve null si
 * prev es 0 (variación no definida). */
export default function DeltaBadge({ curr, prev, variant = "compact" }: DeltaBadgeProps) {
  const delta = pctChange(curr, prev);
  if (delta === undefined) return null;
  const up = delta >= 0;

  if (variant === "pill") {
    return (
      <span className={`flex items-center gap-0.5 text-xs font-semibold px-2 py-0.5 rounded-full ${
        up ? "text-emerald-600 bg-emerald-50" : "text-red-500 bg-red-50"
      }`}>
        {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
        {Math.abs(delta).toFixed(1)}%
      </span>
    );
  }

  return (
    <span className={`ml-1 text-[10px] font-semibold ${up ? "text-emerald-600" : "text-red-500"}`}>
      {up ? "▲" : "▼"}{Math.abs(delta).toFixed(0)}%
    </span>
  );
}
