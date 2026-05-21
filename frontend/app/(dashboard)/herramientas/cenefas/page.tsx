"use client";
import { useState, useRef, ChangeEvent, FormEvent } from "react";
import { Upload, Presentation, Download, AlertCircle, CheckCircle2, Loader2, FileSpreadsheet, FileType2 } from "lucide-react";
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
    <div className="animate-fade-in max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 flex items-center justify-center shrink-0">
          <Presentation size={22} className="text-emerald-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Generador de Cenefas</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Subí el Excel de productos y la plantilla PPTX para generar el archivo final.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Archivos */}
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Archivos</p>

          <FileDropField
            label="Excel de productos"
            hint=".xlsx / .xlsm"
            accept=".xlsx,.xlsm"
            file={excel}
            icon={FileSpreadsheet}
            accentColor="emerald"
            onChange={handleFile(setExcel)}
          />
          <FileDropField
            label="Plantilla PPTX base"
            hint=".pptx"
            accept=".pptx"
            file={template}
            icon={FileType2}
            accentColor="brand"
            onChange={handleFile(setTemplate)}
          />
        </div>

        {/* Configuración */}
        <div className="card p-6 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Configuración</p>

          <Field
            label="Vigencia *"
            placeholder="ej: 28/5/2026 al 3/6/2026"
            value={vigencia}
            onChange={setVigencia}
          />
          <Field
            label="Aclaración"
            value={aclaracion}
            onChange={setAclaracion}
          />
          <Field
            label="Leyenda alcohol"
            value={otraAlcohol}
            onChange={setOtraAlcohol}
          />
        </div>

        {/* Feedback */}
        {status === "error" && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <AlertCircle size={16} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{errorMsg}</p>
          </div>
        )}
        {status === "success" && (
          <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
            <CheckCircle2 size={16} className="text-emerald-600" />
            <p className="text-sm text-emerald-700 font-medium">
              ¡Cenefas generadas! La descarga comenzó automáticamente.
            </p>
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {status === "loading" ? (
            <><Loader2 size={16} className="animate-spin" /> Generando…</>
          ) : (
            <><Download size={16} /> Generar y descargar PPTX</>
          )}
        </button>
      </form>

      <a ref={downloadRef} className="hidden" />
    </div>
  );
}

// ---------------------------------------------------------------------------

function FileDropField({
  label, hint, accept, file, onChange, icon: Icon, accentColor,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  icon: React.ElementType;
  accentColor: "emerald" | "brand";
}) {
  const id = label.replace(/\s+/g, "-").toLowerCase();
  const active = !!file;
  const colors = {
    emerald: {
      border: active ? "border-emerald-400 bg-emerald-50" : "border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white",
      icon: active ? "text-emerald-500" : "text-slate-400",
      text: active ? "text-emerald-700 font-medium" : "text-slate-500",
      badge: "bg-emerald-100 text-emerald-700",
    },
    brand: {
      border: active ? "border-brand-400 bg-brand-50" : "border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white",
      icon: active ? "text-brand-500" : "text-slate-400",
      text: active ? "text-brand-700 font-medium" : "text-slate-500",
      badge: "bg-brand-100 text-brand-700",
    },
  }[accentColor];

  return (
    <label htmlFor={id} className="flex flex-col gap-1.5 cursor-pointer">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        <span className="text-xs text-slate-400">{hint}</span>
      </div>
      <div className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border-2 transition-all duration-150 ${colors.border}`}>
        <Icon size={18} className={`shrink-0 ${colors.icon}`} />
        <span className={`text-sm flex-1 truncate ${colors.text}`}>
          {file ? file.name : "Elegir archivo…"}
        </span>
        {!file && (
          <span className="text-xs px-2.5 py-1 rounded-lg bg-slate-200 text-slate-500 font-medium shrink-0">
            Buscar
          </span>
        )}
        {file && (
          <span className={`text-xs px-2.5 py-1 rounded-lg font-medium shrink-0 ${colors.badge}`}>
            Listo
          </span>
        )}
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
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input text-sm"
      />
    </label>
  );
}
