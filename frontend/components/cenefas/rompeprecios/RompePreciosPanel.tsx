"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, FileSpreadsheet, Image as ImageIcon, Loader2, Plus, Send, X } from "lucide-react";
import { cenefasV2Api } from "@/lib/api";
import type { CenefaTemplateRecord } from "@/types/cenefas";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import PreviewStep from "@/components/cenefas/PreviewStep";
import SizeTemplateUploadModal from "@/components/cenefas/rompeprecios/SizeTemplateUploadModal";
import { FileDropField } from "@/components/cenefas/redexpress/RedExpressPanel";

const SIZES: { id: string; label: string }[] = [
  { id: "a4",   label: "A4" },
  { id: "3xa4", label: "3xA4" },
  { id: "a5",   label: "A5" },
  { id: "6xa4", label: "6xA4" },
];

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

export default function RompePreciosPanel() {
  const { t } = useTranslation();

  const [templatesBySize, setTemplatesBySize] = useState<Record<string, CenefaTemplateRecord>>({});
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [uploadModalSize, setUploadModalSize] = useState<string | null>(null);
  const [selectedSize, setSelectedSize] = useState<string | null>(null);

  const [excel, setExcel] = useState<File | null>(null);
  const [vigencia, setVigencia] = useState("");
  const [cocarda, setCocarda] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  function loadTemplates() {
    setLoadingTemplates(true);
    cenefasV2Api.listTemplates({ category: "rompe_precios" })
      .then(({ data }) => {
        const bySize: Record<string, CenefaTemplateRecord> = {};
        for (const tmpl of data) {
          const size = tmpl.formats?.[0];
          if (size && !bySize[size]) bySize[size] = tmpl;
        }
        setTemplatesBySize(bySize);
      })
      .catch(() => toast.error(t("cenefas.unknownError")))
      .finally(() => setLoadingTemplates(false));
  }

  useEffect(loadTemplates, [t]);

  const canSubmit = !!excel && !!selectedSize && !submitting;

  async function handleSubmit() {
    if (!canSubmit) return;
    const tmpl = templatesBySize[selectedSize!];
    if (!tmpl) return;

    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel!);
      fd.append("template_v2_id", tmpl.id);
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
      {/* Columna izquierda: plantillas por tamaño + Excel */}
      <div className="flex flex-col gap-5">
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            {t("cenefas.rompePrecios.sizesTitle")}
          </p>
          {loadingTemplates ? (
            <div className="grid grid-cols-2 gap-2">
              {SIZES.map((s) => <div key={s.id} className="skeleton h-20 rounded-xl" />)}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {SIZES.map((size) => {
                const tmpl = templatesBySize[size.id];
                const isSelected = selectedSize === size.id;
                return (
                  <div
                    key={size.id}
                    onClick={() => tmpl ? setSelectedSize(size.id) : setUploadModalSize(size.id)}
                    className={`relative flex flex-col gap-1.5 p-3 rounded-xl border-2 cursor-pointer transition-all ${
                      isSelected
                        ? "border-brand-400 bg-brand-50 dark:bg-brand-950/20"
                        : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:border-slate-300 dark:hover:border-slate-600"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-sm font-bold ${isSelected ? "text-brand-700 dark:text-brand-300" : "text-slate-700 dark:text-slate-300"}`}>
                        {size.label}
                      </span>
                      {isSelected && <CheckCircle2 size={14} className="text-brand-500" />}
                    </div>
                    {tmpl ? (
                      <>
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 truncate">{tmpl.name}</p>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setUploadModalSize(size.id); }}
                          className="self-start text-[10px] text-slate-400 hover:text-brand-500 underline"
                        >
                          {t("cenefas.rompePrecios.replace")}
                        </button>
                      </>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] text-slate-400">
                        <Plus size={11} /> {t("cenefas.rompePrecios.uploadTemplate")}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{t("cenefas.filesSection")}</p>
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

      {uploadModalSize && (
        <SizeTemplateUploadModal
          sizeId={uploadModalSize}
          sizeLabel={SIZES.find((s) => s.id === uploadModalSize)?.label ?? uploadModalSize}
          onClose={() => setUploadModalSize(null)}
          onSaved={() => { setUploadModalSize(null); loadTemplates(); }}
        />
      )}
    </div>
  );
}
