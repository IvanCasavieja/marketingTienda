"use client";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types";

interface Props {
  data: { platform: string; spend: number; roas: number }[];
}

export default function SpendByPlatform({ data }: Props) {
  const formatted = data.map((d) => ({
    ...d,
    name: PLATFORM_LABELS[d.platform] || d.platform,
    fill: PLATFORM_COLORS[d.platform] || "#6366f1",
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={formatted} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${v.toLocaleString()}`} />
        <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Inversión"]} />
        <Bar dataKey="spend" radius={[4, 4, 0, 0]}>
          {formatted.map((entry, i) => (
            <rect key={i} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
