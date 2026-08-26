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
from app.services.cenefas.convertidor_variables import FAMILIAS_MECANICA

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

    Devuelve {"suggestions": [...], "failed_row_ids": [...], "errores": [...]}. Nunca
    levanta por un chunk que falla — ese chunk se reporta en failed_row_ids y el resto de
    la respuesta sigue siendo utilizable (fail-soft, mismo criterio que _afinar_seleccion
    en dona_tina_precios.py): un fallo transitorio de red en un chunk no debería tirar
    abajo las sugerencias que ya se generaron en los demás.

    `errores` lleva el MOTIVO de cada fallo, sin repetir. Antes la excepción moría en un
    log del servidor y a la persona le llegaba "completalos a mano" sin causa: no había
    forma de distinguir una key vencida de un JSON cortado ni de un producto que no tenía
    con qué generar. Ahora el motivo llega a la pantalla."""
    # Sin nombre_articulo NI descripcion_web no hay nada que pedirle a Claude —
    # se descarta antes de gastar un slot del batch.
    procesables = [it for it in items if it["nombre_articulo"] or it["descripcion_web"]]
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
# A diferencia de generar_descripciones, acá NO se trocea en chunks: agrupar
# necesita ver todos los productos en una sola pasada, porque dos miembros
# del mismo grupo podrían caer en chunks distintos y nunca detectarse como
# relacionados. Por eso hay un tope duro de filas por request (_UNIFY_ROWS_MAX)
# en vez de un tamaño de lote.

_UNIFY_ROWS_MAX = 150  # tope duro por request síncrona -- mismo criterio que
                       # _ROWS_MAX_PER_REQUEST (sin jobs asíncronos acá).

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

Para cada grupo que encuentres, redactá UNA sola descripción de cartel que sirva para todas \
las variantes de ese grupo -- mencioná algo como "en todas sus variedades" o "todas las \
presentaciones" en vez de listar cada variante por separado -- siguiendo estas mismas reglas \
de estilo:

{_STYLE_RULES}

Los productos que no formen parte de ningún grupo simplemente no aparecen en tu respuesta."""


def _build_unify_prompt(items: list[dict]) -> str:
    lineas = []
    for n, it in enumerate(items, start=1):
        partes = [f'nombre ERP: "{it["nombre_articulo"]}"']
        if it.get("descripcion"):
            partes.append(f'descripción actual: "{it["descripcion"]}"')
        lineas.append(f"{n}. " + " | ".join(partes))
    listado = "\n".join(lineas)
    return (
        f"Encontrá grupos de variantes entre estos {len(items)} productos:\n\n{listado}\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"grupos": [{"filas": [1, 3], "grupo": '
        '"nombre corto de la línea de producto", "descripcion": "texto de cartel unificado..."}, ...]} '
        '-- "filas" son los números de la lista de arriba (al menos 2 por grupo). '
        "Sin comentarios ni texto fuera del JSON."
    )


async def detectar_grupos_unificables(items: list[dict], db, user_id: int) -> dict:
    """items: [{"row_id", "codigo", "nombre_articulo", "descripcion"}, ...] -- pensado
    para recibir TODAS las filas cargadas en la grilla (matcheadas o no), a diferencia
    de generar_descripciones que solo ve las que faltan: acá lo que importa es el nombre
    crudo, no si ya tiene descripción resuelta. Nunca escribe nada -- al aprobar un grupo
    puntual desde el modal, el frontend combina esas filas en una sola y persiste vía el
    mismo PATCH que ya usa la edición manual (ver ConvertidorGrid.tsx: commitUnificacion).

    Devuelve {"grupos": [{"row_ids", "skus", "grupo", "descripcion"}, ...], "truncated": bool,
    "error": bool}. "error" distingue un fallo real de analisis (red caida, JSON que no
    parsea -- posiblemente cortado por quedarse sin max_tokens) de "Claude ya reviso todo
    y genuinamente no encontro grupos" -- sin esto, ambos casos se verian identicos para
    quien usa el modal (una lista vacia sin explicacion)."""
    procesables = [it for it in items if it["nombre_articulo"]]
    truncated = len(procesables) > _UNIFY_ROWS_MAX
    procesables = procesables[:_UNIFY_ROWS_MAX]
    if len(procesables) < 2:
        return {"grupos": [], "truncated": truncated, "error": False}

    try:
        prompt = _build_unify_prompt(procesables)
        # max_tokens generoso a propósito: a diferencia de generar_descripciones (que
        # trocea en chunks de a 20 porque cada item es independiente), acá TODOS los
        # productos van en un solo pedido -- con muchas variantes chicas (2-3 miembros)
        # la cantidad de grupos puede ser alta, y cada uno carga su propio array de
        # filas + nombre + descripción completa. Preferible pagar de más por un output
        # grande que arriesgar un corte a mitad del JSON.
        content, in_tok, out_tok = await _ask_claude(_UNIFY_SYSTEM_PROMPT, prompt, max_tokens=4096)
        await log_ai_usage(db, user_id, "convertidor_unificar_categorias", *_ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content))
        grupos_raw = parsed.get("grupos", [])
        if not isinstance(grupos_raw, list):
            raise ValueError(f"'grupos' no es una lista: {grupos_raw!r}")
    except Exception as exc:
        log.warning("convertidor_ai.detectar_grupos_unificables: fallo — %s", exc)
        return {"grupos": [], "truncated": truncated, "error": True}

    # Una fila no puede pertenecer a dos grupos a la vez -- si Claude la repite
    # (alucinación o solapamiento en su respuesta), se queda con el primer
    # grupo que la reclamó y se descarta de cualquier grupo posterior, en vez
    # de dejar que un mismo SKU termine con dos descripciones "unificadas"
    # distintas según qué grupo se apruebe último.
    grupos: list[dict] = []
    usadas: set[int] = set()
    for g in grupos_raw:
        if not isinstance(g, dict):
            continue
        filas = g.get("filas")
        grupo_nombre = g.get("grupo")
        descripcion = g.get("descripcion")
        if not isinstance(filas, list) or not isinstance(grupo_nombre, str) or not isinstance(descripcion, str):
            continue
        if not grupo_nombre.strip() or not descripcion.strip():
            continue

        # Se arma la lista de candidatos SIN todavía marcarlos como usados --
        # si el grupo termina descartado (menos de 2 miembros válidos), sus
        # filas tienen que seguir disponibles para el próximo grupo del
        # listado. Recién se marca "usadas" una vez confirmado que el grupo
        # entero es válido (ver abajo).
        candidatas: list[int] = []
        for n in filas:
            if isinstance(n, int) and 1 <= n <= len(procesables) and n not in usadas and n not in candidatas:
                candidatas.append(n)
        if len(candidatas) < 2:
            continue

        usadas.update(candidatas)
        miembros = [procesables[n - 1] for n in candidatas]
        grupos.append({
            "row_ids": [m["row_id"] for m in miembros],
            "skus": [m["codigo"] for m in miembros],
            "grupo": grupo_nombre.strip()[:150],
            "descripcion": descripcion.strip()[:300],
        })

    return {"grupos": grupos, "truncated": truncated}


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
    "nombre_articulo":   "el nombre del producto tal como lo escribe el sistema de gestion",
    "descripcion_excel": "una descripcion de cartel ya redactada a mano",
    "descripcion_web":   "la descripcion larga del producto para la web",
    "moneda":            "el simbolo de moneda ($ o U$S)",
    "precio_anterior":   "el precio regular / anterior, el que se tacha",
    "precio":            "el precio de la oferta, el vigente",
    "oferta":            "el literal de la mecanica ('6x4', '2x$299', '20%OFF')",
    "oferta_det":        "el TIPO de mecanica ('M x N', 'Combo', 'Precio fijo', '% descuento')",
    "comprador":         "el rubro o sector del producto (CARNICERIA, BEBIDAS...)",
    "fecha_inicio":      "la fecha en que arranca la vigencia",
    "fecha_fin":         "la fecha en que termina la vigencia",
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


def _build_sugerir_prompt(candidatos: list[dict]) -> str:
    lineas = []
    for n, c in enumerate(candidatos, start=1):
        muestras = ", ".join(f'"{m}"' for m in c["muestras"][:6]) or "(sin valores)"
        lineas.append(f'{n}. Encabezado: "{c["header_display"]}" — valores: {muestras}')
    return (
        f"Clasificá estos {len(candidatos)} encabezados:\n\n" + "\n".join(lineas) + "\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"columnas": {"1": {"campo": "<uno de la '
        'lista>|null", "motivo": "una frase corta explicando por qué"}, ...}} — una entrada por '
        "cada número, en el mismo orden. Sin comentarios ni texto fuera del JSON."
    )


async def sugerir_campos_de_columnas(candidatos: list[dict], db, user_id: int) -> dict:
    """candidatos: [{"header_norm", "header_display", "muestras": [str, ...]}, ...]

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
            _SUGERIR_SYSTEM_PROMPT, _build_sugerir_prompt(recorte), max_tokens=2000)
        await log_ai_usage(db, user_id, "convertidor_columnas", *_ASK_CLAUDE_META, in_tok, out_tok)
        parsed = json.loads(_strip_json_fence(content)).get("columnas", {})
    except Exception as exc:
        log.warning("sugerir_campos_de_columnas: %s", exc, exc_info=True)
        return {"sugerencias": [], "errores": [f"{type(exc).__name__}: {exc}"]}

    sugerencias = []
    for n, c in enumerate(recorte, start=1):
        item = parsed.get(str(n)) or {}
        campo = item.get("campo")
        if campo is not None and campo not in _CAMPOS_SUGERIBLES:
            errores.append(f'Tinin propuso un campo que no existe para "{c["header_display"]}": {campo!r}')
            continue
        sugerencias.append({
            "header_norm":    c["header_norm"],
            "header_display": c["header_display"],
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
        partes = [p for p in (it.get("descripcion"), it.get("nombre_articulo")) if p]
        lineas.append(f'{n}. {" | ".join(partes) or "(sin nombre)"}')
    return (
        f"¿Cuáles de estos {len(items)} productos son bebidas con alcohol?\n\n"
        + "\n".join(lineas) + "\n\n"
        'Devolvé SOLO un JSON con esta forma exacta: {"alcohol": {"1": {"es": true|false, '
        '"motivo": "una frase corta"}, ...}} — una entrada por cada número, en el mismo orden. '
        "Sin comentarios ni texto fuera del JSON."
    )


async def detectar_alcohol(items: list[dict], db, user_id: int) -> dict:
    """items: [{"row_id", "codigo", "descripcion", "nombre_articulo"}, ...] — ya
    filtrados por el caller para dejar solo los que `es_alcohol()` NO reconocio.

    Devuelve {"alcohol": [{row_id, codigo, texto, motivo}, ...], "errores": [...]}
    con SOLO los que Tinin marco como bebida alcoholica. No agrega la leyenda:
    eso lo hace la persona al confirmar.
    """
    procesables = [it for it in items if (it.get("descripcion") or it.get("nombre_articulo"))]
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
                    "texto":  it.get("descripcion") or it.get("nombre_articulo") or "",
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
