"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Upload, Loader2, FileUp, LayoutTemplate, Pencil } from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import { useEditorStore } from "@/store/editor";
import type { CenefaTemplate } from "@/types/cenefas";

interface BuiltinDef {
  slug: string;
  name: string;
  format_id: string;
  definition: CenefaTemplate;
}

interface Props {
  onDismiss: () => void;
}

const FORMAT_LABELS: Record<string, string> = {
  a4:      "A4 · 21 × 29.7 cm",
  pinchos: "Pinchos · 6 por A4",
  "3xa4":  "3 × A4 · 3 franjas en A4 vertical",
  a3:      "A3 · 29.7 × 42 cm",
};

export default function ImportPanel({ onDismiss }: Props) {
  const { loadDefinition } = useEditorStore();

  const [builtins, setBuiltins]   = useState<BuiltinDef[]>([]);
  const [loading, setLoading]     = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    cenefasV2Api
      .getBuiltinDefinitions()
      .then(({ data }) => setBuiltins(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function handleSelectBuiltin(def: BuiltinDef) {
    loadDefinition({ ...def.definition, name: def.name });
    onDismiss();
  }

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pptx")) {
        toast.error("Solo se aceptan archivos .pptx");
        return;
      }
      setUploading(true);
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("name", file.name.replace(/\.pptx$/i, ""));
        const { data } = await cenefasV2Api.importPptx(fd);
        loadDefinition(data);
        onDismiss();
        toast.success(`PPTX importado: ${data.components.length} componentes detectados`);
      } catch {
        toast.error("No se pudo importar el PPTX. Verificá que sea una cenefa válida.");
      } finally {
        setUploading(false);
      }
    },
    [loadDefinition, onDismiss],
  );

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="w-full max-w-2xl">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full overflow-hidden">

        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-100">
          <h2 className="text-base font-semibold text-slate-800">Elegir base para el template</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Empezá desde un template predeterminado, importá un PPTX propio o diseñá desde cero.
          </p>
        </div>

        <div className="p-6 space-y-5">

          {/* --- Plantillas predeterminadas --- */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <LayoutTemplate size={13} className="text-slate-400" />
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Plantillas predeterminadas
              </span>
            </div>
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 size={13} className="animate-spin" /> Cargando…
              </div>
            ) : builtins.length === 0 ? (
              <p className="text-xs text-slate-400">No hay plantillas disponibles</p>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {builtins.map((b) => (
                  <button
                    key={b.slug}
                    onClick={() => handleSelectBuiltin(b)}
                    className="group flex flex-col gap-2 p-4 rounded-xl border border-slate-200 hover:border-brand-400 hover:bg-brand-50 transition-all text-left"
                  >
                    {/* Miniatura del formato */}
                    <FormatThumb formatId={b.format_id} />
                    <div>
                      <p className="text-sm font-semibold text-slate-700 group-hover:text-brand-700">
                        {b.name}
                      </p>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        {FORMAT_LABELS[b.format_id] ?? b.format_id}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {b.definition.components.length} componentes
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* --- Importar PPTX --- */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <FileUp size={13} className="text-slate-400" />
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Importar PPTX propio
              </span>
            </div>
            <div
              onDrop={onDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => !uploading && fileInputRef.current?.click()}
              className="relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 hover:border-brand-300 hover:bg-brand-50/50 transition-all cursor-pointer p-6"
            >
              {uploading ? (
                <>
                  <Loader2 size={20} className="animate-spin text-brand-500" />
                  <p className="text-xs text-slate-500">Importando…</p>
                </>
              ) : (
                <>
                  <Upload size={20} className="text-slate-400" />
                  <p className="text-xs text-slate-600 font-medium">
                    Arrastrá o hacé clic para subir un .pptx
                  </p>
                  <p className="text-[10px] text-slate-400">
                    Los placeholders {"<<PRECIO>>"}, {"<<DESCRIPCION>>"}, etc. se detectan automáticamente
                  </p>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pptx"
                className="hidden"
                onChange={onFileChange}
              />
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between">
          <button
            onClick={onDismiss}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 transition-colors"
          >
            <Pencil size={12} />
            Empezar desde cero
          </button>
          <p className="text-[10px] text-slate-400">
            Podés cambiar el template más adelante desde el menú Cargar
          </p>
        </div>
      </div>
    </div>
  );
}


/* Miniatura visual del formato */
function FormatThumb({ formatId }: { formatId: string }) {
  const configs: Record<string, { w: number; h: number; rows?: number; cols?: number }> = {
    a4:      { w: 32, h: 45 },
    a3:      { w: 45, h: 64 },
    "3xa4":  { w: 32, h: 45, rows: 3 },   // A4 portrait con 3 franjas horizontales apiladas
    pinchos: { w: 32, h: 45, rows: 2, cols: 3 }, // A4 portrait grilla 3×2
  };
  const cfg = configs[formatId] ?? { w: 32, h: 45 };

  return (
    <div
      className="rounded border border-slate-200 bg-slate-50 overflow-hidden"
      style={{ width: cfg.w, height: cfg.h }}
    >
      {cfg.rows && cfg.cols ? (
        // Grilla 2D (pinchos: 3 cols × 2 filas)
        <div className="w-full h-full flex flex-col">
          {Array.from({ length: cfg.rows }).map((_, r) => (
            <div key={r} className="flex flex-1 border-b border-slate-200 last:border-0">
              {Array.from({ length: cfg.cols! }).map((_, c) => (
                <div key={c} className="flex-1 border-r border-slate-200 last:border-0 bg-white" />
              ))}
            </div>
          ))}
        </div>
      ) : cfg.rows ? (
        // Filas apiladas (3xA4: 3 franjas horizontales)
        <div className="w-full h-full flex flex-col">
          {Array.from({ length: cfg.rows }).map((_, i) => (
            <div key={i} className="flex-1 w-full border-b border-slate-200 last:border-0 bg-white" />
          ))}
        </div>
      ) : cfg.cols ? (
        // Columnas (no usado actualmente)
        <div className="w-full h-full flex">
          {Array.from({ length: cfg.cols }).map((_, i) => (
            <div key={i} className="flex-1 h-full border-r border-slate-200 last:border-0 bg-white" />
          ))}
        </div>
      ) : (
        <div className="w-full h-full bg-white" />
      )}
    </div>
  );
}
