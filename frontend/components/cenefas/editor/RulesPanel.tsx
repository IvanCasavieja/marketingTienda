"use client";
import { useState } from "react";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent, CenefaRule, RuleOperator, RuleAction, TextSegment } from "@/types/cenefas";
import { Plus, Trash2, ChevronDown, ChevronRight, Layers } from "lucide-react";

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

// Opciones simplificadas para el formulario amigable.
//
// "Contiene…" se agregó el 08/09/2026: es lo que permite preguntar si la
// cenefa es de una categoría unificada, porque una fila unificada queda con el
// código combinado ("580735 - 590183", lo arma commitUnificacion con
// skus.join(" - ")). Sin este operador el caso no se podía escribir, aunque el
// motor de reglas ya lo soportaba.
const SIMPLE_CONDITIONS = [
  { value: "is_not_empty", label: "Sí tiene valor",  emoji: "✓" },
  { value: "is_empty",     label: "No tiene valor",   emoji: "✗" },
  { value: "equals",       label: "Es igual a…",      emoji: "=" },
  { value: "contains",     label: "Contiene…",        emoji: "⊂" },
] as const;

// ---------------------------------------------------------------------------
// Panel principal — vista agrupada por componente
// ---------------------------------------------------------------------------

interface RulesPanelProps {
  /** Mismo patrón que PropertiesPanel.tsx: sin props explícitas cae al
   * store global del editor completo (/materiales/cenefas/v2).
   * LotePreviewStep/PreviewStep pasan las suyas propias para reusar este
   * panel apuntando al template_def de LA CENEFA QUE SE ESTÁ MIRANDO, que
   * vive en estado local, no en el store. */
  components?: CenefaComponent[];
  rules?: CenefaRule[];
  variables?: { name: string; csv_column: string }[];
  addRule?: (rule: CenefaRule) => void;
  deleteRule?: (id: string) => void;
  selectComponent?: (id: string) => void;
  /** Cuadros marcados en el canvas con Ctrl + click. Con más de uno aparece
   *  el formulario para ponerles la misma regla a todos de una. */
  selectedComponentIds?: string[];
}

export default function RulesPanel(props: RulesPanelProps = {}) {
  const store = useEditorStore();
  const components     = props.components ?? store.template.components;
  const allRules        = props.rules ?? store.template.rules;
  const variables      = props.variables ?? store.template.variables;
  const addRule        = props.addRule ?? store.addRule;
  const deleteRule     = props.deleteRule ?? store.deleteRule;
  const selectComponent = props.selectComponent ?? store.selectComponent;
  const selectedIds    = props.selectedComponentIds ?? store.selectedComponentIds;
  const [expanded, setExpanded]   = useState<string | null>(null);
  const [addingFor, setAddingFor] = useState<string | null>(null);
  const [addingLote, setAddingLote] = useState(false);

  const rulesFor = (compId: string) =>
    allRules.filter((r) => r.target_component_id === compId);

  // Solo los que existen de verdad y en el orden en que se ven en el panel:
  // la selección puede arrastrar ids de un componente borrado.
  const seleccionados = components.filter((c) => selectedIds.includes(c.id));
  const enLote = seleccionados.length > 1;

  function handleAdd(compId: string, rule: CenefaRule) {
    addRule(rule);
    setAddingFor(null);
  }

  // Una regla por cuadro seleccionado: el modelo ata cada regla a UN
  // target_component_id, así que "la misma regla para varios" son N reglas
  // iguales con distinto destino. Se ven después en la fila de cada cuadro y
  // se borran de a una, como cualquier otra.
  function handleAddEnLote(rule: CenefaRule) {
    for (const comp of seleccionados) {
      addRule({ ...rule, id: crypto.randomUUID(), target_component_id: comp.id });
    }
    setAddingLote(false);
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-slate-100 dark:border-slate-800">
        <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
          Reglas de visibilidad
        </p>
        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
          Controlá qué elementos se muestran según los datos del CSV
        </p>
        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
          Ctrl + click en el canvas para marcar varios y darles la misma regla.
        </p>
      </div>

      {/* Barra de selección múltiple — solo con más de un cuadro marcado. */}
      {enLote && (
        <div className="border-b border-brand-200 dark:border-brand-900 bg-brand-50/70 dark:bg-brand-950/30">
          <div className="px-3 py-2">
            <div className="flex items-center gap-2">
              <Layers size={12} className="text-brand-600 dark:text-brand-400 flex-shrink-0" />
              <p className="text-xs font-semibold text-brand-700 dark:text-brand-300 flex-1">
                {seleccionados.length} cuadros seleccionados
              </p>
            </div>
            <p className="text-[10px] text-brand-600/80 dark:text-brand-400/80 mt-1 leading-relaxed">
              {seleccionados.map((c) => c.name).join(" · ")}
            </p>

            {addingLote ? (
              <div className="mt-2.5 rounded-lg bg-white dark:bg-slate-900 border border-brand-200 dark:border-brand-900 p-3">
                <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase mb-2">
                  Misma regla para los {seleccionados.length}
                </p>
                <RuleForm
                  componentId={seleccionados[0].id}
                  variables={variables}
                  onSave={handleAddEnLote}
                  onCancel={() => setAddingLote(false)}
                />
              </div>
            ) : (
              <button
                onClick={() => setAddingLote(true)}
                className="mt-2 flex items-center justify-center gap-1.5 w-full py-1.5 rounded-lg text-[10px] font-semibold bg-brand-600 text-white hover:bg-brand-700 transition-colors"
              >
                <Plus size={10} /> Misma regla para los {seleccionados.length}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {components.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm text-slate-400 dark:text-slate-500">Sin componentes</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              Agregá componentes primero para definir reglas
            </p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {[...components]
              .sort((a, b) => a.z_index - b.z_index)
              .map((comp) => {
                const rules   = rulesFor(comp.id);
                const isOpen  = expanded === comp.id;
                const isAdding = addingFor === comp.id;
                const marcado = selectedIds.includes(comp.id);

                return (
                  <div
                    key={comp.id}
                    className={`rounded-lg border overflow-hidden ${
                      marcado
                        ? "border-brand-300 dark:border-brand-800 ring-1 ring-brand-200 dark:ring-brand-900"
                        : "border-slate-100 dark:border-slate-800"
                    }`}
                  >
                    {/* Header del componente */}
                    <button
                      onClick={() => {
                        setExpanded(isOpen ? null : comp.id);
                        selectComponent(comp.id);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                    >
                      {isOpen
                        ? <ChevronDown size={12} className="text-slate-400 dark:text-slate-500 flex-shrink-0" />
                        : <ChevronRight size={12} className="text-slate-400 dark:text-slate-500 flex-shrink-0" />
                      }
                      <span className="flex-1 text-xs font-medium text-slate-700 dark:text-slate-200 truncate">
                        {comp.name}
                      </span>
                      {rules.length > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 bg-brand-100 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 rounded-full font-medium flex-shrink-0">
                          {rules.length}
                        </span>
                      )}
                    </button>

                    {/* Reglas del componente */}
                    {isOpen && (
                      <div className="border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
                        {rules.length === 0 && !isAdding && (
                          <p className="px-4 py-2 text-[10px] text-slate-400 dark:text-slate-500">
                            Sin reglas — el elemento siempre se muestra
                          </p>
                        )}
                        {rules.map((rule) => (
                          <RuleChip
                            key={rule.id}
                            rule={rule}
                            segments={comp.segments}
                            onDelete={() => deleteRule(rule.id)}
                          />
                        ))}

                        {/* Formulario inline */}
                        {isAdding ? (
                          <div className="p-3 border-t border-slate-100 dark:border-slate-800">
                            <RuleForm
                              componentId={comp.id}
                              variables={variables}
                              segments={comp.segments}
                              onSave={(rule) => handleAdd(comp.id, rule)}
                              onCancel={() => setAddingFor(null)}
                            />
                          </div>
                        ) : (
                          <button
                            onClick={() => setAddingFor(comp.id)}
                            className="flex items-center gap-1.5 w-full px-4 py-2 text-[10px] text-brand-600 dark:text-brand-400 hover:text-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 transition-colors border-t border-slate-100 dark:border-slate-800"
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
  segments,
  onDelete,
}: {
  rule: CenefaRule;
  /** Segmentos del cuadro, para poder nombrar a cuál apunta la regla. */
  segments?: TextSegment[];
  onDelete: () => void;
}) {
  const cond = rule.condition as {
    field?: string; operator?: string; value?: string | number;
  };
  const action        = rule.action.type;
  const operatorLabel = OPERATORS.find((o) => o.value === cond.operator)?.label ?? cond.operator ?? "";
  const valueStr      = NEEDS_VALUE.includes(cond.operator as RuleOperator) ? ` "${cond.value}"` : "";
  const summary       = `${cond.field ?? ""} ${operatorLabel}${valueStr}`;
  // Sin esto, dos reglas del mismo cuadro que apuntan a pedazos distintos se
  // ven idénticas en la lista.
  const seg = rule.target_segment_index;
  const segLabel = seg !== undefined && segments?.[seg]
    ? etiquetaDeSegmento(segments[seg])
    : null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 group hover:bg-white/60 dark:hover:bg-white/5 transition-colors">
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        action === "show" ? "bg-emerald-400" : "bg-rose-400"
      }`} />
      <div className="flex-1 min-w-0">
        <span className={`text-[10px] font-semibold ${
          action === "show" ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
        }`}>
          {action === "show" ? "Mostrar" : "Ocultar"}
        </span>
        {segLabel && (
          <span className="text-[10px] font-mono text-brand-600 dark:text-brand-400 ml-1">
            {segLabel}
          </span>
        )}
        <span className="text-[10px] text-slate-500 dark:text-slate-400 ml-1 italic">{summary}</span>
      </div>
      <button
        onClick={onDelete}
        className="p-0.5 text-slate-300 dark:text-slate-600 hover:text-red-500 opacity-0 group-hover:opacity-100 flex-shrink-0"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formulario de nueva regla (reutilizable desde PropertiesPanel)
// ---------------------------------------------------------------------------

/**
 * Cómo se nombra un segmento en pantalla. Un texto compuesto se ve como un
 * solo renglón, así que para elegir "a cuál de los pedazos" hay que mostrar
 * su contenido: la variable con sus `<< >>` (que es como está escrita en la
 * plantilla) y el texto fijo entre comillas.
 */
export function etiquetaDeSegmento(seg: TextSegment): string {
  if (seg.type === "variable") return `<<${seg.value}>>`;
  const fijo = seg.value ?? "";
  return fijo.trim() ? `"${fijo}"` : `(espacio)`;
}

export function RuleForm({
  componentId,
  variables,
  segments,
  onSave,
  onCancel,
}: {
  componentId: string;
  variables:   { name: string; csv_column: string }[];
  /** Segmentos del cuadro, si es de texto compuesto: habilita apuntar la
   *  regla a UNO solo en vez de a todo el cuadro. */
  segments?:   TextSegment[];
  onSave:      (rule: CenefaRule) => void;
  onCancel:    () => void;
}) {
  const [action,     setAction]     = useState<RuleAction>("show");
  const [fieldSrc,   setFieldSrc]   = useState<"variable" | "custom">(variables.length > 0 ? "variable" : "custom");
  const [field,      setField]      = useState(variables[0]?.name ?? "");
  const [customCol,  setCustomCol]  = useState("");
  const [operator,   setOperator]   = useState<RuleOperator>("is_not_empty");
  const [value,      setValue]      = useState("");
  // -1 = todo el cuadro (el caso de siempre).
  const [segmentIdx, setSegmentIdx] = useState(-1);

  const effectiveField  = fieldSrc === "custom" ? customCol.trim().toUpperCase() : field;
  const actionLabel     = action === "show" ? "Mostrar" : "Ocultar";
  const operatorLabel   = OPERATORS.find((o) => o.value === operator)?.label ?? "";
  // Solo tiene sentido elegir si hay más de un pedazo.
  const puedeElegirSegmento = (segments?.length ?? 0) > 1;
  const alcance = puedeElegirSegmento && segmentIdx >= 0 && segments
    ? ` ${etiquetaDeSegmento(segments[segmentIdx])}`
    : "";
  const autoName        = `${actionLabel}${alcance} si ${effectiveField} ${operatorLabel}`;

  function handleSave() {
    if (!effectiveField) return;
    const condition = NEEDS_VALUE.includes(operator)
      ? { field: effectiveField, operator, value }
      : { field: effectiveField, operator };

    onSave({
      id:                  crypto.randomUUID(),
      name:                autoName,
      target_component_id: componentId,
      // Se omite cuando apunta al cuadro entero: el backend distingue por la
      // ausencia del campo, no por un valor centinela.
      ...(puedeElegirSegmento && segmentIdx >= 0 ? { target_segment_index: segmentIdx } : {}),
      condition:           condition as CenefaRule["condition"],
      action:              { type: action },
    });
  }

  return (
    <div className="space-y-3">
      {/* Paso 0: a qué le aplica — solo en cuadros de texto compuesto, donde
          un mismo renglón tiene varias variables y elegir importa. */}
      {puedeElegirSegmento && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase mb-1.5">¿A qué parte?</p>
          <select
            className="input text-xs w-full"
            value={segmentIdx}
            onChange={(e) => setSegmentIdx(Number(e.target.value))}
          >
            <option value={-1}>Todo el cuadro</option>
            {segments!.map((seg, i) => (
              <option key={i} value={i}>
                Solo {etiquetaDeSegmento(seg)}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Paso 1: Acción */}
      <div>
        <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase mb-1.5">¿Qué hace?</p>
        <div className="flex gap-2">
          {(["show", "hide"] as RuleAction[]).map((a) => (
            <button
              key={a}
              onClick={() => setAction(a)}
              className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                action === a
                  ? a === "show"
                    ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 ring-1 ring-emerald-300 dark:ring-emerald-800"
                    : "bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 ring-1 ring-rose-300 dark:ring-rose-800"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              {a === "show" ? "Mostrar" : "Ocultar"}
            </button>
          ))}
        </div>
      </div>

      {/* Paso 2: Campo — variable de plantilla o columna de Excel */}
      <div>
        <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase mb-1.5">¿Cuándo? Según…</p>
        <div className="flex gap-1 mb-2">
          {variables.length > 0 && (
            <button
              onClick={() => setFieldSrc("variable")}
              className={`flex-1 py-1 rounded text-[10px] font-medium transition-all ${
                fieldSrc === "variable"
                  ? "bg-brand-100 dark:bg-brand-950/40 text-brand-700 dark:text-brand-400 ring-1 ring-brand-300 dark:ring-brand-800"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              Variable de plantilla
            </button>
          )}
          <button
            onClick={() => setFieldSrc("custom")}
            className={`flex-1 py-1 rounded text-[10px] font-medium transition-all ${
              fieldSrc === "custom"
                ? "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 ring-1 ring-amber-300 dark:ring-amber-800"
                : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
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
          <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
            Escribí el nombre exacto de la columna en el Excel (sin tildes).
          </p>
        )}
      </div>

      {/* Paso 3: Condición simplificada */}
      <div>
        <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase mb-1.5">¿Bajo qué condición?</p>
        <div className="flex gap-2 flex-wrap">
          {SIMPLE_CONDITIONS.map((c) => (
            <button
              key={c.value}
              onClick={() => {
                setOperator(c.value as RuleOperator);
                if (!NEEDS_VALUE.includes(c.value as RuleOperator)) setValue("");
              }}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                operator === c.value
                  ? "bg-brand-100 dark:bg-brand-950/40 text-brand-700 dark:text-brand-400 ring-1 ring-brand-300 dark:ring-brand-800"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              {c.emoji} {c.label}
            </button>
          ))}
        </div>
        {NEEDS_VALUE.includes(operator) && (
          <input
            className="input w-full text-xs mt-2"
            placeholder={operator === "contains" ? "Escribí el texto que tiene que aparecer…" : "Escribí el valor exacto…"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
      </div>

      {/* Preview */}
      <p className="text-[10px] text-slate-400 dark:text-slate-500 italic bg-slate-50 dark:bg-slate-800/60 rounded px-2 py-1.5 truncate">
        → {autoName}
      </p>

      <div className="flex gap-1.5">
        <button onClick={handleSave} className="btn-primary text-xs px-2.5 py-1">Guardar</button>
        <button onClick={onCancel} className="btn-secondary text-xs px-2.5 py-1">Cancelar</button>
      </div>
    </div>
  );
}
