"use client";
import { useEffect, useRef, useState } from "react";
import { Stage, Layer, Rect, Text, Group, Transformer, Image as KonvaImage } from "react-konva";
import type Konva from "konva";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent } from "@/types/cenefas";

// ---------------------------------------------------------------------------
// Constantes de escala y dimensiones de formatos
// ---------------------------------------------------------------------------

const PX_PER_CM = 28;

const FORMAT_DIMS: Record<string, { w: number; h: number }> = {
  a4:      { w: 21.0, h: 29.7 },
  a3:      { w: 29.7, h: 42.0 },
  "3xa4":  { w: 63.0, h: 29.7 },
  pinchos: { w: 10.5, h: 29.7 },
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
// Componente principal
// ---------------------------------------------------------------------------

interface CanvasProps { className?: string }

export default function Canvas({ className = "" }: CanvasProps) {
  const { template, activeFormat, selectedComponentId, selectComponent, updateComponent } =
    useEditorStore();

  const [mounted, setMounted] = useState(false);
  const transformerRef = useRef<Konva.Transformer>(null);
  const selectedRef    = useRef<Konva.Group>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!transformerRef.current) return;
    if (selectedRef.current && isEditMode) {
      transformerRef.current.nodes([selectedRef.current]);
    } else {
      transformerRef.current.nodes([]);
    }
    transformerRef.current.getLayer()?.batchDraw();
  });

  const masterFormat = template.master_format;
  const isEditMode   = activeFormat === masterFormat;
  const dims         = FORMAT_DIMS[activeFormat] ?? FORMAT_DIMS.a4;
  const pageW        = scalePx(dims.w);
  const pageH        = scalePx(dims.h);
  const margin       = 40;
  const stageW       = pageW + margin * 2;
  const stageH       = pageH + margin * 2;
  const pageLeft     = margin;
  const pageTop      = margin;

  // Aplicar layout del formato activo para la vista previa
  const displayComps = applyFormatLayout(
    [...template.components].sort((a, b) => a.z_index - b.z_index),
    activeFormat,
    masterFormat,
  );

  if (!mounted) {
    return (
      <div
        className={`bg-slate-100 rounded-lg flex items-center justify-center ${className}`}
        style={{ width: stageW, height: stageH }}
      />
    );
  }

  return (
    <div className={`relative overflow-auto bg-slate-200 rounded-lg ${className}`}>
      {/* Badge modo preview */}
      {!isEditMode && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 px-2.5 py-1 bg-amber-500 text-white text-[10px] font-semibold rounded-full shadow pointer-events-none">
          Vista previa — {activeFormat.toUpperCase()} (solo lectura)
        </div>
      )}

      <Stage
        width={stageW}
        height={stageH}
        onMouseDown={(e) => {
          if (e.target === e.target.getStage()) selectComponent(null);
        }}
      >
        {/* Fondo de la página */}
        <Layer>
          <Rect x={pageLeft + 4} y={pageTop + 4} width={pageW} height={pageH}
            fill="rgba(0,0,0,0.08)" cornerRadius={2} />
          <Rect x={pageLeft} y={pageTop} width={pageW} height={pageH}
            fill="white" stroke="#cbd5e1" strokeWidth={1} cornerRadius={2}
            onClick={() => selectComponent(null)} />
          <Text x={pageLeft} y={pageTop - 22}
            text={`${activeFormat.toUpperCase()}  ${dims.w}×${dims.h} cm`}
            fontSize={10} fill="#94a3b8" fontFamily="Inter, system-ui, sans-serif" />
        </Layer>

        {/* Componentes */}
        <Layer>
          {displayComps.map((comp) => (
            <ComponentShape
              key={comp.id}
              comp={comp}
              pageLeft={pageLeft}
              pageTop={pageTop}
              isSelected={comp.id === selectedComponentId && isEditMode}
              shapeRef={comp.id === selectedComponentId && isEditMode ? selectedRef : undefined}
              draggable={isEditMode && !comp.locked}
              onSelect={() => { if (isEditMode) selectComponent(comp.id); }}
              onDragEnd={(x, y) => {
                const newX = +Math.max(0, Math.min((x - pageLeft) / PX_PER_CM, dims.w - comp.base_bounds.width)).toFixed(2);
                const newY = +Math.max(0, Math.min((y - pageTop)  / PX_PER_CM, dims.h - comp.base_bounds.height)).toFixed(2);
                updateComponent(comp.id, {
                  base_bounds: { ...comp.base_bounds, x: newX, y: newY },
                });
              }}
            />
          ))}

          <Transformer
            ref={transformerRef}
            rotateEnabled={false}
            boundBoxFunc={(old, next) =>
              next.width < 20 || next.height < 10 ? old : next
            }
            onTransformEnd={() => {
              const node = selectedRef.current;
              if (!node) return;
              const scaleX = node.scaleX();
              const scaleY = node.scaleY();
              node.scaleX(1);
              node.scaleY(1);
              const comp = template.components.find((c) => c.id === selectedComponentId);
              if (!comp) return;
              updateComponent(comp.id, {
                base_bounds: {
                  x:      +((node.x() - pageLeft) / PX_PER_CM).toFixed(2),
                  y:      +((node.y() - pageTop)  / PX_PER_CM).toFixed(2),
                  width:  +((node.width()  * scaleX) / PX_PER_CM).toFixed(2),
                  height: +((node.height() * scaleY) / PX_PER_CM).toFixed(2),
                },
              });
            }}
          />
        </Layer>
      </Stage>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shape individual
// ---------------------------------------------------------------------------

interface ComponentShapeProps {
  comp:       CenefaComponent;
  pageLeft:   number;
  pageTop:    number;
  isSelected: boolean;
  draggable:  boolean;
  shapeRef?:  React.RefObject<Konva.Group>;
  onSelect:   () => void;
  onDragEnd:  (x: number, y: number) => void;
}

function useBase64Image(imageData?: string, imageExt?: string) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!imageData) { setImg(null); return; }
    const el = new window.Image();
    el.src = `data:image/${imageExt ?? "png"};base64,${imageData}`;
    el.onload  = () => setImg(el);
    el.onerror = () => setImg(null);
    return () => { el.onload = null; el.onerror = null; };
  }, [imageData, imageExt]);
  return img;
}

function ComponentShape({
  comp, pageLeft, pageTop, isSelected, draggable, shapeRef, onSelect, onDragEnd,
}: ComponentShapeProps) {
  const color = COMP_COLORS[comp.type] ?? "#64748b";
  const b     = comp.base_bounds;
  const x     = pageLeft + scalePx(b.x);
  const y     = pageTop  + scalePx(b.y);
  const w     = Math.max(scalePx(b.width),  20);
  const h     = Math.max(scalePx(b.height), 10);

  const loadedImg = useBase64Image(comp.image_data, comp.image_ext);

  return (
    <Group
      ref={shapeRef as React.RefObject<Konva.Group> | undefined}
      x={x} y={y} width={w} height={h}
      draggable={draggable}
      onClick={onSelect}
      onTap={onSelect}
      onDragEnd={(e) => onDragEnd(e.target.x(), e.target.y())}
    >
      {/* Imagen real cuando está disponible */}
      {loadedImg ? (
        <>
          <KonvaImage
            image={loadedImg}
            width={w} height={h}
            cornerRadius={comp.locked ? 0 : 2}
          />
          {/* Borde de selección encima de la imagen */}
          {isSelected && (
            <Rect width={w} height={h}
              fill="transparent"
              stroke={color} strokeWidth={2}
              cornerRadius={2}
            />
          )}
          {/* Borde tenue cuando no está seleccionado pero es un componente editable */}
          {!isSelected && !comp.locked && (
            <Rect width={w} height={h}
              fill="transparent"
              stroke={`${color}55`} strokeWidth={1}
              dash={[4, 3]}
            />
          )}
        </>
      ) : (
        /* Placeholder coloreado para imágenes sin datos o shapes/textos */
        <>
          <Rect
            width={w} height={h}
            fill={
              comp.type === "shape" && comp.style?.background_color
                ? comp.style.background_color
                : `${color}22`
            }
            stroke={isSelected ? color : `${color}88`}
            strokeWidth={isSelected ? 2 : 1}
            cornerRadius={3}
            dash={comp.locked ? [4, 3] : undefined}
          />
          <Text
            x={4} y={4} width={w - 8} height={h - 8}
            text={
              comp.variable
                ? `${comp.name}\n(${comp.variable})`
                : comp.static_value
                  ? `"${comp.static_value.length > 24 ? comp.static_value.slice(0, 22) + "…" : comp.static_value}"`
                  : comp.name
            }
            fontSize={Math.min(11, Math.max(7, h / 2.5))}
            fill={comp.type === "shape" && comp.style?.background_color ? "#00000055" : color}
            fontFamily="Inter, system-ui, sans-serif"
            ellipsis wrap="word"
          />
        </>
      )}
    </Group>
  );
}
