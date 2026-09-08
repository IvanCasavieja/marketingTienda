"""IA aplicada al Convertidor de Excel: genera sugerencias de descripción
para filas que, después del match con el catálogo y de la columna
"Descripción" del propio Excel (ver convertidor.py), siguen sin
descripción. Nunca escribe en sku_descripciones por su cuenta — solo
produce sugerencias; la persistencia se hace vía el mismo PATCH que ya usa
la edición manual, en cenefas_convertidor.py."""
import asyncio
import json
import logging
import re
import unicodedata

from app.services.ai_usage_service import log_ai_usage
from app.services.cenefas.validation_engine import DESCRIPTION_MAX_CHARS, DESCRIPTION_WARN_CHARS
from app.services.debate_service import _ASK_CLAUDE_META, _ask_claude
from app.services.tino_personas import TININ_BASE
from app.services.cenefas.convertidor_variables import FAMILIAS_MECANICA

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reglas de estilo — ÚNICO bloque a tocar cuando cambien los lineamientos.
# ---------------------------------------------------------------------------
_STYLE_RULES = f"""\
- EL ORDEN ES: producto, MARCA, variedad o sabor, y al final el tamaño después de un punto.
  La marca va INMEDIATAMENTE DESPUÉS del nombre del producto, ANTES de la variedad — nunca al final:
    "Mermelada lime curd TIPTREE. 312g"                   -> "Mermelada TIPTREE lime curd. 312g"
    "Salsa cebolla caramelizada MRS. DARLINGTON'S. 330g"  -> "Salsa MRS. DARLINGTON'S cebolla caramelizada. 330g"
    "Aceite oliva extra virgen TIENDA INGLESA. 500 ml"    -> "Aceite de oliva TIENDA INGLESA extra virgen. 500 ml"
    "Alfajor de chocolate clásico TIENDA INGLESA. 48g"    -> "Alfajor TIENDA INGLESA de chocolate clásico. 48g"
  EXCEPCIÓN — nombres de producto de dos palabras: cuando la segunda palabra es parte del NOMBRE y no
  una variedad, el nombre no se parte y la marca va después del nombre COMPLETO. Son casos como
  "Papas fritas", "Budín inglés", "Curry en polvo", "Mix frutos secos", "Snacks de proteína":
    "Papas fritas onduladas TIENDA INGLESA. 200g" -> "Papas fritas TIENDA INGLESA onduladas. 200g"
  (nunca "Papas TIENDA INGLESA fritas onduladas").
  Los productos de panadería que vienen SIN marca (Cookies, Scones) se dejan tal cual, sin inventarles una.
- La marca del producto va SIEMPRE en MAYÚSCULA COMPLETA, la palabra entera (no solo la primera letra).
- El punto va después de la marca y de la variedad/sabor que la sigue, o sea justo ANTES del tamaño, separando las dos partes como si fuera el inicio de una nueva oración corta.
  Ejemplos reales ya en el catálogo: "Aceite CAÑUELAS alto oleico. 900 ml", "Yogur YOGURISIMO natural original. 460g".
  Si no hay nada después (ni tamaño ni otra info), NO pongas un punto colgado al final — el punto separa dos partes, no es un cierre de oración.
- El resto del texto va en minúscula, con reglas normales de oración en español: mayúscula SOLO en la primera letra de toda la descripción y en la primera letra de la palabra que sigue a cada punto (incluido el punto después de la marca) — ninguna otra palabra lleva mayúscula inicial (ej. "sin piel", "con azúcar", "de cerdo", nunca "Sin Piel" ni "Con Azúcar"). Dos excepciones que no cambian nunca, sea cual sea su posición en el texto: la marca (siempre mayúscula completa, ver arriba) y las unidades de medida (ml, g, kg, L, un, etc.), siempre en minúscula incluso si quedaran al principio de una oración.
- Incluí cantidad/tamaño si se puede inferir de la fuente (ml, g, kg, L, unidades, etc.).
- Es para un cartel de precio: tiene que ser CORTA. Apuntá a menos de {DESCRIPTION_WARN_CHARS} caracteres, nunca más de {DESCRIPTION_MAX_CHARS}.
- No inventes datos (sabor, variedad, tamaño) que no estén sugeridos por el nombre o la descripción de origen.
- Si un producto viene marcado "[FIAMBRE POR KG]", la unidad en la descripción tiene que decir "100g", nunca "kg" — el precio de ese producto ya se va a recalcular aparte para esa unidad, así que el texto tiene que ser consistente con eso.
- Si un producto viene marcado "[SE COBRA POR 100 G]" o "[SE COBRA POR KILO]", la descripción TIENE QUE terminar con esa unidad, escrita exactamente "100g" o "Kg", después del punto: "Muzzarella NATURALACT. 100g", "Panceta VILLA MARGARITA ahumada. 100g", "Morcilla DON JOAQUIN dulce. Kg". Esa marca la pone la plataforma, que sabe con qué unidad se cobra ese producto en la góndola, así que NO cae en "no inventes datos": el nombre del sistema de gestión no la trae y sin ella el cartel no dice por cuánto se está cobrando. "Kg" es la única unidad que va con mayúscula, justamente porque ahí va sola después del punto y no pegada a un número.
- Con una de esas dos marcas, la unidad de cobro es la ÚNICA que va: no le agregues además un peso de envase ("500g", "1 kg") ni lo cambies por otra unidad."""

_SYSTEM_PROMPT = f"""{TININ_BASE}

Te paso productos con su nombre crudo del sistema de gestión y/o una descripción web, y para \
cada uno tenés que devolver una descripción corta y prolija para el cartel, siguiendo estas \
reglas de estilo:

{_STYLE_RULES}"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

# Techo de salida por llamada. Cada producto ocupa su clave, su texto de hasta
# 100 caracteres y la puntuación del JSON: unos 45 tokens. Con 20 productos eso
# es ~900 sólo de contenido, y el techo estaba en 1200 — sin margen. Si la
# respuesta se corta a la mitad el JSON queda inválido, json.loads levanta, y se
# pierde el CHUNK ENTERO de 20, no el producto que sobró.
_MAX_TOKENS_POR_CHUNK = 4000

_CHUNK_SIZE = 20               # productos por llamada a Claude — lotes chicos porque cada
                                # item devuelve texto libre completo, no solo un índice, así
                                # que hay más superficie de error por chunk que en un batch
                                # de "elegí cuáles mantener" (ver dona_tina_precios.py).
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
        if it.get("esFiambreKg"):
            partes.append("[FIAMBRE POR KG]")
        elif it.get("unidadVenta") == "100g":
            # El nombre de gestión no trae la unidad y el producto se cobra por
            # 100 g (ver _unidad_de_venta en convertidor.py). Sin esta marca la
            # descripción salía sin gramaje: no es que el modelo se olvidara, es
            # que tiene prohibido inventar lo que no está en la fuente.
            partes.append("[SE COBRA POR 100 G]")
        elif it.get("unidadVenta") == "kg":
            partes.append("[SE COBRA POR KILO]")
        if it["nombreArticulo"]:
            partes.append(f'nombre ERP: "{it["nombreArticulo"]}"')
        if it["descripcionWeb"]:
            partes.append(f'descripción web: "{it["descripcionWeb"]}"')
        lineas.append(f"{n}. " + " | ".join(partes))
    listado = "\n".join(lineas)
    return (
        f"Generá una descripción de cartel para cada uno de estos {len(items)} productos:\n\n"
        f"{listado}\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"descripciones": {"1": "texto...", "2": "texto...", ...}} '
        "— una entrada por cada número de la lista, en el mismo orden. Sin comentarios ni texto fuera del JSON."
    )


async def generar_descripciones(items: list[dict], db, user_id: int) -> dict:
    """items: [{"row_id", "codigo", "nombreArticulo", "descripcionWeb",
    "esFiambreKg", "unidadVenta"}, ...] — ya filtrados por el caller (filas
    sin descripción, fiambres todavía en kg que necesitan pasar a 100g, o filas
    cuya descripción no dice con qué unidad se cobra). "esFiambreKg" y
    "unidadVenta" son opcionales y solo cambian la redacción de la unidad (ver
    _STYLE_RULES) — el precio÷10 correspondiente lo calcula el frontend, no esta
    función.

    Devuelve {"suggestions": [...], "failed_row_ids": [...], "errores": [...]}. Nunca
    levanta por un chunk que falla — ese chunk se reporta en failed_row_ids y el resto de
    la respuesta sigue siendo utilizable (fail-soft, mismo criterio que _afinar_seleccion
    en dona_tina_precios.py): un fallo transitorio de red en un chunk no debería tirar
    abajo las sugerencias que ya se generaron en los demás.

    `errores` lleva el MOTIVO de cada fallo, sin repetir. Antes la excepción moría en un
    log del servidor y a la persona le llegaba "completalos a mano" sin causa: no había
    forma de distinguir una key vencida de un JSON cortado ni de un producto que no tenía
    con qué generar. Ahora el motivo llega a la pantalla."""
    # Sin nombreArticulo NI descripcionWeb no hay nada que pedirle a Claude —
    # se descarta antes de gastar un slot del batch.
    procesables = [it for it in items if it["nombreArticulo"] or it["descripcionWeb"]]
    procesables_ids = {it["row_id"] for it in procesables}
    failed_row_ids: list[int] = [it["row_id"] for it in items if it["row_id"] not in procesables_ids]

    errores: list[str] = []
    if failed_row_ids:
        # Estas ni siquiera llegan a la API: no hay con qué redactar. Pasa cuando
        # el Excel no trae la columna de nombre de gestión (NOMBREARTICULO) ni
        # DESCRIPCIONWEB -- por ejemplo si se renombró la de nombre.
        errores.append(
            f"{len(failed_row_ids)} fila(s) no tienen ni nombre de gestión ni descripción web: "
            "no hay de dónde sacar la descripción. Revisá que el Excel traiga la columna "
            "NOMBREARTICULO o DESCRIPCIONWEB."
        )

    suggestions: list[dict] = []

    for chunk in _chunks(procesables, _CHUNK_SIZE):
        prompt = _build_prompt(chunk)
        try:
            content, in_tok, out_tok = await _ask_claude(
                _SYSTEM_PROMPT, prompt, max_tokens=_MAX_TOKENS_POR_CHUNK)
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
                    _sumar_error(errores, "Claude no devolvió texto para algún producto del lote.")
        except Exception as exc:
            log.warning("convertidor_ai.generar_descripciones: chunk de %d falló — %s",
                        len(chunk), exc, exc_info=True)
            failed_row_ids.extend(it["row_id"] for it in chunk)
            _sumar_error(errores, f"{type(exc).__name__}: {exc}")

    return {"suggestions": suggestions, "failed_row_ids": failed_row_ids, "errores": errores}


def _sumar_error(errores: list[str], texto: str) -> None:
    """Un motivo por vez. Si los 3 chunks fallan por lo mismo no tiene sentido
    repetirlo tres veces en pantalla."""
    texto = texto[:300]
    if texto not in errores:
        errores.append(texto)


# ---------------------------------------------------------------------------
# "Unificar categorías" — agrupar variantes de la misma línea de producto
# (distinto peso/sabor/envase/al agua-al aceite, etc.) entre TODAS las filas
# del Excel cargado, y redactar una única descripción de cartel por grupo.
# ---------------------------------------------------------------------------
#
# Agrupar necesita que los productos relacionados se vean JUNTOS: dos miembros
# de la misma familia en tandas distintas no se detectan nunca. Durante mucho
# tiempo eso se resolvió con una sola pasada y un tope duro de filas -- pero el
# tope dejaba afuera todo lo que sobrara (207 productos de Gran Bretaña, 57 sin
# mirar) y encima una pasada tan grande se comía el presupuesto de tokens.
#
# Ahora se parte en tandas, pero NO a ciegas:
#
#  1. Se ordena por MARCA (la palabra en mayúsculas del nombre, misma regla que
#     usa el bold automático) y después por nombre. Así "Almendras con
#     chocolate negro FOREST Feast" y "Frutos secos FOREST FEAST" quedan
#     pegadas aunque empiecen con palabras distintas, que es justo el caso que
#     una partición alfabética simple rompía.
#  2. Las tandas se solapan: las últimas filas de una se repiten al principio de
#     la siguiente, así una familia que cae justo en el corte igual se ve
#     entera al menos una vez.
#  3. Al juntar los resultados, si dos tandas reclaman la misma fila gana el
#     grupo MÁS GRANDE, que es el que vio la familia más completa.

_UNIFY_ROWS_MAX = 150   # filas por tanda (una llamada al modelo)
_UNIFY_SOLAPE = 20      # filas que se repiten entre tandas consecutivas --
                        # cubre de sobra una familia típica (2 a 10 miembros)
_UNIFY_TANDAS_MAX = 8   # techo de costo: ~1000 productos por análisis
_UNIFY_CONCURRENCIA = 3 # tandas en vuelo a la vez. Más no acelera (el cuello es
                        # el modelo) y arriesga el rate limit.


_MARCA_MIN_LETRAS = 2  # "TE" o "KP" pueden ser marca; una sola letra no.


def _marca_de(nombre: str) -> str:
    """La primera palabra EN MAYUSCULAS del nombre, o "" si no hay.

    Misma senal que usa split_caps para la negrita automatica de la marca en la
    descripcion: en estos listados el nombre viene como "Mermelada strawberry
    TIPTREE. 340g" y lo que identifica la linea de producto es TIPTREE.

    Se recorre por palabra y no con una expresion regular a proposito: la
    version con \b se escribio mal una vez y quedo matcheando un caracter de
    retroceso, asi que la marca salia siempre vacia y el orden caia de nuevo en
    alfabetico por nombre --sin que nada fallara ni avisara.
    """
    for palabra in nombre.split():
        limpia = "".join(c for c in palabra if c.isalnum())
        letras = [c for c in limpia if c.isalpha()]
        if len(letras) >= _MARCA_MIN_LETRAS and all(c.isupper() for c in letras):
            return limpia.upper()
    return ""


def _clave_agrupado(it: dict) -> tuple[str, str]:
    """(marca, nombre) normalizados, para ordenar antes de partir en tandas.

    Ordenar por marca primero es lo que mantiene juntas a las variantes de una
    misma linea aunque empiecen con palabras distintas -- "Almendras con
    chocolate negro FOREST Feast" y "Mix frutos secos trufa FOREST FEAST" van
    una al lado de la otra, cosa que un orden alfabetico por nombre separaba
    por completo.
    """
    nombre = it.get("nombreArticulo") or ""
    plano = unicodedata.normalize("NFKD", nombre.casefold())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    limpio = "".join(c if (c.isalnum() or c == " ") else " " for c in plano)
    return (_marca_de(nombre), " ".join(limpio.split()))


def _armar_tandas(procesables: list[dict]) -> list[list[dict]]:
    """Parte la lista YA ORDENADA en tandas solapadas de a lo sumo _UNIFY_ROWS_MAX.

    Las tandas se hacen lo más parejas posible en vez de llenar la primera al
    tope: 207 productos salen como 2 tandas de ~104 y no como 150 + 57. Dos
    pedidos medianos terminan antes que uno enorme y uno chico, y ninguno queda
    cerca del techo de tokens.
    """
    total = len(procesables)
    if total <= _UNIFY_ROWS_MAX:
        return [procesables]
    n_tandas = min(_UNIFY_TANDAS_MAX, -(-total // _UNIFY_ROWS_MAX))
    paso = -(-total // n_tandas)
    tandas = []
    for i in range(n_tandas):
        ini = i * paso
        if ini >= total:
            break
        # el solape se toma hacia ATRÁS: la tanda arranca un poco antes de
        # donde terminó la anterior.
        desde = max(0, ini - _UNIFY_SOLAPE) if i else 0
        tandas.append(procesables[desde:ini + paso])
    return tandas

# Cuántas redacciones alternativas se muestran por grupo. Tres es el techo por
# una razón de pantalla, no de modelo: es un desplegable que se lee de un
# vistazo, y con más la elección deja de ser rápida y se vuelve otra tarea.
_UNIFY_MAX_OPCIONES = 3

_UNIFY_SYSTEM_PROMPT = f"""{TININ_BASE}

Hoy también te toca: te paso una lista de productos de un mismo Excel de gestión (su nombre \
crudo del sistema y, si ya la tiene, su descripción actual de cartel), y tenés que encontrar \
grupos de 2 o más que sean VARIANTES de la misma línea de producto -- mismo producto base y \
misma marca, difiriendo solo en peso/tamaño, sabor, tipo de envase, si es al agua o al aceite, \
cantidad de unidades, etc.

NO agrupes productos distintos aunque compartan una categoría general (ej. "atún" y \
"sardinas" NO van juntos aunque los dos sean pescado en lata; dos marcas distintas del mismo \
producto tampoco van juntas). Sé conservador: ante la duda, no agrupes -- es mejor dejar un \
producto sin agrupar que mezclarlo con otro que en realidad es distinto. Un grupo necesita \
como mínimo 2 productos.

EL PRECIO DECIDE TANTO COMO EL NOMBRE. Un grupo unificado imprime UN SOLO cartel: una \
descripción y un precio para todos sus SKU. Si dos productos no están exactamente al mismo \
precio, ese cartel miente para alguno de los dos, aunque sean la misma línea de producto. Te \
paso los precios de cada fila justamente para que puedas verlo.

Para poder agrupar dos productos tienen que coincidir TODOS estos, exactos:

- el precio regular (el tachado), hasta los centavos: $276,75 NO es $276
- el precio de oferta, hasta los centavos
- el precio de banco, si lo tienen
- el % off, la mecánica, el símbolo de moneda y el banco

Si alguno difiere, NO los agrupes y no lo propongas como grupo. Dos mermeladas de la misma \
marca, una a $369 y otra a $299, son dos carteles distintos: no es un grupo. Si de cuatro \
salsas de la misma línea tres están a un precio y la cuarta a otro, el grupo son esas TRES y \
la cuarta queda afuera -- y ojo, entonces la descripción tampoco puede nombrarla.

Mirá los centavos de verdad antes de decidir. La diferencia entre dos productos suele estar \
ahí y no en el número grande.

Para cada grupo que encuentres, redactá DOS O TRES descripciones de cartel ALTERNATIVAS que \
sirvan para todas las variantes de ese grupo, para que la persona elija cuál poner. No es \
elegir la mejor: son ángulos distintos, y cuál sirve depende de algo que vos NO podés saber.

Ese algo es: vos solo ves los productos que están EN OFERTA, no el surtido completo de la \
góndola. Así que "todas las variedades" puede ser MENTIRA. Si de cuatro modelos de bicicleta \
R20 hay dos en oferta y el cartel dice "todas las variedades", el cartel promete algo que no \
se cumple, y eso es lo peor que puede pasar en góndola. Por eso las opciones van ORDENADAS de \
la más segura a la más riesgosa, así:

1. ENUMERANDO lo que realmente vino, cuando entra en el largo permitido: "Cappuccino SAINT \
CAFÉ chocolate, tradicional y vainilla. 6 sobres". Nunca miente, porque nombra exactamente lo \
que está en oferta. Es la primera opción SIEMPRE que los nombres de las variantes quepan.
2. SIN prometer que están todas, mencionando la cantidad o dejándolo neutro: "Cappuccino SAINT \
CAFÉ en 3 variedades. 6 sobres", "Acondicionador ELVIVE variedades surtidas. 370 ml". Es la \
que sirve cuando son demasiadas para enumerar (7, 11, 20 productos) y el texto no entra.
3. "Todas las variedades" / "todas las presentaciones", como en "Acondicionador ELVIVE. Todas \
las variedades. 370 ml". Va SIEMPRE ÚLTIMA y solo como opción, porque es la única que afirma \
que el surtido está completo.

Si el grupo son 2 o 3 productos con nombres cortos, la opción 1 casi siempre entra y es la que \
va primera. Si son muchos, arrancá por la 2. Devolvé 2 o 3 opciones, nunca una sola.

Cada opción lleva además una `etiqueta` de 2 a 5 palabras que diga en qué se diferencia, para \
mostrarla en el desplegable donde se elige: "Nombra los 3 sabores", "Sin decir cuántas", "Dice \
que están todas".

Las tres siguen estas mismas reglas de estilo, y en las tres va el gramaje o la cantidad de \
unidades si se puede inferir (los "6 sobres", los "370 ml"):

{_STYLE_RULES}

Los productos que no formen parte de ningún grupo simplemente no aparecen en tu respuesta."""


def _build_unify_prompt(items: list[dict]) -> str:
    lineas = []
    for n, it in enumerate(items, start=1):
        partes = [f'nombre ERP: "{it["nombreArticulo"]}"']
        if it.get("descripcion"):
            partes.append(f'descripción actual: "{it["descripcion"]}"')
        # El precio va ya armado entero (ver _monto): partido en dos columnas
        # no se puede comparar de un vistazo, y comparar mal es agrupar mal.
        precios = _linea_precios(it)
        if precios:
            partes.append(precios)
        lineas.append(f"{n}. " + " | ".join(partes))
    listado = "\n".join(lineas)
    return (
        f"Encontrá grupos de variantes entre estos {len(items)} productos:\n\n{listado}\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"grupos": [{"filas": [1, 3], "grupo": '
        '"nombre corto de la línea de producto", "opciones": [{"texto": "descripción de cartel...", '
        '"etiqueta": "en qué se diferencia"}, ...]}, ...]} '
        '-- "filas" son los números de la lista de arriba (al menos 2 por grupo), y "opciones" '
        "son 2 o 3 descripciones alternativas ordenadas de la más segura a la más riesgosa. "
        "Sin comentarios ni texto fuera del JSON."
    )


async def detectar_grupos_unificables(items: list[dict], db, user_id: int) -> dict:
    """items: [{"row_id", "codigo", "nombreArticulo", "descripcion"}, ...] -- pensado
    para recibir TODAS las filas cargadas en la grilla (matcheadas o no), a diferencia
    de generar_descripciones que solo ve las que faltan: acá lo que importa es el nombre
    crudo, no si ya tiene descripción resuelta. Nunca escribe nada -- al aprobar un grupo
    puntual desde el modal, el frontend combina esas filas en una sola y persiste vía el
    mismo PATCH que ya usa la edición manual (ver ConvertidorGrid.tsx: commitUnificacion).

    Devuelve {"grupos": [{"row_ids", "skus", "grupo", "descripcion", "opciones"}, ...],
    "truncated": bool, "error": bool}. `opciones` son 2 o 3 redacciones alternativas
    ({"texto", "etiqueta"}) ordenadas de la mas segura a la mas riesgosa, para que la
    persona elija en el modal: Tinin solo ve los productos EN OFERTA, no el surtido
    completo, asi que "todas las variedades" puede ser mentira (ver _UNIFY_SYSTEM_PROMPT).
    `descripcion` es opciones[0]["texto"], la que el modal precarga.

    "error" distingue un fallo real de analisis (red caida, JSON que no
    parsea -- posiblemente cortado por quedarse sin max_tokens) de "Claude ya reviso todo
    y genuinamente no encontro grupos" -- sin esto, ambos casos se verian identicos para
    quien usa el modal (una lista vacia sin explicacion)."""
    procesables = [it for it in items if it["nombreArticulo"]]
    if len(procesables) < 2:
        return {"grupos": [], "truncated": False, "error": False}

    # Ordenar ANTES de partir es lo que hace que las tandas no rompan familias
    # (ver el comentario de _armar_tandas).
    procesables.sort(key=_clave_agrupado)
    truncated = len(procesables) > _UNIFY_ROWS_MAX * _UNIFY_TANDAS_MAX
    procesables = procesables[:_UNIFY_ROWS_MAX * _UNIFY_TANDAS_MAX]
    tandas = _armar_tandas(procesables)

    limite = asyncio.Semaphore(_UNIFY_CONCURRENCIA)

    async def _analizar(tanda: list[dict]):
        async with limite:
            # effort="low" NO es tacañería: es lo único que deja terminar el
            # JSON. El razonamiento sale del MISMO presupuesto que max_tokens, y
            # con un listado grande el modelo se lo gastaba entero pensando.
            # Medido contra producción el 07/09/2026 con el listado real de Gran
            # Bretaña, 150 productos, techo de 16.000:
            #
            #   sin effort   145 s   16000 de salida   stop=max_tokens   texto VACIO
            #   medium       134 s   16000 de salida   stop=max_tokens   JSON cortado
            #   low           89 s   12343 de salida   stop=end_turn     JSON entero
            #
            # O sea que el modal decía "No pudimos generar las sugerencias"
            # después de esperar dos minutos y medio, siempre. Ni "medium" --el
            # valor que usa el chat de La Triada-- alcanza: allá el output es
            # prosa corta, acá un JSON largo con un grupo por familia.
            content, in_tok, out_tok = await _ask_claude(
                _UNIFY_SYSTEM_PROMPT, _build_unify_prompt(tanda), max_tokens=16000, effort="low")
            parsed = json.loads(_strip_json_fence(content))
            crudos = parsed.get("grupos", [])
            if not isinstance(crudos, list):
                raise ValueError(f"'grupos' no es una lista: {crudos!r}")
            return crudos, in_tok, out_tok

    resultados = await asyncio.gather(*(_analizar(t) for t in tandas), return_exceptions=True)

    # Candidatos de TODAS las tandas, ya con los items resueltos. Los índices
    # que devuelve el modelo son locales a su tanda, así que se resuelven acá
    # mismo, mientras se sabe a qué tanda pertenecen.
    candidatos: list[dict] = []
    in_total = out_total = 0
    fallaron = 0
    for tanda, res in zip(tandas, resultados):
        if isinstance(res, BaseException):
            fallaron += 1
            log.warning("convertidor_ai.detectar_grupos_unificables: tanda fallida — %s", res)
            continue
        crudos, in_tok, out_tok = res
        in_total += in_tok
        out_total += out_tok
        for g in crudos:
            if not isinstance(g, dict):
                continue
            filas = g.get("filas")
            nombre = g.get("grupo")
            if not isinstance(filas, list) or not isinstance(nombre, str) or not nombre.strip():
                continue
            opciones = _parsear_opciones(g)
            if not opciones:
                continue
            vistos: set[int] = set()
            miembros = []
            for n in filas:
                if not (isinstance(n, int) and 1 <= n <= len(tanda)):
                    continue
                it = tanda[n - 1]
                if it["row_id"] in vistos:
                    continue
                vistos.add(it["row_id"])
                miembros.append(it)
            if len(miembros) >= 2:
                candidatos.append({"grupo": nombre.strip()[:150],
                                   "opciones": opciones, "miembros": miembros})

    if fallaron == len(tandas):
        return {"grupos": [], "truncated": truncated, "error": True}
    if fallaron:
        # Algo se analizó, pero no todo. Se avisa con la misma marca que el
        # recorte por tamaño: para quien mira la pantalla el efecto es el mismo,
        # pueden faltar grupos.
        truncated = True

    if in_total or out_total:
        await log_ai_usage(db, user_id, "convertidor_unificar_categorias",
                           *_ASK_CLAUDE_META, in_total, out_total)

    # Una fila no puede pertenecer a dos grupos a la vez -- si dos tandas la
    # reclaman (por el solape) o el modelo la repite dentro de una, gana el
    # grupo MÁS GRANDE: es el que vio la familia más completa. Antes ganaba el
    # primero del listado, que con tandas solapadas podía ser el pedazo que
    # quedó cortado justo en el borde.
    candidatos.sort(key=lambda c: len(c["miembros"]), reverse=True)
    grupos: list[dict] = []
    usadas: set[int] = set()
    for c in candidatos:
        miembros = [m for m in c["miembros"] if m["row_id"] not in usadas]
        if len(miembros) < 2:
            continue
        usadas.update(m["row_id"] for m in miembros)
        grupos.append({
            "row_ids": [m["row_id"] for m in miembros],
            "skus": [m["codigo"] for m in miembros],
            "grupo": c["grupo"],
            # La primera es la que Tinín puso primera, o sea la más segura (ver
            # _UNIFY_SYSTEM_PROMPT). Se manda aparte y no solo dentro de
            # `opciones` porque es la que el modal precarga y la que viaja al
            # PATCH si nadie toca el desplegable.
            "descripcion": c["opciones"][0]["texto"],
            "opciones": c["opciones"],
        })

    return {"grupos": grupos, "truncated": truncated, "error": False}


# ---------------------------------------------------------------------------
# El precio, como lo tiene que LEER Tinín
# ---------------------------------------------------------------------------
#
# En toda la plataforma el precio viaja partido en dos columnas: el entero en
# `precioOferta` y la parte decimal en `decimalPrecioOferta`. Mostrarle a
# Tinín las dos columnas por separado es pedirle que se equivoque -- leyendo
# solo la entera, $276,75 y $276 son el mismo número, que es exactamente el
# falso positivo que se quiere evitar.
#
# Así que se le arma el precio ya entero antes de mostrárselo. Tinín trabaja
# con un número por precio, escrito como lo lee una persona.

_RE_SOLO_DIGITOS = re.compile(r"^\d+$")


def _monto(entero, decimal) -> str:
    """El precio completo, a partir de sus dos columnas: ``"1.124"`` + ``",75"``
    -> ``"1.124,75"``.

    El punto de la columna entera es separador de MILES (1.124 = mil ciento
    veinticuatro), así que se conserva tal cual. La columna decimal vacía es
    ",00" y se escribe: es la diferencia entre $276,75 y $276, y si no se
    escribe, no se puede ver.

    Un valor que no es un número (una mecánica escrita en la celda, "2x1") se
    devuelve tal cual: no es un precio, pero es lo que hay en esa fila y Tinín
    tiene que verlo igual.
    """
    txt = str(entero or "").strip()
    if not txt:
        return ""
    limpio = txt.replace(".", "").replace(" ", "")
    if not _RE_SOLO_DIGITOS.fullmatch(limpio):
        return txt
    dec = str(decimal or "").strip().lstrip(",.").strip()
    dec = dec if dec.isdigit() else ""
    return f"{txt},{(dec or '0').ljust(2, '0')[:2]}"


def _linea_precios(it: dict) -> str:
    """Los precios y condiciones de una fila, en una línea legible.

    Solo lo que está: una fila sin precio de banco no arrastra un "banco: —"
    que ocupa lugar en el prompt y no dice nada.
    """
    moneda = str(it.get("unidadMoneda") or "").strip()
    def _con_moneda(valor: str) -> str:
        return f"{moneda}{valor}" if moneda and valor else valor

    partes = []
    for etiqueta, entero, decimal in (
        ("regular", "precioRegular", "decimalPrecioRegular"),
        ("oferta",  "precioOferta",  "decimalPrecioOferta"),
        ("banco",   "precioBanco",   "decimalPrecioBanco"),
    ):
        valor = _monto(it.get(entero), it.get(decimal))
        if valor:
            partes.append(f"{etiqueta} {_con_moneda(valor)}")
    for etiqueta, campo in (("% off", "ofertaUno"), ("banco", "banco"),
                            ("mecánica", "mecanica")):
        valor = str(it.get(campo) or "").strip()
        if valor:
            partes.append(f"{etiqueta}: {valor}")
    return " | ".join(partes)


# Etiqueta de fallback cuando Claude manda una opción sin `etiqueta`: el
# desplegable necesita algo para mostrar y "" dejaría una fila en blanco.
_ETIQUETA_POR_DEFECTO = "Otra redacción"


def _parsear_opciones(g: dict) -> list[dict]:
    """Las descripciones alternativas de un grupo, en el orden que las mandó Claude.

    Tolera la forma vieja (un solo campo `descripcion` de texto) además de la
    nueva (`opciones`). No es paranoia: si el modelo ignora el esquema nuevo y
    contesta como antes, sin esto se descartarían TODOS los grupos y la pantalla
    diría "no encontré nada para unificar", que es la peor forma de fallar --
    parece un resultado legítimo. Con esto degrada a una sola opción, que es
    exactamente lo que había antes de este cambio."""
    crudas = g.get("opciones")
    if not isinstance(crudas, list):
        vieja = g.get("descripcion")
        crudas = [{"texto": vieja}] if isinstance(vieja, str) else []

    opciones: list[dict] = []
    vistos: set[str] = set()
    for o in crudas:
        if isinstance(o, str):
            o = {"texto": o}          # una opción mandada como string pelado
        if not isinstance(o, dict):
            continue
        texto = o.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            continue
        texto = texto.strip()[:300]
        if texto.lower() in vistos:   # dos ángulos que quedaron iguales: una sola fila
            continue
        vistos.add(texto.lower())
        etiqueta = o.get("etiqueta")
        etiqueta = etiqueta.strip()[:60] if isinstance(etiqueta, str) and etiqueta.strip() else _ETIQUETA_POR_DEFECTO
        opciones.append({"texto": texto, "etiqueta": etiqueta})
        if len(opciones) == _UNIFY_MAX_OPCIONES:
            break
    return opciones


# ---------------------------------------------------------------------------
# Detección de columnas de fechaInicio/fechaFin sin alias reconocido
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

_VALID_DATE_FIELDS = {"fechaInicio", "fechaFin"}

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
        '{"clasificaciones": {"1": "fechaInicio"|"fechaFin"|null, ...}} '
        "— una entrada por cada número de la lista, en el mismo orden. Sin comentarios ni texto fuera del JSON."
    )


async def resolve_date_columns_with_ai(candidates: list[dict], db, user_id: int) -> dict[str, str | None]:
    """candidates: [{"header_norm", "header_display", "muestras": [str, ...]}, ...] —
    encabezados sin match en _INPUT_ALIASES ni en el cache aprendido
    (ConvertidorHeaderAlias), ya filtrados para que "muestras" tenga al menos
    un par de valores que parsean como fecha real (ver convertidor.py).

    Devuelve {header_norm: "fechaInicio"|"fechaFin"|None} con UNA entrada
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

# ---------------------------------------------------------------------------
# Columnas que el sistema no reconocio: que campo QUISO poner quien las escribio
# ---------------------------------------------------------------------------
#
# Agregar un alias a mano cada vez que gestion inventa un nombre nuevo es una
# carrera que se pierde: ya pasaron "NOMBRE DE ARTICULO" (con "de"),
# "DESCRIPCIONES WEB" (plural), "precioRegular"/"precioOferta" (los nombres
# canonicos usados como entrada). Cada listado nuevo trae otra variante y la
# columna se ignora EN SILENCIO -- el sintoma tipico es la generacion con IA
# devolviendo "no pudimos generar" para todas las filas porque llegaron sin
# nombre de articulo.
#
# Esto lo da vuelta: en vez de que el sistema adivine solo, Tinin mira las
# columnas que quedaron sin reconocer --el nombre Y los valores-- y PROPONE a
# que campo corresponden. La persona confirma, y la confirmacion se guarda en
# ConvertidorHeaderAlias: ese header nunca vuelve a pasar por IA.
#
# Se le pasan los VALORES a proposito, no solo el nombre. Es la mitad de la
# senal: una columna llamada "oferta" cuyos valores son todos numeros con coma
# no es el titular de una oferta, es un precio; una llamada "regular" con
# numeros mas altos que la de al lado es el precio anterior.
#
# NUNCA aplica nada por su cuenta -- devuelve sugerencias para confirmar. Misma
# regla que la base de conocimiento: nada se activa solo.

# Que campos se le pueden proponer, con la explicacion que ve Tinin. Es el
# vocabulario de ENTRADA (ver _INPUT_ALIASES en convertidor.py), no las
# variables de la cenefa: lo que se mapea es la columna del Excel de gestion.
_CAMPOS_SUGERIBLES: dict[str, str] = {
    "codigo":            "el codigo de articulo / SKU",
    "nombreArticulo":   "el nombre del producto tal como lo escribe el sistema de gestion",
    "descripcionExcel": "una descripcion de cartel ya redactada a mano",
    "descripcionWeb":   "la descripcion larga del producto para la web",
    "moneda":            "el simbolo de moneda ($ o U$S)",
    "precioAnterior":   "el precio regular / anterior, el que se tacha",
    "precio":            "el precio de la oferta, el vigente",
    "oferta":            "el literal de la mecanica ('6x4', '2x$299', '20%OFF')",
    "ofertaDet":        "el TIPO de mecanica ('M x N', 'Combo', 'Precio fijo', '% descuento')",
    "comprador":         "el rubro o sector del producto (CARNICERIA, BEBIDAS...)",
    "fechaInicio":      "la fecha en que arranca la vigencia",
    "fechaFin":         "la fecha en que termina la vigencia",
}

_SUGERIR_SYSTEM_PROMPT = f"""{TININ_BASE}

Hoy también te toca: te paso encabezados de columna de un Excel de gestión que el sistema NO \
reconoció por nombre, cada uno con valores de ejemplo de esa misma columna. Para cada uno tenés \
que decidir a qué campo del sistema corresponde, o null si no corresponde a ninguno.

Los campos posibles son exactamente estos:
{chr(10).join(f'- {k}: {v}' for k, v in _CAMPOS_SUGERIBLES.items())}

Mirá el nombre Y los valores, las dos cosas. Los valores son la mitad de la señal: una columna \
llamada "oferta" cuyos valores son todos números con coma no es el literal de una mecánica, es \
un precio; una llamada "regular" con números más altos que otra es el precio anterior.

Sé conservador: ante la duda, null. Es mejor dejar una columna sin reconocer que mapearla mal — \
un precio en el campo equivocado sale impreso en un cartel de góndola. La persona va a confirmar \
cada propuesta antes de que se aplique, así que tu trabajo es proponer con criterio y explicar por \
qué, no acertar a toda costa."""


def _build_sugerir_prompt(candidatos: list[dict], ya_resueltos: list[str] | None = None) -> str:
    lineas = []
    for n, c in enumerate(candidatos, start=1):
        muestras = ", ".join(f'"{m}"' for m in c["muestras"][:6]) or "(sin valores)"
        lineas.append(f'{n}. Encabezado: "{c["header_display"]}" — valores: {muestras}')
    # Los campos que OTRA columna del mismo archivo ya resuelve. Sin decirle
    # esto, Tinin propone campos ya tomados: en una prueba real mapeo
    # "SUBCATEGORIA" -> comprador en un archivo que YA traia la columna
    # COMPRADOR. Confirmar eso aprende un alias que pisa una columna de verdad,
    # y queda aprendido para siempre.
    tomados = ""
    if ya_resueltos:
        tomados = (
            "\n\nOJO: en este mismo archivo hay otras columnas que YA resuelven estos campos: "
            + ", ".join(sorted(ya_resueltos))
            + ". No propongas ninguno de esos -- si una columna se le parece pero el campo ya "
              "está tomado, la respuesta correcta es null."
        )
    return (
        f"Clasificá estos {len(candidatos)} encabezados:\n\n" + "\n".join(lineas) + tomados + "\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"columnas": {"1": {"campo": "<uno de la '
        'lista>|null", "motivo": "una frase corta explicando por qué"}, ...}} — una entrada por '
        "cada número, en el mismo orden. Sin comentarios ni texto fuera del JSON."
    )


def _campo_o_ninguno(valor) -> str | None:
    """"No es ninguno" puede llegar de varias formas y todas significan lo mismo.

    El prompt pide `null` y a veces vuelve el STRING "null" (o "none", o vacio).
    Sin esto la ruta lo tomaba como un nombre de campo, no lo encontraba en
    _CAMPOS_SUGERIBLES y descartaba la sugerencia con un error -- justo en el
    caso que MAS conviene confirmar, porque un "no es ninguno" guardado es lo
    que hace que esa columna no se vuelva a preguntar nunca.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto.lower() in ("", "null", "none", "ninguno", "ninguna", "n/a", "-"):
        return None
    return texto


async def sugerir_campos_de_columnas(
    candidatos: list[dict], db, user_id: int, ya_resueltos: list[str] | None = None,
) -> dict:
    """candidatos: [{"header_norm", "header_display", "muestras": [str, ...]}, ...]

    `ya_resueltos` son los campos que otras columnas del MISMO archivo ya
    resuelven. Se le dicen a Tinin para que no proponga uno tomado.

    Devuelve {"sugerencias": [{header_norm, header_display, campo, motivo}, ...],
              "errores": [str, ...]}.

    `campo` es None cuando Tinin decidio que la columna no corresponde a ningun
    campo conocido -- se devuelve igual, porque confirmar un "no es ninguno"
    tambien sirve: se cachea y no se vuelve a preguntar.

    No escribe en ConvertidorHeaderAlias: eso pasa cuando la persona confirma
    (ver la ruta /columnas/confirmar-alias). Nada se aplica solo.
    """
    if not candidatos:
        return {"sugerencias": [], "errores": []}

    recorte = candidatos[:_ROWS_MAX_PER_REQUEST]
    errores: list[str] = []
    try:
        content, in_tok, out_tok = await _ask_claude(
            _SUGERIR_SYSTEM_PROMPT, _build_sugerir_prompt(recorte, ya_resueltos), max_tokens=2000)
        await log_ai_usage(db, user_id, "convertidor_columnas", *_ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content)).get("columnas", {})
    except Exception as exc:
        log.warning("sugerir_campos_de_columnas: %s", exc, exc_info=True)
        return {"sugerencias": [], "errores": [f"{type(exc).__name__}: {exc}"]}

    sugerencias = []
    for n, c in enumerate(recorte, start=1):
        item = parsed.get(str(n)) or {}
        campo = _campo_o_ninguno(item.get("campo"))
        # Cinturon ademas del tirante: si igual propuso un campo que otra
        # columna ya resuelve, se baja a "no es ninguno" en vez de dejar que
        # alguien lo confirme sin darse cuenta.
        if campo is not None and campo in (ya_resueltos or []):
            errores.append(
                f'"{c["header_display"]}": {campo} ya lo resuelve otra columna de este archivo')
            campo = None
        if campo is not None and campo not in _CAMPOS_SUGERIBLES:
            errores.append(f'Tinin propuso un campo que no existe para "{c["header_display"]}": {campo!r}')
            continue
        sugerencias.append({
            "header_norm":    c["header_norm"],
            "header_display": c["header_display"],
            # Los valores de ejemplo viajan de vuelta: en la pantalla son lo que
            # permite decidir si la propuesta esta bien cuando el nombre de la
            # columna no dice nada ("COMENTARIOS2").
            "muestras":       c.get("muestras") or [],
            "campo":          campo,
            "motivo":         str(item.get("motivo") or "")[:300],
        })
    return {"sugerencias": sugerencias, "errores": errores}

# ---------------------------------------------------------------------------
# Bebidas con alcohol que no se nombran por tipo
# ---------------------------------------------------------------------------
#
# `es_alcohol()` (variables.py) reconoce el TIPO en el texto: "cerveza",
# "whisky", "fernet". Eso cubre la enorme mayoria, porque el nombre de gestion
# casi siempre lo dice. Pero no cubre lo que se vende por nombre de fantasia
# --un "Cerro Paisa" suelto, un "Aperol Spritz"-- y la leyenda es OBLIGATORIA:
# un cartel de gondola sin ella es una infraccion.
#
# Aca entra Tinin, y solo para lo que el detector por tipo NO reconocio. No se
# le vuelve a preguntar por una cerveza: eso ya esta resuelto por codigo, gratis
# y sin margen de error.
#
# Devuelve SUGERENCIAS. La leyenda no se agrega sola: se propone y una persona
# confirma, igual que las descripciones. La diferencia con el resto es hacia
# donde conviene errar -- aca de mas: una leyenda que sobra no hace dano, una
# que falta es la infraccion. El prompt lo dice explicito.

_ALCOHOL_SYSTEM_PROMPT = f"""{TININ_BASE}

Hoy también te toca: te paso productos de un listado de supermercado y tenés que decir, para \
cada uno, si es una BEBIDA CON ALCOHOL.

Importa porque una cenefa de bebida alcohólica lleva por ley la leyenda "Beber con moderación. \
Prohibida la venta de bebidas alcohólicas a menores de 18 años", y si falta es una infracción.

Estos productos YA fueron descartados por un chequeo que busca el tipo de bebida en el nombre \
("cerveza", "vino", "whisky", "fernet", "vodka", "gin", "ron", "licor", "champagne", "sidra", \
"grappa", "tequila"...). O sea que lo que buscás es lo que ese chequeo no puede ver: bebidas que \
se venden por NOMBRE DE FANTASÍA sin decir de qué son. Por ejemplo un vino o una caña que se \
llama solo por su marca.

Ante la duda, decí que SÍ es alcohol. Una leyenda que sobra no le hace daño a nadie; una que \
falta es una infracción. Pero no la pongas en cosas que claramente no son bebidas: un jabón, un \
kilo de carne o un papel higiénico no llevan leyenda por más raro que sea el nombre."""


def _build_alcohol_prompt(items: list[dict]) -> str:
    lineas = []
    for n, it in enumerate(items, start=1):
        partes = [p for p in (it.get("descripcion"), it.get("nombreArticulo")) if p]
        lineas.append(f'{n}. {" | ".join(partes) or "(sin nombre)"}')
    return (
        f"¿Cuáles de estos {len(items)} productos son bebidas con alcohol?\n\n"
        + "\n".join(lineas) + "\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"alcohol": {"1": {"es": true|false, '
        '"motivo": "una frase corta"}, ...}} — una entrada por cada número, en el mismo orden. '
        "Sin comentarios ni texto fuera del JSON."
    )


async def detectar_alcohol(items: list[dict], db, user_id: int) -> dict:
    """items: [{"row_id", "codigo", "descripcion", "nombreArticulo"}, ...] — ya
    filtrados por el caller para dejar solo los que `es_alcohol()` NO reconocio.

    Devuelve {"alcohol": [{row_id, codigo, texto, motivo}, ...], "errores": [...]}
    con SOLO los que Tinin marco como bebida alcoholica. No agrega la leyenda:
    eso lo hace la persona al confirmar.
    """
    procesables = [it for it in items if (it.get("descripcion") or it.get("nombreArticulo"))]
    if not procesables:
        return {"alcohol": [], "errores": []}

    encontrados: list[dict] = []
    errores: list[str] = []
    for chunk in _chunks(procesables, _CHUNK_SIZE):
        try:
            content, in_tok, out_tok = await _ask_claude(
                _ALCOHOL_SYSTEM_PROMPT, _build_alcohol_prompt(chunk), max_tokens=2000)
            await log_ai_usage(db, user_id, "convertidor_alcohol", *_ASK_CLAUDE_META, in_tok, out_tok)
            parsed = json.loads(_strip_json_fence(content)).get("alcohol", {})
        except Exception as exc:
            log.warning("detectar_alcohol: chunk de %d fallo -- %s", len(chunk), exc, exc_info=True)
            _sumar_error(errores, f"{type(exc).__name__}: {exc}")
            continue
        for n, it in enumerate(chunk, start=1):
            item = parsed.get(str(n)) or {}
            if item.get("es") is True:
                encontrados.append({
                    "row_id": it["row_id"],
                    "codigo": it.get("codigo", ""),
                    "texto":  it.get("descripcion") or it.get("nombreArticulo") or "",
                    "motivo": str(item.get("motivo") or "")[:300],
                })
    return {"alcohol": encontrados, "errores": errores}

# ---------------------------------------------------------------------------
# Mecánicas que el motor no reconoce
# ---------------------------------------------------------------------------
#
# El Convertidor deduce la familia de mecánica del texto de OFERTADET. Cuando
# gestión inventa un tipo nuevo, `familia_de_ofertadet` devuelve None: la fila
# pierde la mecánica ENTERA --sin cocarda, sin "Comprando N", sin unidad-- y lo
# único que queda es el aviso `ofertadet_desconocido` en la grilla.
#
# Y vuelve todas las semanas, porque es el mismo listado de gestión: hoy alguien
# lo arregla a mano y el lunes siguiente está igual.
#
# Acá Tinín mira ese OFERTADET junto con lo que trae la columna OFERTA en las
# filas que lo usan --que es lo que de verdad lo explica: "3x2" se lee distinto
# de "Precio Oferta"-- y dice a qué familia corresponde.
#
# Devuelve SUGERENCIAS. No escribe en cenefa_ofertadet_aliases: eso pasa cuando
# la persona confirma (ver /mecanica/confirmar-alias). Nada se aplica solo,
# porque elegir mal la familia no deja la cenefa vacía: la deja MINTIENDO. Un
# "2x1" resuelto como Combo imprime un precio unitario que no existe.

_FAMILIAS_EXPLICADAS: dict[str, str] = {
    "combo":        'se lleva N unidades por un precio TOTAL ("3x$99" = tres por 99 los tres). '
                    "El precio del cartel es el unitario, que sale de dividir",
    "mxn":          'se lleva M y paga N ("2x1", "6x4"). El literal va en la cocarda y el precio '
                    "del cartel es el unitario que ya viene calculado en la columna PRECIO",
    "segunda":      'la segunda (o tercera) unidad tiene un descuento ("2da unidad al 50%")',
    "sin_mecanica": "no anuncia nada: es un precio y punto (precio fijo, % de descuento, "
                    "una etiqueta interna de gestión). NO lleva cocarda",
}

_MECANICA_SYSTEM_PROMPT = f"""{TININ_BASE}

Hoy también te toca: te paso un tipo de oferta (la columna OFERTADET del listado de gestión) que el sistema NO reconoce, junto con ejemplos de lo que trae la columna OFERTA en las filas que lo usan. Tenés que decir a qué FAMILIA de mecánica corresponde.

Las familias son cuatro y solo cuatro:

{chr(10).join(f'- {k}: {v}' for k, v in _FAMILIAS_EXPLICADAS.items())}

Fijate sobre todo en los ejemplos de OFERTA, que es lo que de verdad lo explica: un "3x2" es otra cosa que un "Precio Oferta". El nombre del tipo ayuda pero a veces es jerga interna que no dice nada.

Si no te queda claro, decí "sin_mecanica": es la opción que no inventa nada. Elegir mal una de las otras tres no deja el cartel vacío, lo deja MINTIENDO -- un "2x1" resuelto como combo imprime un precio unitario que no existe, y eso sale impreso a la góndola."""


def _build_mecanica_prompt(items: list[dict]) -> str:
    lineas = []
    for n, it in enumerate(items, start=1):
        ejemplos = " | ".join(it.get("ejemplos_oferta") or []) or "(la columna OFERTA viene vacía)"
        lineas.append(f'{n}. OFERTADET: "{it["ofertadet_display"]}"  ->  OFERTA dice: {ejemplos}')
    return (
        f"¿Qué familia de mecánica es cada uno de estos {len(items)} tipos?\n\n"
        + "\n".join(lineas) + "\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"mecanicas": {"1": {"familia": "combo|mxn|'
        'segunda|sin_mecanica", "motivo": "una frase corta"}, ...}} — una entrada por cada número. '
        "Sin comentarios ni texto fuera del JSON."
    )


async def sugerir_familia_mecanica(candidatos: list[dict], db, user_id: int) -> dict:
    """candidatos: [{"ofertadet_norm", "ofertadet_display", "ejemplos_oferta"}, ...]

    Devuelve {"sugerencias": [{ofertadet_norm, ofertadet_display, familia,
    motivo}, ...], "errores": [...]}. Una familia que no existe se descarta con
    un error a la vista en vez de viajar a la pantalla: es la única respuesta
    que no se puede confirmar.
    """
    if not candidatos:
        return {"sugerencias": [], "errores": []}

    recorte = candidatos[:_ROWS_MAX_PER_REQUEST]
    errores: list[str] = []
    try:
        content, in_tok, out_tok = await _ask_claude(
            _MECANICA_SYSTEM_PROMPT, _build_mecanica_prompt(recorte), max_tokens=2000)
        await log_ai_usage(db, user_id, "convertidor_mecanica", *_ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content)).get("mecanicas", {})
    except Exception as exc:
        log.warning("sugerir_familia_mecanica: %s", exc, exc_info=True)
        return {"sugerencias": [], "errores": [f"{type(exc).__name__}: {exc}"]}

    sugerencias = []
    for n, c in enumerate(recorte, start=1):
        item = parsed.get(str(n)) or {}
        familia = item.get("familia")
        if familia not in FAMILIAS_MECANICA:
            errores.append(
                f'Tinin propuso una familia que no existe para "{c["ofertadet_display"]}": {familia!r}')
            continue
        sugerencias.append({
            "ofertadet_norm":    c["ofertadet_norm"],
            "ofertadet_display": c["ofertadet_display"],
            "familia":           familia,
            "motivo":            str(item.get("motivo") or "")[:300],
        })
    return {"sugerencias": sugerencias, "errores": errores}
