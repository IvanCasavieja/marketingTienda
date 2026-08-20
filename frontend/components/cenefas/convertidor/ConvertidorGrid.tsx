"use client";
import { useEffect, useMemo, useRef, useState, ChangeEvent, Dispatch, KeyboardEvent, SetStateAction } from "react";
import clsx from "clsx";
import { ArrowLeft, Download, Layers, Loader2, Merge, Sparkles, Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type ConvertidorRow, type MaPair, type UnificarGrupoItem } from "@/lib/api";
import ConvertidorAiModal from "./ConvertidorAiModal";
import ConvertidorMergeModal from "./ConvertidorMergeModal";
import ConvertidorUnifyModal from "./ConvertidorUnifyModal";

// Virtualización manual (sin librería nueva): solo se renderizan las filas
// visibles ± un buffer, con dos <tr> espaciadores para mantener el alto de
// scroll correcto — un export de gestión puede traer varios miles de filas
// y montar un <tr> real por cada una trababa el navegador.
const ROW_HEIGHT = 40;
const CONTAINER_HEIGHT = 560;
const BUFFER_ROWS = 8;
const SAVE_DEBOUNCE_MS = 800;

type ColumnKey =
  | "codigo" | "nombre_articulo" | "comprador" | "descripcion" | "moneda" | "precio_anterior" | "precio"
  | "oferta" | "oferta_det" | "descuento" | "descuento_det" | "descripcion_web"
  | "vigencia" | "aclaracion1" | "aclaracion2" | "aclaracion3";

// "descripcion" es editable con lógica propia (guardado al catálogo
// compartido + sugerencias IA, ver handleDescripcionChange más abajo).
// "simple" es edición local nomás (no persiste a ningún lado hasta
// exportar) — vigencia y aclaracion1/2/3 no tienen catálogo ni columna en
// gestión, son texto libre que se completa acá mismo o se deja vacío.
type EditableKind = "descripcion" | "simple";

// Cada columna tiene un tipo de dato esperado — precio es numérico,
// descripción/nombre son texto, moneda es un símbolo de un set chico
// conocido, oferta det es una categoría (nunca un número). "warningCodes"
// lista los códigos que el backend ya calculó por columna, en orden de
// severidad: vacío ("missing_*") o tipo incorrecto ("*_invalido/a") —
// nunca ambos a la vez para el mismo campo.
const COLUMNS: { key: ColumnKey; i18nKey: string; editable?: EditableKind; warningCodes?: string[] }[] = [
  { key: "codigo",          i18nKey: "codigo" },
  { key: "nombre_articulo", i18nKey: "nombreArticulo", warningCodes: ["nombre_articulo_invalido"] },
  { key: "comprador",       i18nKey: "comprador" },
  { key: "descripcion",     i18nKey: "descripcion",     editable: "descripcion", warningCodes: ["missing_description", "descripcion_invalida", "descripcion_larga", "descripcion_algo_larga"] },
  { key: "moneda",          i18nKey: "moneda",          warningCodes: ["moneda_invalida"] },
  { key: "precio_anterior", i18nKey: "precioAnterior",  warningCodes: ["missing_precio_anterior", "precio_anterior_invalido"] },
  { key: "precio",          i18nKey: "precio",          warningCodes: ["missing_price", "precio_invalido"] },
  { key: "oferta",          i18nKey: "oferta",          warningCodes: ["missing_oferta"] },
  { key: "oferta_det",      i18nKey: "ofertaDet",       warningCodes: ["missing_oferta_det", "oferta_det_invalido"] },
  { key: "descuento",       i18nKey: "descuentoProv" },
  { key: "descuento_det",   i18nKey: "descuentoProvDet" },
  { key: "descripcion_web", i18nKey: "descripcionWeb",  warningCodes: ["missing_descripcion_web", "descripcion_web_invalida"] },
  { key: "vigencia",        i18nKey: "vigencia",        editable: "simple" },
  { key: "aclaracion1",     i18nKey: "aclaracion1",     editable: "simple" },
  { key: "aclaracion2",     i18nKey: "aclaracion2",     editable: "simple" },
  { key: "aclaracion3",     i18nKey: "aclaracion3",     editable: "simple" },
];

// Warnings de "tipo incorrecto" (hay contenido, pero no del tipo esperado
// para esa columna) — más severos que un simple "falta el dato": apuntan a
// la columna exacta donde el Excel de origen viene corrido.
const INVALID_TYPE_CODES = new Set([
  "nombre_articulo_invalido", "descripcion_invalida", "descripcion_larga", "moneda_invalida",
  "precio_anterior_invalido", "precio_invalido", "oferta_det_invalido",
  "descripcion_web_invalida",
]);

const HAS_LETTER_RE = /\p{L}/u;
// Mismos umbrales que DESCRIPTION_WARN_CHARS/DESCRIPTION_MAX_CHARS en
// backend/app/services/cenefas/validation_engine.py — duplicados acá (no
// hay endpoint que los exponga) para recalcular el warning client-side sin
// esperar un round-trip al backend en cada tecla.
const DESCRIPTION_WARN_CHARS = 60;
const DESCRIPTION_MAX_CHARS = 100;
const DESCRIPCION_WARNING_CODES = ["missing_description", "descripcion_invalida", "descripcion_larga", "descripcion_algo_larga"];
// Mismo límite que SkuDescripcion.sku (String(64)) en
// backend/app/models/sku_descripcion.py -- un grupo con muchos SKUs largos
// unidos por " - " podría superarlo, y Postgres rechaza el insert entero en
// vez de truncarlo solo. Se corta acá ANTES de mandar el PATCH para que el
// usuario vea un error claro en el modal en vez de un 500 genérico.
const SKU_COMBINADO_MAX_CHARS = 64;

function computeDescripcionWarnings(currentWarnings: string[], value: string): string[] {
  const warnings = currentWarnings.filter((w) => !DESCRIPCION_WARNING_CODES.includes(w));
  const trimmed = value.trim();
  if (!trimmed) warnings.push("missing_description");
  else if (!HAS_LETTER_RE.test(trimmed)) warnings.push("descripcion_invalida");
  else if (trimmed.length > DESCRIPTION_MAX_CHARS) warnings.push("descripcion_larga");
  else if (trimmed.length > DESCRIPTION_WARN_CHARS) warnings.push("descripcion_algo_larga");
  return warnings;
}

interface Props {
  rows: ConvertidorRow[];
  setRows: Dispatch<SetStateAction<ConvertidorRow[] | null>>;
  maPairs: MaPair[];
  onReset: () => void;
}

function maPairKey(sku1: string, sku2: string): string {
  return `${sku1}|${sku2}`;
}

export default function ConvertidorGrid({ rows, setRows, maPairs, onReset }: Props) {
  const { t } = useTranslation();
  const [scrollTop, setScrollTop] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [savingRowId, setSavingRowId] = useState<number | null>(null);
  const [pendingFocusRowId, setPendingFocusRowId] = useState<number | null>(null);
  // Snapshot local: arranca desde la prop (calculada una vez por el backend
  // al hacer preview) y se achica sola a medida que se unifican o descartan
  // pares -- "descartar" no persiste entre sesiones, es solo estado local.
  const [pendingPairs, setPendingPairs] = useState<MaPair[]>(maPairs);
  const [dismissedPairKeys, setDismissedPairKeys] = useState<Set<string>>(new Set());
  const [mergePair, setMergePair] = useState<MaPair | null>(null);
  // Barra tipo Excel: separado en hover vs. foco (por teclado) para que,
  // al sacar el mouse de la celda que además tiene el foco, la barra no
  // quede vacía -- vuelve a mostrar la celda enfocada en vez de nada.
  const [hoveredCell, setHoveredCell] = useState<{ rowId: number; key: ColumnKey } | null>(null);
  const [focusedCell, setFocusedCell] = useState<{ rowId: number; key: ColumnKey } | null>(null);
  const activeCell = hoveredCell ?? focusedCell;
  const activeCellColumn = activeCell ? COLUMNS.find((c) => c.key === activeCell.key) : undefined;
  const activeCellRow = activeCell ? rows.find((r) => r.row_id === activeCell.rowId) : undefined;
  const activeCellValue =
    activeCellColumn && activeCellRow ? String(activeCellRow[activeCellColumn.key] ?? "") : "";
  // Snapshot fijo tomado al abrir el modal, NO la lista viva
  // rowsNeedingDescripcion -- esa se achica sola a medida que se aprueban
  // filas (porque quita el warning missing_description), y si el modal
  // recibiera esa lista directamente cada fila aprobada desaparecería del
  // modal en vez de quedar mostrando el check verde.
  const [aiModalRows, setAiModalRows] = useState<ConvertidorRow[] | null>(null);
  // Snapshot fijo tomado al abrir el modal, mismo criterio que aiModalRows --
  // "Unificar categorías" analiza TODAS las filas del Excel cargado (no solo
  // las que faltan descripción, a diferencia del modal de IA de arriba).
  const [unifyModalRows, setUnifyModalRows] = useState<ConvertidorRow[] | null>(null);
  const pendingSaves = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const dlRef = useRef<HTMLAnchorElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const descripcionInputRefs = useRef<Map<number, HTMLInputElement>>(new Map());

  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_ROWS);
  const visibleCount = Math.ceil(CONTAINER_HEIGHT / ROW_HEIGHT) + BUFFER_ROWS * 2;
  const endIndex = Math.min(rows.length, startIndex + visibleCount);
  const visibleRows = useMemo(() => rows.slice(startIndex, endIndex), [rows, startIndex, endIndex]);
  const topSpacer = startIndex * ROW_HEIGHT;
  const bottomSpacer = (rows.length - endIndex) * ROW_HEIGHT;

  // Botonera de navegación rápida: filas que todavía necesitan descripción
  // (missing_description se recalcula en cada edit, así que esta lista se
  // achica sola a medida que se van completando).
  const rowsNeedingDescripcion = useMemo(
    () => rows.filter((r) => r.warnings.includes("missing_description")),
    [rows]
  );

  // Vivo, no una foto fija del preview inicial -- así el contador refleja
  // las filas aprobadas en esta misma sesión (vía "Generar con IA" o edición
  // manual) sin necesitar recargar la página.
  const matchedCount = rows.length - rowsNeedingDescripcion.length;

  // Fiambres cuyo nombre/descripción todavía dice "kg" — necesitan pasar a
  // 100g (descripción + precio÷10) aunque ya tengan descripción matcheada
  // del catálogo, por eso es un filtro aparte y no solo un warning más.
  const rowsFiambresKg = useMemo(() => rows.filter((r) => r.es_fiambre_kg), [rows]);

  // Combinado para el modal de IA: fiambres por kg primero, sin duplicar
  // las que también les falta descripción.
  const rowsParaIA = useMemo(() => {
    const fiambresIds = new Set(rowsFiambresKg.map((r) => r.row_id));
    return [...rowsFiambresKg, ...rowsNeedingDescripcion.filter((r) => !fiambresIds.has(r.row_id))];
  }, [rowsFiambresKg, rowsNeedingDescripcion]);

  // Pares "mismo producto, dos SKUs" todavía vigentes -- ni unificados ni
  // descartados en esta sesión.
  const visiblePairs = useMemo(
    () => pendingPairs.filter((p) => !dismissedPairKeys.has(maPairKey(p.sku1, p.sku2))),
    [pendingPairs, dismissedPairKeys]
  );

  function dismissPair(pair: MaPair) {
    setDismissedPairKeys((prev) => new Set(prev).add(maPairKey(pair.sku1, pair.sku2)));
  }

  // Unifica las dos filas en una sola con SKU combinado "SKU1-SKU2": el PATCH
  // existente ya alcanza (mismo endpoint que la edición manual), no hace
  // falta un endpoint nuevo. Se conservan el resto de los campos de la
  // primera fila (precio, oferta, etc.) -- la segunda fila se descarta del
  // grid, ya representada por el SKU combinado.
  async function commitMerge(pair: MaPair, descripcion: string) {
    const skuCombinado = `${pair.sku1}-${pair.sku2}`;
    await convertidorApi.updateDescripcion(skuCombinado, descripcion);
    setRows((prev) =>
      (prev ?? [])
        .filter((r) => r.codigo !== pair.sku2)
        .map((r) =>
          r.codigo === pair.sku1
            ? {
                ...r,
                codigo: skuCombinado,
                descripcion,
                warnings: computeDescripcionWarnings(r.warnings, descripcion),
              }
            : r
        )
    );
    setPendingPairs((prev) => prev.filter((p) => !(p.sku1 === pair.sku1 && p.sku2 === pair.sku2)));
    setMergePair(null);
    toast.success(t("convertidor.merge.merged", { sku: skuCombinado }));
  }

  // Combina las N filas del grupo en una sola -- mismo criterio que commitMerge
  // (el PATCH existente ya alcanza, no hace falta un endpoint de confirmación
  // aparte), generalizado a N SKUs en vez de 2: el código combinado une todos
  // los SKUs con " - " (a diferencia del merge M/A, que no lleva espacios,
  // porque ahí siempre son 2; acá pueden ser varios y se lee peor pegado). La
  // primera fila del grupo sobrevive con el código y la descripción combinados;
  // el resto se saca de la grilla.
  async function commitUnificacion(grupo: UnificarGrupoItem) {
    const codigoCombinado = grupo.skus.join(" - ");
    if (codigoCombinado.length > SKU_COMBINADO_MAX_CHARS) {
      toast.error(t("convertidor.unificar.codigoTooLong"));
      throw new Error("Código combinado demasiado largo");
    }
    await convertidorApi.updateDescripcion(codigoCombinado, grupo.descripcion);
    const [rowIdSuperviviente, ...rowIdsAEliminar] = grupo.row_ids;
    const idsAEliminar = new Set(rowIdsAEliminar);
    setRows((prev) =>
      (prev ?? [])
        .filter((r) => !idsAEliminar.has(r.row_id))
        .map((r) =>
          r.row_id === rowIdSuperviviente
            ? {
                ...r,
                codigo: codigoCombinado,
                descripcion: grupo.descripcion,
                warnings: computeDescripcionWarnings(r.warnings, grupo.descripcion),
              }
            : r
        )
    );
    toast.success(t("convertidor.unificar.saved", { grupo: grupo.grupo, count: grupo.skus.length }));
  }

  function scrollToRow(rowId: number) {
    const container = scrollContainerRef.current;
    if (!container) return;
    const target = Math.max(0, rowId * ROW_HEIGHT - CONTAINER_HEIGHT / 2 + ROW_HEIGHT / 2);
    container.scrollTop = target;
    setScrollTop(target);
    setPendingFocusRowId(rowId);
  }

  // Una vez que la fila objetivo entra en el rango virtualizado (post-scroll),
  // enfocar su input de descripción para poder tipear de una.
  useEffect(() => {
    if (pendingFocusRowId === null) return;
    if (!visibleRows.some((r) => r.row_id === pendingFocusRowId)) return;
    const input = descripcionInputRefs.current.get(pendingFocusRowId);
    if (input) {
      input.focus();
      input.select();
    }
    setPendingFocusRowId(null);
  }, [visibleRows, pendingFocusRowId]);

  // Devuelve si el guardado salió bien -- nunca lanza, porque el uso más
  // común (debounce/Enter en la grilla) es fire-and-forget con el toast
  // como única señal. commitDescripcion (usado por el modal de IA) sí
  // necesita saber el resultado real para no marcar "aprobado" un guardado
  // que en realidad falló -- ver ahí abajo.
  async function flushSave(rowId: number, sku: string, descripcion: string): Promise<boolean> {
    setSavingRowId(rowId);
    try {
      await convertidorApi.updateDescripcion(sku, descripcion);
      toast.success(t("convertidor.savedToCatalog", { sku }));
      return true;
    } catch {
      toast.error(t("convertidor.saveError"));
      return false;
    } finally {
      setSavingRowId((cur) => (cur === rowId ? null : cur));
    }
  }

  // Edición "simple" (vigencia, aclaracion1/2/3): sin catálogo compartido ni
  // debounce a un backend — solo actualiza el estado local, va al export tal
  // cual quede tipeado.
  function handleSimpleFieldChange(rowId: number, key: ColumnKey, value: string) {
    setRows((prev) => (prev ?? []).map((r) => (r.row_id === rowId ? { ...r, [key]: value } : r)));
  }

  function handleDescripcionChange(rowId: number, sku: string, value: string) {
    const trimmed = value.trim();
    setRows((prev) =>
      (prev ?? []).map((r) =>
        r.row_id === rowId
          ? { ...r, descripcion: value, warnings: computeDescripcionWarnings(r.warnings, value) }
          : r
      )
    );

    if (pendingSaves.current[rowId]) clearTimeout(pendingSaves.current[rowId]);
    // Nunca persistir en el catálogo compartido una descripción vacía o sin letras.
    if (!trimmed || !HAS_LETTER_RE.test(trimmed)) return;
    pendingSaves.current[rowId] = setTimeout(() => {
      delete pendingSaves.current[rowId];
      flushSave(rowId, sku, value);
    }, SAVE_DEBOUNCE_MS);
  }

  // Enter guarda ya (sin esperar el debounce de 800ms) — así el usuario
  // tiene una confirmación inmediata en vez de tener que confiar en que
  // el guardado automático silencioso funcionó.
  function handleDescripcionKeyDown(e: KeyboardEvent<HTMLInputElement>, rowId: number, sku: string) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const value = e.currentTarget.value.trim();
    if (!value || !HAS_LETTER_RE.test(value)) return;
    if (pendingSaves.current[rowId]) {
      clearTimeout(pendingSaves.current[rowId]);
      delete pendingSaves.current[rowId];
    }
    flushSave(rowId, sku, value);
  }

  // Callback que usa el modal de IA al aprobar una sugerencia (individual o
  // en bloque) — reusa flushSave (el mismo PATCH + toast que ya existe, no
  // se duplica lógica de guardado), agregando solo la actualización
  // inmediata que handleDescripcionChange hace al tipear. No comparte
  // código con handleDescripcionChange porque ese además programa el
  // debounce, y acá hace falta guardar ya (el usuario ya aprobó).
  async function commitDescripcion(
    rowId: number,
    sku: string,
    value: string,
    precioOverride?: { precio?: number; precio_anterior?: number }
  ) {
    const trimmed = value.trim();
    if (!trimmed || !HAS_LETTER_RE.test(trimmed)) {
      // El modal marca "aprobado" solo si esta promesa resuelve sin lanzar
      // -- una sugerencia vacía o sin letras nunca debería contarse como
      // guardada, aunque el usuario haya clickeado "Aprobar".
      throw new Error("Descripción inválida: no puede quedar vacía ni sin letras");
    }
    setRows((prev) =>
      (prev ?? []).map((r) =>
        r.row_id === rowId
          ? {
              ...r,
              descripcion: value,
              warnings: computeDescripcionWarnings(r.warnings, value),
              // Ya se aprobó desde acá (el único lugar que resuelve description
              // + precio÷10 juntos) -- sin este reset, una fila fiambre_kg ya
              // aprobada seguía volviendo a aparecer en "Generar con IA" cada
              // vez que se reabría el modal en la misma sesión, porque este
              // flag nunca se limpiaba y rowsFiambresKg se arma a partir de él.
              es_fiambre_kg: false,
              // El precio ajustado (÷10 para fiambres que pasan a 100g) solo
              // se actualiza acá, en el estado local — nunca se manda al
              // backend. sku_descripciones no tiene columnas de precio y así
              // se mantiene: el PATCH de abajo (flushSave) sigue mandando
              // únicamente la descripción, igual que siempre.
              ...(precioOverride?.precio !== undefined ? { precio: precioOverride.precio } : {}),
              ...(precioOverride?.precio_anterior !== undefined
                ? { precio_anterior: precioOverride.precio_anterior }
                : {}),
            }
          : r
      )
    );
    const ok = await flushSave(rowId, sku, value);
    if (!ok) throw new Error("No se pudo guardar la descripción");
  }

  async function handleExport() {
    setExporting(true);
    try {
      // Fuerza el flush de cualquier guardado pendiente antes de descargar —
      // así ninguna corrección reciente se pierde del catálogo compartido
      // si el usuario descarga enseguida de tipear.
      for (const rowId of Object.keys(pendingSaves.current).map(Number)) {
        clearTimeout(pendingSaves.current[rowId]);
        delete pendingSaves.current[rowId];
        const row = rows.find((r) => r.row_id === rowId);
        if (row && row.descripcion.trim()) await flushSave(rowId, row.codigo, row.descripcion);
      }

      const { data: blob } = await convertidorApi.export(rows);
      const url = URL.createObjectURL(new Blob([blob]));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = "convertidor_cenefas.xlsx";
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
      toast.success(t("convertidor.downloaded"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setExporting(false);
    }
  }

  function warningClass(row: ConvertidorRow, codes?: string[]): string {
    const code = codes?.find((c) => row.warnings.includes(c));
    if (!code) return "";
    if (code === "missing_description") {
      return "bg-rose-50 dark:bg-rose-500/10 ring-1 ring-inset ring-rose-300 dark:ring-rose-500/40";
    }
    if (INVALID_TYPE_CODES.has(code)) {
      return "bg-violet-50 dark:bg-violet-500/10 ring-1 ring-inset ring-violet-300 dark:ring-violet-500/40";
    }
    return "bg-amber-50 dark:bg-amber-500/10 ring-1 ring-inset ring-amber-300 dark:ring-amber-500/40";
  }

  return (
    <div className="space-y-4">
      <a ref={dlRef} className="hidden" />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <button onClick={onReset} className="btn-ghost flex items-center gap-1.5 text-sm">
            <ArrowLeft size={14} /> {t("convertidor.changeFile")}
          </button>
          <button
            type="button"
            onClick={() => setUnifyModalRows(rows)}
            className="btn-secondary flex items-center gap-1.5 text-xs"
          >
            <Layers size={13} /> {t("convertidor.unificar.button")}
          </button>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600 dark:text-slate-300">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
            {t("convertidor.legendMissing")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-violet-400" />
            {t("convertidor.legendInvalidType")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            {t("convertidor.legendWarning")}
          </span>
          <span className="badge badge-blue">
            {t("convertidor.matchedSummary", { matched: matchedCount, total: rows.length })}
          </span>
        </div>
      </div>

      {visiblePairs.length > 0 && (
        <div className="card p-3 space-y-2 border-l-4 border-l-brand-400">
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
            {t("convertidor.merge.bannerTitle", { count: visiblePairs.length })}
          </p>
          <div className="space-y-1.5">
            {visiblePairs.map((pair) => (
              <div
                key={maPairKey(pair.sku1, pair.sku2)}
                className="flex items-center justify-between gap-3 flex-wrap text-xs bg-slate-50 dark:bg-slate-800/60 rounded-lg px-3 py-2"
              >
                <span className="text-slate-600 dark:text-slate-300 truncate">
                  {pair.sku1} · {pair.nombre1} <span className="text-slate-400">/</span> {pair.sku2} · {pair.nombre2}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => setMergePair(pair)}
                    className="btn-secondary text-[11px] flex items-center gap-1 py-1"
                  >
                    <Merge size={11} /> {t("convertidor.merge.review")}
                  </button>
                  <button
                    type="button"
                    onClick={() => dismissPair(pair)}
                    className="btn-ghost text-[11px] py-1"
                  >
                    {t("convertidor.merge.notSameProduct")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {rowsParaIA.length > 0 && (
        <div className="card p-3 space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
              {t("convertidor.unmatchedNavTitle", { count: rowsParaIA.length })}
            </p>
            <button
              type="button"
              onClick={() => setAiModalRows(rowsParaIA)}
              className="btn-secondary text-xs flex items-center gap-1.5"
            >
              <Sparkles size={13} /> {t("convertidor.ai.button")}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {rowsParaIA.map((row) => (
              <button
                key={row.row_id}
                type="button"
                onClick={() => scrollToRow(row.row_id)}
                className={`badge ${row.es_fiambre_kg ? "badge-yellow" : "badge-red"} flex items-center gap-1 hover:brightness-110 transition-[filter] cursor-pointer max-w-[220px]`}
                title={t("convertidor.unmatchedNavGo")}
              >
                <Target size={11} className="shrink-0" />
                <span className="truncate">
                  {row.codigo} · {row.nombre_articulo || "—"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="h-9 flex items-center gap-2 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs">
        {activeCellColumn ? (
          <>
            <span className="font-semibold text-slate-500 dark:text-slate-400 shrink-0">
              {t(`convertidor.columns.${activeCellColumn.i18nKey}`)}:
            </span>
            <span className="truncate text-slate-800 dark:text-slate-100">{activeCellValue || "—"}</span>
          </>
        ) : (
          <span className="text-slate-300 dark:text-slate-600">{t("convertidor.cellBarPlaceholder")}</span>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <div
          ref={scrollContainerRef}
          className="overflow-auto"
          style={{ height: CONTAINER_HEIGHT }}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        >
          <table className="w-full border-collapse text-xs table-fixed">
            <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800">
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className="text-left px-2 py-2 font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide text-[10px] border-b border-slate-200 dark:border-slate-700"
                  >
                    {t(`convertidor.columns.${c.i18nKey}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topSpacer > 0 && (
                <tr style={{ height: topSpacer }}>
                  <td colSpan={COLUMNS.length} />
                </tr>
              )}
              {visibleRows.map((row) => (
                <tr key={row.row_id} style={{ height: ROW_HEIGHT }} className="border-b border-slate-100 dark:border-slate-800">
                  {COLUMNS.map((c) => (
                    <td
                      key={c.key}
                      className={clsx("px-2 py-1 align-middle", warningClass(row, c.warningCodes))}
                      onMouseEnter={() => setHoveredCell({ rowId: row.row_id, key: c.key })}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      {c.editable === "descripcion" ? (
                        <div className="flex items-center gap-1">
                          <input
                            ref={(el) => {
                              if (el) descripcionInputRefs.current.set(row.row_id, el);
                              else descripcionInputRefs.current.delete(row.row_id);
                            }}
                            type="text"
                            value={row.descripcion}
                            onChange={(e: ChangeEvent<HTMLInputElement>) =>
                              handleDescripcionChange(row.row_id, row.codigo, e.target.value)
                            }
                            onKeyDown={(e) => handleDescripcionKeyDown(e, row.row_id, row.codigo)}
                            onFocus={() => setFocusedCell({ rowId: row.row_id, key: c.key })}
                            onBlur={() => setFocusedCell(null)}
                            className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-xs py-1 px-1 outline-none transition-colors"
                            placeholder={t("convertidor.descripcionPlaceholder")}
                          />
                          {savingRowId === row.row_id && (
                            <Loader2 size={11} className="shrink-0 animate-spin text-slate-400" />
                          )}
                        </div>
                      ) : c.editable === "simple" ? (
                        <input
                          type="text"
                          value={String(row[c.key] ?? "")}
                          onChange={(e: ChangeEvent<HTMLInputElement>) =>
                            handleSimpleFieldChange(row.row_id, c.key, e.target.value)
                          }
                          onFocus={() => setFocusedCell({ rowId: row.row_id, key: c.key })}
                          onBlur={() => setFocusedCell(null)}
                          className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-xs py-1 px-1 outline-none transition-colors"
                        />
                      ) : (
                        <span className="block truncate text-slate-700 dark:text-slate-300" title={String(row[c.key] ?? "")}>
                          {row[c.key] === null || row[c.key] === undefined || row[c.key] === "" ? "—" : String(row[c.key])}
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {bottomSpacer > 0 && (
                <tr style={{ height: bottomSpacer }}>
                  <td colSpan={COLUMNS.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <button onClick={handleExport} disabled={exporting} className="btn-primary flex items-center gap-2 disabled:opacity-50">
        {exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
        {exporting ? t("convertidor.exporting") : t("convertidor.download")}
      </button>

      {aiModalRows && (
        <ConvertidorAiModal
          rows={aiModalRows}
          onApprove={commitDescripcion}
          onClose={() => setAiModalRows(null)}
        />
      )}

      {unifyModalRows && (
        <ConvertidorUnifyModal
          rows={unifyModalRows}
          onApprove={commitUnificacion}
          onClose={() => setUnifyModalRows(null)}
        />
      )}

      {mergePair && (() => {
        const rowA = rows.find((r) => r.codigo === mergePair.sku1);
        const rowB = rows.find((r) => r.codigo === mergePair.sku2);
        if (!rowA || !rowB) return null;
        return (
          <ConvertidorMergeModal
            pair={mergePair}
            rowA={rowA}
            rowB={rowB}
            onConfirm={(descripcion) => commitMerge(mergePair, descripcion)}
            onClose={() => setMergePair(null)}
          />
        );
      })()}
    </div>
  );
}
