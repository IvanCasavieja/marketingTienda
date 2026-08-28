"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { convertidorApi, type SugerenciaColumna, type SugerirColumnasIAResponse } from "@/lib/api";

// Las columnas del archivo que el Convertidor NO reconoce.
//
// Hasta ahora se ignoraban en silencio: si el export de gestión traía
// "NOMBRE DE ARTICULO" y el código esperaba otro nombre, esa columna
// simplemente no existía para el resto del proceso, y nadie se enteraba hasta
// ver la cenefa sin ese dato.
//
// Acá Tinín las mira y dice qué cree que es cada una. No aplica nada solo:
// propone, la persona confirma o corrige, y recién ahí se guarda. Lo que se
// confirma queda APRENDIDO para siempre -- de ahí en adelante esa columna la
// resuelve el código, sin gastar una llamada a IA nunca más.
//
// Por eso conviene contestar hasta las que están mal: un "no es ninguno"
// también se guarda, y es lo que hace que la próxima vez la lista sea corta.

interface Props {
  /** El archivo que se está mapeando. */
  excel: File;
  /** La hoja, para no analizar otra en un archivo de varias. */
  hoja?: string;
}

const NINGUNO = "__ninguno__";

export default function TininMapeo({ excel, hoja }: Props) {
  const { t } = useTranslation();
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [datos, setDatos] = useState<SugerirColumnasIAResponse | null>(null);
  // Lo que va a quedar guardado: arranca en lo que propuso Tinín y la persona
  // lo corrige. La clave es el header, así una corrección pisa la propuesta.
  const [elegido, setElegido] = useState<Record<string, string>>({});
  const [descartados, setDescartados] = useState<Set<string>>(new Set());
  // Se acaba de confirmar algo: el panel se queda un momento mostrando el
  // resultado en vez de desaparecer bajo los pies del que apretó el botón.
  const [recienConfirmado, setRecienConfirmado] = useState(false);
  const pedidoRef = useRef(false);

  // Automático (2026-08-29, pedido de Ivan): Tinín mira las columnas solo,
  // al entrar al mapeo, en vez de esperar a que alguien aprete un botón.
  // Si no hay nada que preguntar, el panel directamente no aparece.
  useEffect(() => {
    if (pedidoRef.current) return;
    pedidoRef.current = true;
    preguntar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function preguntar() {
    setCargando(true);
    try {
      const { data } = await convertidorApi.sugerirColumnasIA(excel, hoja);
      setDatos(data);
      setElegido(Object.fromEntries(
        data.sugerencias.map((s: SugerenciaColumna) => [s.header_norm, s.campo ?? NINGUNO])
      ));
      setDescartados(new Set());
      if (data.errores.length) toast.error(data.errores[0]);
      // Sin toast cuando no hay nada que preguntar: corriendo automático en
      // cada carga, "todo reconocido" es el caso normal y no es noticia.
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setCargando(false);
    }
  }

  async function confirmar() {
    const aliases = Object.entries(elegido)
      .filter(([header]) => !descartados.has(header))
      .map(([header_norm, campo]) => ({
        header_norm,
        campo: campo === NINGUNO ? null : campo,
      }));
    if (aliases.length === 0) return;
    setGuardando(true);
    try {
      await convertidorApi.confirmarAliasColumnas(aliases);
      setRecienConfirmado(true);
      toast.success(t("convertidor.mapeoIA.guardado", { count: aliases.length }));
      // Lo confirmado ya no se pregunta más: se saca de la lista en vez de
      // dejarlo con un tilde, para que quede claro qué falta contestar.
      setDatos((prev) => prev && {
        ...prev,
        sugerencias: prev.sugerencias.filter((s) => descartados.has(s.header_norm)),
      });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setGuardando(false);
    }
  }

  const pendientes = (datos?.sugerencias ?? []).filter((s) => !descartados.has(s.header_norm));

  // Todo reconocido y nada recién confirmado: el panel no tiene nada que
  // decir, así que no aparece. Antes había un botón y un aviso permanente;
  // desde 2026-08-29 esto corre solo y solo habla cuando hay una pregunta.
  if (!cargando && datos && pendientes.length === 0 && !recienConfirmado) {
    return null;
  }

  return (
    <div className="rounded-lg border border-violet-200 dark:border-violet-900/60 bg-violet-50/60 dark:bg-violet-950/20 p-3 space-y-3">
      <div className="flex items-start gap-2">
        <Sparkles className="w-4 h-4 mt-0.5 shrink-0 text-violet-600 dark:text-violet-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-violet-900 dark:text-violet-200">
            {t("convertidor.mapeoIA.titulo")}
          </p>
          <p className="text-xs text-violet-800/80 dark:text-violet-300/70">
            {t("convertidor.mapeoIA.detalle")}
          </p>
        </div>
        {cargando && (
          <span className="shrink-0 inline-flex items-center gap-1.5 text-xs text-violet-700 dark:text-violet-300">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />{t("convertidor.mapeoIA.mirando")}
          </span>
        )}
      </div>

      {datos && datos.ya_aprendidas.length > 0 && (
        <p className="text-xs text-violet-800/70 dark:text-violet-300/60">
          {t("convertidor.mapeoIA.yaAprendidas", { count: datos.ya_aprendidas.length })}{" "}
          {datos.ya_aprendidas.map((a) => `${a.header_display} → ${a.campo}`).join(" · ")}
        </p>
      )}

      {pendientes.length > 0 && (
        <>
          <ul className="space-y-1.5">
            {pendientes.map((s) => (
              <li key={s.header_norm}
                className="flex flex-wrap items-center gap-2 rounded-md bg-white dark:bg-slate-900 px-2.5 py-2 text-xs">
                <div className="min-w-0 flex-1">
                  <span className="font-semibold text-slate-800 dark:text-slate-100">
                    {s.header_display}
                  </span>
                  {(s.muestras?.length ?? 0) > 0 && (
                    <span className="ml-2 text-slate-400 dark:text-slate-500 truncate">
                      {s.muestras.slice(0, 3).join(" · ")}
                    </span>
                  )}
                  {s.motivo && (
                    <p className="text-slate-500 dark:text-slate-400">{s.motivo}</p>
                  )}
                </div>
                <select
                  value={elegido[s.header_norm] ?? NINGUNO}
                  onChange={(e) =>
                    setElegido((prev) => ({ ...prev, [s.header_norm]: e.target.value }))}
                  className="input h-7 text-xs py-0 w-44 shrink-0"
                >
                  <option value={NINGUNO}>{t("convertidor.mapeoIA.ninguno")}</option>
                  {/* Tolerante a las dos formas: el backend manda la lista,
                      pero una version vieja mandaba el dict {campo: desc} y
                      .map sobre un objeto volteaba la pantalla entera. */}
                  {(Array.isArray(datos?.campos) ? datos.campos : Object.keys(datos?.campos ?? {})).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                <button
                  type="button"
                  title={t("convertidor.mapeoIA.despues")}
                  onClick={() => setDescartados((prev) => new Set(prev).add(s.header_norm))}
                  className="h-7 w-7 grid place-items-center rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <button type="button" onClick={confirmar} disabled={guardando}
            className="btn-primary h-8 px-3 text-xs inline-flex items-center gap-1.5">
            {guardando
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Check className="w-3.5 h-3.5" />}
            {t("convertidor.mapeoIA.confirmar", { count: pendientes.length })}
          </button>
        </>
      )}

      {datos && pendientes.length === 0 && (
        <p className="text-xs text-violet-800/70 dark:text-violet-300/60">
          {t("convertidor.mapeoIA.nadaPendiente")}
        </p>
      )}
    </div>
  );
}
