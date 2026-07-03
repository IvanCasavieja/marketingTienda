"use client";
import { useEffect, useState, useRef } from "react";
import { redexpressApi, PlanillaRow, authApi } from "@/lib/api";
import { CheckCircle2, Clock, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { clsx } from "clsx";

// ── Column definitions ─────────────────────────────────────────────────────────

const GROUPS = [
  {
    label: "Ofertas",
    color: "bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200",
    cols: [
      { key: "a4_oferta_vertical",  label: "A4 Oferta Vertical" },
      { key: "cenefa_oferta_x3",    label: "Cenefa Oferta x3" },
      { key: "pinchos",             label: "Pinchos" },
      { key: "afiche_54x74",        label: "Afiche 54x74" },
    ],
  },
  {
    label: "VDS y Supremo",
    color: "bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200",
    cols: [
      { key: "cenefa_valle_del_sol",  label: "Cenefa Valle del Sol" },
      { key: "cenefa_supremo_hogar",  label: "Cenefa Supremo Hogar" },
    ],
  },
  {
    label: "Bombas",
    color: "bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200",
    cols: [
      { key: "bombas_3xa4",    label: "Bombas 3xA4" },
      { key: "bombas_a4",      label: "Bombas A4" },
      { key: "bombas_74x54",   label: "Bombas 74x54" },
      { key: "pinchos_bombas", label: "Pinchos Bombas" },
    ],
  },
  {
    label: "Stickers",
    color: "bg-pink-100 dark:bg-pink-900/30 text-pink-800 dark:text-pink-200",
    cols: [
      { key: "sticker_valle_del_sol", label: "Sticker VDS" },
      { key: "sticker_carne",         label: "Sticker Carne" },
    ],
  },
  {
    label: "Otros items",
    color: "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-200",
    cols: [
      { key: "cenefas_preciazos",    label: "Cenefas Preciazos" },
      { key: "afiche_super_ahorro",  label: "Afiche Super Ahorro" },
      { key: "pinchos_dias_expres",  label: "Pinchos Días Expres" },
      { key: "hojas_amarillas",      label: "Hojas Amarillas", isText: true },
    ],
  },
] as const;

type ColKey = string;

const ALL_COLS: { key: ColKey; label: string; isText?: boolean; group: string }[] = GROUPS.flatMap(
  (g) => g.cols.map((c) => ({ ...c, group: g.label }))
);

const MONTH_NAMES = [
  "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

// ── Main component ─────────────────────────────────────────────────────────────

export default function PlanillaPedidosPage() {
  const [meses, setMeses]         = useState<{ year: number; month: number }[]>([]);
  const [selectedMes, setSelected] = useState<{ year: number; month: number } | null>(null);
  const [rows, setRows]           = useState<PlanillaRow[]>([]);
  const [loading, setLoading]     = useState(false);
  const [isSuperuser, setIsSuperuser] = useState(false);
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
    authApi.me().then(({ data }) => setIsSuperuser(data.is_superuser)).catch(() => {});
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
      toast.error("Error al cargar meses");
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
      toast.error("Error al cargar la planilla");
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
      toast.error(`Error al guardar ${localNombre}`);
    } finally {
      setSavingRow(null);
    }
  }

  function handleCellChange(localNombre: string, colKey: string, value: string) {
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
      toast.success("Pedido confirmado");
    } catch {
      toast.error("Error al confirmar");
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
      toast.success("Pedido desconfirmado");
    } catch {
      toast.error("Error al desconfirmar");
    }
  }

  async function handleCrearMes() {
    try {
      await redexpressApi.crearMes(newYear, newMonth);
      toast.success(`Mes ${MONTH_NAMES[newMonth]} ${newYear} creado`);
      setShowNewMes(false);
      await loadMeses();
      setSelected({ year: newYear, month: newMonth });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Error al crear mes");
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

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
            Planilla de pedidos
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Redexpress · cartelería mensual
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {rows.length > 0 && (
            <span className="text-xs text-slate-400 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-lg">
              {confirmadoCount}/{rows.length} confirmados
            </span>
          )}
          {!isSuperuser && rows.some((r) => r.can_edit) && (
            <button
              onClick={() => setFilterOnly((f) => !f)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                filterOnly
                  ? "border-brand-500 text-brand-600 bg-brand-50 dark:bg-brand-900/20"
                  : "border-slate-200 dark:border-slate-700 text-slate-500 hover:border-slate-300"
              }`}
            >
              {filterOnly ? "Ver todos" : "Solo mi local"}
            </button>
          )}
          {isSuperuser && (
            <button
              onClick={() => setShowNewMes((v) => !v)}
              className="btn-secondary text-xs py-2 px-3"
            >
              <Plus size={13} /> Nuevo mes
            </button>
          )}
        </div>
      </div>

      {/* New month form */}
      {showNewMes && isSuperuser && (
        <div className="card p-4 flex items-center gap-3 animate-slide-up">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Crear mes:</span>
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
            Crear
          </button>
          <button onClick={() => setShowNewMes(false)} className="btn-secondary text-xs py-2 px-3">
            Cancelar
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
          <p className="text-sm text-slate-400">No hay meses cargados todavía.</p>
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
                    Local
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
                    Otros / notas
                  </th>
                  <th className="border-b border-slate-200 dark:border-slate-800 px-2 py-1.5 text-center font-semibold text-[10px] uppercase tracking-wider bg-slate-100 dark:bg-slate-900 text-slate-500">
                    Estado
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
                    Notas libres
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
                          ? "bg-emerald-50/60 dark:bg-emerald-900/10"
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
                            placeholder="notas..."
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
                              <CheckCircle2 size={10} /> Confirmado
                            </span>
                            {isSuperuser && (
                              <button
                                onClick={() => handleDesconfirmar(row)}
                                className="text-[10px] text-slate-400 hover:text-red-500 ml-1"
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
                              <span className="flex items-center gap-1"><RefreshCw size={10} className="animate-spin" /> Confirmando...</span>
                            ) : hasEdits ? (
                              <span className="flex items-center gap-1"><Clock size={10} /> Guardando...</span>
                            ) : (
                              "Confirmar pedido"
                            )}
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-300 dark:text-slate-600 flex items-center justify-center gap-1">
                            <Clock size={10} /> Pendiente
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
            <p className="text-[11px] text-slate-400">
              {confirmadoCount} de {rows.length} locales confirmados
            </p>
            <p className="text-[11px] text-slate-400">
              Los cambios se guardan automáticamente al dejar de escribir
            </p>
          </div>
        </div>
      ) : selectedMes ? (
        <div className="card p-12 flex flex-col items-center text-center gap-3">
          <p className="text-sm text-slate-400">No hay datos para este mes.</p>
        </div>
      ) : null}
    </div>
  );
}
