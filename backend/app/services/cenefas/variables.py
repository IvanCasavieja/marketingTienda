"""Vocabulario único de variables de cenefas — 26 nombres, un solo lenguaje.

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
# Las 26 variables
# ---------------------------------------------------------------------------

# Identificación y textos.
TEXT_VARS: tuple[str, ...] = (
    "codigo",
    "descripcion",
    "mecanica",
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
# SIN prefijo de moneda -- el "$"/"U$S" ahora va como cuadro de texto fijo en
# el diseño de la PPT (decisión explícita 08/2026), así que si el valor
# también lo trajera quedaría duplicado ("$$899").
PRICE_VARS: tuple[str, ...] = (
    "precioRegular",
    "precioOferta",
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
    "precioRegular", "decimalPrecioRegular",
    "precioOferta",  "decimalPrecioOferta",
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
LEGAL_ALCOHOL = "Prohibida la venta de bebidas alcohólicas a menores de 18 años"

_RE_CATEGORIA_ALCOHOL = re.compile(r"alcohol", re.IGNORECASE)


def categoria_es_alcohol(categoria: str) -> bool:
    """True si la categoría corresponde a bebidas con alcohol.

    Por substring y no por igualdad exacta: el valor real varía entre
    exports ("BEBIDAS CON ALCOHOL", "Bebidas c/alcohol", "ALCOHOL"), y
    equivocarse acá significa imprimir un cartel de bebida alcohólica sin
    la leyenda obligatoria.
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
