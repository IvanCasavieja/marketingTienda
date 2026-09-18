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
import { reglas } from "@/lib/cenefas/reglasDeMedicion";

const COLOR_POR_DEFECTO = "#1e293b";
// EL TAMANO POR DEFECTO Y EL ALTO DE LINEA NO SE ESCRIBEN ACA. Salen de
// reglasDeMedicion.ts, que los pide al backend, porque son las MISMAS reglas
// con las que el exportador decide cuántos renglones entran en un cuadro. Si
// este lado tuviera su propia copia y alguien tocara una sola, una descripción
// que en pantalla entra en dos líneas saldría impresa en tres y se le montaría
// encima al precio. Ver backend/app/data/reglas_de_medicion.json.
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
    Math.abs((estilo.font_size ?? reglas().ptPorDefecto) - (caja.font_size ?? reglas().ptPorDefecto)) > TOLERANCIA_PT
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
 *
 * El texto llega YA RESUELTO a propósito: de dónde sale no es asunto de acá.
 * Hoy hay dos orígenes. Con datos reales sale del producto del Excel; en la
 * vista de capacidad sale del relleno que calcula el backend para CADA
 * segmento (ver /capacidad, clave `segmentos`). El segundo se sumó el
 * 18/09/2026: con la tira de relleno del cuadro entero, el decimal de la
 * "Fiesta Alemania-202608-A4" quedaba tapado por los dígitos del precio y no
 * se podía ni ver ni acomodar.
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
    // Bold automático en un segmento: pone en negrita SOLO las mayúsculas.
    //
    // Pero la negrita puesta a mano le gana: si el estilo dice negrita, va
    // TODO en negrita y la automática no se aplica. Espejo exacto de
    // _populate_text_frame en component_renderer.py -- si tocás una, tocá la
    // otra.
    //
    // Antes smart_bold ignoraba `font_bold` por completo y tildar la casilla
    // del panel no cambiaba nada, ni acá ni en el archivo (reportado por Ivan,
    // 14/09/2026). La automática decide por vos cuando no decidiste; en cuanto
    // decidís, manda lo tuyo.
    const partes: [string, boolean][] = seg.transform === "smart_bold" && !estilo.font_bold
      ? tramosSmartBold(texto)
      : [[texto, !!estilo.font_bold]];
    for (const [parte, negrita] of partes) {
      if (!parte) continue;
      const fuente = resolverFuente(estilo.font_family, negrita);
      tramos.push({
        texto: parte,
        pt: estilo.font_size ?? reglas().ptPorDefecto,
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

/**
 * El cuerpo con el que de verdad se dibuja un tramo, ya con el achique de la
 * voladita aplicado. Todo lo que mida o dibuje texto tiene que usar ESTO y no
 * `tramo.pt`, o el preview vuelve a mentir.
 *
 * PowerPoint no dibuja un pedazo volado (el "$", los centavos) en su cuerpo
 * declarado: lo dibuja a dos tercios, y no cambia el número -- si abrís el
 * PPTX, la casilla del tamaño sigue diciendo el original. El achique es
 * BINARIO: subir un pedazo 5 % o 95 % da el mismo tamaño, solo cambia la
 * altura; recién vuelve al completo con desplazamiento 0. Por eso mover el "$"
 * con las flechitas del panel nunca pareció cambiarle el tamaño.
 *
 * EL FACTOR NO SE ESCRIBE ACA: sale de reglasDeMedicion.ts, que lo pide al
 * backend. Está medido contra PowerPoint de verdad y la medición entera está
 * contada en backend/app/data/reglas_de_medicion.json, que es el único lugar
 * donde vive el número.
 */
export function ptEfectivo(tramo: { pt: number; voladita: number }): number {
  return tramo.voladita ? tramo.pt * reglas().factorVoladita : tramo.pt;
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
  const fontDe = (i: number) => cadenaFont(tramos[i].weight, op.ptToPx(ptEfectivo(tramos[i])), tramos[i].stack);
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
  let ptAnterior = tramos.length ? ptEfectivo(tramos[0]) : reglas().ptPorDefecto;
  lineas.forEach((linea, n) => {
    // Átomos seguidos del mismo tramo se miden juntos: así entra el kerning.
    const grupos: { tramo: number; texto: string }[] = [];
    for (const a of linea) {
      const ultimo = grupos[grupos.length - 1];
      if (ultimo && ultimo.tramo === a.tramo) ultimo.texto += a.texto;
      else grupos.push({ tramo: a.tramo, texto: a.texto });
    }

    let mayor = grupos.length ? grupos[0].tramo : -1;
    // Quién manda en el renglón es el que se DIBUJA más grande, no el que
    // declara el número más grande: un pedazo volado de 220 pt se dibuja más
    // chico que uno de 160 sin volar.
    for (const g of grupos) if (ptEfectivo(tramos[g.tramo]) > ptEfectivo(tramos[mayor])) mayor = g.tramo;
    let ptLinea = mayor >= 0 ? ptEfectivo(tramos[mayor]) : ptAnterior;
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
      const base = arriba + (ascent - descent) / 2 + (sizeLinea * reglas().altoDeLinea) / 2;
      grupos.forEach((g, k) => {
        const tramo = tramos[g.tramo];
        const sizePx = op.ptToPx(ptEfectivo(tramo));
        piezas.push({
          texto: g.texto,
          font: fontDe(g.tramo),
          color: tramo.color,
          tachado: tramo.tachado,
          sizePx,
          x,
          // El DESPLAZAMIENTO se sigue midiendo sobre el cuerpo DECLARADO, no
          // sobre el achicado: el esquema define la voladita como un
          // porcentaje "del tamaño de la fuente", y es el que venía dando la
          // altura correcta contra los PPTX reales. Solo cambia el cuerpo con
          // el que se dibuja, que es lo que estaba mintiendo.
          y: base - (op.ptToPx(tramo.pt) * tramo.voladita) / 100000,
          ancho: anchos[k],
        });
        x += anchos[k];
      });
    }
    arriba += sizeLinea * reglas().altoDeLinea;
  });

  return { piezas, alto: arriba };
}
