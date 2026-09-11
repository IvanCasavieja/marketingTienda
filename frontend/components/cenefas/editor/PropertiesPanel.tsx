"use client";
import { useMemo, useState } from "react";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent, CenefaRule, CenefaTemplate, CenefaVariable, TextSegment, TextTransform } from "@/types/cenefas";
import { Trash2, Lock, Unlock, Plus, GripVertical, Search, ArrowDown, ArrowUp } from "lucide-react";
import { RuleChip, RuleForm } from "./RulesPanel";
import { buildSiblingMap } from "@/lib/cenefas/siblingMap";
import { resolverFuente } from "@/lib/cenefas/fuentes";
import { cenefasV2Api } from "@/lib/api";

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

interface PropertiesPanelProps {
  /**
   * Fuente de datos + acciones -- por defecto vienen del store global del
   * editor completo (/materiales/cenefas/v2). LotePreviewStep.tsx pasa las
   * suyas propias (el `template_def` de LA CENEFA QUE SE ESTÁ MIRANDO, que
   * vive en estado local, no en el store) para reusar este mismo panel ahí
   * -- pedido explícito de Ivan: "todo se debería hacer en esta vista", sin
   * un editor aparte que nadie encuentra.
   *
   * `deleteComponent` queda afuera cuando no viene: borrar un componente ahí
   * no tiene dónde guardarse (ComponentOverride, lo que mandan las pantallas
   * de preview al confirmar, no tiene "eliminado") -- mostrar el control
   * igual sería una acción que no hace nada. Para no dibujar un cuadro está
   * la regla de visibilidad, que sí viaja.
   *
   * `addRule`/`deleteRule` SÍ los pasan las dos pantallas de preview desde el
   * 09/09/2026. Antes no, con el argumento de que las reglas no tenían dónde
   * guardarse -- y era cierto cuando se escribió, pero dejó de serlo al
   * agregarse `rules_override` en confirm_generation_job: las reglas se
   * mandan enteras al confirmar y se aplican. La sección quedó apagada por un
   * motivo vencido, así que en el preview de lote el botón "Agregar regla" de
   * cada cuadro no aparecía aunque la pestaña Reglas de al lado sí funcionara.
   */
  template?: CenefaTemplate;
  selectedComponentId?: string | null;
  updateComponent?: (id: string, updates: Partial<CenefaComponent>) => void;
  deleteComponent?: (id: string) => void;
  addRule?: (rule: CenefaRule) => void;
  deleteRule?: (id: string) => void;
  /** Bandas de la plantilla activa, para vincular la edición numérica de
   * posición/tamaño con los mismos hermanos que ya vincula el arrastre en
   * Canvas.tsx (ver buildSiblingMap). Igual patrón que el resto de props:
   * sin prop explícita cae al store global. */
  slotBands?: string[][] | null;
}

function tieneVariable(c: CenefaComponent): boolean {
  if (c.variable) return true;
  return (c.segments ?? []).some((s) => s.type === "variable");
}

export default function PropertiesPanel(props: PropertiesPanelProps = {}) {
  const store = useEditorStore();
  const template = props.template ?? store.template;
  const selectedComponentId =
    props.selectedComponentId !== undefined ? props.selectedComponentId : store.selectedComponentId;
  const updateComponent = props.updateComponent ?? store.updateComponent;
  const deleteComponent = props.deleteComponent;
  const addRule = props.addRule;
  const deleteRule = props.deleteRule;
  const slotBands = props.slotBands !== undefined ? props.slotBands : store.slotBands;

  const siblingMap = useMemo(
    () => buildSiblingMap(template.components, slotBands),
    [template.components, slotBands],
  );

  const comp = template.components.find((c) => c.id === selectedComponentId) ?? null;
  const [showRuleForm, setShowRuleForm] = useState(false);

  // Candidatos a ser la pareja de un cuadro fijo: los que SI imprimen una
  // variable. Un cuadro "fijo" es el que no imprime ninguna (su texto es del
  // diseño: el "$", una leyenda) y es el unico que necesita declarar a que
  // valor acompaña. Va aca arriba, con el resto de los hooks, porque abajo
  // hay un `return` condicional (sin componente seleccionado) y un useMemo
  // despues de el no se llamaria en todos los renders.
  // Escaneo de relaciones: el backend PROPONE con qué cuadro va cada "$"
  // suelto y acá se confirman de a una. Nunca se aplica solo -- fue el
  // pedido explícito: "no dejemos a la adivinanza".
  const [escaneando, setEscaneando] = useState(false);
  const [sugerencias, setSugerencias] = useState<
    { desde: string; desde_nombre: string; hacia: string; hacia_nombre: string; confianza: number }[] | null
  >(null);
  const [errorEscaneo, setErrorEscaneo] = useState<string | null>(null);

  // En qué banda vive cada componente, para poder replicar una relación al
  // cuadro equivalente de las demás bandas. Va con el resto de los hooks:
  // más abajo hay un `return` condicional y un useMemo después de él no se
  // llamaría en todos los renders.
  const bandaDe = useMemo(() => {
    const m = new Map<string, number>();
    (slotBands ?? []).forEach((ids, i) => ids.forEach((id) => m.set(id, i)));
    return m;
  }, [slotBands]);

  const candidatosRelacion = useMemo(
    () => template.components.filter((c) => c.type === "text" && tieneVariable(c)),
    [template.components],
  );

  if (!comp) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-6">
        <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
          <span className="text-slate-300 dark:text-slate-600 text-lg">✦</span>
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Ningún componente seleccionado</p>
        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
          Clic sobre un elemento del canvas para editar sus propiedades
        </p>
      </div>
    );
  }

  // La misma resolución que usa el canvas para dibujar -- asi lo que dice el
  // panel es exactamente lo que se ve.
  const fuente = resolverFuente(comp.style?.font_family, comp.style?.font_bold);

  /**
   * Declara "este cuadro acompaña a aquel" y lo REPLICA en las demás bandas,
   * cada una apuntando al cuadro de SU banda.
   *
   * Es el punto del pedido: el problema no era acomodar un "$", era tener que
   * acomodarlo cenefa por cenefa porque no estaba relacionado con nada.
   * Declararlo una vez en la 6xA4 lo declara en las seis.
   *
   * Si el destino no existe en alguna banda (un cuadro que aparece una sola
   * vez en toda la hoja) esa banda queda sin declarar: no se inventa a quién
   * apuntar.
   */
  function relacionar(origenId: string, destinoId: string | null) {
    updateComponent(origenId, { vinculado_a: destinoId });
    const hermanosOrigen = siblingMap.get(origenId) ?? [];
    if (hermanosOrigen.length === 0) return;

    if (!destinoId) {
      for (const sid of hermanosOrigen) updateComponent(sid, { vinculado_a: null });
      return;
    }
    const destinoPorBanda = new Map<number, string>();
    for (const id of [destinoId, ...(siblingMap.get(destinoId) ?? [])]) {
      const b = bandaDe.get(id);
      if (b !== undefined) destinoPorBanda.set(b, id);
    }
    for (const sid of hermanosOrigen) {
      const b = bandaDe.get(sid);
      const destino = b === undefined ? undefined : destinoPorBanda.get(b);
      if (destino) updateComponent(sid, { vinculado_a: destino });
    }
  }

  async function detectarRelaciones() {
    setEscaneando(true);
    setErrorEscaneo(null);
    try {
      const { data } = await cenefasV2Api.detectarRelaciones(template.components);
      // Las que ya están declaradas no se vuelven a proponer.
      setSugerencias(
        (data.sugerencias ?? []).filter((sg) => {
          const c = template.components.find((x) => x.id === sg.desde);
          return c && !c.vinculado_a;
        }),
      );
    } catch (e) {
      setErrorEscaneo(e instanceof Error ? e.message : "No se pudo escanear");
      setSugerencias(null);
    } finally {
      setEscaneando(false);
    }
  }

  function set<K extends keyof CenefaComponent>(key: K, value: CenefaComponent[K]) {
    updateComponent(comp!.id, { [key]: value } as Partial<CenefaComponent>);
  }

  function setFontSize(value: number) {
    updateComponent(comp!.id, {
      style: { ...comp!.style, font_size: value },
      _manual_font_override: true,
    });
    // Mismo criterio que setStyle: se replica a los hermanos, marcándolos
    // también como _manual_font_override para que el tamaño puesto a mano
    // sobreviva al export en las tres bandas, no solo en la editada.
    for (const sid of siblingMap.get(comp!.id) ?? []) {
      const sComp = template.components.find((c) => c.id === sid);
      if (!sComp || sComp.locked) continue;
      updateComponent(sid, {
        style: { ...sComp.style, font_size: value },
        _manual_font_override: true,
      });
    }
  }

  function setStyle(key: string, value: unknown) {
    updateComponent(comp!.id, { style: { ...comp!.style, [key]: value } });

    // Mismo criterio que setBounds: un cambio de estilo (tamaño de letra,
    // color, negrita, alineación) en un cuadro se replica a sus hermanos
    // de las otras bandas -- acá se copia el mismo VALOR, a diferencia de
    // setBounds que replica un delta, porque el pedido es que las cenefas
    // de una misma hoja queden con el mismo diseño, no un cambio relativo.
    for (const sid of siblingMap.get(comp!.id) ?? []) {
      const sComp = template.components.find((c) => c.id === sid);
      if (!sComp || sComp.locked) continue;
      updateComponent(sid, { style: { ...sComp.style, [key]: value } });
    }
  }

  function setSegments(segs: TextSegment[]) {
    const value = segs.length ? segs : undefined;
    updateComponent(comp!.id, { segments: value });
    // Mismo criterio que setStyle: el estilo por segmento (tamaño, color,
    // negrita) de un cuadro compuesto también se replica a sus hermanos.
    for (const sid of siblingMap.get(comp!.id) ?? []) {
      const sComp = template.components.find((c) => c.id === sid);
      if (!sComp || sComp.locked) continue;
      updateComponent(sid, { segments: value });
    }
  }

  function setBounds(key: "x" | "y" | "width" | "height", value: number) {
    const previous = comp!.base_bounds[key];
    updateComponent(comp!.id, {
      base_bounds: { ...comp!.base_bounds, [key]: value },
    });

    // Igual que el arrastre/resize en Canvas.tsx: el delta de ESTA edición
    // se replica a los hermanos detectados en otras bandas, para que tipear
    // un valor acá no desalinee el cuadro del resto de las cenefas de la
    // hoja (antes solo el arrastre con el mouse vinculaba, y editar el
    // número a mano en este panel dejaba ese cuadro puntual desalineado).
    const delta = value - previous;
    if (!delta) return;
    for (const sid of siblingMap.get(comp!.id) ?? []) {
      const sComp = template.components.find((c) => c.id === sid);
      if (!sComp || sComp.locked) continue;
      const isSize = key === "width" || key === "height";
      const nextValue = isSize
        ? Math.max(key === "width" ? 0.5 : 0.3, sComp.base_bounds[key] + delta)
        : sComp.base_bounds[key] + delta;
      updateComponent(sid, {
        base_bounds: { ...sComp.base_bounds, [key]: +nextValue.toFixed(2) },
      });
    }
  }

  return (
    <div className="flex-1 overflow-y-auto min-h-0">
      {/* Header del componente */}
      <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <input
            className="w-full text-sm font-semibold text-slate-800 dark:text-slate-100 bg-transparent border-b border-transparent hover:border-slate-200 dark:border-slate-700 dark:hover:border-slate-700 focus:border-brand-400 focus:outline-none pb-0.5"
            value={comp.name}
            onChange={(e) => set("name", e.target.value)}
          />
          <span className="text-[10px] text-slate-400 dark:text-slate-500 capitalize">{comp.type}</span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => set("locked", !comp.locked)}
            className={`p-1.5 rounded-lg transition-colors ${
              comp.locked
                ? "bg-amber-50 dark:bg-amber-950/40 text-amber-500"
                : "text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
            title={comp.locked ? "Desbloquear" : "Bloquear"}
          >
            {comp.locked ? <Lock size={14} /> : <Unlock size={14} />}
          </button>
          {deleteComponent && (
            <button
              onClick={() => deleteComponent(comp.id)}
              className="p-1.5 rounded-lg text-slate-400 dark:text-slate-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
              title="Eliminar componente"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      <div className="p-4 space-y-5">
        {/* === TEXTO: sección unificada de contenido con modo simple / compuesto === */}
        {comp.type === "text" && (
          <Section label="Contenido">
            {/* Toggle modo compuesto */}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-500 dark:text-slate-400">Texto compuesto</span>
              <button
                onClick={() => {
                  // Por setSegments y no por updateComponent directo: prender
                  // o apagar el modo compuesto es un cambio de segmentos como
                  // cualquier otro y tiene que replicarse a las hermanas de la
                  // hoja. Sin esto, editar los segmentos DESPUÉS sí replicaba
                  // (setSegments manda el array entero) pero el apagado no, y
                  // las otras cenefas de la 3xA4 quedaban compuestas mientras
                  // la editada volvía a modo simple.
                  if (comp.segments?.length) {
                    setSegments([]);   // [] -> undefined: vuelve a modo simple
                  } else {
                    const initial: TextSegment[] = comp.variable
                      ? [{ type: "variable", value: comp.variable, transform: comp.transform ?? "none" }]
                      : comp.static_value
                      ? [{ type: "static", value: comp.static_value }]
                      : [{ type: "static", value: "" }];
                    setSegments(initial);
                  }
                }}
                className={`relative inline-flex w-9 h-5 rounded-full transition-colors ${
                  comp.segments?.length ? "bg-brand-500" : "bg-slate-200 dark:bg-slate-700"
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
                onChange={setSegments}
              />
            ) : (
              <div className="space-y-3">
                {/* Variable selector */}
                <div>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase mb-1">Variable CSV</p>
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
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase mb-1">Texto fijo</p>
                    <input
                      type="text"
                      className="input w-full text-sm"
                      placeholder="Ej: VÁLIDO AL:, unidad, ..."
                      value={comp.static_value ?? ""}
                      onChange={(e) => set("static_value", e.target.value || undefined)}
                    />
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
                      Aparece igual en todas las cenefas generadas.
                    </p>
                  </div>
                )}

                {/* Transformación */}
                <div>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase mb-1">Transformación</p>
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
                  className="max-h-24 w-auto rounded border border-slate-200 dark:border-slate-700 object-contain"
                />
                <button
                  onClick={() => { set("image_data", undefined); set("image_ext", undefined); }}
                  className="text-[10px] text-rose-500 hover:text-rose-700"
                >
                  Quitar imagen
                </button>
              </div>
            ) : (
              <p className="text-[10px] text-slate-400 dark:text-slate-500 italic mb-1">
                Sin imagen — se mostrará un placeholder gris (o la imagen que subas al generar)
              </p>
            )}
            <label className="mt-2 flex flex-col gap-1">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">
                {comp.image_data ? "Reemplazar imagen" : "Subir imagen al template"}
              </span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
                className="text-xs text-slate-500 dark:text-slate-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-slate-100 dark:file:bg-slate-800 file:text-slate-600 dark:file:text-slate-300 hover:file:bg-slate-200 dark:hover:file:bg-slate-700"
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
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">{key}</span>
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

        {/* Relación con otro cuadro. Solo tiene sentido para un cuadro FIJO
            (un "$", una leyenda del diseño): es el que necesita saber a qué
            valor acompaña. Un cuadro con variable propia ya se identifica
            solo. Ver vinculado_a en types/cenefas.ts. */}
        {comp.type === "text" && !tieneVariable(comp) && (
          <Section label="Relación">
            <div className="space-y-2">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">
                  Acompaña al cuadro
                </span>
                <select
                  className="input text-sm"
                  value={comp.vinculado_a ?? ""}
                  onChange={(e) => relacionar(comp.id, e.target.value || null)}
                >
                  <option value="">Sin relación (el motor lo deduce)</option>
                  {candidatosRelacion.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name || c.variable || c.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <p className="text-[9px] text-slate-400 dark:text-slate-500 leading-snug">
                {comp.vinculado_a
                  ? "Declarada a mano: al exportar se alinea con ese cuadro y no se deduce nada por posición."
                  : "Sin declarar, el motor deduce por posición cuál es su pareja, y puede equivocarse."}
                {(siblingMap.get(comp.id)?.length ?? 0) > 0 &&
                  ` Se aplica también a las otras ${siblingMap.get(comp.id)!.length} cenefas de la hoja.`}
              </p>

              {/* Escaneo de toda la plantilla. Propone, no aplica: cada
                  relación se confirma a mano, una por una. */}
              <div className="pt-2 border-t border-slate-200 dark:border-slate-700">
                <button
                  type="button"
                  className="btn-secondary text-xs w-full flex items-center justify-center gap-1.5"
                  onClick={detectarRelaciones}
                  disabled={escaneando}
                >
                  <Search className="w-3.5 h-3.5" />
                  {escaneando ? "Escaneando…" : "Detectar relaciones en toda la plantilla"}
                </button>

                {errorEscaneo && (
                  <p className="text-[10px] text-rose-500 mt-1.5">{errorEscaneo}</p>
                )}

                {sugerencias !== null && sugerencias.length === 0 && !errorEscaneo && (
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1.5">
                    No quedan cuadros fijos sin relacionar.
                  </p>
                )}

                {sugerencias !== null && sugerencias.length > 0 && (
                  <div className="mt-2 space-y-1.5">
                    <p className="text-[10px] text-slate-400 dark:text-slate-500">
                      {sugerencias.length} propuesta{sugerencias.length === 1 ? "" : "s"} —
                      confirmá las que estén bien:
                    </p>
                    {sugerencias.map((sg) => (
                      <div
                        key={sg.desde}
                        className="rounded border border-slate-200 dark:border-slate-700 p-2 text-[11px]"
                      >
                        <div className="text-slate-600 dark:text-slate-300">
                          <span className="font-medium">{sg.desde_nombre}</span>
                          {" acompaña a "}
                          <span className="font-medium">{sg.hacia_nombre}</span>
                        </div>
                        <div className="text-[9px] text-slate-400 dark:text-slate-500 mt-0.5">
                          confianza {Math.round(sg.confianza * 100)}%
                        </div>
                        <div className="flex gap-1.5 mt-1.5">
                          <button
                            type="button"
                            className="btn-primary text-[10px] px-2 py-1"
                            onClick={() => {
                              relacionar(sg.desde, sg.hacia);
                              setSugerencias((prev) =>
                                (prev ?? []).filter((x) => x.desde !== sg.desde));
                            }}
                          >
                            Confirmar
                          </button>
                          <button
                            type="button"
                            className="btn-secondary text-[10px] px-2 py-1"
                            onClick={() =>
                              setSugerencias((prev) =>
                                (prev ?? []).filter((x) => x.desde !== sg.desde))
                            }
                          >
                            Descartar
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Section>
        )}

        {/* Estilo tipográfico */}
        {comp.type === "text" && (
          <Section label="Estilo">
            <div className="space-y-3">
              {/* Qué tipografía se está dibujando. Antes no se veía en ningún
                  lado y por eso costó tanto darse cuenta de que el preview
                  caía en Impact: el cartel se veía gordo y no había forma de
                  saber con qué fuente estaba dibujando. */}
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">Tipografía (viene del PPTX)</span>
                <div className="rounded border border-slate-200 dark:border-slate-700 px-2 py-1.5 bg-slate-50 dark:bg-slate-800/50">
                  <div
                    className="text-sm text-slate-700 dark:text-slate-200 truncate"
                    style={{ fontFamily: fuente.stack, fontWeight: fuente.weight }}
                    title={comp.style.font_family ?? "sin definir"}
                  >
                    {comp.style.font_family || "(sin definir)"}
                  </div>
                  <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                    {fuente.familia} · {fuente.pesoNombre} ({fuente.weight})
                  </div>
                  {fuente.sustituida && (
                    <div className="text-[10px] text-amber-600 dark:text-amber-500 mt-1 leading-snug">
                      Esta máquina no tiene la fuente exacta: el preview la dibuja
                      con una parecida. El PPTX exportado sí lleva el nombre original.
                    </div>
                  )}
                </div>
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">Tamaño (pt)</span>
                <input
                  type="number"
                  min={6}
                  max={200}
                  className="input text-sm"
                  value={comp.style.font_size ?? 16}
                  onChange={(e) =>
                    // Escrito a mano acá -> el backend lo respeta tal cual al
                    // exportar, sin volver a achicarlo contra el espacio
                    // disponible (ver _manual_font_override en
                    // component_renderer.py). Redimensionar la caja con los 4
                    // puntos ya NO pasa por acá ni toca este tamaño (ver
                    // Canvas.tsx) -- los dos se controlan por separado.
                    setFontSize(parseInt(e.target.value) || 16)
                  }
                />
                {comp._manual_font_override && (
                  <span className="text-[9px] text-slate-400 dark:text-slate-500">
                    Fijado a mano — no se va a achicar solo al exportar.
                  </span>
                )}
              </label>

              <div className="flex gap-2">
                <label className="flex flex-col gap-1 flex-1">
                  <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">Color</span>
                  <div className="flex gap-1.5">
                    <input
                      type="color"
                      className="w-8 h-9 rounded border border-slate-200 dark:border-slate-700 cursor-pointer p-0.5"
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
                  <span className="text-sm text-slate-600 dark:text-slate-300">Negrita</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded text-brand-600"
                    checked={comp.style.strikethrough ?? false}
                    onChange={(e) => setStyle("strikethrough", e.target.checked)}
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-300">Tachado</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded text-brand-600"
                    checked={comp.style.auto_fit ?? true}
                    onChange={(e) => setStyle("auto_fit", e.target.checked)}
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-300">Auto-ajuste</span>
                </label>
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">Alineación</span>
                <div className="flex gap-1">
                  {(["left", "center", "right"] as const).map((a) => (
                    <button
                      key={a}
                      onClick={() => setStyle("align", a)}
                      className={`flex-1 py-1.5 rounded border text-xs transition-all ${
                        (comp.style.align ?? "center") === a
                          ? "bg-brand-50 dark:bg-brand-950/40 border-brand-400 text-brand-600 dark:text-brand-400 font-medium"
                          : "border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600"
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

        {/* Reglas de visibilidad para este componente -- solo si el caller
            las soporta (LotePreviewStep no: ComponentOverride no tiene
            dónde guardarlas). */}
        {addRule && deleteRule && (
          <Section label="Reglas de visibilidad">
            {(() => {
              const compRules = template.rules.filter(
                (r) => r.target_component_id === comp.id
              );
              return (
                <div className="space-y-0.5">
                  {compRules.length === 0 && !showRuleForm && (
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 italic">
                      Siempre visible — sin reglas
                    </p>
                  )}
                  {compRules.map((rule) => (
                    <RuleChip
                      key={rule.id}
                      rule={rule}
                      segments={comp.segments}
                      onDelete={() => deleteRule(rule.id)}
                    />
                  ))}
                  {showRuleForm ? (
                    <div className="mt-2">
                      <RuleForm
                        componentId={comp.id}
                        variables={template.variables}
                        segments={comp.segments}
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
        )}
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
      <p className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
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

  // Tamaño puesto a mano en ESTE segmento: además del valor deja la marca que
  // le dice al motor que manda en su pedazo aunque la caja tenga tamaño manual
  // (ver _populate_text_frame en component_renderer.py). Sin la marca no se
  // puede distinguir del tamaño que el segmento trae copiado del PPTX, y la caja
  // lo pisaba. Vaciar el campo vuelve a "Hereda": se van el valor y la marca.
  function setSegFontSize(idx: number, value: number | undefined) {
    onChange(
      segments.map((s, i) => {
        if (i !== idx) return s;
        const style = { ...s.style };
        const nuevo: TextSegment = { ...s, style };
        if (value === undefined) {
          delete style.font_size;
          delete nuevo._manual_font_override;
        } else {
          style.font_size = value;
          nuevo._manual_font_override = true;
        }
        return nuevo;
      }),
    );
  }

  // Subir o bajar ESTE segmento dentro del renglón: es el "desplazamiento" de
  // PowerPoint, en milésimas de porcentaje del tamaño del segmento (30 % =
  // 30000, igual que lo guarda el PPTX y lo lee el importer). El 0 también se
  // guarda: si la caja trae el pedazo subido, un 0 explícito es lo que lo baja
  // a la línea. Vaciar el campo vuelve a heredar. Viaja con los segmentos, así
  // que se replica a las otras bandas (setSegments) y sale igual en todas las
  // hojas.
  function setSegBaseline(idx: number, porcentaje: number | undefined) {
    const valor = porcentaje === undefined || Number.isNaN(porcentaje)
      ? undefined
      : Math.round(Math.max(-100, Math.min(100, porcentaje)) * 1000);
    updateSegStyle(idx, "baseline", valor);
  }

  function moverSeg(idx: number, pasoPorcentaje: number) {
    const actual = (segments[idx].style?.baseline ?? 0) / 1000;
    setSegBaseline(idx, actual + pasoPorcentaje);
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
        <div key={idx} className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
          {/* Header del segmento */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-100 dark:border-slate-800">
            <GripVertical size={12} className="text-slate-300 dark:text-slate-600" />
            <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase flex-1">
              Segmento {idx + 1}
            </span>
            <button
              onClick={() => removeSeg(idx)}
              className="p-0.5 text-slate-300 dark:text-slate-600 hover:text-rose-500 transition-colors"
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
                      ? "bg-brand-50 dark:bg-brand-950/40 border-brand-400 text-brand-600 dark:text-brand-400 font-medium"
                      : "border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:border-slate-300 dark:hover:border-slate-600"
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
                <span className="text-[9px] text-slate-400 dark:text-slate-500 uppercase">Tamaño (pt)</span>
                <input
                  type="number"
                  min={6}
                  max={400}
                  className="input text-xs"
                  placeholder="Hereda"
                  value={seg.style?.font_size ?? ""}
                  onChange={(e) =>
                    setSegFontSize(idx, e.target.value ? parseInt(e.target.value) : undefined)
                  }
                />
                {seg._manual_font_override && (
                  <span className="text-[9px] text-slate-400 dark:text-slate-500">
                    Fijado a mano — manda sobre la caja.
                  </span>
                )}
              </label>
              <label className="flex flex-col gap-0.5">
                <span className="text-[9px] text-slate-400 dark:text-slate-500 uppercase">Color</span>
                <div className="flex gap-1">
                  <input
                    type="color"
                    className="w-7 h-8 rounded border border-slate-200 dark:border-slate-700 cursor-pointer p-0.5 shrink-0"
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
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] text-slate-400 dark:text-slate-500 uppercase">Subir / bajar (%)</span>
              <div className="flex gap-1">
                <button
                  type="button"
                  title="Bajar 5 %"
                  onClick={() => moverSeg(idx, -5)}
                  className="px-1.5 rounded border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:text-brand-600 hover:border-brand-300 transition-colors"
                >
                  <ArrowDown size={12} />
                </button>
                <input
                  type="number"
                  min={-100}
                  max={100}
                  step={5}
                  className="input text-xs flex-1 min-w-0"
                  placeholder="Hereda"
                  value={seg.style?.baseline !== undefined ? seg.style.baseline / 1000 : ""}
                  onChange={(e) =>
                    setSegBaseline(idx, e.target.value === "" ? undefined : Number(e.target.value))
                  }
                />
                <button
                  type="button"
                  title="Subir 5 %"
                  onClick={() => moverSeg(idx, 5)}
                  className="px-1.5 rounded border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:text-brand-600 hover:border-brand-300 transition-colors"
                >
                  <ArrowUp size={12} />
                </button>
              </div>
              <span className="text-[9px] text-slate-400 dark:text-slate-500">
                Positivo sube, negativo baja (en % del tamaño del segmento). 0 lo deja en la línea.
              </span>
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
              <span className="text-xs text-slate-600 dark:text-slate-300">Negrita</span>
              {seg.style?.font_bold === undefined && (
                <span className="text-[9px] text-slate-400 dark:text-slate-500">(hereda del estilo base)</span>
              )}
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="rounded text-brand-600"
                checked={!!seg.style?.strikethrough}
                onChange={(e) =>
                  updateSegStyle(idx, "strikethrough", e.target.checked ? true : undefined)
                }
              />
              <span className="text-xs text-slate-600 dark:text-slate-300">Tachado</span>
              {seg.style?.strikethrough === undefined && (
                <span className="text-[9px] text-slate-400 dark:text-slate-500">(hereda del estilo base)</span>
              )}
            </label>
          </div>
        </div>
      ))}

      <button
        onClick={addSeg}
        className="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-brand-600 dark:text-brand-400 border border-dashed border-brand-300 dark:border-brand-800 rounded-lg hover:bg-brand-50 dark:hover:bg-brand-950/40 transition-colors"
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
            <div key={fmt} className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
              <button
                onClick={() => setOpen(isOpen ? null : fmt)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <span>{fmt.toUpperCase()}</span>
                <span className="text-slate-400 dark:text-slate-500">
                  {Object.keys(ov).length > 0
                    ? `${Object.keys(ov).length} override${Object.keys(ov).length > 1 ? "s" : ""}`
                    : "heredado"}
                </span>
              </button>
              {isOpen && (
                <div className="px-3 pb-3 pt-1 bg-slate-50 dark:bg-slate-800/60 grid grid-cols-2 gap-2">
                  {(["x", "y", "width", "height"] as const).map((k) => (
                    <label key={k} className="flex flex-col gap-1">
                      <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">{k}</span>
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
                    <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase">Font size (pt)</span>
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
