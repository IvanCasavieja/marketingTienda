"use client";
import { useState, useRef } from "react";
import { X, FileType2, Loader2 } from "lucide-react";
import { cenefasV2Api } from "@/lib/api";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useEscapeKey } from "@/hooks/useEscapeKey";

// Subir o reemplazar la plantilla de UN tamaño de Rompe Precios. Sin edición
// Konva acá — el reposicionamiento pasa en PreviewStep, esto solo importa
// el pptx y lo guarda como CenefaTemplateV2 con category="rompe_precios".

interface SizeTemplateUploadModalProps {
  sizeId: string;
  sizeLabel: string;
  onClose: () => void;
  onSaved: () => void;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function SizeTemplateUploadModal({ sizeId, sizeLabel, onClose, onSaved }: SizeTemplateUploadModalProps) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEscapeKey(onClose);

  async function handleSave() {
    if (!file) return;
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", `Rompe Precios del Finde — ${sizeLabel}`);
      const [{ data: definition }, source_pptx_b64] = await Promise.all([
        cenefasV2Api.importPptx(fd),
        fileToBase64(file),
      ]);

      await cenefasV2Api.createTemplate({
        ...definition,
        formats: [sizeId],
        category: "rompe_precios",
        source_pptx_b64,
      });

      toast.success(t("cenefas.rompePrecios.templateSaved"));
      onSaved();
    } catch {
      toast.error(t("cenefas.rompePrecios.templateSaveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="size-upload-modal-title"
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-sm p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p id="size-upload-modal-title" className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {t("cenefas.rompePrecios.uploadTemplateFor", { size: sizeLabel })}
          </p>
          <button onClick={onClose} aria-label={t("common.close")} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <label
          className={`flex items-center gap-2.5 px-3 py-3 rounded-xl border-2 cursor-pointer transition-all ${
            file ? "border-brand-400 bg-brand-50 dark:bg-brand-950/20" : "border-dashed border-slate-300 dark:border-slate-700 hover:border-slate-400"
          }`}
          onClick={() => inputRef.current?.click()}
        >
          <FileType2 size={16} className={file ? "text-brand-500" : "text-slate-400"} />
          <span className={`text-sm flex-1 truncate ${file ? "text-brand-700 dark:text-brand-300 font-medium" : "text-slate-400"}`}>
            {file ? file.name : t("cenefas.rompePrecios.choosePptx")}
          </span>
          <input
            ref={inputRef}
            type="file"
            accept=".pptx"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
          />
        </label>

        <button
          onClick={handleSave}
          disabled={!file || saving}
          className="btn-primary w-full text-sm py-2 disabled:opacity-40"
        >
          {saving
            ? <span className="flex items-center justify-center gap-1.5"><Loader2 size={14} className="animate-spin" /> {t("cenefas.rompePrecios.saving")}</span>
            : t("cenefas.rompePrecios.saveTemplate")
          }
        </button>
      </div>
    </div>
  );
}
