# -*- coding: utf-8 -*-
"""Relleno de capacidad: cuántas "X" entra de verdad en cada cuadro.

Sirve para ver el cartel en el peor caso ANTES de tener el dato real. El
preview normal muestra el primer producto del Excel, y ese producto puede no
tener decimales, o traer un precio de dos cifras donde mañana va uno de
cuatro: el cuadro se ve holgado y el problema recién aparece al imprimir la
tanda. Con el relleno, cada cuadro se muestra lleno hasta el borde de lo que
su caja y su cuerpo permiten, así se ve de entrada cuánto entra.

Se calcula con la MISMA tabla de métricas que usa el render final
(font_metrics), no con un promedio: la cuenta que se ve en pantalla es la
misma que decide el achique al exportar.
"""
from __future__ import annotations

from app.services.cenefas.font_metrics import ancho_texto_cm
from app.services.cenefas.variables import DECIMAL_VARS

# Cuadros que se rellenan. Son los que llevan dato variable y cambian de
# largo con cada producto: los precios (y sus decimales) y la descripción.
# Las etiquetas fijas del diseño ("unidad", "Comprando 2") no se tocan --
# su texto no depende del Excel y rellenarlas solo taparía el cartel.
VARIABLES_RELLENABLES: frozenset[str] = frozenset({
    "descripcion",
    "precioOferta", "precioRegular", "precioBanco",
    *DECIMAL_VARS,
})

# Margen interno de PowerPoint (0,254 cm por lado). Mismo criterio que
# _INSET_CM en component_renderer: el texto nunca llega al borde de la caja.
_INSET_CM = 0.508

# Tope de seguridad: si una caja es enorme respecto del cuerpo, no tiene
# sentido devolver cientos de caracteres.
_MAX_CARACTERES = 60


def _cabe(texto: str, ancho_cm: float, font_size: float,
          familia: str | None, bold: bool) -> bool:
    return ancho_texto_cm(texto, font_size, familia, bold) <= ancho_cm


def texto_de_capacidad(
    ancho_caja_cm: float,
    alto_caja_cm: float,
    font_size: float,
    familia: str | None,
    bold: bool,
    envuelve: bool,
) -> str:
    """El relleno de "X" más largo que entra en esa caja a ese cuerpo.

    `envuelve` distingue la descripción (texto real, va en varias líneas y se
    corta por palabra) de un precio (un solo bloque sin dónde cortarse, que
    ocupa una sola línea).
    """
    if not font_size or ancho_caja_cm is None or ancho_caja_cm <= 0:
        return "X"
    usable = max(0.1, ancho_caja_cm - _INSET_CM)

    if not envuelve:
        texto = "X"
        while len(texto) < _MAX_CARACTERES and _cabe(texto + "X", usable, font_size, familia, bold):
            texto += "X"
        return texto

    # Con wrap: se arman palabras de 4 letras separadas por espacio y se
    # agregan hasta llenar el alto disponible. El alto de línea es el mismo
    # 1,2 del cuerpo que usa el render.
    alto_linea = font_size / 72.0 * 2.54 * 1.2
    max_lineas = max(1, int((alto_caja_cm or alto_linea) / alto_linea)) if alto_linea else 1
    palabras: list[str] = []
    lineas = 1
    actual = ""
    while lineas <= max_lineas and len(palabras) < _MAX_CARACTERES:
        candidata = f"{actual} XXXX".strip()
        if _cabe(candidata, usable, font_size, familia, bold):
            actual = candidata
            palabras.append("XXXX")
        else:
            lineas += 1
            if lineas > max_lineas:
                break
            actual = "XXXX"
            palabras.append("XXXX")
    return " ".join(palabras) if palabras else "XXXX"


def _variables_del_componente(comp: dict) -> set[str]:
    usadas: set[str] = set()
    if comp.get("variable"):
        usadas.add(comp["variable"])
    for seg in (comp.get("segments") or []):
        if seg.get("type") == "variable" and seg.get("value"):
            usadas.add(seg["value"])
    return usadas


def capacidad_por_componente(definition: dict) -> dict[str, str]:
    """{id de componente -> texto de relleno} para los cuadros rellenables.

    Se indexa por el id del componente (no por variable) porque la misma
    variable puede aparecer en cuadros de distinto tamaño: en la 6xA4 hay
    seis <<precioOferta>>, y lo que interesa es cuánto entra en CADA uno.
    """
    salida: dict[str, str] = {}
    for c in definition.get("components", []):
        if c.get("type") != "text":
            continue
        usadas = _variables_del_componente(c)
        if not usadas or not (usadas & VARIABLES_RELLENABLES):
            continue
        b = c.get("base_bounds") or {}
        if not b.get("width"):
            continue
        estilo = c.get("style") or {}
        cuerpo = estilo.get("font_size")
        if c.get("segments") and not c.get("_manual_font_override"):
            tam_segs = [
                (seg.get("style") or {}).get("font_size")
                for seg in c["segments"] if (seg.get("style") or {}).get("font_size")
            ]
            if tam_segs:
                cuerpo = max(tam_segs)
        if not cuerpo:
            continue
        salida[c["id"]] = texto_de_capacidad(
            b["width"], b.get("height") or 0,
            cuerpo, estilo.get("font_family"), bool(estilo.get("font_bold")),
            envuelve="descripcion" in usadas,
        )
    return salida
