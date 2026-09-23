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
import logging
import unicodedata
from dataclasses import dataclass

import anthropic

from app.core.config import settings
from app.services.rrss import imagenes
from app.services.rrss.hilos import en_hilo
from app.services.rrss.planilla import CAMPOS_DE_LA_PLANILLA
from app.services.tino_personas import CATTI_BASE

logger = logging.getLogger(__name__)

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

# En dos de tres lecturas reales del mismo mailing la Jarra INHAUS salió con un
# dígito de más ('$7799' por '$799') o con un punto de miles que no está
# impreso ('$1.090' por '$1090'). Se le dice explícito: cada dígito una vez.
_DIGITOS = (
    "Los dígitos van UNA sola vez y en el orden impreso: si dudás entre dos cifras no dupliques "
    "ninguna ('$799' no es '$7799'). "
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
            "misma línea, tal cual: '$499', '$340 unidad', '$48 unidad', 'US$149'. " + _DIGITOS + _LITERAL
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
            "pegalos con coma: '$37,50'. " + _DIGITOS + _LITERAL
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
                "description": (
                    "Cualquier otro texto visible que NO sea nada de lo anterior. NO incluyas el texto que "
                    "forma parte del logo de la campaña ('Los Rompe del finde') ni el nombre de la tienda: "
                    "esos van en logo_campana_presente / isotipo_presente. Lista vacía si no hay."
                ),
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

_TOOL_PRODUCTO = {
    "name": "registrar_producto_del_mailing",
    "description": "Registra UN producto del mailing original, tal cual está impreso, a partir de su recorte.",
    "input_schema": {
        "type": "object",
        "properties": _PROPIEDADES_PRODUCTO,
        "required": _REQUERIDOS_PRODUCTO,
    },
}

_INSTRUCCION_PRODUCTO = """
Te paso el recorte de UN producto del mailing original de una campaña de
supermercado, ampliado, para que lo registres con la tool
registrar_producto_del_mailing.

Cómo está armado: una foto, un texto de descripción al costado (con un precio
tachado abajo), y un círculo rojo con 'Oferta' y el precio. Si hay una mecánica
(2x$75, 4x3, 2x1) aparece en un rótulo aparte y el círculo dice 'Comprando N'
arriba y 'unidad' abajo. Cada campo de la tool explica qué va en él. Si en el
borde del recorte asoma parte de OTRO producto, ignoralo.

Lo que importa es la EXACTITUD de cada carácter y de cada dígito: este recorte
se lee para confirmar una lectura anterior de la página entera, así que no
supongas nada; registrá lo que está impreso.
""".strip()

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

# --------------------------------------------------------------------------
# La imposición: CatTi mira la hoja y dice cómo está armada
# --------------------------------------------------------------------------
# Un mailing se disena en carillas verticales pero se entrega IMPUESTO: una
# hoja del PDF puede traer una carilla, dos al lado, tres... Mirarlo por
# proporciones (imagenes.carillas_en) acierta en lo que se usa, pero da por
# sentado que las columnas son iguales y que el corte es vertical. Preguntarle
# a CatTi saca esa suposicion: ve la hoja y dice donde empieza y termina cada
# carilla. Si la lectura falla, se vuelve a las proporciones.
_TOOL_IMPOSICION = {
    "name": "registrar_imposicion",
    "description": "Registra en cuántas carillas está dividida la hoja y dónde está cada una.",
    "input_schema": {
        "type": "object",
        "properties": {
            "carillas": {
                "type": "array",
                "description": (
                    "Una entrada por carilla, en orden de lectura: de izquierda a derecha y, "
                    "si hubiera dos hileras, después de arriba a abajo. Si la hoja es UNA sola "
                    "carilla, devolvé una entrada que cubra la hoja entera."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "caja": {
                            **_CAJA,
                            "description": (
                                "[x0, y0, x1, y1] como fracción (0 a 1) del ancho y del alto de la hoja. "
                                "Leelas contra la grilla. La caja tiene que dejar la carilla ENTERA adentro "
                                "-- ni un producto cortado -- y no invadir la de al lado."
                            ),
                        },
                    },
                    "required": ["caja"],
                },
            },
        },
        "required": ["carillas"],
    },
}

_INSTRUCCION_IMPOSICION = """
Te paso UNA hoja de un mailing de supermercado, con una GRILLA magenta
superpuesta para que puedas leer coordenadas en vez de estimarlas: líneas cada
0.1, las finas cada 0.05, con su valor escrito en los bordes y en el medio. El
contenido de la hoja es lo que está debajo de la grilla.

Los mailings se diseñan en CARILLAS (páginas verticales) pero se imprimen
impuestos: una hoja puede traer una carilla sola, dos al lado, tres, o dos
arriba y dos abajo. Cada carilla es una página completa y se reconoce porque
tiene sus propios elementos de página: el logo de la tienda, el encabezado de
su campaña, su vigencia ("Del 23 al 30 de setiembre"), y a veces su pie. Dos
carillas están separadas por un pliegue, un margen blanco o un corte de fondo.

Lo que NO es una carilla: un bloque de productos dentro de una misma página
(aunque tenga su propio título de sección), una columna de la grilla de
productos, ni una franja de legales.

Devolvé con la tool registrar_imposicion una caja por carilla. Si la hoja es
una sola página, devolvé UNA caja que la cubra entera: preferí una de menos
antes que partir una página por el medio.
""".strip()


async def imposicion_de_la_hoja(hoja) -> tuple[list[list[float]], int, int]:
    """Las cajas de cada carilla de una hoja. Lista vacía si no pudo."""
    bloques = await en_hilo(
        lambda: [_bloque_imagen(imagenes.reducir(imagenes.con_grilla(hoja), _LADO_LARGO_MODELO))])
    raw, t_in, t_out = await _llamar(
        _TOOL_IMPOSICION, _INSTRUCCION_IMPOSICION, bloques,
        "Decime cómo está armada esta hoja.", max_tokens=1000,
    )
    cajas = []
    for c in (raw.get("carillas") or []):
        caja = c.get("caja")
        if isinstance(caja, (list, tuple)) and len(caja) == 4:
            cajas.append([float(v) for v in caja])
    return cajas, t_in, t_out


async def imposicion_del_mailing(hojas: list) -> tuple[list[list[list[float]]], int, int]:
    """Una lista de cajas por hoja. Devuelve [] si alguna falla: el llamador
    vuelve al corte por proporciones, que nunca depende de la red."""
    try:
        lecturas = await asyncio.gather(*(imposicion_de_la_hoja(h) for h in hojas))
    except Exception as exc:  # noqa: BLE001 -- cualquier falla cae al plan B
        logger.warning("imposicion: no se pudo leer, se corta por proporciones -- %s", exc)
        return [], 0, 0
    cortes = [c for c, _, _ in lecturas]
    t_in = sum(ti for _, ti, _ in lecturas)
    t_out = sum(to for _, _, to in lecturas)
    if any(not c for c in cortes):
        logger.warning("imposicion: una hoja quedó sin carillas, se corta por proporciones")
        return [], t_in, t_out
    return cortes, t_in, t_out


# --------------------------------------------------------------------------
# La planilla: CatTi decide qué es cada columna
# --------------------------------------------------------------------------
# Ver el comentario de CAMPOS_DE_LA_PLANILLA en planilla.py: la planilla puede
# venir de cualquier forma, y qué columna es cada dato lo razona CatTi en el
# momento, mirando los títulos Y los valores. Lo que devuelve son COORDENADAS
# (hoja, fila de títulos, letra de columna), no datos: los valores se copian de
# las celdas tal cual, así una planilla sigue siendo dato exacto.
_COLUMNA = (
    " Contestá con la LETRA de la columna como la muestra la tabla ('B', 'F'), o cadena vacía si "
    "la planilla no trae ese dato. Nunca pongas una columna que en realidad trae otra cosa: un dato "
    "que falta se reporta como que falta, uno equivocado acusa a una placa que está bien."
)
_DATOS_DE_LA_PLANILLA = {
    "descripcion": (
        "EL DATO QUE NO PUEDE FALTAR. La columna con el nombre del producto como va impreso en la placa: "
        "tipo, marca y presentación ('Arvejas TIENDA INGLESA. 300 g', 'Cerveza BUDWEISER. 710 ml'). Puede "
        "llamarse de cualquier forma: DESCRIPCIÓN, NOMBRE ARTÍCULO, PRODUCTO, ARTÍCULO, DETALLE, o no tener "
        "título. Si hay dos candidatas --un nombre corto de sistema en MAYÚSCULAS y abreviado ('ARVEJAS TI "
        "300G') y otra con minúsculas, puntos y espacios-- elegí la que se parece a lo que va impreso."
    ),
    "precio_anterior": (
        "El precio de antes, el que en la placa aparece tachado: el MAYOR de los dos precios de la fila. "
        "Puede llamarse PRECIOANT, PRECIO ANTERIOR, PVP REGULAR, PRECIO LISTA, ANTES, o de otra forma."
    ),
    "precio_oferta": (
        "El precio de oferta, el grande del círculo: el MENOR de los dos. Si la fila trae una mecánica como "
        "'2x$75', este es el precio POR UNIDAD de esa mecánica (37,5), no el del combo."
    ),
    "moneda": "La columna que dice la moneda ('$', 'U$S'), si viene aparte del precio.",
    "mecanica": (
        "La mecánica de la oferta, si la hay: '2x$75', '4x3', '2x1', '3x2 combinables'. Suele estar vacía en "
        "la mayoría de las filas. Puede venir en una columna que se llama OFERTA, PROMO, MECÁNICA, "
        "ACCIÓN... Mirá los VALORES, no solo el título: una columna OFERTA que trae '2x$75' es la "
        "mecánica, no el precio."
    ),
    "arriba_del_precio": (
        "El texto chico que va arriba del precio en el círculo ('Oferta', 'Comprando 2'), SOLO si una "
        "columna lo trae escrito tal cual. No lo deduzcas de la mecánica."
    ),
    "abajo_del_precio": (
        "El texto chico que va debajo del precio en el círculo ('unidad', 'c/u', 'el kg'), SOLO si una "
        "columna lo trae escrito tal cual. No lo deduzcas."
    ),
    "vigencia": (
        "La fecha de la campaña ESCRITA como va en la placa ('DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE'). "
        "Una columna de fechas sueltas (FECHA INICIO, 17/09/2026) NO es esto: dejalo vacío."
    ),
    "leyenda_alcohol": "La leyenda de alcohol ('Beber con moderación...'), si una columna la trae.",
    "sucursal": (
        "Si la planilla repite cada producto una vez por sucursal (el mismo producto en varias filas, una "
        "por local), la columna con el nombre de la sucursal. Vacío si cada producto aparece una vez."
    ),
    "stock": "El stock por sucursal, si lo hay.",
    "codigo": "El código o SKU del artículo, si lo hay.",
}
# La lista de datos vive en planilla.py (CAMPOS_DE_LA_PLANILLA): si alguien
# agrega uno allá y no le escribe acá cómo reconocerlo, esto no arranca.
assert set(_DATOS_DE_LA_PLANILLA) == set(CAMPOS_DE_LA_PLANILLA), (
    "catti._DATOS_DE_LA_PLANILLA y planilla.CAMPOS_DE_LA_PLANILLA tienen que traer los mismos datos"
)

_TOOL_COLUMNAS = {
    "name": "registrar_columnas_de_la_planilla",
    "description": "Registra en qué hoja, en qué fila de títulos y en qué columna de la planilla está cada dato del producto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hoja": {
                "type": "string",
                "description": (
                    "El nombre EXACTO de la hoja que tiene los productos de la campaña, copiado de la tabla. "
                    "Cadena vacía si es un CSV."
                ),
            },
            "fila_encabezados": {
                "type": "integer",
                "description": (
                    "El número de fila (el de la tabla, como lo muestra Excel) donde están los títulos de "
                    "las columnas. 0 si la planilla no tiene títulos y los productos arrancan directo."
                ),
            },
            "columnas": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v + _COLUMNA} for k, v in _DATOS_DE_LA_PLANILLA.items()},
                "required": list(_DATOS_DE_LA_PLANILLA),
            },
            "explicacion": {
                "type": "string",
                "description": (
                    "En una o dos frases, en castellano rioplatense y sin tecnicismos, cómo leíste la planilla: "
                    "dónde está cada cosa. Se le muestra a la persona que subió el archivo."
                ),
            },
            "dudas": {
                "type": "string",
                "description": (
                    "Si una columna podía ser dos cosas y tuviste que elegir, o si algo del archivo no lo "
                    "entendiste, decilo acá en una frase. Cadena vacía si no hubo dudas."
                ),
            },
        },
        "required": ["hoja", "fila_encabezados", "columnas", "explicacion", "dudas"],
    },
}

_INSTRUCCION_COLUMNAS = """
Te paso una planilla con el listado de productos de una campaña de
supermercado, en texto: cada hoja con su número de fila (como lo muestra Excel)
y la letra de cada columna. De las planillas largas vas a ver el principio y el
final.

Con esa planilla se van a validar las placas de redes sociales de la campaña:
cada placa muestra un producto (descripción, precio tachado, precio de oferta,
a veces una mecánica como '2x$75') y se compara contra su fila. Tu trabajo es
decir, con la tool registrar_columnas_de_la_planilla, en qué columna está cada
dato. No copies valores: solo coordenadas. Los valores se toman después de las
celdas, tal cual están.

La planilla puede venir de cualquier forma: con títulos o sin ellos, con los
títulos en cualquier fila, con nombres de columna que nunca viste, con hojas de
más adelante o atrás, con filas de título, de totales o de pie de reporte.
Razoná cada columna mirando el título Y los valores que trae. Si un dato no
está en ninguna columna, dejalo vacío: mejor que falte a que salga de la
columna equivocada.
""".strip()


async def interpretar_planilla(texto_planilla: str) -> tuple[dict, int, int]:
    """Le muestra la planilla a CatTi y le pide qué es cada columna. Una sola
    llamada de texto, sin imágenes, que cuesta lo mismo con 8 productos que
    con 800 (ver planilla._MUESTRA_FILAS). Devuelve (mapeo, tokens_in,
    tokens_out); el mapeo lo verifica `planilla._segun_catti` contra el archivo
    antes de usarlo."""
    raw, t_in, t_out = await _llamar(
        _TOOL_COLUMNAS, _INSTRUCCION_COLUMNAS, [],
        "Esta es la planilla:\n\n" + texto_planilla, max_tokens=2000,
    )
    columnas = raw.get("columnas") or {}
    try:
        fila = int(raw.get("fila_encabezados") or 0)
    except (TypeError, ValueError):
        fila = 0
    return {
        "hoja": str(raw.get("hoja") or "").strip(),
        "fila_encabezados": fila,
        "columnas": {k: str(columnas.get(k) or "").strip().upper() for k in _DATOS_DE_LA_PLANILLA},
        "explicacion": limpiar_texto(raw.get("explicacion")),
        "dudas": limpiar_texto(raw.get("dudas")),
    }, t_in, t_out


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


async def _llamar(tool: dict, instruccion: str, bloques: list[dict], texto: str, max_tokens: int) -> tuple[dict, int, int]:
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
            "content": [*bloques, {"type": "text", "text": texto}],
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

def _preparar_pagina(pagina_img) -> list[dict]:
    """SINCRÓNICO (va en un hilo, ver hilos.py): lo que se le manda al modelo
    de una página del mailing -- la página entera y sus dos mitades ampliadas."""
    completa = imagenes.reducir(pagina_img, _LADO_LARGO_MODELO)
    mitades = [
        imagenes.ajustar_ancho(m, _ANCHO_TIRA) for m, _, _ in imagenes.mitades_con_solape(pagina_img)
    ]
    return [_bloque_imagen(i) for i in (completa, *mitades)]


async def leer_pagina_mailing(pagina_img, indice: int) -> tuple[dict, int, int]:
    """Lee UNA página del mailing. Devuelve (lectura normalizada, tokens_in, tokens_out)."""
    bloques = await en_hilo(_preparar_pagina, pagina_img)
    raw, t_in, t_out = await _llamar(
        _TOOL_MAILING, _INSTRUCCION_MAILING, bloques,
        f"Registrá la página {indice + 1} del mailing.", max_tokens=8000,
    )
    return normalizar_pagina_mailing(raw, indice), t_in, t_out


# --------------------------------------------------------------------------
# Las promociones: a qué campaña pertenece cada carilla, y con qué vigencia
# --------------------------------------------------------------------------
# La fecha no es de la página: es de la PROMOCION. Un mailing junta varias --
# la principal ocupa tapa e interior, y se le pegan otras en la contratapa
# con otras fechas-- y las carillas interiores no repiten ni el nombre ni la
# vigencia: se reconocen porque continúan el diseño de la tapa. Leída página
# por página, una carilla interior no tiene fecha y heredaba la primera del
# mailing, que podía ser la de la promo de al lado: la placa del aceite del
# Rompe del Finde (24 al 27) salía marcada contra "Del 23 al 30", que es Rompe
# Precios, la promo de la contratapa. Visto el 23/09/2026.
_TOOL_PROMOCIONES = {
    "name": "registrar_promociones",
    "description": "Registra qué promociones hay en el mailing, la vigencia de cada una y qué carillas ocupa.",
    "input_schema": {
        "type": "object",
        "properties": {
            "promociones": {
                "type": "array",
                "description": "Una entrada por promoción. Toda carilla tiene que quedar en al menos una.",
                "items": {
                    "type": "object",
                    "properties": {
                        "nombre": {
                            "type": "string",
                            "description": (
                                "El nombre de la promoción como aparece en su encabezado ('Los Rompe del "
                                "Finde', 'Rompe Precios Congelados'). Si una carilla no tiene encabezado y "
                                "no continúa el diseño de ninguna otra, describí su diseño en pocas palabras."
                            ),
                        },
                        "vigencia": {
                            "type": "string",
                            "description": (
                                "El texto de vigencia de ESTA promoción, si aparece en alguna de sus carillas. "
                                "Vacío si no aparece en ninguna: no lo inventes ni lo copies de otra promoción. "
                                + _LITERAL
                            ),
                        },
                        "carillas": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Los números de las carillas de esta promoción, como están numeradas en las imágenes (desde 1).",
                        },
                    },
                    "required": ["nombre", "vigencia", "carillas"],
                },
            },
        },
        "required": ["promociones"],
    },
}

_INSTRUCCION_PROMOCIONES = """
Te paso TODAS las carillas de un mailing de supermercado, numeradas desde 1 en
el orden en que vienen. Un mailing puede juntar varias promociones, cada una
con su propia vigencia: la principal ocupa varias carillas (la tapa y el
interior) y a veces se le pegan otras --en la contratapa, por ejemplo-- con
otras fechas.

Cómo reconocer una promoción: su TAPA tiene el logo o encabezado con el nombre
('Los Rompe del Finde') y el texto de vigencia ('Del jueves 24 al domingo 27
de setiembre'). Las carillas interiores muchas veces NO repiten ni el nombre
ni la fecha: se reconocen porque CONTINÚAN el diseño de la tapa -- mismo color
de fondo, mismo estilo del círculo del precio, misma tipografía, mismo marco.

Una carilla puede tener dos promociones si tiene dos encabezados con sus
fechas (ej. 'Rompe Precios Congelados' y 'Rompe Precios Limpieza' en la misma
carilla): en ese caso listá las dos y ponele a cada una esa carilla.

Devolvé con la tool registrar_promociones una entrada por promoción. Toda
carilla tiene que quedar en al menos una. La vigencia se copia tal cual está
impresa; si una promoción no tiene fecha en ninguna de sus carillas, dejala
vacía.
""".strip()

# Alcanza para reconocer un encabezado y el diseño; no hay que leer productos.
_LADO_MINIATURA_PROMO = 720


async def promociones_del_mailing(paginas) -> tuple[list[dict], int, int]:
    """Una sola llamada con todas las carillas en chico. Devuelve
    [{"nombre", "vigencia", "carillas": [índices 0-based]}]."""
    def preparar() -> list[dict]:
        bloques: list[dict] = []
        for i in range(len(paginas)):
            bloques.append({"type": "text", "text": f"Carilla {i + 1}:"})
            bloques.append(_bloque_imagen(imagenes.reducir(paginas[i], _LADO_MINIATURA_PROMO)))
        return bloques

    bloques = await en_hilo(preparar)
    raw, t_in, t_out = await _llamar(
        _TOOL_PROMOCIONES, _INSTRUCCION_PROMOCIONES, bloques,
        f"Son {len(paginas)} carillas. Decime qué promociones hay y a cuál pertenece cada una.",
        max_tokens=1500,
    )
    promos: list[dict] = []
    for p in raw.get("promociones") or []:
        carillas: set[int] = set()
        for c in p.get("carillas") or []:
            try:
                n = int(c)
            except (TypeError, ValueError):
                continue
            if 1 <= n <= len(paginas):
                carillas.add(n - 1)
        promos.append({
            "nombre": limpiar_texto(p.get("nombre")),
            "vigencia": limpiar_texto(p.get("vigencia")),
            "carillas": sorted(carillas),
        })
    return promos, t_in, t_out


def vigencias_por_carilla(promociones: list[dict], fechas_por_pagina: dict, cuantas: int) -> dict[int, str | None]:
    """La vigencia que rige en cada carilla, o None si no se puede saber.

    De cada promoción, su vigencia es la que trae escrita o, si no, la fecha
    que se leyó en alguna de sus carillas. Una carilla con una sola promoción
    (o con varias que coinciden) hereda esa vigencia; con promociones de
    vigencias distintas queda en None -- ambigua, y es mejor no comparar que
    comparar contra la equivocada. Una carilla que no cayó en ninguna
    promoción se queda con su propia fecha leída, si la tiene.

    `fechas_por_pagina` puede venir con claves int o str: al pasar por la base
    (JSONB) los int se vuelven str, y eso fue un bug real.
    """
    def fecha_de(i: int) -> str:
        return (fechas_por_pagina or {}).get(i) or (fechas_por_pagina or {}).get(str(i)) or ""

    vigencia_de_promo: list[str] = []
    for p in promociones:
        v = p.get("vigencia") or next((fecha_de(c) for c in p.get("carillas", []) if fecha_de(c)), "")
        vigencia_de_promo.append(v)

    salida: dict[int, str | None] = {}
    for i in range(cuantas):
        candidatas = {vigencia_de_promo[k] for k, p in enumerate(promociones) if i in p.get("carillas", []) and vigencia_de_promo[k]}
        if len(candidatas) == 1:
            salida[i] = next(iter(candidatas))
        elif len(candidatas) > 1:
            salida[i] = None
        else:
            salida[i] = fecha_de(i) or None
    return salida


# Cuántas páginas del mailing se preparan a la vez. Preparar una arma tres
# imágenes (la página y sus dos mitades ampliadas) y sus JPEG, así que con un
# gather sin tope un mailing de 12 carillas tenía 36 imágenes en vuelo y se
# comía el servidor. Con 4 en paralelo un mailing normal (2 a 4 carillas) no
# pierde nada de velocidad y uno grande deja de ser un pico.
_A_LA_VEZ = asyncio.Semaphore(4)


async def _leer_pagina_acotada(paginas, indice: int):
    """Pide la página DENTRO del semáforo: fuera de él, armar la lista de
    tareas abriría todas las carillas a la vez y el tope no serviría de nada."""
    async with _A_LA_VEZ:
        return await leer_pagina_mailing(paginas[indice], indice)


async def leer_mailing(paginas: list) -> tuple[dict, int, int]:
    """Lee todas las páginas en paralelo y las junta en un solo mailing:
    {"fecha", "fecha_pagina", "legal_alcohol", "legal_alcohol_pagina", "productos": [...]}.
    Los datos de campaña (fecha, leyenda de alcohol) los toma de la primera
    página que los traiga."""
    lecturas = await asyncio.gather(*(_leer_pagina_acotada(paginas, i) for i in range(len(paginas))))
    mailing = {
        "fecha": "", "fecha_pagina": None, "fecha_caja": None,
        "legal_alcohol": "", "legal_alcohol_pagina": None, "legal_alcohol_caja": None,
        # La vigencia de CADA carilla. Un pliego puede traer dos campañas con
        # dos vigencias distintas ("Rompe Precios del 23 al 30" a la izquierda
        # y "Rompe del Finde del 24 al 27" a la derecha): con una sola fecha
        # para todo el mailing, las placas de la segunda salían todas marcadas
        # con la fecha de la primera.
        "fechas_por_pagina": {},
        "productos": [],
    }
    t_in = t_out = 0
    for lectura, ti, to in lecturas:
        t_in += ti
        t_out += to
        if lectura["fecha"]:
            mailing["fechas_por_pagina"][lectura["pagina"]] = lectura["fecha"]
            if not mailing["fecha"]:
                mailing.update(fecha=lectura["fecha"], fecha_pagina=lectura["pagina"])
        if lectura["legal_alcohol"] and not mailing["legal_alcohol"]:
            mailing.update(legal_alcohol=lectura["legal_alcohol"], legal_alcohol_pagina=lectura["pagina"])
        mailing["productos"].extend(lectura["productos"])
    if not mailing["productos"]:
        raise LecturaFallida("No encontré ningún producto con precio en el mailing")

    # Qué promoción rige en cada carilla. Sin esto, una carilla interior sin
    # fecha heredaba la primera del mailing, que podía ser de otra promo.
    mailing["promociones"] = []
    try:
        promos, ti, to = await promociones_del_mailing(paginas)
        t_in += ti
        t_out += to
        mailing["promociones"] = promos
        mailing["vigencia_por_pagina"] = vigencias_por_carilla(
            promos, mailing["fechas_por_pagina"], len(paginas))
    except Exception as exc:  # noqa: BLE001 -- sin la pasada, se sigue por carilla
        logger.warning("promociones: no se pudieron leer, la fecha sale por carilla -- %s", exc)
        mailing["vigencia_por_pagina"] = vigencias_por_carilla([], mailing["fechas_por_pagina"], len(paginas))
    return mailing, t_in, t_out


async def leer_producto_del_mailing(recorte) -> tuple[dict, int, int]:
    """Lee UN producto del mailing desde su recorte ampliado. Devuelve el
    producto normalizado (mismas claves que los de `leer_mailing`) y los tokens.

    Es la segunda lectura del lado del MAILING (ver
    comparador.confirmar_con_relectura_de_la_fuente): se llama solo cuando una
    placa quedó acusada de un error de precio, y se lee el recorte del producto
    --y no la página entera-- porque es donde la lectura es más fiel: la página
    completa entra al modelo achicada a 1568 px y ahí un '$1090' de 18 px de
    alto se convierte en '$1.090' o en '$7799'."""
    bloques = await en_hilo(lambda: [_bloque_imagen(imagenes.reducir(recorte, _LADO_LARGO_MODELO))])
    raw, t_in, t_out = await _llamar(
        _TOOL_PRODUCTO, _INSTRUCCION_PRODUCTO, bloques, "Registrá este producto.", max_tokens=1500,
    )
    return _producto(raw), t_in, t_out


@dataclass
class PlacaPreparada:
    """Lo que se le manda al modelo de una placa, ya armado (base64), más su
    tamaño. NO trae la imagen decodificada: una placa de 2250 px ocupa 15 a 30 MB
    en memoria, y tenerla viva mientras se espera al modelo, con varias placas a
    la vez, era lo que reventaba la memoria del servidor. Las etapas que la
    necesitan de nuevo la reabren desde los bytes (decodificar tarda ~50 ms)."""
    bloques: list[dict]
    ancho: int
    alto: int


def preparar_placa(datos: bytes) -> PlacaPreparada:
    """SINCRÓNICO (va en un hilo, ver hilos.py). ArchivoInvalido si no es una imagen."""
    im = imagenes.abrir_imagen(datos)
    completa = imagenes.reducir(im, _LADO_LARGO_MODELO)
    tira = imagenes.ajustar_ancho(imagenes.tira_inferior(im), _ANCHO_TIRA)
    return PlacaPreparada([_bloque_imagen(completa), _bloque_imagen(tira)], im.width, im.height)


# --------------------------------------------------------------------------
# La foto: placa contra mailing, imagen contra imagen
# --------------------------------------------------------------------------
# Hasta el 23/09/2026 la foto se chequeaba con una pregunta a la lectura de
# la placa sola: "¿la foto parece del producto que dice el texto?". Es una
# opinión de una sola pasada, y fallaba al azar: las placas de la freidora con
# foto de una jarra salieron marcadas en una corrida y limpias en la
# siguiente. Comparar la foto de la placa con la foto del MISMO producto en el
# mailing es una pregunta concreta --"¿son el mismo objeto?"-- y estable. Y
# una foto de otro producto es un ERROR de la placa, no un aviso.
_TOOL_FOTOS = {
    "name": "comparar_fotos",
    "description": "Dice si la foto del producto en la placa y la del producto en el mailing muestran el MISMO producto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "que_hay_en_la_placa": {
                "type": "string",
                "description": "Qué producto muestra la FOTO de la placa, en pocas palabras ('jarra eléctrica de acero', 'freidora de aire negra'). Vacío si la placa no tiene foto de producto.",
            },
            "que_hay_en_el_mailing": {
                "type": "string",
                "description": "Qué producto muestra el recorte del mailing, en pocas palabras.",
            },
            "mismo_producto": {
                "type": "boolean",
                "description": (
                    "true solo si las dos fotos muestran el mismo tipo de producto. Otro ángulo, otro "
                    "tamaño, otro fondo o un envase de otro color NO cuentan como distinto. Un producto "
                    "distinto sí: una jarra no es una freidora aunque sean de la misma marca."
                ),
            },
            "motivo": {"type": "string", "description": "Una frase: por qué sí o por qué no."},
        },
        "required": ["que_hay_en_la_placa", "que_hay_en_el_mailing", "mismo_producto", "motivo"],
    },
}

_INSTRUCCION_FOTOS = """
Te paso dos imágenes: primero UNA placa de redes sociales completa, después el
RECORTE del producto que le corresponde en el mailing original.

Mirá solo la FOTO del producto en cada una --no los textos ni los precios-- y
decime si muestran el mismo producto. Un cambio de ángulo, de tamaño, de fondo
o del color del envase no cuenta como distinto. Un producto distinto sí: una
jarra eléctrica no es una freidora aunque sean de la misma marca; un queso en
horma no es un queso en fetas del mismo nombre.

Si la placa no tiene foto de producto, o el recorte del mailing no se ve bien,
decilo en el motivo y contestá mismo_producto = true: no se acusa sin ver.
""".strip()


async def comparar_fotos(prep: PlacaPreparada, recorte_mailing_uri: str) -> tuple[dict, int, int]:
    """La placa completa (ya en base64) contra el recorte del producto del
    mailing (un data URI JPEG, el que se muestra en pantalla)."""
    b64 = recorte_mailing_uri.split(",", 1)[1] if "," in recorte_mailing_uri else recorte_mailing_uri
    bloque_mailing = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}
    raw, t_in, t_out = await _llamar(
        _TOOL_FOTOS, _INSTRUCCION_FOTOS, [prep.bloques[0], bloque_mailing],
        "¿La foto de la placa y la del mailing son del mismo producto?", max_tokens=400,
    )
    return {
        "mismo_producto": bool(raw.get("mismo_producto", True)),
        "que_hay_en_la_placa": limpiar_texto(raw.get("que_hay_en_la_placa")),
        "que_hay_en_el_mailing": limpiar_texto(raw.get("que_hay_en_el_mailing")),
        "motivo": limpiar_texto(raw.get("motivo")),
    }, t_in, t_out


async def leer_placa(prep: PlacaPreparada) -> tuple[dict, int, int]:
    """Lee UNA placa. Devuelve (lectura normalizada, tokens_in, tokens_out)."""
    raw, t_in, t_out = await _llamar(
        _TOOL_PLACA, _INSTRUCCION_PLACA, prep.bloques, "Registrá esta placa.", max_tokens=3000,
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


def _preparar_bandas(fuente) -> list[tuple[float, float, dict]]:
    """SINCRÓNICO (va en un hilo, ver hilos.py): cada franja de la imagen con su
    grilla, lista para mandar. `fuente` son los bytes de una imagen o una imagen."""
    im = imagenes.abrir_imagen(fuente) if isinstance(fuente, (bytes, bytearray)) else fuente
    salida = []
    for y0, y1 in _bandas(im.height / im.width):
        franja = im.crop((0, int(y0 * im.height), im.width, int(y1 * im.height)))
        franja = imagenes.reducir(franja, _LADO_LARGO_MODELO)
        salida.append((y0, y1, _bloque_imagen(imagenes.con_grilla(franja))))
    return salida


async def localizar(fuente, pedidos: list[tuple[str, str]]) -> tuple[dict, int, int]:
    """Ubica cada elemento de `pedidos` [(id, qué es)] sobre la imagen, con una
    grilla rotulada encima. Devuelve ({id: caja}, tokens_in, tokens_out).

    Va aparte de la lectura a propósito: pedirle al modelo que transcriba
    LITERAL y además mida coordenadas en la misma respuesta empeoraba las dos
    cosas. La lectura de texto queda sobre la imagen limpia; las coordenadas
    se miden sobre franjas con grilla (ver _bandas)."""
    if not pedidos:
        return {}, 0, 0
    lista = "\n".join(f"- {id_}: {que}" for id_, que in pedidos)
    validos = {p[0] for p in pedidos}
    bandas = await en_hilo(_preparar_bandas, fuente)

    async def por_banda(y0: float, y1: float, bloque: dict):
        texto = f"Ubicá estos elementos:\n{lista}"
        if len(bandas) > 1:
            texto += (
                "\n\nEsta imagen es solo una franja de una imagen más grande: puede mostrar un elemento "
                "cortado en el borde de arriba o de abajo. Ubicá únicamente los elementos que se ven "
                "COMPLETOS acá; los cortados omitilos (se van a ubicar en otra franja)."
            )
        raw, ti, to = await _llamar(_TOOL_CAJAS, _INSTRUCCION_CAJAS, [bloque], texto, max_tokens=3000)
        return raw, ti, to, y0, y1

    resultados = await asyncio.gather(*(por_banda(*b) for b in bandas))
    t_in = t_out = 0
    candidatas: dict[str, list] = {}
    for raw, ti, to, y0, y1 in resultados:
        t_in += ti
        t_out += to
        for e in raw.get("elementos") or []:
            if not isinstance(e, dict):
                continue  # el modelo a veces devuelve algo que no es un objeto: se ignora, no rompe la placa
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
    async def por_pagina(indice: int):
        pedidos: list[tuple[str, str]] = []
        for i, prod in enumerate(mailing["productos"]):
            if prod["pagina"] == indice:
                pedidos += _pedidos_producto(f"p{i}.", prod)
        if mailing["fecha_pagina"] == indice:
            pedidos.append(("fecha", f"el texto de vigencia «{mailing['fecha']}»"))
        if mailing["legal_alcohol_pagina"] == indice:
            pedidos.append(("legal_alcohol", f"la leyenda «{mailing['legal_alcohol']}»"))
        # El mismo tope que la lectura, y por el mismo motivo: acá se arma una
        # copia de la página con la grilla encima y sus franjas.
        async with _A_LA_VEZ:
            return await localizar(paginas[indice], pedidos)

    resultados = await asyncio.gather(*(por_pagina(i) for i in range(len(paginas))))
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


async def localizar_placa(datos: bytes, lectura: dict) -> tuple[dict, int, int]:
    """Cajas de lo que se ve en una placa. Solo se llama cuando la placa tiene
    diferencias: el recorte es para mostrarlas, no para validar."""
    prod = lectura["producto"]
    pedidos = _pedidos_producto("", prod) + [
        ("fecha", f"el texto de vigencia «{lectura['fecha']}»"),
        ("legales", "las leyendas legales del pie de la placa"),
        ("imagen", "la foto del producto"),
    ]
    return await localizar(datos, pedidos)
