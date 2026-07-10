"use client";
import { useEffect, useState, useRef, useMemo } from "react";
import { redexpressApi, PlanillaRow, authApi } from "@/lib/api";
import { CheckCircle2, Clock, RefreshCw, Store } from "lucide-react";
import { toast } from "sonner";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

// Misma lógica de datos/guardado que planilla/page.tsx (la de Valentina),
// pero con una sola fila — la del local asignado al usuario logueado — en
// vez de una tabla con las ~65 sucursales. Reusa el mismo endpoint de
// confirmar, pero llama a /redexpress/mi-planilla en vez de /redexpress/planilla
// (ese devuelve solo la fila propia, nunca la de otras sucursales).

export default function MiPedidoPage() {
  const { t } = useTranslation();

  const GROUPS: { label: string; color: string; cols: { key: string; label: string; max?: number; isText?: boolean }[] }[] = useMemo(() => [
    {
      label: t("redexpress.groups.ofertas"),
      color: "bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200",
      cols: [
        { key: "a4_oferta_vertical",  label: t("redexpress.cols.a4OfertaVertical"), max: 200 },
        { key: "cenefa_oferta_x3",    label: t("redexpress.cols.cenefaOfertaX3"),   max: 300 },
        { key: "pinchos",             label: t("redexpress.cols.pinchos"),          max: 100 },
        { key: "afiche_54x74",        label: t("redexpress.cols.afiche54x74"),      max: 20 },
      ],
    },
    {
      label: t("redexpress.groups.vdsSupremo"),
      color: "bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200",
      cols: [
        { key: "cenefa_valle_del_sol",  label: t("redexpress.cols.cenefaValleDelSol"),  max: 100 },
        { key: "cenefa_supremo_hogar",  label: t("redexpress.cols.cenefaSupremoHogar"), max: 100 },
      ],
    },
    {
      label: t("redexpress.groups.bombas"),
      color: "bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200",
      cols: [
        { key: "bombas_3xa4",    label: t("redexpress.cols.bombas3xa4"),    max: 200 },
        { key: "bombas_a4",      label: t("redexpress.cols.bombasA4"),      max: 200 },
        { key: "bombas_74x54",   label: t("redexpress.cols.bombas74x54"),   max: 20 },
        { key: "pinchos_bombas", label: t("redexpress.cols.pinchosBombas"), max: 100 },
      ],
    },
    {
      label: t("redexpress.groups.stickers"),
      color: "bg-pink-100 dark:bg-pink-900/30 text-pink-800 dark:text-pink-200",
      cols: [
        { key: "sticker_valle_del_sol", label: t("redexpress.cols.stickerValleDelSol"), max: 100 },
        { key: "sticker_carne",         label: t("redexpress.cols.stickerCarne"),       max: 100 },
      ],
    },
    {
      label: t("redexpress.groups.otrosItems"),
      color: "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-200",
      cols: [
        { key: "cenefas_preciazos",       label: t("redexpress.cols.cenefasPreciazos"),      max: 100 },
        { key: "cenefas_a4_preciazos",    label: t("redexpress.cols.cenefasA4Preciazos"),    max: 100 },
        { key: "afiche_super_ahorro",     label: t("redexpress.cols.aficheSuperAhorro"),     max: 10 },
        { key: "afiche_grande_preciazos", label: t("redexpress.cols.aficheGrandePreciazos"), max: 10 },
        { key: "pinchos_dias_expres",     label: t("redexpress.cols.pinchosDiasExpres"),     max: 100 },
        { key: "hojas_amarillas",         label: t("redexpress.cols.hojasAmarillas"), isText: true },
      ],
    },
  ], [t]);

  const COL_MAX: Record<string, number> = useMemo(
    () => Object.fromEntries(
      GROUPS.flatMap((g) => g.cols).filter((c) => c.max !== undefined).map((c) => [c.key, c.max as number])
    ),
    [GROUPS]
  );

  const MONTH_NAMES = t("redexpress.months", { returnObjects: true }) as string[];

  const [assignedLocal, setAssignedLocal] = useState<string | null | undefined>(undefined); // undefined = todavía no sabemos
  const [isSuperuser, setIsSuperuser] = useState(false);
  const [locales, setLocales]       = useState<string[]>([]); // solo para superadmin (selector)
  const [selectedLocal, setSelectedLocal] = useState<string | null>(null); // elección manual del superadmin
  const [meses, setMeses]           = useState<{ year: number; month: number }[]>([]);
  const [selectedMes, setSelected]  = useState<{ year: number; month: number } | null>(null);
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
    authApi.me()
      .then(({ data }) => {
        setAssignedLocal(data.assigned_locales?.[0] ?? null);
        setIsSuperuser(!!data.is_superuser);
        if (data.is_superuser) {
          redexpressApi.getLocales()
            .then(({ data: locs }) => setLocales(locs.map((l) => l.local_nombre)))
            .catch(() => setLocales([]));
        }
      })
      .catch(() => setAssignedLocal(null));
    loadMeses();
  }, []);

  async function loadMeses() {
    try {
      const { data } = await redexpressApi.getMeses();
      setMeses(data);
      if (data.length > 0) setSelected(data[data.length - 1]);
    } catch {
      toast.error(t("redexpress.errorCargarMeses"));
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
      const { data } = await redexpressApi.getMiPlanilla(year, month, isSuperuser ? local : undefined);
      setRows(data);
    } catch {
      toast.error(t("redexpress.errorCargarPlanilla"));
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
      const payload: Record<string, number | string | null> = {};
      for (const [key, val] of Object.entries(rowEdits)) {
        if (key === "hojas_amarillas" || key === "otros") {
          payload[key] = val === "" ? null : val;
        } else {
          payload[key] = val === "" ? null : parseInt(val, 10);
          if (typeof payload[key] === "number" && isNaN(payload[key] as number)) payload[key] = null;
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
    setEdits((prev) => ({ ...prev, [localNombre]: { ...(prev[localNombre] || {}), [colKey]: value } }));
    scheduleRowSave(localNombre);
  }

  function getCellValue(row: PlanillaRow, colKey: string): string {
    const editVal = edits[row.local_nombre]?.[colKey];
    if (editVal !== undefined) return editVal;
    const v = (row as any)[colKey];
    return v !== null && v !== undefined ? String(v) : "";
  }

  async function handleConfirmar(row: PlanillaRow) {
    if (!selectedMes) return;
    setConfirming(true);
    try {
      await redexpressApi.confirmar(selectedMes.year, selectedMes.month, row.local_nombre);
      setRows((prev) => prev.map((r) =>
        r.local_nombre === row.local_nombre ? { ...r, confirmado: true, confirmed_at: new Date().toISOString() } : r
      ));
      toast.success(t("redexpress.pedidoConfirmado"));
    } catch {
      toast.error(t("redexpress.errorConfirmar"));
    } finally {
      setConfirming(false);
    }
  }

  const miRow = rows[0];
  const hasEdits = miRow ? !!edits[miRow.local_nombre] : false;
  const isSaving = miRow ? savingRow === miRow.local_nombre : false;
  const isEditable = !!miRow?.can_edit && !miRow?.confirmado;

  return (
    <div className="space-y-4 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-slate-100">
          {t("redexpress.miPedido.title")}
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
          {t("redexpress.miPedido.subtitle")}
        </p>
      </div>

      {assignedLocal !== undefined && (
        <>
          {isSuperuser ? (
            <div className="flex items-center gap-2 flex-wrap">
              <label htmlFor="mi-pedido-local-select" className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {t("redexpress.miPedido.selectLocalLabel")}
              </label>
              <select
                id="mi-pedido-local-select"
                value={selectedLocal ?? ""}
                onChange={(e) => setSelectedLocal(e.target.value || null)}
                className="input text-sm max-w-xs"
              >
                <option value="">{t("redexpress.miPedido.selectLocalPlaceholder")}</option>
                {locales.map((loc) => (
                  <option key={loc} value={loc}>{loc}</option>
                ))}
              </select>
              {miRow?.confirmado && (
                <span className="badge badge-green flex items-center gap-1 text-[10px]">
                  <CheckCircle2 size={10} /> {t("redexpress.confirmado")}
                </span>
              )}
            </div>
          ) : assignedLocal === null ? (
            <div className="card p-8 flex flex-col items-center text-center gap-2">
              <Store size={22} className="text-slate-300" />
              <p className="text-sm text-slate-500 dark:text-slate-400">{t("redexpress.miPedido.noLocalAssigned")}</p>
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300">
                <Store size={12} /> {assignedLocal}
              </span>
              {miRow?.confirmado && (
                <span className="badge badge-green flex items-center gap-1 text-[10px]">
                  <CheckCircle2 size={10} /> {t("redexpress.confirmado")}
                </span>
              )}
            </div>
          )}

          {isSuperuser && !activeLocal && (
            <div className="card p-8 flex flex-col items-center text-center gap-2">
              <Store size={22} className="text-slate-300" />
              <p className="text-sm text-slate-500 dark:text-slate-400">{t("redexpress.miPedido.noLocalSelected")}</p>
            </div>
          )}

          {activeLocal && (
          <>
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
              <p className="text-sm text-slate-400">{t("redexpress.noMeses")}</p>
            )}
          </div>

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
                  {t("redexpress.notasLibres")}
                </label>
                <input
                  type="text"
                  value={getCellValue(miRow, "otros")}
                  disabled={!isEditable}
                  onChange={(e) => handleCellChange(miRow.local_nombre, "otros", e.target.value)}
                  className="input text-sm w-full disabled:opacity-60 disabled:cursor-not-allowed"
                  placeholder={t("redexpress.notasPlaceholder")}
                />
              </div>

              <div className="card p-4 flex items-center justify-between flex-wrap gap-2">
                <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
                  {isSaving && <RefreshCw size={11} className="animate-spin text-brand-400" />}
                  {t("redexpress.footerAutosave")}
                </p>
                {miRow.confirmado ? (
                  <span className="badge badge-green flex items-center gap-1 text-xs">
                    <CheckCircle2 size={12} /> {t("redexpress.confirmado")}
                  </span>
                ) : (
                  <button
                    onClick={() => handleConfirmar(miRow)}
                    disabled={confirming || hasEdits}
                    className="btn-primary text-xs py-2 px-4 disabled:opacity-50"
                  >
                    {confirming ? (
                      <span className="flex items-center gap-1.5"><RefreshCw size={12} className="animate-spin" /> {t("redexpress.confirmando")}</span>
                    ) : hasEdits ? (
                      <span className="flex items-center gap-1.5"><Clock size={12} /> {t("redexpress.guardandoEstado")}</span>
                    ) : (
                      t("redexpress.confirmarPedido")
                    )}
                  </button>
                )}
              </div>
            </div>
          ) : selectedMes ? (
            <div className="card p-12 flex flex-col items-center text-center gap-3">
              <p className="text-sm text-slate-400">{t("redexpress.noData")}</p>
            </div>
          ) : null}
          </>
          )}
        </>
      )}
    </div>
  );
}
