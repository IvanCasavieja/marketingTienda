"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import { useEditorStore } from "@/store/editor";
import type { CenefaComponent, CenefaRule, CenefaTemplate, TextSegment } from "@/types/cenefas";
import { buildSiblingMap } from "@/lib/cenefas/siblingMap";
// Con alias: `segmentosOcultos` es además el nombre de la prop que recibe
// buildComponentGroup más abajo, y ahí la prop tapa a la función.
import {
  cuadrosOcultos as evaluarCuadrosOcultos,
  segmentosOcultos as evaluarSegmentosOcultos,
  tamanosDeCuadro,
  tamanosDeSegmento,
  aplicarTamanos,
} from "@/lib/cenefas/reglas";
import { resolverFuente } from "@/lib/cenefas/fuentes";
import { mascaraNegrita, tieneMarca } from "@/lib/cenefas/smartBold";
import { tramosConEstiloPropio } from "@/lib/cenefas/textoEnriquecido";
import { nodoTextoEnriquecido } from "@/lib/cenefas/dibujarTextoEnriquecido";
import { cargarReglasDeMedicion, reglas } from "@/lib/cenefas/reglasDeMedicion";
import {
  cargarFormatosDeHoja,
  celdaDelFormato,
  formatoConocido,
  papelDeLaPlantilla,
  ruidoEmuCm,
} from "@/lib/cenefas/formatosDeHoja";

// ---------------------------------------------------------------------------
// Constantes de escala y dimensiones de formatos
// ---------------------------------------------------------------------------

const PX_PER_CM = 28;

// ACA HABIA UNA TABLA DE TAMAÑOS DE HOJA ESCRITA A MANO, y era una de cinco:
// las otras estaban en layout_engine.FORMATS, component_renderer.FORMAT_SLIDES,
// pptx_importer._FORMATS_DIM y las etiquetas del panel de importación. Tres de
// los seis formatos tenían números DISTINTOS según a cuál se le preguntara,
// porque unas decían el PAPEL que sale de la impresora y otras la CELDA que
// ocupa una cenefa adentro de él, y las dos cosas se llamaban igual ("3xa4").
// Esta copia tenía la semántica de celda, así que el preview de un "3xa4"
// dibujaba una franja de 21×9,9 cm mientras la impresora sacaba una A4 entera.
// Y encima la orientación estaba mal: la 6xA4 es una A4 HORIZONTAL y la A5 son
// DOS cenefas una al lado de la otra (Ivan, 22/09/2026).
//
// Ahora el tamaño vive en backend/app/data/formatos_de_hoja.json y se lee con
// lib/cenefas/formatosDeHoja.ts. Hay un barrido que falla si vuelve a
// aparecer un número de hoja escrito a mano: backend/tests/test_hoja_unica.py.

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
// Cuándo corresponde el bold automático de marcas. Hoy las 43 cajas que lo
// usan en la base lo declaran a nivel de COMPONENTE sobre <<descripcion>>, y
// no hay ninguna con segmentos mezclados (unos con smart_bold y otros con
// otra transformación). Se contempla igual el caso por segmento, exigiendo
// que NINGÚN otro segmento pida una transformación distinta -- si algún día
// aparece uno mezclado, el preview se abstiene en vez de resaltar mayúsculas
// que el export no va a resaltar.
function aplicaSmartBold(comp: CenefaComponent): boolean {
  // La negrita puesta a mano en la caja le gana a la automática: si está
  // tildada, va todo en negrita y no hay nada que resaltar aparte. Mismo
  // criterio que _populate_text_frame en el motor y que tramosConEstiloPropio
  // -- los tres tienen que decidir igual o el preview vuelve a mentir.
  if (comp.style?.font_bold) return false;
  if (comp.transform === "smart_bold") return true;
  const segs = comp.segments ?? [];
  if (!segs.some((s) => s.transform === "smart_bold")) return false;
  return !segs.some((s) => s.transform && s.transform !== "smart_bold" && s.transform !== "none");
}

function ptToPx(pt: number) {
  return (pt / 72) * 2.54 * PX_PER_CM;
}

// Dónde queda un cuadro que se soltó, en cm sobre un eje del papel.
//
// Un cuadro que ENTRA en la hoja se acomoda para no quedar afuera: es lo que
// se espera al arrastrar. Pero un cuadro MÁS GRANDE que la hoja no puede
// entrar, y la cuenta de siempre (`max(0, min(x, hoja - ancho))`) lo mandaba
// a x = 0 en cada soltada: la caja invisible de 44 cm centrada en una A4 --el
// truco para que el precio no se corra según cuántos dígitos tenga-- se
// descentraba 11 cm con solo tocarla. Eso era acomodar el diseño sin que
// nadie lo pidiera. Si no entra, queda donde se soltó, y se ve saliéndose.
function dentroDelPapel(valor: number, tamano: number, hoja: number): number {
  if (tamano > hoja) return valor;
  return Math.max(0, Math.min(valor, hoja - tamano));
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

  // La CELDA de cada formato --lo que ocupa UNA cenefa--, que es lo que
  // compute_layout usa del otro lado para escalar el mismo diseño de un
  // formato a otro. Sale de la tabla única, igual que allá.
  const master = celdaDelFormato(masterFormat);
  const target = celdaDelFormato(activeFormat);
  const scaleX = target.ancho / master.ancho;
  const scaleY = target.alto  / master.alto;

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

// Vinculación por variable entre bandas — compartida con PropertiesPanel.tsx
// (ver lib/cenefas/siblingMap.ts): las dos vías de editar un cuadro, arrastre
// en el canvas y tipeo numérico en el panel, tienen que vincular exactamente
// igual, si no un cuadro editado a mano en el panel queda desalineado del
// resto aunque el arrastre con el mouse sí lo hubiera vinculado.

// Texto de UN segmento con datos reales. Lo usan el texto del cuadro entero y
// el dibujo pedazo por pedazo (ver textoEnriquecido.ts), que tienen que
// resolverlo exactamente igual.
function textoDeSegmento(
  seg: TextSegment,
  indice: number,
  previewData: Record<string, string>,
  segmentosOcultos?: Set<number>,
): string {
  // Un segmento ocultado por una regla se dibuja VACÍO, no se saca:
  // mismo criterio que `apply_visibility` en el backend, que lo
  // reemplaza por un estático vacío para que el resto del motor lo vea
  // como "sin dato" y no se entere de que hubo una regla.
  if (segmentosOcultos?.has(indice)) return "";
  if (seg.type === "static") return seg.value;
  return applyTransform(previewData[seg.value] ?? "", seg.transform);
}

/** Los rellenos de capacidad de ESTE cuadro, uno por segmento, o null.
 *
 *  El backend solo los manda para los cuadros de 2 o mas segmentos; para
 *  todos los demas --casi todos-- devuelve nada y sigue mandando una sola
 *  tira por cuadro en `capacidad`. */
function rellenosDeSegmentos(
  comp: CenefaComponent,
  capacidadSegmentos?: Record<string, string[]> | null,
): string[] | null {
  const rellenos = capacidadSegmentos?.[comp.id];
  if (!rellenos?.length || !comp.segments?.length) return null;
  return rellenos;
}

/** Texto de UN segmento en la vista de capacidad. Espejo de textoDeSegmento,
 *  pero el texto no sale del producto sino del relleno que calculo el backend
 *  para ESE segmento, con SU cuerpo. */
function textoDeSegmentoCapacidad(
  seg: TextSegment,
  indice: number,
  rellenos: string[],
  segmentosOcultos?: Set<number>,
): string {
  // Las reglas de visibilidad las conoce el front, no el endpoint de
  // capacidad: un segmento tapado por una regla se dibuja vacio igual que con
  // datos reales.
  if (segmentosOcultos?.has(indice)) return "";
  const relleno = rellenos[indice];
  // Se respeta el "" que mande el backend (ej. un segmento que no se rellena).
  // Si directamente falta --array mas corto de lo esperado-- el estatico cae
  // en su literal: mejor ver el "de" o el "$" del diseno que un hueco.
  if (relleno !== undefined) return relleno;
  return seg.type === "static" ? seg.value : "";
}

// Resuelve el texto a mostrar cuando hay datos reales (previewData),
// aplicando el mismo transform por segmento/componente que usa el render
// final (_populate_text_frame en component_renderer.py).
function resolveComponentText(
  comp: CenefaComponent,
  previewData: Record<string, string>,
  capacidad?: Record<string, string> | null,
  segmentosOcultos?: Set<number>,
  rellenoSegs?: string[] | null,
): string {
  // Capacidad POR SEGMENTO: cada pedazo con su propio relleno, medido con su
  // propio cuerpo. Manda sobre la tira del cuadro entero, que para estos
  // cuadros se calcula con el cuerpo MAXIMO de los segmentos y por eso llenaba
  // la caja de digitos gigantes: en "Fiesta Alemania-202608-A4" el precio es
  // un solo cuadro con unidadMoneda + precioOferta + decimalPrecioOferta, y
  // asi el decimal no se veia nunca (Ivan, 18/09/2026).
  if (rellenoSegs) {
    return (comp.segments ?? [])
      .map((seg, i) => textoDeSegmentoCapacidad(seg, i, rellenoSegs, segmentosOcultos))
      .join("");
  }
  // Vista de capacidad: el cuadro se muestra LLENO de "X" hasta donde entra,
  // en vez del valor del primer producto del Excel. Sirve para ver el peor
  // caso antes de tener el dato -- y para que aparezcan las variables que ese
  // producto no trae (el decimal, cuando el primer precio es redondo).
  const relleno = capacidad?.[comp.id];
  if (relleno) return relleno;
  if (comp.segments?.length) {
    return comp.segments
      .map((seg, i) => textoDeSegmento(seg, i, previewData, segmentosOcultos))
      .join("");
  }
  if (comp.variable) return applyTransform(previewData[comp.variable] ?? comp.static_value ?? "", comp.transform);
  return comp.static_value ?? "";
}

function buildComponentGroup({
  comp, pageLeft, pageTop, isSelected, draggable, image, previewData, capacidad,
  capacidadSegmentos, ocultoPorRegla, segmentosOcultos, onSelect, onDragEnd,
}: {
  comp: CenefaComponent;
  pageLeft: number;
  pageTop: number;
  isSelected: boolean;
  draggable: boolean;
  image?: HTMLImageElement;
  previewData?: Record<string, string>;
  capacidad?: Record<string, string> | null;
  /** Relleno de capacidad por segmento, solo para los cuadros de 2+ segmentos. */
  capacidadSegmentos?: Record<string, string[]> | null;
  /** Una regla de visibilidad lo saca de ESTA cenefa. Se sigue dibujando —
   *  como silueta, sin contenido— en vez de desaparecer: si desapareciera no
   *  habría forma de seleccionarlo para revisar o borrar la regla que lo
   *  oculta, y el hueco en el diseño no se distinguiría de un error. */
  ocultoPorRegla?: boolean;
  /** Índices de segmento que una regla oculta dentro de este cuadro. */
  segmentosOcultos?: Set<number>;
  /** `conCtrl` = el click traía Ctrl/Cmd apretado (selección múltiple). */
  onSelect: (conCtrl: boolean) => void;
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
  // metaKey además de ctrlKey: en Mac el modificador de "sumar a la selección"
  // es Cmd, y el navegador no lo reporta como ctrlKey.
  group.on("click tap", (e) => {
    const evt = e.evt as MouseEvent | undefined;
    onSelect(!!evt && (evt.ctrlKey || evt.metaKey));
  });
  group.on("dragend", (e) => onDragEnd(e.target.x(), e.target.y()));

  // Ocultado por una regla: silueta punteada y nada adentro. Es lo que va a
  // pasar de verdad al generar (el motor le saca el shape al slide), y verlo
  // acá es todo el punto de que las reglas existan -- hasta el 09/09/2026 el
  // canvas las ignoraba y agregar una no cambiaba nada en pantalla.
  if (ocultoPorRegla) {
    group.add(new Konva.Rect({
      width: w, height: h, fill: "transparent",
      stroke: "#f43f5e", strokeWidth: 1, dash: [3, 3], cornerRadius: 3, opacity: 0.55,
    }));
    if (h >= 16) {
      group.add(new Konva.Text({
        x: 3, y: 2, width: Math.max(0, w - 6), text: "oculto por regla",
        fontSize: 9, fill: "#f43f5e", opacity: 0.75, ellipsis: true, wrap: "none",
        fontFamily: "Inter, system-ui, sans-serif",
      }));
    }
    return group;
  }

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

  // Relleno de capacidad segmento por segmento. Null para todo lo demas: los
  // cuadros de una sola variable --casi todos-- siguen con la tira de
  // `capacidad`, exactamente igual que antes.
  const rellenoSegs = rellenosDeSegmentos(comp, capacidadSegmentos);

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
        ? resolveComponentText(comp, previewData, capacidad, segmentosOcultos, rellenoSegs)
        : comp.segments?.length
          ? `${comp.name}\n${comp.segments.map((s) => s.type === "static" ? `"${s.value}"` : `{${s.value}}`).join(" + ")}`
          : comp.variable
            ? `${comp.name}\n(${comp.variable})`
            : comp.static_value
              ? `"${comp.static_value.length > 24 ? comp.static_value.slice(0, 22) + "…" : comp.static_value}"`
              : comp.name;

  if (fiel) {
    // Cuadro compuesto cuyos pedazos NO comparten el estilo de la caja: el
    // "$" y los centavos más chicos y arriba (Rompe Precios A4: "$ 250 ,85"
    // se veía todo a 130 pt), una parte en negrita, o un tamaño puesto a mano
    // en un segmento. El PPTX arma un run por segmento con su propio estilo y
    // Konva.Text no admite estilos mezclados: se dibuja pedazo por pedazo.
    // Todos los demás cuadros siguen por el Konva.Text de abajo, sin cambios.
    //
    // La vista de capacidad SÍ pasa por acá cuando el backend mandó un relleno
    // por segmento (`capacidadSegmentos`). Antes no: el cuadro se reemplazaba
    // por una tira de "X" de un solo estilo, y en "Fiesta Alemania-202608-A4"
    // --un solo cuadro con unidadMoneda (60 pt) + precioOferta (140) +
    // decimalPrecioOferta (36)-- esa tira se calculaba con el cuerpo más
    // grande y se comía la caja entera: el decimal no se dibujaba nunca con su
    // tamaño, así que no había con qué verlo ni cómo acomodarlo (reportado por
    // Ivan, 18/09/2026). Con los rellenos por segmento el cuadro se dibuja
    // igual que con datos reales, cada pedazo con su cuerpo y su voladita.
    //
    // Sin `capacidadSegmentos` --el resto de las plantillas-- la vista de
    // capacidad sigue siendo la tira de siempre.
    const datos = previewData;
    const tramos = datos && comp.segments?.length && (rellenoSegs || !capacidad?.[comp.id])
      ? tramosConEstiloPropio(comp, rellenoSegs
          ? (seg, i) => textoDeSegmentoCapacidad(seg, i, rellenoSegs, segmentosOcultos)
          : (seg, i) => textoDeSegmento(seg, i, datos, segmentosOcultos))
      : null;
    // EL MARGEN INTERNO. PowerPoint reserva 0,254 cm a cada lado adentro de
    // todo cuadro de texto (lIns/rIns) y el texto nunca llega al borde: el
    // exportador lo descuenta antes de decidir dónde corta una palabra
    // (_estimate_wrapped_lines en component_renderer.py). Hasta el 18/09/2026
    // el preview NO lo descontaba --dibujaba con el ancho entero de la caja--
    // así que en pantalla el texto cortaba una palabra MÁS TARDE que en el
    // papel, en todos los cuadros de texto de todas las plantillas. Y no había
    // test que lo agarrara, porque de este lado el número directamente no
    // existía: no había dos valores que comparar.
    //
    // El número sale del archivo único de reglas, nunca escrito acá.
    const insetPx = reglas().insetCm * PX_PER_CM;
    const anchoUtilPx = Math.max(1, w - insetPx);

    if (tramos) {
      group.add(nodoTextoEnriquecido(tramos, {
        anchoPx: anchoUtilPx,
        align: comp.style?.align ?? "center",
        lineHeightPt: comp.style?.line_height_pt,
        ptToPx,
      }));
      return group;
    }

    // El cuerpo viaja en puntos; el canvas trabaja en px a PX_PER_CM. El
    // tamaño que se asume cuando el cuadro no declara ninguno sale del archivo
    // único de reglas: es el mismo con el que el exportador mide.
    const pt = comp.style?.font_size ?? reglas().ptPorDefecto;
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
    const fuente = resolverFuente(comp.style?.font_family, comp.style?.font_bold);
    const nodoTexto = new Konva.Text({
      // `x: insetPx / 2` y no 0: PowerPoint mete la mitad del margen de cada
      // lado, así que el texto queda centrado igual que en el PPTX. Este es el
      // camino por el que va la MAYORÍA de los cuadros (los de un solo
      // estilo); arreglar solo el del texto enriquecido los dejaba mintiendo.
      x: insetPx / 2, y: offsetY, width: anchoUtilPx,
      text,
      fontSize: fontSizePx,
      // PowerPoint mete el peso adentro del nombre ("Libre Franklin Black"
      // es Libre Franklin en 900). Konva arma la cadena `font` del canvas
      // como `fontStyle fontVariant fontSize px fontFamily`, asi que el peso
      // numerico va en fontStyle -- "900 normal 40px Libre Franklin" es
      // shorthand CSS valido. Ver lib/cenefas/fuentes.ts.
      fontFamily: fuente.stack,
      fontStyle: String(fuente.weight),
      fill: comp.style?.color ?? "#1e293b",
      align: comp.style?.align ?? "center",
      lineHeight: reglas().altoDeLinea,
      textDecoration: comp.style?.strikethrough ? "line-through" : undefined,
      wrap: "word",
      // Sin ellipsis y sin alto fijo A PROPÓSITO: si el texto no entra tiene
      // que VERSE desbordando, que es justamente lo que hay que detectar.
      listening: false,
    });

    // "Bold automático (MARCAS)": la marca va en negrita dentro de una
    // descripción que no lo está. El PPTX exportado ya salía así --el backend
    // parte el texto en runs y le pone negrita al de mayúsculas-- pero el
    // preview dibujaba todo con un peso solo y la marca se veía igual que el
    // resto. Konva no admite estilos mezclados en un mismo Text, pero sí deja
    // tocar el contexto antes de pintar cada carácter (charRenderFunc), que
    // es justo lo que hace falta.
    //
    // La máscara se calcula sobre el RENGLÓN YA CORTADO, no sobre el texto
    // entero: Konva descarta el espacio donde parte la línea y los índices se
    // corren uno por salto. Se cachea por texto de renglón, no por número,
    // para que siga valiendo si cambia el corte.
    //
    // Solo se activa si de verdad hay mayúsculas: dibujar carácter por
    // carácter pierde el kerning entre letras, y no tiene sentido pagarlo en
    // un cuadro donde no va a haber ninguna negrita.
    if (aplicaSmartBold(comp) && tieneMarca(text)) {
      const cacheLineas = new Map<string, boolean[]>();
      const pesoNegrita = Math.min(900, fuente.weight + 300);
      nodoTexto.charRenderFunc(({ lineIndex, column, context }) => {
        const linea = nodoTexto.textArr?.[lineIndex]?.text ?? "";
        let mascara = cacheLineas.get(linea);
        if (!mascara) { mascara = mascaraNegrita(linea); cacheLineas.set(linea, mascara); }
        if (mascara[column]) {
          context.setAttr("font", `${pesoNegrita} normal ${fontSizePx}px ${fuente.stack}`);
        }
      });
    }

    group.add(nodoTexto);
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
  /** Selección múltiple (Ctrl/Cmd + click). Sin esto, el canvas se comporta
   *  como siempre: un cuadro por vez. Quien la pase tiene que pasar TAMBIÉN
   *  onToggleComponentSelection, si no el Ctrl no tiene dónde escribir. */
  selectedComponentIds?: string[];
  onToggleComponentSelection?: (id: string) => void;
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
  /** Relleno de "X" por componente (ver /capacidad). Cuando viene, cada
   *  cuadro rellenable se dibuja lleno hasta donde entra en vez de mostrar
   *  el valor del primer producto. */
  capacidad?: Record<string, string> | null;
  /** Relleno de capacidad POR SEGMENTO (ver /capacidad, clave `segmentos`).
   *  Solo viene para los cuadros de 2 o más segmentos: ahí la tira única de
   *  `capacidad` se calcula con el cuerpo más grande del cuadro y tapa a los
   *  pedazos chicos (el decimal de la Alemania A4). Con esto el cuadro se
   *  dibuja por segmentos, cada uno con su relleno y su cuerpo. */
  capacidadSegmentos?: Record<string, string[]> | null;
  /** Reglas de visibilidad de la plantilla. Solo tienen efecto cuando además
   *  hay `previewData`: sin datos reales no hay contra qué evaluarlas, y en
   *  el editor sin datos ocultar cuadros dejaría medio diseño invisible y sin
   *  forma de seleccionarlo. Sin la prop se usan las de `template.rules`. */
  rules?: CenefaRule[];
}

export default function Canvas({
  className = "",
  template: propTemplate,
  activeFormat: propActiveFormat,
  selectedComponentId: propSelectedComponentId,
  onSelectComponent,
  selectedComponentIds: propSelectedComponentIds,
  onToggleComponentSelection,
  onUpdateComponent,
  previewData,
  slotBands: propSlotBands,
  previewProducts,
  capacidad,
  capacidadSegmentos,
  rules: propRules,
}: CanvasProps) {
  const store = useEditorStore();
  const template             = propTemplate ?? store.template;
  const activeFormat         = propActiveFormat ?? store.activeFormat;
  const selectedComponentId  = propSelectedComponentId !== undefined ? propSelectedComponentId : store.selectedComponentId;
  const selectComponent      = onSelectComponent ?? store.selectComponent;
  const updateComponent      = onUpdateComponent ?? store.updateComponent;
  // Quien controla la selección de afuera pero no pasó la lista (PreviewStep
  // hoy) sigue trabajando de a un cuadro: la lista es su cuadro primario.
  const seleccionControlada =
    propSelectedComponentId !== undefined || propSelectedComponentIds !== undefined;
  const selectedComponentIds =
    propSelectedComponentIds ??
    (seleccionControlada
      ? (propSelectedComponentId ? [propSelectedComponentId] : [])
      : store.selectedComponentIds);
  // El toggle del store solo sirve si la selección TAMBIÉN sale del store: si
  // la controla el que nos llama y no nos dio un toggle propio, escribir en el
  // store no se vería en pantalla y el Ctrl + click parecería no hacer nada.
  // Sin toggle, Ctrl + click cae en la selección simple de siempre.
  const toggleComponentSelection =
    onToggleComponentSelection ?? (seleccionControlada ? undefined : store.toggleComponentSelection);
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

  // Reglas de visibilidad aplicadas al dibujo. Cada banda se evalúa contra SU
  // producto: en una 3xA4 la cocarda puede corresponder en la primera cenefa y
  // no en la segunda, y mostrar las tres iguales sería mentir igual que no
  // aplicar nada.
  //
  // Solo con datos reales (`previewData`): en el editor de plantillas no hay
  // fila contra la cual evaluar, y ocultar cuadros ahí dejaría al diseño con
  // agujeros que además no se podrían ni seleccionar para sacarles la regla.
  // En su propio useMemo: sin esto, cuando ni la prop ni el template traen
  // reglas, el `?? []` fabrica un array nuevo en cada render y el memo de
  // abajo --y con él la capa de dibujo entera-- se recalcula siempre.
  const rules = useMemo(
    () => propRules ?? template.rules ?? [],
    [propRules, template.rules],
  );
  const reglasPorComp = useMemo(() => {
    const vacio = {
      ocultos: new Set<string>(), segmentos: new Map<string, Set<number>>(),
      tamanos: new Map<string, number>(), tamanosSeg: new Map<string, Map<number, number>>(),
    };
    if (!previewData || rules.length === 0) return vacio;
    const ocultos = new Set<string>();
    const segmentos = new Map<string, Set<number>>();
    // El cuerpo que declaran las reglas. Desde el 14/09/2026 es lo ÚNICO que
    // cambia un tamaño de letra: el achique automático se eliminó entero, así
    // que lo que se ve acá es exactamente lo que sale impreso.
    const tamanos = new Map<string, number>();
    const tamanosSeg = new Map<string, Map<number, number>>();

    // Se recorren las BANDAS, no los productos: la banda es la que dice qué
    // cuadros se evalúan contra qué fila. Al revés, un `previewProducts` más
    // largo que `slotBands` (o al contrario) hacía que una fila se evaluara
    // contra el conjunto entero de cuadros y ocultara los de otra cenefa.
    //
    // Igual que el motor, un cuadro que no pertenece a ninguna banda no recibe
    // reglas: en el render de una hoja multi-cenefa esos se dibujan aparte,
    // con la fila vacía y sin evaluar nada (ver bg_comps en
    // render_template_to_pptx).
    const evaluar = (ids: string[], fila: Record<string, string>) => {
      const deEstaBanda = new Set(ids);
      for (const id of evaluarCuadrosOcultos(rules, fila)) {
        if (deEstaBanda.has(id)) ocultos.add(id);
      }
      for (const [id, idx] of evaluarSegmentosOcultos(rules, fila)) {
        if (deEstaBanda.has(id)) segmentos.set(id, idx);
      }
      for (const [id, pt] of tamanosDeCuadro(rules, fila)) {
        if (deEstaBanda.has(id)) tamanos.set(id, pt);
      }
      for (const [id, porSeg] of tamanosDeSegmento(rules, fila)) {
        if (deEstaBanda.has(id)) tamanosSeg.set(id, porSeg);
      }
    };

    if (slotBands?.length) {
      slotBands.forEach((ids, i) => evaluar(ids, previewProducts?.[i] ?? previewData));
    } else {
      evaluar(template.components.map((c) => c.id), previewData);
    }
    return { ocultos, segmentos, tamanos, tamanosSeg };
  }, [rules, previewData, previewProducts, slotBands, template.components]);

  const wrapperRef       = useRef<HTMLDivElement>(null);
  const [wrapperWidth,  setWrapperWidth]  = useState<number | null>(null);
  const [wrapperHeight, setWrapperHeight] = useState<number | null>(null);

  // Espacio disponible del contenedor scrolleable, para el zoom automático de
  // más abajo -- se re-mide solo (ResizeObserver), sin depender de un resize
  // de la ventana entera: alcanza con que el usuario abra/cierre un panel
  // lateral para que esto cambie.
  //
  // El ALTO hace falta tanto como el ancho: hasta el 14/09/2026 solo se medía
  // el ancho y la hoja se agrandaba hasta llenarlo, quedando más alta que el
  // contenedor. Una A4 salía cortada por abajo y había que scrollear para ver
  // el cartel entero, que es justo lo que un preview no tiene que obligarte a
  // hacer (reportado por Ivan: "la idea es que se vea entera").
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setWrapperWidth(r.width);
      setWrapperHeight(r.height);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

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

  // LA PUERTA DE LA MEDICION. Canvas es el unico lugar por el que se dibuja
  // una cenefa (lo importan v2/page.tsx, PreviewStep y LotePreviewStep, y
  // nada mas dibuja), asi que con esperar aca alcanza para garantizar que
  // ningun cuadro se mida con un numero adivinado.
  //
  // Son DOS archivos del backend y los dos se piden por HTTP:
  //
  //   - las REGLAS de medicion (app/data/reglas_de_medicion.json): el margen
  //     interno, el alto de linea, la voladita, el tamano por defecto;
  //   - el TAMANO DE HOJA (app/data/formatos_de_hoja.json): cuanto mide el
  //     PAPEL que sale de la impresora, que hasta el 22/09/2026 este archivo
  //     tenia copiado a mano --y ademas AGRANDABA hasta que le entrara el
  //     contenido, por eso un cuadro fuera de la hoja se veia adentro.
  //
  // Van juntas en un Promise.all: se necesitan las dos al mismo tiempo, son
  // dos requests en paralelo y una sola espera. (Son dos endpoints y no uno
  // porque cada uno devuelve SU archivo tal cual; el porque completo esta en
  // el docstring de get_formatos_de_hoja, en cenefas_v2.py.)
  //
  // Si no llegan, NO se dibuja: se muestra un cartel. Dibujar con valores
  // propios es exactamente el bug que esto viene a matar, y ademas el editor
  // ya no funciona sin backend (pide /formats al montar y /capacidad para el
  // relleno del preview), asi que no se pierde nada que hoy funcione.
  const [reglasListas, setReglasListas] = useState(false);
  const [errorReglas, setErrorReglas] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    Promise.all([cargarReglasDeMedicion(), cargarFormatosDeHoja()]).then(
      () => { if (vivo) { setErrorReglas(null); setReglasListas(true); } },
      (err) => { if (vivo) setErrorReglas(err?.message ?? String(err)); },
    );
    return () => { vivo = false; };
  }, []);

  const masterFormat = template.master_format;
  const isEditMode   = interactive || activeFormat === masterFormat;

  // EL FORMATO QUE DE VERDAD DECIDE EL PAPEL Y LA ESCALA. Con BANDAS (3xA4,
  // 6xA4, pinchos) el render ignora el formato destino: las celdas ya están
  // en coordenadas absolutas de la hoja del master y se imprimen tal cual
  // (`compute_layout(band, master, master)` en render_template_to_pptx, y
  // `como_se_imprimen` en la ruta del preview hace lo mismo para medir).
  // Hasta el 22/09/2026 acá se escalaba igual: una 3xA4 pedida como "a4" se
  // dibujaba estirada tres veces en alto mientras la impresora la sacaba
  // intacta. Sin bandas, el destino manda, como en el render.
  const formatoQueManda = slotBands?.length ? masterFormat : activeFormat;

  // Sin las tablas no se escala nada: applyFormatLayout le pide la CELDA de
  // cada formato a formatosDeHoja, que tira si todavía no llegó. Igual no se
  // dibuja hasta `reglasListas` (ver LA PUERTA, más arriba).
  const layoutComps = reglasListas
    ? applyFormatLayout(
        [...template.components].sort((a, b) => a.z_index - b.z_index),
        formatoQueManda,
        masterFormat,
      )
    : [];

  // -------------------------------------------------------------------------
  // EL PAPEL. No se deriva del contenido, NUNCA.
  // -------------------------------------------------------------------------
  //
  // ACÁ ESTABA LA MENTIRA. Estas cinco líneas decían, para toda plantilla con
  // varias bandas: `Math.max(ancho_de_la_hoja, ...borde_derecho_de_cada_cuadro)`.
  // O sea: si un cuadro se salía del papel, en vez de mostrarlo saliendo, SE
  // AGRANDABA EL PAPEL hasta que entrara. Por eso todo se veía adentro en
  // pantalla y salía cortado de la impresora. Ivan lo encontró el 18/09/2026
  // exportando una 3xA4 SOLO X 25: nueve de sus veinticuatro cuadros cruzan el
  // borde derecho y el peor termina en 24,588 cm sobre un papel de 21 -- el
  // mismo 24,588 que la etiqueta de abajo le mostraba como "el ancho de la
  // hoja".
  //
  // POR QUÉ ESTABA PUESTO, que es la parte que no se podía borrar y listo: hay
  // cuatro plantillas apaisadas (Preciazos A5 y 6xA4, Mega Rompe Precios A5 y
  // 6xA4) cuyo PPTX mide 29,7×21 cm y al importar detectaron el formato "a5"
  // (14,85×21, la mitad), porque _detect_format compara contra medidas de
  // CELDA y la tabla tenía la A5 parada y de una sola cenefa. Sin agrandar,
  // esas cuatro se dibujaban a media hoja. O sea que una sola línea tapaba DOS
  // cosas distintas: "la hoja está mal detectada" (agrandar era un parche
  // correcto en el lugar equivocado) y "el diseño se sale del papel" (había
  // que mostrarlo).
  //
  // Se separaron. El tamaño ya no se deduce de la etiqueta del formato: el
  // importador guarda la medida EXACTA del PPTX en `definition.hoja` --el
  // número que antes se leía y se tiraba-- y eso es lo que se dibuja, venga
  // la plantilla del formato que venga. Las cuatro apaisadas se dibujan enteras
  // porque su hoja mide 29,7×21 de verdad, no porque el lienzo las persiga.
  //
  // `papelDeLaPlantilla` es la única puerta y es el espejo exacto de
  // `hoja_de_definicion()` del backend, que es la que usa el aviso de desborde:
  // los dos miden contra el mismo papel o volveríamos a tener dos verdades.
  const papel = reglasListas ? papelDeLaPlantilla(template, formatoQueManda) : null;
  const dims = { w: papel?.anchoCm ?? 0, h: papel?.altoCm ?? 0 };

  const pageW        = scalePx(dims.w);
  const pageH        = scalePx(dims.h);
  const margin       = 40;

  // -------------------------------------------------------------------------
  // EL LIENZO ES OTRA COSA QUE EL PAPEL
  // -------------------------------------------------------------------------
  //
  // El papel es el papel y no se mueve. El LIENZO --el rectángulo donde Konva
  // puede dibujar-- sí crece, para que lo que se sale del papel se vea
  // saliendo en vez de desaparecer. Son dos cosas distintas y antes eran una
  // sola (`stageW = pageW + margin*2`), lo que daba la SEGUNDA cara del mismo
  // problema: en las plantillas sin bandas --A4 HELVETICO, Gran Bretaña A4,
  // Mega Rompe Precios A4-- el `Math.max` ni siquiera aplicaba, así que lo que
  // se salía quedaba directamente fuera del stage: invisible, sin hoja
  // inflada y sin aviso. A4 HELVETICO tiene dos cuadros que arrancan en
  // x = -11,74 cm y nadie los vio nunca.
  //
  // Se mide contra la CAJA declarada y no contra la tinta a propósito: acá no
  // se decide si algo está mal --eso lo dice el aviso del backend, que mide
  // tinta con la fila de datos real-- sino cuánto lugar hay que dejar para
  // poder MOSTRARLO. De lugar conviene pasarse, no quedarse corto.
  const sobra = { izq: 0, der: 0, arr: 0, aba: 0 };
  for (const c of layoutComps) {
    const b = c.base_bounds;
    sobra.izq = Math.max(sobra.izq, -b.x);
    sobra.arr = Math.max(sobra.arr, -b.y);
    sobra.der = Math.max(sobra.der, b.x + b.width  - dims.w);
    sobra.aba = Math.max(sobra.aba, b.y + b.height - dims.h);
  }
  // Un cuadro puede ser muchísimo más alto que la hoja sin que eso signifique
  // nada: PowerPoint deja cajas de texto enormes con el texto anclado arriba
  // (Mega Rompe Precios A4 tiene un precioOferta de 61,8 cm de alto sobre una
  // A4, o sea 52 cm por debajo del borde) y no se imprime nada cortado. Dejar
  // lugar para 52 cm de caja vacía dibujaría el cartel del tamaño de una
  // estampilla. Se muestra hasta media hoja de más por lado: alcanza para ver
  // que algo se sale y de qué lado, que es para lo que está.
  const TOPE_SOBRA = 0.5;
  const sobraIzq = scalePx(Math.min(sobra.izq, dims.w * TOPE_SOBRA));
  const sobraDer = scalePx(Math.min(sobra.der, dims.w * TOPE_SOBRA));
  const sobraArr = scalePx(Math.min(sobra.arr, dims.h * TOPE_SOBRA));
  const sobraAba = scalePx(Math.min(sobra.aba, dims.h * TOPE_SOBRA));
  // Con el piso del ruido de EMU: el papel mide 20,999 y el fondo de
  // Preciazos A5 llega a 21,0 -- eso no es salirse, es cómo redondea
  // PowerPoint, y pintaba la mesa gris en una plantilla que está bien.
  const ruido    = reglasListas ? ruidoEmuCm() : 0;
  const seSale   = sobra.izq > ruido || sobra.der > ruido || sobra.arr > ruido || sobra.aba > ruido;

  // QUIÉN se sale, POR DÓNDE y CUÁNTO, con nombre. El tope de arriba tiene
  // una consecuencia que hay que decir: un cuadro que arranca a más de media
  // hoja del borde queda ENTERO fuera del lienzo y no se ve -- ni sobre el
  // gris ni en ningún lado. Un cuadro invisible del que nadie se entera es la
  // misma mentira de siempre con otra forma, así que se lista acá, y a los
  // que no se alcanzan a ver se les dice "fuera de vista". Se mide la CAJA,
  // igual que el lienzo (el aviso de tinta con la fila real es el del
  // backend); es la lista de lo que hay que ir a mirar, no un veredicto.
  const fuera = layoutComps.flatMap((c) => {
    const b = c.base_bounds;
    const excesos: [string, number][] = [
      ["izq", -b.x], ["der", b.x + b.width - dims.w],
      ["arr", -b.y], ["aba", b.y + b.height - dims.h],
    ];
    const [lado, cm] = excesos.reduce((peor, e) => (e[1] > peor[1] ? e : peor));
    if (cm <= 0) return [];
    const topeW = dims.w * TOPE_SOBRA;
    const topeH = dims.h * TOPE_SOBRA;
    const visible =
      b.x < dims.w + topeW && b.x + b.width > -topeW &&
      b.y < dims.h + topeH && b.y + b.height > -topeH;
    return [{ nombre: c.name || c.id, lado, cm, visible }];
  }).sort((a, b) => b.cm - a.cm);

  const stageW       = sobraIzq + pageW + sobraDer + margin * 2;
  const stageH       = sobraArr + pageH + sobraAba + margin * 2;
  const pageLeft     = margin + sobraIzq;
  const pageTop      = margin + sobraArr;

  // Zoom automático: ajusta el dibujo al ANCHO disponible del contenedor en
  // vez de dibujar siempre al mismo tamaño fijo en píxeles (28px/cm) sin
  // importar la pantalla -- en un monitor ancho un A4 fijo dejaba una franja
  // vacía enorme al costado (se pidió centrarlo bien, pero eso no usa el
  // espacio de más; lo notó Ivan viendo la plantilla real). Con `zoom`, una
  // hoja chica (A4) se agranda para llenar el ancho disponible, y una hoja
  // más ancha que la pantalla (6xA4/A5) se achica para entrar entera SIN
  // scroll horizontal -- ambos casos con la MISMA cuenta. Los nodos de Konva
  // siguen viviendo en su espacio de coordenadas de siempre (28px/cm, sin
  // multiplicar por zoom en ningún otro lado del archivo); el escalado lo
  // aplica Konva mismo vía stage.scale(), que ya sabe traducir clicks y
  // arrastres correctamente sobre un stage escalado -- no hay que tocar la
  // lógica de selección/arrastre/resize de más abajo.
  const ZOOM_MIN = 0.25;
  const ZOOM_MAX = 2;
  const WRAPPER_PADDING = 32; // aire para que la hoja no quede pegada al borde
  // La hoja entra ENTERA: manda la dimensión más exigente de las dos, igual que
  // el "Ajustar a la ventana" de PowerPoint. Mirando solo el ancho, una A4
  // (21 x 29,7) se estiraba hasta llenarlo y se pasaba de alto.
  //
  // Se descuenta RULER_SIZE porque las reglas ocupan lugar dentro del mismo
  // contenedor; sin eso la hoja se pasa por 18 px justo en el borde.
  const fitAncho = wrapperWidth
    ? (wrapperWidth  - WRAPPER_PADDING - RULER_SIZE) / stageW
    : null;
  const fitAlto = wrapperHeight
    ? (wrapperHeight - WRAPPER_PADDING - RULER_SIZE) / stageH
    : null;
  const ajuste = fitAncho !== null && fitAlto !== null ? Math.min(fitAncho, fitAlto)
               : fitAncho ?? fitAlto;
  const zoom = ajuste !== null && ajuste !== undefined
    ? Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, ajuste))
    : 1;

  // ACÁ HABÍA UNA SEGUNDA MENTIRA, y sobrevivía intacta a sacar el `Math.max`.
  // Todo cuadro de texto más ancho que la hoja se redibujaba en x = 0 con el
  // ancho de la hoja: o sea, se METÍA A LA FUERZA adentro del papel. El
  // comentario que estaba acá decía que era para compensar "el ajuste que el
  // motor de export sí aplica"; eso es falso, y se verificó: el exportador
  // escribe `computed_bounds` tal cual en shape.left/shape.width
  // (component_renderer, _place_component) y no recorta nada.
  //
  // Es cierto lo otro que decía: una caja invisible mucho más ancha que la
  // hoja es un truco de autoría legítimo --así el precio queda centrado en el
  // mismo lugar tenga 2 o 5 dígitos-- y hoy las dos cajas que lo usan (A4
  // HELVETICO, x = -11,74 cm y 44,47 cm de ancho) son simétricas, así que
  // meterlas a la fuerza dejaba el centro casi donde iba. Pero cambiaba el
  // ANCHO de 44,47 a 21 cm, y el ancho es lo que decide dónde corta el
  // renglón: el corte de línea del preview no era el del papel justo en los
  // cuadros de precio. Y con una caja ancha NO centrada, el preview la
  // mostraría adentro y saldría corrida varios centímetros.
  //
  // Ahora se dibuja lo que hay. Si una caja se sale, se ve saliendo.
  const displayComps = layoutComps;

  // Montaje: crear Stage/Layers/Transformer una sola vez. Todo esto vive
  // adentro de un efecto (nunca corre en el servidor), asi que el contenedor
  // se puede renderizar siempre sin riesgo de mismatch de hidratacion.
  useEffect(() => {
    if (!containerRef.current) return;

    const stage = new Konva.Stage({
      container: containerRef.current,
      width: stageW * zoom,
      height: stageH * zoom,
      scaleX: zoom,
      scaleY: zoom,
    });
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

  // Tamaño y zoom del stage (cambia al cambiar de formato o de ancho
  // disponible). stage.scale() es el mecanismo propio de Konva para esto --
  // ya traduce clicks/arrastres/handles del Transformer sobre el stage
  // escalado, así que todo el código de más abajo sigue trabajando en
  // coordenadas sin escalar.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.width(stageW * zoom);
    stage.height(stageH * zoom);
    stage.scale({ x: zoom, y: zoom });
    stage.batchDraw();
  }, [stageW, stageH, zoom]);

  // Fondo: la MESA DE TRABAJO gris, el PAPEL blanco encima, y la etiqueta.
  //
  // La mesa es todo el lienzo. Lo que cae sobre gris esta FUERA DEL PAPEL y no
  // se va a imprimir: eso es lo que antes no se veia de ninguna forma, porque
  // o se agrandaba el papel hasta tragarlo o quedaba fuera del stage.
  useEffect(() => {
    const layer = bgLayerRef.current;
    if (!layer) return;
    layer.destroyChildren();

    const mesa = new Konva.Rect({
      x: 0, y: 0, width: stageW, height: stageH,
      fill: seSale ? "#e2e8f0" : "transparent",
    });
    mesa.on("click", () => selectComponent(null));
    layer.add(mesa);

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

    // La etiqueta dice EL PAPEL y de donde salio el numero. El "A4 24.588x29.7
    // cm" que Ivan tenia en pantalla no era ningun papel: era el borde derecho
    // del cuadro que se salia 3,6 cm. "medida del archivo" = sale del PPTX que
    // se importo, o sea de lo que PowerPoint va a imprimir; "segun el formato"
    // = la plantilla no trae medida y se esta usando la del formato declarado.
    //
    // Y si el formato no está en la tabla, se dice: `papelDeLaPlantilla` cae a
    // A4 para no tumbar el dibujo, pero "XYZ 21×29,7 · según el formato" haría
    // pasar esa caída por una medida del formato XYZ.
    const conocido = formatoConocido(formatoQueManda);
    const origen = papel?.origen === "pptx"
      ? "medida del archivo"
      : conocido ? "según el formato" : `formato «${formatoQueManda}» desconocido, se dibuja como A4`;
    // Con bandas se dibuja el papel del master aunque se esté mirando otro
    // formato, porque eso es lo que imprime el render (ver formatoQueManda).
    const etiqueta = formatoQueManda === activeFormat
      ? activeFormat.toUpperCase()
      : `${activeFormat.toUpperCase()} → papel de ${formatoQueManda.toUpperCase()} (con bandas no se escala)`;
    layer.add(new Konva.Text({
      x: pageLeft, y: pageTop - 22,
      text: `${etiqueta}  ${dims.w}×${dims.h} cm · ${origen}`,
      fontSize: 10, fill: conocido ? "#94a3b8" : "#dc2626", fontFamily: "Inter, system-ui, sans-serif",
    }));

    // La lista de lo que se sale, arriba de la etiqueta, en rojo. Cabe en la
    // franja del margen superior (40 px) sin pisar nada.
    if (fuera.length) {
      const NOMBRE_LADO: Record<string, string> = { izq: "izquierda", der: "derecha", arr: "arriba", aba: "abajo" };
      const MOSTRAR = 5;
      const partes = fuera.slice(0, MOSTRAR).map((f) =>
        `${f.nombre} (${NOMBRE_LADO[f.lado]} ${f.cm.toFixed(1).replace(".", ",")} cm${f.visible ? "" : ", FUERA DE VISTA"})`,
      );
      const demas = fuera.length - MOSTRAR;
      const ocultos = fuera.filter((f) => !f.visible).length;
      layer.add(new Konva.Text({
        x: pageLeft, y: pageTop - 36,
        width: stageW - pageLeft - 4, wrap: "none", ellipsis: true,
        text:
          `Fuera del papel (${fuera.length}${ocultos ? `, ${ocultos} sin verse` : ""}): `
          + partes.join("; ") + (demas > 0 ? `; +${demas} más` : ""),
        fontSize: 10, fill: "#dc2626", fontFamily: "Inter, system-ui, sans-serif",
      }));
    }

    layer.batchDraw();
  }, [pageLeft, pageTop, pageW, pageH, stageW, stageH, seSale, activeFormat, formatoQueManda,
      dims.w, dims.h, papel?.origen, fuera, selectComponent]);

  // Las tipografias del diseno se bajan de Google (ver globals.css) y tardan
  // un instante. Konva MIDE el texto con la fuente que haya en ese momento:
  // si la capa se arma antes de que lleguen, cada cuadro queda medido con la
  // de reemplazo y ya no se corrige solo. Este flag entra en las
  // dependencias del efecto de abajo para que la capa se rearme una vez que
  // cargaron. `fonts.ready` resuelve una sola vez por carga de pagina, asi
  // que no es un bucle.
  const [fuentesListas, setFuentesListas] = useState(false);
  useEffect(() => {
    if (typeof document === "undefined" || !document.fonts) { setFuentesListas(true); return; }
    let vivo = true;
    document.fonts.ready.then(() => { if (vivo) setFuentesListas(true); });
    return () => { vivo = false; };
  }, []);

  // Componentes: se reconstruye toda la capa en cada cambio relevante (igual
  // de simple que el reconciliador de React, sin diffing fino — para la
  // cantidad de componentes tipica de una cenefa el costo es despreciable).
  useEffect(() => {
    const layer = compLayerRef.current;
    const transformer = transformerRef.current;
    if (!layer || !transformer) return;
    // Sin las reglas de medicion no se dibuja nada: ver LA PUERTA mas arriba.
    // buildComponentGroup llama a reglas(), que TIRA si todavia no llegaron.
    if (!reglasListas) return;

    layer.find(`.${CENEFA_COMP_NAME}`).forEach((n) => n.destroy());
    const nodeMap = new Map<string, Konva.Group>();
    nodeMapRef.current = nodeMap;

    let selectedNode: Konva.Group | null = null;

    for (const comp of displayComps) {
      // Marcado = está en la selección, sea el primario o uno sumado con
      // Ctrl. El Transformer (los 4 puntos de resize) es aparte: se engancha
      // más abajo y solo cuando hay UN cuadro seleccionado.
      const isSelected = selectedComponentIds.includes(comp.id) && isEditMode;
      const bandIdx = bandIndexByCompId.get(comp.id);
      const compPreviewData =
        bandIdx !== undefined && previewProducts ? previewProducts[bandIdx] ?? previewData : previewData;
      const group = buildComponentGroup({
        comp: aplicarTamanos(
          comp, reglasPorComp.tamanos.get(comp.id), reglasPorComp.tamanosSeg.get(comp.id)),
        pageLeft, pageTop, isSelected,
        draggable: isEditMode && !comp.locked,
        image: getImage(comp),
        previewData: compPreviewData,
        capacidad,
        capacidadSegmentos,
        ocultoPorRegla: reglasPorComp.ocultos.has(comp.id),
        segmentosOcultos: reglasPorComp.segmentos.get(comp.id),
        onSelect: (conCtrl) => {
          if (!isEditMode) return;
          if (conCtrl && toggleComponentSelection) toggleComponentSelection(comp.id);
          else selectComponent(comp.id);
        },
        onDragEnd: (x, y) => {
          const newX = +dentroDelPapel((x - pageLeft) / PX_PER_CM, comp.base_bounds.width,  dims.w).toFixed(2);
          const newY = +dentroDelPapel((y - pageTop)  / PX_PER_CM, comp.base_bounds.height, dims.h).toFixed(2);
          updateComponent(comp.id, {
            base_bounds: { ...comp.base_bounds, x: newX, y: newY },
          });
        },
      });
      layer.add(group);
      nodeMap.set(comp.id, group);
      // El Transformer va sobre el PRIMARIO, no sobre cualquiera de los
      // marcados: redimensiona un cuadro a la vez.
      if (comp.id === selectedComponentId && isEditMode) selectedNode = group;
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
          const newX = +dentroDelPapel(sComp.base_bounds.x + dxCm, sComp.base_bounds.width,  dims.w).toFixed(2);
          const newY = +dentroDelPapel(sComp.base_bounds.y + dyCm, sComp.base_bounds.height, dims.h).toFixed(2);
          updateComponent(sid, { base_bounds: { ...sComp.base_bounds, x: newX, y: newY } });
        }
      });
    }

    // EL BORDE DEL PAPEL, MARCADO, cuando hay algo afuera. Va en la capa de
    // componentes y no en la del fondo porque tiene que quedar ENCIMA del
    // diseno: las plantillas traen una imagen de fondo que cubre la hoja
    // entera, asi que un borde dibujado abajo no se veria. `listening: false`
    // para que no se coma los clicks de seleccion.
    if (seSale) {
      const borde = new Konva.Rect({
        name: CENEFA_COMP_NAME,
        x: pageLeft, y: pageTop, width: pageW, height: pageH,
        stroke: "#dc2626", strokeWidth: 1.5, dash: [8, 5],
        listening: false,
      });
      layer.add(borde);
      borde.moveToTop();
    }

    transformer.moveToTop();
    selectedNodeRef.current = selectedNode;
    // Con varios cuadros marcados no se muestran los handles de resize: el
    // Transformer, el achique automático y la réplica a los hermanos entre
    // bandas están escritos alrededor de UN nodo primario. Mostrarlos acá
    // haría que un resize se aplique solo al primario mientras la persona ve
    // tres cuadros marcados, que es peor que no ofrecerlo. La selección
    // múltiple hoy sirve para las reglas en lote (ver RulesPanel.tsx).
    const soloUnoMarcado = selectedComponentIds.length <= 1;
    transformer.nodes(selectedNode && soloUnoMarcado ? [selectedNode] : []);
    layer.batchDraw();
    // `reglasPorComp` va en las dependencias o el arreglo no sirve para nada:
    // agregar o borrar una regla cambia ese memo y NO redibujaría la capa, así
    // que en pantalla seguiría sin pasar nada -- que es justo el problema que
    // vino a resolver.
  }, [displayComps, selectedComponentId, selectedComponentIds, toggleComponentSelection, isEditMode, pageLeft, pageTop, pageW, pageH, seSale, dims.w, dims.h, getImage, previewData, previewProducts, capacidad, capacidadSegmentos, bandIndexByCompId, siblingMap, reglasPorComp, template.components, selectComponent, updateComponent, fuentesListas, reglasListas]);

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

  // justify-[safe_center], no justify-center a secas: centrado normal
  // ("unsafe") con overflow-auto recorta el desborde por igual a los dos
  // lados cuando el contenido es mas ancho que el contenedor, y ese sobrante
  // queda inalcanzable con scroll (bug conocido de flexbox) -- paso
  // desapercibido porque hasta ahora ningun formato desbordaba. `safe center`
  // es exactamente el valor de la spec de CSS Box Alignment para esto: centra
  // cuando entra (A4, 3xA4) y cae a alineado-al-inicio SOLO si desborda
  // (6xA4/A5, ver el calculo de `dims` mas arriba), sin la fea franja vacia
  // de justify-start ni el recorte de justify-center a secas.
  return (
    <div ref={wrapperRef} className={`relative overflow-auto bg-slate-200 dark:bg-slate-950 rounded-lg flex ${className}`}>
      {/* Mientras no lleguen las reglas de medicion Y el tamano de hoja no
          hay nada dibujado debajo (ver LA PUERTA): este cartel es lo unico
          que se ve. */}
      {!reglasListas && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-slate-200/90 dark:bg-slate-950/90 px-6 text-center">
          {errorReglas ? (
            <div className="max-w-md">
              <p className="text-sm font-semibold text-red-600 dark:text-red-400">
                No se pudo traer la medición del backend
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                Faltan las reglas de medición o el tamaño de la hoja. Sin ellas
                la cenefa se dibujaría con medidas distintas de las que usa el
                archivo que se imprime, así que no se dibuja nada. Probá
                recargar; si sigue, el backend no está respondiendo.
              </p>
              <p className="mt-2 text-[10px] font-mono text-slate-500 break-words">{errorReglas}</p>
            </div>
          ) : (
            <p className="text-sm text-slate-600 dark:text-slate-400">Cargando la medición (reglas y tamaño de hoja)…</p>
          )}
        </div>
      )}
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
      {/* `m-auto` y no `justify-center` en el contenedor: en flexbox los
          márgenes automáticos absorben SOLO el espacio libre positivo, así que
          centran cuando la hoja entra y se resuelven a 0 cuando no, sin dejar
          el borde de arriba/izquierda fuera del scroll. Es lo que hace
          `safe center`, pero sin depender de esa palabra clave. */}
      <div
        className="grid m-auto"
        style={{ gridTemplateColumns: `${RULER_SIZE}px ${stageW * zoom}px`, gridTemplateRows: `${RULER_SIZE}px ${stageH * zoom}px` }}
      >
        <div
          className="sticky top-0 left-0 z-30 bg-slate-100 dark:bg-slate-900 border-b border-r border-slate-300 dark:border-slate-700"
        />
        <div
          className="sticky top-0 z-20 bg-slate-100 dark:bg-slate-900 border-b border-slate-300 dark:border-slate-700 relative overflow-hidden"
          style={{ width: stageW * zoom, height: RULER_SIZE }}
        >
          {hTicks.map((t, i) => (
            <div key={i} className="absolute bottom-0" style={{ left: t.pos * zoom }}>
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
          style={{ width: RULER_SIZE, height: stageH * zoom }}
        >
          {vTicks.map((t, i) => (
            <div key={i} className="absolute right-0" style={{ top: t.pos * zoom }}>
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
