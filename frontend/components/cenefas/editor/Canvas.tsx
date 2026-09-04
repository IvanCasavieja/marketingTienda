"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent, CenefaTemplate } from "@/types/cenefas";

// ---------------------------------------------------------------------------
// Constantes de escala y dimensiones de formatos
// ---------------------------------------------------------------------------

const PX_PER_CM = 28;

const FORMAT_DIMS: Record<string, { w: number; h: number }> = {
  a4:      { w: 21.0,  h: 29.7  },
  a3:      { w: 29.7,  h: 42.0  },
  "3xa4":  { w: 21.0,  h: 9.9   },  // franja horizontal única (1/3 A4)
  pinchos: { w: 7.0,   h: 14.85 },  // pincho individual (grilla 3×2 en A4)
  a5:      { w: 14.85, h: 21.0  },
  "6xa4":  { w: 7.0,   h: 14.85 },  // celda individual (grilla 3×2 en A4)
};

const COMP_COLORS: Record<string, string> = {
  text:  "#3B82F6",
  image: "#8B5CF6",
  shape: "#10B981",
};

function scalePx(cm: number) {
  return Math.round(cm * PX_PER_CM);
}

// ---------------------------------------------------------------------------
// Regla en centímetros (arriba + costado, como PowerPoint) — pedido
// explícito: la persona tiene que poder ver en qué centímetro exacto está
// parada una caja al moverla/redimensionarla, no solo "a ojo".
// ---------------------------------------------------------------------------

const RULER_SIZE = 18; // px

interface RegleTick { pos: number; major: boolean; label?: number }

function buildRulerTicks(lengthCm: number, offset: number): RegleTick[] {
  const ticks: RegleTick[] = [];
  for (let cm = 0; cm <= Math.ceil(lengthCm); cm++) {
    const major = cm % 5 === 0;
    ticks.push({ pos: offset + scalePx(cm), major, label: major ? cm : undefined });
  }
  return ticks;
}

// Proporcion del cuerpo que ocupa el ascendente en las tipografias de titular
// que usan estas plantillas (Impact y condensadas). Aproximado a proposito:
// esto es el preview, no el render final.
const ASCENDENTE_EM = 0.9;

// Los cuerpos de fuente viajan en puntos (1 pt = 1/72 pulgada) y el canvas
// trabaja en px a razon de PX_PER_CM.
function ptToPx(pt: number) {
  return (pt / 72) * 2.54 * PX_PER_CM;
}

// La tipografia del diseno con alternativas: si la maquina no la tiene
// instalada, el navegador cae a algo parecido en vez de a la fuente por
// defecto. Impact y las condensadas son las que usan estas plantillas.
function fontStack(familia?: string | null) {
  const base = (familia ?? "").trim();
  const alternativas = "Impact, 'Haettenschweiler', 'Arial Narrow Bold', 'Franklin Gothic Medium', Arial, sans-serif";
  return base ? `${base}, ${alternativas}` : alternativas;
}

// ---------------------------------------------------------------------------
// Aplicar layout del formato destino sobre los componentes
// Replica la lógica de layout_engine.py en el cliente para la vista previa
// ---------------------------------------------------------------------------

function applyFormatLayout(
  components: CenefaComponent[],
  activeFormat: string,
  masterFormat: string,
): CenefaComponent[] {
  if (activeFormat === masterFormat) return components;

  const master = FORMAT_DIMS[masterFormat] ?? FORMAT_DIMS.a4;
  const target = FORMAT_DIMS[activeFormat] ?? FORMAT_DIMS.a4;
  const scaleX = target.w / master.w;
  const scaleY = target.h / master.h;

  return components.map((comp) => {
    const ov = comp.format_overrides[activeFormat] ?? {};
    const b  = comp.base_bounds;
    const styleOv: Partial<CenefaComponent["style"]> = {};
    if (ov.font_size !== undefined) styleOv.font_size = ov.font_size;
    if (ov.color     !== undefined) styleOv.color     = ov.color;

    return {
      ...comp,
      base_bounds: {
        x:      ov.x      !== undefined ? ov.x      : b.x      * scaleX,
        y:      ov.y      !== undefined ? ov.y      : b.y      * scaleY,
        width:  ov.width  !== undefined ? ov.width  : b.width  * scaleX,
        height: ov.height !== undefined ? ov.height : b.height * scaleY,
      },
      style: { ...comp.style, ...styleOv },
    };
  });
}

// ---------------------------------------------------------------------------
// Cache de imagenes base64 (una por componente), fuera del ciclo de Konva
// ---------------------------------------------------------------------------

// Formatos que los navegadores pueden mostrar en data URLs
const _WEB_EXTS = new Set(["jpeg", "jpg", "png", "gif", "webp", "svg+xml"]);

function useImageCache(components: CenefaComponent[]) {
  const cacheRef = useRef<Map<string, HTMLImageElement>>(new Map());
  const [, bump] = useState(0);

  useEffect(() => {
    const cache = cacheRef.current;
    const validIds = new Set<string>();

    for (const comp of components) {
      if (!comp.image_data || !comp.image_ext || !_WEB_EXTS.has(comp.image_ext)) continue;
      validIds.add(comp.id);
      const cacheKey = `${comp.id}:${comp.image_data}`;
      if (cache.has(cacheKey)) continue;

      // Invalidar una entrada vieja de este mismo componente si cambio la imagen
      for (const k of cache.keys()) {
        if (k.startsWith(`${comp.id}:`)) cache.delete(k);
      }

      const el = new window.Image();
      el.onload = () => { cache.set(cacheKey, el); bump((n) => n + 1); };
      el.src = `data:image/${comp.image_ext};base64,${comp.image_data}`;
    }

    // Podar componentes que ya no existen o dejaron de tener imagen valida
    for (const k of cache.keys()) {
      const id = k.slice(0, k.indexOf(":"));
      if (!validIds.has(id)) cache.delete(k);
    }
  }, [components]);

  return (comp: CenefaComponent) => cacheRef.current.get(`${comp.id}:${comp.image_data}`);
}

// ---------------------------------------------------------------------------
// Construccion imperativa de un shape (equivalente al viejo <ComponentShape>)
// ---------------------------------------------------------------------------

const CENEFA_COMP_NAME = "cenefa-comp";

// Puerto directo de apply_transform (component_renderer.py) -- mismos casos,
// mismo orden, para que el preview corte "399,50" en entero/decimal igual
// que el render final. smart_bold/combo_price/none devuelven el valor sin
// cambios, igual que el backend (smart_bold solo afecta negrita por letra,
// no el texto).
function applyTransform(value: string, transform?: string): string {
  if (!value || !transform || transform === "none" || transform === "smart_bold") return value || "";

  if (transform === "price_full" || transform === "price_integer" || transform === "price_decimal") {
    const num = value.replace(/[^\d.,]/g, "");
    if (transform === "price_full") return value;
    const lastComma = num.lastIndexOf(",");
    if (transform === "price_integer") return lastComma >= 0 ? num.slice(0, lastComma) : num;
    if (transform === "price_decimal") return lastComma >= 0 ? "," + num.slice(lastComma + 1) : "";
  }

  if (transform === "combo_quantity") {
    const m = value.toUpperCase().match(/^(\d+X)/);
    return m ? m[1] : value;
  }

  if (transform === "combo_price") return value;
  if (transform === "uppercase") return value.toUpperCase();

  return value;
}

// ---------------------------------------------------------------------------
// Vinculación por variable entre bandas de una plantilla multi-producto
// (3xA4/6xA4/A5/pinchos) — mover/achicar/agrandar la caja de una variable en
// una banda replica el mismo cambio en las demás. Ver Parte 2 del plan.
// ---------------------------------------------------------------------------

// Identidad de "qué variable imprime este cuadro", para emparejar la MISMA
// caja entre bandas. Sin variable (texto fijo, o sin match) nunca vincula --
// su key es única por componente.
function keyOfComponent(c: CenefaComponent): string {
  if (c.variable) return c.variable;
  const vars = (c.segments ?? [])
    .filter((s) => s.type === "variable")
    .map((s) => s.value);
  return vars.length ? vars.join("+") : `_id_${c.id}`;
}

// Mapa componente -> ids de sus "hermanos" (misma variable, en OTRAS
// bandas). Nunca vincula dos apariciones de la misma variable DENTRO de una
// banda (ej. "unidad" repetida dos veces en un solo cartel de la A4 de
// Preciazos, confirmado intencional). Si el multiset de keys no es idéntico
// en todas las bandas, esa key queda sin vincular -- nunca se adivina un
// emparejamiento que no cierra parejo.
function buildSiblingMap(
  components: CenefaComponent[], slotBands: string[][] | null | undefined,
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  if (!slotBands || slotBands.length < 2) return map;

  const byId = new Map(components.map((c) => [c.id, c]));
  const porBanda: Map<string, string[]>[] = slotBands.map((ids) => {
    const g = new Map<string, string[]>();
    for (const id of ids) {
      const c = byId.get(id);
      if (!c) continue;
      const k = keyOfComponent(c);
      (g.get(k) ?? g.set(k, []).get(k)!).push(id);
    }
    return g;
  });

  const todasLasKeys = new Set<string>();
  porBanda.forEach((g) => g.forEach((_, k) => todasLasKeys.add(k)));

  for (const k of todasLasKeys) {
    if (k.startsWith("_id_")) continue; // sin variable: nunca vincula
    const counts = porBanda.map((g) => (g.get(k) ?? []).length);
    if (counts[0] === 0 || counts.some((n) => n !== counts[0])) continue;
    for (let occ = 0; occ < counts[0]; occ++) {
      const idsEnEstaOcurrencia = porBanda.map((g) => g.get(k)![occ]);
      for (const id of idsEnEstaOcurrencia) {
        map.set(id, idsEnEstaOcurrencia.filter((otro) => otro !== id));
      }
    }
  }
  return map;
}

// Resuelve el texto a mostrar cuando hay datos reales (previewData),
// aplicando el mismo transform por segmento/componente que usa el render
// final (_populate_text_frame en component_renderer.py).
function resolveComponentText(comp: CenefaComponent, previewData: Record<string, string>): string {
  if (comp.segments?.length) {
    return comp.segments
      .map((seg) => {
        if (seg.type === "static") return seg.value;
        return applyTransform(previewData[seg.value] ?? "", seg.transform);
      })
      .join("");
  }
  if (comp.variable) return applyTransform(previewData[comp.variable] ?? comp.static_value ?? "", comp.transform);
  return comp.static_value ?? "";
}

function buildComponentGroup({
  comp, pageLeft, pageTop, isSelected, draggable, image, previewData, onSelect, onDragEnd,
}: {
  comp: CenefaComponent;
  pageLeft: number;
  pageTop: number;
  isSelected: boolean;
  draggable: boolean;
  image?: HTMLImageElement;
  previewData?: Record<string, string>;
  onSelect: () => void;
  onDragEnd: (x: number, y: number) => void;
}): Konva.Group {
  const color = COMP_COLORS[comp.type] ?? "#64748b";
  const b = comp.base_bounds;
  const x = pageLeft + scalePx(b.x);
  const y = pageTop  + scalePx(b.y);
  const w = Math.max(scalePx(b.width),  20);
  const h = Math.max(scalePx(b.height), 10);
  const imgInvalid = comp.type === "image" && !!comp.image_data && !_WEB_EXTS.has(comp.image_ext ?? "");

  const group = new Konva.Group({ name: CENEFA_COMP_NAME, x, y, width: w, height: h, draggable });
  group.on("click tap", onSelect);
  group.on("dragend", (e) => onDragEnd(e.target.x(), e.target.y()));

  if (image) {
    group.add(new Konva.Image({ image, width: w, height: h, cornerRadius: comp.locked ? 0 : 2 }));
    if (isSelected) {
      group.add(new Konva.Rect({
        width: w, height: h, fill: "transparent",
        stroke: color, strokeWidth: 2, cornerRadius: 2,
      }));
    } else if (!comp.locked) {
      group.add(new Konva.Rect({
        width: w, height: h, fill: "transparent",
        stroke: `${color}55`, strokeWidth: 1, dash: [4, 3],
      }));
    }
    return group;
  }

  // Con datos reales el cuadro se dibuja FIEL: misma tipografía, mismo cuerpo
  // y mismo color que va a salir en el PPTX. Antes se dibujaba esquemático
  // (Inter, cuerpo derivado del alto de la caja) y el preview cortaba las
  // líneas distinto al archivo final -- se aprobaba en pantalla algo que en
  // PowerPoint se montaba sobre el precio.
  //
  // Sin datos reales (modo edición del template) sigue siendo esquemático: ahí
  // lo que importa es ver qué variable tiene cada cuadro, no cómo queda.
  const fiel = !!previewData && !imgInvalid;

  group.add(new Konva.Rect({
    width: w, height: h,
    fill: comp.type === "shape" && comp.style?.background_color
      ? comp.style.background_color
      : (fiel ? "transparent" : `${color}22`),
    stroke: isSelected ? color : (fiel ? `${color}44` : `${color}88`),
    strokeWidth: isSelected ? 2 : 1,
    cornerRadius: 3,
    dash: comp.locked ? [4, 3] : (fiel ? [3, 3] : undefined),
  }));

  const text =
    imgInvalid
      ? `⚠ Re-importá el PPTX\n(${comp.image_ext ?? "?"} no soportado)`
      : previewData
        ? resolveComponentText(comp, previewData)
        : comp.segments?.length
          ? `${comp.name}\n${comp.segments.map((s) => s.type === "static" ? `"${s.value}"` : `{${s.value}}`).join(" + ")}`
          : comp.variable
            ? `${comp.name}\n(${comp.variable})`
            : comp.static_value
              ? `"${comp.static_value.length > 24 ? comp.static_value.slice(0, 22) + "…" : comp.static_value}"`
              : comp.name;

  if (fiel) {
    // El cuerpo viaja en puntos; el canvas trabaja en px a PX_PER_CM.
    const pt = comp.style?.font_size ?? 12;
    const fontSizePx = ptToPx(pt);
    // PowerPoint apoya la primera linea en el ASCENDENTE del run mas grande
    // del parrafo. Cuando el diseno mete un "run espaciador" --un espacio en
    // un cuerpo mucho mayor-- para levantar el alto de linea, el texto chico
    // queda apoyado en esa linea alta, no pegado al techo de la caja. Es como
    // el diseñador alinea el "$" con el precio gigante de al lado.
    //
    // Sin esto el "$" de 80pt junto a un espaciador de 180pt se dibujaba 3,2 cm
    // mas arriba de donde sale en el PPTX.
    const lineHeightPt = comp.style?.line_height_pt ?? pt;
    const offsetY = lineHeightPt > pt ? ptToPx(lineHeightPt - pt) * ASCENDENTE_EM : 0;
    group.add(new Konva.Text({
      x: 0, y: offsetY, width: w,
      text,
      fontSize: fontSizePx,
      fontFamily: fontStack(comp.style?.font_family),
      fontStyle: comp.style?.font_bold ? "bold" : "normal",
      fill: comp.style?.color ?? "#1e293b",
      align: comp.style?.align ?? "center",
      lineHeight: 1.2,
      textDecoration: comp.style?.strikethrough ? "line-through" : undefined,
      wrap: "word",
      // Sin ellipsis y sin alto fijo A PROPÓSITO: si el texto no entra tiene
      // que VERSE desbordando, que es justamente lo que hay que detectar.
      listening: false,
    }));
  } else {
    group.add(new Konva.Text({
      x: 4, y: 4, width: w - 8, height: h - 8,
      text,
      fontSize: Math.min(11, Math.max(7, h / 2.5)),
      fill: imgInvalid ? "#F59E0B" : (comp.type === "shape" && comp.style?.background_color ? "#00000055" : color),
      fontFamily: "Inter, system-ui, sans-serif",
      textDecoration: comp.style?.strikethrough ? "line-through" : undefined,
      ellipsis: true,
      wrap: "word",
    }));
  }

  return group;
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

interface CanvasProps {
  className?: string;
  // Todas opcionales — si no se pasan, cae al store global del editor
  // (comportamiento original, sin cambios). PreviewStep las pasa todas
  // explícitamente y mantiene su propio estado local, sin tocar el store.
  template?: CenefaTemplate;
  activeFormat?: string;
  selectedComponentId?: string | null;
  onSelectComponent?: (id: string | null) => void;
  onUpdateComponent?: (id: string, updates: Partial<CenefaComponent>) => void;
  // Datos reales de un producto para reemplazar los placeholders {variable}
  // por su valor resuelto — y habilita edición sin importar activeFormat
  // vs master_format (en el preview solo existe el formato que se va a
  // generar, no tiene sentido el modo "solo lectura" del editor standalone).
  previewData?: Record<string, string>;
  // Plantillas multi-banda (ej. 3xA4, ver _detect_slot_bands en
  // component_renderer.py): slotBands[i] = ids de componentes que le
  // corresponden a previewProducts[i]. Sin esto, todos los componentes usan
  // previewData por igual y las 3 bandas muestran el mismo producto.
  slotBands?: string[][];
  previewProducts?: Record<string, string>[];
}

export default function Canvas({
  className = "",
  template: propTemplate,
  activeFormat: propActiveFormat,
  selectedComponentId: propSelectedComponentId,
  onSelectComponent,
  onUpdateComponent,
  previewData,
  slotBands: propSlotBands,
  previewProducts,
}: CanvasProps) {
  const store = useEditorStore();
  const template             = propTemplate ?? store.template;
  const activeFormat         = propActiveFormat ?? store.activeFormat;
  const selectedComponentId  = propSelectedComponentId !== undefined ? propSelectedComponentId : store.selectedComponentId;
  const selectComponent      = onSelectComponent ?? store.selectComponent;
  const updateComponent      = onUpdateComponent ?? store.updateComponent;
  const interactive          = previewData !== undefined; // true en PreviewStep
  // Sin prop explícita (uso standalone del editor, ver v2/page.tsx) cae al
  // store, que las pide con detectSlotBands() cuando el formato activo tiene
  // más de un slot. PreviewStep/LotePreviewStep siempre pasan la prop.
  const slotBands = propSlotBands ?? store.slotBands ?? undefined;

  // Mapa id de componente -> índice de banda, para elegir qué producto de
  // previewProducts le toca a cada uno (ver slotBands en CanvasProps).
  const bandIndexByCompId = useMemo(() => {
    const map = new Map<string, number>();
    if (!slotBands) return map;
    slotBands.forEach((ids, bandIdx) => {
      for (const id of ids) map.set(id, bandIdx);
    });
    return map;
  }, [slotBands]);

  // Hermanos por variable entre bandas — ver buildSiblingMap arriba.
  const siblingMap = useMemo(
    () => buildSiblingMap(template.components, slotBands),
    [template.components, slotBands],
  );

  const containerRef    = useRef<HTMLDivElement>(null);
  const stageRef        = useRef<Konva.Stage | null>(null);
  const bgLayerRef      = useRef<Konva.Layer | null>(null);
  const compLayerRef    = useRef<Konva.Layer | null>(null);
  const transformerRef  = useRef<Konva.Transformer | null>(null);
  const selectedNodeRef = useRef<Konva.Group | null>(null);
  // id de componente -> nodo Konva, para mover/escalar hermanos en vivo sin
  // pasar por el reconciliador de React en cada frame de arrastre/resize.
  const nodeMapRef      = useRef<Map<string, Konva.Group>>(new Map());

  const getImage = useImageCache(template.components);

  const masterFormat = template.master_format;
  const isEditMode   = interactive || activeFormat === masterFormat;
  const dims         = FORMAT_DIMS[activeFormat] ?? FORMAT_DIMS.a4;
  const pageW        = scalePx(dims.w);
  const pageH        = scalePx(dims.h);
  const margin       = 40;
  const stageW       = pageW + margin * 2;
  const stageH       = pageH + margin * 2;
  const pageLeft     = margin;
  const pageTop      = margin;

  // Aplicar layout del formato activo para la vista previa, y corregir para
  // mostrar cajas de texto más anchas que la propia hoja: es un truco de
  // autoría de PowerPoint (caja invisible mucho más ancha que la diapositiva,
  // con el texto centrado adentro, para que el centrado no dependa de la
  // cantidad de dígitos) — no es un error de la plantilla ni algo que este
  // código esté agrandando, pero acá se ve tal cual el shape crudo, sin el
  // ajuste que el motor de export sí aplica al generar el archivo final. Solo
  // afecta cómo se dibuja el preview — no toca los bounds guardados.
  const displayComps = applyFormatLayout(
    [...template.components].sort((a, b) => a.z_index - b.z_index),
    activeFormat,
    masterFormat,
  ).map((comp) => {
    if (comp.type !== "text" || comp.base_bounds.width <= dims.w) return comp;
    return { ...comp, base_bounds: { ...comp.base_bounds, x: 0, width: dims.w } };
  });

  // Montaje: crear Stage/Layers/Transformer una sola vez. Todo esto vive
  // adentro de un efecto (nunca corre en el servidor), asi que el contenedor
  // se puede renderizar siempre sin riesgo de mismatch de hidratacion.
  useEffect(() => {
    if (!containerRef.current) return;

    const stage = new Konva.Stage({ container: containerRef.current, width: stageW, height: stageH });
    const bgLayer = new Konva.Layer();
    const compLayer = new Konva.Layer();
    const transformer = new Konva.Transformer({
      rotateEnabled: false,
      boundBoxFunc: (old, next) => (next.width < 20 || next.height < 10 ? old : next),
    });

    stage.add(bgLayer);
    stage.add(compLayer);
    compLayer.add(transformer);
    stage.on("mousedown", (e) => {
      if (e.target === stage) selectComponent(null);
    });

    stageRef.current = stage;
    bgLayerRef.current = bgLayer;
    compLayerRef.current = compLayer;
    transformerRef.current = transformer;

    return () => {
      stage.destroy();
      stageRef.current = null;
      bgLayerRef.current = null;
      compLayerRef.current = null;
      transformerRef.current = null;
      selectedNodeRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tamaño del stage (cambia al cambiar de formato)
  useEffect(() => {
    stageRef.current?.width(stageW);
    stageRef.current?.height(stageH);
  }, [stageW, stageH]);

  // Fondo de pagina (sombra + rect blanco + etiqueta de formato)
  useEffect(() => {
    const layer = bgLayerRef.current;
    if (!layer) return;
    layer.destroyChildren();

    layer.add(new Konva.Rect({
      x: pageLeft + 4, y: pageTop + 4, width: pageW, height: pageH,
      fill: "rgba(0,0,0,0.08)", cornerRadius: 2,
    }));

    const pageRect = new Konva.Rect({
      x: pageLeft, y: pageTop, width: pageW, height: pageH,
      fill: "white", stroke: "#cbd5e1", strokeWidth: 1, cornerRadius: 2,
    });
    pageRect.on("click", () => selectComponent(null));
    layer.add(pageRect);

    layer.add(new Konva.Text({
      x: pageLeft, y: pageTop - 22,
      text: `${activeFormat.toUpperCase()}  ${dims.w}×${dims.h} cm`,
      fontSize: 10, fill: "#94a3b8", fontFamily: "Inter, system-ui, sans-serif",
    }));

    layer.batchDraw();
  }, [pageLeft, pageTop, pageW, pageH, activeFormat, dims.w, dims.h, selectComponent]);

  // Componentes: se reconstruye toda la capa en cada cambio relevante (igual
  // de simple que el reconciliador de React, sin diffing fino — para la
  // cantidad de componentes tipica de una cenefa el costo es despreciable).
  useEffect(() => {
    const layer = compLayerRef.current;
    const transformer = transformerRef.current;
    if (!layer || !transformer) return;

    layer.find(`.${CENEFA_COMP_NAME}`).forEach((n) => n.destroy());
    const nodeMap = new Map<string, Konva.Group>();
    nodeMapRef.current = nodeMap;

    let selectedNode: Konva.Group | null = null;

    for (const comp of displayComps) {
      const isSelected = comp.id === selectedComponentId && isEditMode;
      const bandIdx = bandIndexByCompId.get(comp.id);
      const compPreviewData =
        bandIdx !== undefined && previewProducts ? previewProducts[bandIdx] ?? previewData : previewData;
      const group = buildComponentGroup({
        comp, pageLeft, pageTop, isSelected,
        draggable: isEditMode && !comp.locked,
        image: getImage(comp),
        previewData: compPreviewData,
        onSelect: () => { if (isEditMode) selectComponent(comp.id); },
        onDragEnd: (x, y) => {
          const newX = +Math.max(0, Math.min((x - pageLeft) / PX_PER_CM, dims.w - comp.base_bounds.width)).toFixed(2);
          const newY = +Math.max(0, Math.min((y - pageTop)  / PX_PER_CM, dims.h - comp.base_bounds.height)).toFixed(2);
          updateComponent(comp.id, {
            base_bounds: { ...comp.base_bounds, x: newX, y: newY },
          });
        },
      });
      layer.add(group);
      nodeMap.set(comp.id, group);
      if (isSelected) selectedNode = group;
    }

    // Arrastre vinculado por variable entre bandas — segundo set de
    // listeners además del que ya conecta buildComponentGroup arriba (Konva
    // soporta varios handlers para el mismo evento). Solo para componentes
    // con hermanos DETECTADOS (siblingMap ya excluye pares dentro de una
    // misma banda, como "unidad" repetida a propósito en la A4).
    for (const comp of displayComps) {
      const siblings = (siblingMap.get(comp.id) ?? []).filter((sid) => {
        const s = template.components.find((c) => c.id === sid);
        return s && !s.locked;
      });
      const group = nodeMap.get(comp.id);
      if (!group || siblings.length === 0 || !isEditMode || comp.locked) continue;

      let dragStart: { x: number; y: number } | null = null;
      const siblingStarts = new Map<string, { x: number; y: number }>();

      group.on("dragstart", () => {
        dragStart = { x: group.x(), y: group.y() };
        siblingStarts.clear();
        for (const sid of siblings) {
          const sNode = nodeMap.get(sid);
          if (sNode) siblingStarts.set(sid, { x: sNode.x(), y: sNode.y() });
        }
      });
      group.on("dragmove", () => {
        if (!dragStart) return;
        const dx = group.x() - dragStart.x;
        const dy = group.y() - dragStart.y;
        for (const [sid, start] of siblingStarts) {
          const sNode = nodeMap.get(sid);
          if (sNode) { sNode.x(start.x + dx); sNode.y(start.y + dy); }
        }
        layer.batchDraw();
      });
      group.on("dragend", () => {
        if (!dragStart) return;
        const dxCm = (group.x() - dragStart.x) / PX_PER_CM;
        const dyCm = (group.y() - dragStart.y) / PX_PER_CM;
        dragStart = null;
        for (const sid of siblingStarts.keys()) {
          const sComp = template.components.find((c) => c.id === sid);
          if (!sComp) continue;
          const newX = +Math.max(0, Math.min(sComp.base_bounds.x + dxCm, dims.w - sComp.base_bounds.width)).toFixed(2);
          const newY = +Math.max(0, Math.min(sComp.base_bounds.y + dyCm, dims.h - sComp.base_bounds.height)).toFixed(2);
          updateComponent(sid, { base_bounds: { ...sComp.base_bounds, x: newX, y: newY } });
        }
      });
    }

    transformer.moveToTop();
    selectedNodeRef.current = selectedNode;
    transformer.nodes(selectedNode ? [selectedNode] : []);
    layer.batchDraw();
  }, [displayComps, selectedComponentId, isEditMode, pageLeft, pageTop, dims.w, dims.h, getImage, previewData, previewProducts, bandIndexByCompId, siblingMap, template.components, selectComponent, updateComponent]);

  // "Última versión conocida" de template/selectedComponentId/siblingMap —
  // evita closures viejas dentro de los handlers de abajo (registrados una
  // sola vez con [] o pocas deps) sin depender de useEditorStore.getState(),
  // que no existe cuando estas props vienen de afuera (ej. PreviewStep).
  const latestRef = useRef({ template, selectedComponentId, siblingMap });
  useEffect(() => {
    latestRef.current = { template, selectedComponentId, siblingMap };
  }, [template, selectedComponentId, siblingMap]);

  // Handler de fin de transformacion (resize con los 4 puntos), registrado
  // una sola vez. SOLO cambia la caja -- desde 09/2026 (pedido explícito de
  // Ivan, reemplaza la decisión anterior) redimensionar NUNCA toca el
  // tamaño de letra: los dos se controlan por separado, como en PowerPoint
  // (ver el campo "Tamaño (pt)" en PropertiesPanel.tsx). Antes se escalaba
  // la letra en proporción a la caja, lo que obligaba a agrandar la caja
  // muchísimo más de lo necesario solo para conseguir letra más grande, y
  // encima ese tamaño "de facto" no sobrevivía al exportar (el motor de
  // render lo recalculaba solo contra el espacio disponible). Solo replica
  // el cambio de bounds (delta absoluto) a cada hermano detectado en otras
  // bandas -- nunca font_size.
  useEffect(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;

    function handleTransformEnd() {
      const node = selectedNodeRef.current;
      if (!node) return;
      const scaleX = node.scaleX();
      const scaleY = node.scaleY();
      node.scaleX(1);
      node.scaleY(1);

      const { template: t, selectedComponentId: selId, siblingMap: siblings } = latestRef.current;
      const comp = t.components.find((c) => c.id === selId);
      if (!comp) return;

      const nuevoBounds = {
        x:      +((node.x() - pageLeft) / PX_PER_CM).toFixed(2),
        y:      +((node.y() - pageTop)  / PX_PER_CM).toFixed(2),
        width:  +((node.width()  * scaleX) / PX_PER_CM).toFixed(2),
        height: +((node.height() * scaleY) / PX_PER_CM).toFixed(2),
      };

      updateComponent(comp.id, { base_bounds: nuevoBounds });

      const dx = nuevoBounds.x      - comp.base_bounds.x;
      const dy = nuevoBounds.y      - comp.base_bounds.y;
      const dw = nuevoBounds.width  - comp.base_bounds.width;
      const dh = nuevoBounds.height - comp.base_bounds.height;
      for (const sid of siblings.get(comp.id) ?? []) {
        const sComp = t.components.find((c) => c.id === sid);
        if (!sComp || sComp.locked) continue;
        const sBounds = {
          x:      +(sComp.base_bounds.x + dx).toFixed(2),
          y:      +(sComp.base_bounds.y + dy).toFixed(2),
          width:  +Math.max(0.5, sComp.base_bounds.width  + dw).toFixed(2),
          height: +Math.max(0.3, sComp.base_bounds.height + dh).toFixed(2),
        };
        updateComponent(sid, { base_bounds: sBounds });
      }
    }

    transformer.on("transformend", handleTransformEnd);
    return () => { transformer.off("transformend", handleTransformEnd); };
  }, [pageLeft, pageTop, updateComponent]);

  // Feedback en vivo mientras se arrastra un handle de resize: refleja el
  // mismo desplazamiento + escala del nodo primario sobre sus hermanos, para
  // "ver en vivo" cómo cambian las otras cenefas de la hoja (pedido
  // explícito) sin esperar a soltar. Konva escala TODO lo de adentro del
  // grupo (rect + texto) vía scaleX/scaleY -- el mismo mecanismo con el que
  // ya se ve crecer/achicarse el nodo seleccionado durante el arrastre; acá
  // solo se replica sobre los grupos hermanos, que el Transformer no toca
  // por no estar seleccionados.
  useEffect(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;

    let inicio: { x: number; y: number } | null = null;
    const hermanoInicio = new Map<string, { x: number; y: number }>();

    function handleTransformStart() {
      const node = selectedNodeRef.current;
      const selId = latestRef.current.selectedComponentId;
      if (!node || !selId) return;
      inicio = { x: node.x(), y: node.y() };
      hermanoInicio.clear();
      for (const sid of latestRef.current.siblingMap.get(selId) ?? []) {
        const sNode = nodeMapRef.current.get(sid);
        if (sNode) hermanoInicio.set(sid, { x: sNode.x(), y: sNode.y() });
      }
    }

    function handleTransform() {
      const node = selectedNodeRef.current;
      if (!node || !inicio) return;
      const dx = node.x() - inicio.x;
      const dy = node.y() - inicio.y;
      const scaleX = node.scaleX();
      const scaleY = node.scaleY();
      for (const [sid, start] of hermanoInicio) {
        const sNode = nodeMapRef.current.get(sid);
        if (!sNode) continue;
        sNode.x(start.x + dx);
        sNode.y(start.y + dy);
        sNode.scaleX(scaleX);
        sNode.scaleY(scaleY);
      }
      compLayerRef.current?.batchDraw();
    }

    function handleTransformEndReset() {
      inicio = null;
      hermanoInicio.clear();
    }

    transformer.on("transformstart", handleTransformStart);
    transformer.on("transform", handleTransform);
    transformer.on("transformend", handleTransformEndReset);
    return () => {
      transformer.off("transformstart", handleTransformStart);
      transformer.off("transform", handleTransform);
      transformer.off("transformend", handleTransformEndReset);
    };
  }, []);

  const hTicks = useMemo(() => buildRulerTicks(dims.w, pageLeft), [dims.w, pageLeft]);
  const vTicks = useMemo(() => buildRulerTicks(dims.h, pageTop),  [dims.h, pageTop]);

  return (
    <div className={`relative overflow-auto bg-slate-200 dark:bg-slate-950 rounded-lg flex justify-center items-start ${className}`}>
      {/* Badge modo preview (solo en el editor standalone, no en PreviewStep) */}
      {!interactive && !isEditMode && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-40 px-2.5 py-1 bg-amber-500 text-white text-[10px] font-semibold rounded-full shadow pointer-events-none">
          Vista previa — {activeFormat.toUpperCase()} (solo lectura)
        </div>
      )}
      {/* Regla en cm: esquina + tira horizontal + tira vertical, todas
          `sticky` DENTRO del mismo contenedor con overflow-auto que envuelve
          el Stage -- así se scrollean solas con el canvas (mismo patrón que
          la fila/columna congelada de una planilla), sin sincronizar scroll
          por JS. */}
      <div
        className="grid"
        style={{ gridTemplateColumns: `${RULER_SIZE}px ${stageW}px`, gridTemplateRows: `${RULER_SIZE}px ${stageH}px` }}
      >
        <div
          className="sticky top-0 left-0 z-30 bg-slate-100 dark:bg-slate-900 border-b border-r border-slate-300 dark:border-slate-700"
        />
        <div
          className="sticky top-0 z-20 bg-slate-100 dark:bg-slate-900 border-b border-slate-300 dark:border-slate-700 relative overflow-hidden"
          style={{ width: stageW, height: RULER_SIZE }}
        >
          {hTicks.map((t, i) => (
            <div key={i} className="absolute bottom-0" style={{ left: t.pos }}>
              <div className="bg-slate-400 dark:bg-slate-600" style={{ width: 1, height: t.major ? 8 : 4 }} />
              {t.label !== undefined && (
                <span className="absolute -top-px left-1 text-[9px] leading-none text-slate-500 dark:text-slate-400 whitespace-nowrap">
                  {t.label}
                </span>
              )}
            </div>
          ))}
        </div>
        <div
          className="sticky left-0 z-20 bg-slate-100 dark:bg-slate-900 border-r border-slate-300 dark:border-slate-700 relative overflow-hidden"
          style={{ width: RULER_SIZE, height: stageH }}
        >
          {vTicks.map((t, i) => (
            <div key={i} className="absolute right-0" style={{ top: t.pos }}>
              <div className="bg-slate-400 dark:bg-slate-600" style={{ height: 1, width: t.major ? 8 : 4 }} />
              {t.label !== undefined && (
                <span className="absolute left-0.5 top-0.5 text-[8px] leading-none text-slate-500 dark:text-slate-400 whitespace-nowrap">
                  {t.label}
                </span>
              )}
            </div>
          ))}
        </div>
        <div ref={containerRef} />
      </div>
    </div>
  );
}
