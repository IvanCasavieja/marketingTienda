"use client";
import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Sparkles, X, Check } from "lucide-react";
import { useTranslation } from "react-i18next";

// Una sola puerta para todo lo que Tinín encontró en la grilla.
//
// Antes había tres accesos distintos para la misma conversación: el botón
// "Unificar categorías" (que había que apretar), el cartel de pares parecidos y
// el cartel de filas sin descripción (que aparecían solos). Tres cajas
// compitiendo arriba de la grilla, cada una con su modal, para decir todas lo
// mismo: "encontré algo, mirá".
//
// Ahora es una barra: "encontré N cosas". Se abre y se resuelven de a UNA, con
// Siguiente. Mostrar todo junto de una es lo que vuelve la pantalla ilegible
// para alguien que no la usa todos los días.

export interface ItemTema {
  clave: string;
  texto: string;
  /** Llevar la grilla hasta esa fila. */
  onIr?: () => void;
  /** Acción principal sobre ese item puntual (ej. revisar un par). */
  onRevisar?: () => void;
  revisarEtiqueta?: string;
  /** Descartar ese item sin hacer nada. */
  onDescartar?: () => void;
  descartarEtiqueta?: string;
}

export interface TemaTinin {
  id: string;
  titulo: string;
  detalle: string;
  /** Acción que resuelve el tema entero (ej. generar todas las descripciones). */
  accion?: { etiqueta: string; onClick: () => void };
  items?: ItemTema[];
}

interface Props {
  temas: TemaTinin[];
}

export default function TininRevision({ temas }: Props) {
  const { t } = useTranslation();
  const [abierto, setAbierto] = useState(false);
  const [paso, setPaso] = useState(0);

  // Los temas se recalculan con cada cambio de la grilla: si el que estabas
  // mirando se resolvió y desapareció, el paso guardado queda apuntando al
  // vacío. Se acota al LEERLO en vez de resincronizarlo con un efecto -- así no
  // hay un render intermedio con el índice fuera de rango.
  const total = temas.length;
  const pasoActual = Math.min(paso, Math.max(0, total - 1));
  const actual = temas[pasoActual];
  const resumen = useMemo(
    () => temas.map((x) => x.titulo).join(" · "),
    [temas],
  );

  if (total === 0) {
    return (
      <div className="card px-4 py-2.5 flex items-center gap-2 border-l-4 border-l-emerald-400">
        <Check size={14} className="text-emerald-500 shrink-0" />
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {t("convertidor.tinin.sinTemas")}
        </p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden border-l-4 border-l-brand-400">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="w-full flex items-center gap-2.5 px-4 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
      >
        <Sparkles size={15} className="text-brand-500 shrink-0" />
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-100 shrink-0">
          {t("convertidor.tinin.barra", { count: total })}
        </span>
        <span className="text-xs text-slate-400 truncate flex-1 min-w-0">{resumen}</span>
        <ChevronRight
          size={15}
          className={`text-slate-400 shrink-0 transition-transform ${abierto ? "rotate-90" : ""}`}
        />
      </button>

      {abierto && actual && (
        <div className="border-t border-slate-100 dark:border-slate-800 px-4 py-3 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {actual.titulo}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{actual.detalle}</p>
            </div>
            <span className="text-[11px] text-slate-400 shrink-0 tabular-nums">
              {t("convertidor.tinin.paso", { actual: pasoActual + 1, total })}
            </span>
          </div>

          {actual.accion && (
            <button
              type="button"
              onClick={actual.accion.onClick}
              className="btn-secondary text-xs flex items-center gap-1.5"
            >
              <Sparkles size={13} /> {actual.accion.etiqueta}
            </button>
          )}

          {actual.items && actual.items.length > 0 && (
            <div className="space-y-1.5 max-h-56 overflow-y-auto">
              {actual.items.map((it) => (
                <div
                  key={it.clave}
                  className="flex items-center justify-between gap-3 flex-wrap text-xs bg-slate-50 dark:bg-slate-800/60 rounded-lg px-3 py-2"
                >
                  <button
                    type="button"
                    onClick={it.onIr}
                    disabled={!it.onIr}
                    className={`min-w-0 truncate text-left text-slate-600 dark:text-slate-300 ${
                      it.onIr ? "hover:text-brand-600 dark:hover:text-brand-400 cursor-pointer" : "cursor-default"
                    }`}
                    title={it.onIr ? t("convertidor.unmatchedNavGo") : undefined}
                  >
                    {it.texto}
                  </button>
                  <div className="flex items-center gap-2 shrink-0">
                    {it.onRevisar && (
                      <button type="button" onClick={it.onRevisar} className="btn-secondary text-[11px] py-1">
                        {it.revisarEtiqueta ?? t("convertidor.merge.review")}
                      </button>
                    )}
                    {it.onDescartar && (
                      <button type="button" onClick={it.onDescartar} className="btn-ghost text-[11px] py-1">
                        {it.descartarEtiqueta ?? t("convertidor.merge.notSameProduct")}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-1">
            <button
              type="button"
              onClick={() => setPaso(Math.max(0, pasoActual - 1))}
              disabled={pasoActual === 0}
              className="btn-ghost text-xs flex items-center gap-1 disabled:opacity-30"
            >
              <ChevronLeft size={13} /> {t("convertidor.tinin.anterior")}
            </button>
            {pasoActual < total - 1 ? (
              <button
                type="button"
                onClick={() => setPaso(pasoActual + 1)}
                className="btn-primary text-xs flex items-center gap-1"
              >
                {t("convertidor.tinin.siguiente")} <ChevronRight size={13} />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setAbierto(false)}
                className="btn-secondary text-xs flex items-center gap-1"
              >
                <X size={13} /> {t("convertidor.tinin.cerrar")}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
