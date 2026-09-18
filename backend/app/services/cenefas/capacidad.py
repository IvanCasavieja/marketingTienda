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

from app.services.cenefas.font_metrics import ancho_texto_cm, digito_mas_ancho, pt_efectivo
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
    """El relleno más largo que entra en esa caja a ese cuerpo.

    `envuelve` distingue la descripción (texto real, va en varias líneas y se
    corta por palabra) de un precio (un solo bloque sin dónde cortarse, que
    ocupa una sola línea), y además decide CON QUÉ se rellena:

    - La descripción, con "X": es texto, y la X es de las letras más anchas.
    - Un precio, con el DÍGITO MÁS ANCHO de su tipografía, no con "X".

    Lo segundo no es un detalle. En Impact --la fuente de los precios-- la "X"
    mide 0,4800 em y el "6" 0,5400: la X es un 11% MÁS ANGOSTA que el dígito
    más ancho, así que el relleno prometía lugar para más caracteres de los que
    después entraban de verdad. En Franklin Gothic pasa lo mismo, 3,4% corto.
    En las otras siete la X sobra ancho y el relleno quedaba conservador, que
    es el lado seguro -- por eso el error solo se veía en los precios grandes,
    que son justo donde importa.

    Esto es además la vara con la que se elige el cuerpo que se escribe en una
    regla de tamaño (`set_font_size`): la regla condiciona por CANTIDAD de
    caracteres, y en Impact la cantidad no determina el ancho, así que el pt
    hay que elegirlo para el peor caso. El peor caso es esto.
    """
    if not font_size or ancho_caja_cm is None or ancho_caja_cm <= 0:
        return "X"
    usable = max(0.1, ancho_caja_cm - _INSET_CM)

    if not envuelve:
        relleno = digito_mas_ancho(familia)
        texto = relleno
        while len(texto) < _MAX_CARACTERES and _cabe(texto + relleno, usable, font_size, familia, bold):
            texto += relleno
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
        # El cuerpo con el que se DIBUJA, no el declarado: un pedazo volado
        # (superíndice) sale a ~2/3 y entran más caracteres de los que la
        # cuenta cruda decía. Sin esto, el precio de Congelados A4 --220 pt
        # declarados, ~145 dibujados-- rellenaba con dos dígitos cuando en el
        # cartel real entran varios más.
        cuerpo = pt_efectivo(estilo.get("font_size"), estilo.get("baseline"))
        if c.get("segments") and not c.get("_manual_font_override"):
            tam_segs = [
                pt_efectivo((seg.get("style") or {}).get("font_size"),
                            (seg.get("style") or {}).get("baseline", estilo.get("baseline")))
                for seg in c["segments"] if (seg.get("style") or {}).get("font_size")
            ]
            tam_segs = [t for t in tam_segs if t]
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


# ---------------------------------------------------------------------------
# Relleno POR SEGMENTO
# ---------------------------------------------------------------------------
#
# Hasta el 18/09/2026 la capacidad se calculaba de a un cuadro entero: un
# string por componente, con el cuerpo MAXIMO de sus segmentos, y se llenaba la
# caja de digitos. Eso alcanzaba mientras cada variable viviera en su propio
# cuadro.
#
# Lo rompio la plantilla nueva de Alemania ("Fiesta Alemania-202608-A4"), que
# mete todo el bloque del precio en UN cuadro de tres segmentos:
#
#     [ unidadMoneda 60 pt | precioOferta 140 pt | decimalPrecioOferta 36 pt ]
#
# Con el criterio viejo el cuadro se llenaba con un solo bloque de digitos a
# 140 pt: el decimal no se dibujaba nunca con su propio cuerpo. Ivan lo reporto
# asi: "el primer precio que tengo de oferta no tiene decimal, y no tengo como
# verlo ni como ordenarlo porque el relleno de x no funciona en esa variable".
#
# De paso se corrige algo que el relleno viejo tambien mentia: no todo segmento
# es de largo libre. El simbolo de moneda solo puede ser "$" o "U$S", y un
# decimal es SIEMPRE coma y dos cifras. Rellenarlos con digitos hasta el borde
# mostraba un peor caso que no existe. Ahora lo de largo conocido se mide tal
# cual, y recien lo que SOBRA se reparte entre los segmentos de largo variable
# (el precio): esa es la cuenta que de verdad importa, cuantos digitos entran
# al lado del simbolo y del decimal.

# El peor caso real del simbolo de moneda. Los unicos dos valores que escribe
# el Convertidor son "$" y "U$S" (columna MONEDA del export de gestion), asi
# que el ancho maximo es este y no "cuantos digitos entren".
_PEOR_CASO_MONEDA = "U$S"


def _estilo_segmento(comp: dict, seg: dict) -> tuple[float | None, str | None, bool]:
    """(cuerpo efectivo, familia, negrita) con los que se DIBUJA ese segmento.

    Misma regla que al dibujar y al medir (_piezas_con_tamano_manual): lo que
    se pone a mano manda donde se pone. Si la caja tiene tamano manual, todos
    los segmentos toman el de la caja salvo el que tenga el suyo propio puesto
    a mano; si no, cada segmento usa el suyo y cae al de la caja si no tiene.
    """
    est_comp = comp.get("style") or {}
    est_seg = seg.get("style") or {}
    propio = est_seg.get("font_size")
    if seg.get("_manual_font_override") and propio:
        pt = propio
    elif comp.get("_manual_font_override"):
        pt = est_comp.get("font_size")
    else:
        # 18 pt es el default real de PowerPoint cuando nadie declara tamano.
        pt = propio or est_comp.get("font_size") or 18.0
    baseline = est_seg.get("baseline", est_comp.get("baseline"))
    familia = est_seg.get("font_family") or est_comp.get("font_family")
    bold = bool(est_seg.get("font_bold", est_comp.get("font_bold")))
    return pt_efectivo(pt, baseline), familia, bold


def _texto_fijo_del_segmento(seg: dict, familia: str | None) -> str | None:
    """El relleno de un segmento de largo CONOCIDO, o None si es de largo libre.

    - Un pedazo estatico del diseno ("Comprando 2", "x") ya es su propio peor
      caso: se mide tal cual.
    - `unidadMoneda`: "U$S".
    - Cualquier decimal: coma y dos cifras, con el digito mas ancho de la
      tipografia (no un "6" literal: en Impact el "1" mide 0,38 em y el "6"
      0,54, ver digito_mas_ancho).
    """
    if seg.get("type") != "variable":
        return str(seg.get("value", "") or "")
    var = seg.get("value")
    if var == "unidadMoneda":
        return _PEOR_CASO_MONEDA
    if var in DECIMAL_VARS:
        return "," + digito_mas_ancho(familia) * 2
    return None


def capacidad_por_segmento(comp: dict) -> list[str] | None:
    """Relleno de CADA segmento del cuadro, en el orden de comp["segments"].

    Devuelve None si el cuadro tiene menos de 2 segmentos: ahi el relleno del
    cuadro entero (capacidad_por_componente) ya es correcto y el front lo sigue
    usando.

    El orden del calculo importa: primero se mide todo lo de largo conocido
    --estaticos, moneda, decimales-- con SU propio cuerpo, y recien el ancho
    que sobra se reparte entre los segmentos de largo libre (los precios).
    Medir todo con el cuerpo maximo, como se hacia antes, daba un decimal de
    140 pt que en el cartel se dibuja a 36.

    Si hay MAS DE UN segmento de largo libre, el sobrante se reparte en partes
    iguales. Es una decision arbitraria --ninguna plantilla de hoy tiene dos
    precios variables en la misma caja-- pero es la unica neutral: cualquier
    otro reparto le estaria prometiendo lugar a un precio a costa del otro, y
    el relleno existe justamente para no prometer lugar que no hay.
    """
    segs = comp.get("segments") or []
    if len(segs) < 2:
        return None
    b = comp.get("base_bounds") or {}
    ancho = b.get("width")
    if not ancho or ancho <= 0:
        return None
    usable = max(0.1, ancho - _INSET_CM)

    # Primera pasada: lo de largo conocido, cada uno con su cuerpo.
    fijos: list[str | None] = []
    ocupado = 0.0
    libres: list[int] = []
    estilos: list[tuple[float | None, str | None, bool]] = []
    for i, seg in enumerate(segs):
        cuerpo, familia, bold = _estilo_segmento(comp, seg)
        estilos.append((cuerpo, familia, bold))
        texto = _texto_fijo_del_segmento(seg, familia)
        fijos.append(texto)
        if texto is None:
            libres.append(i)
        elif cuerpo:
            ocupado += ancho_texto_cm(texto, cuerpo, familia, bold)

    salida = [t if t is not None else "" for t in fijos]
    if not libres:
        return salida

    cuota = max(0.0, usable - ocupado) / len(libres)
    for i in libres:
        cuerpo, familia, bold = estilos[i]
        seg = segs[i]
        # La descripcion es texto, y la "X" es de las letras mas anchas; un
        # precio se rellena con el digito mas ancho de su tipografia (el
        # porque, largo, esta en texto_de_capacidad). Aca no se envuelve en
        # varias lineas: un segmento comparte renglon con los otros.
        relleno = "X" if seg.get("value") == "descripcion" else digito_mas_ancho(familia)
        if not cuerpo:
            salida[i] = relleno
            continue
        # Siempre al menos un caracter: un segmento vacio en el preview se lee
        # como "esta variable no existe", que es justo la confusion que este
        # relleno viene a sacar.
        texto = relleno
        while len(texto) < _MAX_CARACTERES and _cabe(texto + relleno, cuota, cuerpo, familia, bold):
            texto += relleno
        salida[i] = texto
    return salida


def segmentos_por_componente(definition: dict) -> dict[str, list[str]]:
    """{id de componente -> relleno de cada segmento} para los cuadros de 2+.

    Hermana de capacidad_por_componente y con el MISMO filtro de que cuadros
    entran, para que el preview no empiece a rellenar etiquetas fijas del
    diseno. Los cuadros de una sola variable no aparecen aca: para esos el
    front sigue usando `capacidad`.
    """
    salida: dict[str, list[str]] = {}
    for c in definition.get("components", []):
        if c.get("type") != "text":
            continue
        usadas = _variables_del_componente(c)
        if not usadas or not (usadas & VARIABLES_RELLENABLES):
            continue
        rellenos = capacidad_por_segmento(c)
        if rellenos is not None:
            salida[c["id"]] = rellenos
    return salida
