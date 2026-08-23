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
  strikethrough?: boolean;
  color?: string;
  background_color?: string;
  align?: "left" | "center" | "right";
  auto_fit?: boolean;
  vertical_align?: string;
  /**
   * Alto de linea del parrafo en puntos, cuando el diseno lo fuerza con un
   * "run espaciador": un espacio en un cuerpo mucho mayor que el texto. Se usa
   * para apoyar un texto chico en la linea de uno grande (el "$" al lado del
   * precio). Ver _populate_text_frame en component_renderer.py.
   */
  line_height_pt?: number;
}

export interface TextSegment {
  type: "static" | "variable";
  value: string;
  transform?: TextTransform;
  style?: {
    font_size?: number;
    font_bold?: boolean;
    strikethrough?: boolean;
    color?: string;
  };
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
  segments?: TextSegment[];
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

/** Una cenefa dentro de un lote: un Excel contra una plantilla. */
export interface CenefaLoteItem {
  job_id?: string;
  id?: string;
  excel: string;
  template: string;
  template_id?: string;
  status?: string;
  format?: string;
  row_count?: number | null;
  template_def?: CenefaTemplate;
  preview_product?: Record<string, string>;
  preview_products?: Record<string, string>[];
  slot_bands?: string[][];
  validation_report?: { error?: string } | null;
}

/** Un lote: todas las cenefas que se pidieron juntas. */
export interface CenefaLote {
  lote_id: string;
  /** running | preview | done | parcial | error */
  status: string;
  total: number;
  cenefas: CenefaLoteItem[];
}

/** Un "mundo" de cenefas. Son datos, no código: se crean desde la UI. */
export interface CenefaDestino {
  slug: string;
  nombre: string;
  descripcion: string;
  icono: string;
  color: string;
}

export interface CenefaTemplateRecord {
  id: string;
  name: string;
  formats: string[];
  category?: string | null;
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

export interface CenefaJobIssue {
  row: number;
  product: string;
  type: string;
  detail: string;
}

export interface CenefaJob {
  id: string;
  status: "pending" | "running" | "preview" | "done" | "error";
  format: string;
  export_type: string;
  row_count?: number;
  error_count: number;
  created_at: string;
  completed_at?: string;
  missing_vars?: string[];
  errors?: CenefaJobIssue[];
  warnings?: CenefaJobIssue[];
  validation_summary?: {
    total: number;
    correct: number;
    with_warnings: number;
    critical_errors: number;
    status: "ok" | "warning" | "error";
  };
  // Solo presente cuando status === "error" (ver _job_to_dict en cenefas_v2.py)
  validation_report?: { error?: string };
  // Solo presentes cuando status === "preview" (ver PreviewStep)
  template_def?: CenefaTemplate;
  preview_product?: Record<string, string>;
  // Solo presentes cuando el template es multi-banda (ej. 3xA4) — ver
  // _detect_slot_bands en component_renderer.py y su uso en _job_to_dict.
  // slot_bands[i] = ids de componentes que le corresponden al producto
  // preview_products[i].
  slot_bands?: string[][];
  preview_products?: Record<string, string>[];
}

export interface ValidationReport {
  total: number;
  errors: { row: number; product: string; type: string; detail: string }[];
  warnings: { row: number; product: string; type: string; detail: string }[];
  status: "ok" | "warning" | "error";
}
