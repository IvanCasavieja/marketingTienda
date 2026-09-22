"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Upload, Loader2, FileUp, LayoutTemplate, Pencil } from "lucide-react";
import { toast } from "sonner";
import { cenefasV2Api } from "@/lib/api";
import { useEditorStore } from "@/store/editor";
import type { CenefaTemplate } from "@/types/cenefas";
import { cargarFormatosDeHoja, type FormatoDeHoja } from "@/lib/cenefas/formatosDeHoja";

interface BuiltinDef {
  slug: string;
  name: string;
  format_id: string;
  definition: CenefaTemplate;
}

interface Props {
  onDismiss: () => void;
}

// ACÁ HABÍA UNA TABLA DE ETIQUETAS ESCRITA A MANO ("A4 · 21 × 29.7 cm",
// "Pinchos · 6 por A4") y era una de las cinco copias del tamaño de hoja. Se
// desfasó como se desfasan todas: decía 6 pinchos y la tabla única dice 9.
// Ahora la etiqueta se arma con lo que trae backend/app/data/formatos_de_hoja.json.
function etiquetaDeFormato(tabla: Record<string, FormatoDeHoja> | null, id: string): string {
  const f = tabla?.[id];
  if (!f) return id;
  const papel = `${f.papel.ancho} × ${f.papel.alto} cm`;
  return f.slots > 1 ? `${f.label} · ${f.slots} por hoja de ${papel}` : `${f.label} · ${papel}`;
}

export default function ImportPanel({ onDismiss }: Props) {
  const { loadDefinition } = useEditorStore();

  const [builtins, setBuiltins]   = useState<BuiltinDef[]>([]);
  const [loading, setLoading]     = useState(true);
  const [uploading, setUploading] = useState(false);
  // La tabla de formatos, para etiquetas y miniaturas. Si no llega, se
  // muestra el id pelado: peor que un cartel feo es uno con un número
  // inventado.
  const [hojas, setHojas] = useState<Record<string, FormatoDeHoja> | null>(null);
  useEffect(() => {
    let vivo = true;
    cargarFormatosDeHoja().then((t) => { if (vivo) setHojas(t); }).catch(() => {});
    return () => { vivo = false; };
  }, []);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    cenefasV2Api
      .getBuiltinDefinitions()
      .then(({ data }) => setBuiltins(data))
      .catch(() => toast.error("No se pudieron cargar las plantillas predeterminadas"))
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
        // PowerPoint puede agrandar una caja al escribir el nombre de una
        // variable larga adentro (autoajuste "cambiar tamaño de la forma al
        // texto") y dejarla centrada fuera de la hoja -- invisible en el
        // PPTX final. El backend ya lo corrige solo al importar
        // (_autocorregir_geometria en pptx_importer.py); esto solo avisa,
        // nunca bloquea, mismo criterio que la revisión previa del Excel.
        const avisos = data.import_warnings ?? [];
        if (avisos.length > 0) {
          const variables = avisos
            .map((w) => w.detalle_datos?.variable)
            .filter(Boolean)
            .join(", ");
          toast.warning(
            `Se corrigieron ${avisos.length} cuadro${avisos.length > 1 ? "s" : ""} que PowerPoint había agrandado mal` +
              (variables ? ` (${variables})` : "") +
              " — revisalos en el editor si querés ajustarlos.",
            { duration: 8000 },
          );
        }
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
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 w-full overflow-hidden">

        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Elegir base para el template</h2>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Empezá desde un template predeterminado, importá un PPTX propio o diseñá desde cero.
          </p>
        </div>

        <div className="p-6 space-y-5">

          {/* --- Plantillas predeterminadas --- */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <LayoutTemplate size={13} className="text-slate-400 dark:text-slate-500" />
              <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                Plantillas predeterminadas
              </span>
            </div>
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
                <Loader2 size={13} className="animate-spin" /> Cargando…
              </div>
            ) : builtins.length === 0 ? (
              <p className="text-xs text-slate-400 dark:text-slate-500">No hay plantillas disponibles</p>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {builtins.map((b) => (
                  <button
                    key={b.slug}
                    onClick={() => handleSelectBuiltin(b)}
                    className="group flex flex-col gap-2 p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950/30 transition-all text-left"
                  >
                    {/* Miniatura del formato */}
                    <FormatThumb formato={hojas?.[b.format_id]} />
                    <div>
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 group-hover:text-brand-700 dark:group-hover:text-brand-400">
                        {b.name}
                      </p>
                      <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                        {etiquetaDeFormato(hojas, b.format_id)}
                      </p>
                      <p className="text-[10px] text-slate-400 dark:text-slate-500">
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
              <FileUp size={13} className="text-slate-400 dark:text-slate-500" />
              <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                Importar PPTX propio
              </span>
            </div>
            <div
              onDrop={onDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => !uploading && fileInputRef.current?.click()}
              className="relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700 hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50/50 dark:hover:bg-brand-950/20 transition-all cursor-pointer p-6"
            >
              {uploading ? (
                <>
                  <Loader2 size={20} className="animate-spin text-brand-500" />
                  <p className="text-xs text-slate-500 dark:text-slate-400">Importando…</p>
                </>
              ) : (
                <>
                  <Upload size={20} className="text-slate-400 dark:text-slate-500" />
                  <p className="text-xs text-slate-600 dark:text-slate-300 font-medium">
                    Arrastrá o hacé clic para subir un .pptx
                  </p>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500">
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
        <div className="px-6 py-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <button
            onClick={onDismiss}
            className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
          >
            <Pencil size={12} />
            Empezar desde cero
          </button>
          <p className="text-[10px] text-slate-400 dark:text-slate-500">
            Podés cambiar el template más adelante desde el menú Cargar
          </p>
        </div>
      </div>
    </div>
  );
}


/* Miniatura visual del formato: la proporción del PAPEL y la grilla de
   celdas, las dos sacadas de la tabla única. Sin tabla, un rectángulo. */
function FormatThumb({ formato }: { formato?: FormatoDeHoja }) {
  const ANCHO_PX = 32;
  const cfg: { w: number; h: number; rows?: number; cols?: number } = formato
    ? {
        w: formato.papel.ancho >= formato.papel.alto ? Math.round(ANCHO_PX * 1.4) : ANCHO_PX,
        h: Math.round(
          (formato.papel.ancho >= formato.papel.alto ? Math.round(ANCHO_PX * 1.4) : ANCHO_PX)
          * formato.papel.alto / formato.papel.ancho,
        ),
        rows: formato.slotRows > 1 ? formato.slotRows : undefined,
        cols: formato.slotCols > 1 ? formato.slotCols : undefined,
      }
    : { w: ANCHO_PX, h: Math.round(ANCHO_PX * 1.41) };

  return (
    <div
      className="rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 overflow-hidden"
      style={{ width: cfg.w, height: cfg.h }}
    >
      {cfg.rows && cfg.cols ? (
        // Grilla 2D (pinchos, 6xA4)
        <div className="w-full h-full flex flex-col">
          {Array.from({ length: cfg.rows }).map((_, r) => (
            <div key={r} className="flex flex-1 border-b border-slate-200 dark:border-slate-700 last:border-0">
              {Array.from({ length: cfg.cols! }).map((_, c) => (
                <div key={c} className="flex-1 border-r border-slate-200 dark:border-slate-700 last:border-0 bg-white" />
              ))}
            </div>
          ))}
        </div>
      ) : cfg.rows ? (
        // Filas apiladas (3xA4: 3 franjas horizontales)
        <div className="w-full h-full flex flex-col">
          {Array.from({ length: cfg.rows }).map((_, i) => (
            <div key={i} className="flex-1 w-full border-b border-slate-200 dark:border-slate-700 last:border-0 bg-white" />
          ))}
        </div>
      ) : cfg.cols ? (
        // Columnas (A5: dos cenefas una al lado de la otra)
        <div className="w-full h-full flex">
          {Array.from({ length: cfg.cols }).map((_, i) => (
            <div key={i} className="flex-1 h-full border-r border-slate-200 dark:border-slate-700 last:border-0 bg-white" />
          ))}
        </div>
      ) : (
        <div className="w-full h-full bg-white" />
      )}
    </div>
  );
}
