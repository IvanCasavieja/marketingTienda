import { format, subDays, subYears } from "date-fns";
import type { Locale } from "date-fns";

export type CompareMode = "prev_period" | "prev_year" | "custom";

export interface DateRange {
  from: string;
  to: string;
}

/** Calcula el rango de comparación automático para "prev_period"/"prev_year".
 * Para "custom" no hay cálculo automático — el caller maneja su propio estado
 * de fechas con inputs manuales (mismo patrón que ya usaba campaigns/page.tsx
 * antes de esta extracción). */
export function getCompareDates(days: number, mode: CompareMode, customFrom?: string, customTo?: string): DateRange {
  if (mode === "custom") return { from: "", to: "" };

  if (customFrom && customTo) {
    // Rango personalizado: comparar con el mismo rango de días hacia atrás
    const duration = Math.round((new Date(customTo).getTime() - new Date(customFrom).getTime()) / 86400000) + 1;
    if (mode === "prev_year") {
      return {
        from: format(subYears(new Date(customFrom + "T00:00:00"), 1), "yyyy-MM-dd"),
        to:   format(subYears(new Date(customTo   + "T00:00:00"), 1), "yyyy-MM-dd"),
      };
    }
    return {
      from: format(subDays(new Date(customFrom + "T00:00:00"), duration), "yyyy-MM-dd"),
      to:   format(subDays(new Date(customFrom + "T00:00:00"), 1),        "yyyy-MM-dd"),
    };
  }

  if (mode === "prev_year") {
    return {
      from: format(subYears(subDays(new Date(), days), 1), "yyyy-MM-dd"),
      to:   format(subYears(new Date(), 1), "yyyy-MM-dd"),
    };
  }
  return {
    from: format(subDays(new Date(), days * 2), "yyyy-MM-dd"),
    to:   format(subDays(new Date(), days + 1), "yyyy-MM-dd"),
  };
}

export function getCompareLabel(days: number, mode: CompareMode, locale: Locale, customFrom?: string, customTo?: string): string {
  if (mode === "custom") return "";
  const { from, to } = getCompareDates(days, mode, customFrom, customTo);
  const f = format(new Date(from + "T00:00:00"), "d MMM", { locale });
  const t = format(new Date(to   + "T00:00:00"), "d MMM", { locale });
  return `vs. ${f} – ${t}`;
}

export function pctChange(curr: number, prev: number): number | undefined {
  if (prev === 0) return undefined;
  return ((curr - prev) / prev) * 100;
}
