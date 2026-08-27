"use client";
import { ChangeEvent, FormEvent, useCallback, useState } from "react";
import { FileSpreadsheet, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  convertidorApi,
  type ConvertidorHoja,
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

// Un archivo puede traer varias hojas y cada una es un listado aparte: el
// export crudo de gestión, el "Frente" curado a mano, el "Dorso". Traen
// columnas distintas (una tiene OFERTA/OFERTADET, otra tiene COMENTARIO), así
// que cada una lleva su propio mapeo y su propia grilla, y se descarga por
// separado. Antes se convertía siempre la primera hoja, sin avisar.
interface EstadoHoja {
  rows: ConvertidorRow[];
  maPairs: MaPair[];
}

interface Props {
  /** Se avisa cada vez que cambian las filas, para que Tinin pueda mirarlas. */
  onRowsChange?: (rows: ConvertidorRow[] | null) => void;
}

export default function ConvertidorPanel({ onRowsChange }: Props = {}) {
  const { t } = useTranslation();
  const [paso, setPaso] = useState<Paso>("subir");
  const [excel, setExcel] = useState<File | null>(null);
  const [hojas, setHojas] = useState<ConvertidorHoja[]>([]);
  const [hojaActual, setHojaActual] = useState(0);
  const [variablesMapeables, setVariablesMapeables] = useState<string[]>([]);
  // {variable: campo_de_entrada} -- esa variable no se pide a mano si el campo
  // ya vino reconocido en la hoja, porque el Convertidor la calcula solo.
  const [resueltaPorCampo, setResueltaPorCampo] = useState<Record<string, string>>({});
  // {campo: qué es} -- a qué campos se puede reasignar una columna.
  const [camposAsignables, setCamposAsignables] = useState<Record<string, string>>({});
  // Lo convertido de cada hoja, por índice. Cambiar de hoja no pierde lo que
  // ya se corrigió a mano en la otra.
  const [resultados, setResultados] = useState<Record<number, EstadoHoja>>({});
  const [loading, setLoading] = useState(false);
  // El último mapeo con el que se convirtió cada hoja. Se guarda para poder
  // REHACER la conversión sin volver a pasar por la pantalla de mapeo: hace
  // falta cuando Tinín aprende algo que cambia cómo se resuelven las filas
  // (una mecánica nueva), porque eso lo resuelve el backend y la grilla que
  // está en pantalla ya no lo refleja.
  const [ultimoMapeo, setUltimoMapeo] = useState<
    Record<number, {
      mapeo: Record<string, string>;
      valores: Record<string, string>;
      campos?: Record<string, string>;
    }>
  >({});

  const hoja = hojas.find((h) => h.indice === hojaActual) ?? null;
  const actual = resultados[hojaActual] ?? null;

  // Cada cambio de filas se replica hacia afuera: es lo que le da a Tinin la
  // grilla que la persona esta mirando. Sin esto solo puede tirar hipotesis.
  const setRows = useCallback(
    (valor: React.SetStateAction<ConvertidorRow[] | null>) => {
      setResultados((prev) => {
        const previo = prev[hojaActual];
        if (!previo) return prev;
        const siguiente = typeof valor === "function"
          ? (valor as (p: ConvertidorRow[] | null) => ConvertidorRow[] | null)(previo.rows)
          : valor;
        onRowsChange?.(siguiente);
        return { ...prev, [hojaActual]: { ...previo, rows: siguiente ?? [] } };
      });
    },
    [onRowsChange, hojaActual],
  );

  function reset() {
    setPaso("subir");
    setResultados({});
    onRowsChange?.(null);
    setExcel(null);
    setHojas([]);
    setHojaActual(0);
  }

  function irAHoja(indice: number) {
    setHojaActual(indice);
    const ya = resultados[indice];
    onRowsChange?.(ya ? ya.rows : null);
    setPaso(ya ? "grilla" : "mapear");
  }

  async function handleLeerColumnas(e: FormEvent) {
    e.preventDefault();
    if (!excel) return;
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel);
      const { data } = await convertidorApi.columnas(fd);
      setHojas(data.hojas);
      setHojaActual(data.hoja_sugerida);
      setVariablesMapeables(data.variables_mapeables);
      setResueltaPorCampo(data.resuelta_por_campo ?? {});
      setCamposAsignables(data.campos_asignables ?? {});
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
    // {nombre_de_columna: campo} -- pisa el campo de entrada de esa columna solo
    // en esta corrida. Hoy lo llena una sola cosa: aceptar el aviso de "la
    // columna OFERTA trae precios". No se aprende, a propósito.
    campos: Record<string, string> = {},
  ) {
    if (!excel) return;
    setUltimoMapeo((prev) => ({ ...prev, [hojaActual]: { mapeo, valores, campos } }));
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel);
      fd.append("mapeo_json", JSON.stringify(mapeo));
      fd.append("valores_json", JSON.stringify(valores));
      fd.append("campos_json", JSON.stringify(campos));
      fd.append("hoja", String(hojaActual));
      const { data } = await convertidorApi.preview(fd);
      setResultados((prev) => ({
        ...prev,
        [hojaActual]: { rows: data.rows, maPairs: data.ma_pairs },
      }));
      onRowsChange?.(data.rows);
      setPaso("grilla");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setLoading(false);
    }
  }

  // Rehace la conversión de la hoja actual con el mismo mapeo. Se usa cuando
  // Tinín aprende algo que cambia cómo el backend resuelve las filas.
  //
  // OJO: reconstruye la grilla, así que se pierden las correcciones hechas a
  // mano en ella. Es aceptable porque el aviso que dispara esto (una mecánica
  // que el motor no reconoce) aparece apenas se convierte, antes de que haya
  // trabajo manual encima -- y el texto del botón lo dice.
  function revalidar() {
    const guardado = ultimoMapeo[hojaActual];
    if (!guardado) return;
    handleConvertir(guardado.mapeo, guardado.valores, guardado.campos ?? {});
  }

  // Barra de hojas: solo aparece si el archivo trae más de una. Numeradas 1, 2,
  // 3 porque es como se las nombra al hablar de ellas; el nombre real de la
  // hoja va al lado, que es lo que las distingue de verdad.
  const barraHojas = hojas.length > 1 ? (
    <div className="card p-2 flex items-center gap-1.5 flex-wrap">
      <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest px-2">
        Hojas
      </span>
      {hojas.map((h, i) => {
        const activa = h.indice === hojaActual;
        const convertida = !!resultados[h.indice];
        const vacia = !h.error && h.total_filas === 0;
        return (
          <button
            key={h.indice}
            type="button"
            onClick={() => irAHoja(h.indice)}
            disabled={!!h.error}
            title={h.error ?? `${h.nombre} · ${h.total_filas} filas`}
            className={`px-2.5 py-1.5 rounded-lg text-xs border-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              activa
                ? "border-brand-400 bg-brand-50 dark:bg-brand-950/30 text-brand-700 dark:text-brand-300"
                : "border-transparent bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
            }`}
          >
            <span className="font-bold">{i + 1}</span>
            <span className="ml-1.5 max-w-[160px] truncate inline-block align-bottom">{h.nombre}</span>
            <span className={`ml-1.5 ${vacia ? "text-slate-400" : "text-slate-400"}`}>
              {h.error ? "·  —" : `· ${h.total_filas}`}
            </span>
            {convertida && <span className="ml-1 text-emerald-500">✓</span>}
          </button>
        );
      })}
    </div>
  ) : null;

  if (paso === "grilla" && actual) {
    return (
      <div className="space-y-3">
        {barraHojas}
        <ConvertidorGrid
          key={hojaActual}
          rows={actual.rows}
          setRows={setRows}
          maPairs={actual.maPairs}
          onReset={reset}
          onRevalidar={revalidar}
        />
      </div>
    );
  }

  if (paso === "mapear" && hoja) {
    return (
      <div className="space-y-3">
        {barraHojas}
        <ConvertidorMapeoStep
          key={hojaActual}
          columnas={hoja.columnas}
          variablesMapeables={variablesMapeables}
          camposReconocidos={hoja.campos_reconocidos ?? []}
          resueltaPorCampo={resueltaPorCampo}
          ofertaConPrecios={hoja.oferta_con_precios ?? null}
          camposAsignables={camposAsignables}
          totalFilas={hoja.total_filas}
          excel={excel}
          hoja={hoja.nombre}
          onBack={() => setPaso("subir")}
          onConfirm={handleConvertir}
          converting={loading}
        />
      </div>
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
