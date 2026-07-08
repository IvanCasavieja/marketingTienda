"""
don_tino_precios.py — IA aplicada a los resultados del buscador de precios en vivo,
presentada bajo la persona de Don Tino.

Por detrás usa Claude y ChatGPT (mismos helpers _ask_claude/_ask_gpt de
debate_service.py que ya usa La Triada) pero el usuario nunca ve "Claude" ni
"ChatGPT" — todo se devuelve en primera persona como Don Tino. No se reusan
CLAUDE_PERSONA/GPT_PERSONA de debate_service.py: esas están armadas para un
debate adversarial de métricas de campañas, tono equivocado para esto.

100% stateless — no persiste nada, no dispara scraping. Opera sobre los
resultados que ya trajo la búsqueda en vivo de ese momento.
"""
import json
import logging
import re

from app.services.debate_service import _ask_claude, _ask_gpt

log = logging.getLogger(__name__)

DON_TINO_BASE = (
    "Sos Don Tino, el asistente de MKTG Platform para Tienda Inglesa. Hablás en "
    "primera persona, en español rioplatense, directo y útil. Nunca mencionás que "
    "sos un modelo de lenguaje ni cuál — para quien te lee, siempre sos vos, Don Tino, "
    "respondiendo directamente."
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_json_fence(text: str) -> str:
    """Los modelos a veces envuelven el JSON en ```json ... ``` a pesar de que se
    les pide texto plano — se le hace strip antes de json.loads en vez de fallar."""
    return _JSON_FENCE_RE.sub("", text).strip()


def _formatear_items_numerados(items: list[dict]) -> str:
    lineas = []
    for i, it in enumerate(items, start=1):
        moneda = it.get("moneda") or "UYU"
        simbolo = "U$S" if moneda == "USD" else "$"
        precio = it.get("precio")
        precio_txt = f"{simbolo} {precio:.2f} ({moneda})" if precio is not None else "sin precio"
        lineas.append(f"{i}. [{it['tienda']}] {it['nombre']} — {precio_txt}")
    return "\n".join(lineas)


async def responder_consulta(termino: str, items: list[dict], mensaje: str) -> dict:
    """Un único punto de entrada para todo lo que el usuario le escribe a Don
    Tino sobre estos resultados: puede ser una instrucción de filtro ("quiero
    solo los celulares") o una pregunta general ("¿cuál es el más barato de
    DIMM?"). items: [{"tienda", "nombre", "precio", "moneda"}, ...] numerados
    1-indexado en el prompt, mismo orden que la respuesta.

    Devuelve {"tipo": "seleccion"|"respuesta", "mantener": [1,4,7] | None, "respuesta": "..."}.
    "mantener" solo viene poblado cuando tipo="seleccion" — el frontend lo usa
    para actualizar un checklist si existe; si no hay checklist en esa pantalla
    (ej. la página de búsqueda sin gráfico abierto), simplemente se ignora.
    Si el parseo del JSON falla, se devuelve tipo="respuesta" con un mensaje de
    error — nunca se vacía nada por un fallo de parseo.
    """
    listado = _formatear_items_numerados(items)
    prompt = (
        f'El usuario buscó "{termino}" en el comparador de precios de la competencia y ahora te escribió: '
        f'"{mensaje}"\n\n'
        f"Estos son los productos encontrados, numerados con su precio:\n{listado}\n\n"
        'Primero decidí qué tipo de pedido es:\n'
        '- Si te está pidiendo filtrar/quedarse solo con ciertos productos (ej. "quiero solo los celulares", '
        '"sacá los accesorios"), es tipo "seleccion".\n'
        '- Si te está haciendo una pregunta general sobre los datos (ej. "¿cuál es el más barato?", '
        '"¿cuántos hay de DIMM?"), es tipo "respuesta".\n\n'
        'Devolvé SOLO un objeto JSON, sin texto antes ni después:\n'
        '- Para tipo "seleccion": {"tipo": "seleccion", "mantener": [1, 4, 7], "respuesta": '
        '"una frase corta explicando qué sacaste y por qué"}\n'
        '- Para tipo "respuesta": {"tipo": "respuesta", "mantener": null, "respuesta": '
        '"la respuesta completa a la pregunta, con números concretos de la lista"}\n\n'
        '"mantener" son los números de los productos que SÍ corresponden a lo pedido '
        '(lista vacía si ninguno aplica).'
    )
    try:
        content, _ = await _ask_claude(DON_TINO_BASE, prompt, max_tokens=600)
        parsed = json.loads(_strip_json_fence(content))
        tipo = parsed.get("tipo") if parsed.get("tipo") in ("seleccion", "respuesta") else "respuesta"
        respuesta = str(parsed.get("respuesta") or "").strip()
        mantener = None
        if tipo == "seleccion":
            crudo = parsed.get("mantener") or []
            mantener = [i for i in crudo if isinstance(i, int) and 1 <= i <= len(items)]
        return {"tipo": tipo, "mantener": mantener, "respuesta": respuesta or "Listo."}
    except Exception as exc:
        log.warning("don_tino_precios.responder_consulta: fallo parseando respuesta — %s", exc)
        return {
            "tipo": "respuesta",
            "mantener": None,
            "respuesta": "No pude interpretar bien tu pedido — probá reformulándolo.",
        }


def _formatear_items_para_prompt(items: list[dict]) -> str:
    lineas = []
    for it in items:
        moneda = it.get("moneda") or "UYU"
        simbolo = "U$S" if moneda == "USD" else "$"
        lineas.append(f"- [{it['tienda']}] {it['nombre']}: {simbolo} {it['precio']:.2f} ({moneda})")
    return "\n".join(lineas)


async def generar_reporte(
    items: list[dict],
    nuestro_precio: float | None = None,
    nuestra_moneda: str | None = None,
) -> str:
    """items: [{"tienda": str, "nombre": str, "precio": float, "moneda": str}, ...]

    Los precios pueden venir en monedas distintas (UYU/USD mezclados) — mismo
    criterio de no comparar entre monedas que ya usa el resto de la app
    (ComparisonModal.hayMismaMoneda, "cheapest" en precios/page.tsx). El prompt
    lo deja explícito para que ningún modelo compare UYU contra USD como si
    fueran lo mismo.

    Patrón: Claude analiza en frío (picos, mediana, dispersión) -> ChatGPT
    analiza en frío (lectura estratégica/posicionamiento) -> Claude sintetiza
    ambos en el texto final, en primera persona como Don Tino. Los pasos 1 y 2
    quedan internos, solo se devuelve el texto final.
    """
    datos = _formatear_items_para_prompt(items)
    nuestro_line = ""
    if nuestro_precio is not None and nuestra_moneda:
        simbolo = "U$S" if nuestra_moneda == "USD" else "$"
        nuestro_line = f"\n\nNuestro precio: {simbolo} {nuestro_precio:.2f} ({nuestra_moneda})"

    datos_completos = (
        f"Precios de la competencia encontrados (separados por moneda — nunca compares UYU contra "
        f"USD como si fueran equivalentes):\n{datos}{nuestro_line}"
    )

    prompt_cuantitativo = (
        f"{datos_completos}\n\n"
        "Analizá estos precios con rigor numérico: precio más bajo y más alto (con cadena), "
        "mediana y promedio (separado por moneda si hay más de una), y qué tan dispersos están los "
        "precios entre cadenas. Si hay nuestro precio, decí exactamente dónde queda posicionado "
        "respecto al resto (en su misma moneda). Sé concreto y con números — máximo 3 párrafos cortos."
    )
    analisis_cuantitativo, _ = await _ask_claude(
        DON_TINO_BASE + " Tu tarea ahora: análisis cuantitativo de precios de la competencia.",
        prompt_cuantitativo,
        max_tokens=600,
    )

    prompt_estrategico = (
        f"{datos_completos}\n\n"
        "Dame una lectura estratégica de estos precios: ¿alguna cadena está siendo agresiva en esta "
        "categoría? ¿hay una oportunidad de posicionamiento clara? Si hay nuestro precio, decí si "
        "conviene sostenerlo, bajarlo o si está bien donde está, y por qué. Concreto — máximo 3 párrafos cortos."
    )
    analisis_estrategico, _ = await _ask_gpt(
        DON_TINO_BASE + " Tu tarea ahora: lectura estratégica de posicionamiento de precios.",
        prompt_estrategico,
        max_tokens=600,
    )

    prompt_sintesis = (
        f"{datos_completos}\n\n"
        f"Ya hiciste el análisis cuantitativo internamente: \"{analisis_cuantitativo}\"\n\n"
        f"Y tenés esta lectura estratégica adicional: \"{analisis_estrategico}\"\n\n"
        "Ahora escribí el reporte final que le vas a mostrar al usuario, en tu propia voz — no cites "
        "ni menciones que hubo dos análisis separados, es tu conclusión. Estructuralo en:\n"
        "1. Los números clave (más barato, más caro, mediana/promedio)\n"
        "2. Dónde queda posicionado nuestro precio, si lo hay\n"
        "3. Una recomendación concreta y corta\n"
        "Máximo 4 párrafos cortos, directo, sin relleno."
    )
    reporte_final, _ = await _ask_claude(
        DON_TINO_BASE + " Tu tarea ahora: redactar el reporte final que va a leer el usuario.",
        prompt_sintesis,
        max_tokens=700,
    )
    return reporte_final
