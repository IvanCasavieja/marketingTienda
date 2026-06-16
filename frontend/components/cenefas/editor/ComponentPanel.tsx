"use client";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent } from "@/types/cenefas";
import { Type, Image, Square, Plus, Eye, EyeOff, Lock, Trash2, Award } from "lucide-react";

// ---------------------------------------------------------------------------
// Catálogo de componentes predefinidos
// ---------------------------------------------------------------------------

interface ComponentBlueprint {
  label: string;
  type: CenefaComponent["type"];
  variable?: string;
  static_value?: string;
  transform?: CenefaComponent["transform"];
  icon: React.ReactNode;
  color: string;
  defaults: Partial<CenefaComponent>;
}

const CATALOG: { category: string; items: ComponentBlueprint[] }[] = [
  {
    category: "Precio",
    items: [
      {
        label: "Precio completo",
        type: "text", variable: "precioActual", transform: "price_full",
        icon: <Type size={14} />, color: "text-blue-600",
        defaults: { style: { font_size: 72, font_bold: true, color: "#E31E24", align: "center" },
                    base_bounds: { x: 1, y: 8, width: 8, height: 3.5 } },
      },
      {
        label: "Precio — entero",
        type: "text", variable: "precioActual", transform: "price_integer",
        icon: <Type size={14} />, color: "text-blue-600",
        defaults: { style: { font_size: 96, font_bold: true, color: "#E31E24", align: "center" },
                    base_bounds: { x: 1.5, y: 8, width: 7, height: 4 } },
      },
      {
        label: "Precio — decimal",
        type: "text", variable: "precioActual", transform: "price_decimal",
        icon: <Type size={14} />, color: "text-blue-500",
        defaults: { style: { font_size: 20, color: "#E31E24" },
                    base_bounds: { x: 9, y: 8, width: 2, height: 1.5 } },
      },
      {
        label: "Precio anterior",
        type: "text", variable: "precioAnterior", transform: "price_full",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 28, color: "#94A3B8" },
                    base_bounds: { x: 1, y: 6, width: 8, height: 1.8 } },
      },
      {
        label: "Precio bancario",
        type: "text", variable: "precioBanco", transform: "price_full",
        icon: <Type size={14} />, color: "text-blue-400",
        defaults: { style: { font_size: 40, color: "#1E3A5F" },
                    base_bounds: { x: 1, y: 12, width: 8, height: 2.5 } },
      },
    ],
  },
  {
    category: "Texto",
    items: [
      {
        label: "Descripción",
        type: "text", variable: "descripcion", transform: "smart_bold",
        icon: <Type size={14} />, color: "text-slate-600",
        defaults: { style: { font_size: 16, align: "center" },
                    base_bounds: { x: 0.5, y: 4, width: 10, height: 3 } },
      },
      {
        label: "Título / Mecánica",
        type: "text", variable: "titulo", transform: "uppercase",
        icon: <Type size={14} />, color: "text-orange-500",
        defaults: { style: { font_size: 32, font_bold: true, color: "#F97316" },
                    base_bounds: { x: 1, y: 6, width: 8, height: 1.5 } },
      },
      {
        label: "Banco / Beneficio",
        type: "text", variable: "banco", transform: "none",
        icon: <Type size={14} />, color: "text-slate-500",
        defaults: { style: { font_size: 11, color: "#1E3A5F" },
                    base_bounds: { x: 0.5, y: 14.5, width: 10, height: 1 } },
      },
      {
        label: "Aclaración",
        type: "text", variable: "aclaracion", transform: "none",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 9 },
                    base_bounds: { x: 0.5, y: 27.5, width: 10, height: 1.5 } },
      },
      {
        label: "Segunda aclaración",
        type: "text", variable: "segundaAclaracion", transform: "none",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 9 },
                    base_bounds: { x: 0.5, y: 29.5, width: 10, height: 1.5 } },
      },
      {
        label: "Vigencia",
        type: "text", variable: "vigencia", transform: "none",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 10 },
                    base_bounds: { x: 0.5, y: 26, width: 10, height: 1 } },
      },
      {
        label: "Código SKU",
        type: "text", variable: "codigoSKU", transform: "none",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 10 },
                    base_bounds: { x: 0.5, y: 0.5, width: 4, height: 0.8 } },
      },
    ],
  },
  {
    category: "Fecha",
    items: [
      {
        label: "Día",
        type: "text", variable: "dia", transform: "uppercase",
        icon: <Type size={14} />, color: "text-slate-500",
        defaults: { style: { font_size: 14, font_bold: true },
                    base_bounds: { x: 0.5, y: 25, width: 3, height: 1 } },
      },
      {
        label: "Mes",
        type: "text", variable: "mes", transform: "none",
        icon: <Type size={14} />, color: "text-slate-500",
        defaults: { style: { font_size: 12 },
                    base_bounds: { x: 3.5, y: 25, width: 3.5, height: 1 } },
      },
      {
        label: "Año",
        type: "text", variable: "año", transform: "none",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 10 },
                    base_bounds: { x: 7.5, y: 25, width: 2.5, height: 1 } },
      },
    ],
  },
  {
    category: "Otros",
    items: [
      {
        label: "Imagen producto",
        type: "image", variable: "imagen",
        icon: <Image size={14} />, color: "text-violet-500",
        defaults: { style: {}, base_bounds: { x: 1, y: 0.5, width: 9, height: 5 } },
      },
      {
        label: "Cocarda / Badge",
        type: "image",
        icon: <Award size={14} />, color: "text-amber-500",
        defaults: { style: {}, base_bounds: { x: 7.5, y: 0, width: 3.5, height: 3.5 } },
      },
      {
        label: "Forma / fondo",
        type: "shape",
        icon: <Square size={14} />, color: "text-emerald-500",
        defaults: { style: { background_color: "#F1F5F9" },
                    base_bounds: { x: 0, y: 0, width: 21, height: 5 } },
      },
      {
        label: "Texto fijo",
        type: "text",
        static_value: "Texto fijo",
        icon: <Type size={14} />, color: "text-slate-400",
        defaults: { style: { font_size: 10, align: "center" },
                    base_bounds: { x: 0.5, y: 1, width: 10, height: 0.8 },
                    static_value: "Texto fijo" },
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Panel principal
// ---------------------------------------------------------------------------

export default function ComponentPanel() {
  const { template, addComponent, selectComponent, updateComponent, deleteComponent } =
    useEditorStore();

  function handleAdd(blueprint: ComponentBlueprint) {
    const id = crypto.randomUUID();
    const comp: CenefaComponent = {
      id,
      type:         blueprint.type,
      name:         blueprint.label,
      variable:     blueprint.variable,
      static_value: blueprint.defaults.static_value,
      transform:    blueprint.transform,
      style:        blueprint.defaults.style ?? {},
      base_bounds:  blueprint.defaults.base_bounds ?? { x: 1, y: 1, width: 6, height: 2 },
      format_overrides: {},
      z_index: template.components.length + 1,
      locked:  false,
      visible: true,
    };
    addComponent(comp);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Catálogo */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {CATALOG.map((section) => (
          <div key={section.category}>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              {section.category}
            </p>
            <div className="space-y-1">
              {section.items.map((item) => (
                <button
                  key={item.label}
                  onClick={() => handleAdd(item)}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left text-xs text-slate-600 hover:bg-slate-50 hover:text-slate-900 border border-transparent hover:border-slate-200 transition-all group"
                >
                  <span className={`${item.color} flex-shrink-0`}>{item.icon}</span>
                  <span className="flex-1">{item.label}</span>
                  <Plus
                    size={12}
                    className="text-slate-300 group-hover:text-brand-500 flex-shrink-0"
                  />
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Lista de componentes en el canvas */}
      {template.components.length > 0 && (
        <div className="border-t border-slate-100 p-3">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
            En el canvas ({template.components.length})
          </p>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {[...template.components]
              .sort((a, b) => b.z_index - a.z_index)
              .map((comp) => (
                <div
                  key={comp.id}
                  className="flex items-center gap-1.5 group"
                >
                  <button
                    onClick={() => selectComponent(comp.id)}
                    className="flex-1 flex items-center gap-2 px-2 py-1 rounded text-left text-xs text-slate-600 hover:bg-slate-50 truncate"
                  >
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{
                        background:
                          comp.type === "text"
                            ? "#3B82F6"
                            : comp.type === "image"
                            ? "#8B5CF6"
                            : "#10B981",
                      }}
                    />
                    <span className="truncate">{comp.name}</span>
                  </button>
                  <button
                    onClick={() => updateComponent(comp.id, { visible: !comp.visible })}
                    className="p-0.5 text-slate-300 hover:text-slate-600 opacity-0 group-hover:opacity-100"
                    title={comp.visible ? "Ocultar" : "Mostrar"}
                  >
                    {comp.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                  </button>
                  <button
                    onClick={() => updateComponent(comp.id, { locked: !comp.locked })}
                    className="p-0.5 text-slate-300 hover:text-slate-600 opacity-0 group-hover:opacity-100"
                    title={comp.locked ? "Desbloquear" : "Bloquear"}
                  >
                    <Lock size={12} className={comp.locked ? "text-amber-400" : ""} />
                  </button>
                  <button
                    onClick={() => deleteComponent(comp.id)}
                    className="p-0.5 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                    title="Eliminar"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
