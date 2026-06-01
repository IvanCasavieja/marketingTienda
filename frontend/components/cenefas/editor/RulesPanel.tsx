"use client";
import { useState } from "react";
import { useEditorStore } from "@/store/editor";
import type { CenefaRule, RuleOperator, RuleAction } from "@/types/cenefas";
import { Plus, Trash2, Eye, EyeOff, ChevronDown, ChevronUp } from "lucide-react";

const OPERATORS: { value: RuleOperator; label: string }[] = [
  { value: "equals",       label: "es igual a" },
  { value: "not_equals",   label: "es distinto de" },
  { value: "greater_than", label: "es mayor que" },
  { value: "less_than",    label: "es menor que" },
  { value: "contains",     label: "contiene" },
  { value: "is_empty",     label: "está vacío" },
  { value: "is_not_empty", label: "tiene valor" },
];

const NEEDS_VALUE: RuleOperator[] = [
  "equals", "not_equals", "greater_than", "less_than", "contains",
];

// ---------------------------------------------------------------------------
// Panel principal
// ---------------------------------------------------------------------------

export default function RulesPanel() {
  const { template, addRule, deleteRule } = useEditorStore();
  const [showForm, setShowForm] = useState(false);

  function handleAdd(rule: CenefaRule) {
    addRule(rule);
    setShowForm(false);
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-slate-100 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-500">
          Reglas ({template.rules.length})
        </p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium"
        >
          <Plus size={12} />
          Agregar
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Formulario nueva regla */}
        {showForm && (
          <div className="p-3 border-b border-brand-100 bg-brand-50/30">
            <RuleForm
              components={template.components}
              variables={template.variables}
              onSave={handleAdd}
              onCancel={() => setShowForm(false)}
            />
          </div>
        )}

        {/* Lista de reglas */}
        {template.rules.length === 0 && !showForm && (
          <div className="p-6 text-center">
            <p className="text-sm text-slate-400">Sin reglas definidas</p>
            <p className="text-xs text-slate-400 mt-1">
              Las reglas controlan qué componentes se muestran según los datos del CSV
            </p>
          </div>
        )}

        <div className="p-2 space-y-1">
          {template.rules.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              componentName={
                template.components.find((c) => c.id === rule.target_component_id)
                  ?.name ?? rule.target_component_id
              }
              onDelete={() => deleteRule(rule.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fila de regla existente
// ---------------------------------------------------------------------------

function RuleRow({
  rule,
  componentName,
  onDelete,
}: {
  rule: CenefaRule;
  componentName: string;
  onDelete: () => void;
}) {
  const cond = rule.condition as {
    field?: string;
    operator?: string;
    value?: string | number;
  };
  const action = rule.action.type;

  const operatorLabel =
    OPERATORS.find((o) => o.value === cond.operator)?.label ?? cond.operator ?? "";
  const valueStr =
    NEEDS_VALUE.includes(cond.operator as RuleOperator) ? ` "${cond.value}"` : "";
  const summary = `${cond.field ?? ""} ${operatorLabel}${valueStr}`;

  return (
    <div className="flex items-start gap-2 px-2 py-2 rounded-lg hover:bg-slate-50 group">
      <span
        className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
          action === "show" ? "bg-emerald-400" : "bg-rose-400"
        }`}
      />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-slate-700 truncate">{rule.name}</p>
        <p className="text-[10px] text-slate-400 mt-0.5 leading-snug">
          <span
            className={`font-medium ${
              action === "show" ? "text-emerald-600" : "text-rose-600"
            }`}
          >
            {action === "show" ? "Mostrar" : "Ocultar"}
          </span>{" "}
          <span className="text-brand-600">{componentName}</span>
          {" si "}
          <span className="italic">{summary}</span>
        </p>
      </div>
      <button
        onClick={onDelete}
        className="p-1 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 flex-shrink-0"
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formulario de nueva regla
// ---------------------------------------------------------------------------

function RuleForm({
  components,
  variables,
  onSave,
  onCancel,
}: {
  components: { id: string; name: string }[];
  variables: { name: string; csv_column: string }[];
  onSave: (rule: CenefaRule) => void;
  onCancel: () => void;
}) {
  const [name,        setName]        = useState("Nueva regla");
  const [targetId,    setTargetId]    = useState(components[0]?.id ?? "");
  const [action,      setAction]      = useState<RuleAction>("show");
  const [field,       setField]       = useState(variables[0]?.name ?? "");
  const [operator,    setOperator]    = useState<RuleOperator>("equals");
  const [value,       setValue]       = useState("");

  function handleSave() {
    if (!targetId || !field) return;
    const condition = NEEDS_VALUE.includes(operator)
      ? { field, operator, value }
      : { field, operator };

    onSave({
      id:                  crypto.randomUUID(),
      name,
      target_component_id: targetId,
      condition:           condition as CenefaRule["condition"],
      action:              { type: action },
    });
  }

  return (
    <div className="space-y-3">
      <input
        className="input w-full text-sm"
        placeholder="Nombre de la regla"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />

      {/* Acción + Componente */}
      <div className="flex gap-2">
        <select
          className="input text-sm flex-shrink-0"
          value={action}
          onChange={(e) => setAction(e.target.value as RuleAction)}
        >
          <option value="show">Mostrar</option>
          <option value="hide">Ocultar</option>
        </select>
        <select
          className="input text-sm flex-1"
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
        >
          {components.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {/* Condición */}
      <div className="text-xs text-slate-500 font-medium">si…</div>
      <div className="grid grid-cols-2 gap-2">
        <select
          className="input text-sm"
          value={field}
          onChange={(e) => setField(e.target.value)}
        >
          {variables.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name}
            </option>
          ))}
        </select>
        <select
          className="input text-sm"
          value={operator}
          onChange={(e) => setOperator(e.target.value as RuleOperator)}
        >
          {OPERATORS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {NEEDS_VALUE.includes(operator) && (
        <input
          className="input w-full text-sm"
          placeholder="Valor"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      )}

      {/* Acciones */}
      <div className="flex gap-2 pt-1">
        <button onClick={handleSave} className="btn-primary text-xs px-3 py-1.5">
          Agregar regla
        </button>
        <button onClick={onCancel} className="btn-secondary text-xs px-3 py-1.5">
          Cancelar
        </button>
      </div>
    </div>
  );
}
