"use client";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileSpreadsheet, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { rrssApi } from "@/lib/api";

/**
 * El motivo real de un error que vino con responseType: "blob": axios no parsea
 * la respuesta y err.response.data es un Blob, así que el .detail de siempre da
 * undefined. Mismo criterio que motivoDelError en ConvertidorDividirModal.
 */
async function motivoDelError(err: unknown): Promise<string | null> {
  const data = (err as { response?: { data?: unknown } } | null)?.response?.data;
  if (!data) return null;
  if (typeof (data as { detail?: unknown }).detail === "string") return (data as { detail: string }).detail;
  if (typeof Blob === "undefined" || !(data instanceof Blob)) return null;
  try {
    const json = JSON.parse(await data.text());
    return typeof json?.detail === "string" ? json.detail : null;
  } catch {
    return null; // un 502 del proxy devuelve HTML: no hay motivo que mostrar
  }
}

interface Props {
  validacionId: number;
  nombreMailing: string;
}

/** Baja el Excel de correcciones para el diseñador: solo las placas con algo para corregir. */
export default function DescargarExcel({ validacionId, nombreMailing }: Props) {
  const { t } = useTranslation();
  const [bajando, setBajando] = useState(false);
  const enlace = useRef<HTMLAnchorElement>(null);

  async function descargar() {
    setBajando(true);
    try {
      const { data } = await rrssApi.excel(validacionId);
      const url = URL.createObjectURL(
        new Blob([data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
      );
      // El nombre lo arma el navegador: entre dominios distintos (Vercel contra Render)
      // el content-disposition del backend no se puede leer.
      const base = nombreMailing.replace(/\.[a-z0-9]+$/i, "");
      if (enlace.current) {
        enlace.current.href = url;
        enlace.current.download = `Correcciones RRSS - ${base}.xlsx`;
        enlace.current.click();
      }
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error((await motivoDelError(e)) ?? t("rrss.errorExcel"));
    } finally {
      setBajando(false);
    }
  }

  return (
    <>
      <button onClick={descargar} disabled={bajando} className="btn-secondary text-xs flex items-center gap-1.5 disabled:opacity-60">
        {bajando ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} className="text-emerald-600" />}
        {bajando ? t("rrss.armandoExcel") : t("rrss.descargarExcel")}
      </button>
      <a ref={enlace} className="hidden" />
    </>
  );
}
