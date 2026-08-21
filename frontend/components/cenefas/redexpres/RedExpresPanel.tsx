"use client";
import { useState, useEffect, ChangeEvent, FormEvent } from "react";
import { FileSpreadsheet, Plus, Trash2, Download, Loader2 } from "lucide-react";
import { cenefasV2Api } from "@/lib/api";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { CenefaTemplateRecord } from "@/types/cenefas";
import PreviewStep from "@/components/cenefas/PreviewStep";
import { FileDropField } from "@/components/cenefas/rompeprecios/RompePreciosPanel";

// Redexpress v2: unificado con Rompe Precios y Parrilla y Vinos.
// Flujo: seleccionar plantilla v2 (category="redexpres") → cargar Excel → preview → download
// Usa las 21 variables estándares, sin parámetros globales.

export default function RedExpresPanel() {
  const { t } = useTranslation();

  const [excel, setExcel] = useState<File | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<CenefaTemplateRecord | null>(null);
  const [templates, setTemplates] = useState<CenefaTemplateRecord[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    cenefasV2Api.listTemplates({ category: "redexpres" })
      .then(({ data }) => setTemplates(data))
      .catch(() => toast.error("No se pudieron cargar los templates guardados"))
      .finally(() => setLoadingTemplates(false));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedTemplate || !excel || submitting) return;
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("excel", excel);
      fd.append("template_v2_id", selectedTemplate.id);
      const { data } = await cenefasV2Api.createJob(fd);
      setJobId(data.job_id);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("cenefas.unknownError"));
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = !!selectedTemplate && !!excel && !submitting;

  if (jobId) {
    return <PreviewStep jobId={jobId} onBack={() => setJobId(null)} />;
  }

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-6 items-start">
      {/* Plantillas */}
      <div className="flex flex-col gap-5">
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            {t("cenefas.savedTemplates")}
          </p>
          {loadingTemplates ? (
            <div className="flex gap-2">{[1, 2].map((i) => <div key={i} className="skeleton h-16 w-40 rounded-xl" />)}</div>
          ) : templates.length === 0 ? (
            <div className="flex items-center gap-2 py-3 text-slate-400">
              <span className="text-xs">{t("cenefas.noTemplates")}</span>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {templates.map((tmpl) => (
                <button
                  key={tmpl.id}
                  type="button"
                  onClick={() => setSelectedTemplate(selectedTemplate?.id === tmpl.id ? null : tmpl)}
                  className={`px-3 py-2.5 rounded-xl border-2 transition-all text-xs font-semibold ${
                    selectedTemplate?.id === tmpl.id
                      ? "border-emerald-400 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:border-slate-300"
                  }`}
                >
                  {tmpl.name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Excel + Botón */}
      <div className="flex flex-col gap-5">
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

        <button type="submit" disabled={!canSubmit} className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed">
          {submitting ? (
            <><Loader2 size={16} className="animate-spin" /> {t("cenefas.generating")}</>
          ) : (
            <><Download size={16} /> {t("cenefas.generate")}</>
          )}
        </button>
      </div>
    </form>
  );
}
