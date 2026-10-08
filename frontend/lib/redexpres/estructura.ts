"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { redexpresApi, type PlanillaRow } from "@/lib/api";

/**
 * La planilla de pedidos de cada mes es editable (Ivan, 08/10/2026): grupos y
 * columnas con su tope viven en la base y los arma quien gestiona Redexpres.
 * Este archivo es lo que comparten "Mi pedido" y la planilla general.
 * Espejo de backend/app/services/redexpres_estructura.py.
 */
export interface ColumnaEstructura { key: string; label: string; max?: number; texto?: boolean }
export interface GrupoEstructura { id: string; label: string; color: string; cols: ColumnaEstructura[] }
export interface Estructura { grupos: GrupoEstructura[] }

/** Los campos que ya existían en la tabla; el resto va en `extras`. */
export const CAMPOS_FIJOS = new Set([
  "a4_oferta_vertical", "cenefa_oferta_x3", "pinchos", "afiche_54x74",
  "cenefa_valle_del_sol", "cenefa_supremo_hogar",
  "bombas_3xa4", "bombas_a4", "bombas_74x54", "pinchos_bombas",
  "sticker_valle_del_sol", "sticker_carne",
  "cenefas_preciazos", "cenefas_a4_preciazos", "afiche_super_ahorro", "afiche_grande_preciazos",
  "pinchos_dias_expres", "hojas_amarillas", "otros",
]);

// Clases escritas completas: Tailwind no ve las que se arman con texto.
export const COLORES_GRUPO: Record<string, string> = {
  blue: "bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-300",
  purple: "bg-purple-100 dark:bg-purple-500/20 text-purple-800 dark:text-purple-300",
  orange: "bg-orange-100 dark:bg-orange-500/20 text-orange-800 dark:text-orange-300",
  pink: "bg-pink-100 dark:bg-pink-500/20 text-pink-800 dark:text-pink-300",
  emerald: "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300",
  amber: "bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300",
  sky: "bg-sky-100 dark:bg-sky-500/20 text-sky-800 dark:text-sky-300",
  rose: "bg-rose-100 dark:bg-rose-500/20 text-rose-800 dark:text-rose-300",
  slate: "bg-slate-100 dark:bg-slate-500/20 text-slate-700 dark:text-slate-300",
};

export interface GrupoVista {
  label: string;
  color: string;
  cols: { key: string; label: string; max?: number; isText?: boolean }[];
}

/** La estructura del mes elegido, lista para dibujar, y cómo recargarla. */
export function useEstructura(sel: { year: number; month: number } | null) {
  const [estructura, setEstructura] = useState<Estructura | null>(null);
  const [puedeEditar, setPuedeEditar] = useState(false);

  const recargar = useCallback(async () => {
    if (!sel) { setEstructura(null); return; }
    try {
      const { data } = await redexpresApi.getEstructura(sel.year, sel.month);
      setEstructura(data.estructura);
      setPuedeEditar(data.puede_editar);
    } catch {
      setEstructura(null);
    }
  }, [sel?.year, sel?.month]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { recargar(); }, [recargar]);

  const grupos: GrupoVista[] = useMemo(
    () => (estructura?.grupos ?? []).map((g) => ({
      label: g.label,
      color: COLORES_GRUPO[g.color] ?? COLORES_GRUPO.slate,
      cols: g.cols.map((c) => ({ key: c.key, label: c.label, max: c.max, isText: !!c.texto })),
    })),
    [estructura],
  );

  return { estructura, grupos, puedeEditar, recargar };
}

/** El valor de una columna en una fila: el campo fijo o, si no, `extras`. */
export function valorDeColumna(row: PlanillaRow, key: string): string {
  const v = CAMPOS_FIJOS.has(key) ? (row as any)[key] : row.extras?.[key];
  return v !== null && v !== undefined ? String(v) : "";
}

/** Lo editado de una fila, listo para el PATCH: campos fijos arriba, columnas nuevas en `extras`. */
export function payloadDeEdicion(
  ediciones: Record<string, string>,
  esTexto: (key: string) => boolean,
): Record<string, unknown> {
  const payload: Record<string, any> = {};
  const extras: Record<string, number | string | null> = {};
  for (const [key, val] of Object.entries(ediciones)) {
    let valor: number | string | null;
    if (esTexto(key) || key === "otros") {
      valor = val === "" ? null : val;
    } else {
      const n = val === "" ? null : parseInt(val, 10);
      valor = n === null || isNaN(n) ? null : n;
    }
    if (CAMPOS_FIJOS.has(key)) payload[key] = valor; else extras[key] = valor;
  }
  if (Object.keys(extras).length) payload.extras = extras;
  return payload;
}
