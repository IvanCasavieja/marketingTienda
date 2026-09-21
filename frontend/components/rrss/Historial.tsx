"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Trash2 } from "lucide-react";
import { rrssApi, type RrssValidacionResumen } from "@/lib/api";

interface Props {
  puedeBorrar: boolean;
  onAbrir: (id: number) => void;
  abriendoId: number | null;
}

export default function Historial({ puedeBorrar, onAbrir, abriendoId }: Props) {
  const { t, i18n } = useTranslation();
  const [filas, setFilas] = useState<RrssValidacionResumen[] | null>(null);
  const [error, setError] = useState(false);

  const cargar = useCallback(() => {
    rrssApi.listar().then(({ data }) => setFilas(data)).catch(() => setError(true));
  }, []);
  useEffect(cargar, [cargar]);

  async function borrar(f: RrssValidacionResumen) {
    if (!window.confirm(t("rrss.borrarConfirm", { nombre: f.nombre_mailing }))) return;
    try {
      await rrssApi.borrar(f.id);
      setFilas((prev) => prev?.filter((x) => x.id !== f.id) ?? null);
    } catch {
      setError(true);
    }
  }

  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{t("rrss.errorHistorial")}</p>;
  if (filas === null) return <p className="text-sm text-slate-500 flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> {t("common.loading")}</p>;
  if (filas.length === 0) return <div className="card p-10 text-center text-sm text-slate-500">{t("rrss.historialVacio")}</div>;

  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="text-xs text-slate-500 bg-slate-50 dark:bg-slate-800/50">
          <tr>
            <th className="text-left font-medium px-4 py-3">{t("rrss.hFecha")}</th>
            <th className="text-left font-medium px-4 py-3">{t("rrss.mailing")}</th>
            <th className="text-left font-medium px-4 py-3 hidden md:table-cell">{t("rrss.hUsuario")}</th>
            <th className="text-left font-medium px-4 py-3">{t("rrss.hResultado")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.id} className="border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40">
              <td className="px-4 py-3 whitespace-nowrap text-slate-600 dark:text-slate-300">
                {f.created_at ? new Date(f.created_at).toLocaleString(i18n.language, { dateStyle: "short", timeStyle: "short" }) : "—"}
              </td>
              <td className="px-4 py-3 max-w-[22rem] truncate" title={f.nombre_mailing}>{f.nombre_mailing}</td>
              <td className="px-4 py-3 hidden md:table-cell text-slate-500">{f.usuario ?? "—"}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1.5">
                  <span className="badge-slate">{t("rrss.nPlacas", { count: f.total })}</span>
                  {f.ok > 0 && <span className="badge-green">{f.ok} · {t("rrss.estado.ok")}</span>}
                  {f.con_diferencias > 0 && <span className="badge-red">{f.con_diferencias} · {t("rrss.conDiferencias")}</span>}
                  {f.sin_match > 0 && <span className="badge-blue">{f.sin_match} · {t("rrss.estado.sin_match")}</span>}
                  {f.error > 0 && <span className="badge-slate">{f.error} · {t("rrss.estado.error")}</span>}
                </div>
              </td>
              <td className="px-4 py-3 text-right whitespace-nowrap">
                <button onClick={() => onAbrir(f.id)} disabled={abriendoId !== null} className="btn-secondary text-xs mr-2">
                  {abriendoId === f.id ? <Loader2 size={13} className="animate-spin" /> : t("rrss.abrir")}
                </button>
                {puedeBorrar && (
                  <button onClick={() => borrar(f)} className="btn-ghost text-xs" title={t("rrss.borrar")}>
                    <Trash2 size={14} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
