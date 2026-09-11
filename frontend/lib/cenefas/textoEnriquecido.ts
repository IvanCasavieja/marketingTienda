/**
 * Preview de un cuadro de texto cuyos segmentos tienen estilos distintos.
 *
 * El PPTX exportado arma un run por segmento, cada uno con su tamaño, peso,
 * color, tachado y voladita (ver _populate_text_frame en
 * component_renderer.py). El canvas dibujaba el cuadro entero como UN texto
 * con el estilo de la caja: en Rompe Precios A4 "$ 250 ,85" se veía todo a
 * 130 pt, sin el "$" ni los centavos arriba, y un tamaño puesto a mano en un
 * segmento no se veía nunca (visto el 11/09/2026).
 *
 * Esta es la parte pura --sin Konva ni DOM--: qué estilo lleva cada pedazo y
 * dónde va cada uno. El dibujo está en dibujarTextoEnriquecido.ts.
 */
import type { CenefaComponent, ComponentStyle, TextSegment } from "@/types/cenefas";
import { resolverFuente } from "@/lib/cenefas/fuentes";
import { tramosSmartBold } from "@/lib/cenefas/smartBold";

// Los mismos valores por defecto con los que el canvas dibuja un cuadro sin
// estilo propio (ver buildComponentGroup en Canvas.tsx).
const PT_POR_DEFECTO = 12;
const COLOR_POR_DEFECTO = "#1e293b";
// Konva.Text se arma con lineHeight 1.2: los renglones de acá tienen que medir
// lo mismo para no correrse respecto de los cuadros que siguen por ese camino.
const ALTO_DE_LINEA = 1.2;
// El achique del backend deja 91.29999999999998 en un segmento y 91.3 en la
// caja (Red Expres 17): son el mismo tamaño, no un estilo propio.
const TOLERANCIA_PT = 0.05;

export interface Tramo {
  texto: string;
  pt: number;
  /** Peso CSS, con la negrita ya sumada (ver resolverFuente). */
  weight: number;
  /** Cadena para la familia del canvas. */
  stack: string;
  color: string;
  tachado: boolean;
  /** Voladita como la guarda PowerPoint: 30000 = 30% del cuerpo arriba de la línea de base. */
  voladita: number;
}

type EstiloSegmento = ComponentStyle & NonNullable<TextSegment["style"]>;

/**
 * Espejo de _populate_text_frame: estilo de la caja + estilo del segmento. Con
 * tamaño puesto a mano en la caja, ese tamaño pisa a los segmentos que no
 * tienen el suyo puesto a mano ("lo que ponés a mano manda donde lo ponés").
 */
export function estiloEfectivoSegmento(comp: CenefaComponent, seg: TextSegment): EstiloSegmento {
  const caja = comp.style ?? {};
  const estilo: EstiloSegmento = { ...caja, ...(seg.style ?? {}) };
  if (comp._manual_font_override && caja.font_size && !seg._manual_font_override) {
    estilo.font_size = caja.font_size;
  }
  return estilo;
}

function difiereDeLaCaja(estilo: EstiloSegmento, caja: ComponentStyle): boolean {
  const fuente = resolverFuente(estilo.font_family, estilo.font_bold);
  const fuenteCaja = resolverFuente(caja.font_family, caja.font_bold);
  return (
    Math.abs((estilo.font_size ?? PT_POR_DEFECTO) - (caja.font_size ?? PT_POR_DEFECTO)) > TOLERANCIA_PT
    || fuente.weight !== fuenteCaja.weight
    || fuente.stack !== fuenteCaja.stack
    || (estilo.color ?? COLOR_POR_DEFECTO).toLowerCase() !== (caja.color ?? COLOR_POR_DEFECTO).toLowerCase()
    || !!estilo.strikethrough !== !!caja.strikethrough
    || !!estilo.baseline
  );
}

/**
 * Los pedazos a dibujar, o null si ninguno difiere del estilo de la caja. Con
 * null el canvas sigue dibujando como siempre (un solo Konva.Text): este
 * camino solo toca los cuadros que de verdad lo necesitan.
 *
 * `textoDeSegmento` devuelve el texto ya resuelto (variable + transformación,
 * vacío si una regla lo oculta). Un segmento vacío no cuenta ni se dibuja,
 * igual que en el export, que no le crea run.
 */
export function tramosConEstiloPropio(
  comp: CenefaComponent,
  textoDeSegmento: (seg: TextSegment, indice: number) => string,
): Tramo[] | null {
  const caja = comp.style ?? {};
  const tramos: Tramo[] = [];
  let alguno = false;
  (comp.segments ?? []).forEach((seg, i) => {
    const texto = textoDeSegmento(seg, i);
    if (!texto) return;
    const estilo = estiloEfectivoSegmento(comp, seg);
    if (difiereDeLaCaja(estilo, caja)) alguno = true;
    // Bold automático en un segmento: el export le pone negrita SOLO a las
    // mayúsculas, sin mirar la negrita del estilo (bold_override).
    const partes: [string, boolean][] = seg.transform === "smart_bold"
      ? tramosSmartBold(texto)
      : [[texto, !!estilo.font_bold]];
    for (const [parte, negrita] of partes) {
      if (!parte) continue;
      const fuente = resolverFuente(estilo.font_family, negrita);
      tramos.push({
        texto: parte,
        pt: estilo.font_size ?? PT_POR_DEFECTO,
        weight: fuente.weight,
        stack: fuente.stack,
        color: estilo.color ?? COLOR_POR_DEFECTO,
        tachado: !!estilo.strikethrough,
        voladita: estilo.baseline ?? 0,
      });
    }
  });
  return alguno ? tramos : null;
}

export interface Pieza {
  texto: string;
  /** Cadena `font` del canvas. */
  font: string;
  color: string;
  tachado: boolean;
  sizePx: number;
  x: number;
  /** Línea de base, ya con la voladita aplicada. */
  y: number;
  ancho: number;
}

export interface OpcionesDiagrama {
  anchoPx: number;
  align: "left" | "center" | "right";
  /** Alto de línea forzado por el run espaciador del diseño (style.line_height_pt). */
  lineHeightPt?: number;
  ptToPx: (pt: number) => number;
  /** Ancho en px de un texto dibujado con esa cadena `font`. */
  medir: (texto: string, font: string) => number;
  /** Ascendente y descendente de la fuente, medidos como los mide Konva.Text. */
  metricas: (font: string) => { ascent: number; descent: number };
}

/** Mismo formato que arma Konva.Text: "peso variante tamañopx familia". */
export function cadenaFont(weight: number, sizePx: number, stack: string): string {
  return `${weight} normal ${sizePx}px ${stack}`;
}

interface Atomo {
  texto: string;
  tramo: number;
  espacio: boolean;
  salto: boolean;
}

/**
 * Dónde va cada pedazo, renglón por renglón. Imita a Konva.Text con
 * wrap "word" (lo que se veía hasta ahora) y a PowerPoint:
 *
 * - Se corta por palabra. Una palabra son los caracteres sin espacios
 *   seguidos AUNQUE vengan de tramos distintos: "$" + "250" + ",85" es una
 *   sola palabra y nunca se parte entre medio.
 * - Una palabra más ancha que la caja se corta por carácter ("1.91" + "9"),
 *   como hacen los dos: el desborde tiene que verse.
 * - Todos los pedazos de un renglón se apoyan en la MISMA línea de base, la
 *   del pedazo más grande. En el primer renglón cuenta también el alto del
 *   run espaciador, que es lo que baja al "$" chico hasta el precio grande.
 */
export function diagramarTramos(tramos: Tramo[], op: OpcionesDiagrama): { piezas: Pieza[]; alto: number } {
  const fontDe = (i: number) => cadenaFont(tramos[i].weight, op.ptToPx(tramos[i].pt), tramos[i].stack);
  const anchoDe = (a: Atomo) => op.medir(a.texto, fontDe(a.tramo));

  const atomos: Atomo[] = [];
  tramos.forEach((t, i) => {
    for (const parte of t.texto.split(/(\n|[^\S\n]+)/)) {
      if (!parte) continue;
      atomos.push({ texto: parte === "\n" ? "" : parte, tramo: i, espacio: /^[^\S\n]+$/.test(parte), salto: parte === "\n" });
    }
  });

  const lineas: Atomo[][] = [[]];
  let anchoLinea = 0;
  // Un renglón abierto por un corte automático no arranca con los espacios
  // donde se cortó; uno abierto por un salto de línea del texto sí los conserva.
  let abiertoPorCorte = false;
  const nuevaLinea = (porCorte: boolean) => {
    lineas.push([]);
    anchoLinea = 0;
    abiertoPorCorte = porCorte;
  };

  let espacios: Atomo[] = [];
  let i = 0;
  while (i < atomos.length) {
    const a = atomos[i];
    if (a.salto) { nuevaLinea(false); espacios = []; i++; continue; }
    if (a.espacio) { espacios.push(a); i++; continue; }

    const palabra: Atomo[] = [];
    while (i < atomos.length && !atomos[i].espacio && !atomos[i].salto) palabra.push(atomos[i++]);
    const anchoPalabra = palabra.reduce((s, p) => s + anchoDe(p), 0);
    const anchoEspacios = espacios.reduce((s, p) => s + anchoDe(p), 0);

    let linea = lineas[lineas.length - 1];
    if (linea.length > 0) {
      if (anchoLinea + anchoEspacios + anchoPalabra <= op.anchoPx) {
        linea.push(...espacios, ...palabra);
        anchoLinea += anchoEspacios + anchoPalabra;
        espacios = [];
        continue;
      }
      nuevaLinea(true);
      linea = lineas[lineas.length - 1];
    } else if (!abiertoPorCorte && espacios.length) {
      linea.push(...espacios);
      anchoLinea += anchoEspacios;
    }
    espacios = [];

    if (anchoLinea + anchoPalabra <= op.anchoPx || linea.length === 0 && anchoPalabra <= op.anchoPx) {
      linea.push(...palabra);
      anchoLinea += anchoPalabra;
      continue;
    }
    for (const p of palabra) {
      for (const letra of Array.from(p.texto)) {
        const pedazo = { ...p, texto: letra };
        const ancho = anchoDe(pedazo);
        if (lineas[lineas.length - 1].length > 0 && anchoLinea + ancho > op.anchoPx) nuevaLinea(true);
        lineas[lineas.length - 1].push(pedazo);
        anchoLinea += ancho;
      }
    }
  }

  const piezas: Pieza[] = [];
  let arriba = 0;
  let ptAnterior = tramos.length ? tramos[0].pt : PT_POR_DEFECTO;
  lineas.forEach((linea, n) => {
    // Átomos seguidos del mismo tramo se miden juntos: así entra el kerning.
    const grupos: { tramo: number; texto: string }[] = [];
    for (const a of linea) {
      const ultimo = grupos[grupos.length - 1];
      if (ultimo && ultimo.tramo === a.tramo) ultimo.texto += a.texto;
      else grupos.push({ tramo: a.tramo, texto: a.texto });
    }

    let mayor = grupos.length ? grupos[0].tramo : -1;
    for (const g of grupos) if (tramos[g.tramo].pt > tramos[mayor].pt) mayor = g.tramo;
    let ptLinea = mayor >= 0 ? tramos[mayor].pt : ptAnterior;
    if (n === 0 && op.lineHeightPt && op.lineHeightPt > ptLinea) ptLinea = op.lineHeightPt;
    ptAnterior = ptLinea;
    const sizeLinea = op.ptToPx(ptLinea);

    const anchos = grupos.map((g) => op.medir(g.texto, fontDe(g.tramo)));
    const total = anchos.reduce((s, a) => s + a, 0);
    let x = op.align === "center" ? (op.anchoPx - total) / 2 : op.align === "right" ? op.anchoPx - total : 0;

    if (mayor >= 0) {
      // Misma cuenta que Konva.Text (_sceneFunc, sin legacyTextRendering):
      // la base queda a medio renglón más la mitad de ascendente - descendente.
      const t = tramos[mayor];
      const { ascent, descent } = op.metricas(cadenaFont(t.weight, sizeLinea, t.stack));
      const base = arriba + (ascent - descent) / 2 + (sizeLinea * ALTO_DE_LINEA) / 2;
      grupos.forEach((g, k) => {
        const tramo = tramos[g.tramo];
        const sizePx = op.ptToPx(tramo.pt);
        piezas.push({
          texto: g.texto,
          font: fontDe(g.tramo),
          color: tramo.color,
          tachado: tramo.tachado,
          sizePx,
          x,
          y: base - (sizePx * tramo.voladita) / 100000,
          ancho: anchos[k],
        });
        x += anchos[k];
      });
    }
    arriba += sizeLinea * ALTO_DE_LINEA;
  });

  return { piezas, alto: arriba };
}
