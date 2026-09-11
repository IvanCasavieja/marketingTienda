/**
 * Dibuja en Konva los pedazos que arma textoEnriquecido.ts: un cuadro de
 * texto cuyos segmentos tienen tamaños, pesos, colores o voladitas distintos.
 * Konva.Text no admite estilos mezclados, así que se pinta con un Shape que
 * escribe cada pedazo en su lugar.
 */
import Konva from "konva";
import { diagramarTramos, type OpcionesDiagrama, type Tramo } from "@/lib/cenefas/textoEnriquecido";

let contextoDeMedida: CanvasRenderingContext2D | null = null;

function contexto(): CanvasRenderingContext2D | null {
  if (!contextoDeMedida && typeof document !== "undefined") {
    contextoDeMedida = document.createElement("canvas").getContext("2d");
  }
  return contextoDeMedida;
}

function medir(texto: string, font: string): number {
  const ctx = contexto();
  if (!ctx) return 0;
  ctx.font = font;
  return ctx.measureText(texto).width;
}

// Igual que Konva.Text: ascendente y descendente de la caja de la fuente sobre
// una "M", y si el navegador no los informa, los de la letra.
function metricas(font: string): { ascent: number; descent: number } {
  const ctx = contexto();
  if (!ctx) return { ascent: 0, descent: 0 };
  ctx.font = font;
  const m = ctx.measureText("M");
  return {
    ascent: Number.isFinite(m.fontBoundingBoxAscent) ? m.fontBoundingBoxAscent : m.actualBoundingBoxAscent,
    descent: Number.isFinite(m.fontBoundingBoxDescent) ? m.fontBoundingBoxDescent : m.actualBoundingBoxDescent,
  };
}

export function nodoTextoEnriquecido(
  tramos: Tramo[],
  opciones: Omit<OpcionesDiagrama, "medir" | "metricas">,
): Konva.Shape {
  const { piezas, alto } = diagramarTramos(tramos, { ...opciones, medir, metricas });
  return new Konva.Shape({
    x: 0,
    y: 0,
    width: opciones.anchoPx,
    height: alto,
    // Sin alto fijo ni recorte A PROPÓSITO, igual que el Konva.Text del
    // canvas: si el texto no entra tiene que VERSE desbordando.
    listening: false,
    sceneFunc: (context) => {
      context.setAttr("textBaseline", "alphabetic");
      context.setAttr("textAlign", "left");
      for (const p of piezas) {
        context.setAttr("font", p.font);
        context.setAttr("fillStyle", p.color);
        context.fillText(p.texto, p.x, p.y);
        if (p.tachado) {
          const yTachado = p.y - Math.round(p.sizePx / 4);
          context.beginPath();
          context.moveTo(p.x, yTachado);
          context.lineTo(p.x + p.ancho, yTachado);
          context.setAttr("strokeStyle", p.color);
          context.setAttr("lineWidth", p.sizePx / 15);
          context.stroke();
        }
      }
    },
  });
}
