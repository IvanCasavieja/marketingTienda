"use client";
import { useMemo, useRef } from "react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export interface MesSel { year: number; month: number }

/**
 * Selector de período de los pedidos de Redexpres (Ivan, 08/10/2026): un select
 * de AÑO arriba y las 12 pastillas Enero..Diciembre sin año, en vez de una
 * pastilla por cada mes-año que existe ("Enero 2026", "Febrero 2026"...), que
 * crecía sin límite. La planilla es la misma todos los meses.
 *
 * Un mes que todavía no existe para ese año (no hay filas en la base) se ve
 * apagado. Quien puede crear meses (`onCrear`, los superusuarios) lo crea con
 * un clic y queda la hoja en blanco; para las sucursales queda deshabilitado.
 * Abrir un mes no se puede deshacer y les aparece a todos los locales: antes
 * se pregunta (H-009), y si falla no se salta a ese mes.
 */
export default function SelectorMes({
  meses, seleccionado, onSeleccionar, onCrear,
}: {
  meses: MesSel[];
  seleccionado: MesSel | null;
  onSeleccionar: (m: MesSel) => void;
  /** Si viene, un mes inexistente se puede crear con un clic. */
  onCrear?: (m: MesSel) => Promise<void>;
}) {
  const { t } = useTranslation();
  const nombres = t("redexpres.months", { returnObjects: true }) as string[];
  const anioActual = new Date().getFullYear();
  const anio = seleccionado?.year ?? anioActual;
  // Un doble clic en un mes punteado no tiene que preguntar (ni crear) dos veces.
  const creando = useRef(false);

  const anios = useMemo(() => {
    const existentes = meses.map((m) => m.year);
    const desde = Math.min(2024, ...existentes);
    const hasta = Math.max(anioActual + 2, anio, ...existentes);
    return Array.from({ length: hasta - desde + 1 }, (_, i) => desde + i);
  }, [meses, anio, anioActual]);

  const existe = (y: number, m: number) => meses.some((x) => x.year === y && x.month === m);

  // Al cambiar de año se queda en el mismo mes si existe; si no, en el último que haya.
  function cambiarAnio(y: number) {
    const mes = seleccionado?.month ?? new Date().getMonth() + 1;
    if (existe(y, mes)) return onSeleccionar({ year: y, month: mes });
    const delAnio = meses.filter((x) => x.year === y);
    if (delAnio.length) return onSeleccionar(delAnio[delAnio.length - 1]);
    onSeleccionar({ year: y, month: mes });
  }

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <select
        value={anio}
        onChange={(e) => cambiarAnio(Number(e.target.value))}
        aria-label={t("redexpres.anio")}
        className="input text-sm w-24"
      >
        {anios.map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
      <div className="flex gap-1.5 flex-wrap">
        {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => {
          const hay = existe(anio, m);
          const activo = seleccionado?.year === anio && seleccionado?.month === m;
          const clickeable = hay || !!onCrear;
          return (
            <button
              key={m}
              disabled={!clickeable}
              title={hay ? undefined : onCrear ? t("redexpres.crearMesAqui") : t("redexpres.mesNoHabilitado")}
              onClick={async () => {
                if (!hay && onCrear) {
                  if (creando.current) return;
                  creando.current = true;
                  try {
                    if (!window.confirm(t("redexpres.confirmarCrearMes", { mes: nombres[m], year: anio }))) return;
                    await onCrear({ year: anio, month: m });
                  } catch {
                    return; // el error ya lo avisó quien crea el mes
                  } finally {
                    creando.current = false;
                  }
                }
                onSeleccionar({ year: anio, month: m });
              }}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                activo
                  ? "bg-brand-600 text-white shadow-sm"
                  : hay
                    ? "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
                    : clickeable
                      ? "bg-transparent border border-dashed border-slate-400 dark:border-slate-600 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                      : "bg-transparent text-slate-500 dark:text-slate-400 cursor-not-allowed",
              )}
            >
              {nombres[m]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
