"use client";
import { useState } from "react";
import { Check, Loader2, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type SugerirMecanicaIAResponse } from "@/lib/api";

// Un OFERTADET que el motor no reconoce.
//
// El Convertidor deduce la familia de mecánica del texto de OFERTADET. Cuando
// gestión inventa un tipo nuevo la fila pierde la mecánica ENTERA -- sin
// cocarda, sin "Comprando N", sin unidad -- y lo único que queda es el aviso.
//
// Y vuelve todas las semanas, porque es el mismo listado: hoy se arregla a mano
// y el lunes siguiente está igual. Por eso lo que se confirma acá queda
// APRENDIDO: de ahí en adelante ese OFERTADET lo resuelve el código.
//
// Se pregunta por TIPO, no por fila: cuarenta filas con el mismo OFERTADET
// nuevo son una sola pregunta.
//
// Nada se aplica solo. Elegir mal la familia no deja el cartel vacío, lo deja
// MINTIENDO: un "2x1" resuelto como combo imprime un precio unitario que no
// existe, y eso sale impreso a la góndola.

interface Props {
  /** Las filas de la grilla, para agrupar por OFERTADET y ver qué dice OFERTA. */
  rows: { ofertaDet: string; ofertaOrigen: string }[];
  /** Para que la grilla vuelva a resolver las filas con lo recién aprendido. */
  onAprendido: () => void;
}

export default function TininMecanica({ rows, onAprendido }: Props) {
  const { t } = useTranslation();
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [datos, setDatos] = useState<SugerirMecanicaIAResponse | null>(null);
  const [elegido, setElegido] = useState<Record<string, string>>({});

  async function preguntar() {
    setCargando(true);
    try {
      const { data } = await convertidorApi.sugerirMecanicaIA(
        rows.map((r) => ({ ofertaDet: r.ofertaDet, oferta: r.ofertaOrigen }))
      );
      setDatos(data);
      setElegido(Object.fromEntries(data.sugerencias.map((s) => [s.ofertadet_norm, s.familia])));
      if (data.errores.length) toast.error(data.errores[0]);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setCargando(false);
    }
  }

  async function confirmar() {
    const mecanicas = (datos?.sugerencias ?? [])
      .filter((s) => elegido[s.ofertadet_norm])
      .map((s) => ({
        ofertadet_norm: s.ofertadet_norm,
        ofertadet_display: s.ofertadet_display,
        familia: elegido[s.ofertadet_norm],
      }));
    if (mecanicas.length === 0) return;
    setGuardando(true);
    try {
      await convertidorApi.confirmarAliasMecanica(mecanicas);
      toast.success(t("convertidor.mecanicaIA.guardado", { count: mecanicas.length }));
      setDatos(null);
      // Lo aprendido no se aplica a la grilla que ya está en pantalla: hay que
      // volver a resolverla contra el backend, que es el que sabe leerlo.
      onAprendido();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setGuardando(false);
    }
  }

  const familias = datos?.familias ?? {};

  return (
    <div className="rounded-lg border border-violet-200 dark:border-violet-900/60 bg-violet-50/60 dark:bg-violet-950/20 p-3 space-y-2.5">
      {!datos && (
        <button type="button" onClick={preguntar} disabled={cargando}
          className="btn-secondary h-8 px-3 text-xs inline-flex items-center gap-1.5">
          {cargando
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />{t("convertidor.mecanicaIA.mirando")}</>
            : <><Sparkles className="w-3.5 h-3.5" />{t("convertidor.mecanicaIA.boton")}</>}
        </button>
      )}

      {datos && datos.ya_aprendidas.length > 0 && (
        <p className="text-xs text-violet-800/70 dark:text-violet-300/60">
          {t("convertidor.mecanicaIA.yaAprendidas", { count: datos.ya_aprendidas.length })}{" "}
          {datos.ya_aprendidas.map((a) => `${a.ofertadet_display} → ${a.familia}`).join(" · ")}
        </p>
      )}

      {datos && datos.sugerencias.length > 0 && (
        <>
          <ul className="space-y-1.5">
            {datos.sugerencias.map((s) => (
              <li key={s.ofertadet_norm}
                className="rounded-md bg-white dark:bg-slate-900 px-2.5 py-2 text-xs space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-800 dark:text-slate-100 flex-1 min-w-0 truncate">
                    {s.ofertadet_display}
                  </span>
                  <select
                    value={elegido[s.ofertadet_norm] ?? s.familia}
                    onChange={(e) =>
                      setElegido((prev) => ({ ...prev, [s.ofertadet_norm]: e.target.value }))}
                    className="input h-7 text-xs py-0 w-40 shrink-0"
                  >
                    {Object.keys(familias).map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </div>
                {s.motivo && <p className="text-slate-500 dark:text-slate-400">{s.motivo}</p>}
                {/* Qué significa la familia elegida, para poder decidir sin
                    saberse los nombres internos de memoria. */}
                <p className="text-slate-400 dark:text-slate-500">
                  {familias[elegido[s.ofertadet_norm] ?? s.familia]}
                </p>
              </li>
            ))}
          </ul>
          <button type="button" onClick={confirmar} disabled={guardando}
            className="btn-primary h-8 px-3 text-xs inline-flex items-center gap-1.5">
            {guardando
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Check className="w-3.5 h-3.5" />}
            {t("convertidor.mecanicaIA.confirmar", { count: datos.sugerencias.length })}
          </button>
        </>
      )}

      {datos && datos.sugerencias.length === 0 && (
        <p className="text-xs text-violet-800/70 dark:text-violet-300/60">
          {t("convertidor.mecanicaIA.nadaQueProponer")}
        </p>
      )}
    </div>
  );
}
