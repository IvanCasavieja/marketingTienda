"use client";
import { useState } from "react";
import { FileSpreadsheet, FolderOpen, Image as ImageIcon, Loader2, Send, X } from "lucide-react";
import { cenefasV2Api, toolsApi } from "@/lib/api";
import type { CenefaTemplateRecord } from "@/types/cenefas";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import PreviewStep from "@/components/cenefas/PreviewStep";
import TemplatePickerModal, { typeLabel } from "@/components/cenefas/rompeprecios/TemplatePickerModal";
import { FileDropField } from "@/components/cenefas/FileDropField";

// Variable convencional para la imagen de cocarda — la plantilla pptx debe
// tener un componente de imagen con esta variable para que se reemplace.
const COCARDA_VAR = "imagen";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

interface RompePreciosPanelProps {
  // Destino/categoría de este panel -- separa las plantillas y el Excel de
  // este flujo de las de cualquier otro destino que reuse el mismo panel
  // (ver DestinoModal.tsx). El label mostrado se deriva de
  // cenefas.destino.{category}.label, así que un destino nuevo no necesita
  // tocar este archivo, solo agregar su entrada al i18n.
  category: "rompe_precios" | "parrilla_y_vinos";
}

export default function RompePreciosPanel({ category }: RompePreciosPanelProps) {
  const { t } = useTranslation();
  const categoryLabel = t(`cenefas.destino.${category}.label`);

  const [selectedTemplate, setSelectedTemplate] = useState<CenefaTemplateRecord | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const [excel, setExcel] = useState<File | null>(null);
  const [vigencia, setVigencia] = useState("");
  const [cocarda, setCocarda] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

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

  const canSubmit = !!excel && !!selectedTemplate && !submitting;

  async function handleSubmit() {
    if (!canSubmit || !selectedTemplate) return;

    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel!);
      fd.append("template_v2_id", selectedTemplate.id);
      fd.append("vigencia", vigencia.trim());

      if (cocarda) {
        const ext = cocarda.name.split(".").pop()?.toLowerCase() ?? "png";
        const b64 = await fileToBase64(cocarda);
        fd.append("image_overrides_json", JSON.stringify({ [COCARDA_VAR]: `${ext}:${b64}` }));
      }

      const { data } = await cenefasV2Api.createJob(fd);
      setJobId(data.job_id);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setSubmitting(false);
    }
  }

  if (jobId) {
    return <PreviewStep jobId={jobId} onBack={() => setJobId(null)} />;
  }

  return (
    <div className="grid grid-cols-2 gap-6 items-start">
      {/* Columna izquierda: plantilla + Excel */}
      <div className="flex flex-col gap-5">
        <div className="card p-6 space-y-3">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            {t("cenefas.rompePrecios.templateLabel")}
          </p>
          {selectedTemplate ? (
            <div className="flex items-center justify-between gap-3 p-3 rounded-xl border-2 border-brand-400 bg-brand-50 dark:bg-brand-950/20">
              <div className="min-w-0">
                <p className="text-sm font-bold text-brand-700 dark:text-brand-300 truncate">{selectedTemplate.name}</p>
                <p className="text-[10px] text-brand-500/80 dark:text-brand-400/80">
                  {selectedTemplate.formats?.length ? selectedTemplate.formats.map((f) => typeLabel(f)).join(", ") : "—"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="shrink-0 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-800 underline"
              >
                {t("cenefas.rompePrecios.changeTemplate")}
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex items-center justify-center gap-2 w-full p-4 rounded-xl border-2 border-dashed border-slate-300 dark:border-slate-700 text-sm font-semibold text-slate-500 dark:text-slate-400 hover:border-brand-400 hover:text-brand-600 dark:hover:text-brand-400 transition-all"
            >
              <FolderOpen size={16} /> {t("cenefas.rompePrecios.chooseTemplate")}
            </button>
          )}
        </div>

        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{t("cenefas.filesSection")}</p>
            <button
              type="button"
              onClick={handleDownloadTemplate}
              className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 hover:text-emerald-700 transition-colors"
            >
              <FileSpreadsheet size={13} />
              {t("cenefas.downloadTemplate")}
            </button>
          </div>
          <FileDropField
            label={t("cenefas.excelLabel")}
            hint={t("cenefas.excelHint")}
            accept=".xlsx,.xlsm"
            file={excel}
            icon={FileSpreadsheet}
            accentColor="emerald"
            onChange={(e) => e.target.files?.[0] && setExcel(e.target.files[0])}
            chooseLabel={t("cenefas.chooseFile")}
            readyLabel={t("cenefas.ready")}
            searchLabel={t("cenefas.search")}
          />
        </div>
      </div>

      {/* Columna derecha: vigencia + cocarda + generar */}
      <div className="flex flex-col gap-5">
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{t("cenefas.configSection")}</p>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("cenefas.vigencia")}</span>
            <input
              type="text"
              value={vigencia}
              onChange={(e) => setVigencia(e.target.value)}
              placeholder={t("cenefas.vigenciaPlaceholder")}
              className="input text-sm"
            />
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{t("cenefas.rompePrecios.cocarda")}</span>
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

        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting
            ? <><Loader2 size={16} className="animate-spin" /> {t("cenefas.generating")}</>
            : <><Send size={16} /> {t("cenefas.generate")}</>
          }
        </button>
      </div>

      {pickerOpen && (
        <TemplatePickerModal
          category={category}
          categoryLabel={categoryLabel}
          onClose={() => setPickerOpen(false)}
          onSelect={(tmpl) => { setSelectedTemplate(tmpl); setPickerOpen(false); }}
        />
      )}
    </div>
  );
}
