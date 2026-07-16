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
import unicodedata

from app.services.debate_service import _ask_claude, _ask_gpt, _ASK_CLAUDE_META, _ASK_GPT_META
from app.services.ai_usage_service import log_ai_usage

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


async def _log_uso(db, user_id, meta: tuple[str, str], input_tokens: int, output_tokens: int) -> None:
    """db/user_id son opcionales — sin ellos (llamadas sin contexto de request/DB
    a mano) simplemente no se loguea, no se rompe el flujo stateless de este módulo."""
    if db is not None and user_id is not None:
        await log_ai_usage(db, user_id, "don_tino_precios", meta[0], meta[1], input_tokens, output_tokens)


def _strip_json_fence(text: str) -> str:
    """Los modelos a veces envuelven el JSON en ```json ... ``` a pesar de que se
    les pide texto plano — se le hace strip antes de json.loads en vez de fallar."""
    return _JSON_FENCE_RE.sub("", text).strip()


def _normalizar(s: str) -> str:
    """minúsculas + sin tildes + sin espacios de sobra. Sin esto, un "tipo":
    "selección" (bien escrito, con tilde — lo más natural para un modelo que
    habla español) no matchea el "seleccion" literal que le pedimos en el
    prompt, y cae en silencio al camino de "respuesta" aunque el texto narrado
    diga que sí filtró."""
    s = s.strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _muestra_nombres(items: list[dict], max_items: int = _MUESTRA_MAX) -> str:
    muestra = items[:max_items]
    lineas = [f"- [{it['tienda']}] {it['nombre']}" for it in muestra]
    if len(items) > max_items:
        lineas.append(f"... y {len(items) - max_items} más (no se muestran todos, hay {len(items)} en total)")
    return "\n".join(lineas)


def _matches(nombre: str, incluir: list[str], excluir: list[str]) -> bool:
    """Cada palabra de la keyword tiene que aparecer en el nombre, pero NO
    necesariamente pegadas ni en ese orden — si se buscara la frase completa
    como substring, "samsung galaxy" nunca matchearía "SAMSUNG Celular Galaxy
    A17" (tiene "Celular" en el medio), aunque semánticamente sea exactamente
    lo que se pidió."""
    n = nombre.lower()

    def _todas_las_palabras(frase: str) -> bool:
        return all(palabra in n for palabra in frase.split())

    ok_incluir = not incluir or any(_todas_las_palabras(k) for k in incluir)
    ok_excluir = not any(_todas_las_palabras(k) for k in excluir)
    return ok_incluir and ok_excluir


async def _afinar_seleccion(termino: str, mensaje: str, candidatos: list[tuple[int, dict]], db=None, user_id=None) -> list[int]:
    """candidatos: [(índice_original, item), ...] ya prefiltrados por palabra
    clave. Antes de mandarlos a Claude se AGRUPAN por (tienda, nombre): la
    revisión semántica es una decisión por PRODUCTO, no por sucursal — el
    mismo producto puede aparecer 8 veces (una por sucursal de Ta-Ta/El
    Dorado/GDU) con el nombre IDÉNTICO. Sin agrupar, Claude ve varias líneas
    numeradas que se leen exactamente igual y tiende a tratarlas como
    duplicados a limpiar, quedándose con una sola en vez de con todas — se
    vio en producción con "Celular Samsung Galaxy A06 Negro" repetido por
    sucursal, donde solo una quedaba tildada. Agrupando, Claude toma UNA
    decisión por producto único y acá se expande a todas las sucursales de
    ese grupo. Devuelve los índices ORIGINALES a mantener.
    """
    grupos: dict[tuple[str, str], list[int]] = {}
    item_de_grupo: dict[tuple[str, str], dict] = {}
    for idx, it in candidatos:
        key = (it["tienda"], it["nombre"])
        grupos.setdefault(key, []).append(idx)
        item_de_grupo.setdefault(key, it)

    claves = list(grupos.keys())
    if len(claves) > _REFINAR_MAX:
        # Demasiados productos únicos para una revisión confiable uno por uno
        # — nos quedamos con el filtro de palabras clave tal cual.
        return [idx for idxs in grupos.values() for idx in idxs]

    listado = "\n".join(f"{n}. [{tienda}] {nombre}" for n, (tienda, nombre) in enumerate(claves, start=1))
    prompt = (
        f'El usuario buscó "{termino}" y te pidió: "{mensaje}"\n\n'
        f"Estos son los PRODUCTOS ÚNICOS que ya pasaron un filtro de palabras clave (si un producto se "
        f"vende en varias sucursales, acá aparece una sola vez representándolas a todas), pero puede "
        f"haber falsos positivos — por ejemplo, si pidió \"celulares\" y hay una tablet o un accesorio "
        f"que coincide por texto pero no es lo que pidió. Revisalos uno por uno con criterio real (qué "
        f"tipo de producto es, no solo si el texto matchea):\n{listado}\n\n"
        'Devolvé SOLO un JSON: {"mantener": [1, 3, 5]} — los números de los que SÍ corresponden '
        'de verdad a lo que pidió el usuario. Si todos corresponden, incluilos todos.'
    )
    try:
        content, in_tok, out_tok = await _ask_claude(DON_TINO_BASE, prompt, max_tokens=400)
        await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content))
        mantener_local = [i for i in parsed.get("mantener", []) if isinstance(i, int) and 1 <= i <= len(claves)]
        claves_mantener = {claves[i - 1] for i in mantener_local}
    except Exception as exc:
        log.warning("don_tino_precios._afinar_seleccion: fallo, uso el filtro de palabras clave sin afinar — %s", exc)
        claves_mantener = set(claves)

    return [idx for key in claves if key in claves_mantener for idx in grupos[key]]


async def responder_consulta(termino: str, items: list[dict], mensaje: str, db=None, user_id=None) -> dict:
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
        '- "seleccion" si te pide filtrar/quedarse solo con ciertos productos, aunque lo pida de forma '
        'informal o indirecta (ej. "quiero solo los Galaxy A17", "sacá los accesorios", "te animás a '
        'dejarme solo los Galaxy?", "che, quedate solo con...") — cualquier variante de "mostrame/'
        'dejame/filtrá esto" cuenta como "seleccion".\n'
        '- "respuesta" únicamente si es una pregunta general sobre los datos, sin pedir que cambies '
        'lo que se ve (ej. "¿cuál es el más barato?").\n\n'
        'IMPORTANTE: el campo "tipo" tiene que ser EXACTAMENTE el string "seleccion" (así, sin tilde) o '
        '"respuesta" — nada más. Y el campo "respuesta" tiene que ser consistente con "tipo": si "tipo" '
        'es "respuesta", no digas frases como "filtré" o "dejé solo" porque no vas a aplicar ningún '
        'cambio.\n\n'
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
        content, in_tok, out_tok = await _ask_claude(DON_TINO_BASE, prompt, max_tokens=500)
        await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content))
        tipo = "seleccion" if _normalizar(str(parsed.get("tipo") or "")) == "seleccion" else "respuesta"
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
        mantener = await _afinar_seleccion(termino, mensaje, candidatos, db, user_id)
    else:
        mantener = [i for i, _ in candidatos]

    if not mantener:
        # Claude redactó "respuesta" ANTES de saber si el filtro iba a matchear
        # algo de verdad — si terminó sin candidatos, esa frase puede ser
        # optimista o directamente incorrecta. Se pisa con un mensaje preciso;
        # el frontend además no toca la selección actual cuando mantener viene vacío.
        return {
            "tipo": "seleccion",
            "mantener": [],
            "respuesta": "No encontré ningún producto que coincida con eso — dejé tu selección como estaba.",
        }

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
    db=None,
    user_id=None,
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
    analisis_cuantitativo, in_tok, out_tok = await _ask_claude(
        DON_TINO_BASE + " Tu tarea ahora: interpretar estadísticas de precios de la competencia.",
        prompt_cuantitativo,
        max_tokens=600,
    )
    await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)

    prompt_estrategico = (
        f"{datos_completos}\n\n"
        "Dame una lectura estratégica: ¿alguna cadena está siendo agresiva en esta categoría según el "
        "rango de precios? ¿hay una oportunidad de posicionamiento clara? Si hay nuestro precio, decí si "
        "conviene sostenerlo, bajarlo o si está bien donde está, y por qué. Concreto — máximo 3 párrafos cortos."
    )
    analisis_estrategico, in_tok, out_tok = await _ask_gpt(
        DON_TINO_BASE + " Tu tarea ahora: lectura estratégica de posicionamiento de precios.",
        prompt_estrategico,
        max_tokens=600,
    )
    await _log_uso(db, user_id, _ASK_GPT_META, in_tok, out_tok)

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
    reporte_final, in_tok, out_tok = await _ask_claude(
        DON_TINO_BASE + " Tu tarea ahora: redactar el reporte final que va a leer el usuario.",
        prompt_sintesis,
        max_tokens=700,
    )
    await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
    return reporte_final


async def explicar_cambio_precio(
    tienda: str, nombre: str, precio_anterior: float, precio_nuevo: float, moneda: str,
    db=None, user_id=None,
) -> str:
    """Frase corta para la notificación de un producto seguido en una lista
    de monitoreo — un solo call barato, no un debate. Usado por
    watchlist_service.py cuando el chequeo diario detecta un precio distinto."""
    simbolo = "U$S" if moneda == "USD" else "$"
    variacion_pct = (precio_nuevo - precio_anterior) / precio_anterior * 100 if precio_anterior else 0.0
    prompt = (
        f"Detectaste un cambio de precio en un producto que el usuario tiene en una lista de monitoreo:\n"
        f"Cadena monitoreada (competencia, NO Tienda Inglesa): {tienda}\n"
        f"Producto: {nombre}\n"
        f"Precio anterior: {simbolo}{precio_anterior:.2f}\n"
        f"Precio nuevo: {simbolo}{precio_nuevo:.2f} ({variacion_pct:+.1f}%)\n\n"
        f"Escribí UNA sola frase corta (para una notificación, no un párrafo) avisándole del cambio, "
        f"en tu voz. Mencioná el nombre del producto, los dos precios, y la cadena — que es "
        f"literalmente \"{tienda}\", tal cual está escrita arriba. No la reemplaces por ninguna otra."
    )
    content, in_tok, out_tok = await _ask_claude(
        # Sin DON_TINO_BASE completo a propósito: ese system prompt te ubica
        # como "el asistente de Tienda Inglesa" — en un prompt tan corto como
        # este, Claude terminaba mencionando "Tienda Inglesa" como si fuera la
        # cadena del cambio de precio, en vez de la competencia real (ver
        # tienda arriba). Acá alcanza con la voz/tono de Don Tino, sin el
        # anclaje de identidad que causaba la confusión.
        "Sos Don Tino, un asistente que habla en primera persona, en español rioplatense, "
        "directo y útil. Nunca mencionás que sos un modelo de lenguaje. "
        "Tu tarea ahora: redactar una notificación de un solo cambio de precio de la competencia.",
        prompt,
        max_tokens=150,
    )
    await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
    return content.strip()
