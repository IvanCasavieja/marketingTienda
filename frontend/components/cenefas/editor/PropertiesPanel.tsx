"use client";
import { useState } from "react";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent, CenefaRule, CenefaTemplate, CenefaVariable, TextSegment, TextTransform } from "@/types/cenefas";
import { Trash2, Lock, Unlock, Plus, GripVertical } from "lucide-react";
import { RuleChip, RuleForm } from "./RulesPanel";

const TRANSFORMS = [
  { value: "none",           label: "Sin transformación" },
  { value: "price_full",     label: "Precio completo ($1.250,90)" },
  { value: "price_integer",  label: "Precio — entero (1250)" },
  { value: "price_decimal",  label: "Precio — decimal (,90)" },
  { value: "combo_quantity", label: "Combo — cantidad (3X)" },
  { value: "combo_price",    label: "Combo — precio ($50)" },
  { value: "uppercase",      label: "Mayúsculas" },
  { value: "smart_bold",     label: "Bold automático (MARCAS)" },
];

export default function PropertiesPanel() {
  const { template, selectedComponentId, getSelectedComponent, updateComponent, deleteComponent, addRule, deleteRule } =
    useEditorStore();

  const comp = getSelectedComponent();
  const [showRuleForm, setShowRuleForm] = useState(false);

  if (!comp) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-6">
        <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mb-3">
          <span className="text-slate-300 text-lg">✦</span>
        </div>
        <p className="text-sm text-slate-500 font-medium">Ningún componente seleccionado</p>
        <p className="text-xs text-slate-400 mt-1">
          Clic sobre un elemento del canvas para editar sus propiedades
        </p>
      </div>
    );
  }

  function set<K extends keyof CenefaComponent>(key: K, value: CenefaComponent[K]) {
    updateComponent(comp!.id, { [key]: value } as Partial<CenefaComponent>);
  }

  function setStyle(key: string, value: unknown) {
    updateComponent(comp!.id, { style: { ...comp!.style, [key]: value } });
  }

  function setBounds(key: string, value: number) {
    updateComponent(comp!.id, {
      base_bounds: { ...comp!.base_bounds, [key]: value },
    });
  }

  return (
    <div className="flex-1 overflow-y-auto min-h-0">
      {/* Header del componente */}
      <div className="p-4 border-b border-slate-100 flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <input
            className="w-full text-sm font-semibold text-slate-800 bg-transparent border-b border-transparent hover:border-slate-200 focus:border-brand-400 focus:outline-none pb-0.5"
            value={comp.name}
            onChange={(e) => set("name", e.target.value)}
          />
          <span className="text-[10px] text-slate-400 capitalize">{comp.type}</span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => set("locked", !comp.locked)}
            className={`p-1.5 rounded-lg transition-colors ${
              comp.locked
                ? "bg-amber-50 text-amber-500"
                : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            }`}
            title={comp.locked ? "Desbloquear" : "Bloquear"}
          >
            {comp.locked ? <Lock size={14} /> : <Unlock size={14} />}
          </button>
          <button
            onClick={() => deleteComponent(comp.id)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
            title="Eliminar componente"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="p-4 space-y-5">
        {/* === TEXTO: sección unificada de contenido con modo simple / compuesto === */}
        {comp.type === "text" && (
          <Section label="Contenido">
            {/* Toggle modo compuesto */}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-500">Texto compuesto</span>
              <button
                onClick={() => {
                  if (comp.segments?.length) {
                    updateComponent(comp.id, { segments: undefined });
                  } else {
                    const initial: TextSegment[] = comp.variable
                      ? [{ type: "variable", value: comp.variable, transform: comp.transform ?? "none" }]
                      : comp.static_value
                      ? [{ type: "static", value: comp.static_value }]
                      : [{ type: "static", value: "" }];
                    updateComponent(comp.id, { segments: initial });
                  }
                }}
                className={`relative inline-flex w-9 h-5 rounded-full transition-colors ${
                  comp.segments?.length ? "bg-brand-500" : "bg-slate-200"
                }`}
                title={comp.segments?.length ? "Volver a modo simple" : "Activar texto compuesto (múltiples variables/estilos)"}
              >
                <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                  comp.segments?.length ? "translate-x-4" : "translate-x-0.5"
                }`} />
              </button>
            </div>

            {comp.segments?.length ? (
              <SegmentsEditor
                segments={comp.segments}
                variables={template.variables}
                onChange={(segs) => updateComponent(comp.id, { segments: segs.length ? segs : undefined })}
              />
            ) : (
              <div className="space-y-3">
                {/* Variable selector */}
                <div>
                  <p className="text-[10px] text-slate-400 uppercase mb-1">Variable CSV</p>
                  <select
                    className="input w-full text-sm"
                    value={comp.variable ?? ""}
                    onChange={(e) => set("variable", e.target.value || undefined)}
                  >
                    <option value="">— Texto fijo (sin variable) —</option>
                    {template.variables.map((v) => (
                      <option key={v.name} value={v.name}>
                        {v.name} ({v.csv_column})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Texto fijo — solo cuando no hay variable */}
                {!comp.variable && (
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase mb-1">Texto fijo</p>
                    <input
                      type="text"
                      className="input w-full text-sm"
                      placeholder="Ej: VÁLIDO AL:, unidad, ..."
                      value={comp.static_value ?? ""}
                      onChange={(e) => set("static_value", e.target.value || undefined)}
                    />
                    <p className="text-[10px] text-slate-400 mt-1">
                      Aparece igual en todas las cenefas generadas.
                    </p>
                  </div>
                )}

                {/* Transformación */}
                <div>
                  <p className="text-[10px] text-slate-400 uppercase mb-1">Transformación</p>
                  <select
                    className="input w-full text-sm"
                    value={comp.transform ?? "none"}
                    onChange={(e) => set("transform", e.target.value as CenefaComponent["transform"])}
                  >
                    {TRANSFORMS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </Section>
        )}

        {/* === IMAGEN: variable + upload === */}
        {comp.type === "image" && (
          <Section label="Variable imagen">
            <select
              className="input w-full text-sm"
              value={comp.variable ?? ""}
              onChange={(e) => set("variable", e.target.value || undefined)}
            >
              <option value="">— Sin variable (imagen estática) —</option>
              {template.variables.map((v) => (
                <option key={v.name} value={v.name}>
                  {v.name} ({v.csv_column})
                </option>
              ))}
            </select>
          </Section>
        )}

        {comp.type === "image" && (
          <Section label="Imagen estática">
            {comp.image_data ? (
              <div className="space-y-2">
                <img
                  src={`data:image/${comp.image_ext ?? "png"};base64,${comp.image_data}`}
                  alt="preview"
                  className="max-h-24 w-auto rounded border border-slate-200 object-contain"
                />
                <button
                  onClick={() => { set("image_data", undefined); set("image_ext", undefined); }}
                  className="text-[10px] text-rose-500 hover:text-rose-700"
                >
                  Quitar imagen
                </button>
              </div>
            ) : (
              <p className="text-[10px] text-slate-400 italic mb-1">
                Sin imagen — se mostrará un placeholder gris (o la imagen que subas al generar)
              </p>
            )}
            <label className="mt-2 flex flex-col gap-1">
              <span className="text-[10px] text-slate-400 uppercase">
                {comp.image_data ? "Reemplazar imagen" : "Subir imagen al template"}
              </span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                className="text-xs text-slate-500 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-slate-100 file:text-slate-600 hover:file:bg-slate-200"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const ext = file.name.split(".").pop()?.toLowerCase() ?? "png";
                  const reader = new FileReader();
                  reader.onload = (ev) => {
                    const b64 = (ev.target?.result as string).split(",")[1];
                    set("image_data", b64);
                    set("image_ext", ext);
                  };
                  reader.readAsDataURL(file);
                }}
              />
            </label>
          </Section>
        )}

        {/* Posición y tamaño */}
        <Section label="Posición y tamaño (cm)">
          <div className="grid grid-cols-2 gap-2">
            {(["x", "y", "width", "height"] as const).map((key) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 uppercase">{key}</span>
                <input
                  type="number"
                  step="0.1"
                  min={key === "width" || key === "height" ? 0.2 : 0}
                  className="input text-sm"
                  value={comp.base_bounds[key]}
                  onChange={(e) => setBounds(key, parseFloat(e.target.value) || 0)}
                />
              </label>
            ))}
          </div>
        </Section>

        {/* Estilo tipográfico */}
        {comp.type === "text" && (
          <Section label="Estilo">
            <div className="space-y-3">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 uppercase">Tamaño (pt)</span>
                <input
                  type="number"
                  min={6}
                  max={200}
                  className="input text-sm"
                  value={comp.style.font_size ?? 16}
                  onChange={(e) => setStyle("font_size", parseInt(e.target.value) || 16)}
                />
              </label>

              <div className="flex gap-2">
                <label className="flex flex-col gap-1 flex-1">
                  <span className="text-[10px] text-slate-400 uppercase">Color</span>
                  <div className="flex gap-1.5">
                    <input
                      type="color"
                      className="w-8 h-9 rounded border border-slate-200 cursor-pointer p-0.5"
                      value={comp.style.color ?? "#1e293b"}
                      onChange={(e) => setStyle("color", e.target.value)}
                    />
                    <input
                      type="text"
                      className="input text-sm flex-1"
                      value={comp.style.color ?? "#1e293b"}
                      onChange={(e) => setStyle("color", e.target.value)}
                    />
                  </div>
                </label>
              </div>

              <div className="flex items-center gap-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded text-brand-600"
                    checked={comp.style.font_bold ?? false}
                    onChange={(e) => setStyle("font_bold", e.target.checked)}
                  />
                  <span className="text-sm text-slate-600">Negrita</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded text-brand-600"
                    checked={comp.style.auto_fit ?? true}
                    onChange={(e) => setStyle("auto_fit", e.target.checked)}
                  />
                  <span className="text-sm text-slate-600">Auto-ajuste</span>
                </label>
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 uppercase">Alineación</span>
                <div className="flex gap-1">
                  {(["left", "center", "right"] as const).map((a) => (
                    <button
                      key={a}
                      onClick={() => setStyle("align", a)}
                      className={`flex-1 py-1.5 rounded border text-xs transition-all ${
                        (comp.style.align ?? "center") === a
                          ? "bg-brand-50 border-brand-400 text-brand-600 font-medium"
                          : "border-slate-200 text-slate-500 hover:border-slate-300"
                      }`}
                    >
                      {a === "left" ? "←" : a === "center" ? "↔" : "→"}
                    </button>
                  ))}
                </div>
              </label>
            </div>
          </Section>
        )}

        {/* Z-index */}
        <Section label="Orden (z-index)">
          <input
            type="number"
            min={0}
            className="input text-sm w-24"
            value={comp.z_index}
            onChange={(e) => set("z_index", parseInt(e.target.value) || 0)}
          />
        </Section>

        {/* Format overrides */}
        {template.formats.filter((f) => f !== template.master_format).length > 0 && (
          <FormatOverridesSection comp={comp} updateComponent={updateComponent} template={template} />
        )}

        {/* Reglas de visibilidad para este componente */}
        <Section label="Reglas de visibilidad">
          {(() => {
            const compRules = template.rules.filter(
              (r) => r.target_component_id === comp.id
            );
            return (
              <div className="space-y-0.5">
                {compRules.length === 0 && !showRuleForm && (
                  <p className="text-[10px] text-slate-400 italic">
                    Siempre visible — sin reglas
                  </p>
                )}
                {compRules.map((rule) => (
                  <RuleChip
                    key={rule.id}
                    rule={rule}
                    onDelete={() => deleteRule(rule.id)}
                  />
                ))}
                {showRuleForm ? (
                  <div className="mt-2">
                    <RuleForm
                      componentId={comp.id}
                      variables={template.variables}
                      onSave={(rule: CenefaRule) => { addRule(rule); setShowRuleForm(false); }}
                      onCancel={() => setShowRuleForm(false)}
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => setShowRuleForm(true)}
                    className="flex items-center gap-1 text-[10px] text-brand-600 hover:text-brand-700 font-medium mt-1"
                  >
                    <Plus size={10} /> Agregar regla
                  </button>
                )}
              </div>
            );
          })()}
        </Section>
      </div>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
        {label}
      </p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editor de segmentos de texto compuesto
// ---------------------------------------------------------------------------

function SegmentsEditor({
  segments,
  variables,
  onChange,
}: {
  segments: TextSegment[];
  variables: CenefaVariable[];
  onChange: (segs: TextSegment[]) => void;
}) {
  function updateSeg(idx: number, patch: Partial<TextSegment>) {
    onChange(segments.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }

  function updateSegStyle(idx: number, key: string, value: number | string | boolean | undefined) {
    onChange(
      segments.map((s, i) => {
        if (i !== idx) return s;
        const newStyle = { ...s.style };
        if (value === undefined || value === "") {
          delete (newStyle as Record<string, unknown>)[key];
        } else {
          (newStyle as Record<string, unknown>)[key] = value;
        }
        return { ...s, style: newStyle };
      }),
    );
  }

  function removeSeg(idx: number) {
    onChange(segments.filter((_, i) => i !== idx));
  }

  function addSeg() {
    onChange([...segments, { type: "static", value: "" }]);
  }

  return (
    <div className="space-y-2">
      {segments.map((seg, idx) => (
        <div key={idx} className="border border-slate-200 rounded-lg overflow-hidden">
          {/* Header del segmento */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-50 border-b border-slate-100">
            <GripVertical size={12} className="text-slate-300" />
            <span className="text-[10px] font-semibold text-slate-400 uppercase flex-1">
              Segmento {idx + 1}
            </span>
            <button
              onClick={() => removeSeg(idx)}
              className="p-0.5 text-slate-300 hover:text-rose-500 transition-colors"
            >
              <Trash2 size={11} />
            </button>
          </div>

          <div className="p-2.5 space-y-2">
            {/* Tipo: fijo o variable */}
            <div className="flex gap-1">
              {(["static", "variable"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => updateSeg(idx, { type: t, value: "" })}
                  className={`flex-1 py-1 text-xs rounded border transition-all ${
                    seg.type === t
                      ? "bg-brand-50 border-brand-400 text-brand-600 font-medium"
                      : "border-slate-200 text-slate-400 hover:border-slate-300"
                  }`}
                >
                  {t === "static" ? "Texto fijo" : "Variable"}
                </button>
              ))}
            </div>

            {/* Valor */}
            {seg.type === "static" ? (
              <input
                type="text"
                className="input w-full text-sm"
                placeholder='Ej: "$", "X", "Precio:"'
                value={seg.value}
                onChange={(e) => updateSeg(idx, { value: e.target.value })}
              />
            ) : (
              <select
                className="input w-full text-sm"
                value={seg.value}
                onChange={(e) => updateSeg(idx, { value: e.target.value })}
              >
                <option value="">— Seleccionar variable —</option>
                {variables.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.name} ({v.csv_column})
                  </option>
                ))}
              </select>
            )}

            {/* Transformación (solo para variable) */}
            {seg.type === "variable" && (
              <select
                className="input w-full text-xs"
                value={seg.transform ?? "none"}
                onChange={(e) => updateSeg(idx, { transform: e.target.value as TextTransform })}
              >
                {TRANSFORMS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            )}

            {/* Estilos del segmento */}
            <div className="grid grid-cols-2 gap-1.5">
              <label className="flex flex-col gap-0.5">
                <span className="text-[9px] text-slate-400 uppercase">Tamaño (pt)</span>
                <input
                  type="number"
                  min={6}
                  max={400}
                  className="input text-xs"
                  placeholder="Hereda"
                  value={seg.style?.font_size ?? ""}
                  onChange={(e) =>
                    updateSegStyle(idx, "font_size", e.target.value ? parseInt(e.target.value) : undefined)
                  }
                />
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="text-[9px] text-slate-400 uppercase">Color</span>
                <div className="flex gap-1">
                  <input
                    type="color"
                    className="w-7 h-8 rounded border border-slate-200 cursor-pointer p-0.5 shrink-0"
                    value={seg.style?.color ?? "#1e293b"}
                    onChange={(e) => updateSegStyle(idx, "color", e.target.value)}
                  />
                  <input
                    type="text"
                    className="input text-xs flex-1 min-w-0"
                    placeholder="Hereda"
                    value={seg.style?.color ?? ""}
                    onChange={(e) => updateSegStyle(idx, "color", e.target.value || undefined)}
                  />
                </div>
              </label>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="rounded text-brand-600"
                checked={!!seg.style?.font_bold}
                onChange={(e) =>
                  updateSegStyle(idx, "font_bold", e.target.checked ? true : undefined)
                }
              />
              <span className="text-xs text-slate-600">Negrita</span>
              {seg.style?.font_bold === undefined && (
                <span className="text-[9px] text-slate-400">(hereda del estilo base)</span>
              )}
            </label>
          </div>
        </div>
      ))}

      <button
        onClick={addSeg}
        className="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-brand-600 border border-dashed border-brand-300 rounded-lg hover:bg-brand-50 transition-colors"
      >
        <Plus size={12} /> Agregar segmento
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Format overrides por formato no-master
// ---------------------------------------------------------------------------

function FormatOverridesSection({
  comp,
  updateComponent,
  template,
}: {
  comp: CenefaComponent;
  updateComponent: (id: string, updates: Partial<CenefaComponent>) => void;
  template: CenefaTemplate;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const nonMaster = template.formats.filter((f) => f !== template.master_format);

  function setOverride(fmt: string, key: string, value: number | undefined) {
    const current = comp.format_overrides[fmt] ?? {};
    const updated  = value === undefined
      ? Object.fromEntries(Object.entries(current).filter(([k]) => k !== key))
      : { ...current, [key]: value };
    updateComponent(comp.id, {
      format_overrides: { ...comp.format_overrides, [fmt]: updated },
    });
  }

  return (
    <Section label="Overrides por formato">
      <div className="space-y-2">
        {nonMaster.map((fmt) => {
          const ov = comp.format_overrides[fmt] ?? {};
          const isOpen = open === fmt;
          return (
            <div key={fmt} className="border border-slate-200 rounded-lg overflow-hidden">
              <button
                onClick={() => setOpen(isOpen ? null : fmt)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                <span>{fmt.toUpperCase()}</span>
                <span className="text-slate-400">
                  {Object.keys(ov).length > 0
                    ? `${Object.keys(ov).length} override${Object.keys(ov).length > 1 ? "s" : ""}`
                    : "heredado"}
                </span>
              </button>
              {isOpen && (
                <div className="px-3 pb-3 pt-1 bg-slate-50 grid grid-cols-2 gap-2">
                  {(["x", "y", "width", "height"] as const).map((k) => (
                    <label key={k} className="flex flex-col gap-1">
                      <span className="text-[10px] text-slate-400 uppercase">{k}</span>
                      <input
                        type="number"
                        step="0.1"
                        placeholder={String(+(comp.base_bounds[k] * 1).toFixed(1))}
                        className="input text-xs"
                        value={ov[k] !== undefined ? ov[k] : ""}
                        onChange={(e) =>
                          setOverride(fmt, k, e.target.value === "" ? undefined : parseFloat(e.target.value))
                        }
                      />
                    </label>
                  ))}
                  <label className="flex flex-col gap-1 col-span-2">
                    <span className="text-[10px] text-slate-400 uppercase">Font size (pt)</span>
                    <input
                      type="number"
                      step="1"
                      placeholder={String(comp.style.font_size ?? "")}
                      className="input text-xs w-24"
                      value={ov.font_size !== undefined ? ov.font_size : ""}
                      onChange={(e) =>
                        setOverride(fmt, "font_size", e.target.value === "" ? undefined : parseInt(e.target.value))
                      }
                    />
                  </label>
                  {Object.keys(ov).length > 0 && (
                    <button
                      onClick={() =>
                        updateComponent(comp.id, {
                          format_overrides: {
                            ...comp.format_overrides,
                            [fmt]: {},
                          },
                        })
                      }
                      className="col-span-2 text-[10px] text-rose-500 hover:text-rose-700 text-left"
                    >
                      Limpiar overrides para {fmt}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}
