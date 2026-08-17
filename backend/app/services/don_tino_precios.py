"""
don_tino_precios.py — IA aplicada a los resultados del buscador de precios en vivo,
presentada bajo la persona de Doña Tina (el nombre del archivo quedó de una
primera versión donde este dominio era de Don Tino — ver tino_personas.py
para el reparto vigente: Don Tino es la guía general de la plataforma, Doña
Tina es la experta en precios).

Por detrás usa Claude y ChatGPT (mismos helpers _ask_claude/_ask_gpt de
debate_service.py que ya usa La Triada) pero el usuario nunca ve "Claude" ni
"ChatGPT" — todo se devuelve en primera persona como Doña Tina. No se reusan
CLAUDE_PERSONA/GPT_PERSONA de debate_service.py: esas están armadas para un
debate adversarial de métricas de campañas, tono equivocado para esto.

100% stateless — no persiste nada. La única excepción es responder_consulta():
su chat abierto SÍ puede disparar una búsqueda nueva (tool buscar_precios) si
la pregunta del usuario lo requiere -- es la única función de este archivo con
un loop de tool-use real, ver su docstring. El resto sigue siendo pipelines
fijos que solo operan sobre los resultados que ya trajo la búsqueda en vivo.
"""
import asyncio
import json
import logging
import re
import statistics
import unicodedata

import anthropic

from app.core.config import settings
from app.services.debate_service import _ask_claude, _ask_gpt, _ASK_CLAUDE_META, _ASK_GPT_META
from app.services.ai_usage_service import log_ai_usage
from app.services.tino_personas import DONA_TINA_BASE

log = logging.getLogger(__name__)

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


async def _afinar_seleccion(
    termino: str, mensaje: str, candidatos: list[tuple[int, dict]], db=None, user_id=None
) -> tuple[list[int], list[dict]]:
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
    ese grupo. Devuelve (índices ORIGINALES a mantener, usage_items) — el
    segundo elemento para que el caller (responder_consulta) pueda sumarlo
    al total de tokens de la tarea completa."""
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
        return [idx for idxs in grupos.values() for idx in idxs], []

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
    usage_items: list[dict] = []
    try:
        content, in_tok, out_tok = await _ask_claude(DONA_TINA_BASE, prompt, max_tokens=400)
        usage_items.append({"provider": _ASK_CLAUDE_META[0], "model": _ASK_CLAUDE_META[1], "input_tokens": in_tok, "output_tokens": out_tok})
        await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content))
        mantener_local = [i for i in parsed.get("mantener", []) if isinstance(i, int) and 1 <= i <= len(claves)]
        claves_mantener = {claves[i - 1] for i in mantener_local}
    except Exception as exc:
        log.warning("don_tino_precios._afinar_seleccion: fallo, uso el filtro de palabras clave sin afinar — %s", exc)
        claves_mantener = set(claves)

    return [idx for key in claves if key in claves_mantener for idx in grupos[key]], usage_items


_SINONIMOS_MAX_TOKENS = 300


async def generar_sinonimos_busqueda(termino: str, db=None, user_id=None) -> list[str]:
    """Que una cadena no encuentre nada con el término buscado puede ser un problema
    de VOCABULARIO, no de que el producto no exista ahí -- ejemplo real: buscar
    "perfume" no encuentra ningún perfume real en Pigalle porque esos productos se
    nombran "EDT"/"EDP"/"PARFUM" (nunca dicen literalmente "perfume" -- esa palabra
    solo aparece en productos "SIN PERFUME" de otras categorías, que sí le ganan por
    coincidencia de texto). O buscar "heladera" no encuentra nada en un catálogo que
    solo usa "Refrigerador".

    Le pide a Doña Tina hasta 3 términos alternativos para la MISMA categoría de
    producto, con vocabulario distinto (técnico, de marca, o un sinónimo regional)
    al que el término original -- se usan SOLO para ensanchar la búsqueda en las
    cadenas que ya se sabe que no encontraron nada, nunca reemplazan al término
    original ni se le muestran al usuario.

    Devuelve [] si el término ya es específico (no hace falta ensanchar) o si la
    llamada a Claude falla -- fail-open: sin sinónimos, la búsqueda sigue nomás con
    el término original, nunca se rompe por esto."""
    prompt = (
        f'Alguien buscó "{termino}" en un comparador de precios de comercios uruguayos, y '
        'ESTA búsqueda no encontró nada en algunas cadenas.\n\n'
        'Si el término ya es específico (marca + tipo de producto reconocible, ej. '
        '"lavarropas james", "celular samsung"), respondé con una lista vacía -- lo más '
        'probable es que esa cadena simplemente no tenga ese producto, no hace falta '
        'ensanchar nada.\n\n'
        'Si en cambio es un término GENÉRICO de categoría donde el catálogo real podría '
        'nombrar el producto con otra palabra o terminología técnica (ejemplos reales: '
        '"perfume" -> los perfumes se nombran "EDT", "EDP", "PARFUM" o "colonia", casi '
        'nunca dicen literalmente "perfume"; "heladera" -> algunos catálogos dicen '
        '"refrigerador"), dame hasta 3 términos de búsqueda alternativos que un catálogo '
        'real podría usar para EL MISMO tipo de producto.\n\n'
        'Devolvé SOLO un JSON: {"sinonimos": ["termino1", "termino2"]} -- lista vacía si '
        'no hace falta ensanchar.'
    )
    try:
        content, in_tok, out_tok = await _ask_claude(DONA_TINA_BASE, prompt, max_tokens=_SINONIMOS_MAX_TOKENS)
        await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content))
        sinonimos = parsed.get("sinonimos")
        if not isinstance(sinonimos, list):
            return []
        return [s.strip() for s in sinonimos if isinstance(s, str) and s.strip()][:3]
    except Exception as exc:
        log.warning("don_tino_precios.generar_sinonimos_busqueda: fallo — %s", exc)
        return []


_AUTO_FILTRO_MAX_POR_TANDA = 60  # mismo criterio que _REFINAR_MAX -- por encima de esto
                                  # Claude no revisa producto por producto de forma confiable.
                                  # A diferencia de _afinar_seleccion (que si se pasa del tope
                                  # se resigna a no afinar), acá se trocea en tandas: este
                                  # filtro reemplaza por completo al filtro rígido de palabras
                                  # (ver live_search.py score_match) como único chequeo de
                                  # marca/categoría real, no es una segunda pasada opcional
                                  # sobre una lista ya angostada por palabras clave.

_TANDA_CONCURRENCY = 8  # tope de tandas en simultáneo -- una búsqueda ancha
                        # (ej. "coca cola", miles de candidatos) arma decenas
                        # de tandas; corriéndolas todas en paralelo con este
                        # techo bajan de minutos a segundos sin bombardear la
                        # API de Claude con decenas de llamadas a la vez.


def _en_tandas(items: list, tam: int):
    for i in range(0, len(items), tam):
        yield items[i:i + tam]


def _norm_marca(marca: str) -> str:
    """minúsculas + sin tildes + separadores (espacio/guión) colapsados a uno
    solo -- sin esto, la misma marca real termina partida en varios buckets
    del "agrupado por marca" solo porque Claude la escribió distinto en tandas
    distintas (ej. "Coca-Cola" / "COCA COLA" / "Coca Cola" quedaban como 3
    marcas separadas en vez de una sola)."""
    return re.sub(r"[\s\-_]+", " ", _normalizar(marca)).strip()


async def filtrar_relevancia_automatica(termino: str, items: list[dict], db=None, user_id=None) -> dict:
    """Reemplazo AUTOMÁTICO (corre siempre, sin que el usuario le pida nada a Doña Tina) del
    filtro rígido por palabras: trata el término buscado como el pedido implícito ("mostrame
    solo lo que de verdad es esto"), con el mismo criterio real de _afinar_seleccion — no si el
    texto matchea, sino si el tipo de producto y la marca corresponden. Ejemplo real que motivó
    esto: buscar "lavarropas james" no debería traer "Refrigerador JAMES" (misma marca, otro
    producto) ni "Lavarropas MIDEA" (mismo producto, otra marca) — score_match no puede
    distinguir esto de forma confiable (ver su propio docstring), y exigir que todas las
    palabras del término aparezcan literalmente (lo que se probó primero) rechaza también
    búsquedas más amplias legítimas.

    items: [{"tienda", "nombre", "marca": str|None, ...}, ...] — la lista COMPLETA de
    resultados de la búsqueda en vivo, en el mismo orden en que se les va a aplicar el resto de
    los campos (precio, url, etc.) al armar la respuesta final.

    Se agrupa por (tienda, nombre) igual que _afinar_seleccion — mismo producto en varias
    sucursales es UNA sola decisión, no una por fila. Además de mantener/descartar, Claude
    devuelve la marca que infiere de cada nombre (con la marca ya conocida, si el adapter la
    expone, como pista) — así se puede armar un total por marca aunque la mayoría de los
    adapters no traigan un campo de marca propio.

    Devuelve {"indices_mantener": [...], "conteo_por_marca": {"James": 8, ...}, "fallo_parcial":
    bool}. Los índices son 0-based sobre `items`. Si una tanda falla (red, JSON raro), esa tanda
    se deja SIN FILTRAR (fail-open, "fallo_parcial"=True) — más vale mostrar de más por un fallo
    transitorio de la IA que romper la búsqueda entera."""
    if not items:
        return {"indices_mantener": [], "conteo_por_marca": {}, "fallo_parcial": False}

    grupos: dict[tuple[str, str], list[int]] = {}
    marca_conocida: dict[tuple[str, str], str | None] = {}
    for idx, it in enumerate(items):
        key = (it["tienda"], it["nombre"])
        grupos.setdefault(key, []).append(idx)
        marca_conocida.setdefault(key, it.get("marca"))

    claves = list(grupos.keys())
    tandas = list(_en_tandas(claves, _AUTO_FILTRO_MAX_POR_TANDA))
    sem = asyncio.Semaphore(_TANDA_CONCURRENCY)
    resultados_tandas = await asyncio.gather(
        *[_procesar_tanda_relevancia(termino, tanda, marca_conocida, sem) for tanda in tandas]
    )

    mantener: set[tuple[str, str]] = set()
    conteo_por_marca_norm: dict[str, int] = {}
    marca_display: dict[str, str] = {}
    fallo_parcial = False

    # El merge de resultados y el logueo de uso quedan secuenciales acá --
    # AsyncSession no soporta uso concurrente desde varias corutinas a la vez
    # (mismo criterio que documentos.py::crear_documentos_y_extraer), así que
    # solo la llamada a Claude en sí se paraleliza arriba.
    for tanda, (resultado_items, in_tok, out_tok) in zip(tandas, resultados_tandas):
        if resultado_items is None:
            fallo_parcial = True
            for key in tanda:
                mantener.add(key)
            continue

        await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)

        for n, key in enumerate(tanda, start=1):
            entrada = resultado_items.get(str(n))
            if not isinstance(entrada, dict) or entrada.get("mantener") is not True:
                continue
            mantener.add(key)
            marca = entrada.get("marca")
            marca = marca.strip() if isinstance(marca, str) and marca.strip() else marca_conocida.get(key)
            if marca:
                marca_key = _norm_marca(marca)
                marca_display.setdefault(marca_key, marca)
                conteo_por_marca_norm[marca_key] = conteo_por_marca_norm.get(marca_key, 0) + len(grupos[key])

    conteo_por_marca = {marca_display[k]: v for k, v in conteo_por_marca_norm.items()}
    indices_mantener = sorted(idx for key in mantener for idx in grupos[key])
    return {
        "indices_mantener": indices_mantener,
        "conteo_por_marca": conteo_por_marca,
        "fallo_parcial": fallo_parcial,
    }


async def _procesar_tanda_relevancia(
    termino: str,
    tanda: list[tuple[str, str]],
    marca_conocida: dict[tuple[str, str], str | None],
    sem: asyncio.Semaphore,
) -> tuple[dict | None, int, int]:
    """Solo la llamada a Claude para una tanda, sin tocar `db` -- así
    filtrar_relevancia_automatica puede correr todas las tandas en paralelo
    (ver ahí el motivo de por qué el logueo de uso queda afuera, secuencial).
    Devuelve (resultado_items o None si la tanda falló, input_tokens,
    output_tokens) -- tokens en 0 si falló, no se gastó nada que loguear."""
    lineas = []
    for n, (tienda, nombre) in enumerate(tanda, start=1):
        pista = marca_conocida.get((tienda, nombre))
        lineas.append(f"{n}. [{tienda}] {nombre}" + (f" (marca conocida: {pista})" if pista else ""))
    listado = "\n".join(lineas)
    prompt = (
        f'El usuario buscó "{termino}" en el comparador de precios de la competencia. '
        f'Estos son los productos únicos que trajeron los distintos sitios (si el mismo '
        f'producto aparece en varias sucursales de una cadena, acá aparece una sola vez '
        f'representándolas a todas):\n{listado}\n\n'
        'Para cada uno, decidí con criterio real (qué tipo de producto es y de qué marca, '
        'no solo si el texto se parece a la búsqueda) si corresponde de verdad a lo que se '
        'buscó. Por ejemplo, si se buscó "lavarropas james": un "Refrigerador JAMES" NO '
        'corresponde (misma marca, otro tipo de producto) y un "Lavarropas MIDEA" tampoco '
        '(mismo tipo de producto, otra marca), aunque los dos compartan texto con la '
        'búsqueda. Si el término NO menciona una marca específica (ej. solo "notebook"), no '
        'rechaces por marca — dejá pasar todas las marcas que sean genuinamente el producto '
        'buscado.\n\n'
        'Devolvé SOLO un JSON con esta forma exacta: {"items": {"1": {"mantener": true, '
        '"marca": "James"}, "2": {"mantener": false, "marca": null}, ...}} — una entrada '
        'por cada número de la lista, en el mismo orden. "marca" es el fabricante tal como '
        'aparece en el nombre (null si "mantener" es false, o si de verdad no se puede '
        'inferir ninguna marca del nombre).'
    )
    try:
        async with sem:
            content, in_tok, out_tok = await _ask_claude(DONA_TINA_BASE, prompt, max_tokens=3000)
        parsed = json.loads(_strip_json_fence(content))
        resultado_items = parsed.get("items")
        if not isinstance(resultado_items, dict):
            raise ValueError(f"'items' no es un dict: {resultado_items!r}")
        return resultado_items, in_tok, out_tok
    except Exception as exc:
        log.warning("don_tino_precios.filtrar_relevancia_automatica: fallo en una tanda — %s", exc)
        return None, 0, 0


_MAX_TOOL_ITERATIONS = 3  # tope de vueltas de tool-use -- alcanza con "busca -> responde",
# no hace falta el margen más generoso de Tinín/DogTi acá.

_TOOLS_CONSULTA = [{
    "name": "buscar_precios",
    "description": (
        "Busca precios en vivo de un producto en las cadenas uruguayas soportadas. Usala SOLO "
        "cuando la pregunta necesita datos que NO están en la muestra de productos ya buscados "
        "-- otro término, otra marca, u otra cadena que no aparece en los resultados actuales "
        "(ej. \"¿y en Fama hay algo?\", \"buscá también auriculares\"). Sus resultados son "
        "SOLO para responder con tipo=\"respuesta\" -- nunca los uses para decidir incluir/"
        "excluir de una selección, esos filtros siempre se aplican sobre la búsqueda ORIGINAL "
        "que ya está en pantalla, nunca sobre una búsqueda nueva."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "termino": {"type": "string", "description": "Qué buscar, ej. 'auriculares bluetooth'"},
        },
        "required": ["termino"],
    },
}]


async def _tool_buscar_precios(termino: str) -> str:
    from app.services.scraper.live_search import buscar_todas_cached

    termino = (termino or "").strip()
    if len(termino) < 2:
        return json.dumps({"error": "El término de búsqueda es muy corto"})
    try:
        resultados = await asyncio.wait_for(asyncio.to_thread(buscar_todas_cached, termino), timeout=45.0)
    except Exception as exc:
        log.warning("don_tino_precios._tool_buscar_precios: error buscando '%s' — %s", termino, exc)
        return json.dumps({"error": "Error al buscar precios en este momento"})

    items = []
    for records in resultados.values():
        for r in records:
            if r.nombre and r.precio is not None:
                items.append({
                    "tienda": r.tienda, "nombre": r.nombre, "precio": r.precio, "moneda": r.moneda,
                    "marca": r.marca, "sucursal": r.sucursal_nombre, "relevancia": r.relevancia,
                })
    items.sort(key=lambda x: x["relevancia"], reverse=True)
    top = items[:12]
    if not top:
        return json.dumps({"resultados": [], "mensaje": f"No se encontraron resultados para '{termino}'"})
    return json.dumps({"resultados": top}, ensure_ascii=False)


async def responder_consulta(termino: str, items: list[dict], mensaje: str, db=None, user_id=None) -> dict:
    """Un único punto de entrada para todo lo que el usuario le escribe a Doña
    Tina sobre estos resultados: puede ser una instrucción de filtro ("quiero
    solo los que sean Galaxy A17") o una pregunta general ("¿cuál es el más
    barato de DIMM?") -- y, a diferencia de antes, también puede disparar una
    búsqueda nueva vía la tool buscar_precios si la pregunta lo requiere (ej.
    "¿y en Fama hay algo?" cuando Fama no está en los resultados actuales).
    Esta es la única función de este archivo con un loop de tool-use real
    (patrón tinin_agent.py) -- el resto sigue siendo pipelines fijos.

    "seleccion" se resuelve en DOS pasos para poder ser rápido/barato con
    listas de cientos de productos Y semánticamente correcto:
      1) Claude propone palabras clave de inclusión/exclusión mirando solo una
         MUESTRA acotada de nombres reales (no la lista completa) — cuestión
         de vocabulario, no de enumerar productos. Esta parte ahora puede
         incluir vueltas de tool-use antes de llegar a la respuesta final.
      2) Ese filtro de palabras clave se aplica en Python sobre la lista
         COMPLETA (determinístico, cualquier tamaño). Si los candidatos que
         matchean son pocos (<= _REFINAR_MAX), una segunda pasada de Claude
         los revisa uno por uno con criterio real — así no alcanza con que el
         texto "matchee": una tablet Galaxy no se cuela en "solo celulares"
         aunque comparta la palabra "galaxy".

    Devuelve {"tipo": "seleccion"|"respuesta", "mantener": [1,4,7] | None,
    "respuesta": "...", "usage_items": [...]}. Si el parseo del primer paso
    falla, se devuelve tipo="respuesta" con un mensaje de error — nunca se
    aplica un filtro por un fallo de parseo."""
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
        'lo que se ve (ej. "¿cuál es el más barato?"), o si necesitaste usar buscar_precios para '
        'responder (una búsqueda nueva nunca produce una "seleccion" sobre la lista original).\n\n'
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
        'Cuando ya sepas qué responder (con o sin haber usado buscar_precios antes), devolvé SOLO un '
        'objeto JSON, sin texto antes ni después:\n'
        '- Para "seleccion": {"tipo": "seleccion", "incluir": ["a17"], "excluir": [], "respuesta": '
        '"una frase corta explicando qué filtro aplicaste"}\n'
        '- Para "respuesta": {"tipo": "respuesta", "incluir": null, "excluir": null, "respuesta": '
        '"la respuesta a la pregunta — si necesitás precios exactos y la muestra no alcanza, decilo"}'
    )

    usage_items: list[dict] = []

    if not settings.ANTHROPIC_API_KEY:
        return {"tipo": "respuesta", "mantener": None, "respuesta": "No pude interpretar bien tu pedido — probá reformulándolo.", "usage_items": usage_items}

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    contenido_final: str | None = None

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await client.messages.create(
            model="claude-sonnet-4-6", max_tokens=500, system=DONA_TINA_BASE,
            tools=_TOOLS_CONSULTA, messages=messages,
        )
        usage_items.append({
            "provider": "anthropic", "model": "claude-sonnet-4-6",
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
        })
        await _log_uso(db, user_id, _ASK_CLAUDE_META, response.usage.input_tokens, response.usage.output_tokens)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            contenido_final = next((b.text for b in response.content if b.type == "text"), "")
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            resultado = await _tool_buscar_precios(block.input.get("termino", ""))
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": resultado})
        messages.append({"role": "user", "content": tool_results})

    if contenido_final is None:
        return {
            "tipo": "respuesta", "mantener": None,
            "respuesta": "No pude terminar de procesar tu pedido — probá reformulándolo.",
            "usage_items": usage_items,
        }

    try:
        parsed = json.loads(_strip_json_fence(contenido_final))
        tipo = "seleccion" if _normalizar(str(parsed.get("tipo") or "")) == "seleccion" else "respuesta"
        respuesta = str(parsed.get("respuesta") or "").strip()
    except Exception as exc:
        log.warning("don_tino_precios.responder_consulta: fallo parseando respuesta — %s", exc)
        return {
            "tipo": "respuesta",
            "mantener": None,
            "respuesta": "No pude interpretar bien tu pedido — probá reformulándolo.",
            "usage_items": usage_items,
        }

    if tipo != "seleccion":
        return {"tipo": "respuesta", "mantener": None, "respuesta": respuesta or "Listo.", "usage_items": usage_items}

    incluir = [str(k).lower() for k in (parsed.get("incluir") or []) if str(k).strip()]
    excluir = [str(k).lower() for k in (parsed.get("excluir") or []) if str(k).strip()]
    candidatos = [(i, it) for i, it in enumerate(items, start=1) if _matches(it["nombre"], incluir, excluir)]

    if candidatos and len(candidatos) <= _REFINAR_MAX:
        mantener, usage_afinar = await _afinar_seleccion(termino, mensaje, candidatos, db, user_id)
        usage_items.extend(usage_afinar)
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
            "usage_items": usage_items,
        }

    return {"tipo": "seleccion", "mantener": mantener, "respuesta": respuesta or "Listo.", "usage_items": usage_items}


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
) -> tuple[str, list[dict]]:
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
    el texto final, en primera persona como Doña Tina. Los pasos 1 y 2 quedan
    internos, solo se devuelve el texto final -- sigue siendo el mismo
    pipeline fijo de siempre, ahora devuelve además (texto, usage_items) para
    que el caller pueda mostrar cuánto costó la tarea completa.
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
    usage_items: list[dict] = []

    analisis_cuantitativo, in_tok, out_tok = await _ask_claude(
        DONA_TINA_BASE + " Tu tarea ahora: interpretar estadísticas de precios de la competencia.",
        prompt_cuantitativo,
        max_tokens=600,
    )
    usage_items.append({"provider": _ASK_CLAUDE_META[0], "model": _ASK_CLAUDE_META[1], "input_tokens": in_tok, "output_tokens": out_tok})
    await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)

    prompt_estrategico = (
        f"{datos_completos}\n\n"
        "Dame una lectura estratégica: ¿alguna cadena está siendo agresiva en esta categoría según el "
        "rango de precios? ¿hay una oportunidad de posicionamiento clara? Si hay nuestro precio, decí si "
        "conviene sostenerlo, bajarlo o si está bien donde está, y por qué. Concreto — máximo 3 párrafos cortos."
    )
    analisis_estrategico, in_tok, out_tok = await _ask_gpt(
        DONA_TINA_BASE + " Tu tarea ahora: lectura estratégica de posicionamiento de precios.",
        prompt_estrategico,
        max_tokens=600,
    )
    usage_items.append({"provider": _ASK_GPT_META[0], "model": _ASK_GPT_META[1], "input_tokens": in_tok, "output_tokens": out_tok})
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
        DONA_TINA_BASE + " Tu tarea ahora: redactar el reporte final que va a leer el usuario.",
        prompt_sintesis,
        max_tokens=700,
    )
    usage_items.append({"provider": _ASK_CLAUDE_META[0], "model": _ASK_CLAUDE_META[1], "input_tokens": in_tok, "output_tokens": out_tok})
    await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
    return reporte_final, usage_items


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
        # Sin DONA_TINA_BASE completo a propósito: ese system prompt te ubica
        # como "el asistente de Tienda Inglesa" — en un prompt tan corto como
        # este, Claude terminaba mencionando "Tienda Inglesa" como si fuera la
        # cadena del cambio de precio, en vez de la competencia real (ver
        # tienda arriba). Acá alcanza con la voz/tono de Doña Tina, sin el
        # anclaje de identidad que causaba la confusión.
        "Sos Doña Tina, una asistente que habla en primera persona, en español rioplatense, "
        "directo y útil. Nunca mencionás que sos un modelo de lenguaje. "
        "Tu tarea ahora: redactar una notificación de un solo cambio de precio de la competencia.",
        prompt,
        max_tokens=150,
    )
    await _log_uso(db, user_id, _ASK_CLAUDE_META, in_tok, out_tok)
    return content.strip()
