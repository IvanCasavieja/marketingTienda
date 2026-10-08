"use client";
import { useEffect, useState, useRef, useMemo } from "react";
import { redexpresApi, PlanillaRow } from "@/lib/api";
import { CheckCircle2, Clock, RefreshCw, Store } from "lucide-react";
import { toast } from "sonner";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import SelectorMes from "@/components/redexpres/SelectorMes";
import EditorPlanilla from "@/components/redexpres/EditorPlanilla";
import { useEstructura, valorDeColumna, payloadDeEdicion } from "@/lib/redexpres/estructura";

// Misma lógica de datos/guardado que planilla/page.tsx (la de Valentina),
// pero con una sola fila — la del local asignado al usuario logueado — en
// vez de una tabla con las ~65 sucursales. Reusa el mismo endpoint de
// confirmar, pero llama a /redexpres/mi-planilla en vez de /redexpres/planilla
// (ese devuelve solo la fila propia, nunca la de otras sucursales).

export default function MiPedidoPage() {
  const { t } = useTranslation();

  const { user: currentUser, loading: loadingUser } = useCurrentUser();
  // Perfil completo (ver y editar cualquier sucursal, crear meses): superusuarios y
  // quien tenga redexpres.manage (Lucía y Valentina). Ver _es_gestor en el backend.
  const isSuperuser = !!currentUser && (currentUser.is_superuser || hasPermission(currentUser, "redexpres.manage"));
  // undefined = todavía no sabemos (usuario sin resolver todavía)
  const assignedLocal = loadingUser ? undefined : (currentUser?.assigned_locales?.[0] ?? null);
  const [locales, setLocales]       = useState<string[]>([]); // solo para superadmin (selector)
  const [selectedLocal, setSelectedLocal] = useState<string | null>(null); // elección manual del superadmin
  const [meses, setMeses]           = useState<{ year: number; month: number }[]>([]);
  const [selectedMes, setSelected]  = useState<{ year: number; month: number } | null>(null);
  // La planilla del mes (grupos, columnas y topes) viene de la base y la edita quien gestiona.
  const { estructura, grupos: GROUPS, puedeEditar, recargar: recargarEstructura } = useEstructura(selectedMes);
  const [editando, setEditando] = useState(false);
  const ALL_COLS = useMemo(() => GROUPS.flatMap((g) => g.cols), [GROUPS]);
  const COL_MAX: Record<string, number> = useMemo(
    () => Object.fromEntries(ALL_COLS.filter((c) => c.max !== undefined).map((c) => [c.key, c.max as number])),
    [ALL_COLS]
  );
  const esTexto = (key: string) => !!ALL_COLS.find((c) => c.key === key)?.isText;

  const [rows, setRows]             = useState<PlanillaRow[]>([]);
  const [loading, setLoading]       = useState(false);
  const [savingRow, setSavingRow]   = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const pendingSaves = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Local "activo": para sucursales es la propia (fija), para superadmin es
  // la que elija en el selector (arranca vacío = pantalla general sin datos).
  const activeLocal = isSuperuser ? selectedLocal : (assignedLocal ?? null);

  useEffect(() => {
    if (isSuperuser) {
      redexpresApi.getLocales()
        .then(({ data: locs }) => setLocales(locs.map((l) => l.local_nombre)))
        .catch(() => setLocales([]));
    }
  }, [currentUser, isSuperuser]);

  useEffect(() => {
    loadMeses();
  }, []);

  async function loadMeses() {
    try {
      const { data } = await redexpresApi.getMeses();
      setMeses(data);
      if (data.length > 0) setSelected(data[data.length - 1]);
    } catch {
      toast.error(t("redexpres.errorCargarMeses"));
    }
  }

  async function crearMesVacio(m: { year: number; month: number }) {
    try {
      await redexpresApi.crearMes(m.year, m.month);
      setMeses((prev) => [...prev, m].sort((a, b) => a.year - b.year || a.month - b.month));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || t("redexpres.errorCrearMes"));
      throw e;
    }
  }

  useEffect(() => {
    if (selectedMes && activeLocal) loadPlanilla(selectedMes.year, selectedMes.month, activeLocal);
    else setRows([]);
  }, [selectedMes, activeLocal]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadPlanilla(year: number, month: number, local: string) {
    setLoading(true);
    setEdits({});
    try {
      const { data } = await redexpresApi.getMiPlanilla(year, month, isSuperuser ? local : undefined);
      setRows(data);
    } catch {
      toast.error(t("redexpres.errorCargarPlanilla"));
    } finally {
      setLoading(false);
    }
  }

  function scheduleRowSave(localNombre: string) {
    if (pendingSaves.current[localNombre]) clearTimeout(pendingSaves.current[localNombre]);
    pendingSaves.current[localNombre] = setTimeout(() => flushRowSave(localNombre), 800);
  }

  async function flushRowSave(localNombre: string) {
    if (!selectedMes) return;
    const rowEdits = edits[localNombre];
    if (!rowEdits || Object.keys(rowEdits).length === 0) return;

    setSavingRow(localNombre);
    try {
      const payload = payloadDeEdicion(rowEdits, esTexto);
      const { data: updated } = await redexpresApi.updateRow(
        selectedMes.year, selectedMes.month, localNombre, payload as any
      );
      setRows((prev) => prev.map((r) => r.local_nombre === localNombre ? updated : r));
      setEdits((prev) => {
        const next = { ...prev };
        delete next[localNombre];
        return next;
      });
    } catch {
      toast.error(t("redexpres.errorGuardarLocal", { local: localNombre }));
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
        toast.warning(t("redexpres.limiteMaximo", { max }));
      }
    }
    setEdits((prev) => ({ ...prev, [localNombre]: { ...(prev[localNombre] || {}), [colKey]: value } }));
    scheduleRowSave(localNombre);
  }

  function getCellValue(row: PlanillaRow, colKey: string): string {
    const editVal = edits[row.local_nombre]?.[colKey];
    if (editVal !== undefined) return editVal;
    return valorDeColumna(row, colKey);
  }

  async function handleConfirmar(row: PlanillaRow) {
    if (!selectedMes) return;
    setConfirming(true);
    try {
      await redexpresApi.confirmar(selectedMes.year, selectedMes.month, row.local_nombre);
      setRows((prev) => prev.map((r) =>
        r.local_nombre === row.local_nombre ? { ...r, confirmado: true, confirmed_at: new Date().toISOString() } : r
      ));
      toast.success(t("redexpres.pedidoConfirmado"));
    } catch {
      toast.error(t("redexpres.errorConfirmar"));
    } finally {
      setConfirming(false);
    }
  }

  const miRow = rows[0];
  const hasEdits = miRow ? !!edits[miRow.local_nombre] : false;
  const isSaving = miRow ? savingRow === miRow.local_nombre : false;
  const isEditable = !!miRow?.can_edit && !miRow?.confirmado;

  return (
    <div className="space-y-4 animate-fade-in max-w-6xl">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
          {t("redexpres.miPedido.title")}
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
          {t("redexpres.miPedido.subtitle")}
        </p>
      </div>

      {assignedLocal !== undefined && (
        <>
          {isSuperuser ? (
            <div className="flex items-center gap-2 flex-wrap">
              <label htmlFor="mi-pedido-local-select" className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {t("redexpres.miPedido.selectLocalLabel")}
              </label>
              <select
                id="mi-pedido-local-select"
                value={selectedLocal ?? ""}
                onChange={(e) => setSelectedLocal(e.target.value || null)}
                className="input text-sm max-w-xs"
              >
                <option value="">{t("redexpres.miPedido.selectLocalPlaceholder")}</option>
                {locales.map((loc) => (
                  <option key={loc} value={loc}>{loc}</option>
                ))}
              </select>
              {miRow?.confirmado && (
                <span className="badge badge-green flex items-center gap-1 text-[10px]">
                  <CheckCircle2 size={10} /> {t("redexpres.confirmado")}
                </span>
              )}
            </div>
          ) : assignedLocal === null ? (
            <div className="card p-8 flex flex-col items-center text-center gap-2">
              <Store size={22} className="text-slate-300" />
              <p className="text-sm text-slate-500 dark:text-slate-400">{t("redexpres.miPedido.noLocalAssigned")}</p>
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300">
                <Store size={12} /> {assignedLocal}
              </span>
              {miRow?.confirmado && (
                <span className="badge badge-green flex items-center gap-1 text-[10px]">
                  <CheckCircle2 size={10} /> {t("redexpres.confirmado")}
                </span>
              )}
            </div>
          )}

          {isSuperuser && !activeLocal && (
            <div className="card p-8 flex flex-col items-center text-center gap-2">
              <Store size={22} className="text-slate-300" />
              <p className="text-sm text-slate-500 dark:text-slate-400">{t("redexpres.miPedido.noLocalSelected")}</p>
            </div>
          )}

          {activeLocal && (
          <>
          {/* Año + 12 meses fijos (Ivan, 08/10/2026) */}
          <SelectorMes
            meses={meses}
            seleccionado={selectedMes}
            onSeleccionar={setSelected}
            onCrear={isSuperuser ? crearMesVacio : undefined}
          />

          {puedeEditar && selectedMes && estructura && (
            <button onClick={() => setEditando(true)} className="btn-secondary text-xs">
              Editar planilla de este mes
            </button>
          )}
          {editando && selectedMes && estructura && (
            <EditorPlanilla
              year={selectedMes.year} month={selectedMes.month} inicial={estructura}
              onGuardado={recargarEstructura} onCerrar={() => setEditando(false)}
            />
          )}

          {loading ? (
            <div className="card p-10 flex items-center justify-center">
              <RefreshCw size={20} className="animate-spin text-slate-400" />
            </div>
          ) : selectedMes && miRow ? (
            <div className="space-y-3">
              {GROUPS.map((g) => (
                <div key={g.label} className="card p-4">
                  <span className={clsx("inline-block text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-lg mb-3", g.color)}>
                    {g.label}
                  </span>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {g.cols.map((col) => (
                      <div key={col.key}>
                        <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">
                          {col.label}
                        </label>
                        <input
                          type={col.isText ? "text" : "number"}
                          min={0}
                          max={col.max}
                          value={getCellValue(miRow, col.key)}
                          disabled={!isEditable}
                          onChange={(e) => handleCellChange(miRow.local_nombre, col.key, e.target.value)}
                          className="input text-sm w-full disabled:opacity-60 disabled:cursor-not-allowed"
                          placeholder="—"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <div className="card p-4">
                <label className="block text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1">
                  {t("redexpres.notasLibres")}
                </label>
                <input
                  type="text"
                  value={getCellValue(miRow, "otros")}
                  disabled={!isEditable}
                  onChange={(e) => handleCellChange(miRow.local_nombre, "otros", e.target.value)}
                  className="input text-sm w-full disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder={t("redexpres.notasPlaceholder")}
                />
              </div>

              <div className="card p-4 flex items-center justify-between flex-wrap gap-2">
                <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
                  {isSaving && <RefreshCw size={11} className="animate-spin text-brand-400" />}
                  {t("redexpres.footerAutosave")}
                </p>
                {miRow.confirmado ? (
                  <span className="badge badge-green flex items-center gap-1 text-xs">
                    <CheckCircle2 size={12} /> {t("redexpres.confirmado")}
                  </span>
                ) : (
                  <button
                    onClick={() => handleConfirmar(miRow)}
                    disabled={confirming || hasEdits}
                    className="btn-primary text-xs py-2 px-4 disabled:opacity-50"
                  >
                    {confirming ? (
                      <span className="flex items-center gap-1.5"><RefreshCw size={12} className="animate-spin" /> {t("redexpres.confirmando")}</span>
                    ) : hasEdits ? (
                      <span className="flex items-center gap-1.5"><Clock size={12} /> {t("redexpres.guardandoEstado")}</span>
                    ) : (
                      t("redexpres.confirmarPedido")
                    )}
                  </button>
                )}
              </div>
            </div>
          ) : selectedMes ? (
            <div className="card p-12 flex flex-col items-center text-center gap-3">
              <p className="text-sm text-slate-400">{t("redexpres.noData")}</p>
            </div>
          ) : null}
          </>
          )}
        </>
      )}
    </div>
  );
}
