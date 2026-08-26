"use client";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Loader2, Save, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  convertidorApi,
  type ConvertidorColumna,
  type ConvertidorMapeo,
} from "@/lib/api";
import { varDef } from "@/lib/cenefaVariables";
import TininMapeo from "./TininMapeo";

// Paso previo a convertir: resolver las variables EXTRA, las que el
// Convertidor no puede deducir solo. Ninguna es obligatoria.
//
// Cada una se resuelve de una de dos formas, a elección:
//
//   Columna  -> se lee de una columna del Excel, fila por fila.
//   Escribir -> el mismo texto para todas las filas.
//
// La segunda hace falta porque el export de gestión no trae nunca vigencia
// ni legales: esos textos los escribe una persona, no salen de ninguna
// columna. Por eso esas dos arrancan en modo "Escribir".
//
// Las demás variables (codigo, descripcion, precioRegular, precioOferta,
// mecanica y los decimales) no aparecen acá porque el Convertidor las
// resuelve solo: salen de columnas fijas del export o las calcula.

const SIN_MAPEAR = "";

type Modo = "columna" | "texto";

// Variables que no vienen nunca en el export de gestión: arrancan listas para
// escribir, en vez de obligar a buscar una columna que no existe.
//
// precioBanco queda afuera a propósito: es un precio y lo normal es que salga
// de una columna, no que alguien escriba el mismo importe para todas las
// filas.
const ARRANCAN_EN_TEXTO = new Set([
  "vigencia", "legales", "banco", "dia", "mes", "año",
]);

interface Props {
  columnas: ConvertidorColumna[];
  variablesMapeables: string[];
  totalFilas: number;
  /**
   * El archivo subido y la hoja que se está mapeando. Van juntos porque el
   * panel de Tinín vuelve a leer el Excel para mirar las columnas que el
   * Convertidor NO reconoció -- que son justo las que no aparecen en esta
   * pantalla, porque acá se mapea al revés (variable -> columna).
   */
  excel?: File | null;
  hoja?: string;
  /** Mundo al que se apunta, para filtrar y etiquetar las plantillas. */
  destino?: string | null;
  onBack: () => void;
  onConfirm: (mapeo: Record<string, string>, valores: Record<string, string>) => void;
  converting: boolean;
}

export default function ConvertidorMapeoStep({
  columnas, variablesMapeables, totalFilas, destino, excel, hoja, onBack, onConfirm, converting,
}: Props) {
  const { t } = useTranslation();
  const [mapeo, setMapeo] = useState<Record<string, string>>({});
  const [valores, setValores] = useState<Record<string, string>>({});
  const [modos, setModos] = useState<Record<string, Modo>>(() =>
    Object.fromEntries(
      variablesMapeables.map((v) => [v, ARRANCAN_EN_TEXTO.has(v) ? "texto" : "columna"]),
    ),
  );
  const [plantillas, setPlantillas] = useState<ConvertidorMapeo[]>([]);
  const [plantillaId, setPlantillaId] = useState("");
  const [nombreNuevo, setNombreNuevo] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    convertidorApi.listarMapeos(destino ?? undefined)
      .then(({ data }) => setPlantillas(data))
      .catch(() => toast.error(t("convertidor.mapeo.errorPlantillas")));
  }, [destino, t]);

  // Si el archivo no trae la columna que la plantilla nombra, ese campo queda
  // vacío en vez de aplicarse a ciegas: mejor que la persona lo vea faltar.
  function aplicarPlantilla(id: string) {
    setPlantillaId(id);
    if (!id) {
      setMapeo({});
      setValores({});
      return;
    }
    const p = plantillas.find((x) => x.id === id);
    if (!p) return;
    const disponibles = new Set(columnas.map((c) => c.nombre));
    const aplicado: Record<string, string> = {};
    const faltantes: string[] = [];
    for (const [variable, col] of Object.entries(p.mapeo)) {
      if (disponibles.has(col)) aplicado[variable] = col;
      else faltantes.push(col);
    }
    const fijos = p.valores ?? {};
    setMapeo(aplicado);
    setValores(fijos);
    // El modo de cada variable sale de la plantilla: si trae texto fijo va a
    // "Escribir", si trae columna va a "Columna", y si no trae nada queda
    // como estaba.
    setModos((prev) => {
      const next = { ...prev };
      for (const v of variablesMapeables) {
        if (fijos[v]) next[v] = "texto";
        else if (aplicado[v]) next[v] = "columna";
      }
      return next;
    });
    setNombreNuevo(p.nombre);
    if (faltantes.length) {
      toast.warning(t("convertidor.mapeo.columnasFaltantes", { columnas: faltantes.join(", ") }));
    }
  }

  async function guardarPlantilla() {
    const nombre = nombreNuevo.trim();
    if (!nombre) return;
    setGuardando(true);
    try {
      const { data } = await convertidorApi.guardarMapeo({ nombre, destino: destino ?? null, mapeo, valores });
      setPlantillas((prev) => {
        const resto = prev.filter((p) => p.id !== data.id);
        return [...resto, data].sort((a, b) => a.nombre.localeCompare(b.nombre));
      });
      setPlantillaId(data.id);
      toast.success(t("convertidor.mapeo.plantillaGuardada"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setGuardando(false);
    }
  }

  async function borrarPlantilla() {
    const p = plantillas.find((x) => x.id === plantillaId);
    if (!p || !confirm(t("convertidor.mapeo.borrarConfirm", { nombre: p.nombre }))) return;
    try {
      await convertidorApi.borrarMapeo(p.id);
      setPlantillas((prev) => prev.filter((x) => x.id !== p.id));
      setPlantillaId("");
      toast.success(t("convertidor.mapeo.plantillaBorrada"));
    } catch {
      toast.error(t("convertidor.unknownError"));
    }
  }

  // Una misma columna asignada a dos variables casi siempre es un descuido.
  const duplicadas = useMemo(() => {
    const cuenta = new Map<string, number>();
    Object.values(mapeo).forEach((c) => c && cuenta.set(c, (cuenta.get(c) ?? 0) + 1));
    return new Set([...cuenta.entries()].filter(([, n]) => n > 1).map(([c]) => c));
  }, [mapeo]);

  // Solo viaja lo del modo activo de cada variable: si alguien mapeó una
  // columna y después pasó a "Escribir", esa columna ya no cuenta.
  const mapeoEfectivo = useMemo(
    () => Object.fromEntries(
      variablesMapeables
        .filter((v) => (modos[v] ?? "columna") === "columna" && mapeo[v])
        .map((v) => [v, mapeo[v]]),
    ),
    [variablesMapeables, modos, mapeo],
  );
  const valoresEfectivos = useMemo(
    () => Object.fromEntries(
      variablesMapeables
        .filter((v) => modos[v] === "texto" && valores[v]?.trim())
        .map((v) => [v, valores[v].trim()]),
    ),
    [variablesMapeables, modos, valores],
  );

  // Cuenta las resueltas de las dos formas: una variable con texto escrito
  // está tan resuelta como una con columna asignada.
  const asignadas = variablesMapeables.filter(
    (v) => (modos[v] === "texto" ? valores[v] : mapeo[v])?.trim(),
  ).length;

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <div className="card p-5 space-y-1">
        <h2 className="text-base font-bold text-slate-800 dark:text-slate-100">
          {t("convertidor.mapeo.titulo")}
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {t("convertidor.mapeo.subtitulo", { filas: totalFilas, columnas: columnas.length })}
        </p>
      </div>

      {/* Las columnas que el Convertidor NO reconoce no aparecen en esta
          pantalla -- acá se mapea variable -> columna, y esas quedan afuera de
          las dos puntas. Antes se ignoraban en silencio; ahora Tinín las
          levanta acá, que es el único momento del flujo en que alguien está
          mirando las columnas del archivo. */}
      {excel && <TininMapeo excel={excel} hoja={hoja} />}

      {/* Plantillas guardadas */}
      <div className="card p-5 space-y-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
          {t("convertidor.mapeo.plantillas")}
        </p>
        <div className="flex gap-2 items-center flex-wrap">
          <select
            className="input text-sm flex-1 min-w-[220px]"
            value={plantillaId}
            onChange={(e) => aplicarPlantilla(e.target.value)}
          >
            <option value="">{t("convertidor.mapeo.sinPlantilla")}</option>
            {plantillas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}{p.destino ? "" : ` · ${t("convertidor.mapeo.paraTodos")}`}
              </option>
            ))}
          </select>
          {plantillaId && (
            <button
              type="button"
              onClick={borrarPlantilla}
              className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
              title={t("convertidor.mapeo.borrar")}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
        <div className="flex gap-2 items-center">
          <input
            className="input text-sm flex-1"
            placeholder={t("convertidor.mapeo.nombrePlantillaPlaceholder")}
            value={nombreNuevo}
            onChange={(e) => setNombreNuevo(e.target.value)}
            maxLength={120}
          />
          <button
            type="button"
            onClick={guardarPlantilla}
            disabled={!nombreNuevo.trim() || asignadas === 0 || guardando}
            className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 disabled:opacity-40 shrink-0"
          >
            {guardando ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {t("convertidor.mapeo.guardarPlantilla")}
          </button>
        </div>
      </div>

      {/* Mapeo variable -> columna */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            {t("convertidor.mapeo.variables")}
          </p>
          <span className="text-xs text-slate-400">
            {t("convertidor.mapeo.asignadas", { n: asignadas, total: variablesMapeables.length })}
          </span>
        </div>

        <div className="space-y-2">
          {variablesMapeables.map((variable) => {
            const def = varDef(variable);
            const modo = modos[variable] ?? "columna";
            const valor = mapeo[variable] ?? SIN_MAPEAR;
            const texto = valores[variable] ?? "";
            const col = columnas.find((c) => c.nombre === valor);
            return (
              <div key={variable} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-3 items-start">
                <div className="min-w-0 pt-1.5">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 font-mono truncate">
                    {variable}
                  </p>
                  {def && (
                    <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{def.desc}</p>
                  )}
                </div>
                <div className="min-w-0 space-y-1.5">
                  {/* Columna del Excel, o un texto igual para todas las filas */}
                  <div className="flex gap-1 p-0.5 rounded-lg bg-slate-100 dark:bg-slate-800/60 w-fit">
                    {(["columna", "texto"] as Modo[]).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setModos((prev) => ({ ...prev, [variable]: m }))}
                        className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                          modo === m
                            ? "bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-100 shadow-sm"
                            : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                        }`}
                      >
                        {t(m === "columna" ? "convertidor.mapeo.modoColumna" : "convertidor.mapeo.modoTexto")}
                      </button>
                    ))}
                  </div>

                  {modo === "columna" ? (
                    <>
                      <select
                        className={`input text-sm w-full ${duplicadas.has(valor) ? "border-amber-400" : ""}`}
                        value={valor}
                        onChange={(e) =>
                          setMapeo((prev) => {
                            const next = { ...prev };
                            if (e.target.value) next[variable] = e.target.value;
                            else delete next[variable];
                            return next;
                          })
                        }
                      >
                        <option value="">{t("convertidor.mapeo.sinAsignar")}</option>
                        {columnas.map((c) => (
                          <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
                        ))}
                      </select>
                      {col && col.muestras.length > 0 && (
                        <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">
                          {col.muestras.join(" · ")}
                        </p>
                      )}
                      {duplicadas.has(valor) && (
                        <p className="text-[11px] text-amber-600 dark:text-amber-400">
                          {t("convertidor.mapeo.columnaRepetida")}
                        </p>
                      )}
                    </>
                  ) : (
                    <input
                      className="input text-sm w-full"
                      value={texto}
                      placeholder={t("convertidor.mapeo.textoPlaceholder", { n: totalFilas })}
                      onChange={(e) =>
                        setValores((prev) => {
                          const next = { ...prev };
                          if (e.target.value) next[variable] = e.target.value;
                          else delete next[variable];
                          return next;
                        })
                      }
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-xs text-slate-400 dark:text-slate-500 pt-1">
          {t("convertidor.mapeo.opcional")}
        </p>
      </div>

      <div className="flex justify-between gap-3">
        <button onClick={onBack} className="btn-secondary flex items-center gap-2">
          <ArrowLeft size={15} /> {t("convertidor.mapeo.volver")}
        </button>
        <button
          onClick={() => onConfirm(mapeoEfectivo, valoresEfectivos)}
          disabled={converting}
          className="btn-primary flex items-center gap-2 disabled:opacity-50"
        >
          {converting ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
          {converting ? t("convertidor.processing") : t("convertidor.mapeo.convertir")}
        </button>
      </div>
    </div>
  );
}
