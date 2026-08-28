"""Vocabulario único de variables de cenefas — 32 nombres, un solo lenguaje.

Desde 08/2026 el nombre de la columna del Excel, el placeholder del PPTX
(``<<nombre>>``) y la clave del JSON del template son SIEMPRE el mismo
string. No hay alias, no hay traducción de un nombre a otro y no hay
nombres legacy: si una columna no se llama como la variable, no matchea —
para eso está la pantalla de mapeo del Convertidor, que renombra las
columnas del export de gestión ANTES de que este motor las vea.

Ninguna variable es obligatoria. Si la PPT no tiene el cuadro de texto de
una variable, no se sustituye nada y el sistema sigue de largo; si el Excel
no trae la columna, la variable queda vacía.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Las 32 variables
# ---------------------------------------------------------------------------

# Identificación y textos.
#
# `tipoOferta` se agregó el 2026-08-24 para el titular grande de las cenefas de
# Redexpres, el que va arriba del precio ("2x1", "SOLO X 25", "25% OFF").
# Es de TEXTO aunque casi siempre traiga números y símbolos: no es un precio,
# no se le separa el decimal y no se le da formato -- se imprime tal cual venga.
# No confundir con ofertaUno..Cuatro, que sí son precios (los niveles 4x3/5x3
# de Parrilla y Vinos) y arrastran su columna de decimales.
# `tipoOfertaComprando` y `unidad` se agregaron el 2026-08-26 para las cenefas
# de Rompe del Finde (Tienda Inglesa), donde la mecánica se dibuja repartida en
# tres lugares en vez de en un renglón:
#
#     cocarda al costado   tipoOferta            "2x$299" / "6x4"
#     arriba del precio    tipoOfertaComprando   "Comprando 2"
#     abajo del precio     unidad                "unidad"
#
# En Redexpres esa misma mecánica va entera adentro de `mecanica`
# ("$75,33 la unidad."), así que las dos nuevas quedan vacías ahí. Son de TEXTO:
# se imprimen tal cual, sin separar decimal ni dar formato.
# ===========================================================================
# LEER ESTO ANTES DE TOCAR precioOferta  (decision de Ivan, 2026-08-26)
# ===========================================================================
#
#   `precioOferta` es SIEMPRE UN PRECIO. Literalmente. En todos los mundos.
#
# Nunca vuelve a llevar un literal de mecanica ("6x4", "2x1") adentro. Si en
# una cenefa hay que mostrar el literal en el lugar del precio, eso NO se
# resuelve metiendolo en `precioOferta`: se resuelve con `promoOferta`, que es
# una variable aparte que el diseno dibuja SUPERPUESTA encima del cuadro del
# precio. Cuando hay mecanica, `promoOferta` trae el literal y tapa al precio;
# cuando no hay, queda vacia y se ve el precio.
#
# Por que se decidio asi, y por que NO se hizo al reves (una variable nueva
# para el precio y dejar el literal en precioOferta):
#
#   Todo Excel de gestion que se suba de ahora en adelante va a traer mecanica,
#   oferta y ofertadet, y va a pasar por el mismo camino. Si el literal viviera
#   en `precioOferta`, CADA plantilla nueva y CADA Excel futuro tendria que
#   acomodarse a que la variable del precio a veces no trae un precio. Se
#   arregla una vez, del lado del dato: el precio es el precio, y lo que tape
#   al precio es otra cosa con su propio nombre.
#
# Estado al 2026-08-29 (decision de Ivan: promoOferta se usa SOLO en M x N):
#   - M x N ("2x1")    -> precioOferta = el unitario de la columna PRECIO
#                         promoOferta  = "2x1" (tapa al precio Y a la cocarda
#                         de tipoOferta si el diseno tiene su cuadro -- son el
#                         mismo literal y salia impreso dos veces)
#   - Combo ("2x$299") -> precioOferta = el unitario (total / cantidad)
#                         promoOferta  = VACIA: hay un precio para mostrar, se
#                         muestra, con la cocarda de tipoOferta arriba
#   - Precio fijo      -> las dos vacias.
# ===========================================================================

TEXT_VARS: tuple[str, ...] = (
    "codigo",
    "descripcion",
    "mecanica",
    "tipoOferta",
    "tipoOfertaComprando",
    "unidad",
    # El simbolo de moneda ("$" / "U$S"), agregado el 2026-08-29 (decision de
    # Ivan). El Convertidor la escribe SIEMPRE, leyendo la columna MONEDA del
    # export de gestion, y el diseno la dibuja al lado de cada precio con el
    # placeholder <<unidadMoneda>>. Reemplaza al "$" como texto fijo del
    # diseno: con la variable, una fila en dolares sale con U$S sola, sin
    # depender de una plantilla especial. Es de TEXTO: se imprime tal cual.
    "unidadMoneda",
    "vigencia",
    "aclaracionUno",
    "aclaracionDos",
    "aclaracionTres",
    "legales",
    "dia",
    "mes",
    "año",
    "banco",
)

# Precios: se normalizan al formato uruguayo y se les separa el decimal.
# SIN prefijo de moneda -- el "$"/"U$S" viaja aparte en `unidadMoneda`
# (desde 2026-08-29; antes era texto fijo del diseño), así que si el valor
# también lo trajera quedaría duplicado ("$$899").
PRICE_VARS: tuple[str, ...] = (
    "precioRegular",
    "precioOferta",
    # El literal de la mecanica cuando el diseno lo dibuja TAPANDO al precio
    # (Redexpres). Es de tipo precio solo para que arrastre su decimal como el
    # resto y no haya que tratarla aparte; el valor que lleva es texto ("6x4").
    # Ver el bloque grande del principio del archivo.
    "promoOferta",
    "ofertaUno",
    "ofertaDos",
    "ofertaTres",
    "ofertaCuatro",
    "precioBanco",
)

# Parte decimal de cada precio, en su propio cuadro de texto. Siempre CON la
# coma adelante (",50"); vacía si el precio es redondo o no existe.
DECIMAL_OF: dict[str, str] = {
    "precioRegular": "decimalPrecioRegular",
    "precioOferta":  "decimalPrecioOferta",
    "promoOferta":   "decimalPromoOferta",
    "ofertaUno":     "decimalPrecioUno",
    "ofertaDos":     "decimalPrecioDos",
    "ofertaTres":    "decimalPrecioTres",
    "ofertaCuatro":  "decimalPrecioCuatro",
    "precioBanco":   "decimalPrecioBanco",
}

DECIMAL_VARS: tuple[str, ...] = tuple(DECIMAL_OF.values())

CANONICAL_VARS: tuple[str, ...] = TEXT_VARS + PRICE_VARS + DECIMAL_VARS

CANONICAL_SET: frozenset[str] = frozenset(CANONICAL_VARS)

# Orden de las columnas en todo Excel que produce o entrega la plataforma
# (la plantilla descargable y la salida del Convertidor). Agrupa cada precio
# con su decimal al lado, que es como se leen: una persona revisando la
# planilla necesita ver "719" y ",20" juntos, no en puntas opuestas.
ORDEN_EXPORT: tuple[str, ...] = (
    "codigo",
    "descripcion",
    "mecanica",
    "tipoOferta",
    "tipoOfertaComprando",
    "unidad",
    "unidadMoneda",
    "precioRegular", "decimalPrecioRegular",
    "precioOferta",  "decimalPrecioOferta",
    "promoOferta",   "decimalPromoOferta",
    "ofertaUno",     "decimalPrecioUno",
    "ofertaDos",     "decimalPrecioDos",
    "ofertaTres",    "decimalPrecioTres",
    "ofertaCuatro",  "decimalPrecioCuatro",
    "precioBanco",   "decimalPrecioBanco",
    "banco",
    "vigencia",
    "aclaracionUno", "aclaracionDos", "aclaracionTres",
    "legales",
    "dia", "mes", "año",
)

assert set(ORDEN_EXPORT) == CANONICAL_SET, "ORDEN_EXPORT quedó desincronizado de las variables"

# ---------------------------------------------------------------------------
# Campos internos
# ---------------------------------------------------------------------------
#
# Se leen del Excel pero NO se dibujan nunca: no son variables, no aparecen
# en el editor y no tienen placeholder. Solo alimentan decisiones del motor.
#
#   categoria    -> dispara el legal automático de alcohol (se SUMA a legales)
#   subCategoria -> reservado para reglas por rubro
#   comprador    -> reservado para reglas por rubro
#   ofertaDet    -> tipo de mecánica; el Convertidor ya la resolvió a texto,
#                   acá solo queda como rastro para diagnóstico
#
INTERNAL_FIELDS: tuple[str, ...] = ("categoria", "subCategoria", "comprador", "ofertaDet")

INTERNAL_SET: frozenset[str] = frozenset(INTERNAL_FIELDS)

# Texto que se agrega a `legales` cuando la categoría es de bebidas con
# alcohol y el usuario habilitó los legales (ver checkbox del panel de
# generación). No pisa lo que la persona escribió: se suma.
# Las DOS frases. "Beber con moderación" faltaba: la constante solo tenía la
# de la prohibición de venta, y el diseño de referencia de Rompe del Finde
# imprime las dos ("Descuento aplicado en cajas. Beber con moderación.
# Prohibida la venta a menores de 18 años.").
LEGAL_ALCOHOL = (
    "Beber con moderación. "
    "Prohibida la venta de bebidas alcohólicas a menores de 18 años"
)

_RE_CATEGORIA_ALCOHOL = re.compile(r"alcohol", re.IGNORECASE)

# Tipos de bebida con alcohol, para reconocerlos por el NOMBRE del producto
# cuando el export no trae una categoría que lo diga.
#
# Por qué hace falta: `categoria_es_alcohol` busca la palabra "alcohol" en la
# columna CATEGORIA, y esa columna NO existe en varios exports -- el Convertidor
# ni la lee. Con COMPRADOR="BEBIDAS" no alcanza: ahí conviven la Coca-Cola y el
# fernet. Resultado real: una cenefa de Stella Artois salía sin la leyenda.
#
# Va por TIPO de bebida y no por marca a propósito. Una lista de marcas hay que
# mantenerla para siempre y falla justo con la marca nueva; "cerveza", "whisky" o
# "fernet" aparecen en el nombre de gestión de todas las marcas de su tipo.
# Igual queda corto para lo que no se nombra por tipo, y para eso está Tinín --
# ver `detectar_alcohol` (pendiente) en convertidor_ai.py.
#
# "sin alcohol" NO se excluye: la Stella sin alcohol se vende al lado de la
# original y la leyenda de más no hace daño. Omitirla sí.
_TIPOS_ALCOHOL = (
    "cerveza", "vino", "whisky", "whiskey", "fernet", "vodka", "gin ", "ginebra",
    "ron ", "licor", "champagne", "champaña", "espumante", "sidra", "aperitivo",
    "grappa", "grapa", "caña", "tequila", "aperol", "vermouth", "vermut",
    "sangria", "sangría", "coñac", "cognac", "brandy", "pisco", "amargo serrano",
)

# El borde de PALABRA va de los dos lados, y ahí está la gracia.
#
# Por delante, para no pescar un tipo en el medio de otra palabra. Por
# detrás, porque sin eso "gin" matcheaba dentro de "Ginger ale" --que no
# tiene alcohol y se vende igual-- y "ron" dentro de "Ronda de quesos". Los
# espacios finales de "gin " y "ron " en la lista de arriba estaban puestos
# justo para eso y el .strip() se los comía.
#
# El plural opcional (`e?s`) es lo que evita que el borde de atrás rompa lo
# que sí hay que agarrar: "Vinos", "Cervezas", "Licores".
_RE_TIPO_ALCOHOL = re.compile(
    r"(?:^|[^a-záéíóúñ])(?:"
    + "|".join(t.strip() for t in _TIPOS_ALCOHOL)
    + r")(?:e?s)?(?![a-záéíóúñ])",
    re.IGNORECASE,
)


def es_alcohol(*textos: str) -> bool:
    """True si alguno de esos textos habla de una bebida con alcohol.

    Se le pasa la categoría, la descripción y el nombre de gestión: basta que
    UNO lo diga. Errar por exceso agrega una leyenda que sobra; errar por
    defecto imprime un cartel de bebida alcohólica sin la leyenda obligatoria,
    que es una infracción.
    """
    for t in textos:
        t = str(t or "")
        if not t:
            continue
        if _RE_CATEGORIA_ALCOHOL.search(t) or _RE_TIPO_ALCOHOL.search(t):
            return True
    return False


def categoria_es_alcohol(categoria: str) -> bool:
    """True si la categoría corresponde a bebidas con alcohol.

    Por substring y no por igualdad exacta: el valor real varía entre
    exports ("BEBIDAS CON ALCOHOL", "Bebidas c/alcohol", "ALCOHOL"), y
    equivocarse acá significa imprimir un cartel de bebida alcohólica sin
    la leyenda obligatoria.

    Se mantiene para lo que ya la usaba; lo nuevo va por `es_alcohol`, que
    además mira el nombre del producto.
    """
    return bool(_RE_CATEGORIA_ALCOHOL.search(categoria or ""))


# ---------------------------------------------------------------------------
# Normalización de nombres
# ---------------------------------------------------------------------------

def norm(name) -> str:
    """Normaliza un nombre para comparar: sin acentos, sin separadores, minúsculas.

    "Precio Regular", "precio_regular" y "PRECIOREGULAR" son todos
    `precioregular`. La ñ/tildes se colapsan también, así que "año" y "ano"
    resuelven a la misma variable -- es el único caso donde el nombre
    canónico lleva un carácter no ASCII.
    """
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-.]+", "", s).lower()


# Mapa: nombre normalizado -> nombre canónico. Se arma de las variables
# mismas, no a mano: no hay forma de que se desincronicen.
_BY_NORM: dict[str, str] = {norm(v): v for v in CANONICAL_VARS}
_BY_NORM.update({norm(f): f for f in INTERNAL_FIELDS})


def resolve(name) -> str | None:
    """Nombre de columna/placeholder -> variable canónica, o None si no es una."""
    return _BY_NORM.get(norm(name))


def is_price(var_name: str) -> bool:
    return var_name in PRICE_VARS


def is_decimal(var_name: str) -> bool:
    return var_name in DECIMAL_VARS
