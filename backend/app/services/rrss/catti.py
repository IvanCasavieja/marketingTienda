"""CatTi lee el mailing original y las placas de redes sociales, y devuelve lo
que VE, literal. No decide si algo está bien o mal: eso lo hace comparador.py
con código. Un precio tiene que ser exactamente igual al del mailing, y una
opinión del modelo ("me parece que coincide") no es una comparación.

Por eso cada lado se lee POR SEPARADO y a ciegas: al leer una placa el modelo
no ve el mailing, y al revés. Si viera los dos, tendería a "corregir" la
placa hacia lo que dice el mailing y el error que hay que encontrar
desaparecería en la lectura, antes de compararlo.

Mismo patrón que facturacion/extraccion.py: tool forzada (respuesta siempre
estructurada, nunca texto libre) y las funciones no tocan la base; devuelven
los tokens para que el llamador decida cuándo y cómo loguear el uso.
"""
import asyncio
import unicodedata

import anthropic

from app.core.config import settings
from app.services.rrss import imagenes
from app.services.tino_personas import CATTI_BASE

_MODEL = settings.MODELO_IA  # el de toda la familia -- ver MODELO_IA en config.py
FEATURE = "rrss_catti"
PROVEEDOR = "anthropic"

_LADO_LARGO_MODELO = 1568  # más que esto el API lo achica igual
_ANCHO_TIRA = 1568

_CAJA = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 4,
    "maxItems": 4,
    "description": (
        "Caja [x0, y0, x1, y1] con valores entre 0 y 1: fracción del ancho y del alto de la "
        "PRIMERA imagen (x hacia la derecha, y hacia abajo). Ajustada al elemento, sin sobrar mucho."
    ),
}

_LITERAL = (
    "Transcripción LITERAL: respetá mayúsculas y minúsculas ('kg' no es 'Kg'), los espacios "
    "('100g' no es '100 g'), puntos, comas, tildes y símbolos ('$', 'U$S', 'US$'). No corrijas, no "
    "completes, no normalices. Los números van EXACTAMENTE como están impresos: no agregues separador de "
    "miles ('$1090' no es '$1.090') ni espacios entre el símbolo y el número ('U$S79' no es 'U$S 79'). "
    "No transcribas adornos gráficos (viñetas o puntos rojos, líneas, íconos). Los saltos de renglón se "
    "unen con un espacio. Cadena vacía si no existe."
)

_PROPIEDADES_PRODUCTO = {
    "descripcion": {
        "type": "string",
        "description": (
            "Todo el texto del producto que NO es precio: tipo, marca, variedades y presentación "
            "(ej. 'Cerveza STELLA ARTOIS. Lata 710 ml'). Sin la línea del precio. " + _LITERAL
        ),
    },
    "precio_anterior": {
        "type": "string",
        "description": (
            "La línea de precio que está debajo de la descripción, con lo que la acompaña en ESA "
            "misma línea, tal cual: '$499', '$340 unidad', '$48 unidad', 'US$149'. " + _LITERAL
        ),
    },
    "precio_anterior_tachado": {
        "type": "boolean",
        "description": "true si esa línea de precio está tachada (cruzada por una línea).",
    },
    "mecanica": {
        "type": "string",
        "description": (
            "El rótulo de la mecánica, si lo hay: '2x$75', '4x3 Combinables', '2x1'. "
            "NO es el círculo del precio. " + _LITERAL
        ),
    },
    "oferta_encabezado": {
        "type": "string",
        "description": "Texto chico arriba del precio en el círculo: 'Oferta' o 'Comprando 2'. " + _LITERAL,
    },
    "oferta_precio": {
        "type": "string",
        "description": (
            "El precio grande del círculo con su símbolo. Si los centavos van chicos arriba, "
            "pegalos con coma: '$37,50'. " + _LITERAL
        ),
    },
    "oferta_pie": {
        "type": "string",
        "description": "Texto chico debajo del precio en el círculo: 'unidad', o vacío. " + _LITERAL,
    },
    "es_alcohol": {
        "type": "boolean",
        "description": "true si el producto es una bebida alcohólica (cerveza, vino, whisky, etc.).",
    },
}
_REQUERIDOS_PRODUCTO = [
    "descripcion", "precio_anterior", "precio_anterior_tachado", "mecanica",
    "oferta_encabezado", "oferta_precio", "oferta_pie", "es_alcohol",
]

_TOOL_MAILING = {
    "name": "registrar_pagina_del_mailing",
    "description": "Registra lo que hay en UNA página del mailing original: cada producto con su precio, y los datos de la campaña.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fecha": {"type": "string", "description": "El texto de vigencia de la campaña ('DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE'). " + _LITERAL},
            "legal_alcohol": {"type": "string", "description": "La leyenda de alcohol ('Beber con moderación...'), si está en esta página. " + _LITERAL},
            "productos": {
                "type": "array",
                "description": "Cada producto de la página, UNA sola vez, con su precio. No incluyas el encabezado ni los banners sin precio de producto.",
                "items": {
                    "type": "object",
                    "properties": _PROPIEDADES_PRODUCTO,
                    "required": _REQUERIDOS_PRODUCTO,
                },
            },
        },
        "required": ["fecha", "legal_alcohol", "productos"],
    },
}

_TOOL_PLACA = {
    "name": "registrar_placa",
    "description": "Registra lo que hay en UNA placa de redes sociales: el producto con su precio y los elementos fijos de la placa.",
    "input_schema": {
        "type": "object",
        "properties": {
            "producto": {
                "type": "object",
                "properties": _PROPIEDADES_PRODUCTO,
                "required": _REQUERIDOS_PRODUCTO,
            },
            "fecha": {"type": "string", "description": "El texto de vigencia de la campaña. " + _LITERAL},
            "logo_campana_presente": {"type": "boolean", "description": "true si está el logo de la campaña (ej. 'Los Rompe del finde')."},
            "isotipo_presente": {"type": "boolean", "description": "true si está el isotipo/logo de la tienda (ej. el asterisco de Tienda Inglesa)."},
            "legal_bases": {"type": "string", "description": "La leyenda de bases y condiciones ('Bases y condiciones en ...'). " + _LITERAL},
            "legal_alcohol": {"type": "string", "description": "La leyenda de alcohol ('Beber con moderación...'). " + _LITERAL},
            "cta": {"type": "string", "description": "El texto de un botón o llamado a la acción ('Comprar', 'Ver más'), si hay. " + _LITERAL},
            "otros_textos": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Cualquier otro texto visible que NO sea nada de lo anterior. Lista vacía si no hay.",
            },
            "imagen_producto": {
                "type": "object",
                "properties": {
                    "presente": {"type": "boolean", "description": "true si hay una foto del producto."},
                    "que_se_ve": {"type": "string", "description": "Qué producto muestra la foto, en pocas palabras."},
                    "coincide_con_descripcion": {"type": "boolean", "description": "true si la foto es razonablemente del producto que dice la descripción."},
                    "motivo": {"type": "string", "description": "Solo si no coincide: por qué."},
                },
                "required": ["presente", "que_se_ve", "coincide_con_descripcion", "motivo"],
            },
        },
        "required": [
            "producto", "fecha", "logo_campana_presente", "isotipo_presente",
            "legal_bases", "legal_alcohol", "cta", "otros_textos", "imagen_producto",
        ],
    },
}

_INSTRUCCION_MAILING = """
Te paso UNA página del mailing original de una campaña de supermercado, para
que registres cada producto con la tool registrar_pagina_del_mailing.

Vas a recibir tres imágenes de la MISMA página: la primera es la página
completa; las otras dos son su mitad de arriba y su mitad de abajo, ampliadas
para que puedas leer la letra chica. Un producto puede verse en el solape de
las dos mitades: registralo UNA sola vez.

Cómo está armado un producto: una foto, un texto de descripción al costado
(con un precio tachado abajo), y un círculo rojo con 'Oferta' y el precio. Si
hay una mecánica (2x$75, 4x3, 2x1) aparece en un rótulo aparte y el círculo
dice 'Comprando N' arriba y 'unidad' abajo. Cada campo de la tool explica qué
va en él.

Lo que importa acá es la EXACTITUD de cada carácter: lo que registres se va a
comparar contra la placa de una red social, y una diferencia de una coma o de
una mayúscula tiene que salir a la luz, no quedar corregida por vos. No
registres banners que no son un producto con precio.
""".strip()

_INSTRUCCION_PLACA = """
Te paso UNA placa de redes sociales de una campaña de supermercado, para que
registres lo que tiene con la tool registrar_placa.

Vas a recibir dos imágenes de la MISMA placa: la primera es la placa
completa; la segunda es solo su franja inferior, ampliada, para que puedas
leer los textos legales.

La placa tiene un producto (foto, descripción, y un círculo rojo con el precio
de oferta) y elementos fijos (fecha de la campaña, logo, isotipo de la
tienda, leyendas legales al pie). Cada campo de la tool explica qué va en él.

Lo que importa acá es la EXACTITUD de cada carácter: lo que registres se va a
comparar contra el mailing original y una diferencia de una coma, un espacio
o una mayúscula tiene que salir a la luz. No corrijas nada ni lo completes
con lo que "debería" decir: registrá lo que está impreso. Si un elemento no
está en la placa, dejalo vacío o en false — nunca lo supongas.
""".strip()

_TOOL_CAJAS = {
    "name": "registrar_cajas",
    "description": "Registra dónde está cada elemento pedido, como una caja sobre la imagen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "elementos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "El id del elemento, tal cual se pidió."},
                        "caja": {
                            **_CAJA,
                            "description": (
                                "[x0, y0, x1, y1] como fracción (0 a 1) del ancho y del alto de la imagen: "
                                "esquina superior izquierda y esquina inferior derecha. Leela contra la grilla."
                            ),
                        },
                    },
                    "required": ["id", "caja"],
                },
            },
        },
        "required": ["elementos"],
    },
}

_INSTRUCCION_CAJAS = """
Te paso una imagen con una GRILLA superpuesta: líneas magenta cada 0.1 (las
más finas son cada 0.05), con su valor escrito en los bordes y en el medio.
Es una herramienta de medición: el contenido de la imagen es lo que está
debajo de la grilla.

Para cada elemento de la lista devolvé, con la tool registrar_cajas, la caja
[x0, y0, x1, y1] que lo contiene, leyendo las coordenadas contra la grilla.
La caja tiene que dejar TODO el elemento adentro — ni una letra cortada — y
sobrar poco. Si un elemento no aparece en la imagen, omitilo de la respuesta.
""".strip()

_SISTEMA = [{
    "type": "text",
    "text": CATTI_BASE,
    "cache_control": {"type": "ephemeral"},
}]


class LecturaFallida(RuntimeError):
    """El modelo no devolvió una lectura utilizable -- mensaje apto para el usuario."""


# Adornos gráficos que el modelo a veces transcribe como si fueran texto: los
# puntos rojos de "• DE SETIEMBRE •" están en la placa Y en el mailing, pero un
# día los lee y otro no, y eso aparecía como una diferencia de fecha en casi
# todas las placas. No son texto: se sacan siempre.
_ADORNOS = dict.fromkeys(map(ord, "•●·▪◦■□◆◇★☆"), " ")


def limpiar_texto(valor) -> str:
    """Texto de una lectura: NFC, sin adornos gráficos, y los saltos de
    renglón/espacios múltiples llevados a un solo espacio. Es lo ÚNICO que se
    normaliza: el resto de la comparación es estricto, y un renglón que se corta
    distinto en la placa que en el mailing no es una diferencia de contenido."""
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFC", str(valor)).translate(_ADORNOS)
    return " ".join(texto.split())


def _producto(raw: dict) -> dict:
    raw = raw or {}
    return {
        "descripcion": limpiar_texto(raw.get("descripcion")),
        "precio_anterior": limpiar_texto(raw.get("precio_anterior")),
        "precio_anterior_tachado": bool(raw.get("precio_anterior_tachado")),
        "mecanica": limpiar_texto(raw.get("mecanica")),
        "oferta_encabezado": limpiar_texto(raw.get("oferta_encabezado")),
        "oferta_precio": limpiar_texto(raw.get("oferta_precio")),
        "oferta_pie": limpiar_texto(raw.get("oferta_pie")),
        "es_alcohol": bool(raw.get("es_alcohol")),
        "cajas": {},  # las llena localizar_*: la lectura no mide coordenadas
    }


def normalizar_pagina_mailing(raw: dict, pagina: int) -> dict:
    """`pagina` es el número de página (0-based) donde se leyó cada producto."""
    productos = []
    for p in raw.get("productos") or []:
        prod = _producto(p)
        if not prod["descripcion"] and not prod["oferta_precio"]:
            continue  # ni texto ni precio: no es un producto
        prod["pagina"] = pagina
        productos.append(prod)
    return {
        "fecha": limpiar_texto(raw.get("fecha")),
        "legal_alcohol": limpiar_texto(raw.get("legal_alcohol")),
        "pagina": pagina,
        "productos": productos,
    }


def normalizar_placa(raw: dict) -> dict:
    img = raw.get("imagen_producto") or {}
    otros = [limpiar_texto(t) for t in (raw.get("otros_textos") or [])]
    return {
        "producto": _producto(raw.get("producto")),
        "fecha": limpiar_texto(raw.get("fecha")),
        "logo_campana_presente": bool(raw.get("logo_campana_presente")),
        "isotipo_presente": bool(raw.get("isotipo_presente")),
        "legal_bases": limpiar_texto(raw.get("legal_bases")),
        "legal_alcohol": limpiar_texto(raw.get("legal_alcohol")),
        "cta": limpiar_texto(raw.get("cta")),
        "otros_textos": [t for t in otros if t],
        "imagen_producto": {
            "presente": bool(img.get("presente")),
            "que_se_ve": limpiar_texto(img.get("que_se_ve")),
            "coincide_con_descripcion": bool(img.get("coincide_con_descripcion", True)),
            "motivo": limpiar_texto(img.get("motivo")),
        },
        "cajas": {},
    }


def _bloque_imagen(im) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": imagenes.base64_jpeg(im)},
    }


async def _llamar(tool: dict, instruccion: str, imgs: list, texto: str, max_tokens: int) -> tuple[dict, int, int]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=4, timeout=180.0)
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=[*_SISTEMA, {"type": "text", "text": instruccion}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{
            "role": "user",
            "content": [*[_bloque_imagen(i) for i in imgs], {"type": "text", "text": texto}],
        }],
    )
    if response.stop_reason == "max_tokens":
        raise LecturaFallida("La lectura quedó cortada: hay demasiado contenido para leer de una vez")
    bloque = next((b for b in response.content if b.type == "tool_use"), None)
    if bloque is None:
        raise LecturaFallida("CatTi no pudo leer la imagen")

    u = response.usage
    # Con caché, input_tokens deja de traer el prompt fijo: lo leído del caché
    # viaja aparte. Se suman los tres (mismo criterio que tinin_agent.py) para
    # que el informe de consumo no muestre una caída que no ocurrió.
    entrada = (
        (u.input_tokens or 0)
        + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        + (getattr(u, "cache_read_input_tokens", 0) or 0)
    )
    return bloque.input, entrada, u.output_tokens or 0


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------

async def leer_pagina_mailing(pagina_img, indice: int) -> tuple[dict, int, int]:
    """Lee UNA página del mailing. Devuelve (lectura normalizada, tokens_in, tokens_out)."""
    completa = imagenes.reducir(pagina_img, _LADO_LARGO_MODELO)
    mitades = [
        imagenes.ajustar_ancho(m, _ANCHO_TIRA) for m, _, _ in imagenes.mitades_con_solape(pagina_img)
    ]
    raw, t_in, t_out = await _llamar(
        _TOOL_MAILING, _INSTRUCCION_MAILING, [completa, *mitades],
        f"Registrá la página {indice + 1} del mailing.", max_tokens=8000,
    )
    return normalizar_pagina_mailing(raw, indice), t_in, t_out


async def leer_mailing(paginas: list) -> tuple[dict, int, int]:
    """Lee todas las páginas en paralelo y las junta en un solo mailing:
    {"fecha", "fecha_pagina", "legal_alcohol", "legal_alcohol_pagina", "productos": [...]}.
    Los datos de campaña (fecha, leyenda de alcohol) los toma de la primera
    página que los traiga."""
    lecturas = await asyncio.gather(*(leer_pagina_mailing(p, i) for i, p in enumerate(paginas)))
    mailing = {
        "fecha": "", "fecha_pagina": None, "fecha_caja": None,
        "legal_alcohol": "", "legal_alcohol_pagina": None, "legal_alcohol_caja": None,
        "productos": [],
    }
    t_in = t_out = 0
    for lectura, ti, to in lecturas:
        t_in += ti
        t_out += to
        if lectura["fecha"] and not mailing["fecha"]:
            mailing.update(fecha=lectura["fecha"], fecha_pagina=lectura["pagina"])
        if lectura["legal_alcohol"] and not mailing["legal_alcohol"]:
            mailing.update(legal_alcohol=lectura["legal_alcohol"], legal_alcohol_pagina=lectura["pagina"])
        mailing["productos"].extend(lectura["productos"])
    if not mailing["productos"]:
        raise LecturaFallida("No encontré ningún producto con precio en el mailing")
    return mailing, t_in, t_out


async def leer_placa(placa_img) -> tuple[dict, int, int]:
    """Lee UNA placa. Devuelve (lectura normalizada, tokens_in, tokens_out)."""
    completa = imagenes.reducir(placa_img, _LADO_LARGO_MODELO)
    tira = imagenes.ajustar_ancho(imagenes.tira_inferior(placa_img), _ANCHO_TIRA)
    raw, t_in, t_out = await _llamar(
        _TOOL_PLACA, _INSTRUCCION_PLACA, [completa, tira], "Registrá esta placa.", max_tokens=3000,
    )
    return normalizar_placa(raw), t_in, t_out


# --------------------------------------------------------------------------
# Localización: dónde está cada cosa (para poder mostrar recortes)
# --------------------------------------------------------------------------

def _bandas(alto_sobre_ancho: float) -> list[tuple[float, float]]:
    """Franjas horizontales (y0, y1, como fracción del alto) en las que partir
    una imagen para localizar cosas. Una imagen cuadrada va entera; una alta
    (página del mailing, placa 9:16) se parte en franjas que se solapan, cada
    una más o menos cuadrada. El modelo mide bien coordenadas sobre una
    imagen chica y mal sobre una alta: en una página entera las cajas se
    corrían y varios productos ni aparecían."""
    if alto_sobre_ancho <= 1.05:
        return [(0.0, 1.0)]
    f = min(1.0, 0.75 / alto_sobre_ancho)  # alto de cada franja
    paso = f * 0.65                        # el resto es solape
    bandas, y0 = [], 0.0
    while y0 + f < 1.0 - 1e-6:
        bandas.append((y0, y0 + f))
        y0 += paso
    bandas.append((1.0 - f, 1.0))
    return bandas


def _elegir_candidata(candidatas: list[tuple[list[float], float, bool, bool]]) -> list[float]:
    """De las cajas que salieron de distintas franjas para un mismo elemento,
    la de la franja donde quedó más lejos de un borde de corte: ahí es donde
    el elemento se ve entero. Cada candidata es (caja_en_la_página,
    margen_al_corte, ...); el margen ya viene calculado."""
    return max(candidatas, key=lambda c: c[1])[0]


async def localizar(im, pedidos: list[tuple[str, str]]) -> tuple[dict, int, int]:
    """Ubica cada elemento de `pedidos` [(id, qué es)] sobre `im`, con una
    grilla rotulada encima. Devuelve ({id: caja}, tokens_in, tokens_out).

    Va aparte de la lectura a propósito: pedirle al modelo que transcriba
    LITERAL y además mida coordenadas en la misma respuesta empeoraba las dos
    cosas. La lectura de texto queda sobre la imagen limpia; las coordenadas
    se miden sobre franjas con grilla (ver _bandas)."""
    if not pedidos:
        return {}, 0, 0
    lista = "\n".join(f"- {id_}: {que}" for id_, que in pedidos)
    validos = {p[0] for p in pedidos}
    bandas = _bandas(im.height / im.width)

    async def por_banda(y0: float, y1: float):
        franja = im.crop((0, int(y0 * im.height), im.width, int(y1 * im.height)))
        franja = imagenes.reducir(franja, _LADO_LARGO_MODELO)
        texto = f"Ubicá estos elementos:\n{lista}"
        if len(bandas) > 1:
            texto += (
                "\n\nEsta imagen es solo una franja de una imagen más grande: puede mostrar un elemento "
                "cortado en el borde de arriba o de abajo. Ubicá únicamente los elementos que se ven "
                "COMPLETOS acá; los cortados omitilos (se van a ubicar en otra franja)."
            )
        raw, ti, to = await _llamar(
            _TOOL_CAJAS, _INSTRUCCION_CAJAS, [imagenes.con_grilla(franja)], texto, max_tokens=3000,
        )
        return raw, ti, to, y0, y1

    resultados = await asyncio.gather(*(por_banda(y0, y1) for y0, y1 in bandas))
    t_in = t_out = 0
    candidatas: dict[str, list] = {}
    for raw, ti, to, y0, y1 in resultados:
        t_in += ti
        t_out += to
        for e in raw.get("elementos") or []:
            caja = imagenes.caja_valida(e.get("caja"))
            if caja is None or e.get("id") not in validos:
                continue
            bx0, by0, bx1, by1 = caja
            # de la franja a la imagen entera
            pagina = [bx0, y0 + by0 * (y1 - y0), bx1, y0 + by1 * (y1 - y0)]
            # margen a los bordes de la franja que son cortes (no los de la imagen)
            margen = 1.0
            if y0 > 0:
                margen = min(margen, by0)
            if y1 < 1:
                margen = min(margen, 1 - by1)
            candidatas.setdefault(e["id"], []).append((pagina, margen, True, True))
    cajas = {id_: _elegir_candidata(c) for id_, c in candidatas.items()}
    return cajas, t_in, t_out


def _pedidos_producto(prefijo: str, prod: dict) -> list[tuple[str, str]]:
    desc = prod["descripcion"] or prod["oferta_precio"]
    pedidos = [
        (f"{prefijo}producto", f"el producto completo «{desc}» (foto, descripción y círculo del precio)"),
        (f"{prefijo}descripcion", f"el bloque de texto de «{desc}», incluida la línea del precio tachado que va debajo"),
        (f"{prefijo}oferta", f"el círculo del precio de oferta ({prod['oferta_precio']}) de «{desc}»"),
    ]
    if prod["mecanica"]:
        pedidos.append((f"{prefijo}mecanica", f"el rótulo de la mecánica «{prod['mecanica']}» de «{desc}»"))
    return pedidos


async def localizar_mailing(paginas: list, mailing: dict) -> tuple[int, int]:
    """Completa `cajas` de cada producto (y de la fecha y la leyenda de alcohol)
    con una llamada por página. Modifica `mailing` en el lugar."""
    async def por_pagina(indice: int, pagina_img):
        pedidos: list[tuple[str, str]] = []
        for i, prod in enumerate(mailing["productos"]):
            if prod["pagina"] == indice:
                pedidos += _pedidos_producto(f"p{i}.", prod)
        if mailing["fecha_pagina"] == indice:
            pedidos.append(("fecha", f"el texto de vigencia «{mailing['fecha']}»"))
        if mailing["legal_alcohol_pagina"] == indice:
            pedidos.append(("legal_alcohol", f"la leyenda «{mailing['legal_alcohol']}»"))
        return await localizar(pagina_img, pedidos)

    resultados = await asyncio.gather(*(por_pagina(i, p) for i, p in enumerate(paginas)))
    t_in = t_out = 0
    for cajas, ti, to in resultados:
        t_in += ti
        t_out += to
        for id_, caja in cajas.items():
            if id_ == "fecha":
                mailing["fecha_caja"] = caja
            elif id_ == "legal_alcohol":
                mailing["legal_alcohol_caja"] = caja
            else:
                prefijo, clave = id_[1:].split(".", 1)
                mailing["productos"][int(prefijo)]["cajas"][clave] = caja
    return t_in, t_out


async def localizar_placa(placa_img, lectura: dict) -> tuple[dict, int, int]:
    """Cajas de lo que se ve en una placa. Solo se llama cuando la placa tiene
    diferencias: el recorte es para mostrarlas, no para validar."""
    prod = lectura["producto"]
    pedidos = _pedidos_producto("", prod) + [
        ("fecha", f"el texto de vigencia «{lectura['fecha']}»"),
        ("legales", "las leyendas legales del pie de la placa"),
        ("imagen", "la foto del producto"),
    ]
    return await localizar(placa_img, pedidos)
