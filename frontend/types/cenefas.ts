// Tipos TypeScript para el sistema de cenefas v2

export type ComponentType = "text" | "image" | "shape";

export type TextTransform =
  | "none"
  | "price_integer"
  | "price_decimal"
  | "price_full"
  | "combo_quantity"
  | "combo_price"
  | "uppercase"
  | "smart_bold";

export interface ComponentBounds {
  x: number;      // cm desde la izquierda
  y: number;      // cm desde arriba
  width: number;  // cm
  height: number; // cm
}

export interface ComponentStyle {
  font_family?: string;
  font_size?: number;
  font_bold?: boolean;
  color?: string;
  background_color?: string;
  align?: "left" | "center" | "right";
  auto_fit?: boolean;
}

export interface CenefaComponent {
  id: string;
  type: ComponentType;
  name: string;
  variable?: string;
  static_value?: string;
  image_data?: string;
  image_ext?: string;
  transform?: TextTransform;
  style: ComponentStyle;
  base_bounds: ComponentBounds;
  format_overrides: Record<string, Partial<ComponentBounds> & Partial<ComponentStyle>>;
  z_index: number;
  locked: boolean;
  visible: boolean;
}

export type RuleOperator =
  | "equals"
  | "not_equals"
  | "greater_than"
  | "less_than"
  | "contains"
  | "is_empty"
  | "is_not_empty";

export type RuleAction = "show" | "hide";

export interface RuleCondition {
  field?: string;
  operator: RuleOperator | "and" | "or" | "not";
  value?: string | number;
  conditions?: RuleCondition[];
  condition?: RuleCondition;
}

export interface CenefaRule {
  id: string;
  name: string;
  target_component_id: string;
  condition: RuleCondition;
  action: { type: RuleAction };
}

export interface CenefaVariable {
  name: string;
  type: "text" | "price" | "number" | "image_url" | "boolean";
  required: boolean;
  csv_column: string;
  default_value?: string;
}

export interface CenefaTemplate {
  version: string;
  name: string;
  master_format: string;
  formats: string[];
  variables: CenefaVariable[];
  components: CenefaComponent[];
  rules: CenefaRule[];
}

export interface CenefaTemplateRecord {
  id: string;
  name: string;
  formats: string[];
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
  definition?: CenefaTemplate;
}

export interface CenefaFormat {
  id: string;
  label: string;
  width_cm: number;
  height_cm: number;
  slots: number;
  slot_cols: number;
  slot_rows: number;
}

export interface CenefaJob {
  id: string;
  status: "pending" | "running" | "done" | "error";
  format: string;
  export_type: string;
  row_count?: number;
  error_count: number;
  created_at: string;
  completed_at?: string;
  missing_vars?: string[];
  validation_summary?: {
    total: number;
    correct: number;
    with_warnings: number;
    critical_errors: number;
    status: "ok" | "warning" | "error";
  };
}

export interface ValidationReport {
  total: number;
  errors: { row: number; product: string; type: string; detail: string }[];
  warnings: { row: number; product: string; type: string; detail: string }[];
  status: "ok" | "warning" | "error";
}
