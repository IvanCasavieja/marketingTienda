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
import statistics

from app.services.debate_service import _ask_claude, _ask_gpt

log = logging.getLogger(__name__)

DON_TINO_BASE = (
    "Sos Don Tino, el asistente de MKTG Platform para Tienda Inglesa. Hablás en "
    "primera persona, en español rioplatense, directo y útil. Nunca mencionás que "
    "sos un modelo de lenguaje ni cuál — para quien te lee, siempre sos vos, Don Tino, "
    "respondiendo directamente."
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_MUESTRA_MAX  = 40  # tope de nombres que se muestran de ejemplo en el paso 1 — con
                    # listas de cientos de productos, pedirle a un modelo que
                    # enumere/cuente índices exactos ahí mismo es lento, caro y
                    # poco confiable.
_REFINAR_MAX  = 60  # tope de candidatos para el paso 2 (revisión semántica) —
                    # por debajo de esto, Claude SÍ puede revisar uno por uno de
                    # forma confiable. Por encima, nos quedamos con el filtro de
                    # palabras clave solo (sin la segunda pasada).


def _strip_json_fence(text: str) -> str:
    """Los modelos a veces envuelven el JSON en ```json ... ``` a pesar de que se
    les pide texto plano — se le hace strip antes de json.loads en vez de fallar."""
    return _JSON_FENCE_RE.sub("", text).strip()


def _muestra_nombres(items: list[dict], max_items: int = _MUESTRA_MAX) -> str:
    muestra = items[:max_items]
    lineas = [f"- [{it['tienda']}] {it['nombre']}" for it in muestra]
    if len(items) > max_items:
        lineas.append(f"... y {len(items) - max_items} más (no se muestran todos, hay {len(items)} en total)")
    return "\n".join(lineas)


def _matches(nombre: str, incluir: list[str], excluir: list[str]) -> bool:
    n = nombre.lower()
    ok_incluir = not incluir or any(k in n for k in incluir)
    ok_excluir = not any(k in n for k in excluir)
    return ok_incluir and ok_excluir


async def _afinar_seleccion(termino: str, mensaje: str, candidatos: list[tuple[int, dict]]) -> list[int]:
    """candidatos: [(índice_original, item), ...] ya prefiltrados por palabra
    clave — acotado a lo sumo a _REFINAR_MAX, así que acá SÍ es confiable
    pedirle a Claude que los revise uno por uno con criterio real, no solo
    texto. Esto es lo que agarra el caso "pedí celulares, el filtro de palabra
    clave también trajo una tablet o un accesorio que coincide por texto pero
    no es lo que se pidió". Devuelve los índices ORIGINALES a mantener.
    """
    listado = "\n".join(f"{n}. [{it['tienda']}] {it['nombre']}" for n, (_, it) in enumerate(candidatos, start=1))
    prompt = (
        f'El usuario buscó "{termino}" y te pidió: "{mensaje}"\n\n'
        f"Estos productos ya pasaron un filtro de palabras clave, pero puede haber falsos positivos — "
        f"por ejemplo, si pidió \"celulares\" y hay una tablet o un accesorio que coincide por texto pero "
        f"no es lo que pidió. Revisalos uno por uno con criterio real (qué tipo de producto es, no solo "
        f"si el texto matchea):\n{listado}\n\n"
        'Devolvé SOLO un JSON: {"mantener": [1, 3, 5]} — los números de los que SÍ corresponden '
        'de verdad a lo que pidió el usuario. Si todos corresponden, incluilos todos.'
    )
    try:
        content, _ = await _ask_claude(DON_TINO_BASE, prompt, max_tokens=400)
        parsed = json.loads(_strip_json_fence(content))
        mantener_local = [i for i in parsed.get("mantener", []) if isinstance(i, int) and 1 <= i <= len(candidatos)]
        return [candidatos[i - 1][0] for i in mantener_local]
    except Exception as exc:
        log.warning("don_tino_precios._afinar_seleccion: fallo, uso el filtro de palabras clave sin afinar — %s", exc)
        return [idx for idx, _ in candidatos]


async def responder_consulta(termino: str, items: list[dict], mensaje: str) -> dict:
    """Un único punto de entrada para todo lo que el usuario le escribe a Don
    Tino sobre estos resultados: puede ser una instrucción de filtro ("quiero
    solo los que sean Galaxy A17") o una pregunta general ("¿cuál es el más
    barato de DIMM?").

    "seleccion" se resuelve en DOS pasos para poder ser rápido/barato con
    listas de cientos de productos Y semánticamente correcto:
      1) Claude propone palabras clave de inclusión/exclusión mirando solo una
         MUESTRA acotada de nombres reales (no la lista completa) — cuestión
         de vocabulario, no de enumerar productos.
      2) Ese filtro de palabras clave se aplica en Python sobre la lista
         COMPLETA (determinístico, cualquier tamaño). Si los candidatos que
         matchean son pocos (<= _REFINAR_MAX), una segunda pasada de Claude
         los revisa uno por uno con criterio real — así no alcanza con que el
         texto "matchee": una tablet Galaxy no se cuela en "solo celulares"
         aunque comparta la palabra "galaxy".

    Devuelve {"tipo": "seleccion"|"respuesta", "mantener": [1,4,7] | None, "respuesta": "..."}.
    Si el parseo del primer paso falla, se devuelve tipo="respuesta" con un
    mensaje de error — nunca se aplica un filtro por un fallo de parseo.
    """
    muestra = _muestra_nombres(items)
    prompt = (
        f'El usuario buscó "{termino}" en el comparador de precios de la competencia y ahora te escribió: '
        f'"{mensaje}"\n\n'
        f"Ejemplos reales de productos encontrados (hay {len(items)} en total, esto es solo una muestra):\n{muestra}\n\n"
        'Primero decidí qué tipo de pedido es:\n'
        '- "seleccion" si te pide filtrar/quedarse solo con ciertos productos (ej. "quiero solo los Galaxy A17", '
        '"sacá los accesorios").\n'
        '- "respuesta" si es una pregunta general sobre los datos (ej. "¿cuál es el más barato?").\n\n'
        'Para "seleccion": NO cuentes ni enumeres productos todavía (eso viene en un paso aparte). Dame '
        'palabras clave de qué nombre hay que buscar, usando la forma real en que aparecen en los ejemplos '
        'de arriba (ej. si el usuario dice "Galaxy 17" pero los productos dicen "Galaxy A17", la palabra '
        'clave correcta es "a17", no "17"). Podés dar palabras para incluir y, si aplica, para excluir '
        '(ej. "sacá los accesorios" -> excluir: ["funda", "soporte", "cargador", ...] según lo que veas '
        'en los ejemplos).\n\n'
        'Devolvé SOLO un objeto JSON, sin texto antes ni después:\n'
        '- Para "seleccion": {"tipo": "seleccion", "incluir": ["a17"], "excluir": [], "respuesta": '
        '"una frase corta explicando qué filtro aplicaste"}\n'
        '- Para "respuesta": {"tipo": "respuesta", "incluir": null, "excluir": null, "respuesta": '
        '"la respuesta a la pregunta — si necesitás precios exactos y la muestra no alcanza, decilo"}'
    )
    try:
        content, _ = await _ask_claude(DON_TINO_BASE, prompt, max_tokens=500)
        parsed = json.loads(_strip_json_fence(content))
        tipo = parsed.get("tipo") if parsed.get("tipo") in ("seleccion", "respuesta") else "respuesta"
        respuesta = str(parsed.get("respuesta") or "").strip()
    except Exception as exc:
        log.warning("don_tino_precios.responder_consulta: fallo parseando respuesta — %s", exc)
        return {
            "tipo": "respuesta",
            "mantener": None,
            "respuesta": "No pude interpretar bien tu pedido — probá reformulándolo.",
        }

    if tipo != "seleccion":
        return {"tipo": "respuesta", "mantener": None, "respuesta": respuesta or "Listo."}

    incluir = [str(k).lower() for k in (parsed.get("incluir") or []) if str(k).strip()]
    excluir = [str(k).lower() for k in (parsed.get("excluir") or []) if str(k).strip()]
    candidatos = [(i, it) for i, it in enumerate(items, start=1) if _matches(it["nombre"], incluir, excluir)]

    if candidatos and len(candidatos) <= _REFINAR_MAX:
        mantener = await _afinar_seleccion(termino, mensaje, candidatos)
    else:
        mantener = [i for i, _ in candidatos]

    return {"tipo": "seleccion", "mantener": mantener, "respuesta": respuesta or "Listo."}


def _stats_por_moneda(items: list[dict]) -> dict[str, dict]:
    """Estadísticas exactas calculadas en Python (no le pedimos a un modelo que
    "calcule" la mediana de cientos de precios — eso es aritmética, no análisis,
    y con listas grandes es donde más se equivocan)."""
    por_moneda: dict[str, list[dict]] = {}
    for it in items:
        por_moneda.setdefault(it.get("moneda") or "UYU", []).append(it)

    resultado: dict[str, dict] = {}
    for moneda, lst in por_moneda.items():
        precios = [it["precio"] for it in lst]
        mas_barato = min(lst, key=lambda it: it["precio"])
        mas_caro = max(lst, key=lambda it: it["precio"])
        resultado[moneda] = {
            "cantidad": len(lst),
            "minimo": mas_barato["precio"], "minimo_tienda": mas_barato["tienda"], "minimo_nombre": mas_barato["nombre"],
            "maximo": mas_caro["precio"], "maximo_tienda": mas_caro["tienda"], "maximo_nombre": mas_caro["nombre"],
            "mediana": statistics.median(precios),
            "promedio": statistics.mean(precios),
        }
    return resultado


def _resumen_por_cadena(items: list[dict]) -> str:
    """Rango de precios por cadena — a diferencia de listar cada producto, esto
    queda acotado a lo sumo a las ~13 cadenas soportadas, sin importar cuántos
    productos haya en total."""
    agregado: dict[tuple[str, str], list[float]] = {}
    for it in items:
        key = (it["tienda"], it.get("moneda") or "UYU")
        agregado.setdefault(key, []).append(it["precio"])

    lineas = []
    for (tienda, moneda), precios in sorted(agregado.items()):
        simbolo = "U$S" if moneda == "USD" else "$"
        rango = f"{simbolo}{min(precios):.2f}" if min(precios) == max(precios) else f"{simbolo}{min(precios):.2f}–{simbolo}{max(precios):.2f}"
        lineas.append(f"- {tienda} ({moneda}): {len(precios)} producto(s), rango {rango}")
    return "\n".join(lineas)


def _formatear_stats(stats: dict[str, dict], nuestro_precio: float | None, nuestra_moneda: str | None) -> str:
    lineas = []
    for moneda, s in stats.items():
        simbolo = "U$S" if moneda == "USD" else "$"
        lineas.append(
            f"[{moneda}] {s['cantidad']} producto(s) — "
            f"más barato: {simbolo}{s['minimo']:.2f} ({s['minimo_tienda']} — {s['minimo_nombre']}); "
            f"más caro: {simbolo}{s['maximo']:.2f} ({s['maximo_tienda']} — {s['maximo_nombre']}); "
            f"mediana: {simbolo}{s['mediana']:.2f}; promedio: {simbolo}{s['promedio']:.2f}"
        )
        if nuestro_precio is not None and nuestra_moneda == moneda:
            if nuestro_precio < s["mediana"]:
                posicion = "por debajo de la mediana"
            elif nuestro_precio > s["mediana"]:
                posicion = "por encima de la mediana"
            else:
                posicion = "justo en la mediana"
            lineas.append(f"  → Nuestro precio en {moneda}: {simbolo}{nuestro_precio:.2f} ({posicion})")
    return "\n".join(lineas)


async def generar_reporte(
    items: list[dict],
    nuestro_precio: float | None = None,
    nuestra_moneda: str | None = None,
) -> str:
    """items: [{"tienda": str, "nombre": str, "precio": float, "moneda": str}, ...]

    Los números clave (mínimo, máximo, mediana, promedio) se calculan en
    Python, no se le piden a un modelo — son aritmética exacta y no dependen
    de cuántos productos haya. Los modelos solo interpretan esos números ya
    calculados, más un resumen acotado por cadena (rango de precios), nunca
    la lista completa producto por producto.

    Los precios pueden venir en monedas distintas (UYU/USD mezclados) — mismo
    criterio de no comparar entre monedas que ya usa el resto de la app
    (ComparisonModal.hayMismaMoneda, "cheapest" en precios/page.tsx).

    Patrón: Claude analiza en frío (lectura de los números) -> ChatGPT analiza
    en frío (lectura estratégica/posicionamiento) -> Claude sintetiza ambos en
    el texto final, en primera persona como Don Tino. Los pasos 1 y 2 quedan
    internos, solo se devuelve el texto final.
    """
    stats = _stats_por_moneda(items)
    stats_txt = _formatear_stats(stats, nuestro_precio, nuestra_moneda)
    resumen_cadenas = _resumen_por_cadena(items)

    datos_completos = (
        f"Estadísticas de precios de la competencia (ya calculadas, exactas — separadas por moneda, "
        f"nunca compares UYU contra USD como si fueran equivalentes):\n{stats_txt}\n\n"
        f"Rango de precios por cadena:\n{resumen_cadenas}"
    )

    prompt_cuantitativo = (
        f"{datos_completos}\n\n"
        "Interpretá estos números con rigor: qué tan dispersos están los precios entre cadenas, "
        "si hay outliers claros, y si hay nuestro precio, dónde queda posicionado exactamente "
        "(ya te digo si está por encima o debajo de la mediana — explicá qué implica eso). "
        "Sé concreto, citá los números tal cual te los di — máximo 3 párrafos cortos."
    )
    analisis_cuantitativo, _ = await _ask_claude(
        DON_TINO_BASE + " Tu tarea ahora: interpretar estadísticas de precios de la competencia.",
        prompt_cuantitativo,
        max_tokens=600,
    )

    prompt_estrategico = (
        f"{datos_completos}\n\n"
        "Dame una lectura estratégica: ¿alguna cadena está siendo agresiva en esta categoría según el "
        "rango de precios? ¿hay una oportunidad de posicionamiento clara? Si hay nuestro precio, decí si "
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
        "1. Los números clave (más barato, más caro, mediana/promedio) — citalos tal cual\n"
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


async def explicar_cambio_precio(
    tienda: str, nombre: str, precio_anterior: float, precio_nuevo: float, moneda: str,
) -> str:
    """Frase corta para la notificación de un producto seguido en una lista
    de monitoreo — un solo call barato, no un debate. Usado por
    watchlist_service.py cuando el chequeo diario detecta un precio distinto."""
    simbolo = "U$S" if moneda == "USD" else "$"
    variacion_pct = (precio_nuevo - precio_anterior) / precio_anterior * 100 if precio_anterior else 0.0
    prompt = (
        f"Detectaste un cambio de precio en un producto que el usuario tiene en una lista de monitoreo:\n"
        f"[{tienda}] {nombre}\n"
        f"Precio anterior: {simbolo}{precio_anterior:.2f}\n"
        f"Precio nuevo: {simbolo}{precio_nuevo:.2f} ({variacion_pct:+.1f}%)\n\n"
        "Escribí UNA sola frase corta (para una notificación, no un párrafo) avisándole del cambio, "
        "en tu voz. Mencioná el nombre del producto, la cadena, y los dos precios."
    )
    content, _ = await _ask_claude(
        DON_TINO_BASE + " Tu tarea ahora: redactar una notificación de un solo cambio de precio.",
        prompt,
        max_tokens=150,
    )
    return content.strip()
