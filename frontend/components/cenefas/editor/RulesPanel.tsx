"use client";
import { useState } from "react";
import { useEditorStore } from "@/store/editor";
import type { CenefaRule, RuleOperator, RuleAction } from "@/types/cenefas";
import { Plus, Trash2, ChevronDown, ChevronRight } from "lucide-react";

export const OPERATORS: { value: RuleOperator; label: string }[] = [
  { value: "equals",       label: "es igual a" },
  { value: "not_equals",   label: "es distinto de" },
  { value: "greater_than", label: "es mayor que" },
  { value: "less_than",    label: "es menor que" },
  { value: "contains",     label: "contiene" },
  { value: "is_empty",     label: "está vacío" },
  { value: "is_not_empty", label: "tiene valor" },
];

export const NEEDS_VALUE: RuleOperator[] = [
  "equals", "not_equals", "greater_than", "less_than", "contains",
];

// Opciones simplificadas para el formulario amigable
const SIMPLE_CONDITIONS = [
  { value: "is_not_empty", label: "Sí tiene valor",  emoji: "✓" },
  { value: "is_empty",     label: "No tiene valor",   emoji: "✗" },
  { value: "equals",       label: "Es igual a…",      emoji: "=" },
] as const;

// ---------------------------------------------------------------------------
// Panel principal — vista agrupada por componente
// ---------------------------------------------------------------------------

export default function RulesPanel() {
  const { template, addRule, deleteRule, selectComponent } = useEditorStore();
  const [expanded, setExpanded]   = useState<string | null>(null);
  const [addingFor, setAddingFor] = useState<string | null>(null);

  const rulesFor = (compId: string) =>
    template.rules.filter((r) => r.target_component_id === compId);

  function handleAdd(compId: string, rule: CenefaRule) {
    addRule(rule);
    setAddingFor(null);
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-slate-100">
        <p className="text-xs font-semibold text-slate-500">
          Reglas de visibilidad
        </p>
        <p className="text-[10px] text-slate-400 mt-0.5">
          Controlá qué elementos se muestran según los datos del CSV
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {template.components.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm text-slate-400">Sin componentes</p>
            <p className="text-xs text-slate-400 mt-1">
              Agregá componentes primero para definir reglas
            </p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {[...template.components]
              .sort((a, b) => a.z_index - b.z_index)
              .map((comp) => {
                const rules   = rulesFor(comp.id);
                const isOpen  = expanded === comp.id;
                const isAdding = addingFor === comp.id;

                return (
                  <div key={comp.id} className="rounded-lg border border-slate-100 overflow-hidden">
                    {/* Header del componente */}
                    <button
                      onClick={() => {
                        setExpanded(isOpen ? null : comp.id);
                        selectComponent(comp.id);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 transition-colors"
                    >
                      {isOpen
                        ? <ChevronDown size={12} className="text-slate-400 flex-shrink-0" />
                        : <ChevronRight size={12} className="text-slate-400 flex-shrink-0" />
                      }
                      <span className="flex-1 text-xs font-medium text-slate-700 truncate">
                        {comp.name}
                      </span>
                      {rules.length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-brand-100 text-brand-600 rounded-full font-medium flex-shrink-0">
                          {rules.length}
                        </span>
                      )}
                    </button>

                    {/* Reglas del componente */}
                    {isOpen && (
                      <div className="border-t border-slate-100 bg-slate-50/50">
                        {rules.length === 0 && !isAdding && (
                          <p className="px-4 py-2 text-[10px] text-slate-400">
                            Sin reglas — el elemento siempre se muestra
                          </p>
                        )}
                        {rules.map((rule) => (
                          <RuleChip
                            key={rule.id}
                            rule={rule}
                            onDelete={() => deleteRule(rule.id)}
                          />
                        ))}

                        {/* Formulario inline */}
                        {isAdding ? (
                          <div className="p-3 border-t border-slate-100">
                            <RuleForm
                              componentId={comp.id}
                              variables={template.variables}
                              onSave={(rule) => handleAdd(comp.id, rule)}
                              onCancel={() => setAddingFor(null)}
                            />
                          </div>
                        ) : (
                          <button
                            onClick={() => setAddingFor(comp.id)}
                            className="flex items-center gap-1.5 w-full px-4 py-2 text-[10px] text-brand-600 hover:text-brand-700 hover:bg-brand-50 transition-colors border-t border-slate-100"
                          >
                            <Plus size={10} /> Agregar regla
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chip de regla individual
// ---------------------------------------------------------------------------

export function RuleChip({
  rule,
  onDelete,
}: {
  rule: CenefaRule;
  onDelete: () => void;
}) {
  const cond = rule.condition as {
    field?: string; operator?: string; value?: string | number;
  };
  const action        = rule.action.type;
  const operatorLabel = OPERATORS.find((o) => o.value === cond.operator)?.label ?? cond.operator ?? "";
  const valueStr      = NEEDS_VALUE.includes(cond.operator as RuleOperator) ? ` "${cond.value}"` : "";
  const summary       = `${cond.field ?? ""} ${operatorLabel}${valueStr}`;

  return (
    <div className="flex items-center gap-2 px-4 py-2 group hover:bg-white/60 transition-colors">
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        action === "show" ? "bg-emerald-400" : "bg-rose-400"
      }`} />
      <div className="flex-1 min-w-0">
        <span className={`text-[10px] font-semibold ${
          action === "show" ? "text-emerald-600" : "text-rose-600"
        }`}>
          {action === "show" ? "Mostrar" : "Ocultar"}
        </span>
        <span className="text-[10px] text-slate-500 ml-1 italic">{summary}</span>
      </div>
      <button
        onClick={onDelete}
        className="p-0.5 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 flex-shrink-0"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formulario de nueva regla (reutilizable desde PropertiesPanel)
// ---------------------------------------------------------------------------

export function RuleForm({
  componentId,
  variables,
  onSave,
  onCancel,
}: {
  componentId: string;
  variables:   { name: string; csv_column: string }[];
  onSave:      (rule: CenefaRule) => void;
  onCancel:    () => void;
}) {
  const [action,     setAction]     = useState<RuleAction>("show");
  const [fieldSrc,   setFieldSrc]   = useState<"variable" | "custom">(variables.length > 0 ? "variable" : "custom");
  const [field,      setField]      = useState(variables[0]?.name ?? "");
  const [customCol,  setCustomCol]  = useState("");
  const [operator,   setOperator]   = useState<RuleOperator>("is_not_empty");
  const [value,      setValue]      = useState("");

  const effectiveField  = fieldSrc === "custom" ? customCol.trim().toUpperCase() : field;
  const actionLabel     = action === "show" ? "Mostrar" : "Ocultar";
  const operatorLabel   = OPERATORS.find((o) => o.value === operator)?.label ?? "";
  const autoName        = `${actionLabel} si ${effectiveField} ${operatorLabel}`;

  function handleSave() {
    if (!effectiveField) return;
    const condition = NEEDS_VALUE.includes(operator)
      ? { field: effectiveField, operator, value }
      : { field: effectiveField, operator };

    onSave({
      id:                  crypto.randomUUID(),
      name:                autoName,
      target_component_id: componentId,
      condition:           condition as CenefaRule["condition"],
      action:              { type: action },
    });
  }

  return (
    <div className="space-y-3">
      {/* Paso 1: Acción */}
      <div>
        <p className="text-[10px] font-semibold text-slate-400 uppercase mb-1.5">¿Qué hace?</p>
        <div className="flex gap-2">
          {(["show", "hide"] as RuleAction[]).map((a) => (
            <button
              key={a}
              onClick={() => setAction(a)}
              className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                action === a
                  ? a === "show"
                    ? "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300"
                    : "bg-rose-100 text-rose-700 ring-1 ring-rose-300"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200"
              }`}
            >
              {a === "show" ? "Mostrar" : "Ocultar"}
            </button>
          ))}
        </div>
      </div>

      {/* Paso 2: Campo — variable de plantilla o columna de Excel */}
      <div>
        <p className="text-[10px] font-semibold text-slate-400 uppercase mb-1.5">¿Cuándo? Según…</p>
        <div className="flex gap-1 mb-2">
          {variables.length > 0 && (
            <button
              onClick={() => setFieldSrc("variable")}
              className={`flex-1 py-1 rounded text-[10px] font-medium transition-all ${
                fieldSrc === "variable"
                  ? "bg-brand-100 text-brand-700 ring-1 ring-brand-300"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200"
              }`}
            >
              Variable de plantilla
            </button>
          )}
          <button
            onClick={() => setFieldSrc("custom")}
            className={`flex-1 py-1 rounded text-[10px] font-medium transition-all ${
              fieldSrc === "custom"
                ? "bg-amber-100 text-amber-700 ring-1 ring-amber-300"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
          >
            Columna del Excel
          </button>
        </div>

        {fieldSrc === "variable" && variables.length > 0 ? (
          <select
            className="input text-xs w-full"
            value={field}
            onChange={(e) => setField(e.target.value)}
          >
            {variables.map((v) => (
              <option key={v.name} value={v.name}>{v.name} ({v.csv_column})</option>
            ))}
          </select>
        ) : (
          <input
            className="input text-xs w-full"
            placeholder="Ej: DESCUENTO 20"
            value={customCol}
            onChange={(e) => setCustomCol(e.target.value)}
          />
        )}
        {fieldSrc === "custom" && (
          <p className="text-[10px] text-slate-400 mt-1">
            Escribí el nombre exacto de la columna en el Excel (sin tildes).
          </p>
        )}
      </div>

      {/* Paso 3: Condición simplificada */}
      <div>
        <p className="text-[10px] font-semibold text-slate-400 uppercase mb-1.5">¿Bajo qué condición?</p>
        <div className="flex gap-2 flex-wrap">
          {SIMPLE_CONDITIONS.map((c) => (
            <button
              key={c.value}
              onClick={() => { setOperator(c.value as RuleOperator); if (c.value !== "equals") setValue(""); }}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                operator === c.value
                  ? "bg-brand-100 text-brand-700 ring-1 ring-brand-300"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200"
              }`}
            >
              {c.emoji} {c.label}
            </button>
          ))}
        </div>
        {operator === "equals" && (
          <input
            className="input w-full text-xs mt-2"
            placeholder="Escribí el valor exacto…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
      </div>

      {/* Preview */}
      <p className="text-[10px] text-slate-400 italic bg-slate-50 rounded px-2 py-1.5 truncate">
        → {autoName}
      </p>

      <div className="flex gap-1.5">
        <button onClick={handleSave} className="btn-primary text-xs px-2.5 py-1">Guardar</button>
        <button onClick={onCancel} className="btn-secondary text-xs px-2.5 py-1">Cancelar</button>
      </div>
    </div>
  );
}
