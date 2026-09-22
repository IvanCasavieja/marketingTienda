/**
 * EL TAMAÑO DE HOJA, traído del ÚNICO lugar donde vive.
 *
 * -------------------------------------------------------------------------
 * Qué estaba roto
 * -------------------------------------------------------------------------
 *
 * Ivan exportó una 3xA4 SOLO X 25 y el texto salió impreso fuera de la hoja,
 * mientras el preview se lo mostraba adentro. No era un error de medición: el
 * preview **agrandaba el papel hasta que entrara el contenido**. La línea era
 * un `Math.max(ancho_de_la_hoja, ...borde_derecho_de_cada_cuadro)` en
 * Canvas.tsx, así que un cuadro que se salía no se veía saliéndose: hacía
 * crecer la hoja dibujada. El editor le mostraba "A4 24.588×29.7 cm" — 24,588
 * es exactamente el borde derecho del cuadro que se iba 3,6 cm afuera.
 *
 * Y abajo de eso había un problema más viejo: el tamaño de hoja estaba escrito
 * a mano en CINCO tablas (`Canvas.FORMAT_DIMS`, `layout_engine.FORMATS`,
 * `component_renderer.FORMAT_SLIDES`, `pptx_importer._FORMATS_DIM` y las
 * etiquetas del panel de importación) y tres de los seis formatos tenían
 * números DISTINTOS según a cuál se le preguntara. No era descuido: unas
 * decían el PAPEL que sale de la impresora y otras la CELDA que ocupa una
 * cenefa adentro de ese papel, y las dos cosas se llamaban igual ("3xa4"). El
 * preview copiaba la semántica de celda, así que el de un "3xa4" dibujaba una
 * franja de 21×9,9 cm mientras la impresora sacaba una A4 entera.
 *
 * Y la orientación también estaba mal, que es la parte que explica el resto:
 * la 6xA4 es una A4 HORIZONTAL y la A5 son DOS cenefas una al lado de la otra
 * (Ivan, 22/09/2026, "si te imaginás que la 6xA4 está en vertical, nunca van a
 * salir bien"). Con la tabla vieja, una A4 apaisada de 29,7×21 se detectaba
 * como "a5" — la mitad — al importar.
 *
 * -------------------------------------------------------------------------
 * Qué hace este archivo
 * -------------------------------------------------------------------------
 *
 * Trae la tabla del backend (`GET /tools/cenefas/v2/formatos-de-hoja`, que
 * devuelve `backend/app/data/formatos_de_hoja.json` tal cual) y expone UNA
 * función para la pregunta que importa: `papelDeLaPlantilla()`.
 *
 * Esa función es la única puerta, y es el espejo exacto de
 * `formatos_de_hoja.hoja_de_definicion()` del backend:
 *
 *   1. si la plantilla trae `hoja`, ése es el papel — la medida del PPTX
 *      original (`prs.slide_width/height`), o sea sobre lo que PowerPoint va a
 *      imprimir de verdad, porque el render reusa ese mismo archivo;
 *   2. si no, el papel del formato declarado, y se dice que salió de ahí.
 *
 * NUNCA se deriva del contenido. Ése era el bug entero.
 *
 * Igual que `reglasDeMedicion.ts`: acá NO hay ni un número escrito y NO hay
 * valores por defecto. Los dos despliegues están rooteados cada uno en su
 * carpeta (Vercel en `frontend/`, Docker en `backend/`), así que este lado no
 * puede importar el JSON — lo pide. Y un default acá sería la duplicación
 * entrando por la ventana: dibujaríamos una hoja que nadie comparó nunca con
 * la que sale de la impresora.
 */
import { cenefasV2Api } from "@/lib/api";

export interface FormatoDeHoja {
  label: string;
  /** El papel que sale de la impresora, en cm. */
  papel: { ancho: number; alto: number };
  /** Lo que ocupa UNA cenefa adentro de ese papel, en cm. */
  celda: { ancho: number; alto: number };
  slots: number;
  slotCols: number;
  slotRows: number;
  scale: number;
}

/** El papel de una plantilla, y de dónde salió el número. */
export interface Papel {
  anchoCm: number;
  altoCm: number;
  /**
   * `"pptx"` = medido del archivo original: es la hoja de verdad.
   * `"formato"` = la plantilla no trae medida (se armó a mano en el editor, o
   * se importó antes del 22/09/2026 y todavía no se abrió una vez), así que es
   * el papel del formato declarado. Se distingue para que la pantalla pueda
   * decirlo y nadie confunda medido con supuesto.
   */
  origen: "pptx" | "formato";
}

/** Lo mínimo que este módulo necesita de una plantilla. */
interface ConHoja {
  master_format?: string;
  hoja?: { ancho_cm?: number | null; alto_cm?: number | null; origen?: string | null } | null;
}

let _tabla: Record<string, FormatoDeHoja> | null = null;
let _toleranciaDesborde: number | null = null;
let _ruidoEmu: number | null = null;
let _promesa: Promise<Record<string, FormatoDeHoja>> | null = null;

/**
 * Trae la tabla del backend. Una sola vez por sesión, igual que las reglas de
 * medición: la promesa queda cacheada a nivel de módulo.
 */
export function cargarFormatosDeHoja(): Promise<Record<string, FormatoDeHoja>> {
  if (_promesa) return _promesa;
  _promesa = cenefasV2Api.getFormatosDeHoja().then(({ data }) => {
    const salida: Record<string, FormatoDeHoja> = {};
    for (const [id, f] of Object.entries(data?.formatos ?? {})) {
      salida[id] = {
        label: f.label,
        papel: { ancho: f.papel_cm.ancho, alto: f.papel_cm.alto },
        celda: { ancho: f.celda_cm.ancho, alto: f.celda_cm.alto },
        slots: f.slots,
        slotCols: f.slot_cols ?? 1,
        slotRows: f.slot_rows ?? 1,
        scale: f.scale,
      };
    }
    if (!Object.keys(salida).length) {
      throw new Error(
        "la tabla de formatos de hoja llegó vacía del backend. Vive en " +
        "backend/app/data/formatos_de_hoja.json y la sirve " +
        "GET /tools/cenefas/v2/formatos-de-hoja. No la escribas acá.",
      );
    }
    _tabla = salida;
    _toleranciaDesborde = data?.tolerancia_desborde_cm?.valor ?? null;
    _ruidoEmu = data?.ruido_emu_cm?.valor ?? null;
    return salida;
  }).catch((err) => {
    // Sin esto, un fallo de red dejaría la promesa cacheada para siempre y el
    // preview no se recuperaría ni recargando el paso.
    _promesa = null;
    throw err;
  });
  return _promesa;
}

/**
 * La tabla ya cargada. TIRA si todavía no llegó, igual que `reglas()`: quien
 * dibuja tiene que haber esperado a `cargarFormatosDeHoja()` primero (lo hace
 * Canvas.tsx, que es la única puerta por la que se dibuja una cenefa).
 */
function tabla(): Record<string, FormatoDeHoja> {
  if (!_tabla) {
    throw new Error(
      "se quiso dibujar una cenefa antes de que llegara la tabla de formatos " +
      "de hoja. Esperá a cargarFormatosDeHoja() antes de dibujar.",
    );
  }
  return _tabla;
}

/** El formato, o el de a4 si el id no está (una etiqueta vieja de la base). */
function formato(id?: string | null): FormatoDeHoja {
  const t = tabla();
  return t[id ?? ""] ?? t.a4;
}

/** El papel que sale de la impresora para ese formato, en cm. */
export function papelDelFormato(id?: string | null): { ancho: number; alto: number } {
  return formato(id).papel;
}

/** Lo que ocupa UNA cenefa adentro de la hoja, en cm. */
export function celdaDelFormato(id?: string | null): { ancho: number; alto: number } {
  return formato(id).celda;
}

/** La etiqueta de un formato, como se le muestra a la persona ("3xA4"). */
export function etiquetaDelFormato(id?: string | null): string {
  return formato(id).label;
}

/** Los ids de formato que la tabla trae, en el orden del archivo. */
export function formatosConocidos(): string[] {
  return Object.keys(tabla());
}

/**
 * Si la tabla conoce ese formato. `formato()` cae a a4 cuando no, para que una
 * etiqueta vieja de la base no tumbe el dibujo; pero la PANTALLA tiene que
 * decir que cayó ahí, no mostrar "XYZ 21×29,7 · según el formato" como si el
 * formato XYZ midiera eso.
 */
export function formatoConocido(id?: string | null): boolean {
  return id != null && id in tabla();
}

/**
 * EL PAPEL DE UNA PLANTILLA. Espejo de `hoja_de_definicion()` en
 * backend/app/services/cenefas/formatos_de_hoja.py.
 *
 * `formatoActivo` es el formato que se está mirando: cuando no es el mismo que
 * el master, el diseño se está viendo escalado a OTRA hoja, así que la medida
 * del PPTX original ya no aplica y manda el papel del formato destino.
 */
export function papelDeLaPlantilla(
  plantilla: ConHoja | null | undefined,
  formatoActivo?: string | null,
): Papel {
  const master = plantilla?.master_format;
  const mirandoElMaster = !formatoActivo || formatoActivo === master;
  const hoja = plantilla?.hoja;
  if (mirandoElMaster && hoja && (hoja.ancho_cm ?? 0) > 0 && (hoja.alto_cm ?? 0) > 0) {
    return {
      anchoCm: hoja.ancho_cm as number,
      altoCm: hoja.alto_cm as number,
      // Espejo del backend (`hoja.get("origen") or "pptx"`): si alguien guardó
      // una hoja diciendo que salió del formato, acá no se la hace pasar por
      // medida.
      origen: hoja.origen === "formato" ? "formato" : "pptx",
    };
  }
  const papel = papelDelFormato(formatoActivo ?? master);
  return { anchoCm: papel.ancho, altoCm: papel.alto, origen: "formato" };
}

/**
 * Cuánto se tiene que salir algo del papel para que valga la pena marcarlo, en
 * cm. Es el mismo número con el que el backend decide avisar
 * (`tolerancia_desborde_cm`), para que lo que se ve marcado en pantalla y lo
 * que aparece en la lista de avisos sean la misma cosa.
 */
export function toleranciaDesbordeCm(): number {
  if (_toleranciaDesborde === null) {
    throw new Error(
      "la tolerancia de desborde no llegó del backend. Vive en " +
      "backend/app/data/formatos_de_hoja.json. No la escribas acá.",
    );
  }
  return _toleranciaDesborde;
}

/**
 * Por debajo de cuántos cm dos medidas son la misma medida. PowerPoint guarda
 * EMU enteros y 21 cm da 20,999: una imagen de fondo que "se pasa" 0,001 cm
 * del papel no se pasa de nada. El número es el mismo con el que el backend
 * compara hojas (`ruido_emu_cm`), para no tener dos ideas de "igual".
 */
export function ruidoEmuCm(): number {
  if (_ruidoEmu === null) {
    throw new Error(
      "el ruido de EMU no llegó del backend. Vive en " +
      "backend/app/data/formatos_de_hoja.json. No lo escribas acá.",
    );
  }
  return _ruidoEmu;
}

/** Solo para los tests: olvida lo cargado. */
export function _olvidarFormatosDeHoja(): void {
  _tabla = null;
  _toleranciaDesborde = null;
  _ruidoEmu = null;
  _promesa = null;
}
