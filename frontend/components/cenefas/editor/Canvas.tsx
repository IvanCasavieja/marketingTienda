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

  group.add(new Konva.Rect({
    width: w, height: h,
    fill: comp.type === "shape" && comp.style?.background_color ? comp.style.background_color : `${color}22`,
    stroke: isSelected ? color : `${color}88`,
    strokeWidth: isSelected ? 2 : 1,
    cornerRadius: 3,
    dash: comp.locked ? [4, 3] : undefined,
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
  slotBands,
  previewProducts,
}: CanvasProps) {
  const store = useEditorStore();
  const template             = propTemplate ?? store.template;
  const activeFormat         = propActiveFormat ?? store.activeFormat;
  const selectedComponentId  = propSelectedComponentId !== undefined ? propSelectedComponentId : store.selectedComponentId;
  const selectComponent      = onSelectComponent ?? store.selectComponent;
  const updateComponent      = onUpdateComponent ?? store.updateComponent;
  const interactive          = previewData !== undefined; // true en PreviewStep

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

  const containerRef    = useRef<HTMLDivElement>(null);
  const stageRef        = useRef<Konva.Stage | null>(null);
  const bgLayerRef      = useRef<Konva.Layer | null>(null);
  const compLayerRef    = useRef<Konva.Layer | null>(null);
  const transformerRef  = useRef<Konva.Transformer | null>(null);
  const selectedNodeRef = useRef<Konva.Group | null>(null);

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
      if (isSelected) selectedNode = group;
    }

    transformer.moveToTop();
    selectedNodeRef.current = selectedNode;
    transformer.nodes(selectedNode ? [selectedNode] : []);
    layer.batchDraw();
  }, [displayComps, selectedComponentId, isEditMode, pageLeft, pageTop, dims.w, dims.h, getImage, previewData, previewProducts, bandIndexByCompId, selectComponent, updateComponent]);

  // "Última versión conocida" de template/selectedComponentId — evita closures
  // viejas dentro de handleTransformEnd sin depender de useEditorStore.getState(),
  // que no existe cuando estas props vienen de afuera (ej. PreviewStep).
  const latestRef = useRef({ template, selectedComponentId });
  useEffect(() => {
    latestRef.current = { template, selectedComponentId };
  }, [template, selectedComponentId]);

  // Handler de fin de transformacion (resize), registrado una sola vez
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

      const { template: t, selectedComponentId: selId } = latestRef.current;
      const comp = t.components.find((c) => c.id === selId);
      if (!comp) return;

      updateComponent(comp.id, {
        base_bounds: {
          x:      +((node.x() - pageLeft) / PX_PER_CM).toFixed(2),
          y:      +((node.y() - pageTop)  / PX_PER_CM).toFixed(2),
          width:  +((node.width()  * scaleX) / PX_PER_CM).toFixed(2),
          height: +((node.height() * scaleY) / PX_PER_CM).toFixed(2),
        },
      });
    }

    transformer.on("transformend", handleTransformEnd);
    return () => { transformer.off("transformend", handleTransformEnd); };
  }, [pageLeft, pageTop, updateComponent]);

  return (
    <div className={`relative overflow-auto bg-slate-200 dark:bg-slate-950 rounded-lg flex justify-center items-start ${className}`}>
      {/* Badge modo preview (solo en el editor standalone, no en PreviewStep) */}
      {!interactive && !isEditMode && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 px-2.5 py-1 bg-amber-500 text-white text-[10px] font-semibold rounded-full shadow pointer-events-none">
          Vista previa — {activeFormat.toUpperCase()} (solo lectura)
        </div>
      )}
      <div ref={containerRef} />
    </div>
  );
}
