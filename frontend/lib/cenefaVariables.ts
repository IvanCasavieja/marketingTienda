// Vocabulario único de variables de cenefas — espejo de
// backend/app/services/cenefas/variables.py.
//
// El nombre de la columna del Excel, el placeholder del PPTX (<<nombre>>) y
// la clave del JSON del template son SIEMPRE el mismo string. Si tocás esta
// lista, tocá también la del backend: son la misma verdad escrita dos veces
// porque no hay endpoint que la exponga.
//
// Ninguna variable es obligatoria.

export type CenefaVarGroup = "precio" | "decimal" | "texto";

export interface CenefaVarDef {
  name: string;
  desc: string;
  group: CenefaVarGroup;
  /** Variable de decimales asociada, para las que son precio. */
  decimal?: string;
}

export const CENEFA_VARIABLES: CenefaVarDef[] = [
  // ── Identificación y textos ───────────────────────────────────────────
  { name: "codigo",         desc: "Código de artículo / SKU",                       group: "texto" },
  { name: "descripcion",    desc: "Nombre del producto",                            group: "texto" },
  { name: "mecanica",       desc: "Mecánica ya redactada (\"Comprando 3, $33 la unidad.\")", group: "texto" },
  { name: "unidadMoneda",   desc: "Símbolo de moneda ($ o U$S) — va al lado de cada precio", group: "texto" },
  { name: "vigencia",       desc: "Período de validez de la promo",                 group: "texto" },
  { name: "aclaracionUno",  desc: "Primera aclaración",                             group: "texto" },
  { name: "aclaracionDos",  desc: "Segunda aclaración",                             group: "texto" },
  { name: "aclaracionTres", desc: "Tercera aclaración",                             group: "texto" },
  { name: "legales",        desc: "Legales — solo se sustituyen si se tildan al generar", group: "texto" },
  { name: "dia",            desc: "Día",                                            group: "texto" },
  { name: "mes",            desc: "Mes",                                            group: "texto" },
  { name: "año",            desc: "Año",                                            group: "texto" },
  { name: "banco",          desc: "Nombre del banco o beneficio",                   group: "texto" },

  // Titular grande de Redexpres, arriba del precio. Es TEXTO aunque traiga
  // numeros y simbolos: no se le separa el decimal ni se le da formato.
  { name: "tipoOferta",    desc: "Tipo de oferta (ej. \"2x1\", \"25% OFF\") — se imprime tal cual", group: "texto" },

  // tipoOfertaComprando y unidad: agregadas 2026-08-26 para Rompe del Finde
  // (Tienda Inglesa), donde la mecánica se reparte en tres lugares en vez de
  // en un renglón: la cocarda (tipoOferta), "Comprando N" arriba del precio
  // (tipoOfertaComprando) y "unidad" abajo del precio (unidad). En Redexpres
  // esa misma mecánica va entera adentro de `mecanica`, así que estas dos
  // quedan vacías ahí. Espejo de backend/app/services/cenefas/variables.py.
  { name: "tipoOfertaComprando", desc: "Cuántas se llevan (ej. \"Comprando 2\")", group: "texto" },
  { name: "unidad",              desc: "La palabra que va debajo del precio (\"unidad\")", group: "texto" },

  // ── Precios (parte entera) ────────────────────────────────────────────
  { name: "precioRegular", desc: "Precio regular / anterior",  group: "precio", decimal: "decimalPrecioRegular" },
  { name: "precioOferta",  desc: "Precio de oferta — el que se muestra grande", group: "precio", decimal: "decimalPrecioOferta" },
  // promoOferta: el literal de la mecánica ("6x4", o el total de un combo)
  // cuando el diseño lo dibuja SUPERPUESTO tapando el cuadro del precio.
  // Es de tipo "precio" solo para que arrastre su decimal como el resto —
  // el valor que lleva puede ser texto. precioOferta siempre es un precio
  // real; lo que tapa al precio es esta variable. Ver variables.py.
  { name: "promoOferta",   desc: "Literal de la mecánica que tapa al precio (ej. \"6x4\")", group: "precio", decimal: "decimalPromoOferta" },
  { name: "ofertaUno",     desc: "Nivel de oferta 1 (ej. \"3x\") — número o texto", group: "precio", decimal: "decimalPrecioUno" },
  { name: "ofertaDos",     desc: "Nivel de oferta 2",          group: "precio", decimal: "decimalPrecioDos" },
  { name: "ofertaTres",    desc: "Nivel de oferta 3",          group: "precio", decimal: "decimalPrecioTres" },
  { name: "ofertaCuatro",  desc: "Nivel de oferta 4",          group: "precio", decimal: "decimalPrecioCuatro" },
  { name: "precioBanco",   desc: "Precio con beneficio bancario", group: "precio", decimal: "decimalPrecioBanco" },

  // ── Decimales (cuadro aparte, siempre con la coma: ",50") ─────────────
  { name: "decimalPrecioRegular", desc: "Decimales de precioRegular", group: "decimal" },
  { name: "decimalPrecioOferta",  desc: "Decimales de precioOferta",  group: "decimal" },
  { name: "decimalPromoOferta",   desc: "Decimales de promoOferta",   group: "decimal" },
  { name: "decimalPrecioUno",     desc: "Decimales de ofertaUno",     group: "decimal" },
  { name: "decimalPrecioDos",     desc: "Decimales de ofertaDos",     group: "decimal" },
  { name: "decimalPrecioTres",    desc: "Decimales de ofertaTres",    group: "decimal" },
  { name: "decimalPrecioCuatro",  desc: "Decimales de ofertaCuatro",  group: "decimal" },
  { name: "decimalPrecioBanco",   desc: "Decimales de precioBanco",   group: "decimal" },
];

export const CENEFA_VARIABLE_NAMES: string[] = CENEFA_VARIABLES.map((v) => v.name);

/**
 * Variables cuyo nombre de columna cambia según el archivo de gestión que se
 * suba, y que por eso hay que mapear a mano en el Convertidor.
 *
 * Las que NO están acá (codigo, descripcion, precioRegular, precioOferta,
 * mecanica y todos los decimales) las resuelve el Convertidor solo: o salen
 * de una columna fija del export, o las calcula él.
 */
export const VARIABLES_MAPEABLES: string[] = [
  "ofertaUno",
  "ofertaDos",
  "ofertaTres",
  "ofertaCuatro",
  "vigencia",
  "aclaracionUno",
  "aclaracionDos",
  "aclaracionTres",
  "legales",
];

export function varDef(name: string): CenefaVarDef | undefined {
  return CENEFA_VARIABLES.find((v) => v.name === name);
}

/**
 * Alias corto de cada variable — espejo de ALIAS_CORTOS en variables.py.
 *
 * La convención es la inicial de cada palabra (`precioOferta` -> `po`,
 * `decimalPrecioRegular` -> `dpr`), conservando el número si lo lleva
 * (`ofertaUno` -> `o1`). El nombre largo sigue siendo el canónico: el alias
 * se acepta solo a la entrada y se resuelve ahí mismo.
 */
export const ALIAS_CORTOS: Record<string, string> = {
  c: "codigo", d: "descripcion", m: "mecanica",
  to: "tipoOferta", toc: "tipoOfertaComprando", u: "unidad", um: "unidadMoneda",
  pr: "precioRegular", dpr: "decimalPrecioRegular",
  po: "precioOferta", dpo: "decimalPrecioOferta",
  pmo: "promoOferta", dpmo: "decimalPromoOferta",
  o1: "ofertaUno", do1: "decimalPrecioUno",
  o2: "ofertaDos", do2: "decimalPrecioDos",
  o3: "ofertaTres", do3: "decimalPrecioTres",
  o4: "ofertaCuatro", do4: "decimalPrecioCuatro",
  pb: "precioBanco", dpb: "decimalPrecioBanco",
  b: "banco", v: "vigencia",
  a1: "aclaracionUno", a2: "aclaracionDos", a3: "aclaracionTres",
  l: "legales", dd: "dia", mm: "mes", aa: "año",
};

/** Sin acentos, sin separadores, minúsculas — espejo de `norm()` en variables.py. */
function norm(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[\s_\-.]+/g, "")
    .toLowerCase();
}

const POR_NORM: Record<string, string> = Object.fromEntries(
  CENEFA_VARIABLE_NAMES.map((v) => [norm(v), v]),
);

/**
 * Nombre de columna o placeholder -> variable canónica, o null si no es una.
 * Espejo de `resolve()` en variables.py: tolera mayúsculas, separadores,
 * acentos y el alias corto, igual que el encabezado del Excel y el `<<...>>`
 * del PPTX.
 */
export function resolverNombreVariable(name: string): string | null {
  if (!name) return null;
  const directo = POR_NORM[norm(name)];
  if (directo) return directo;
  return ALIAS_CORTOS[name.trim().toLowerCase()] ?? null;
}
