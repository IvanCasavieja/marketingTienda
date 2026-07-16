"use client";
import { useMemo, useRef, useState, ChangeEvent, Dispatch, SetStateAction } from "react";
import clsx from "clsx";
import { AlertTriangle, ArrowLeft, Download, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type ConvertidorRow } from "@/lib/api";

// Virtualización manual (sin librería nueva): solo se renderizan las filas
// visibles ± un buffer, con dos <tr> espaciadores para mantener el alto de
// scroll correcto — un export de gestión puede traer varios miles de filas
// y montar un <tr> real por cada una trababa el navegador.
const ROW_HEIGHT = 40;
const CONTAINER_HEIGHT = 560;
const BUFFER_ROWS = 8;
const SAVE_DEBOUNCE_MS = 800;

type ColumnKey = "codigo" | "nombre_articulo" | "descripcion" | "moneda" | "precio_anterior" | "precio" | "oferta" | "oferta_det" | "descripcion_web";

const COLUMNS: { key: ColumnKey; i18nKey: string; editable?: boolean; warningCode?: string }[] = [
  { key: "codigo",          i18nKey: "codigo" },
  { key: "nombre_articulo", i18nKey: "nombreArticulo" },
  { key: "descripcion",     i18nKey: "descripcion",     editable: true, warningCode: "missing_description" },
  { key: "moneda",          i18nKey: "moneda" },
  { key: "precio_anterior", i18nKey: "precioAnterior",  warningCode: "missing_precio_anterior" },
  { key: "precio",          i18nKey: "precio",          warningCode: "missing_price" },
  { key: "oferta",          i18nKey: "oferta",          warningCode: "missing_oferta" },
  { key: "oferta_det",      i18nKey: "ofertaDet",       warningCode: "missing_oferta_det" },
  { key: "descripcion_web", i18nKey: "descripcionWeb",  warningCode: "missing_descripcion_web" },
];

interface Summary {
  total: number;
  matched_count: number;
  unmatched_count: number;
}

interface Props {
  rows: ConvertidorRow[];
  setRows: Dispatch<SetStateAction<ConvertidorRow[] | null>>;
  summary: Summary | null;
  onReset: () => void;
}

export default function ConvertidorGrid({ rows, setRows, summary, onReset }: Props) {
  const { t } = useTranslation();
  const [scrollTop, setScrollTop] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [savingRowId, setSavingRowId] = useState<number | null>(null);
  const pendingSaves = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const dlRef = useRef<HTMLAnchorElement>(null);

  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_ROWS);
  const visibleCount = Math.ceil(CONTAINER_HEIGHT / ROW_HEIGHT) + BUFFER_ROWS * 2;
  const endIndex = Math.min(rows.length, startIndex + visibleCount);
  const visibleRows = useMemo(() => rows.slice(startIndex, endIndex), [rows, startIndex, endIndex]);
  const topSpacer = startIndex * ROW_HEIGHT;
  const bottomSpacer = (rows.length - endIndex) * ROW_HEIGHT;

  async function flushSave(rowId: number, sku: string, descripcion: string) {
    setSavingRowId(rowId);
    try {
      await convertidorApi.updateDescripcion(sku, descripcion);
    } catch {
      toast.error(t("convertidor.saveError"));
    } finally {
      setSavingRowId((cur) => (cur === rowId ? null : cur));
    }
  }

  function handleDescripcionChange(rowId: number, sku: string, value: string) {
    setRows((prev) =>
      (prev ?? []).map((r) =>
        r.row_id === rowId
          ? {
              ...r,
              descripcion: value,
              warnings: value.trim()
                ? r.warnings.filter((w) => w !== "missing_description")
                : r.warnings.includes("missing_description")
                ? r.warnings
                : [...r.warnings, "missing_description"],
            }
          : r
      )
    );

    if (pendingSaves.current[rowId]) clearTimeout(pendingSaves.current[rowId]);
    if (!value.trim()) return; // nunca persistir una descripción vacía en el catálogo compartido
    pendingSaves.current[rowId] = setTimeout(() => {
      delete pendingSaves.current[rowId];
      flushSave(rowId, sku, value);
    }, SAVE_DEBOUNCE_MS);
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

  function warningClass(row: ConvertidorRow, code?: string): string {
    if (!code || !row.warnings.includes(code)) return "";
    return code === "missing_description"
      ? "bg-rose-50 dark:bg-rose-500/10 ring-1 ring-inset ring-rose-300 dark:ring-rose-500/40"
      : "bg-amber-50 dark:bg-amber-500/10 ring-1 ring-inset ring-amber-300 dark:ring-amber-500/40";
  }

  return (
    <div className="space-y-4">
      <a ref={dlRef} className="hidden" />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <button onClick={onReset} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft size={14} /> {t("convertidor.changeFile")}
        </button>
        {summary && (
          <div className="flex items-center gap-4 text-xs text-slate-600 dark:text-slate-300">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
              {t("convertidor.legendMissing")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
              {t("convertidor.legendWarning")}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-violet-400" />
              {t("convertidor.legendShifted")}
            </span>
            <span className="badge badge-blue">
              {t("convertidor.matchedSummary", { matched: summary.matched_count, total: summary.total })}
            </span>
          </div>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <div
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
              {visibleRows.map((row) => {
                const rowShifted = row.warnings.includes("shifted_columns");
                return (
                  <tr
                    key={row.row_id}
                    style={{ height: ROW_HEIGHT }}
                    className={clsx(
                      "border-b border-slate-100 dark:border-slate-800",
                      rowShifted && "border-l-4 border-l-violet-400 dark:border-l-violet-500"
                    )}
                  >
                    {COLUMNS.map((c) => (
                      <td key={c.key} className={clsx("px-2 py-1 align-middle", warningClass(row, c.warningCode))}>
                        {c.editable ? (
                          <div className="flex items-center gap-1">
                            <input
                              type="text"
                              value={row.descripcion}
                              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                                handleDescripcionChange(row.row_id, row.codigo, e.target.value)
                              }
                              className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-xs py-1 px-1 outline-none transition-colors"
                              placeholder={t("convertidor.descripcionPlaceholder")}
                            />
                            {savingRowId === row.row_id && (
                              <Loader2 size={11} className="shrink-0 animate-spin text-slate-400" />
                            )}
                          </div>
                        ) : (
                          <span className="flex items-center gap-1 truncate text-slate-700 dark:text-slate-300" title={String(row[c.key] ?? "")}>
                            {c.key === "codigo" && rowShifted && (
                              <span title={t("convertidor.shiftedTooltip")} className="inline-flex shrink-0">
                                <AlertTriangle size={12} className="text-violet-500" />
                              </span>
                            )}
                            <span className="truncate">
                              {row[c.key] === null || row[c.key] === undefined || row[c.key] === "" ? "—" : String(row[c.key])}
                            </span>
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
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
    </div>
  );
}
