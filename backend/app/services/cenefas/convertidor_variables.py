"""De una fila del export de gestión a las 26 variables de cenefas.

Acá vive TODA la lógica de negocio que antes estaba repartida entre
data_engine.py (combos, M x N, precios por kilo) y el render. La decisión de
08/2026 es que el Convertidor entregue el Excel con una columna por variable
y el valor final ya escrito, para que el motor de cenefas solo sustituya.
"""
from __future__ import annotations

import re

from app.services.cenefas.data_engine import split_price
from app.services.cenefas.formatters import fmt_price, parse_price_raw
from app.services.cenefas.variables import CANONICAL_VARS, DECIMAL_OF, PRICE_VARS

# ---------------------------------------------------------------------------
# Variables que resuelve la persona
# ---------------------------------------------------------------------------
#
# El Convertidor no puede deducirlas: o su nombre de columna cambia según el
# archivo de gestión que se suba, o directamente no vienen en ningún export.
# Se resuelven en la pantalla de mapeo, de una de dos formas: mapeando una
# columna, o escribiendo un texto que va en todas las filas.
#
# El resto (codigo, descripcion, precioRegular, precioOferta, mecanica y
# todos los decimales) sale de columnas fijas del export o se calcula acá.
#
# El orden es el mismo de ORDEN_EXPORT, así la pantalla se lee en el mismo
# orden en que después salen las columnas del Excel.
#
# banco, precioBanco, dia, mes y año se sumaron el 2026-08-23: antes no
# estaban en ningún lado del Convertidor, así que el Excel que bajaba no
# podía traerlas nunca. Se notaba en que decimalPrecioBanco existía pero no
# podía tener valor jamás, porque su precio no se podía cargar.
VARIABLES_MAPEABLES: tuple[str, ...] = (
    "tipoOferta",
    "ofertaUno",
    "ofertaDos",
    "ofertaTres",
    "ofertaCuatro",
    "precioBanco",
    "banco",
    "vigencia",
    "aclaracionUno",
    "aclaracionDos",
    "aclaracionTres",
    "legales",
    "dia",
    "mes",
    "año",
)

assert set(VARIABLES_MAPEABLES) <= set(CANONICAL_VARS), (
    "hay una variable mapeable que no es canónica"
)

MECANICA_PRECIO_FIJO = "Precio Final"

# ---------------------------------------------------------------------------
# Mecánicas
# ---------------------------------------------------------------------------

# "3x99" / "3 X $99" -> cantidad 3, total 99. El "$" es opcional a propósito:
# el valor real viene escrito de las dos formas y un símbolo de moneda no
# puede cortar el cálculo (ya rompió una vez, dejando el precio en $0).
#
# Se BUSCA dentro del texto, no se matchea la cadena entera. Gestión escribe
# la columna OFERTA de las dos formas: "2x$299" pelado en algunos listados y
# "Coca Cola Zero 2.25 L 2x$299" en otros. Anclado con ^...$ el segundo no
# matcheaba y la fila perdía TODO -- precio, tipoOferta y mecánica quedaban
# vacíos y la cenefa salía sin precio (visto en el boceto del 27/08).
# El "$" es OPCIONAL: gestion escribe "3x99" y "2x$299". No hay ambiguedad
# con un M x N ("6x4") porque este regex solo se usa cuando OFERTADET ya
# dijo que es un combo -- el tipo lo decide OFERTADET, nunca el texto.
_RE_COMBO = re.compile(r"(\d+)\s*[xX×]\s*\$?\s*([\d.,]+)")

# "2x1" / "4X2" -- la mecánica M x N no trae precio, trae cuántas se llevan
# y cuántas se pagan. Sin "$" en el medio: eso lo distingue de un combo.
_RE_MXN = re.compile(r"(?<![\d.,])(\d+)\s*[xX×]\s*(\d+)(?![\d.,])")

# "2da unidad al 50%" -- se lleva la segunda a mitad de precio. No es combo
# (no hay un total) ni M x N (no se paga por unidades enteras).
_RE_SEGUNDA = re.compile(
    r"(\d+)\s*(?:da|ra|ta|va|ma|era|º|°)?\s*unidad(?:es)?\s*al\s*(\d+)\s*%",
    re.IGNORECASE,
)

_RE_ES_MXN_DET = re.compile(r"m\s*[xX×]\s*n", re.IGNORECASE)
_RE_ES_COMBO_DET = re.compile(r"combo", re.IGNORECASE)
_RE_ES_SEGUNDA_DET = re.compile(r"unidad\s*al", re.IGNORECASE)

# OFERTADET que significan "no hay mecánica". No es una lista negra de valores
# de OFERTA: es la lista de TIPOS que no anuncian nada. Ver la regla de
# tipoOferta en resolver_mecanica.
_RE_SIN_MECANICA_DET = re.compile(r"precio\s*fijo|%\s*descuento|descuentos?", re.IGNORECASE)

# Las familias de mecánica que el motor sabe resolver. Es la respuesta a "¿qué
# ES esto?", separada de "¿cómo se resuelve?" -- porque desde 08/2026 la
# respuesta puede venir de dos lados: del texto de OFERTADET (acá abajo) o
# aprendida de una confirmación anterior (cenefa_ofertadet_aliases).
FAMILIAS_MECANICA = ("combo", "mxn", "segunda", "sin_mecanica")


def familia_de_ofertadet(oferta_det: str) -> str | None:
    """Qué familia de mecánica es este OFERTADET, o None si no la reconozco.

    None es el caso que importa: gestión inventó un tipo nuevo. Sin esto la
    fila perdía la mecánica en silencio y solo quedaba un aviso."""
    oferta_det = (oferta_det or "").strip()
    if not oferta_det:
        return None
    if _RE_ES_COMBO_DET.search(oferta_det):
        return "combo"
    if _RE_ES_MXN_DET.search(oferta_det):
        return "mxn"
    if _RE_ES_SEGUNDA_DET.search(oferta_det):
        return "segunda"
    if _RE_SIN_MECANICA_DET.search(oferta_det):
        return "sin_mecanica"
    return None

# La lista negra de etiquetas de OFERTA ("pvp", "fullprice", "noaplica",
# "ante/despues"...) junto con _norm_etiqueta() y _es_numero() se eliminaron el
# 2026-08-25: existían para adivinar desde OFERTA si había mecánica, y OFERTADET
# ya lo dice. Ver la regla de tipoOferta en resolver_mecanica.


def resolver_mecanica(
    oferta_det: str,
    oferta: str,
    precio: float | None,
    moneda: str = "$",
    familia: str | None = None,
) -> tuple[dict, list[str]]:
    """Resuelve la mecánica de una fila.

    Devuelve ({ofertaUno, precioOferta, mecanica}, warnings).

    Tres caminos, según OFERTADET:

    - **Combo** ("3x99"): se lleva 3 pagando 99 en total. El unitario sale de
      dividir (99÷3 = 33), no de la columna PRECIO -- esa trae el precio de
      una unidad suelta, que es otro número. El cuadro grande muestra el
      total del combo y ``ofertaUno`` la cantidad ("3x").
    - **M x N** ("2x1"): no hay un precio de oferta que mostrar, así que el
      literal de la mecánica ocupa el cuadro grande y el unitario sale de la
      columna PRECIO (gestión ya lo dejó calculado ahí). ``ofertaUno`` queda
      vacía.
    - **Precio fijo / % descuento / vacío**: solo precio, mecánica "Precio
      Final".
    """
    oferta = (oferta or "").strip()
    oferta_det = (oferta_det or "").strip()
    warnings: list[str] = []
    # `familia` la pasa el caller cuando alguien ya confirmó qué es este
    # OFERTADET (ver cenefa_ofertadet_aliases). Gana sobre el texto: es una
    # persona diciendo lo que las expresiones regulares no supieron leer.
    familia = familia if familia in FAMILIAS_MECANICA else familia_de_ofertadet(oferta_det)
    prefijo = "U$S " if moneda.strip().upper() in ("U$S", "US$", "USD") else "$"

    # ── Combo ─────────────────────────────────────────────────────────────
    if familia == "combo":
        m = _RE_COMBO.search(oferta)
        if not m:
            warnings.append("combo_no_parseable")
            return {"ofertaUno": "", "tipoOferta": "", "precioOferta": "", "promoOferta": "", "mecanica": "",
                    "tipoOfertaComprando": "", "unidad": ""}, warnings
        cantidad = int(m.group(1))
        total = parse_price_raw(m.group(2))
        if cantidad <= 0 or total <= 0:
            warnings.append("combo_no_parseable")
            return {"ofertaUno": "", "tipoOferta": "", "precioOferta": "", "promoOferta": "", "mecanica": "",
                    "tipoOfertaComprando": "", "unidad": ""}, warnings
        unitario = round(total / cantidad, 2)
        return {
            # El literal LIMPIO que matcheo, no la frase entera: gestion escribe
            # "Coca Cola Zero 2.25 L 2x$299" y en la cocarda va "2x$299".
            "tipoOferta":   re.sub(r"\s+", "", m.group(0)),
            "ofertaUno":    f"{cantidad}x",
            # El unitario, no el total: precioOferta ES UN PRECIO y es el que
            # se imprime grande. El literal del combo ("2x$299") va a
            # promoOferta, igual que el "6x4" de un M x N -- el diseno lo
            # dibuja tapando al precio cuando corresponde.
            #
            # El unitario sale de DIVIDIR el total (299/2), no de la columna
            # PRECIO: esa trae el precio de una unidad suelta, que puede ser
            # otro numero. Ver el bloque del principio de variables.py.
            "precioOferta": unitario,
            "promoOferta":  re.sub(r"\s+", "", m.group(0)),
            "mecanica":     f"Comprando {cantidad}, {prefijo}{fmt_price(unitario)} la unidad.",
            # Los dos pedazos sueltos, para el diseno que los dibuja separados
            # arriba y abajo del precio en vez de en un renglon (Rompe del
            # Finde). Se calculan SIEMPRE: una plantilla que no los tenga
            # simplemente no los dibuja, asi que no hace falta que el
            # Convertidor sepa para que mundo esta trabajando.
            "tipoOfertaComprando": f"Comprando {cantidad}",
            "unidad":              "unidad",
        }, warnings

    # ── M x N ─────────────────────────────────────────────────────────────
    if familia == "mxn":
        m = _RE_MXN.search(oferta)
        if not m:
            warnings.append("mxn_no_parseable")
            return {"ofertaUno": "", "tipoOferta": "", "precioOferta": "", "promoOferta": "", "mecanica": "",
                    "tipoOfertaComprando": "", "unidad": ""}, warnings
        literal = re.sub(r"\s+", "", m.group(0))
        if not precio:
            # Sin precio unitario no hay mecánica que redactar; el literal
            # igual va al cuadro grande, para no perder la oferta.
            warnings.append("mxn_sin_precio")
            return {"ofertaUno": "", "tipoOferta": literal, "precioOferta": "", "promoOferta": literal, "mecanica": "",
                    "tipoOfertaComprando": "", "unidad": ""}, warnings
        cantidad = m.group(1)
        return {
            "tipoOferta":   literal,       # "2x1" / "6x4" -- la cocarda
            "ofertaUno":    "",
            # precioOferta ES UN PRECIO, SIEMPRE. El literal ya no va aca: va a
            # promoOferta, que el diseno de Redexpres dibuja TAPANDO el cuadro
            # del precio. Ver el bloque del principio de variables.py antes de
            # cambiar esto.
            "precioOferta": precio,
            "promoOferta":  literal,
            "mecanica":     f"{prefijo}{fmt_price(precio)} la unidad.",
            "tipoOfertaComprando": f"Comprando {cantidad}",
            "unidad":              "unidad",
        }, warnings

    # ── 2da unidad al XX% ─────────────────────────────────────────────────
    # "Sprite sin azucar 2.25L 2da unidad al 50%". No es combo (no hay total)
    # ni M x N (no se paga por unidades enteras): el precio grande es el de la
    # columna PRECIO y la cocarda anuncia la condicion.
    if familia == "segunda":
        m = _RE_SEGUNDA.search(oferta)
        if not m:
            warnings.append("segunda_unidad_no_parseable")
            return {"ofertaUno": "", "tipoOferta": "", "precioOferta": "", "promoOferta": "", "mecanica": "",
                    "tipoOfertaComprando": "", "unidad": ""}, warnings
        n, pct = m.group(1), m.group(2)
        sufijo = {"1": "ra", "3": "ra"}.get(n, "da")
        return {
            "tipoOferta":   f"{n}{sufijo} al {pct}%",
            "ofertaUno":    "",
            "precioOferta": precio if precio is not None else "",
            "promoOferta":  "",
            "mecanica":     f"{n}{sufijo} unidad al {pct}%.",
            # Sin "Comprando N": no se lleva una cantidad fija, se lleva una
            # segunda unidad. La cocarda ya lo dice entero.
            "tipoOfertaComprando": "",
            "unidad":              "",
        }, warnings

    # ── Precio fijo / % descuento / cualquier otra cosa ───────────────────
    # `tipoOferta` queda VACÍA. La regla (decisión de Ivan, 2026-08-25):
    #
    #   tipoOferta se llena SOLO cuando OFERTADET es una mecánica de verdad
    #   -- Combo, M x N, o 2da unidad al XX%. Precio fijo, % descuento y lo
    #   que gestión invente mañana no anuncian nada, así que no hay cocarda.
    #
    # Sale de OFERTADET y NUNCA de OFERTA. Antes se miraba OFERTA y se trataba
    # de adivinar si era un titular o jerga interna, con una lista negra
    # (pvp/fullprice/noaplica...), un chequeo de "¿es un número?" y un warning
    # `oferta_inesperada`. Los tres existían para deducir lo que OFERTADET ya
    # decía, y los tres fallaban: "Precio Oferta" y "sin detalle" se imprimían
    # como cocarda, y un `% descuento` mandaba "-0.253164556962025" al cartel.
    #
    # El único aviso que queda es para un OFERTADET DESCONOCIDO: con esta regla
    # una mecánica nueva se descartaría en silencio, y eso sí hay que verlo.
    if oferta_det and familia is None:
        warnings.append("ofertadet_desconocido")

    return {
        "ofertaUno":    "",
        "tipoOferta":   "",
        "precioOferta": precio if precio is not None else "",
        "promoOferta":  "",
        "mecanica":     MECANICA_PRECIO_FIJO,
        "tipoOfertaComprando": "",
        "unidad":              "",
    }, warnings


# ---------------------------------------------------------------------------
# Fila completa
# ---------------------------------------------------------------------------

def construir_variables(
    parsed: dict,
    descripcion: str,
    mapeo: dict[str, str],
    vigencia_fallback: str = "",
    familia_ofertadet: str | None = None,
) -> tuple[dict, list[str]]:
    """Arma las 26 variables de una fila.

    `mapeo` es {variable: valor_ya_leido_de_la_columna_mapeada} -- el caller
    resuelve qué columna corresponde (ver parse_input_excel), acá solo se
    aplica. Una variable mapeada SIEMPRE gana sobre el valor calculado: si
    el Excel ya trae una columna con los niveles de oferta (el caso de
    Parrilla y Vinos con 4x3/5x3/6x3), eso es más confiable que inferirlo.
    """
    out: dict[str, str] = {v: "" for v in CANONICAL_VARS}
    warnings: list[str] = []

    out["codigo"] = parsed.get("codigo", "")
    out["descripcion"] = descripcion

    mecanica, w = resolver_mecanica(
        parsed.get("oferta_det", ""),
        parsed.get("oferta", ""),
        parsed.get("precio"),
        parsed.get("moneda", "$"),
        familia_ofertadet,
    )
    warnings.extend(w)

    valores: dict[str, object] = {
        "precioRegular": parsed.get("precio_anterior"),
        "precioOferta":  mecanica["precioOferta"],
        "promoOferta":   mecanica.get("promoOferta", ""),
        "ofertaUno":     mecanica["ofertaUno"],
    }
    out["mecanica"] = mecanica["mecanica"]
    # Los dos pedazos sueltos de la mecanica, para el diseno que los dibuja
    # arriba y abajo del precio en vez de en un renglon.
    out["tipoOfertaComprando"] = str(mecanica.get("tipoOfertaComprando", "") or "")
    out["unidad"] = str(mecanica.get("unidad", "") or "")
    # El titular sale de la columna OFERTA del listado, ya filtrado de las
    # etiquetas internas de gestión (ver resolver_mecanica).
    out["tipoOferta"] = str(mecanica.get("tipoOferta", "") or "")

    # Lo mapeado pisa lo calculado.
    for var, valor in mapeo.items():
        if var not in CANONICAL_VARS:
            continue
        if valor is None or str(valor).strip() == "":
            continue
        valores[var] = valor

    # Precios -> entero + decimal en columnas separadas.
    for var in PRICE_VARS:
        entero, decimal = split_price(valores.get(var, ""))
        out[var] = entero
        out[DECIMAL_OF[var]] = decimal

    # Textos mapeados.
    for var in ("tipoOferta", "vigencia", "aclaracionUno", "aclaracionDos", "aclaracionTres",
                "legales", "banco", "dia", "mes", "año"):
        valor = valores.get(var, mapeo.get(var, ""))
        if valor is not None and str(valor).strip():
            out[var] = str(valor).strip()

    # La vigencia se arma sola con fecha_inicio/fecha_fin cuando el export
    # las trae y no hay una columna mapeada.
    if not out["vigencia"]:
        out["vigencia"] = vigencia_fallback

    return out, warnings
