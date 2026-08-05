// ── Colores por cadena ────────────────────────────────────────────────────────
// Compartido entre la página de precios y el modal de comparación — no puede
// vivir en page.tsx porque Next.js no permite named exports extra en un Page.

export const CADENA_CONFIG: Record<string, { bg: string; dot: string; label: string; border: string; hex: string }> = {
  "Disco":     { bg: "bg-blue-500/10 text-blue-600 dark:text-blue-400",         dot: "bg-blue-500",    label: "Disco",     border: "border-l-blue-500",    hex: "#3b82f6" },
  "Devoto":    { bg: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400", dot: "bg-emerald-500", label: "Devoto",    border: "border-l-emerald-500", hex: "#10b981" },
  "Geant":     { bg: "bg-violet-500/10 text-violet-600 dark:text-violet-400",    dot: "bg-violet-500",  label: "Géant",     border: "border-l-violet-500",  hex: "#8b5cf6" },
  "GDU":       { bg: "bg-blue-500/10 text-blue-600 dark:text-blue-400",         dot: "bg-blue-500",    label: "Disco / Devoto / Géant", border: "border-l-blue-500", hex: "#3b82f6" },
  "Ta-Ta":     { bg: "bg-rose-500/10 text-rose-600 dark:text-rose-400",          dot: "bg-rose-500",    label: "Ta-Ta",     border: "border-l-rose-500",    hex: "#f43f5e" },
  "ElDorado":  { bg: "bg-amber-500/10 text-amber-600 dark:text-amber-400",       dot: "bg-amber-500",   label: "El Dorado", border: "border-l-amber-500",   hex: "#f59e0b" },
  "FarmaShop": { bg: "bg-teal-500/10 text-teal-600 dark:text-teal-400",          dot: "bg-teal-500",    label: "FarmaShop", border: "border-l-teal-500",    hex: "#14b8a6" },
  "Botiga":    { bg: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400", dot: "bg-fuchsia-500", label: "Botiga",    border: "border-l-fuchsia-500",  hex: "#d946ef" },
  "Pigalle":   { bg: "bg-purple-500/10 text-purple-600 dark:text-purple-400",   dot: "bg-purple-500",  label: "Pigalle",   border: "border-l-purple-500",  hex: "#a855f7" },
  "Fama":         { bg: "bg-sky-500/10 text-sky-600 dark:text-sky-400",         dot: "bg-sky-500",     label: "Fama",         border: "border-l-sky-500",     hex: "#0ea5e9" },
  "Stienda":      { bg: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400", dot: "bg-indigo-500",  label: "Stienda",      border: "border-l-indigo-500",  hex: "#6366f1" },
  "BlackDog":     { bg: "bg-stone-500/10 text-stone-600 dark:text-stone-400",    dot: "bg-stone-500",   label: "Black Dog",    border: "border-l-stone-500",   hex: "#78716c" },
  "CoverCompany": { bg: "bg-orange-500/10 text-orange-600 dark:text-orange-400", dot: "bg-orange-500",  label: "Cover Company", border: "border-l-orange-500", hex: "#f97316" },
  "DIMM":         { bg: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",       dot: "bg-cyan-500",    label: "DIMM",         border: "border-l-cyan-500",    hex: "#06b6d4" },
  "Electrohogar": { bg: "bg-lime-500/10 text-lime-600 dark:text-lime-400",       dot: "bg-lime-500",    label: "Electrohogar", border: "border-l-lime-500",    hex: "#84cc16" },
  "LOi":          { bg: "bg-pink-500/10 text-pink-600 dark:text-pink-400",       dot: "bg-pink-500",    label: "LOi",          border: "border-l-pink-500",    hex: "#ec4899" },
  "Zona Tecno":     { bg: "bg-red-500/10 text-red-600 dark:text-red-400",         dot: "bg-red-500",     label: "Zona Tecno",     border: "border-l-red-500",     hex: "#ef4444" },
  "AMV":            { bg: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400", dot: "bg-yellow-500",  label: "AMV",            border: "border-l-yellow-500",  hex: "#eab308" },
  "Estación Hogar": { bg: "bg-green-500/10 text-green-600 dark:text-green-400",   dot: "bg-green-500",   label: "Estación Hogar", border: "border-l-green-500",   hex: "#22c55e" },
};

// Agrupación usada para ordenar los chips de filtro en /precios — con 14
// cadenas sueltas es difícil escanear, agrupadas por rubro se entiende de un vistazo.
export const CADENA_CATEGORIA: Record<string, string> = {
  "Disco": "Supermercados", "Devoto": "Supermercados", "Geant": "Supermercados",
  "Ta-Ta": "Supermercados", "ElDorado": "Supermercados", "GDU": "Supermercados",
  "FarmaShop": "Farmacia", "Botiga": "Farmacia", "Pigalle": "Farmacia",
  "Fama": "Electrónica", "Stienda": "Electrónica", "BlackDog": "Electrónica",
  "CoverCompany": "Electrónica", "DIMM": "Electrónica", "Electrohogar": "Electrónica",
  "LOi": "Electrónica",
  "Zona Tecno": "Electrónica", "AMV": "Electrónica", "Estación Hogar": "Electrónica",
};

export function CadenaBadge({ tienda }: { tienda: string }) {
  const cfg = CADENA_CONFIG[tienda];
  if (!cfg) return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">
      {tienda}
    </span>
  );
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full ${cfg.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}
