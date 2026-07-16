"use client";
import { useEffect, useState, useRef, useMemo } from "react";
import * as XLSX from "xlsx";
import { redexpressApi, PlanillaRow } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { CheckCircle2, Clock, Plus, RefreshCw, Download } from "lucide-react";
import { toast } from "sonner";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

type ColKey = string;

// ── Main component ─────────────────────────────────────────────────────────────

export default function PlanillaPedidosPage() {
  const { t } = useTranslation();

  // Grupos/columnas y nombres de mes salen de i18n para que la planilla se vea
  // en el idioma elegido (antes estaban hardcodeados en español).
  const GROUPS = useMemo(() => [
    {
      label: t("redexpress.groups.ofertas"),
      color: "bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-300",
      cols: [
        { key: "a4_oferta_vertical",  label: t("redexpress.cols.a4OfertaVertical"), max: 200 },
        { key: "cenefa_oferta_x3",    label: t("redexpress.cols.cenefaOfertaX3"),   max: 300 },
        { key: "pinchos",             label: t("redexpress.cols.pinchos"),          max: 100 },
        { key: "afiche_54x74",        label: t("redexpress.cols.afiche54x74"),      max: 20 },
      ],
    },
    {
      label: t("redexpress.groups.vdsSupremo"),
      color: "bg-purple-100 dark:bg-purple-500/20 text-purple-800 dark:text-purple-300",
      cols: [
        { key: "cenefa_valle_del_sol",  label: t("redexpress.cols.cenefaValleDelSol"),  max: 100 },
        { key: "cenefa_supremo_hogar",  label: t("redexpress.cols.cenefaSupremoHogar"), max: 100 },
      ],
    },
    {
      label: t("redexpress.groups.bombas"),
      color: "bg-orange-100 dark:bg-orange-500/20 text-orange-800 dark:text-orange-300",
      cols: [
        { key: "bombas_3xa4",    label: t("redexpress.cols.bombas3xa4"),    max: 200 },
        { key: "bombas_a4",      label: t("redexpress.cols.bombasA4"),      max: 200 },
        { key: "bombas_74x54",   label: t("redexpress.cols.bombas74x54"),   max: 20 },
        { key: "pinchos_bombas", label: t("redexpress.cols.pinchosBombas"), max: 100 },
      ],
    },
    {
      label: t("redexpress.groups.stickers"),
      color: "bg-pink-100 dark:bg-pink-500/20 text-pink-800 dark:text-pink-300",
      cols: [
        { key: "sticker_valle_del_sol", label: t("redexpress.cols.stickerValleDelSol"), max: 100 },
        { key: "sticker_carne",         label: t("redexpress.cols.stickerCarne"),       max: 100 },
      ],
    },
    {
      label: t("redexpress.groups.otrosItems"),
      color: "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300",
      cols: [
        { key: "cenefas_preciazos",       label: t("redexpress.cols.cenefasPreciazos"),       max: 100 },
        { key: "cenefas_a4_preciazos",    label: t("redexpress.cols.cenefasA4Preciazos"),     max: 100 },
        { key: "afiche_super_ahorro",     label: t("redexpress.cols.aficheSuperAhorro"),      max: 10 },
        { key: "afiche_grande_preciazos", label: t("redexpress.cols.aficheGrandePreciazos"),  max: 10 },
        { key: "pinchos_dias_expres",     label: t("redexpress.cols.pinchosDiasExpres"),      max: 100 },
        { key: "hojas_amarillas",         label: t("redexpress.cols.hojasAmarillas"), isText: true },
      ],
    },
  ], [t]);

  const ALL_COLS: { key: ColKey; label: string; isText?: boolean; max?: number; group: string }[] = useMemo(
    () => GROUPS.flatMap((g) => g.cols.map((c) => ({ ...c, group: g.label }))),
    [GROUPS]
  );

  const COL_MAX: Record<string, number> = useMemo(
    () => Object.fromEntries(ALL_COLS.filter((c) => c.max !== undefined).map((c) => [c.key, c.max as number])),
    [ALL_COLS]
  );

  const MONTH_NAMES = t("redexpress.months", { returnObjects: true }) as string[];

  const [meses, setMeses]         = useState<{ year: number; month: number }[]>([]);
  const [selectedMes, setSelected] = useState<{ year: number; month: number } | null>(null);
  const [rows, setRows]           = useState<PlanillaRow[]>([]);
  const [loading, setLoading]     = useState(false);
  const { user: currentUser } = useCurrentUser();
  const isSuperuser = currentUser?.is_superuser ?? false;
  const [savingRow, setSavingRow] = useState<string | null>(null);
  const [confirmingRow, setConfirmingRow] = useState<string | null>(null);
  const [showNewMes, setShowNewMes] = useState(false);
  const [newYear, setNewYear]     = useState(new Date().getFullYear());
  const [newMonth, setNewMonth]   = useState(new Date().getMonth() + 1);
  const [filterOnly, setFilterOnly] = useState(false);

  // Local editing state (key = local_nombre, value = partial row data)
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const pendingSaves = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    loadMeses();
  }, []);

  async function loadMeses() {
    try {
      const { data } = await redexpressApi.getMeses();
      setMeses(data);
      if (data.length > 0) {
        const last = data[data.length - 1];
        setSelected(last);
      }
    } catch {
      toast.error(t("redexpress.errorCargarMeses"));
    }
  }

  useEffect(() => {
    if (selectedMes) loadPlanilla(selectedMes.year, selectedMes.month);
  }, [selectedMes]);

  async function loadPlanilla(year: number, month: number) {
    setLoading(true);
    setEdits({});
    try {
      const { data } = await redexpressApi.getPlanilla(year, month);
      setRows(data);
    } catch {
      toast.error(t("redexpress.errorCargarPlanilla"));
    } finally {
      setLoading(false);
    }
  }

  // Trigger save after 800ms of inactivity per row
  function scheduleRowSave(localNombre: string) {
    if (pendingSaves.current[localNombre]) {
      clearTimeout(pendingSaves.current[localNombre]);
    }
    pendingSaves.current[localNombre] = setTimeout(() => {
      flushRowSave(localNombre);
    }, 800);
  }

  async function flushRowSave(localNombre: string) {
    if (!selectedMes) return;
    const rowEdits = edits[localNombre];
    if (!rowEdits || Object.keys(rowEdits).length === 0) return;

    setSavingRow(localNombre);
    try {
      const payload: Record<string, number | string | null> = {};
      for (const [key, val] of Object.entries(rowEdits)) {
        if (key === "hojas_amarillas" || key === "otros") {
          payload[key] = val === "" ? null : val;
        } else {
          payload[key] = val === "" ? null : parseInt(val, 10);
          if (typeof payload[key] === "number" && isNaN(payload[key] as number)) {
            payload[key] = null;
          }
        }
      }
      const { data: updated } = await redexpressApi.updateRow(
        selectedMes.year, selectedMes.month, localNombre, payload
      );
      setRows((prev) => prev.map((r) => r.local_nombre === localNombre ? updated : r));
      setEdits((prev) => {
        const next = { ...prev };
        delete next[localNombre];
        return next;
      });
    } catch {
      toast.error(t("redexpress.errorGuardarLocal", { local: localNombre }));
    } finally {
      setSavingRow(null);
    }
  }

  function handleCellChange(localNombre: string, colKey: string, value: string) {
    const max = COL_MAX[colKey];
    if (max !== undefined && value !== "") {
      const num = parseInt(value, 10);
      if (!isNaN(num) && num > max) {
        value = String(max);
        toast.warning(t("redexpress.limiteMaximo", { max }));
      }
    }
    setEdits((prev) => ({
      ...prev,
      [localNombre]: { ...(prev[localNombre] || {}), [colKey]: value },
    }));
    scheduleRowSave(localNombre);
  }

  async function handleConfirmar(row: PlanillaRow) {
    if (!selectedMes) return;
    setConfirmingRow(row.local_nombre);
    try {
      await redexpressApi.confirmar(selectedMes.year, selectedMes.month, row.local_nombre);
      setRows((prev) =>
        prev.map((r) =>
          r.local_nombre === row.local_nombre
            ? { ...r, confirmado: true, confirmed_at: new Date().toISOString() }
            : r
        )
      );
      toast.success(t("redexpress.pedidoConfirmado"));
    } catch {
      toast.error(t("redexpress.errorConfirmar"));
    } finally {
      setConfirmingRow(null);
    }
  }

  async function handleDesconfirmar(row: PlanillaRow) {
    if (!selectedMes) return;
    try {
      await redexpressApi.desconfirmar(selectedMes.year, selectedMes.month, row.local_nombre);
      setRows((prev) =>
        prev.map((r) =>
          r.local_nombre === row.local_nombre ? { ...r, confirmado: false, confirmed_at: null } : r
        )
      );
      toast.success(t("redexpress.pedidoDesconfirmado"));
    } catch {
      toast.error(t("redexpress.errorDesconfirmar"));
    }
  }

  async function handleCrearMes() {
    try {
      await redexpressApi.crearMes(newYear, newMonth);
      toast.success(t("redexpress.mesCreado", { month: MONTH_NAMES[newMonth], year: newYear }));
      setShowNewMes(false);
      await loadMeses();
      setSelected({ year: newYear, month: newMonth });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || t("redexpress.errorCrearMes"));
    }
  }

  const visibleRows = filterOnly && !isSuperuser
    ? rows.filter((r) => r.can_edit)
    : rows;

  const confirmadoCount = rows.filter((r) => r.confirmado).length;

  function getCellValue(row: PlanillaRow, colKey: string): string {
    const editVal = edits[row.local_nombre]?.[colKey];
    if (editVal !== undefined) return editVal;
    const v = (row as any)[colKey];
    return v !== null && v !== undefined ? String(v) : "";
  }

  function handleExportExcel() {
    if (!selectedMes) return;
    const data = visibleRows.map((row) => {
      const out: Record<string, string | number> = { [t("redexpress.local")]: row.local_nombre };
      for (const col of ALL_COLS) {
        const v = getCellValue(row, col.key);
        out[`${col.group} — ${col.label}`] = col.isText ? v : (v === "" ? "" : Number(v));
      }
      out[t("redexpress.otrosNotas")] = row.otros ?? "";
      out[t("redexpress.estado")] = row.confirmado
        ? t("redexpress.confirmarPedido")
        : t("redexpress.pendiente");
      return out;
    });
    const ws = XLSX.utils.json_to_sheet(data);
    ws["!cols"] = [{ wch: 24 }, ...ALL_COLS.map(() => ({ wch: 14 })), { wch: 20 }, { wch: 14 }];
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Planilla");
    const mesNombre = MONTH_NAMES[selectedMes.month - 1] ?? String(selectedMes.month);
    XLSX.writeFile(wb, `planilla_${mesNombre}_${selectedMes.year}.xlsx`);
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            {t("redexpress.title")}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            {t("redexpress.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {rows.length > 0 && (
            <span className="text-xs text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-lg">
              {t("redexpress.confirmadosCount", { count: confirmadoCount, total: rows.length })}
            </span>
          )}
          {rows.length > 0 && (
            <button
              onClick={handleExportExcel}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-emerald-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
            >
              <Download size={13} />
              {t("precios.downloadExcel")}
            </button>
          )}
          {!isSuperuser && rows.some((r) => r.can_edit) && (
            <button
              onClick={() => setFilterOnly((f) => !f)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                filterOnly
                  ? "border-brand-500 text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-500/20"
                  : "border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600"
              }`}
            >
              {filterOnly ? t("redexpress.verTodos") : t("redexpress.soloMiLocal")}
            </button>
          )}
          {isSuperuser && (
            <button
              onClick={() => setShowNewMes((v) => !v)}
              className="btn-secondary text-xs py-2 px-3"
            >
              <Plus size={13} /> {t("redexpress.nuevoMes")}
            </button>
          )}
        </div>
      </div>

      {/* New month form */}
      {showNewMes && isSuperuser && (
        <div className="card p-4 flex items-center gap-3 animate-slide-up">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("redexpress.crearMesLabel")}</span>
          <select
            value={newMonth}
            onChange={(e) => setNewMonth(Number(e.target.value))}
            className="input text-xs py-1.5 w-32"
          >
            {MONTH_NAMES.slice(1).map((m, i) => (
              <option key={i + 1} value={i + 1}>{m}</option>
            ))}
          </select>
          <input
            type="number"
            value={newYear}
            onChange={(e) => setNewYear(Number(e.target.value))}
            className="input text-xs py-1.5 w-24"
            min={2024} max={2030}
          />
          <button onClick={handleCrearMes} className="btn-primary text-xs py-2 px-3">
            {t("redexpress.crear")}
          </button>
          <button onClick={() => setShowNewMes(false)} className="btn-secondary text-xs py-2 px-3">
            {t("redexpress.cancelar")}
          </button>
        </div>
      )}

      {/* Month tabs */}
      <div className="flex gap-1.5 flex-wrap">
        {meses.map((m) => (
          <button
            key={`${m.year}-${m.month}`}
            onClick={() => setSelected(m)}
            className={clsx(
              "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              selectedMes?.year === m.year && selectedMes?.month === m.month
                ? "bg-brand-600 text-white shadow-sm"
                : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
            )}
          >
            {MONTH_NAMES[m.month]} {m.year}
          </button>
        ))}
        {meses.length === 0 && !loading && (
          <p className="text-sm text-slate-400 dark:text-slate-500">{t("redexpress.noMeses")}</p>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <div className="card p-10 flex items-center justify-center">
          <RefreshCw size={20} className="animate-spin text-slate-400" />
        </div>
      ) : selectedMes && rows.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto overflow-y-auto max-h-[calc(100svh-18rem)]">
            <table className="w-full text-xs border-collapse">
              {/* Group headers */}
              <thead className="sticky top-0 z-20">
                <tr className="bg-slate-50 dark:bg-slate-950">
                  <th className="sticky left-0 z-30 bg-slate-50 dark:bg-slate-950 w-52 min-w-[200px] border-b border-r border-slate-200 dark:border-slate-800 px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400 text-[11px] uppercase tracking-wide">
                    {t("redexpress.local")}
                  </th>
                  {GROUPS.map((g) => (
                    <th
                      key={g.label}
                      colSpan={g.cols.length}
                      className={clsx(
                        "border-b border-slate-200 dark:border-slate-800 px-2 py-1.5 text-center font-semibold text-[10px] uppercase tracking-wider",
                        g.color
                      )}
                    >
                      {g.label}
                    </th>
                  ))}
                  <th className="border-b border-slate-200 dark:border-slate-800 px-2 py-1.5 text-center font-semibold text-[10px] uppercase tracking-wider bg-slate-100 dark:bg-slate-900 text-slate-500">
                    {t("redexpress.otrosNotas")}
                  </th>
                  <th className="border-b border-slate-200 dark:border-slate-800 px-2 py-1.5 text-center font-semibold text-[10px] uppercase tracking-wider bg-slate-100 dark:bg-slate-900 text-slate-500">
                    {t("redexpress.estado")}
                  </th>
                </tr>
                {/* Column labels */}
                <tr className="bg-white dark:bg-slate-900">
                  <th className="sticky left-0 z-30 bg-white dark:bg-slate-900 border-b border-r border-slate-200 dark:border-slate-800 px-3 py-1.5" />
                  {ALL_COLS.map((col) => (
                    <th
                      key={col.key}
                      className="border-b border-slate-100 dark:border-slate-800 px-1.5 py-1.5 text-center font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap"
                      style={{ minWidth: col.isText ? 80 : 64 }}
                    >
                      {col.label}
                    </th>
                  ))}
                  <th className="border-b border-slate-100 dark:border-slate-800 px-2 py-1.5 text-center font-medium text-slate-500 dark:text-slate-400" style={{ minWidth: 140 }}>
                    {t("redexpress.notasLibres")}
                  </th>
                  <th className="border-b border-slate-100 dark:border-slate-800 px-2 py-1.5" style={{ minWidth: 120 }} />
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const isSaving = savingRow === row.local_nombre;
                  const isConfirming = confirmingRow === row.local_nombre;
                  const hasEdits = !!edits[row.local_nombre];
                  return (
                    <tr
                      key={row.local_nombre}
                      className={clsx(
                        "border-b border-slate-100 dark:border-slate-800 transition-colors",
                        row.confirmado
                          ? "bg-emerald-50/60 dark:bg-emerald-500/10"
                          : row.can_edit
                          ? "bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                          : "bg-slate-50/50 dark:bg-slate-900/30"
                      )}
                    >
                      {/* Local name */}
                      <td className="sticky left-0 z-10 bg-inherit border-r border-slate-200 dark:border-slate-800 px-3 py-2 font-medium text-slate-800 dark:text-slate-200 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          {row.confirmado && (
                            <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
                          )}
                          <span className="truncate max-w-[180px]" title={row.local_nombre}>
                            {row.local_nombre}
                          </span>
                          {isSaving && (
                            <RefreshCw size={10} className="animate-spin text-brand-400 shrink-0" />
                          )}
                        </div>
                      </td>

                      {/* Numeric / text columns */}
                      {ALL_COLS.map((col) => {
                        const val = getCellValue(row, col.key);
                        const isEditable = row.can_edit && !row.confirmado;
                        return (
                          <td key={col.key} className="px-1 py-0.5 text-center">
                            {isEditable ? (
                              <input
                                type={col.isText ? "text" : "number"}
                                min={0}
                                max={col.max}
                                value={val}
                                onChange={(e) =>
                                  handleCellChange(row.local_nombre, col.key, e.target.value)
                                }
                                className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-center text-xs py-1 px-1 outline-none transition-colors"
                                style={{ minWidth: col.isText ? 70 : 52 }}
                                placeholder="—"
                              />
                            ) : (
                              <span className={clsx("text-xs", val ? "text-slate-700 dark:text-slate-300" : "text-slate-300 dark:text-slate-600")}>
                                {val || "—"}
                              </span>
                            )}
                          </td>
                        );
                      })}

                      {/* Otros / notas */}
                      <td className="px-1 py-0.5">
                        {row.can_edit && !row.confirmado ? (
                          <input
                            type="text"
                            value={getCellValue(row, "otros")}
                            onChange={(e) =>
                              handleCellChange(row.local_nombre, "otros", e.target.value)
                            }
                            className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-xs py-1 px-1 outline-none transition-colors"
                            placeholder={t("redexpress.notasPlaceholder")}
                          />
                        ) : (
                          <span className="text-xs text-slate-500 dark:text-slate-400 truncate block max-w-[130px]" title={(row as any).otros || ""}>
                            {(row as any).otros || ""}
                          </span>
                        )}
                      </td>

                      {/* Estado + confirmar */}
                      <td className="px-2 py-1 text-center">
                        {row.confirmado ? (
                          <div className="flex items-center justify-center gap-1">
                            <span className="badge badge-green flex items-center gap-1 text-[10px]">
                              <CheckCircle2 size={10} /> {t("redexpress.confirmado")}
                            </span>
                            {isSuperuser && (
                              <button
                                onClick={() => handleDesconfirmar(row)}
                                className="text-[10px] text-slate-400 dark:text-slate-500 hover:text-red-500 ml-1"
                              >
                                ✕
                              </button>
                            )}
                          </div>
                        ) : row.can_edit ? (
                          <button
                            onClick={() => handleConfirmar(row)}
                            disabled={isConfirming || hasEdits}
                            className="text-[11px] font-semibold px-2 py-1 rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors whitespace-nowrap"
                          >
                            {isConfirming ? (
                              <span className="flex items-center gap-1"><RefreshCw size={10} className="animate-spin" /> {t("redexpress.confirmando")}</span>
                            ) : hasEdits ? (
                              <span className="flex items-center gap-1"><Clock size={10} /> {t("redexpress.guardandoEstado")}</span>
                            ) : (
                              t("redexpress.confirmarPedido")
                            )}
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-300 dark:text-slate-600 flex items-center justify-center gap-1">
                            <Clock size={10} /> {t("redexpress.pendiente")}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-slate-100 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/50 flex items-center justify-between">
            <p className="text-[11px] text-slate-400 dark:text-slate-500">
              {t("redexpress.footerConfirmados", { count: confirmadoCount, total: rows.length })}
            </p>
            <p className="text-[11px] text-slate-400 dark:text-slate-500">
              {t("redexpress.footerAutosave")}
            </p>
          </div>
        </div>
      ) : selectedMes ? (
        <div className="card p-12 flex flex-col items-center text-center gap-3">
          <p className="text-sm text-slate-400 dark:text-slate-500">{t("redexpress.noData")}</p>
        </div>
      ) : null}
    </div>
  );
}
