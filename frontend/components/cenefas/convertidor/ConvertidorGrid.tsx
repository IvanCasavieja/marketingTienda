"use client";
import { useEffect, useMemo, useRef, useState, ChangeEvent, Dispatch, KeyboardEvent, SetStateAction } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { ArrowLeft, Download, Loader2, Merge, Presentation, Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  convertidorApi,
  type ConvertidorRow,
  type GrupoUnificado,
  type MaPair,
  type UnificarGrupoItem,
} from "@/lib/api";
import { guardarExcelParaCenefa } from "@/lib/cenefaHandoff";
import ConvertidorAiModal from "./ConvertidorAiModal";
import ConvertidorMergeModal from "./ConvertidorMergeModal";
import ConvertidorUnifyModal from "./ConvertidorUnifyModal";
import TininMecanica from "./TininMecanica";
import TininRevision, { type TemaTinin } from "./TininRevision";

// Virtualización manual (sin librería nueva): solo se renderizan las filas
// visibles ± un buffer, con dos <tr> espaciadores para mantener el alto de
// scroll correcto — un export de gestión puede traer varios miles de filas
// y montar un <tr> real por cada una trababa el navegador.
const ROW_HEIGHT = 40;
const CONTAINER_HEIGHT = 560;
const BUFFER_ROWS = 8;
const SAVE_DEBOUNCE_MS = 800;

type ColumnKey =
  // contexto del export de gestión (solo lectura, no se exporta)
  | "nombreArticulo" | "comprador" | "moneda" | "ofertaOrigen" | "ofertaDet" | "descripcionWeb"
  // las 26 variables
  | "codigo" | "descripcion" | "mecanica"
  | "tipoOferta" | "unidadMoneda"
  | "precioRegular" | "decimalPrecioRegular"
  | "precioOferta" | "decimalPrecioOferta"
  | "ofertaUno" | "decimalPrecioUno"
  | "ofertaDos" | "decimalPrecioDos"
  | "ofertaTres" | "decimalPrecioTres"
  | "ofertaCuatro" | "decimalPrecioCuatro"
  | "precioBanco" | "decimalPrecioBanco" | "banco"
  | "vigencia" | "aclaracionUno" | "aclaracionDos" | "aclaracionTres" | "legales"
  | "dia" | "mes" | "año";

// "descripcion" es editable con lógica propia (guardado al catálogo
// compartido + sugerencias IA, ver handleDescripcionChange). "simple" es
// edición local: no persiste a ningún lado hasta exportar.
type EditableKind = "descripcion" | "simple";

interface ColumnDef {
  key: ColumnKey;
  label: string;
  editable?: EditableKind;
  warningCodes?: string[];
  /** Columna del export de gestión: contexto para revisar, no se exporta. */
  contexto?: boolean;
  /** Se muestra siempre, aunque venga vacía en todas las filas. */
  siempre?: boolean;
}

// Ancho de cada columna, en px. La tabla es table-fixed: sin un ancho propio
// reparte el espacio en partes iguales y los encabezados largos se desbordan
// sobre el de al lado ("DECIMALPRECIOOFERTA" pegado a "OFERTAUNO"). Con anchos
// explicitos la tabla se hace mas ancha que el contenedor y scrollea, que es
// lo que ya hace el contenedor (overflow-auto).
// Cada precio con su columna de decimales. Si el precio se muestra, el decimal
// va con el aunque este vacio.
const DECIMAL_DE: [ColumnKey, ColumnKey][] = [
  ["ofertaUno",    "decimalPrecioUno"],
  ["ofertaDos",    "decimalPrecioDos"],
  ["ofertaTres",   "decimalPrecioTres"],
  ["ofertaCuatro", "decimalPrecioCuatro"],
  ["precioBanco",  "decimalPrecioBanco"],
];

const ANCHO_TEXTO_LARGO = 240;   // descripcion, mecanica, legales, aclaraciones
const ANCHO_DECIMAL     = 170;   // decimalPrecioRegular y compania: nombres largos
const ANCHO_CONTEXTO    = 170;   // las columnas de gestion, con su punto adelante
const ANCHO_NORMAL      = 140;

const CLAVES_TEXTO_LARGO = new Set([
  "descripcion", "mecanica", "legales",
  "aclaracionUno", "aclaracionDos", "aclaracionTres",
]);

function anchoDeColumna(c: ColumnDef): number {
  if (CLAVES_TEXTO_LARGO.has(c.key)) return ANCHO_TEXTO_LARGO;
  if (c.key.startsWith("decimal")) return ANCHO_DECIMAL;
  if (c.contexto) return ANCHO_CONTEXTO;
  return ANCHO_NORMAL;
}

const COLUMNS: ColumnDef[] = [
  // ── Lo que define la cenefa ─────────────────────────────────────────────
  { key: "codigo",        label: "codigo",      siempre: true },
  { key: "descripcion",   label: "descripcion", editable: "descripcion", siempre: true,
    warningCodes: ["missing_description", "descripcion_invalida", "descripcion_larga", "descripcion_algo_larga"] },
  // Sin warningCodes a propósito: los avisos de mecánica nacen de OFERTA y
  // OFERTADET, y se pintan allá. Ver la nota en esas dos columnas.
  { key: "mecanica",      label: "mecanica",    editable: "simple", siempre: true },
  // Los avisos de mecánica ("combo_no_parseable", etc.) se pintan acá desde
  // 2026-08-29: tipoOferta ES la columna OFERTA renombrada (el crudo ya no se
  // muestra aparte), así que el valor, la edición y el aviso viven juntos.
  { key: "tipoOferta",    label: "tipoOferta",    editable: "simple",
    warningCodes: ["oferta_inesperada", "combo_no_parseable", "mxn_no_parseable", "mxn_sin_precio"] },
  // El simbolo de moneda ("$" / "U$S"), variable propia desde 2026-08-29:
  // el Convertidor la escribe siempre desde MONEDA. Editable por si una fila
  // puntual necesita corregirse a mano.
  { key: "unidadMoneda",  label: "unidadMoneda",  editable: "simple", siempre: true,
    warningCodes: ["moneda_invalida", "moneda_no_pesos"] },
  { key: "precioRegular", label: "precioRegular", editable: "simple", siempre: true,
    warningCodes: ["missing_precio_anterior", "precio_anterior_invalido"] },
  { key: "decimalPrecioRegular", label: "decimalPrecioRegular", editable: "simple", siempre: true },
  { key: "precioOferta",  label: "precioOferta",  editable: "simple", siempre: true,
    warningCodes: ["missing_price", "precio_invalido", "moneda_invalida", "moneda_no_pesos"] },
  { key: "decimalPrecioOferta", label: "decimalPrecioOferta", editable: "simple", siempre: true },
  { key: "ofertaUno",     label: "ofertaUno",     editable: "simple" },
  { key: "decimalPrecioUno",    label: "decimalPrecioUno", editable: "simple" },
  { key: "ofertaDos",     label: "ofertaDos",     editable: "simple" },
  { key: "decimalPrecioDos",    label: "decimalPrecioDos", editable: "simple" },
  { key: "ofertaTres",    label: "ofertaTres",    editable: "simple" },
  { key: "decimalPrecioTres",   label: "decimalPrecioTres", editable: "simple" },
  { key: "ofertaCuatro",  label: "ofertaCuatro",  editable: "simple" },
  { key: "decimalPrecioCuatro", label: "decimalPrecioCuatro", editable: "simple" },
  { key: "precioBanco",   label: "precioBanco",   editable: "simple" },
  { key: "decimalPrecioBanco",  label: "decimalPrecioBanco", editable: "simple" },
  { key: "banco",         label: "banco",         editable: "simple" },
  { key: "vigencia",      label: "vigencia",      editable: "simple" },
  { key: "aclaracionUno", label: "aclaracionUno", editable: "simple" },
  { key: "aclaracionDos", label: "aclaracionDos", editable: "simple" },
  { key: "aclaracionTres",label: "aclaracionTres",editable: "simple" },
  { key: "legales",       label: "legales",       editable: "simple" },
  { key: "dia",           label: "dia",           editable: "simple" },
  { key: "mes",           label: "mes",           editable: "simple" },
  { key: "año",           label: "año",           editable: "simple" },

  // ── Contexto de gestión: de dónde salió lo de arriba ────────────────────
  { key: "nombreArticulo", label: "· Nombre gestión", contexto: true, siempre: true,
    warningCodes: ["nombre_articulo_invalido"] },
  // Estas dos son de donde sale la mecánica, así que también es donde se
  // marca cuando no cierra. Antes se pintaba la columna "mecanica", que es
  // donde se corrige pero no donde está el problema: se veían dos celdas que
  // decían "Precio Final" igual, una morada y otra no, sin forma de entender
  // por qué mirando esa columna.
  { key: "ofertaDet",      label: "· Oferta Det",     contexto: true, siempre: true,
    warningCodes: ["missing_oferta_det", "oferta_det_invalido"] },
  // La columna "· Oferta" (el crudo de gestión) se eliminó el 2026-08-29:
  // tipoOferta ES esa columna renombrada por el Convertidor, mostrarla dos
  // veces era duplicarla. Los avisos que vivían acá pasaron a tipoOferta.
  { key: "moneda",          label: "· Moneda",         contexto: true, siempre: true },
  { key: "comprador",       label: "· Comprador",      contexto: true },
  { key: "descripcionWeb", label: "· Descripción web", contexto: true,
    warningCodes: ["missing_descripcion_web", "descripcion_web_invalida"] },
];

// Warnings de "hay contenido que no cierra" — no se arreglan completando el
// dato, los tiene que mirar una persona. Espejo de _INVALID_TYPE_CODES en
// backend/app/services/cenefas/convertidor.py.
const INVALID_TYPE_CODES = new Set([
  "nombre_articulo_invalido", "descripcion_invalida", "descripcion_larga",
  "moneda_invalida", "moneda_no_pesos",
  "precio_anterior_invalido", "precio_invalido", "oferta_det_invalido",
  "descripcion_web_invalida",
  "oferta_inesperada", "combo_no_parseable", "mxn_no_parseable", "mxn_sin_precio",
]);

const HAS_LETTER_RE = /\p{L}/u;
// Mismos umbrales que DESCRIPTION_WARN_CHARS/DESCRIPTION_MAX_CHARS en
// backend/app/services/cenefas/validation_engine.py — duplicados acá (no
// hay endpoint que los exponga) para recalcular el warning client-side sin
// esperar un round-trip al backend en cada tecla.
const DESCRIPTION_WARN_CHARS = 60;
const DESCRIPTION_MAX_CHARS = 100;
const DESCRIPCION_WARNING_CODES = ["missing_description", "descripcion_invalida", "descripcion_larga", "descripcion_algo_larga"];
// El tope SKU_COMBINADO_MAX_CHARS se eliminó el 2026-08-28: la clave combinada
// ya no se guarda en sku_descripciones (los grupos viven en
// cenefa_grupos_unificados, donde los SKU van como lista), así que no hay
// columna que la limite.

// ¿La descripción ya dice con qué cantidad/unidad se cobra? Espejo de
// _RE_CANTIDAD_PROPIA en backend/app/services/cenefas/convertidor.py, duplicado
// acá porque se recalcula en vivo mientras se edita la celda (no hay endpoint
// que lo exponga, mismo criterio que los umbrales de largo de arriba).
const CANTIDAD_EN_TEXTO_RE =
  /\d\s*(?:kgs?|kilos?|kg|grs?|gramos?|g|mls?|cc|litros?|lts?|l|un|u)\b|\bx\s*\d+\b|(?:^|[\s.])kg\.?(?:$|[\s.,)])/i;

function computeDescripcionWarnings(currentWarnings: string[], value: string): string[] {
  const warnings = currentWarnings.filter((w) => !DESCRIPCION_WARNING_CODES.includes(w));
  const trimmed = value.trim();
  if (!trimmed) warnings.push("missing_description");
  else if (!HAS_LETTER_RE.test(trimmed)) warnings.push("descripcion_invalida");
  else if (trimmed.length > DESCRIPTION_MAX_CHARS) warnings.push("descripcion_larga");
  else if (trimmed.length > DESCRIPTION_WARN_CHARS) warnings.push("descripcion_algo_larga");
  return warnings;
}

// El precio ajustado del modal de IA (÷10 para fiambres que pasan a 100g)
// llega como número, pero en la grilla los precios viven partidos en entero +
// decimal, con formato uruguayo. Espejo de split_price() en
// backend/app/services/cenefas/data_engine.py.
function partirPrecio(
  claveEntero: string, claveDecimal: string, valor?: number,
): Record<string, string> {
  if (valor === undefined || !Number.isFinite(valor) || valor <= 0) return {};
  const entero = Math.trunc(valor);
  const centavos = Math.round((valor - entero) * 100);
  return {
    [claveEntero]: entero.toLocaleString("es-UY").replace(/,/g, "."),
    // Un precio redondo no imprime ",00": el diseño de la cenefa no lo contempla.
    [claveDecimal]: centavos > 0 ? "," + String(centavos).padStart(2, "0") : "",
  };
}

// El precio de la grilla vive partido en entero + decimal con formato
// uruguayo ("1.100" + ",50"). Esto lo vuelve a armar como numero para poder
// operarlo. Inverso de partirPrecio.
function aNumero(entero: string, decimal: string): number {
  return parseFloat((entero || "").replace(/\./g, "") + (decimal || "").replace(",", "."));
}

// El precio de 100 g que se le propone al usuario, ya formateado.
function precioA100g(entero: string, decimal: string): string {
  const n = aNumero(entero, decimal);
  if (!Number.isFinite(n) || n <= 0) return "—";
  const p = partirPrecio("entero", "decimal", n / 10);
  return `${p.entero ?? ""}${p.decimal ?? ""}`;
}

interface Props {
  rows: ConvertidorRow[];
  setRows: Dispatch<SetStateAction<ConvertidorRow[] | null>>;
  maPairs: MaPair[];
  onReset: () => void;
  /**
   * Rehace la conversión con el mismo mapeo. Hace falta cuando Tinín aprende
   * una mecánica nueva: eso lo resuelve el backend, así que la grilla que está
   * en pantalla no lo refleja hasta volver a pedirla.
   */
  onRevalidar?: () => void;
}

function maPairKey(sku1: string, sku2: string): string {
  return `${sku1}|${sku2}`;
}

export default function ConvertidorGrid({ rows, setRows, maPairs, onReset, onRevalidar }: Props) {
  const { t } = useTranslation();
  const [scrollTop, setScrollTop] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [enviandoACenefa, setEnviandoACenefa] = useState(false);
  const router = useRouter();
  const [savingRowId, setSavingRowId] = useState<number | null>(null);
  const [pendingFocusRowId, setPendingFocusRowId] = useState<number | null>(null);
  // Snapshot local: arranca desde la prop (calculada una vez por el backend
  // al hacer preview) y se achica sola a medida que se unifican o descartan
  // pares -- "descartar" no persiste entre sesiones, es solo estado local.
  const [pendingPairs, setPendingPairs] = useState<MaPair[]>(maPairs);
  const [dismissedPairKeys, setDismissedPairKeys] = useState<Set<string>>(new Set());
  const [mergePair, setMergePair] = useState<MaPair | null>(null);
  // Barra tipo Excel: separado en hover vs. foco (por teclado) para que,
  // al sacar el mouse de la celda que además tiene el foco, la barra no
  // quede vacía -- vuelve a mostrar la celda enfocada en vez de nada.
  const [hoveredCell, setHoveredCell] = useState<{ rowId: number; key: ColumnKey } | null>(null);
  const [focusedCell, setFocusedCell] = useState<{ rowId: number; key: ColumnKey } | null>(null);
  const activeCell = hoveredCell ?? focusedCell;
  // Que columnas se ven: las marcadas "siempre" mas las que traen algun dato.
  // Es el mismo criterio con el que el backend arma el Excel de salida
  // (_columnas_de_salida), asi que la grilla muestra exactamente lo que va a
  // bajar: ni una columna vacia de mas.
  //
  // Un precio arrastra su decimal aunque el decimal quede vacio: son un par y
  // el diseno de la cenefa tiene un cuadro aparte para cada uno.
  const columnasVisibles = useMemo(() => {
    const conDato = new Set(
      COLUMNS.filter((c) => rows.some((r) => String(r[c.key] ?? "").trim() !== ""))
             .map((c) => c.key),
    );
    for (const [precio, decimal] of DECIMAL_DE) {
      if (conDato.has(precio)) conDato.add(decimal);
    }
    return COLUMNS.filter((c) => c.siempre || conDato.has(c.key));
  }, [rows]);
  const activeCellColumn = activeCell ? COLUMNS.find((c) => c.key === activeCell.key) : undefined;
  const activeCellRow = activeCell ? rows.find((r) => r.row_id === activeCell.rowId) : undefined;
  const activeCellValue =
    activeCellColumn && activeCellRow ? String(activeCellRow[activeCellColumn.key] ?? "") : "";
  // Snapshot fijo tomado al abrir el modal, NO la lista viva
  // rowsNeedingDescripcion -- esa se achica sola a medida que se aprueban
  // filas (porque quita el warning missing_description), y si el modal
  // recibiera esa lista directamente cada fila aprobada desaparecería del
  // modal en vez de quedar mostrando el check verde.
  const [aiModalRows, setAiModalRows] = useState<ConvertidorRow[] | null>(null);
  // Snapshot fijo tomado al abrir el modal, mismo criterio que aiModalRows --
  // "Unificar categorías" analiza TODAS las filas del Excel cargado (no solo
  // las que faltan descripción, a diferencia del modal de IA de arriba).
  const [unifyModalRows, setUnifyModalRows] = useState<ConvertidorRow[] | null>(null);
  const pendingSaves = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const dlRef = useRef<HTMLAnchorElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const descripcionInputRefs = useRef<Map<number, HTMLInputElement>>(new Map());

  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_ROWS);
  const visibleCount = Math.ceil(CONTAINER_HEIGHT / ROW_HEIGHT) + BUFFER_ROWS * 2;
  const endIndex = Math.min(rows.length, startIndex + visibleCount);
  const visibleRows = useMemo(() => rows.slice(startIndex, endIndex), [rows, startIndex, endIndex]);
  const topSpacer = startIndex * ROW_HEIGHT;
  const bottomSpacer = (rows.length - endIndex) * ROW_HEIGHT;

  // Botonera de navegación rápida: filas que todavía necesitan descripción
  // (missing_description se recalcula en cada edit, así que esta lista se
  // achica sola a medida que se van completando).
  const rowsNeedingDescripcion = useMemo(
    () => rows.filter((r) => r.warnings.includes("missing_description")),
    [rows]
  );

  // Vivo, no una foto fija del preview inicial -- así el contador refleja
  // las filas aprobadas en esta misma sesión (vía "Generar con IA" o edición
  // manual) sin necesitar recargar la página.
  const matchedCount = rows.length - rowsNeedingDescripcion.length;

  // Fiambres cuyo nombre/descripción todavía dice "kg" — necesitan pasar a
  // 100g (descripción + precio÷10) aunque ya tengan descripción matcheada
  // del catálogo, por eso es un filtro aparte y no solo un warning más.
  const rowsFiambresKg = useMemo(() => rows.filter((r) => r.esFiambreKg), [rows]);

  // Se cobran por 100 g o por kilo y la descripción no lo dice. Mismo criterio
  // de filtro aparte que rowsFiambresKg de arriba: una descripción que ya vino
  // del catálogo escrita sin gramaje no tiene ningún warning, así que sin esto
  // nunca volvía a pasar por Tinín y el cartel salía sin decir por cuánto se
  // cobra. Las que NO tienen descripción ya entran por missing_description, y
  // las que alguien escribió a mano en el Excel quedan afuera: esas no se
  // reescriben (decisión de 2026-08-24, ver match_rows en convertidor.py).
  const rowsSinUnidad = useMemo(
    () => rows.filter((r) => r.unidadVenta && !r.esFiambreKg
                             && r.descripcionOrigen !== "excel"
                             && r.descripcion.trim() && !CANTIDAD_EN_TEXTO_RE.test(r.descripcion)),
    [rows]
  );

  // Grupos unificados que ya se armaron antes y tocan los SKU de este listado.
  //
  // Se busca UNA vez, con los códigos tal como vinieron del Excel -- no con
  // cada cambio de la grilla: unificar cambia los códigos (pasan a ser el
  // combinado) y volver a preguntar con eso no encontraría nada y además haría
  // parpadear el aviso justo después de resolverlo.
  const [grupos, setGrupos] = useState<GrupoUnificado[]>([]);
  const [gruposDescartados, setGruposDescartados] = useState<Set<string>>(new Set());

  useEffect(() => {
    const skus = rows.map((r) => r.codigo).filter(Boolean);
    if (skus.length === 0) return;
    let vivo = true;
    convertidorApi
      .buscarGruposUnificados(skus)
      .then(({ data }) => { if (vivo) setGrupos(data.grupos); })
      // Silencioso a propósito: esto es una ayuda, no un paso del flujo. Si el
      // pedido falla la grilla funciona igual y no hay nada que la persona
      // pueda hacer con el error.
      .catch(() => {});
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Aplica un grupo COMPLETO: las filas de esos SKU pasan a ser una sola, con
  // la descripción que ya se escribió la vez pasada.
  async function aplicarGrupo(g: GrupoUnificado) {
    const filas = rows.filter((r) => g.presentes.includes(r.codigo));
    if (filas.length < 2) {
      toast.error(t("convertidor.grupos.noEstanLasFilas"));
      return;
    }
    try {
      await commitUnificacion({
        row_ids:     filas.map((r) => r.row_id),
        skus:        filas.map((r) => r.codigo),
        grupo:       g.nombre,
        descripcion: g.descripcion,
      });
    } catch {
      // El toast del error ya lo mostró commitUnificacion; el grupo queda
      // ofrecido para reintentar en vez de descartarse sin haberse aplicado.
      return;
    }
    setGruposDescartados((prev) => new Set(prev).add(g.id));
  }

  // Se vende por 100 g pero el precio vino del kilo -- el caso inverso al de
  // arriba: acá la descripción ya está bien y el que quedó mal es el precio.
  // Pasó de verdad y se imprimió (Rompe del Finde 27 al 30/8: jamón crudo a
  // $1.100 cuando los 100 g eran $110). La app NO divide sola: lo propone y
  // alguien confirma, porque un falso positivo imprime un precio diez veces
  // más barato en la góndola.
  const rowsPrecioDeKilo = useMemo(
    () => rows.filter((r) => r.precioDeKiloEn100g), [rows]);

  function pasarPreciosA100g(ids: Set<number>) {
    setRows((prev) => (prev ?? []).map((r) => {
      if (!ids.has(r.row_id)) return r;
      const oferta   = aNumero(r.precioOferta, r.decimalPrecioOferta);
      const regular  = aNumero(r.precioRegular, r.decimalPrecioRegular);
      return {
        ...r,
        ...partirPrecio("precioOferta", "decimalPrecioOferta",
                        Number.isFinite(oferta) ? oferta / 10 : undefined),
        ...partirPrecio("precioRegular", "decimalPrecioRegular",
                        Number.isFinite(regular) ? regular / 10 : undefined),
        // Sin limpiar la bandera y el warning la fila vuelve a aparecer en el
        // aviso en el próximo render, ya con el precio corregido.
        precioDeKiloEn100g: false,
        warnings: (r.warnings ?? []).filter((w) => w !== "precioDeKiloEn100g"),
      };
    }));
    toast.success(t("convertidor.tinin.cienGramosAplicado", { count: ids.size }));
  }

  // Combinado para el modal de IA, en orden de urgencia y sin repetir una fila
  // que caiga en más de una lista: fiambres por kg (descripción + precio),
  // después las que no tienen descripción, y al final las que la tienen pero sin
  // la unidad de cobro.
  const rowsParaIA = useMemo(() => {
    const vistas = new Set<number>();
    const combinadas: ConvertidorRow[] = [];
    for (const r of [...rowsFiambresKg, ...rowsNeedingDescripcion, ...rowsSinUnidad]) {
      if (vistas.has(r.row_id)) continue;
      vistas.add(r.row_id);
      combinadas.push(r);
    }
    return combinadas;
  }, [rowsFiambresKg, rowsNeedingDescripcion, rowsSinUnidad]);

  // Pares "mismo producto, dos SKUs" todavía vigentes -- ni unificados ni
  // descartados en esta sesión.
  const visiblePairs = useMemo(
    () => pendingPairs.filter((p) => !dismissedPairKeys.has(maPairKey(p.sku1, p.sku2))),
    [pendingPairs, dismissedPairKeys]
  );

  function dismissPair(pair: MaPair) {
    setDismissedPairKeys((prev) => new Set(prev).add(maPairKey(pair.sku1, pair.sku2)));
  }

  // Unifica las dos filas en una sola con SKU combinado "SKU1 - SKU2".
  // Desde 2026-08-28 el grupo se persiste SOLO en cenefa_grupos_unificados
  // (guardarGrupoUnificado): el catálogo singular (sku_descripciones) nunca
  // más recibe claves combinadas -- ahí cada SKU lleva la descripción de ESE
  // producto, y lo grupal vive aparte. El código combinado queda solo en la
  // grilla y en el Excel de salida, como texto.
  async function commitMerge(pair: MaPair, descripcion: string) {
    const skuCombinado = `${pair.sku1} - ${pair.sku2}`;
    try {
      await convertidorApi.guardarGrupoUnificado(descripcion, descripcion, [pair.sku1, pair.sku2]);
    } catch (err: any) {
      // Única persistencia del grupo: si falla, no hay nada guardado y
      // unificar la grilla igual sería mentirle al usuario.
      toast.error(err?.response?.data?.detail ?? t("convertidor.grupos.noSeGuardo"));
      return;
    }
    setRows((prev) =>
      (prev ?? [])
        .filter((r) => r.codigo !== pair.sku2)
        .map((r) =>
          r.codigo === pair.sku1
            ? {
                ...r,
                codigo: skuCombinado,
                descripcion,
                warnings: computeDescripcionWarnings(r.warnings, descripcion),
              }
            : r
        )
    );
    setPendingPairs((prev) => prev.filter((p) => !(p.sku1 === pair.sku1 && p.sku2 === pair.sku2)));
    setMergePair(null);
    toast.success(t("convertidor.merge.merged", { sku: skuCombinado }));
  }

  // Combina las N filas del grupo en una sola. El código combinado ("A - B - C",
  // ordenado, para que el mismo conjunto sea siempre la misma clave visible)
  // queda SOLO en la grilla y en el Excel de salida: desde 2026-08-28 el grupo
  // se persiste únicamente en cenefa_grupos_unificados -- el catálogo singular
  // no recibe más claves combinadas. La primera fila del grupo sobrevive con
  // el código y la descripción combinados; el resto se saca de la grilla.
  async function commitUnificacion(grupo: UnificarGrupoItem) {
    const skusOrdenados = [...grupo.skus].sort();
    const codigoCombinado = skusOrdenados.join(" - ");
    // Única persistencia del grupo (por su CONJUNTO de SKU, no por el código
    // combinado: así mañana se detecta que vinieron 2 de los 3). Si falla, no
    // se unifica nada -- unificar la grilla sin guardar sería mentir.
    try {
      await convertidorApi.guardarGrupoUnificado(grupo.grupo, grupo.descripcion, skusOrdenados);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.grupos.noSeGuardo"));
      throw err;
    }
    const [rowIdSuperviviente, ...rowIdsAEliminar] = grupo.row_ids;
    const idsAEliminar = new Set(rowIdsAEliminar);
    setRows((prev) =>
      (prev ?? [])
        .filter((r) => !idsAEliminar.has(r.row_id))
        .map((r) =>
          r.row_id === rowIdSuperviviente
            ? {
                ...r,
                codigo: codigoCombinado,
                descripcion: grupo.descripcion,
                warnings: computeDescripcionWarnings(r.warnings, grupo.descripcion),
              }
            : r
        )
    );
    toast.success(t("convertidor.unificar.saved", { grupo: grupo.grupo, count: grupo.skus.length }));
  }

  function scrollToRow(rowId: number) {
    const container = scrollContainerRef.current;
    if (!container) return;
    const target = Math.max(0, rowId * ROW_HEIGHT - CONTAINER_HEIGHT / 2 + ROW_HEIGHT / 2);
    container.scrollTop = target;
    setScrollTop(target);
    setPendingFocusRowId(rowId);
  }

  // Una vez que la fila objetivo entra en el rango virtualizado (post-scroll),
  // enfocar su input de descripción para poder tipear de una.
  useEffect(() => {
    if (pendingFocusRowId === null) return;
    if (!visibleRows.some((r) => r.row_id === pendingFocusRowId)) return;
    const input = descripcionInputRefs.current.get(pendingFocusRowId);
    if (input) {
      input.focus();
      input.select();
    }
    setPendingFocusRowId(null);
  }, [visibleRows, pendingFocusRowId]);

  // Devuelve si el guardado salió bien -- nunca lanza, porque el uso más
  // común (debounce/Enter en la grilla) es fire-and-forget con el toast
  // como única señal. commitDescripcion (usado por el modal de IA) sí
  // necesita saber el resultado real para no marcar "aprobado" un guardado
  // que en realidad falló -- ver ahí abajo.
  async function flushSave(rowId: number, sku: string, descripcion: string): Promise<boolean> {
    setSavingRowId(rowId);
    try {
      await convertidorApi.updateDescripcion(sku, descripcion);
      toast.success(t("convertidor.savedToCatalog", { sku }));
      return true;
    } catch {
      toast.error(t("convertidor.saveError"));
      return false;
    } finally {
      setSavingRowId((cur) => (cur === rowId ? null : cur));
    }
  }

  // Edición "simple" (todas las variables salvo descripcion): sin catálogo ni
  // debounce a un backend — solo actualiza el estado local, va al export tal
  // cual quede tipeado.
  function handleSimpleFieldChange(rowId: number, key: ColumnKey, value: string) {
    setRows((prev) => (prev ?? []).map((r) => (r.row_id === rowId ? { ...r, [key]: value } : r)));
  }

  function handleDescripcionChange(rowId: number, sku: string, value: string) {
    const trimmed = value.trim();
    setRows((prev) =>
      (prev ?? []).map((r) =>
        r.row_id === rowId
          ? { ...r, descripcion: value, warnings: computeDescripcionWarnings(r.warnings, value) }
          : r
      )
    );

    if (pendingSaves.current[rowId]) clearTimeout(pendingSaves.current[rowId]);
    // Nunca persistir en el catálogo compartido una descripción vacía o sin letras.
    if (!trimmed || !HAS_LETTER_RE.test(trimmed)) return;
    pendingSaves.current[rowId] = setTimeout(() => {
      delete pendingSaves.current[rowId];
      flushSave(rowId, sku, value);
    }, SAVE_DEBOUNCE_MS);
  }

  // Enter guarda ya (sin esperar el debounce de 800ms) — así el usuario
  // tiene una confirmación inmediata en vez de tener que confiar en que
  // el guardado automático silencioso funcionó.
  function handleDescripcionKeyDown(e: KeyboardEvent<HTMLInputElement>, rowId: number, sku: string) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const value = e.currentTarget.value.trim();
    if (!value || !HAS_LETTER_RE.test(value)) return;
    if (pendingSaves.current[rowId]) {
      clearTimeout(pendingSaves.current[rowId]);
      delete pendingSaves.current[rowId];
    }
    flushSave(rowId, sku, value);
  }

  // Callback que usa el modal de IA al aprobar una sugerencia (individual o
  // en bloque) — reusa flushSave (el mismo PATCH + toast que ya existe, no
  // se duplica lógica de guardado), agregando solo la actualización
  // inmediata que handleDescripcionChange hace al tipear. No comparte
  // código con handleDescripcionChange porque ese además programa el
  // debounce, y acá hace falta guardar ya (el usuario ya aprobó).
  async function commitDescripcion(
    rowId: number,
    sku: string,
    value: string,
    precioOverride?: { precio?: number; precioAnterior?: number }
  ) {
    const trimmed = value.trim();
    if (!trimmed || !HAS_LETTER_RE.test(trimmed)) {
      // El modal marca "aprobado" solo si esta promesa resuelve sin lanzar
      // -- una sugerencia vacía o sin letras nunca debería contarse como
      // guardada, aunque el usuario haya clickeado "Aprobar".
      throw new Error("Descripción inválida: no puede quedar vacía ni sin letras");
    }
    setRows((prev) =>
      (prev ?? []).map((r) =>
        r.row_id === rowId
          ? {
              ...r,
              descripcion: value,
              warnings: computeDescripcionWarnings(r.warnings, value),
              // Ya se aprobó desde acá (el único lugar que resuelve description
              // + precio÷10 juntos) -- sin este reset, una fila fiambre_kg ya
              // aprobada seguía volviendo a aparecer en "Generar con IA" cada
              // vez que se reabría el modal en la misma sesión, porque este
              // flag nunca se limpiaba y rowsFiambresKg se arma a partir de él.
              esFiambreKg: false,
              // El precio ajustado (÷10 para fiambres que pasan a 100g) solo
              // se actualiza acá, en el estado local — nunca se manda al
              // backend. sku_descripciones no tiene columnas de precio y así
              // se mantiene: el PATCH de abajo (flushSave) sigue mandando
              // únicamente la descripción, igual que siempre.
              ...partirPrecio("precioOferta", "decimalPrecioOferta", precioOverride?.precio),
              ...partirPrecio("precioRegular", "decimalPrecioRegular", precioOverride?.precioAnterior),
            }
          : r
      )
    );
    const ok = await flushSave(rowId, sku, value);
    if (!ok) throw new Error("No se pudo guardar la descripción");
  }

  /** Vacía el debounce de guardado para que nada tipeado recién se pierda. */
  async function flushPendientes() {
    for (const rowId of Object.keys(pendingSaves.current).map(Number)) {
      clearTimeout(pendingSaves.current[rowId]);
      delete pendingSaves.current[rowId];
      const row = rows.find((r) => r.row_id === rowId);
      if (row && row.descripcion.trim()) await flushSave(rowId, row.codigo, row.descripcion);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      await flushPendientes();
      const { data: blob } = await convertidorApi.export(rows);
      const url = URL.createObjectURL(new Blob([blob]));
      if (dlRef.current) {
        dlRef.current.href = url;
        dlRef.current.download = "convertidor_cenefas.xlsx";
        dlRef.current.click();
      }
      URL.revokeObjectURL(url);
      toast.success(t("convertidor.downloaded"));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setExporting(false);
    }
  }

  // "Convertir a cenefa": el mismo Excel que se descargaría, pero entregado
  // directo al generador en vez de bajarlo y volver a subirlo. Viaja por
  // sessionStorage (un File no entra en un query param) y lo levanta
  // materiales/cenefas/page.tsx, que lo borra apenas lo lee.
  async function handleConvertirACenefa() {
    setEnviandoACenefa(true);
    try {
      await flushPendientes();
      const { data: blob } = await convertidorApi.export(rows);
      await guardarExcelParaCenefa(blob as Blob);
      router.push("/materiales/cenefas");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
      setEnviandoACenefa(false);
    }
  }

  // Por qué está marcada esta celda, en castellano. Sin esto hay que deducirlo
  // mirando otras columnas, y con dos filas que dicen lo mismo es imposible.
  function warningMotivo(row: ConvertidorRow, c: ColumnDef): string | undefined {
    const code = c.warningCodes?.find((x) => row.warnings.includes(x));
    if (!code) return undefined;
    const valor = String(row[c.key] ?? "").trim();
    const textos: Record<string, string> = {
      oferta_inesperada:
        `No entiendo «${valor}» acá. Esperaba una etiqueta conocida (PVP, ANTE/DESPUES, ` +
        `FULL PRICE) o una copia del precio. La mecánica se armó ignorando este valor, ` +
        `así que si tenía que salir en el cartel, no sale.`,
      combo_no_parseable:  `Es un combo pero no pude leerlo de «${valor}». Esperaba algo tipo "3x99".`,
      mxn_no_parseable:    `Es un M x N pero no pude leerlo de «${valor}». Esperaba algo tipo "2x1".`,
      mxn_sin_precio:      "Es un M x N y falta el precio unitario, así que no puedo redactar la mecánica.",
      missing_oferta_det:  "Falta el tipo de mecánica, así que la armé como precio fijo.",
      oferta_det_invalido: `Acá esperaba el tipo de mecánica y vino un número («${valor}»). ` +
                           `Puede ser que el Excel tenga las columnas corridas.`,
      missing_description: "Este SKU no tiene descripción: hay que escribirla o generarla.",
      descripcion_invalida: "Esto no parece una descripción.",
      descripcion_larga:   `${valor.length} caracteres: no entra en el cartel.`,
      descripcion_algo_larga: `${valor.length} caracteres: puede no entrar, conviene acortarla.`,
      missing_price:       "Falta el precio.",
      precio_invalido:     `«${valor}» no es un precio.`,
      missing_precio_anterior: "Falta el precio anterior.",
      precio_anterior_invalido: `«${valor}» no es un precio.`,
      moneda_invalida:     `No reconozco la moneda «${valor}».`,
      moneda_no_pesos:     `Está en «${valor}», no en pesos: revisá que el precio sea el correcto.`,
      nombre_articulo_invalido: "Esto no parece el nombre del artículo.",
      missing_descripcion_web: "Sin descripción web: si hay que generar la descripción con IA, sale peor.",
      descripcion_web_invalida: "La descripción web no parece válida.",
    };
    return textos[code] ?? code;
  }

  function warningClass(row: ConvertidorRow, codes?: string[]): string {
    const code = codes?.find((c) => row.warnings.includes(c));
    if (!code) return "";
    if (code === "missing_description") {
      return "bg-rose-50 dark:bg-rose-500/10 ring-1 ring-inset ring-rose-300 dark:ring-rose-500/40";
    }
    if (INVALID_TYPE_CODES.has(code)) {
      return "bg-violet-50 dark:bg-violet-500/10 ring-1 ring-inset ring-violet-300 dark:ring-violet-500/40";
    }
    return "bg-amber-50 dark:bg-amber-500/10 ring-1 ring-inset ring-amber-300 dark:ring-amber-500/40";
  }

  // Bebidas con alcohol que el chequeo por tipo no ve. La leyenda es
  // OBLIGATORIA, así que se pregunta a pedido y se aplica solo con confirmación:
  // se escribe en la celda `legales` de esas filas, que es el dato que después
  // viaja al Excel y a la cenefa. El generador no la duplica -- chequea que no
  // esté ya presente (ver data_engine.py).
  const [buscandoAlcohol, setBuscandoAlcohol] = useState(false);

  async function buscarAlcoholConIA() {
    setBuscandoAlcohol(true);
    try {
      const { data } = await convertidorApi.detectarAlcoholIA(
        rows.map((r) => ({
          row_id: r.row_id, codigo: r.codigo,
          descripcion: r.descripcion, nombreArticulo: r.nombreArticulo,
        }))
      );
      if (data.errores.length) toast.error(data.errores[0]);
      if (data.alcohol.length === 0) {
        toast.success(t("convertidor.tinin.alcoholNinguna", { count: data.revisadas }));
        return;
      }
      const marcadas = new Set(data.alcohol.map((a) => a.row_id));
      setRows((prev) =>
        (prev ?? []).map((r) => {
          if (!marcadas.has(r.row_id) || r.legales.includes(data.leyenda)) return r;
          return { ...r, legales: `${r.legales} ${data.leyenda}`.trim() };
        })
      );
      toast.success(t("convertidor.tinin.alcoholAplicada", { count: data.alcohol.length }));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t("convertidor.unknownError"));
    } finally {
      setBuscandoAlcohol(false);
    }
  }

  // Todo lo que Tinín tiene para decir, en un solo lugar y en orden de
  // impacto: primero lo que impide generar (falta el dato), después lo que
  // conviene revisar (dos filas que parecen el mismo cartel), al final lo
  // opcional. Cada tema desaparece solo cuando se resuelve.
  const temasTinin = useMemo<TemaTinin[]>(() => {
    const out: TemaTinin[] = [];

    if (rowsParaIA.length > 0) {
      out.push({
        id: "sin-descripcion",
        titulo: t("convertidor.tinin.sinDescripcionTitulo", { count: rowsParaIA.length }),
        detalle: t("convertidor.tinin.sinDescripcionDetalle"),
        accion: {
          etiqueta: t("convertidor.ai.button"),
          onClick: () => setAiModalRows(rowsParaIA),
        },
        items: rowsParaIA.slice(0, 40).map((row) => ({
          clave: String(row.row_id),
          texto: `${row.codigo} · ${row.nombreArticulo || "—"}`,
          onIr: () => scrollToRow(row.row_id),
        })),
      });
    }

    if (visiblePairs.length > 0) {
      out.push({
        id: "pares",
        titulo: t("convertidor.tinin.paresTitulo", { count: visiblePairs.length }),
        detalle: t("convertidor.tinin.paresDetalle"),
        items: visiblePairs.map((pair) => ({
          clave: maPairKey(pair.sku1, pair.sku2),
          texto: `${pair.sku1} · ${pair.nombre1} / ${pair.sku2} · ${pair.nombre2}`,
          onRevisar: () => setMergePair(pair),
          onDescartar: () => dismissPair(pair),
        })),
      });
    }

    // OFERTADET que el motor no conoce: la mecánica se descarta en silencio,
    // así que hay que verlo. Ver resolver_mecanica en convertidor_variables.py.
    const detDesconocido = rows.filter((r) =>
      (r.warningsMecanica ?? []).includes("ofertadet_desconocido"));
    if (detDesconocido.length > 0) {
      out.push({
        id: "ofertadet",
        titulo: t("convertidor.tinin.ofertadetTitulo", { count: detDesconocido.length }),
        detalle: t("convertidor.tinin.ofertadetDetalle"),
        panel: (
          <TininMecanica
            rows={detDesconocido.map((r) => ({
              ofertaDet: r.ofertaDet, ofertaOrigen: r.ofertaOrigen,
            }))}
            onAprendido={() => onRevalidar?.()}
          />
        ),
        items: detDesconocido.slice(0, 40).map((row) => ({
          clave: String(row.row_id),
          texto: `${row.codigo} · ${row.ofertaDet || "—"}`,
          onIr: () => scrollToRow(row.row_id),
        })),
      });
    }

    if (rowsPrecioDeKilo.length > 0) {
      out.push({
        id: "cien-gramos",
        titulo: t("convertidor.tinin.cienGramosTitulo", { count: rowsPrecioDeKilo.length }),
        detalle: t("convertidor.tinin.cienGramosDetalle"),
        accion: {
          etiqueta: t("convertidor.tinin.cienGramosBoton"),
          onClick: () => pasarPreciosA100g(new Set(rowsPrecioDeKilo.map((r) => r.row_id))),
        },
        items: rowsPrecioDeKilo.slice(0, 40).map((row) => ({
          clave: String(row.row_id),
          texto: `${row.codigo} · ${row.descripcion || row.nombreArticulo || "—"} · `
               + `$${row.precioOferta}${row.decimalPrecioOferta} → `
               + `$${precioA100g(row.precioOferta, row.decimalPrecioOferta)}`,
          onIr: () => scrollToRow(row.row_id),
        })),
      });
    }

    out.push({
      id: "alcohol",
      titulo: t("convertidor.tinin.alcoholTitulo"),
      detalle: t("convertidor.tinin.alcoholDetalle"),
      accion: {
        etiqueta: buscandoAlcohol
          ? t("convertidor.tinin.alcoholBuscando")
          : t("convertidor.tinin.alcoholBoton"),
        onClick: buscarAlcoholConIA,
      },
    });

    // Un grupo que vino INCOMPLETO. Es el aviso que más importa de los dos: la
    // descripción guardada menciona un producto que hoy NO está en oferta, y un
    // cartel de góndola no puede anunciar algo que no se vende a ese precio.
    // Por eso no hay botón de "aplicar": hay que reescribirla.
    const parciales = grupos.filter((g) => !g.completo && !gruposDescartados.has(g.id));
    if (parciales.length > 0) {
      out.push({
        id: "grupos-parciales",
        titulo: t("convertidor.grupos.parcialesTitulo", { count: parciales.length }),
        detalle: t("convertidor.grupos.parcialesDetalle"),
        items: parciales.map((g) => ({
          clave: g.id,
          texto: `${g.nombre} — ${t("convertidor.grupos.faltan", {
            faltan: g.faltantes.join(", "),
            hay: g.presentes.join(", "),
          })}`,
          onIr: () => {
            const fila = rows.find((r) => g.presentes.includes(r.codigo));
            if (fila) scrollToRow(fila.row_id);
          },
          onDescartar: () => setGruposDescartados((prev) => new Set(prev).add(g.id)),
        })),
      });
    }

    // Un grupo que vino ENTERO: ya se escribió una vez, se puede reusar tal cual.
    const completos = grupos.filter(
      (g) => g.completo && !gruposDescartados.has(g.id)
             && g.presentes.every((sku) => rows.some((r) => r.codigo === sku)));
    if (completos.length > 0) {
      out.push({
        id: "grupos-completos",
        titulo: t("convertidor.grupos.completosTitulo", { count: completos.length }),
        detalle: t("convertidor.grupos.completosDetalle"),
        items: completos.map((g) => ({
          clave: g.id,
          texto: `${g.presentes.join(" · ")} — ${g.descripcion}`,
          onRevisar: () => { void aplicarGrupo(g); },
          revisarEtiqueta: t("convertidor.grupos.aplicar"),
          onDescartar: () => setGruposDescartados((prev) => new Set(prev).add(g.id)),
        })),
      });
    }

    out.push({
      id: "unificar",
      titulo: t("convertidor.tinin.unificarTitulo"),
      detalle: t("convertidor.tinin.unificarDetalle"),
      accion: {
        etiqueta: t("convertidor.unificar.button"),
        onClick: () => setUnifyModalRows(rows),
      },
    });

    return out;
  }, [rows, rowsParaIA, visiblePairs, rowsPrecioDeKilo, grupos, gruposDescartados,
      buscandoAlcohol, onRevalidar, t]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <a ref={dlRef} className="hidden" />

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <button onClick={onReset} className="btn-ghost flex items-center gap-1.5 text-sm">
            <ArrowLeft size={14} /> {t("convertidor.changeFile")}
          </button>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600 dark:text-slate-300">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
            {t("convertidor.legendMissing")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-violet-400" />
            {t("convertidor.legendInvalidType")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            {t("convertidor.legendWarning")}
          </span>
          <span className="badge badge-blue">
            {t("convertidor.matchedSummary", { matched: matchedCount, total: rows.length })}
          </span>
        </div>
      </div>

      <TininRevision temas={temasTinin} />

      <div className="h-9 flex items-center gap-2 px-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs">
        {activeCellColumn ? (
          <>
            <span className="font-semibold text-slate-500 dark:text-slate-400 shrink-0">
              {activeCellColumn.label}:
            </span>
            <span className="truncate text-slate-800 dark:text-slate-100">{activeCellValue || "—"}</span>
          </>
        ) : (
          <span className="text-slate-300 dark:text-slate-600">{t("convertidor.cellBarPlaceholder")}</span>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <div
          ref={scrollContainerRef}
          className="overflow-auto"
          style={{ height: CONTAINER_HEIGHT }}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        >
          <table className="min-w-full border-collapse text-xs table-fixed">
            <colgroup>
              {columnasVisibles.map((c) => (
                <col key={c.key} style={{ width: anchoDeColumna(c) }} />
              ))}
            </colgroup>
            <thead className="sticky top-0 z-10 bg-slate-100 dark:bg-slate-800">
              <tr>
                {columnasVisibles.map((c) => (
                  <th
                    key={c.key}
                    title={c.label}
                    className="text-left px-2 py-2 font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wide text-[10px] border-b border-slate-200 dark:border-slate-700 truncate"
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topSpacer > 0 && (
                <tr style={{ height: topSpacer }}>
                  <td colSpan={columnasVisibles.length} />
                </tr>
              )}
              {visibleRows.map((row) => (
                <tr key={row.row_id} style={{ height: ROW_HEIGHT }} className="border-b border-slate-100 dark:border-slate-800">
                  {columnasVisibles.map((c) => (
                    <td
                      key={c.key}
                      className={clsx("px-2 py-1 align-middle", warningClass(row, c.warningCodes))}
                      title={warningMotivo(row, c)}
                      onMouseEnter={() => setHoveredCell({ rowId: row.row_id, key: c.key })}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      {c.editable === "descripcion" ? (
                        <div className="flex items-center gap-1">
                          <input
                            ref={(el) => {
                              if (el) descripcionInputRefs.current.set(row.row_id, el);
                              else descripcionInputRefs.current.delete(row.row_id);
                            }}
                            type="text"
                            value={row.descripcion}
                            onChange={(e: ChangeEvent<HTMLInputElement>) =>
                              handleDescripcionChange(row.row_id, row.codigo, e.target.value)
                            }
                            onKeyDown={(e) => handleDescripcionKeyDown(e, row.row_id, row.codigo)}
                            onFocus={() => setFocusedCell({ rowId: row.row_id, key: c.key })}
                            onBlur={() => setFocusedCell(null)}
                            className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-xs py-1 px-1 outline-none transition-colors"
                            placeholder={t("convertidor.descripcionPlaceholder")}
                          />
                          {savingRowId === row.row_id && (
                            <Loader2 size={11} className="shrink-0 animate-spin text-slate-400" />
                          )}
                        </div>
                      ) : c.editable === "simple" ? (
                        <input
                          type="text"
                          value={String(row[c.key] ?? "")}
                          onChange={(e: ChangeEvent<HTMLInputElement>) =>
                            handleSimpleFieldChange(row.row_id, c.key, e.target.value)
                          }
                          onFocus={() => setFocusedCell({ rowId: row.row_id, key: c.key })}
                          onBlur={() => setFocusedCell(null)}
                          className="w-full rounded border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 bg-transparent text-xs py-1 px-1 outline-none transition-colors"
                        />
                      ) : (
                        <span className="block truncate text-slate-700 dark:text-slate-300" title={String(row[c.key] ?? "")}>
                          {row[c.key] === null || row[c.key] === undefined || row[c.key] === "" ? "—" : String(row[c.key])}
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
              {bottomSpacer > 0 && (
                <tr style={{ height: bottomSpacer }}>
                  <td colSpan={columnasVisibles.length} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleConvertirACenefa}
          disabled={enviandoACenefa || exporting}
          className="btn-primary flex items-center gap-2 disabled:opacity-50"
        >
          {enviandoACenefa ? <Loader2 size={16} className="animate-spin" /> : <Presentation size={16} />}
          {t("convertidor.convertirACenefa")}
        </button>
        <button
          onClick={handleExport}
          disabled={exporting || enviandoACenefa}
          className="btn-secondary flex items-center gap-2 disabled:opacity-50"
        >
          {exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          {exporting ? t("convertidor.exporting") : t("convertidor.download")}
        </button>
      </div>

      {aiModalRows && (
        <ConvertidorAiModal
          rows={aiModalRows}
          onApprove={commitDescripcion}
          onClose={() => setAiModalRows(null)}
        />
      )}

      {unifyModalRows && (
        <ConvertidorUnifyModal
          rows={unifyModalRows}
          onApprove={commitUnificacion}
          onClose={() => setUnifyModalRows(null)}
        />
      )}

      {mergePair && (() => {
        const rowA = rows.find((r) => r.codigo === mergePair.sku1);
        const rowB = rows.find((r) => r.codigo === mergePair.sku2);
        if (!rowA || !rowB) return null;
        return (
          <ConvertidorMergeModal
            pair={mergePair}
            rowA={rowA}
            rowB={rowB}
            onConfirm={(descripcion) => commitMerge(mergePair, descripcion)}
            onClose={() => setMergePair(null)}
          />
        );
      })()}
    </div>
  );
}
