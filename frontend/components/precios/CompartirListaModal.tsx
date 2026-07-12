"use client";
import { useEffect, useState } from "react";
import { watchlistApi, type UsuarioCompartible } from "@/lib/api";
import { X, UserPlus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";

export default function CompartirListaModal({
  watchlistId,
  nombre,
  onClose,
}: {
  watchlistId: number;
  nombre: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [usuarios, setUsuarios] = useState<UsuarioCompartible[] | null>(null);
  const [compartidos, setCompartidos] = useState<UsuarioCompartible[] | null>(null);
  const [query, setQuery] = useState("");
  const [procesando, setProcesando] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([watchlistApi.usuariosCompartibles(), watchlistApi.listarCompartidos(watchlistId)])
      .then(([u, c]) => {
        setUsuarios(u.data);
        setCompartidos(c.data);
      })
      .catch(() => toast.error(t("precios.listas.compartir.loadError")));
  }, [watchlistId, t]);

  const compartidosIds = new Set((compartidos ?? []).map((u) => u.id));
  const disponibles = (usuarios ?? []).filter(
    (u) => !compartidosIds.has(u.id) && (u.full_name + u.email).toLowerCase().includes(query.trim().toLowerCase())
  );

  async function agregar(userId: number) {
    setProcesando(userId);
    try {
      await watchlistApi.compartir(watchlistId, userId);
      const usuario = usuarios?.find((u) => u.id === userId);
      if (usuario) setCompartidos((prev) => [...(prev ?? []), usuario]);
      toast.success(t("precios.listas.compartir.added"));
    } catch {
      toast.error(t("precios.listas.compartir.addError"));
    } finally {
      setProcesando(null);
    }
  }

  async function quitar(userId: number) {
    setProcesando(userId);
    try {
      await watchlistApi.dejarDeCompartir(watchlistId, userId);
      setCompartidos((prev) => prev?.filter((u) => u.id !== userId) ?? null);
    } catch {
      toast.error(t("precios.listas.compartir.removeError"));
    } finally {
      setProcesando(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-md max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{t("precios.listas.compartir.title")}</p>
            <p className="text-xs text-slate-400 truncate">{nombre}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {compartidos !== null && compartidos.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
                {t("precios.listas.compartir.currentlyShared")}
              </p>
              <div className="space-y-1.5">
                {compartidos.map((u) => (
                  <div key={u.id} className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-800/60">
                    <div className="w-6 h-6 rounded-full bg-brand-600/15 text-brand-600 dark:text-brand-400 flex items-center justify-center text-[11px] font-bold shrink-0">
                      {u.full_name.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{u.full_name}</p>
                      <p className="text-[10.5px] text-slate-400 truncate">{u.email}</p>
                    </div>
                    <button
                      onClick={() => quitar(u.id)}
                      disabled={procesando === u.id}
                      className="text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors shrink-0 disabled:opacity-40"
                      title={t("precios.listas.compartir.revoke")}
                    >
                      {procesando === u.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
              {t("precios.listas.compartir.addNew")}
            </p>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("precios.listas.compartir.searchPlaceholder")}
              className="input text-xs w-full mb-2"
            />
            {usuarios === null && (
              <div className="flex justify-center py-6">
                <Loader2 size={16} className="animate-spin text-slate-400" />
              </div>
            )}
            {usuarios !== null && disponibles.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-4">{t("precios.listas.compartir.noUsers")}</p>
            )}
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {disponibles.map((u) => (
                <button
                  key={u.id}
                  onClick={() => agregar(u.id)}
                  disabled={procesando === u.id}
                  className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-left disabled:opacity-40"
                >
                  <div className="w-6 h-6 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 flex items-center justify-center text-[11px] font-bold shrink-0">
                    {u.full_name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{u.full_name}</p>
                    <p className="text-[10.5px] text-slate-400 truncate">{u.email}</p>
                  </div>
                  {procesando === u.id ? (
                    <Loader2 size={14} className="animate-spin text-slate-400 shrink-0" />
                  ) : (
                    <UserPlus size={14} className="text-brand-500 shrink-0" />
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
