"use client";
import { useState, useRef, ChangeEvent, FormEvent } from "react";
import { Upload, FilePresentation, Download, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { toolsApi } from "@/lib/api";

type Status = "idle" | "loading" | "success" | "error";

export default function CenefasPage() {
  const [excel, setExcel] = useState<File | null>(null);
  const [template, setTemplate] = useState<File | null>(null);
  const [vigencia, setVigencia] = useState("");
  const [aclaracion, setAclaracion] = useState("Bases y condiciones en redexpres.uy");
  const [otraAlcohol, setOtraAlcohol] = useState(
    "Prohibida la venta de bebidas alcohólicas a menores de 18 años"
  );
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const downloadRef = useRef<HTMLAnchorElement>(null);

  function handleFile(setter: (f: File) => void) {
    return (e: ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.[0]) setter(e.target.files[0]);
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!excel || !template || !vigencia.trim()) return;

    setStatus("loading");
    setErrorMsg("");

    try {
      const fd = new FormData();
      fd.append("excel", excel);
      fd.append("template", template);
      fd.append("vigencia", vigencia.trim());
      fd.append("aclaracion", aclaracion.trim());
      fd.append("otra_alcohol", otraAlcohol.trim());

      const { data } = await toolsApi.generateCenefas(fd);
      const url = URL.createObjectURL(new Blob([data], {
        type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      }));
      if (downloadRef.current) {
        downloadRef.current.href = url;
        downloadRef.current.download = "cenefas_output.pptx";
        downloadRef.current.click();
        URL.revokeObjectURL(url);
      }
      setStatus("success");
    } catch (err: any) {
      const detail = err?.response?.data
        ? await err.response.data.text?.() ?? "Error desconocido"
        : err?.message ?? "Error desconocido";
      setErrorMsg(detail);
      setStatus("error");
    }
  }

  const canSubmit = !!excel && !!template && !!vigencia.trim() && status !== "loading";

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-xl bg-brand-500/10 flex items-center justify-center">
            <FilePresentation size={17} className="text-brand-400" />
          </div>
          <h1 className="section-title">Generador de Cenefas</h1>
        </div>
        <p className="section-sub ml-11">
          Subí el Excel de productos y la plantilla PPTX para generar el archivo final.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* File uploads */}
        <div className="card space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Archivos</p>

          <FileDropField
            label="Excel de productos (.xlsx)"
            accept=".xlsx,.xlsm"
            file={excel}
            onChange={handleFile(setExcel)}
          />
          <FileDropField
            label="Plantilla PPTX base (.pptx)"
            accept=".pptx"
            file={template}
            onChange={handleFile(setTemplate)}
          />
        </div>

        {/* Config */}
        <div className="card space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Configuración</p>

          <Field label="Vigencia *" placeholder="ej: 28/5/2026 al 3/6/2026" value={vigencia} onChange={setVigencia} />
          <Field label="Aclaración" value={aclaracion} onChange={setAclaracion} />
          <Field label="Leyenda alcohol" value={otraAlcohol} onChange={setOtraAlcohol} />
        </div>

        {/* Status feedback */}
        {status === "error" && (
          <div className="flex items-start gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <span>{errorMsg}</span>
          </div>
        )}
        {status === "success" && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-3">
            <CheckCircle2 size={16} />
            <span>¡Cenefas generadas! La descarga comenzó automáticamente.</span>
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="btn-secondary w-full flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {status === "loading" ? (
            <><Loader2 size={16} className="animate-spin" /> Generando…</>
          ) : (
            <><Download size={16} /> Generar y descargar PPTX</>
          )}
        </button>
      </form>

      {/* Hidden anchor for programmatic download */}
      <a ref={downloadRef} className="hidden" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FileDropField({
  label, accept, file, onChange,
}: {
  label: string;
  accept: string;
  file: File | null;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
}) {
  const id = label.replace(/\s+/g, "-").toLowerCase();
  return (
    <label htmlFor={id} className="flex flex-col gap-1 cursor-pointer">
      <span className="text-xs text-slate-400">{label}</span>
      <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors
        ${file
          ? "border-brand-500/50 bg-brand-500/5 text-brand-300"
          : "border-white/10 bg-white/3 text-slate-500 hover:border-white/20 hover:text-slate-400"
        }`}>
        <Upload size={15} className="shrink-0" />
        <span className="text-sm truncate">
          {file ? file.name : "Elegir archivo…"}
        </span>
      </div>
      <input id={id} type="file" accept={accept} onChange={onChange} className="hidden" />
    </label>
  );
}

function Field({
  label, placeholder, value, onChange,
}: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-slate-200
                   placeholder:text-slate-600 focus:outline-none focus:border-brand-500/60
                   focus:bg-brand-500/5 transition-colors"
      />
    </label>
  );
}
