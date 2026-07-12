"use client";
import { useEditorStore } from "@/store/editor";
import type { CenefaFormat } from "@/types/cenefas";

interface Props {
  formats: CenefaFormat[];
}

export default function FormatSelector({ formats }: Props) {
  const { template, activeFormat, setActiveFormat, toggleFormat } = useEditorStore();

  const enabledFormats = formats.filter((f) => template.formats.includes(f.id));
  const allFormats     = formats;

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {/* Tabs de formatos activos */}
      {enabledFormats.map((fmt) => (
        <button
          key={fmt.id}
          onClick={() => setActiveFormat(fmt.id)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            activeFormat === fmt.id
              ? "bg-brand-600 text-white shadow-sm"
              : "bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-brand-300 dark:hover:border-brand-600 hover:text-brand-600 dark:hover:text-brand-400"
          }`}
        >
          {fmt.label}
          <span className="ml-1.5 text-[10px] opacity-70">
            {fmt.width_cm}×{fmt.height_cm}
          </span>
        </button>
      ))}

      {/* Separador */}
      {allFormats.length > enabledFormats.length && (
        <span className="text-slate-300 dark:text-slate-600 text-xs mx-1">|</span>
      )}

      {/* Formatos desactivados (toggle para agregar) */}
      {allFormats
        .filter((f) => !template.formats.includes(f.id))
        .map((fmt) => (
          <button
            key={fmt.id}
            onClick={() => { toggleFormat(fmt.id); setActiveFormat(fmt.id); }}
            title={`Agregar formato ${fmt.label}`}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-dashed border-slate-300 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:border-brand-400 hover:text-brand-500 dark:hover:text-brand-400 transition-all"
          >
            + {fmt.label}
          </button>
        ))}
    </div>
  );
}
