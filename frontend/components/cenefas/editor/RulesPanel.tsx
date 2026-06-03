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
  const [action,   setAction]   = useState<RuleAction>("show");
  const [field,    setField]    = useState(variables[0]?.name ?? "");
  const [operator, setOperator] = useState<RuleOperator>("is_not_empty");
  const [value,    setValue]    = useState("");

  const actionLabel     = action === "show" ? "Mostrar" : "Ocultar";
  const operatorLabel   = OPERATORS.find((o) => o.value === operator)?.label ?? "";
  const autoName        = `${actionLabel} si ${field} ${operatorLabel}`;

  function handleSave() {
    if (!field) return;
    const condition = NEEDS_VALUE.includes(operator)
      ? { field, operator, value }
      : { field, operator };

    onSave({
      id:                  crypto.randomUUID(),
      name:                autoName,
      target_component_id: componentId,
      condition:           condition as CenefaRule["condition"],
      action:              { type: action },
    });
  }

  if (variables.length === 0) {
    return (
      <p className="text-[10px] text-slate-400 italic">
        Primero agregá variables en la pestaña Variables
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {/* Acción */}
      <div className="flex gap-2">
        <select
          className="input text-xs flex-shrink-0 w-24"
          value={action}
          onChange={(e) => setAction(e.target.value as RuleAction)}
        >
          <option value="show">Mostrar</option>
          <option value="hide">Ocultar</option>
        </select>
        <span className="text-[10px] text-slate-400 self-center">este elemento si…</span>
      </div>

      {/* Condición */}
      <div className="flex gap-1.5 flex-wrap">
        <select
          className="input text-xs flex-1 min-w-0"
          value={field}
          onChange={(e) => setField(e.target.value)}
        >
          {variables.map((v) => (
            <option key={v.name} value={v.name}>{v.name}</option>
          ))}
        </select>
        <select
          className="input text-xs flex-1 min-w-0"
          value={operator}
          onChange={(e) => setOperator(e.target.value as RuleOperator)}
        >
          {OPERATORS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {NEEDS_VALUE.includes(operator) && (
        <input
          className="input w-full text-xs"
          placeholder="Valor a comparar"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      )}

      {/* Preview del nombre auto-generado */}
      <p className="text-[10px] text-slate-400 italic truncate">→ {autoName}</p>

      <div className="flex gap-1.5">
        <button onClick={handleSave} className="btn-primary text-xs px-2.5 py-1">
          Guardar
        </button>
        <button onClick={onCancel} className="btn-secondary text-xs px-2.5 py-1">
          Cancelar
        </button>
      </div>
    </div>
  );
}
