"use client";
import { useEffect, useState, useRef, useMemo } from "react";
import { redexpresApi, PlanillaRow } from "@/lib/api";
import { CalendarX, CheckCircle2, Clock, Lock, RefreshCw, Store } from "lucide-react";
import { toast } from "sonner";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { hasPermission } from "@/lib/permissions";
import SelectorMes from "@/components/redexpres/SelectorMes";
import EditorPlanilla from "@/components/redexpres/EditorPlanilla";
import { useEstructura, valorDeColumna, payloadDeEdicion } from "@/lib/redexpres/estructura";
import { conEdicion, sinLoGuardado, type Ediciones } from "@/lib/redexpres/ediciones";
import { limpiarCantidad, TECLAS_NO_CANTIDAD } from "@/lib/redexpres/cantidades";
import { estadoDelPedido } from "@/lib/redexpres/estado";

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
  // Hasta que llegan los meses no se sabe si hay alguno abierto: sin esto
  // aparecía un instante «Marketing todavía no abrió…» al entrar.
  const [mesesCargados, setMesesCargados] = useState(false);
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

  const [edits, setEdits] = useState<Ediciones>({});
  // Lo último escrito, para el guardado que sale 800 ms después: leer `edits`
  // desde ese momento daba lo de ANTES de la última tecla ("12" guardaba "1").
  const editsRef = useRef<Ediciones>({});
  function ponerEdits(next: Ediciones) {
    editsRef.current = next;
    setEdits(next);
  }
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
      setMesesCargados(true);
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
    ponerEdits({});
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
    const rowEdits = editsRef.current[localNombre];
    if (!rowEdits || Object.keys(rowEdits).length === 0) return;

    setSavingRow(localNombre);
    try {
      const payload = payloadDeEdicion(rowEdits, esTexto);
      const { data: updated } = await redexpresApi.updateRow(
        selectedMes.year, selectedMes.month, localNombre, payload as any
      );
      setRows((prev) => prev.map((r) => r.local_nombre === localNombre ? updated : r));
      // Sale de pendientes solo lo que se mandó: lo que se siguió escribiendo
      // mientras se guardaba queda para el próximo guardado.
      ponerEdits(sinLoGuardado(editsRef.current, localNombre, rowEdits));
    } catch (e: any) {
      // 409: el pedido se confirmó mientras tanto (otra pestaña, o marketing).
      // Se dice por qué y se recarga, así se ve bloqueado y sin lo que no entró.
      if (e?.response?.status === 409) {
        toast.error(e.response.data?.detail || t("redexpres.errorGuardarLocal", { local: localNombre }));
        if (activeLocal) loadPlanilla(selectedMes.year, selectedMes.month, activeLocal);
      } else if (e?.response?.status === 422) {
        // El servidor no aceptó alguna cantidad: lo mandado se descarta y la
        // casilla vuelve a lo guardado, así no queda mostrando algo que no entró.
        ponerEdits(sinLoGuardado(editsRef.current, localNombre, rowEdits));
        toast.error(t("redexpres.revisaCantidades"), { id: "cantidades" });
      } else {
        toast.error(t("redexpres.errorGuardarLocal", { local: localNombre }));
      }
    } finally {
      setSavingRow(null);
    }
  }

  // La tecla «-», «.» o «e» no se escribe (Safari en iOS manda "" con un
  // «-» a medio escribir), pero se avisa por qué no aparece.
  function bloquearTeclaNoCantidad(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!TECLAS_NO_CANTIDAD.has(e.key)) return;
    e.preventDefault();
    toast.warning(t("redexpres.soloEnteros"), { id: "cantidades" });
  }

  function handleCellChange(localNombre: string, colKey: string, value: string) {
    // Las cantidades son enteros desde 0 y sin pasar el tope (H-085): se
    // corrige al escribir y se avisa una sola vez (mismo id, no se apilan).
    if (!esTexto(colKey) && colKey !== "otros") {
      const { valor, aviso } = limpiarCantidad(value, COL_MAX[colKey]);
      value = valor;
      if (aviso === "maximo") toast.warning(t("redexpres.limiteMaximo", { max: COL_MAX[colKey] }), { id: "cantidades" });
      else if (aviso) toast.warning(t("redexpres.soloEnteros"), { id: "cantidades" });
    }
    ponerEdits(conEdicion(editsRef.current, localNombre, colKey, value));
    scheduleRowSave(localNombre);
  }

  function getCellValue(row: PlanillaRow, colKey: string): string {
    const editVal = edits[row.local_nombre]?.[colKey];
    if (editVal !== undefined) return editVal;
    return valorDeColumna(row, colKey);
  }

  async function handleConfirmar(row: PlanillaRow) {
    if (!selectedMes) return;
    // Confirmar no tiene vuelta atrás para el local: se pregunta antes.
    if (!window.confirm(t("redexpres.confirmarSeguro", { mes: nombreMes }))) return;
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
  const estado = estadoDelPedido(meses, selectedMes, miRow);
  // "Diciembre 2026": el mes elegido, o el actual si todavía no hay ninguno.
  const nombresMes = t("redexpres.months", { returnObjects: true }) as string[];
  const mesMostrado = selectedMes ?? { year: new Date().getFullYear(), month: new Date().getMonth() + 1 };
  const nombreMes = `${nombresMes[mesMostrado.month]} ${mesMostrado.year}`;

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
          ) : mesesCargados && (estado === "sinMeses" || estado === "mesNoAbierto") ? (
            <div className="card p-10 flex flex-col items-center text-center gap-3">
              <CalendarX size={22} className="text-slate-500 dark:text-slate-400" aria-hidden />
              <p className="text-sm text-slate-600 dark:text-slate-300 max-w-md">
                {!isSuperuser
                  ? t("redexpres.miPedido.noAbierto", { mes: nombreMes })
                  : estado === "sinMeses"
                    ? t("redexpres.sinMesesGestor")
                    // El gestor llega acá cambiando de año a uno sin ese mes: lo abre tocando la pastilla.
                    : t("redexpres.mesNoHabilitado")}
              </p>
            </div>
          ) : selectedMes && miRow ? (
            <div className="space-y-3">
              {miRow.confirmado && (
                <div
                  role="status"
                  className="flex items-start gap-3 rounded-xl border border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/60 px-4 py-3 text-sm font-medium text-emerald-900 dark:text-emerald-100"
                >
                  <Lock size={16} className="mt-0.5 shrink-0" aria-hidden />
                  <p>
                    {isSuperuser
                      ? t("redexpres.miPedido.yaConfirmadoGestor")
                      : t("redexpres.miPedido.yaConfirmado", { mes: nombreMes })}
                  </p>
                </div>
              )}
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
                          inputMode={col.isText ? undefined : "numeric"}
                          step={col.isText ? undefined : 1}
                          onKeyDown={col.isText ? undefined : bloquearTeclaNoCantidad}
                          min={0}
                          max={col.max}
                          value={getCellValue(miRow, col.key)}
                          disabled={!isEditable}
                          onChange={(e) => handleCellChange(miRow.local_nombre, col.key, e.target.value)}
                          className="input text-sm w-full disabled:bg-transparent dark:disabled:bg-transparent disabled:border-dashed disabled:border-slate-300 dark:disabled:border-slate-600 disabled:text-slate-700 dark:disabled:text-slate-200 disabled:cursor-not-allowed"
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
                  className="input text-sm w-full disabled:bg-transparent dark:disabled:bg-transparent disabled:border-dashed disabled:border-slate-300 dark:disabled:border-slate-600 disabled:text-slate-700 dark:disabled:text-slate-200 disabled:cursor-not-allowed"
                  placeholder={t("redexpres.notasPlaceholder")}
                />
              </div>

              <div className="card p-4 flex items-center justify-between flex-wrap gap-2">
                {/* Confirmado ya no se guarda nada: el texto de autoguardado confundía. */}
                {miRow.confirmado ? <span /> : (
                  <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
                    {isSaving && <RefreshCw size={11} className="animate-spin text-brand-400" />}
                    {t("redexpres.footerAutosave")}
                  </p>
                )}
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
