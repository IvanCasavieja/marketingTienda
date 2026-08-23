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

// Paso previo a convertir: decir a qué columna del Excel corresponde cada
// variable cuyo nombre cambia según el archivo de gestión que se suba.
//
// Las demás variables (codigo, descripcion, precioRegular, precioOferta,
// mecanica y los decimales) no aparecen acá porque el Convertidor las
// resuelve solo: salen de columnas fijas del export o las calcula.

const SIN_MAPEAR = "";

interface Props {
  columnas: ConvertidorColumna[];
  variablesMapeables: string[];
  totalFilas: number;
  /** Mundo al que se apunta, para filtrar y etiquetar las plantillas. */
  destino?: string | null;
  onBack: () => void;
  onConfirm: (mapeo: Record<string, string>) => void;
  converting: boolean;
}

export default function ConvertidorMapeoStep({
  columnas, variablesMapeables, totalFilas, destino, onBack, onConfirm, converting,
}: Props) {
  const { t } = useTranslation();
  const [mapeo, setMapeo] = useState<Record<string, string>>({});
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
    setMapeo(aplicado);
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
      const { data } = await convertidorApi.guardarMapeo({ nombre, destino: destino ?? null, mapeo });
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

  const asignadas = Object.values(mapeo).filter(Boolean).length;

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
            const valor = mapeo[variable] ?? SIN_MAPEAR;
            const col = columnas.find((c) => c.nombre === valor);
            return (
              <div key={variable} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-3 items-center">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 font-mono truncate">
                    {variable}
                  </p>
                  {def && (
                    <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{def.desc}</p>
                  )}
                </div>
                <div className="min-w-0">
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
                    <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 truncate">
                      {col.muestras.join(" · ")}
                    </p>
                  )}
                  {duplicadas.has(valor) && (
                    <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">
                      {t("convertidor.mapeo.columnaRepetida")}
                    </p>
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
          onClick={() => onConfirm(mapeo)}
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
