"use client";
import { useState } from "react";
import {
  FileSpreadsheet, Image as ImageIcon, Loader2, Plus, Send, Trash2, X,
} from "lucide-react";
import { cenefasV2Api, toolsApi } from "@/lib/api";
import type { CenefaTemplateRecord } from "@/types/cenefas";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import LotePreviewStep from "@/components/cenefas/LotePreviewStep";
import TemplatePickerModal, { typeLabel } from "@/components/cenefas/rompeprecios/TemplatePickerModal";
import { ComboField } from "@/components/cenefas/fields";

// Panel único de generación, para TODOS los destinos.
//
// Hasta 08/2026 había dos (Redexpres y el resto), con dos sistemas de
// plantillas y dos motores. Ahora hay uno solo, y el destino es apenas la
// etiqueta que separa las plantillas de cada mundo.
//
// Se cargan varios Excel y a cada uno se le eligen SUS plantillas: no es
// "todos contra todos". Cada par (Excel, plantilla) es una cenefa.

const COCARDA_VAR = "imagen";
const MAX_PLANTILLAS = 5;

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/** Un Excel cargado con las plantillas que le tocan. */
interface Entrada {
  archivo: File;
  plantillas: CenefaTemplateRecord[];
}

interface CenefaPanelProps {
  category: string;
  categoryLabel: string;
  /** Excel ya convertido que llega desde el Convertidor. */
  excelInicial?: File | null;
}

export default function CenefaPanel({ category, categoryLabel, excelInicial }: CenefaPanelProps) {
  const { t } = useTranslation();

  const [entradas, setEntradas] = useState<Entrada[]>(
    excelInicial ? [{ archivo: excelInicial, plantillas: [] }] : [],
  );
  const [pickerPara, setPickerPara] = useState<number | null>(null);
  const [vigencia, setVigencia] = useState("");
  const [usarLegales, setUsarLegales] = useState(false);
  const [legales, setLegales] = useState("");
  const [cocarda, setCocarda] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [loteId, setLoteId] = useState<string | null>(null);

  function agregarExcels(files: FileList | null) {
    if (!files?.length) return;
    // El nombre del archivo es la clave con la que el backend empareja cada
    // Excel con sus plantillas, así que no puede haber dos iguales.
    const nuevos = Array.from(files).filter(
      (f) => !entradas.some((e) => e.archivo.name === f.name),
    );
    if (nuevos.length < files.length) toast.warning(t("cenefas.lote.excelRepetido"));
    setEntradas((prev) => [...prev, ...nuevos.map((archivo) => ({ archivo, plantillas: [] }))]);
  }

  function quitarExcel(i: number) {
    setEntradas((prev) => prev.filter((_, idx) => idx !== i));
  }

  function agregarPlantilla(i: number, tmpl: CenefaTemplateRecord) {
    setEntradas((prev) => prev.map((e, idx) => {
      if (idx !== i) return e;
      if (e.plantillas.some((p) => p.id === tmpl.id)) return e;
      if (e.plantillas.length >= MAX_PLANTILLAS) {
        toast.warning(t("cenefas.lote.maxPlantillas", { n: MAX_PLANTILLAS }));
        return e;
      }
      return { ...e, plantillas: [...e.plantillas, tmpl] };
    }));
  }

  function agregarPlantillas(i: number, tmpls: CenefaTemplateRecord[]) {
    setEntradas((prev) => prev.map((e, idx) => {
      if (idx !== i) return e;
      const nuevas = tmpls.filter((tm) => !e.plantillas.some((p) => p.id === tm.id));
      const hueco = MAX_PLANTILLAS - e.plantillas.length;
      if (nuevas.length > hueco) toast.warning(t("cenefas.lote.maxPlantillas", { n: MAX_PLANTILLAS }));
      return { ...e, plantillas: [...e.plantillas, ...nuevas.slice(0, hueco)] };
    }));
  }

  function quitarPlantilla(i: number, id: string) {
    setEntradas((prev) => prev.map((e, idx) =>
      idx === i ? { ...e, plantillas: e.plantillas.filter((p) => p.id !== id) } : e,
    ));
  }

  async function handleDownloadTemplate() {
    try {
      const { data } = await toolsApi.downloadExcelTemplate(category);
      const url = URL.createObjectURL(new Blob([data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `plantilla_${category}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error(t("cenefas.unknownError"));
    }
  }

  const emparejadas = entradas.filter((e) => e.plantillas.length > 0);
  const totalCenefas = emparejadas.reduce((n, e) => n + e.plantillas.length, 0);
  const puedeGenerar = totalCenefas > 0 && !enviando;

  async function handleGenerar() {
    if (!puedeGenerar) return;
    setEnviando(true);
    try {
      const fd = new FormData();
      for (const e of emparejadas) fd.append("excels", e.archivo);
      fd.append("pares_json", JSON.stringify(
        emparejadas.map((e) => ({
          excel: e.archivo.name,
          templates: e.plantillas.map((p) => p.id),
        })),
      ));
      fd.append("vigencia", vigencia.trim());
      fd.append("usar_legales", String(usarLegales));
      fd.append("legales", usarLegales ? legales.trim() : "");

      if (cocarda) {
        const ext = cocarda.name.split(".").pop()?.toLowerCase() ?? "png";
        const b64 = await fileToBase64(cocarda);
        fd.append("image_overrides_json", JSON.stringify({ [COCARDA_VAR]: `${ext}:${b64}` }));
      }

      const { data } = await cenefasV2Api.createLote(fd);
      setLoteId(data.lote_id);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setEnviando(false);
    }
  }

  if (loteId) {
    return <LotePreviewStep loteId={loteId} onBack={() => setLoteId(null)} />;
  }

  return (
    <div className="grid grid-cols-2 gap-6 items-start">
      {/* Izquierda: cada Excel con sus plantillas */}
      <div className="flex flex-col gap-5">
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
              {t("cenefas.filesSection")}
            </p>
            <button
              type="button"
              onClick={handleDownloadTemplate}
              className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 hover:text-emerald-700"
            >
              <FileSpreadsheet size={13} /> {t("cenefas.downloadTemplate")}
            </button>
          </div>

          <label className="flex items-center justify-center gap-2 w-full p-4 rounded-xl border-2 border-dashed border-slate-300 dark:border-slate-700 text-sm font-semibold text-slate-500 dark:text-slate-400 hover:border-brand-400 hover:text-brand-600 cursor-pointer transition-all">
            <Plus size={16} /> {t("cenefas.lote.agregarExcel")}
            <input
              type="file"
              accept=".xlsx,.xlsm"
              multiple
              className="hidden"
              onChange={(e) => { agregarExcels(e.target.files); e.target.value = ""; }}
            />
          </label>

          {entradas.length === 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500 text-center py-2">
              {t("cenefas.lote.sinExcel")}
            </p>
          )}

          {entradas.map((e, i) => (
            <div key={e.archivo.name} className="rounded-xl border border-slate-200 dark:border-slate-700 p-3 space-y-2.5">
              <div className="flex items-center gap-2">
                <FileSpreadsheet size={15} className="text-emerald-500 shrink-0" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate flex-1">
                  {e.archivo.name}
                </span>
                <button
                  type="button"
                  onClick={() => quitarExcel(i)}
                  className="shrink-0 p-1 text-slate-300 hover:text-rose-500"
                  title={t("cenefas.lote.quitarExcel")}
                >
                  <Trash2 size={13} />
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {e.plantillas.map((p) => (
                  <span
                    key={p.id}
                    className="flex items-center gap-1 pl-2 pr-1 py-1 rounded-lg bg-brand-50 dark:bg-brand-950/30 border border-brand-200 dark:border-brand-800 text-xs text-brand-700 dark:text-brand-300"
                  >
                    <span className="truncate max-w-[160px]">{p.name}</span>
                    <span className="text-[10px] text-brand-400">
                      {p.formats?.length ? typeLabel(p.formats[0]) : ""}
                    </span>
                    <button
                      type="button"
                      onClick={() => quitarPlantilla(i, p.id)}
                      className="p-0.5 text-brand-400 hover:text-rose-500"
                    >
                      <X size={11} />
                    </button>
                  </span>
                ))}
                <button
                  type="button"
                  onClick={() => setPickerPara(i)}
                  disabled={e.plantillas.length >= MAX_PLANTILLAS}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg border border-dashed border-slate-300 dark:border-slate-600 text-xs text-slate-500 hover:border-brand-400 hover:text-brand-600 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus size={11} />
                  {e.plantillas.length === 0
                    ? t("cenefas.lote.elegirPlantillas")
                    : t("cenefas.lote.otraPlantilla")}
                </button>
              </div>

              {e.plantillas.length >= MAX_PLANTILLAS && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">
                  {t("cenefas.lote.maxPlantillas", { n: MAX_PLANTILLAS })}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Derecha: configuración + generar */}
      <div className="flex flex-col gap-5">
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            {t("cenefas.configSection")}
          </p>

          <ComboField
            label={t("cenefas.vigencia")}
            value={vigencia}
            onChange={setVigencia}
            storageKey={`cenefas.vigencia.${category}`}
          />

          {/* Legales apagados por defecto: muchas plantillas ya los traen
              impresos en el diseño y sustituir encima duplica la leyenda. */}
          <div className="flex flex-col gap-1.5 pt-1">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={usarLegales}
                onChange={(e) => setUsarLegales(e.target.checked)}
                className="rounded"
              />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                {t("cenefas.usarLegales")}
              </span>
            </label>
            <span className="text-xs text-slate-400 dark:text-slate-500">{t("cenefas.usarLegalesHint")}</span>
            {usarLegales && (
              <div className="pt-1.5">
                <ComboField
                  label={t("cenefas.legales")}
                  value={legales}
                  onChange={setLegales}
                  storageKey={`cenefas.legales.${category}`}
                />
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1.5">
                  {t("cenefas.legalesAlcoholHint")}
                </p>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
              {t("cenefas.rompePrecios.cocarda")}
            </span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{t("cenefas.rompePrecios.cocardaHint")}</span>
            <label className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border-2 transition-all cursor-pointer ${
              cocarda ? "border-brand-400 bg-brand-50 dark:bg-brand-950/20" : "border-dashed border-slate-300 dark:border-slate-700 hover:border-slate-400"
            }`}>
              <ImageIcon size={18} className={cocarda ? "text-brand-500" : "text-slate-400"} />
              <span className={`text-sm flex-1 truncate ${cocarda ? "text-brand-700 dark:text-brand-300 font-medium" : "text-slate-400"}`}>
                {cocarda ? cocarda.name : t("cenefas.chooseFile")}
              </span>
              {cocarda && (
                <button
                  type="button"
                  onClick={(e) => { e.preventDefault(); setCocarda(null); }}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X size={14} />
                </button>
              )}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && setCocarda(e.target.files[0])}
              />
            </label>
          </div>
        </div>

        <div className="card p-5 space-y-3">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {totalCenefas > 0
              ? t("cenefas.lote.seVanAGenerar", { n: totalCenefas, excels: emparejadas.length })
              : t("cenefas.lote.faltaEmparejar")}
          </p>
          <button
            onClick={handleGenerar}
            disabled={!puedeGenerar}
            className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {enviando
              ? <><Loader2 size={16} className="animate-spin" /> {t("cenefas.generating")}</>
              : <><Send size={16} /> {t("cenefas.generate")}</>}
          </button>
        </div>
      </div>

      {pickerPara !== null && (
        <TemplatePickerModal
          category={category}
          categoryLabel={categoryLabel}
          maxSeleccion={MAX_PLANTILLAS - (entradas[pickerPara]?.plantillas.length ?? 0)}
          onClose={() => setPickerPara(null)}
          onSelect={(tmpl) => { agregarPlantilla(pickerPara, tmpl); setPickerPara(null); }}
          onSelectMany={(tmpls) => { agregarPlantillas(pickerPara, tmpls); setPickerPara(null); }}
        />
      )}
    </div>
  );
}
