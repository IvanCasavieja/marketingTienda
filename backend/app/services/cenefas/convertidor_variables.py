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
_RE_COMBO = re.compile(r"^\s*(\d+)\s*[xX×]\s*\$?\s*([\d.,]+)\s*$")

# "2x1" / "4X2" -- la mecánica M x N no trae precio, trae cuántas se llevan
# y cuántas se pagan.
_RE_MXN = re.compile(r"^\s*\d+\s*[xX×]\s*\d+\s*$")

_RE_ES_MXN_DET = re.compile(r"m\s*[xX×]\s*n", re.IGNORECASE)
_RE_ES_COMBO_DET = re.compile(r"combo", re.IGNORECASE)

# Etiquetas que gestión escribe en la columna OFERTA cuando NO hay ninguna
# mecánica: son el nombre interno del tipo de precio, no una oferta.
# Confirmadas contra el export real (33 de 55 filas de precio fijo).
_ETIQUETAS_SIN_OFERTA = {
    "pvp", "pvpoferta", "fullprice", "preciofijo", "precionormal",
    "regular", "noaplica", "-",
    # El mismo rótulo aparece escrito de las dos formas en el export real
    # ("ANTE/DESPUES" y "Antes/Después"), así que van las dos.
    "antedespues", "antesdespues",
}


def _norm_etiqueta(texto: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _es_numero(texto: str) -> bool:
    return bool(re.fullmatch(r"[\$\s]*\d[\d.,]*\s*", texto or ""))


def resolver_mecanica(
    oferta_det: str,
    oferta: str,
    precio: float | None,
    moneda: str = "$",
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
    prefijo = "U$S " if moneda.strip().upper() in ("U$S", "US$", "USD") else "$"

    # ── Combo ─────────────────────────────────────────────────────────────
    if _RE_ES_COMBO_DET.search(oferta_det):
        m = _RE_COMBO.match(oferta)
        if not m:
            warnings.append("combo_no_parseable")
            return {"ofertaUno": "", "precioOferta": "", "mecanica": ""}, warnings
        cantidad = int(m.group(1))
        total = parse_price_raw(m.group(2))
        if cantidad <= 0 or total <= 0:
            warnings.append("combo_no_parseable")
            return {"ofertaUno": "", "precioOferta": "", "mecanica": ""}, warnings
        unitario = round(total / cantidad, 2)
        return {
            "ofertaUno":    f"{cantidad}x",
            "precioOferta": total,
            "mecanica":     f"Comprando {cantidad}, {prefijo}{fmt_price(unitario)} la unidad.",
        }, warnings

    # ── M x N ─────────────────────────────────────────────────────────────
    if _RE_ES_MXN_DET.search(oferta_det):
        if not _RE_MXN.match(oferta):
            warnings.append("mxn_no_parseable")
            return {"ofertaUno": "", "precioOferta": "", "mecanica": ""}, warnings
        if not precio:
            # Sin precio unitario no hay mecánica que redactar; el literal
            # igual va al cuadro grande, para no perder la oferta.
            warnings.append("mxn_sin_precio")
            return {"ofertaUno": "", "precioOferta": oferta, "mecanica": ""}, warnings
        return {
            "ofertaUno":    "",
            "precioOferta": oferta,   # "2x1" ocupa el lugar del precio
            "mecanica":     f"{prefijo}{fmt_price(precio)} la unidad.",
        }, warnings

    # ── Precio fijo / % descuento / sin mecánica ──────────────────────────
    # OFERTA no se ignora en silencio: se clasifica. Si trae algo que no sea
    # una etiqueta conocida de gestión ni una copia del precio, es un dato
    # que nadie sabe interpretar y se marca para revisión humana.
    if oferta:
        norm = _norm_etiqueta(oferta)
        if norm in _ETIQUETAS_SIN_OFERTA:
            pass                                    # nombre interno del tipo de precio
        elif _es_numero(oferta) and precio is not None and abs(parse_price_raw(oferta) - precio) < 0.01:
            pass                                    # copia redundante del precio
        else:
            warnings.append("oferta_inesperada")

    return {
        "ofertaUno":    "",
        "precioOferta": precio if precio is not None else "",
        "mecanica":     MECANICA_PRECIO_FIJO,
    }, warnings


# ---------------------------------------------------------------------------
# Fila completa
# ---------------------------------------------------------------------------

def construir_variables(
    parsed: dict,
    descripcion: str,
    mapeo: dict[str, str],
    vigencia_fallback: str = "",
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
    )
    warnings.extend(w)

    valores: dict[str, object] = {
        "precioRegular": parsed.get("precio_anterior"),
        "precioOferta":  mecanica["precioOferta"],
        "ofertaUno":     mecanica["ofertaUno"],
    }
    out["mecanica"] = mecanica["mecanica"]

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
