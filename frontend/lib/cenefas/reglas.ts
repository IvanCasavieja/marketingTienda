import { resolverNombreVariable } from "@/lib/cenefaVariables";
import type { CenefaComponent, CenefaRule, RuleCondition } from "@/types/cenefas";

// ---------------------------------------------------------------------------
// Evaluación de reglas de visibilidad EN EL NAVEGADOR.
//
// Espejo exacto de backend/app/services/cenefas/rules_engine.py. Existe para
// que el canvas muestre lo que de verdad va a salir impreso: hasta el
// 09/09/2026 el frontend no evaluaba ninguna regla, así que agregar una y
// apretar Guardar no cambiaba UN PIXEL de la pantalla. El efecto solo
// aparecía al abrir el PPTX descargado, y la conclusión razonable de
// cualquiera que las probara era que las reglas no funcionaban.
//
// Es una segunda implementación de la misma lógica, con lo que eso tiene de
// peligroso, y por eso se mantiene deliberadamente literal: mismos nombres de
// operador, mismo orden de precedencia, misma respuesta ante lo desconocido.
// Si tocás rules_engine.py, tocá esto.
//
// Lo que NO se replica acá, a propósito, son las reglas AUTOMÁTICAS del motor
// (exclusión por promoOferta, cuadros de variables vacías, achique por
// solape): esas dependen de medir texto con las métricas de fuente reales y
// ya vienen resueltas desde el backend en el `template_def` del preview.
// ---------------------------------------------------------------------------

type Valores = Record<string, string>;

/**
 * El valor del campo que mira una condición.
 *
 * Primero por el nombre tal cual vino, que es lo que hace falta para una
 * columna suelta del Excel ("DESCUENTO 20"): esas no son variables y no
 * resuelven a nada. Si no está, se resuelve como nombre de variable — el
 * formulario de reglas pasa a MAYÚSCULAS lo que se escribe en "Columna del
 * Excel", así que `codigo` llega acá como `CODIGO`.
 */
function valorDeCampo(values: Valores, field: string): string | undefined {
  if (field in values) return values[field];
  const canonica = resolverNombreVariable(field);
  if (canonica && canonica in values) return values[canonica];
  return undefined;
}

function evaluarCondicion(cond: RuleCondition, values: Valores): boolean {
  const op = cond.operator ?? "";

  // Compuestas
  if (op === "and") return (cond.conditions ?? []).every((c) => evaluarCondicion(c, values));
  if (op === "or")  return (cond.conditions ?? []).some((c) => evaluarCondicion(c, values));
  if (op === "not") return !evaluarCondicion(cond.condition ?? ({} as RuleCondition), values);

  // Simples
  const value  = valorDeCampo(values, cond.field ?? "");
  const target = cond.value;
  const s = (v: unknown) => String(v ?? "").trim();

  switch (op) {
    case "equals":       return s(value) === s(target);
    case "not_equals":   return s(value) !== s(target);
    case "greater_than": {
      const a = parseFloat(String(value ?? 0)), b = parseFloat(String(target ?? 0));
      return Number.isFinite(a) && Number.isFinite(b) ? a > b : false;
    }
    case "less_than": {
      const a = parseFloat(String(value ?? 0)), b = parseFloat(String(target ?? 0));
      return Number.isFinite(a) && Number.isFinite(b) ? a < b : false;
    }
    case "contains":     return s(value).toLowerCase().includes(String(target ?? "").toLowerCase());
    case "is_empty":     return s(value) === "";
    case "is_not_empty": return s(value) !== "";
    case "length_greater_than":
    case "length_less_than": {
      // Largo del texto, no valor numérico. Ver el tipo RuleOperator.
      const largo = s(value).length;
      const objetivo = parseFloat(String(target).trim());
      if (!Number.isFinite(objetivo)) return false;
      return op === "length_greater_than" ? largo > objetivo : largo < objetivo;
    }
    default:             return true;   // operador desconocido no filtra
  }
}

/**
 * Modelo de visibilidad, para la clave que devuelva `claveDe`.
 *
 * - Sin reglas       -> visible (no aparece en el mapa devuelto)
 * - Con regla show   -> visible solo si al menos una show matchea
 * - Con regla hide   -> oculto si alguna hide matchea (gana sobre show)
 */
function resolverVisibilidad<K>(
  rules: CenefaRule[],
  values: Valores,
  claveDe: (r: CenefaRule) => K | null,
  serializar: (k: K) => string,
): Map<string, { clave: K; visible: boolean }> {
  const hasShow = new Map<string, K>();
  const hasHide = new Map<string, K>();
  const showOk  = new Set<string>();
  const hideOk  = new Set<string>();

  for (const rule of rules) {
    const clave = claveDe(rule);
    if (clave === null) continue;
    const k = serializar(clave);
    const accion  = rule.action?.type ?? "show";
    const matchea = evaluarCondicion(rule.condition, values);

    if (accion === "show") {
      hasShow.set(k, clave);
      if (matchea) showOk.add(k);
    } else if (accion === "hide") {
      hasHide.set(k, clave);
      if (matchea) hideOk.add(k);
    }
  }

  const salida = new Map<string, { clave: K; visible: boolean }>();
  for (const [k, clave] of [...hasShow, ...hasHide]) {
    const visible = hideOk.has(k) ? false : hasShow.has(k) ? showOk.has(k) : true;
    salida.set(k, { clave, visible });
  }
  return salida;
}

/**
 * Ids de los cuadros que estas reglas OCULTAN para esta fila.
 *
 * Las reglas que apuntan a un segmento no entran acá: si entraran, una regla
 * de "ocultá la palabra unidad" ocultaría el cuadro entero del precio.
 */
export function cuadrosOcultos(rules: CenefaRule[], values: Valores): Set<string> {
  const mapa = resolverVisibilidad<string>(
    rules, values,
    (r) => (r.target_segment_index !== undefined ? null : r.target_component_id || null),
    (k) => k,
  );
  const ocultos = new Set<string>();
  for (const { clave, visible } of mapa.values()) if (!visible) ocultos.add(clave);
  return ocultos;
}

/**
 * Por cuadro, los índices de segmento que estas reglas OCULTAN para esta fila.
 *
 * Un segmento oculto se dibuja vacío, no se saca de la lista — igual que hace
 * `apply_visibility` en el backend, que lo reemplaza por un segmento estático
 * vacío para que todo lo que viene después lo vea como "sin dato".
 */
export function segmentosOcultos(
  rules: CenefaRule[], values: Valores,
): Map<string, Set<number>> {
  const mapa = resolverVisibilidad<[string, number]>(
    rules, values,
    (r) => {
      const idx = r.target_segment_index;
      return idx === undefined || !r.target_component_id ? null : [r.target_component_id, idx];
    },
    ([id, idx]) => `${id}#${idx}`,
  );
  const salida = new Map<string, Set<number>>();
  for (const { clave, visible } of mapa.values()) {
    if (visible) continue;
    const [compId, idx] = clave;
    const set = salida.get(compId) ?? new Set<number>();
    set.add(idx);
    salida.set(compId, set);
  }
  return salida;
}

// ---------------------------------------------------------------------------
// Cuerpo declarado por regla
// ---------------------------------------------------------------------------
//
// Espejo de `_resolver_tamanos` / `evaluate_font_size_rules` en
// rules_engine.py. A diferencia del achique automático que esto reemplaza, acá
// no hay NADA que pueda desincronizarse: no se mide texto, no se miran vecinos
// y no se usa el ancho del papel. Se cuenta `len()` y se compara un número.

/**
 * El cuerpo en pt que las reglas le imponen a cada clave.
 *
 * Si matchean varias gana la MÁS CHICA, no la última: el orden de las reglas
 * no importa, igual que en `resolverVisibilidad`.
 */
function resolverTamanos<K>(
  rules: CenefaRule[],
  values: Valores,
  claveDe: (r: CenefaRule) => K | null,
  serializar: (k: K) => string,
): Map<string, { clave: K; pt: number }> {
  const salida = new Map<string, { clave: K; pt: number }>();
  for (const rule of rules) {
    const clave = claveDe(rule);
    if (clave === null) continue;
    if (rule.action?.type !== "set_font_size") continue;
    const pt = Number(rule.action?.value);
    if (!Number.isFinite(pt) || pt <= 0) continue;
    if (!evaluarCondicion(rule.condition, values)) continue;
    const k = serializar(clave);
    const previo = salida.get(k);
    if (!previo || pt < previo.pt) salida.set(k, { clave, pt });
  }
  return salida;
}

/** {id de cuadro -> cuerpo en pt} para los cuadros con regla de tamaño. */
export function tamanosDeCuadro(rules: CenefaRule[], values: Valores): Map<string, number> {
  const mapa = resolverTamanos<string>(
    rules, values,
    (r) => (r.target_segment_index !== undefined ? null : r.target_component_id || null),
    (k) => k,
  );
  const salida = new Map<string, number>();
  for (const { clave, pt } of mapa.values()) salida.set(clave, pt);
  return salida;
}

/** Por cuadro, {índice de segmento -> cuerpo en pt}. */
export function tamanosDeSegmento(
  rules: CenefaRule[], values: Valores,
): Map<string, Map<number, number>> {
  const mapa = resolverTamanos<[string, number]>(
    rules, values,
    (r) => {
      const idx = r.target_segment_index;
      return idx === undefined || !r.target_component_id ? null : [r.target_component_id, idx];
    },
    ([id, idx]) => `${id}#${idx}`,
  );
  const salida = new Map<string, Map<number, number>>();
  for (const { clave, pt } of mapa.values()) {
    const [compId, idx] = clave;
    const porSegmento = salida.get(compId) ?? new Map<number, number>();
    porSegmento.set(idx, pt);
    salida.set(compId, porSegmento);
  }
  return salida;
}

/**
 * El cuadro con el cuerpo que dictan las reglas. Espejo de `apply_font_sizes`.
 *
 * En un cuadro multi-segmento cada segmento lleva SU font_size y ese pisa al
 * del componente al dibujar --tanto acá como en _populate_text_frame del
 * backend--, así que una regla sobre el cuadro entero tiene que llegar también
 * a sus segmentos. Sin eso el cuerpo declarado se descarta en silencio en casi
 * todas las plantillas, que se importan multi-segmento.
 *
 * El número de la regla es el número que sale, en todos los pedazos: 90 en el
 * cuadro es 90 en cada uno (decisión de Ivan, 20/09/2026). Antes se calculaba
 * una escala contra el font_size de la caja --un número que nadie elige, lo
 * llena el importador con el del primer pedazo-- y el resultado era
 * impredecible: en Congelados A4 una regla de 90 dejaba el precio en 338,5. El
 * porqué completo está en apply_font_sizes (rules_engine.py), que es de donde
 * este archivo es espejo.
 *
 * `line_height_pt` no se toca: no es una letra, es el pedazo invisible con el
 * que el diseño fuerza la altura del renglón.
 *
 * Devuelve el MISMO objeto si no hay nada que aplicar: el Canvas lo llama en
 * cada render y una copia nueva por cuadro invalidaría memos río abajo.
 */
export function aplicarTamanos(
  comp: CenefaComponent,
  pt?: number,
  porSegmento?: Map<number, number>,
): CenefaComponent {
  if (pt === undefined && !porSegmento?.size) return comp;

  let nuevo = comp;
  if (pt !== undefined) {
    nuevo = { ...nuevo, style: { ...nuevo.style, font_size: pt } };
    if (nuevo.segments) {
      nuevo = { ...nuevo, segments: nuevo.segments.map((seg) =>
        ({ ...seg, style: { ...seg.style, font_size: pt } })) };
    }
  }
  if (porSegmento?.size && nuevo.segments) {
    nuevo = { ...nuevo, segments: nuevo.segments.map((seg, i) =>
      porSegmento.has(i)
        ? { ...seg, style: { ...seg.style, font_size: porSegmento.get(i)! } }
        : seg) };
  }
  return nuevo;
}
