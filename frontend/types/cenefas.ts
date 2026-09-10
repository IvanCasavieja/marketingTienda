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
  /**
   * true cuando la persona escribió el tamaño de letra a mano en el panel de
   * propiedades (no al redimensionar la caja, que desde 09/2026 ya no toca
   * la letra -- pedido explícito de Ivan: la caja y el tamaño de fuente se
   * controlan por separado, como en PowerPoint). El backend (ver
   * _fit_text_to_box en component_renderer.py) respeta este tamaño tal cual
   * y no lo vuelve a achicar contra el ancho/alto disponible.
   */
  _manual_font_override?: boolean;
  /**
   * Relación EXPLÍCITA con otro cuadro: el id del componente cuyo valor este
   * cuadro acompaña. La declara la persona en el panel de propiedades, y
   * manda sobre cualquier heurística — donde hay relación declarada el motor
   * no adivina por posición.
   *
   * El caso típico es el "$" suelto del diseño: sin esto, el motor tenía que
   * deducir a qué precio pertenece mirando la geometría, y se equivocaba
   * (lo emparejaba con el cuadro del decimal vacío, o con el "$" de la celda
   * de al lado en la 6xA4).
   */
  vinculado_a?: string | null;
}

/** Override efímero de UN componente al confirmar un job (POST
 * /jobs/{id}/confirm) — lo que la persona ajustó en PreviewStep antes de
 * bajar el archivo. Cada campo es opcional y se mergea sobre el componente
 * original del lado del backend (ver confirm_generation_job en jobs.py);
 * lo que no se manda queda como estaba. `style` cubre el font_size que
 * cambia al redimensionar con los 4 puntos (ver Canvas.tsx); `segments` va
 * completo cuando el componente es multi-segmento, porque cada segmento
 * lleva su propio font_size. */
/**
 * Lo que se ajustó de UN cuadro revisando una cenefa, para mandarlo al
 * confirmar. No es el componente entero: solo los campos tocados, que se
 * mergean sobre el `template_def` congelado del job (ver `_con_override` en
 * jobs.py, que tiene la lista espejo de esto).
 *
 * Además de la caja y el estilo van los campos de CONTENIDO. Sin ellos,
 * cambiar la variable de un cuadro en el preview se veía en pantalla y no
 * salía en el archivo.
 *
 * `segments: null` es "volver a modo simple" — distinto de no mandar el
 * campo, que es "no lo toqué".
 */
export interface ComponentOverride {
  id: string;
  base_bounds?: ComponentBounds;
  style?: Partial<ComponentStyle>;
  segments?: TextSegment[] | null;
  variable?: string | null;
  static_value?: string | null;
  transform?: TextTransform;
  vinculado_a?: string | null;
  image_data?: string | null;
  image_ext?: string | null;
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
  /**
   * Índice del segmento al que apunta la regla, dentro de `segments` del
   * cuadro. Sin esto, la regla apunta al CUADRO ENTERO (el caso de siempre).
   *
   * Existe para condicionar un pedazo de un texto compuesto sin tocar el
   * resto: la palabra "unidad" al lado del precio, que solo corresponde
   * cuando la cenefa es de una categoría unificada. En un cuadro aparte
   * quedaba desalineada del precio; con una regla sobre el cuadro, ocultarla
   * se llevaba puesto también al precio.
   */
  target_segment_index?: number;
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

/** Aviso de auto-corrección al importar un PPTX (ver _autocorregir_geometria
 * en pptx_importer.py) — misma forma que CenefaRevisionItem, pero es un
 * "ya se corrigió esto", no un pendiente. Solo viaja en la respuesta de
 * POST /import-pptx, nunca en una plantilla ya guardada. */
export interface CenefaImportWarning {
  nivel: "alto" | "medio" | "info";
  tipo: string;
  titulo: string;
  detalle: string;
  sugerencia: string;
  detalle_datos?: { variable?: string | null; [key: string]: unknown };
}

export interface CenefaTemplate {
  version: string;
  name: string;
  master_format: string;
  formats: string[];
  variables: CenefaVariable[];
  components: CenefaComponent[];
  rules: CenefaRule[];
  /** Solo presente en la respuesta de POST /import-pptx. */
  import_warnings?: CenefaImportWarning[];
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
  /** Una persona confirmó que esta corrida salió bien (decide la retención del archivo). */
  verificado?: boolean;
  /** Revisión del Excel contra esta plantilla, antes de confirmar. Nunca bloquea. */
  revision?: CenefaRevisionItem[];
}

/** Un hallazgo de la revisión previa: qué va a salir mal y cómo arreglarlo. */
export interface CenefaRevisionItem {
  nivel: "alto" | "medio" | "info";
  tipo: string;
  titulo: string;
  detalle: string;
  sugerencia: string;
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
  /**
   * Si el trabajo de este mundo se valoriza en el informe de produccion.
   * Redexpres y el mundo de pruebas van en false: pasan por el motor pero no
   * son trabajo facturable.
   */
  cobrable?: boolean;
  /** Cenefas hechas antes de que el job registrara el mundo (declaradas). */
  cenefas_previas?: number;
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
  // Solo presente cuando el job se generó desde una plantilla del equipo
  // (no builtin_slug ni template_upload) — decide si tiene sentido ofrecer
  // "guardar estos cambios en la plantilla" al confirmar (ver PreviewStep).
  template_id?: string | null;
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
