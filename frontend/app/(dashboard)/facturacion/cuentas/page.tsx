"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Landmark, Loader2, Pencil, Plus, RotateCcw, Trash2, X, Check, Eye, EyeOff } from "lucide-react";
import { facturacionCuentasApi, type FacturacionCuenta } from "@/lib/api";

export default function FacturacionCuentasPage() {
  const { t } = useTranslation();
  const [cuentas, setCuentas] = useState<FacturacionCuenta[]>([]);
  const [loading, setLoading] = useState(true);
  const [mostrarInactivas, setMostrarInactivas] = useState(false);
  const [nombreNuevo, setNombreNuevo] = useState("");
  const [creando, setCreando] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [nombreEditado, setNombreEditado] = useState("");
  const [guardandoId, setGuardandoId] = useState<number | null>(null);
  const [confirmandoId, setConfirmandoId] = useState<number | null>(null);

  function load(incluirInactivas: boolean) {
    setLoading(true);
    facturacionCuentasApi
      .listar(incluirInactivas)
      .then(({ data }) => setCuentas(data))
      .catch(() => toast.error(t("facturacion.upload.error")))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(mostrarInactivas);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mostrarInactivas]);

  async function handleCrear(e: FormEvent) {
    e.preventDefault();
    const nombre = nombreNuevo.trim();
    if (!nombre) return;
    setCreando(true);
    try {
      const { data } = await facturacionCuentasApi.crear(nombre);
      setCuentas((prev) => [...prev, data].sort((a, b) => a.nombre.localeCompare(b.nombre)));
      setNombreNuevo("");
      toast.success(t("facturacion.cuentas.creada"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("facturacion.upload.error"));
    } finally {
      setCreando(false);
    }
  }

  function startEdit(c: FacturacionCuenta) {
    setEditandoId(c.id);
    setNombreEditado(c.nombre);
  }

  async function handleGuardarNombre(id: number) {
    const nombre = nombreEditado.trim();
    if (!nombre) return;
    setGuardandoId(id);
    try {
      const { data } = await facturacionCuentasApi.editar(id, { nombre });
      setCuentas((prev) => prev.map((c) => (c.id === id ? data : c)));
      setEditandoId(null);
      toast.success(t("facturacion.cuentas.actualizada"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("facturacion.upload.error"));
    } finally {
      setGuardandoId(null);
    }
  }

  async function handleToggleActiva(c: FacturacionCuenta) {
    setGuardandoId(c.id);
    setConfirmandoId(null);
    try {
      const { data } = await facturacionCuentasApi.editar(c.id, { activa: !c.activa });
      if (!mostrarInactivas && !data.activa) {
        setCuentas((prev) => prev.filter((x) => x.id !== c.id));
      } else {
        setCuentas((prev) => prev.map((x) => (x.id === c.id ? data : x)));
      }
      toast.success(t("facturacion.cuentas.actualizada"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("facturacion.upload.error"));
    } finally {
      setGuardandoId(null);
    }
  }

  return (
    <div className="animate-fade-in w-full space-y-6">
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-2xl bg-amber-500/10 flex items-center justify-center shrink-0">
          <Landmark size={22} className="text-amber-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("facturacion.cuentas.title")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t("facturacion.cuentas.subtitle")}</p>
        </div>
      </div>

      <div className="card p-6 max-w-2xl space-y-5">
        <form onSubmit={handleCrear} className="flex gap-2">
          <input
            type="text"
            value={nombreNuevo}
            onChange={(e) => setNombreNuevo(e.target.value)}
            placeholder={t("facturacion.cuentas.nombrePlaceholder")}
            className="input text-sm flex-1"
          />
          <button
            type="submit"
            disabled={creando || !nombreNuevo.trim()}
            className="btn-primary text-xs flex items-center gap-1.5 disabled:opacity-50 shrink-0"
          >
            {creando ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            {creando ? t("facturacion.cuentas.creando") : t("facturacion.cuentas.crear")}
          </button>
        </form>

        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{t("facturacion.cuentas.title")}</p>
          <button
            onClick={() => setMostrarInactivas((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400"
          >
            {mostrarInactivas ? <EyeOff size={13} /> : <Eye size={13} />}
            {mostrarInactivas ? t("facturacion.cuentas.ocultarInactivas") : t("facturacion.cuentas.verInactivas")}
          </button>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <div key={i} className="h-12 skeleton rounded-lg" />)}
          </div>
        ) : cuentas.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-6">{t("facturacion.cuentas.sinCuentas")}</p>
        ) : (
          <div className="space-y-1.5">
            {cuentas.map((c) => (
              <div key={c.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/60">
                {editandoId === c.id ? (
                  <>
                    <input
                      autoFocus
                      type="text"
                      value={nombreEditado}
                      onChange={(e) => setNombreEditado(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleGuardarNombre(c.id)}
                      className="input text-sm flex-1 py-1"
                    />
                    <button
                      onClick={() => handleGuardarNombre(c.id)}
                      disabled={guardandoId === c.id || !nombreEditado.trim()}
                      className="text-emerald-600 hover:text-emerald-700 shrink-0 disabled:opacity-50"
                      title={t("facturacion.cuentas.guardar")}
                    >
                      {guardandoId === c.id ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
                    </button>
                    <button onClick={() => setEditandoId(null)} className="text-slate-400 hover:text-slate-600 shrink-0" title={t("common.close")}>
                      <X size={15} />
                    </button>
                  </>
                ) : (
                  <>
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 ${
                        c.activa
                          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                          : "bg-slate-100 text-slate-500 dark:bg-slate-500/10 dark:text-slate-400"
                      }`}
                    >
                      {c.activa ? t("facturacion.cuentas.activa") : t("facturacion.cuentas.inactiva")}
                    </span>
                    <span className="text-sm text-slate-700 dark:text-slate-300 flex-1 truncate">{c.nombre}</span>

                    {confirmandoId === c.id ? (
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">{t("facturacion.cuentas.confirmarDesactivar")}</span>
                        <button
                          onClick={() => handleToggleActiva(c)}
                          className="text-xs font-semibold text-red-600 hover:text-red-700 shrink-0"
                        >
                          {t("facturacion.cuentas.desactivar")}
                        </button>
                        <button onClick={() => setConfirmandoId(null)} className="text-slate-400 hover:text-slate-600 shrink-0">
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 shrink-0">
                        <button onClick={() => startEdit(c)} className="text-slate-400 hover:text-brand-600 dark:hover:text-brand-400" title={t("facturacion.cuentas.editar")}>
                          <Pencil size={14} />
                        </button>
                        {c.activa ? (
                          <button
                            onClick={() => setConfirmandoId(c.id)}
                            disabled={guardandoId === c.id}
                            className="text-slate-400 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-50"
                            title={t("facturacion.cuentas.desactivar")}
                          >
                            <Trash2 size={14} />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleToggleActiva(c)}
                            disabled={guardandoId === c.id}
                            className="text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 disabled:opacity-50"
                            title={t("facturacion.cuentas.reactivar")}
                          >
                            {guardandoId === c.id ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                          </button>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
