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

  // ── Precios (parte entera) ────────────────────────────────────────────
  { name: "precioRegular", desc: "Precio regular / anterior",  group: "precio", decimal: "decimalPrecioRegular" },
  { name: "precioOferta",  desc: "Precio de oferta — el que se muestra grande", group: "precio", decimal: "decimalPrecioOferta" },
  { name: "ofertaUno",     desc: "Nivel de oferta 1 (ej. \"3x\") — número o texto", group: "precio", decimal: "decimalPrecioUno" },
  { name: "ofertaDos",     desc: "Nivel de oferta 2",          group: "precio", decimal: "decimalPrecioDos" },
  { name: "ofertaTres",    desc: "Nivel de oferta 3",          group: "precio", decimal: "decimalPrecioTres" },
  { name: "ofertaCuatro",  desc: "Nivel de oferta 4",          group: "precio", decimal: "decimalPrecioCuatro" },
  { name: "precioBanco",   desc: "Precio con beneficio bancario", group: "precio", decimal: "decimalPrecioBanco" },

  // ── Decimales (cuadro aparte, siempre con la coma: ",50") ─────────────
  { name: "decimalPrecioRegular", desc: "Decimales de precioRegular", group: "decimal" },
  { name: "decimalPrecioOferta",  desc: "Decimales de precioOferta",  group: "decimal" },
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
