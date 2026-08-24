"use client";
import { useState, ChangeEvent, FormEvent } from "react";
import { FileSpreadsheet, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  convertidorApi,
  type ConvertidorColumna,
  type ConvertidorRow,
  type MaPair,
} from "@/lib/api";
import { FileDropField } from "@/components/cenefas/fields";
import ConvertidorGrid from "./ConvertidorGrid";
import ConvertidorMapeoStep from "./ConvertidorMapeoStep";

// Tres pasos: subir el archivo, mapear las columnas que cambian entre
// exports, y revisar/corregir la grilla antes de descargar o pasar a cenefa.
//
// El mapeo es un paso propio y no un panel lateral de la grilla porque
// cambia CÓMO se interpreta cada fila: elegirlo después de convertir
// obligaría a reconvertir todo, y verlo antes deja explícito qué columna
// alimenta cada variable.
type Paso = "subir" | "mapear" | "grilla";

export default function ConvertidorPanel() {
  const { t } = useTranslation();
  const [paso, setPaso] = useState<Paso>("subir");
  const [excel, setExcel] = useState<File | null>(null);
  const [columnas, setColumnas] = useState<ConvertidorColumna[]>([]);
  const [variablesMapeables, setVariablesMapeables] = useState<string[]>([]);
  const [totalFilas, setTotalFilas] = useState(0);
  const [rows, setRows] = useState<ConvertidorRow[] | null>(null);
  const [maPairs, setMaPairs] = useState<MaPair[]>([]);
  const [loading, setLoading] = useState(false);

  function reset() {
    setPaso("subir");
    setRows(null);
    setMaPairs([]);
    setExcel(null);
    setColumnas([]);
    setTotalFilas(0);
  }

  async function handleLeerColumnas(e: FormEvent) {
    e.preventDefault();
    if (!excel) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel);
      const { data } = await convertidorApi.columnas(fd);
      setColumnas(data.columnas);
      setVariablesMapeables(data.variables_mapeables);
      setTotalFilas(data.total_filas);
      setPaso("mapear");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setLoading(false);
    }
  }

  async function handleConvertir(
    mapeo: Record<string, string>,
    valores: Record<string, string>,
  ) {
    if (!excel) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel);
      fd.append("mapeo_json", JSON.stringify(mapeo));
      fd.append("valores_json", JSON.stringify(valores));
      const { data } = await convertidorApi.preview(fd);
      setRows(data.rows);
      setMaPairs(data.ma_pairs);
      setPaso("grilla");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setLoading(false);
    }
  }

  if (paso === "grilla" && rows) {
    return (
      <ConvertidorGrid
        rows={rows}
        setRows={setRows}
        maPairs={maPairs}
        onReset={reset}
      />
    );
  }

  if (paso === "mapear") {
    return (
      <ConvertidorMapeoStep
        columnas={columnas}
        variablesMapeables={variablesMapeables}
        totalFilas={totalFilas}
        onBack={() => setPaso("subir")}
        onConfirm={handleConvertir}
        converting={loading}
      />
    );
  }

  return (
    <div className="card p-6 space-y-4 max-w-xl mx-auto">
      <p className="text-sm text-slate-500 dark:text-slate-400">{t("convertidor.intro")}</p>
      <form onSubmit={handleLeerColumnas} className="space-y-4">
        <FileDropField
          label={t("convertidor.excelLabel")}
          hint=".xlsx / .csv"
          accept=".xlsx,.xlsm,.csv"
          file={excel}
          onChange={(e: ChangeEvent<HTMLInputElement>) => e.target.files?.[0] && setExcel(e.target.files[0])}
          icon={FileSpreadsheet}
          accentColor="brand"
          chooseLabel={t("cenefas.chooseFile")}
          readyLabel={t("cenefas.ready")}
          searchLabel={t("cenefas.search")}
        />
        <button
          type="submit"
          disabled={!excel || loading}
          className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <FileSpreadsheet size={16} />}
          {loading ? t("convertidor.processing") : t("convertidor.continuar")}
        </button>
      </form>
    </div>
  );
}
