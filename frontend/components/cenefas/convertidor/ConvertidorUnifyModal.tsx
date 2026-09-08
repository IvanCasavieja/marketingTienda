"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Layers, Loader2, Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { convertidorApi, type ConvertidorRow, type UnificarGrupoItem } from "@/lib/api";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { DonTinoTrabajando } from "@/components/DonTinoTrabajando";

interface Props {
  // TODAS las filas de la grilla (matcheadas o no) -- a diferencia de
  // ConvertidorAiModal, acá importa el nombre crudo de cada una, no si ya
  // tiene descripción resuelta.
  rows: ConvertidorRow[];
  onApprove: (grupo: UnificarGrupoItem) => Promise<void>;
  onClose: () => void;
}

type GrupoState = UnificarGrupoItem & {
  status: "pending" | "approving" | "approved" | "error";
  // Se aprobó al menos una vez. Queda en true aunque "Editar" devuelva el grupo
  // a "pending", y sirve para dos cosas: que el botón diga "Guardar cambios" en
  // vez de "Aprobar", y que NO se vuelva a mostrar el aviso de "al aprobar estas
  // N filas se combinan en una sola" -- ya están combinadas, repetirlo mentiría.
  yaAprobado: boolean;
};

// Mismo umbral que ConvertidorAiModal.tsx / DESCRIPTION_WARN_CHARS en
// backend/app/services/cenefas/validation_engine.py.
const DESCRIPTION_WARN_CHARS = 60;

// Cuántos productos se ofrecen a la vez al buscar uno para sumar al grupo.
// El listado entero puede tener cientos de filas: sin tope, abrir el buscador
// sin escribir nada dibujaría toda la grilla adentro de la tarjeta.
const MAX_CANDIDATOS = 8;

export default function ConvertidorUnifyModal({ rows, onApprove, onClose }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<"not_configured" | "generic" | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [grupos, setGrupos] = useState<GrupoState[]>([]);
  // "error" es distinto de un vacío legítimo -- data.error=true significa que el
  // análisis en sí falló (red, JSON cortado, etc.), no que Tinín ya revisó todo
  // y no encontró nada para unificar (ver detectar_grupos_unificables).
  const [analysisError, setAnalysisError] = useState(false);
  // Índice del grupo con el buscador de "agregar producto" abierto (uno a la
  // vez), y el texto tipeado. La búsqueda es una sola para todos: al cerrar y
  // abrir en otra tarjeta arranca limpia.
  const [agregandoEn, setAgregandoEn] = useState<number | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  useEscapeKey(onClose);

  useEffect(() => {
    // Mismo piso mínimo que ConvertidorAiModal.tsx -- nunca corta la
    // animación antes de que la IA real termine, solo evita que se sienta
    // cortada cuando la respuesta llega muy rápido.
    const MIN_LOADING_MS = 6000;
    const start = Date.now();
    const finishLoading = () => {
      const remaining = Math.max(0, MIN_LOADING_MS - (Date.now() - start));
      setTimeout(() => {
        if (mountedRef.current) setLoading(false);
      }, remaining);
    };

    convertidorApi
      .unificarCategoriasIA(
        rows.map((r) => ({
          row_id: r.row_id,
          codigo: r.codigo,
          nombreArticulo: r.nombreArticulo,
          descripcion: r.descripcion,
          // Los precios no se le muestran a Tinín: los usa el backend para
          // descartar del grupo lo que no esté al mismo precio. Cada uno va
          // partido en sus dos columnas, porque comparar solo la entera da
          // $276,75 == $276 (ver _filtrar_por_precio).
          precioRegular: r.precioRegular,
          decimalPrecioRegular: r.decimalPrecioRegular,
          precioOferta: r.precioOferta,
          decimalPrecioOferta: r.decimalPrecioOferta,
          precioBanco: r.precioBanco,
          decimalPrecioBanco: r.decimalPrecioBanco,
          ofertaUno: r.ofertaUno,
          decimalPrecioUno: r.decimalPrecioUno,
          mecanica: r.mecanica,
          unidadMoneda: r.unidadMoneda,
          banco: r.banco,
        }))
      )
      .then(({ data }) => {
        if (!mountedRef.current) return;
        setGrupos(data.grupos.map((g) => ({ ...g, status: "pending" as const, yaAprobado: false })));
        setTruncated(data.truncated);
        setAnalysisError(data.error);
      })
      .catch((err) => {
        if (!mountedRef.current) return;
        setLoadError(err?.response?.status === 503 ? "not_configured" : "generic");
      })
      .finally(finishLoading);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateGrupo(idx: number, patch: Partial<GrupoState>) {
    setGrupos((prev) => prev.map((g, i) => (i === idx ? { ...g, ...patch } : g)));
  }

  async function approveGrupo(idx: number) {
    const g = grupos[idx];
    if (!g || g.status === "approving" || g.status === "approved") return;
    if (!g.grupo.trim() || !g.descripcion.trim()) return;
    updateGrupo(idx, { status: "approving" });
    try {
      await onApprove(g);
      if (mountedRef.current) updateGrupo(idx, { status: "approved", yaAprobado: true });
    } catch {
      if (mountedRef.current) updateGrupo(idx, { status: "error" });
    }
  }

  // Vuelve un grupo ya aprobado a editable, sin salir del Convertidor. Aprobar
  // de nuevo es seguro: las filas ya combinadas no se vuelven a combinar (las
  // sobrantes ya no están en la grilla), el PATCH de la descripción es un upsert
  // por código combinado, y guardar_grupo_unificado ACTUALIZA el grupo cuando el
  // conjunto de SKU es el mismo en vez de crear un duplicado.
  function editarDeNuevo(idx: number) {
    updateGrupo(idx, { status: "pending" });
  }

  function nombreDeFila(rowId: number): string {
    return rows.find((r) => r.row_id === rowId)?.nombreArticulo || "—";
  }

  // Los dos precios de una fila, ya armados con su decimal y su símbolo, para
  // poder corroborarlos SIN salir del modal: un grupo unificado imprime UNA
  // descripción y UN precio para varios SKU, así que si dos miembros no están
  // al mismo precio el grupo está mal armado y hay que verlo acá, antes de
  // aprobar -- después las filas ya se combinaron.
  //
  // `precioRegular` es el anterior (el tachado) y `precioOferta` el vigente;
  // el símbolo sale de `unidadMoneda`, nunca escrito a mano, porque una fila
  // en dólares tiene que mostrar U$S.
  function preciosDeFila(rowId: number): { anterior: string; oferta: string } | null {
    const r = rows.find((x) => x.row_id === rowId);
    if (!r) return null;
    const simbolo = r.unidadMoneda || "$";
    const armar = (entero: string, decimal: string) =>
      entero ? `${simbolo}${entero}${decimal || ""}` : "";
    return {
      anterior: armar(r.precioRegular, r.decimalPrecioRegular),
      oferta:   armar(r.precioOferta,  r.decimalPrecioOferta),
    };
  }

  // Un producto no puede estar en dos grupos: al combinar, cada fila se funde
  // en UNA sola, así que ofrecer una fila que ya es miembro de otro grupo
  // sería ofrecer un conflicto.
  const yaEnAlgunGrupo = new Set(grupos.flatMap((g) => g.row_ids));

  function candidatos(): ConvertidorRow[] {
    const q = busqueda.trim().toLowerCase();
    return rows
      .filter((r) => !yaEnAlgunGrupo.has(r.row_id))
      .filter((r) =>
        !q ||
        r.nombreArticulo.toLowerCase().includes(q) ||
        r.codigo.toLowerCase().includes(q))
      .slice(0, MAX_CANDIDATOS);
  }

  // Suma al grupo un producto que el análisis dejó afuera. El caso que lo
  // motivó: una "infusión" quedó fuera del grupo de los "té" porque Tinín
  // agrupa por el nombre y ese no decía "té". Sin esto había que descartar el
  // grupo y rehacerlo a mano.
  function agregarMiembro(idx: number, row: ConvertidorRow) {
    const g = grupos[idx];
    if (!g || g.row_ids.includes(row.row_id)) return;
    updateGrupo(idx, {
      row_ids: [...g.row_ids, row.row_id],
      skus:    [...g.skus, row.codigo],
    });
  }

  // Saca UN producto de un grupo propuesto antes de aprobar -- Tinín agrupa
  // por nombre y a veces se cuela un SKU que en realidad no corresponde, o
  // el grupo entero queda muy largo para el cartel y hay que partirlo. El
  // que se saca no se borra ni se toca: simplemente no
  // entra en el "combinar en una sola fila" de commitUnificacion, así que
  // sigue en la grilla como una fila propia, sin combinar.
  //
  // Disponible siempre, incluso con 2 nada más: un grupo unificado necesita
  // como mínimo 2 SKU (ver GrupoUnificadoIn en el backend), así que sacar el
  // segundo no deja "un grupo de 1" -- directamente descarta la tarjeta
  // entera, porque ya no queda nada para unificar.
  function quitarMiembro(idx: number, posicion: number) {
    const g = grupos[idx];
    if (!g) return;
    if (g.skus.length <= 2) {
      setGrupos((prev) => prev.filter((_, i) => i !== idx));
      return;
    }
    updateGrupo(idx, {
      row_ids: g.row_ids.filter((_, i) => i !== posicion),
      skus: g.skus.filter((_, i) => i !== posicion),
    });
  }

  // Qué opción está seleccionada, o -1 si la persona editó el texto a mano. Se
  // deriva del texto en vez de guardarse aparte: así editar el campo desengancha
  // el desplegable solo, y volver a elegir una opción lo vuelve a enganchar, sin
  // dos estados que puedan quedar diciendo cosas distintas.
  function indiceElegido(g: GrupoState): number {
    return g.opciones?.findIndex((op) => op.texto === g.descripcion) ?? -1;
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <p className="text-sm font-semibold flex items-center gap-1.5 text-slate-800 dark:text-slate-100">
            <Layers size={15} className="text-brand-500" /> {t("convertidor.unificar.modalTitle")}
          </p>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {loading && (
            <div className="flex flex-col items-center gap-3 py-8">
              <DonTinoTrabajando size={72} />
              <p className="text-xs text-slate-400">{t("convertidor.unificar.loading")}</p>
            </div>
          )}

          {!loading && loadError === "not_configured" && (
            <p className="text-sm text-amber-600 dark:text-amber-400 text-center py-8">
              {t("convertidor.ai.notConfigured")}
            </p>
          )}
          {!loading && loadError === "generic" && (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
              {t("convertidor.ai.genericError")}
            </p>
          )}

          {!loading && !loadError && analysisError && (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
              {t("convertidor.ai.genericError")}
            </p>
          )}

          {!loading && !loadError && !analysisError && truncated && (
            <p className="text-xs text-amber-600 dark:text-amber-400">{t("convertidor.unificar.truncated")}</p>
          )}

          {!loading && !loadError && !analysisError && grupos.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-8">
              {t("convertidor.unificar.noGroups")}
            </p>
          )}

          {!loading &&
            !loadError &&
            !analysisError &&
            grupos.map((g, idx) => {
              // Una sola vez por tarjeta: se usa para el "no hay nada" y para
              // la lista, y filtra sobre TODAS las filas del listado.
              const disponibles = agregandoEn === idx ? candidatos() : [];
              return (
              <div key={idx} className="border border-slate-100 dark:border-slate-800 rounded-lg p-3 space-y-2">
                <input
                  value={g.grupo}
                  disabled={g.status === "approved" || g.status === "approving"}
                  onChange={(e) => updateGrupo(idx, { grupo: e.target.value })}
                  className="input text-xs w-full font-semibold"
                />
                <div className="text-[10px] text-slate-400 space-y-0.5">
                  {g.row_ids.map((rowId, i) => {
                    const precios = preciosDeFila(rowId);
                    return (
                      <p key={rowId} className="flex items-center gap-2">
                        <span className="truncate flex-1 min-w-0">{g.skus[i]} · {nombreDeFila(rowId)}</span>
                        {precios && (
                          <span className="shrink-0 tabular-nums flex items-center gap-1.5">
                            {precios.anterior && (
                              <span
                                title={t("convertidor.unificar.precioAnterior")}
                                className="line-through text-slate-300 dark:text-slate-600"
                              >
                                {precios.anterior}
                              </span>
                            )}
                            {precios.oferta && (
                              <span
                                title={t("convertidor.unificar.precioOferta")}
                                className="font-semibold text-slate-600 dark:text-slate-300"
                              >
                                {precios.oferta}
                              </span>
                            )}
                          </span>
                        )}
                        {!g.yaAprobado && g.status !== "approving" && (
                          <button
                            type="button"
                            onClick={() => quitarMiembro(idx, i)}
                            title={t("convertidor.unificar.quitarDelGrupo")}
                            className="shrink-0 text-slate-400 hover:text-rose-500 dark:hover:text-rose-400"
                          >
                            <X size={11} />
                          </button>
                        )}
                      </p>
                    );
                  })}
                </div>

                {/* Sumar un producto que el análisis dejó afuera. Mismo
                    criterio que el botón de quitar: solo ANTES de la primera
                    aprobación — después las filas ya están combinadas y
                    cambiar el conjunto de SKU sería otro grupo, no este. */}
                {!g.yaAprobado && g.status !== "approving" && (
                  agregandoEn === idx ? (
                    <div className="rounded-lg border border-brand-200 dark:border-brand-900 bg-brand-50/50 dark:bg-brand-950/20 p-2 space-y-1.5">
                      <p className="text-[10px] text-slate-500 dark:text-slate-400">
                        {t("convertidor.unificar.agregarSkuAyuda")}
                      </p>
                      <input
                        autoFocus
                        value={busqueda}
                        onChange={(e) => setBusqueda(e.target.value)}
                        placeholder={t("convertidor.unificar.buscarSku")}
                        className="input text-xs w-full"
                      />
                      <div className="max-h-40 overflow-y-auto space-y-0.5">
                        {disponibles.length === 0 ? (
                          <p className="text-[10px] text-slate-400 px-1 py-1.5">
                            {t("convertidor.unificar.sinCandidatos")}
                          </p>
                        ) : (
                          disponibles.map((r) => {
                            const precios = preciosDeFila(r.row_id);
                            return (
                              <button
                                key={r.row_id}
                                type="button"
                                onClick={() => agregarMiembro(idx, r)}
                                className="w-full flex items-center gap-2 text-left text-[10px] px-1.5 py-1 rounded hover:bg-white dark:hover:bg-slate-800 transition-colors"
                              >
                                <Plus size={10} className="shrink-0 text-brand-500" />
                                <span className="truncate flex-1 min-w-0 text-slate-600 dark:text-slate-300">
                                  {r.codigo} · {r.nombreArticulo}
                                </span>
                                {precios?.oferta && (
                                  <span className="shrink-0 tabular-nums text-slate-400">{precios.oferta}</span>
                                )}
                              </button>
                            );
                          })
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => { setAgregandoEn(null); setBusqueda(""); }}
                        className="btn-secondary text-[10px] px-2 py-0.5"
                      >
                        {t("convertidor.unificar.listo")}
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => { setAgregandoEn(idx); setBusqueda(""); }}
                      className="flex items-center gap-1 text-[10px] font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700"
                    >
                      <Plus size={10} /> {t("convertidor.unificar.agregarSku")}
                    </button>
                  )
                )}
                {/* `yaAprobado`, no `status`: si el grupo se aprobó y se volvió a
                    editar, las filas YA están combinadas y avisar que "al aprobar
                    se combinan" sería falso. */}
                {!g.yaAprobado && (
                  <p className="text-[10px] text-amber-600 dark:text-amber-400">
                    {t("convertidor.unificar.combinedSkuNotice", { codigo: g.skus.join(" - "), count: g.skus.length })}
                  </p>
                )}
                <div>
                  <label className="text-[10px] text-slate-400 uppercase tracking-wide">
                    {t("convertidor.unificar.descripcionUnificada")}
                  </label>
                  {/* El desplegable elige el ÁNGULO; el campo de abajo sigue
                      editable para ajustarlo. Tinín no sabe si el surtido de la
                      góndola está completo -- solo ve lo que está en oferta --
                      así que "todas las variedades" es una opción, no la
                      respuesta, y la elección es de la persona. */}
                  {(g.opciones?.length ?? 0) > 1 && (
                    <select
                      value={indiceElegido(g)}
                      disabled={g.status === "approved" || g.status === "approving"}
                      onChange={(e) => {
                        const i = Number(e.target.value);
                        const op = g.opciones?.[i];
                        if (op) updateGrupo(idx, { descripcion: op.texto });
                      }}
                      className="input text-xs w-full mt-1"
                    >
                      {g.opciones!.map((op, i) => (
                        <option key={i} value={i}>
                          {op.etiqueta} — {op.texto}
                        </option>
                      ))}
                      {indiceElegido(g) === -1 && (
                        <option value={-1}>{t("convertidor.unificar.opcionEditada")}</option>
                      )}
                    </select>
                  )}
                  <input
                    value={g.descripcion}
                    disabled={g.status === "approved" || g.status === "approving"}
                    onChange={(e) => updateGrupo(idx, { descripcion: e.target.value })}
                    className="input text-xs w-full mt-1"
                  />
                  {g.descripcion.trim().length > DESCRIPTION_WARN_CHARS && (
                    <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                      {t("convertidor.ai.tooLong")}
                    </p>
                  )}
                  {g.status === "error" && (
                    <p className="text-[10px] text-red-600 dark:text-red-400 mt-0.5">
                      {t("convertidor.ai.rowError")}
                    </p>
                  )}
                </div>
                <div className="flex justify-end">
                  {g.status === "approved" ? (
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-xs text-emerald-500">
                        <Check size={14} /> {t("convertidor.unificar.approved")}
                      </span>
                      <button onClick={() => editarDeNuevo(idx)} className="btn-secondary text-xs">
                        {t("convertidor.ai.edit")}
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => approveGrupo(idx)}
                      disabled={g.status === "approving" || !g.grupo.trim() || !g.descripcion.trim()}
                      className={`text-xs disabled:opacity-50 ${
                        g.status === "error" ? "btn-secondary border-red-300 text-red-600 dark:text-red-400" : "btn-primary"
                      }`}
                    >
                      {g.status === "approving" ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : g.status === "error" ? (
                        t("convertidor.ai.retry")
                      ) : g.yaAprobado ? (
                        t("convertidor.ai.saveChanges")
                      ) : (
                        t("convertidor.unificar.approve")
                      )}
                    </button>
                  )}
                </div>
              </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
