"""IA aplicada al Convertidor de Excel: genera sugerencias de descripción
para filas que, después del match con el catálogo y de la columna
"Descripción" del propio Excel (ver convertidor.py), siguen sin
descripción. Nunca escribe en sku_descripciones por su cuenta — solo
produce sugerencias; la persistencia se hace vía el mismo PATCH que ya usa
la edición manual, en cenefas_convertidor.py."""
import json
import logging
import re

from app.services.ai_usage_service import log_ai_usage
from app.services.cenefas.validation_engine import DESCRIPTION_MAX_CHARS, DESCRIPTION_WARN_CHARS
from app.services.debate_service import _ASK_CLAUDE_META, _ask_claude
from app.services.tino_personas import TININ_BASE

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reglas de estilo — ÚNICO bloque a tocar cuando cambien los lineamientos.
# ---------------------------------------------------------------------------
_STYLE_RULES = f"""\
- La marca del producto va SIEMPRE en MAYÚSCULA COMPLETA, la palabra entera (no solo la primera letra).
- Justo después de la marca (y de alguna palabra corta de variante/sabor que la siga inmediatamente, si la hay) va SIEMPRE un punto, separando la marca de lo que venga después (cantidad/tamaño u otra info) como si fuera el inicio de una nueva oración corta — incluso si la marca no está al final del todo del texto.
  Ejemplos reales ya en el catálogo: "Aceite alto oleico CAÑUELAS. 900 ml", "Yogur natural YOGURISIMO original. 460g".
  Si la marca queda al final de la descripción y no hay nada más después, NO pongas un punto colgado ahí — el punto separa dos partes, no es un cierre de oración.
- El resto del texto va en minúscula, con reglas normales de oración en español: mayúscula SOLO en la primera letra de toda la descripción y en la primera letra de la palabra que sigue a cada punto (incluido el punto después de la marca) — ninguna otra palabra lleva mayúscula inicial (ej. "sin piel", "con azúcar", "de cerdo", nunca "Sin Piel" ni "Con Azúcar"). Dos excepciones que no cambian nunca, sea cual sea su posición en el texto: la marca (siempre mayúscula completa, ver arriba) y las unidades de medida (ml, g, kg, L, un, etc.), siempre en minúscula incluso si quedaran al principio de una oración.
- Incluí cantidad/tamaño si se puede inferir de la fuente (ml, g, kg, L, unidades, etc.).
- Es para un cartel de precio: tiene que ser CORTA. Apuntá a menos de {DESCRIPTION_WARN_CHARS} caracteres, nunca más de {DESCRIPTION_MAX_CHARS}.
- No inventes datos (sabor, variedad, tamaño) que no estén sugeridos por el nombre o la descripción de origen.
- Si un producto viene marcado "[FIAMBRE POR KG]", la unidad en la descripción tiene que decir "100g", nunca "kg" — el precio de ese producto ya se va a recalcular aparte para esa unidad, así que el texto tiene que ser consistente con eso."""

_SYSTEM_PROMPT = f"""{TININ_BASE}

Te paso productos con su nombre crudo del sistema de gestión y/o una descripción web, y para \
cada uno tenés que devolver una descripción corta y prolija para el cartel, siguiendo estas \
reglas de estilo:

{_STYLE_RULES}"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_CHUNK_SIZE = 20               # productos por llamada a Claude — lotes chicos porque cada
                                # item devuelve texto libre completo, no solo un índice, así
                                # que hay más superficie de error por chunk que en un batch
                                # de "elegí cuáles mantener" (ver don_tino_precios.py).
_ROWS_MAX_PER_REQUEST = 80      # tope duro por request síncrona — por encima, se trunca y se
                                # avisa "truncated" en la respuesta en vez de encadenar
                                # decenas de chunks y arriesgar timeout del navegador/proxy.


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _strip_json_fence(text: str) -> str:
    """Los modelos a veces envuelven el JSON en ```json ... ``` a pesar de que se
    les pide texto plano — se le hace strip antes de json.loads en vez de fallar."""
    return _JSON_FENCE_RE.sub("", text).strip()


def _build_prompt(items: list[dict]) -> str:
    lineas = []
    for n, it in enumerate(items, start=1):
        partes = []
        if it.get("es_fiambre_kg"):
            partes.append("[FIAMBRE POR KG]")
        if it["nombre_articulo"]:
            partes.append(f'nombre ERP: "{it["nombre_articulo"]}"')
        if it["descripcion_web"]:
            partes.append(f'descripción web: "{it["descripcion_web"]}"')
        lineas.append(f"{n}. " + " | ".join(partes))
    listado = "\n".join(lineas)
    return (
        f"Generá una descripción de cartel para cada uno de estos {len(items)} productos:\n\n"
        f"{listado}\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"descripciones": {"1": "texto...", "2": "texto...", ...}} '
        "— una entrada por cada número de la lista, en el mismo orden. Sin comentarios ni texto fuera del JSON."
    )


async def generar_descripciones(items: list[dict], db, user_id: int) -> dict:
    """items: [{"row_id", "codigo", "nombre_articulo", "descripcion_web",
    "es_fiambre_kg"}, ...] — ya filtrados por el caller (filas sin descripción,
    o fiambres todavía en kg que necesitan pasar a 100g). "es_fiambre_kg" es
    opcional, solo cambia la redacción de la unidad (ver _STYLE_RULES) — el
    precio÷10 correspondiente lo calcula el frontend, no esta función.

    Devuelve {"suggestions": [...], "failed_row_ids": [...]}. Nunca levanta por un chunk
    que falla — ese chunk se reporta en failed_row_ids y el resto de la respuesta sigue
    siendo utilizable (fail-soft, mismo criterio que _afinar_seleccion en
    don_tino_precios.py): un fallo transitorio de red en un chunk no debería tirar abajo
    las sugerencias que ya se generaron en los demás."""
    # Sin nombre_articulo NI descripcion_web no hay nada que pedirle a Claude —
    # se descarta antes de gastar un slot del batch.
    procesables = [it for it in items if it["nombre_articulo"] or it["descripcion_web"]]
    procesables_ids = {it["row_id"] for it in procesables}
    failed_row_ids: list[int] = [it["row_id"] for it in items if it["row_id"] not in procesables_ids]

    suggestions: list[dict] = []

    for chunk in _chunks(procesables, _CHUNK_SIZE):
        prompt = _build_prompt(chunk)
        try:
            content, in_tok, out_tok = await _ask_claude(_SYSTEM_PROMPT, prompt, max_tokens=1200)
            await log_ai_usage(db, user_id, "convertidor_descripciones", *_ASK_CLAUDE_META, in_tok, out_tok)
            parsed = json.loads(_strip_json_fence(content))
            descripciones = parsed.get("descripciones", {})
            for n, it in enumerate(chunk, start=1):
                texto = descripciones.get(str(n))
                if isinstance(texto, str) and texto.strip():
                    texto = texto.strip()
                    suggestions.append({
                        "row_id": it["row_id"],
                        "codigo": it["codigo"],
                        "descripcion": texto,
                        "too_long": len(texto) > DESCRIPTION_WARN_CHARS,
                    })
                else:
                    failed_row_ids.append(it["row_id"])
        except Exception as exc:
            log.warning("convertidor_ai.generar_descripciones: chunk de %d falló — %s", len(chunk), exc)
            failed_row_ids.extend(it["row_id"] for it in chunk)

    return {"suggestions": suggestions, "failed_row_ids": failed_row_ids}


# ---------------------------------------------------------------------------
# Detección de columnas de fecha_inicio/fecha_fin sin alias reconocido
# ---------------------------------------------------------------------------
#
# Ninguna de las dos es obligatoria en el Excel de gestión, y el nombre real
# de la columna varía entre exports (ver _INPUT_ALIASES en convertidor.py).
# Cuando el matching por nombre de columna no alcanza, esto le pasa a Tinín
# el encabezado + un par de valores de muestra YA confirmados como fechas
# reales (ver convertidor.py: solo llega acá una columna si sus valores
# parsean como fecha) para que decida cuál es inicio y cuál es fin de la
# vigencia — nunca al revés (nunca se le manda una columna a ciegas para que
# decida SI es una fecha, eso ya se filtró antes de llegar acá).

_VALID_DATE_FIELDS = {"fecha_inicio", "fecha_fin"}

_HEADER_SYSTEM_PROMPT = f"""{TININ_BASE}

Hoy también te toca: te paso encabezados de columna de un Excel de gestión que el sistema no \
reconoció automáticamente por nombre, junto con valores de ejemplo de esa misma columna (ya \
confirmados como fechas válidas). Tu tarea es decidir, para cada uno, si es la columna de FECHA \
DE INICIO o FECHA DE FIN de la vigencia de un precio/oferta (el período en que ese precio es \
válido) — o si no tiene nada que ver con eso (por ejemplo fecha de alta, de modificación, de \
nacimiento, etc.).

Sé conservador: ante la duda, respondé null. Es mejor dejar una columna sin reconocer que \
etiquetarla mal — alguien va a completarla a mano si hace falta."""


def _build_header_prompt(candidates: list[dict]) -> str:
    lineas = []
    for n, c in enumerate(candidates, start=1):
        muestras = ", ".join(f'"{m}"' for m in c["muestras"])
        lineas.append(f'{n}. Encabezado: "{c["header_display"]}" — valores de ejemplo: {muestras}')
    listado = "\n".join(lineas)
    return (
        f"Clasificá estos {len(candidates)} encabezados de columna:\n\n{listado}\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: '
        '{"clasificaciones": {"1": "fecha_inicio"|"fecha_fin"|null, ...}} '
        "— una entrada por cada número de la lista, en el mismo orden. Sin comentarios ni texto fuera del JSON."
    )


async def resolve_date_columns_with_ai(candidates: list[dict], db, user_id: int) -> dict[str, str | None]:
    """candidates: [{"header_norm", "header_display", "muestras": [str, ...]}, ...] —
    encabezados sin match en _INPUT_ALIASES ni en el cache aprendido
    (ConvertidorHeaderAlias), ya filtrados para que "muestras" tenga al menos
    un par de valores que parsean como fecha real (ver convertidor.py).

    Devuelve {header_norm: "fecha_inicio"|"fecha_fin"|None} con UNA entrada
    por cada candidato pasado -- None significa que Claude confirmó que esa
    columna no es de vigencia (ej. fecha de alta/modificación), y el caller
    lo cachea igual que un match positivo para no volver a preguntar por ese
    mismo header en el futuro (ver convertidor.py). Si la llamada entera
    falla (red, JSON con forma inesperada, etc.) devuelve {} -- ningún
    candidato se cachea, así que se reintenta en el próximo import en vez de
    quedar mal clasificado a partir de una respuesta que no se pudo leer.

    Nunca levanta: todo el trabajo con la respuesta de Claude (incluido el
    JSON parseado) vive dentro del try -- una forma inesperada en
    "clasificaciones" (None, una lista, lo que sea distinto de un dict) se
    trata igual que cualquier otro fallo, no como un crash aparte."""
    if not candidates:
        return {}
    try:
        prompt = _build_header_prompt(candidates)
        content, in_tok, out_tok = await _ask_claude(_HEADER_SYSTEM_PROMPT, prompt, max_tokens=400)
        await log_ai_usage(db, user_id, "convertidor_columnas_fecha", *_ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content))
        clasificaciones = parsed.get("clasificaciones", {})
        if not isinstance(clasificaciones, dict):
            # Forma inesperada (None, una lista, ...) -- no es lo mismo que
            # "Claude no marcó ninguna columna": es una respuesta que no se
            # pudo leer. Se trata como fallo total (except de abajo, sin
            # cachear nada) en vez de asumir "todas None" y cachear eso como
            # si fuera un negativo confirmado.
            raise ValueError(f"'clasificaciones' no es un dict: {clasificaciones!r}")

        result: dict[str, str | None] = {}
        for n, c in enumerate(candidates, start=1):
            field = clasificaciones.get(str(n))
            result[c["header_norm"]] = field if field in _VALID_DATE_FIELDS else None
        return result
    except Exception as exc:
        log.warning("convertidor_ai.resolve_date_columns_with_ai: fallo — %s", exc)
        return {}
