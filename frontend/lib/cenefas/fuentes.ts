/**
 * Qué tipografía dibuja de verdad el preview.
 *
 * El problema que resuelve (visto el 07/09/2026, "Fiesta de Gran Bretaña"):
 * el canvas pedía la fuente del diseño con UNA sola cadena de alternativas
 * que empezaba por Impact. Cuando la máquina no tenía la fuente pedida --y
 * "Libre Franklin" no viene con Windows ni la cargaba la app-- el navegador
 * caía en Impact, que es una condensada pesadísima. Resultado: la
 * descripción y el título "PRECIO REGULAR:" se veían mucho más gordos que en
 * el PPTX, y parecía que el editor estaba poniendo todo en negrita.
 *
 * Dos cosas hacen falta para que el preview se parezca al PPTX:
 *
 * 1. PowerPoint guarda el PESO DENTRO DEL NOMBRE. "Libre Franklin Black" no
 *    es otra familia, es Libre Franklin en 900; "Franklin Gothic Demi" es
 *    Franklin Gothic en 600. Para el navegador esos nombres no existen: hay
 *    que separarlos en familia + peso.
 *
 * 2. La alternativa tiene que PARECERSE a lo pedido. Caer siempre en Impact
 *    convierte cualquier fuente ausente en un cartelón. Cada familia lleva
 *    acá su propia cadena, y las que se pueden cargar de Google se cargan en
 *    globals.css (Libre Franklin cubre toda la familia Franklin, que es
 *    justamente de donde viene: es un revival de la Franklin Gothic).
 */

export interface FuenteResuelta {
  /** La cadena que va a `fontFamily` del canvas. */
  stack: string;
  /** El peso CSS (100-900). PowerPoint lo esconde en el nombre. */
  weight: number;
  /** Familia limpia, sin el sufijo de peso -- para mostrarla en el panel. */
  familia: string;
  /** Cómo se llama el peso en castellano, para mostrarlo. */
  pesoNombre: string;
  /** true si la fuente exacta del diseño NO está y se dibuja con una parecida. */
  sustituida: boolean;
}

const NOMBRE_PESO: Record<number, string> = {
  100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular",
  500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black",
};

// Las que SÍ vienen instaladas en Windows y macOS: se piden tal cual y no
// se marcan como sustituidas.
const DEL_SISTEMA = new Set([
  "impact", "arial", "arial black", "verdana", "tahoma", "georgia",
  "times new roman", "trebuchet ms", "courier new", "comic sans ms",
  "franklin gothic medium",
]);

interface Entrada { familia: string; weight: number; stack: string; }

// Cadena neutra: una grotesca de palo seco. NUNCA Impact -- ese es el bug
// que estamos arreglando.
const NEUTRA = "'Libre Franklin', Inter, 'Helvetica Neue', Arial, sans-serif";
// Para las condensadas de cartel (Impact y compañía) sí corresponde una
// condensada pesada de reemplazo.
const CONDENSADA = "Impact, Haettenschweiler, 'Anton', 'Arial Narrow', sans-serif";

/**
 * Nombres tal como los escribe PowerPoint -> familia real + peso.
 *
 * La clave va en minúsculas. Lo que no esté acá se resuelve por sufijo (ver
 * `separarPeso`), así que la tabla solo lista lo que necesita algo especial.
 */
const TABLA: Record<string, Entrada> = {
  // Franklin Gothic: la familia de Office. Libre Franklin es su revival
  // libre y está en Google, así que sirve de reemplazo real, no de parche.
  "franklin gothic book":        { familia: "Franklin Gothic", weight: 400, stack: `'Franklin Gothic Book', ${NEUTRA}` },
  "franklin gothic medium":      { familia: "Franklin Gothic", weight: 500, stack: `'Franklin Gothic Medium', ${NEUTRA}` },
  "franklin gothic demi":        { familia: "Franklin Gothic", weight: 600, stack: `'Franklin Gothic Demi', ${NEUTRA}` },
  "franklin gothic heavy":       { familia: "Franklin Gothic", weight: 800, stack: `'Franklin Gothic Heavy', ${NEUTRA}` },
  "franklin gothic medium cond": { familia: "Franklin Gothic Cond", weight: 500, stack: `'Franklin Gothic Medium Cond', 'Archivo Narrow', 'Arial Narrow', ${NEUTRA}` },
  "franklin gothic demi cond":   { familia: "Franklin Gothic Cond", weight: 600, stack: `'Franklin Gothic Demi Cond', 'Archivo Narrow', 'Arial Narrow', ${NEUTRA}` },

  // Libre Franklin: la que dispara el bug. Se carga de Google en variable
  // 100-900, asi que el peso del nombre se respeta de verdad.
  "libre franklin":        { familia: "Libre Franklin", weight: 400, stack: NEUTRA },
  "libre franklin medium": { familia: "Libre Franklin", weight: 500, stack: NEUTRA },
  "libre franklin black":  { familia: "Libre Franklin", weight: 900, stack: NEUTRA },

  // Condensadas de cartel.
  "impact":            { familia: "Impact", weight: 400, stack: CONDENSADA },
  "haettenschweiler":  { familia: "Haettenschweiler", weight: 400, stack: CONDENSADA },
  "anton":             { familia: "Anton", weight: 400, stack: CONDENSADA },

  // Arial Black es Arial en 900, no una familia aparte.
  "arial black": { familia: "Arial", weight: 900, stack: `'Arial Black', 'Archivo Black', Arial, ${NEUTRA}` },
  "arial":       { familia: "Arial", weight: 400, stack: `Arial, Helvetica, ${NEUTRA}` },

  // De Office. Carlito es el clon métrico libre de Calibri; Aptos (la nueva
  // por defecto de Office) no tiene clon, se cae a una grotesca neutra.
  "calibri": { familia: "Calibri", weight: 400, stack: `Calibri, Carlito, ${NEUTRA}` },
  "aptos":   { familia: "Aptos",   weight: 400, stack: `Aptos, Inter, ${NEUTRA}` },
};

// Sufijos de peso que PowerPoint pega al nombre de la familia.
const SUFIJOS: [RegExp, number][] = [
  [/\s+(extra\s?black|ultra\s?black)$/i, 900],
  [/\s+black$/i, 900],
  [/\s+(extra\s?bold|ultra\s?bold)$/i, 800],
  [/\s+heavy$/i, 800],
  [/\s+bold$/i, 700],
  [/\s+(semi\s?bold|demi\s?bold|demi)$/i, 600],
  [/\s+medium$/i, 500],
  [/\s+(book|regular|normal)$/i, 400],
  [/\s+light$/i, 300],
  [/\s+(extra\s?light|ultra\s?light)$/i, 200],
  [/\s+thin$/i, 100],
];

function separarPeso(nombre: string): { familia: string; weight: number } {
  for (const [re, w] of SUFIJOS) {
    if (re.test(nombre)) return { familia: nombre.replace(re, "").trim(), weight: w };
  }
  return { familia: nombre, weight: 400 };
}

/**
 * @param familia lo que guardó el importer (`style.font_family`)
 * @param bold    la marca de negrita del cuadro; suma 300 al peso, con techo
 *                en 900, que es lo que hace PowerPoint al poner negrita
 *                sobre una fuente que ya es pesada.
 */
export function resolverFuente(familia?: string | null, bold?: boolean | null): FuenteResuelta {
  const bruto = (familia ?? "").trim();
  if (!bruto) {
    return {
      stack: NEUTRA, weight: bold ? 700 : 400, familia: "(sin definir)",
      pesoNombre: bold ? "Bold" : "Regular", sustituida: false,
    };
  }

  const clave = bruto.toLowerCase();
  const enTabla = TABLA[clave];
  const base = enTabla ?? (() => {
    const { familia: f, weight } = separarPeso(bruto);
    return { familia: f, weight, stack: `'${bruto}', '${f}', ${NEUTRA}` };
  })();

  let weight = base.weight;
  if (bold) weight = Math.min(900, weight + 300);

  return {
    stack: base.stack,
    weight,
    familia: base.familia,
    pesoNombre: NOMBRE_PESO[weight] ?? String(weight),
    // "Sustituida" quiere decir: el navegador no va a tener esta fuente
    // exacta y va a dibujar con la siguiente de la cadena. Las del sistema
    // y Libre Franklin (que la app carga de Google) sí están.
    sustituida: !DEL_SISTEMA.has(clave)
      && !clave.startsWith("libre franklin")
      && !clave.startsWith("franklin gothic"),
  };
}
