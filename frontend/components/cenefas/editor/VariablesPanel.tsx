"use client";
import { useState } from "react";
import { useEditorStore } from "@/store/editor";
import type { CenefaVariable } from "@/types/cenefas";
import { Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react";

const VAR_TYPES: { value: CenefaVariable["type"]; label: string }[] = [
  { value: "text",      label: "Texto" },
  { value: "price",     label: "Precio" },
  { value: "number",    label: "Número" },
  { value: "image_url", label: "URL imagen" },
  { value: "boolean",   label: "Booleano" },
];

const TYPE_COLORS: Record<string, string> = {
  text:      "bg-blue-100 text-blue-700",
  price:     "bg-emerald-100 text-emerald-700",
  number:    "bg-violet-100 text-violet-700",
  image_url: "bg-amber-100 text-amber-700",
  boolean:   "bg-rose-100 text-rose-700",
};

export default function VariablesPanel() {
  const { template, upsertVariable, deleteVariable } = useEditorStore();
  const [showForm, setShowForm]   = useState(false);
  const [editName, setEditName]   = useState<string | null>(null);

  // Form state
  const [name,      setName]      = useState("");
  const [type,      setType]      = useState<CenefaVariable["type"]>("text");
  const [required,  setRequired]  = useState(false);
  const [csvColumn, setCsvColumn] = useState("");

  function resetForm() {
    setName(""); setType("text"); setRequired(false); setCsvColumn("");
    setEditName(null); setShowForm(false);
  }

  function handleEdit(v: CenefaVariable) {
    setName(v.name); setType(v.type); setRequired(v.required); setCsvColumn(v.csv_column);
    setEditName(v.name); setShowForm(true);
  }

  function handleSave() {
    const n = name.trim();
    if (!n || !csvColumn.trim()) return;
    upsertVariable({ name: n, type, required, csv_column: csvColumn.trim() });
    resetForm();
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-slate-100 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-500">
          Variables ({template.variables.length})
        </p>
        <button
          onClick={() => { resetForm(); setShowForm((v) => !v); }}
          className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium"
        >
          <Plus size={12} /> Agregar
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Formulario */}
        {showForm && (
          <div className="p-3 border-b border-brand-100 bg-brand-50/30 space-y-2.5">
            <p className="text-[10px] font-semibold text-brand-600 uppercase tracking-wide">
              {editName ? "Editar variable" : "Nueva variable"}
            </p>
            <input
              className="input w-full text-sm"
              placeholder="Nombre interno (ej: marca)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!!editName}
            />
            <input
              className="input w-full text-sm"
              placeholder="Columna del CSV (ej: MARCA)"
              value={csvColumn}
              onChange={(e) => setCsvColumn(e.target.value)}
            />
            <div className="flex gap-2">
              <select
                className="input text-sm flex-1"
                value={type}
                onChange={(e) => setType(e.target.value as CenefaVariable["type"])}
              >
                {VAR_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={required}
                  onChange={(e) => setRequired(e.target.checked)}
                  className="rounded"
                />
                Requerida
              </label>
            </div>
            <div className="flex gap-2">
              <button onClick={handleSave} className="btn-primary text-xs px-3 py-1.5">
                {editName ? "Guardar" : "Agregar"}
              </button>
              <button onClick={resetForm} className="btn-secondary text-xs px-3 py-1.5">
                Cancelar
              </button>
            </div>
          </div>
        )}

        {/* Lista */}
        {template.variables.length === 0 && !showForm && (
          <div className="p-6 text-center">
            <p className="text-sm text-slate-400">Sin variables</p>
            <p className="text-xs text-slate-400 mt-1">
              Las variables conectan componentes con columnas del CSV
            </p>
          </div>
        )}

        <div className="p-2 space-y-1">
          {template.variables.map((v) => (
            <div
              key={v.name}
              className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-slate-50 group cursor-pointer"
              onClick={() => handleEdit(v)}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-700">{v.name}</span>
                  {v.required && (
                    <span className="text-[9px] text-rose-500 font-bold">*</span>
                  )}
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${TYPE_COLORS[v.type] ?? "bg-slate-100 text-slate-500"}`}>
                    {v.type}
                  </span>
                </div>
                <p className="text-[10px] text-slate-400 font-mono mt-0.5">{v.csv_column}</p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); deleteVariable(v.name); }}
                className="p-1 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                title="Eliminar variable"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
