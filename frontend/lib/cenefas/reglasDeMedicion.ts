/**
 * Las reglas de medición de las cenefas, traídas del ÚNICO lugar donde viven.
 *
 * Una cenefa se dibuja dos veces: el servidor arma el PPTX (Python) y esto
 * dibuja el preview (TypeScript). Cada regla de medición estaba escrita a mano
 * en los dos lados, y cada vez que alguien tocaba una y se olvidaba de la otra,
 * la pantalla dejaba de mostrar lo que salía impreso sin que nadie se enterara.
 * Pasó tres veces: la voladita, Arial Black medida como Arial, y el margen
 * interno --que de este lado ni siquiera existía, así que no había dos números
 * que comparar--.
 *
 * Pedido de Ivan (18/09/2026): "el archivo de reglas tiene que ser uno solo,
 * sino nos va a pasar de poner una regla en algún lado y luego olvidarnos de
 * cambiarla en el otro y eso es una mierda".
 *
 * Ese archivo es `backend/app/data/reglas_de_medicion.json`, y ahí está también
 * el porqué de cada número. Acá NO hay ni un valor escrito: los dos despliegues
 * están rooteados cada uno en su carpeta (el build de Vercel arranca en
 * `frontend/`, el de Docker en `backend/`), así que este lado no puede importar
 * ese archivo -- lo pide por HTTP.
 *
 * Y NO HAY VALORES POR DEFECTO, a propósito. Un default acá es la duplicación
 * entrando por la ventana: dibujaríamos con un número inventado que nadie
 * comparó nunca con lo que imprime PowerPoint, que es exactamente el bug que
 * esto viene a matar. Si las reglas no llegaron, no se dibuja.
 */
import { cenefasV2Api } from "@/lib/api";

export interface Reglas {
  /** Cuánto achica PowerPoint un pedazo volado (el "$", los centavos). */
  factorVoladita: number;
  /** Cuánto ocupa de alto un renglón, en múltiplos del tamaño de la letra. */
  altoDeLinea: number;
  /** Margen interno de la caja de texto, en cm, sumando los dos lados. */
  insetCm: number;
  /** Tamaño de letra que se asume cuando el cuadro no declara ninguno. */
  ptPorDefecto: number;
}

/** Cómo se llama cada regla en el JSON del backend. */
const CLAVES: Record<keyof Reglas, string> = {
  factorVoladita: "factor_voladita",
  altoDeLinea: "alto_de_linea",
  insetCm: "inset_cm",
  ptPorDefecto: "pt_por_defecto",
};

let _reglas: Reglas | null = null;
let _promesa: Promise<Reglas> | null = null;

/**
 * Trae las reglas del backend. Una sola vez por sesión: la promesa queda
 * cacheada a nivel de módulo, así tres cuadros pidiéndolas a la vez no hacen
 * tres requests.
 */
export function cargarReglasDeMedicion(): Promise<Reglas> {
  if (_promesa) return _promesa;
  _promesa = cenefasV2Api.getReglasDeMedicion().then(({ data }) => {
    const salida = {} as Reglas;
    for (const [campo, clave] of Object.entries(CLAVES) as [keyof Reglas, string][]) {
      const valor = data?.[clave]?.valor;
      if (typeof valor !== "number" || !Number.isFinite(valor)) {
        // Nombrar la clave que falta y no caer a un default: si el preview
        // dibujara con un número propio, volvería a mentir en silencio.
        throw new Error(
          `la regla de medición "${clave}" no llegó del backend (llegó ${JSON.stringify(valor)}). ` +
          `Se define en backend/app/data/reglas_de_medicion.json y la sirve ` +
          `GET /tools/cenefas/v2/reglas-de-medicion. No la escribas acá.`,
        );
      }
      salida[campo] = valor;
    }
    _reglas = salida;
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
 * Las reglas ya cargadas. TIRA si todavía no llegaron: quien dibuja tiene que
 * haber esperado a `cargarReglasDeMedicion()` primero (lo hace Canvas.tsx, que
 * es la única puerta por la que se dibuja una cenefa).
 */
export function reglas(): Reglas {
  if (!_reglas) {
    throw new Error(
      "se quiso medir una cenefa antes de que llegaran las reglas de medición. " +
      "Esperá a cargarReglasDeMedicion() antes de dibujar.",
    );
  }
  return _reglas;
}

/** Solo para los tests: olvida lo cargado. */
export function _olvidarReglas(): void {
  _reglas = null;
  _promesa = null;
}
