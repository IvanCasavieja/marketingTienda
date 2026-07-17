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
  Ejemplos reales ya en el catálogo: "Aceite alto oleico CAÑUELAS. 900 ml", "Yogur natural YOGURISIMO Original. 460g".
- El resto del texto en formato oración normal (minúsculas salvo inicio de oración o nombres propios).
- Incluí cantidad/tamaño si se puede inferir de la fuente (ml, g, kg, L, unidades, etc.).
- Es para un cartel de precio: tiene que ser CORTA. Apuntá a menos de {DESCRIPTION_WARN_CHARS} caracteres, nunca más de {DESCRIPTION_MAX_CHARS}.
- No inventes datos (sabor, variedad, tamaño) que no estén sugeridos por el nombre o la descripción de origen."""

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
    """items: [{"row_id", "codigo", "nombre_articulo", "descripcion_web"}, ...] — ya
    filtrados por el caller a los que realmente necesitan sugerencia (sin descripción).

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
