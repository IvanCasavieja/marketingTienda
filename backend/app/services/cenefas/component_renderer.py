"""Renderer de componentes v2 — genera PPTX desde definición JSON de componentes."""
import copy
import io
import math
import re

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Cm, Pt

from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.font_metrics import ancho_texto_cm, pt_efectivo
from app.services.cenefas.formatters import split_caps
# Lo único que el motor genérico sabe del mundo de pruebas: una llamada al
# final del render, que no hace NADA en los otros mundos. Ver pruebas.py.
from app.services.cenefas.pruebas import aplicar_autofit as aplicar_autofit_de_pruebas
from app.services.cenefas.layout_engine import compute_layout, get_format
from app.services.cenefas.rules_engine import (
    apply_font_sizes,
    apply_visibility,
    evaluate_font_size_rules,
    evaluate_rules,
    evaluate_segment_font_size_rules,
    evaluate_segment_rules,
)
from app.services.cenefas.variables import DECIMAL_OF, DECIMAL_VARS, PRICE_VARS

# ---------------------------------------------------------------------------
# Dimensiones de slide por formato
# ---------------------------------------------------------------------------

FORMAT_SLIDES: dict[str, tuple] = {
    "a4":      (Cm(21.0),  Cm(29.7)),
    "a3":      (Cm(29.7),  Cm(42.0)),
    "3xa4":    (Cm(21.0),  Cm(29.7)),   # A4 portrait completo, 3 franjas verticales
    "pinchos": (Cm(21.0),  Cm(29.7)),   # A4 portrait completo, grilla 3×2
    "a5":      (Cm(14.85), Cm(21.0)),
    "6xa4":    (Cm(21.0),  Cm(29.7)),   # A4 portrait completo, grilla 3×2 (arte propio)
}

ALIGN_MAP = {
    "left":   PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right":  PP_ALIGN.RIGHT,
}

# ---------------------------------------------------------------------------
# Transforms de valores
# ---------------------------------------------------------------------------

def apply_transform(value: str, transform: str | None) -> str:
    """Aplica la transformación al valor del campo."""
    if not value or not transform or transform in ("none", "smart_bold"):
        return value or ""

    if transform in ("price_full", "price_integer", "price_decimal"):
        # value ya viene formateado como "$1.250,90" desde data_engine
        num = re.sub(r"[^\d.,]", "", value)
        if transform == "price_full":
            return value
        if transform == "price_integer":
            return num.rsplit(",", 1)[0] if "," in num else num
        if transform == "price_decimal":
            return ("," + num.rsplit(",", 1)[1]) if "," in num else ""

    if transform == "combo_quantity":
        m = re.match(r"(\d+X)", value.upper())
        return m.group(1) if m else value

    if transform == "combo_price":
        return value  # ya es el precio formateado

    if transform == "uppercase":
        return value.upper()

    return value


# ---------------------------------------------------------------------------
# Achique automático de texto que no entra
# ---------------------------------------------------------------------------
#
# Única excepción a la regla de "el motor respeta el PPTX tal cual". Aplica a
# la descripción y a los precios: los nombres reales de gestión pasan seguido
# de los 60 caracteres y desbordan sobre el precio de al lado, y un precio de
# cuatro dígitos ("1.919") no entra en un cuadro calibrado para tres --
# PowerPoint lo parte al medio ("1.91" + "9", visto en un cartel real).
#
# Se sacó en 08/2026 junto con el resto de los ajustes automáticos y volvió a
# pedido explícito, primero para la descripción y después para el precio.
#
# Lo que NO volvió: el corrimiento vertical del cuadro de precio cuando la
# descripción desborda. Acá solo se achica texto; ninguna caja se mueve de
# donde la puso el diseño.


# Inset interno por defecto de PowerPoint: 0,1" a cada lado (lIns/rIns =
# 91440 EMU). Antes se descontaba 0,4 cm y el word-wrap simulado cortaba una
# palabra más tarde que el real.
_INSET_CM = 0.508

# Interlineado tipico de una caja sin espaciado explicito.
_INTERLINEADO = 1.2

# Letras que bajan de la línea de base.
_DESCENDENTES = frozenset("gjpqy")


def _alto_ultima_linea(texto: str) -> float:
    """Alto de la última línea, en múltiplos del tamaño de fuente.

    El interlineado separa una línea de la siguiente, pero debajo de la última
    no hay nada que separar: lo que puede chocar con el cuadro de abajo es la
    TINTA, y hasta dónde llega depende de qué diga el texto.

    Contando 1,2 em también para la última línea, un precio de una sola línea a
    140 pt "necesitaba" 5,93 cm donde el diseño le da 5,51 -- y el motor
    terminaba achicando los 145 precios de la A5 uno por uno sin que ninguno
    estuviera pisando nada. Un precio son dígitos: no bajan de la base, su tinta
    no pasa de la altura de mayúscula.
    """
    if _DESCENDENTES & set(texto):
        return 1.15
    if any(c.islower() for c in texto):
        return 1.05
    return 0.95


def _alto_texto_cm(lineas: int, font_size: float, texto: str) -> float:
    """Alto que ocupa la tinta de un texto de N líneas a ese tamaño."""
    factor = (lineas - 1) * _INTERLINEADO + _alto_ultima_linea(texto)
    return factor * font_size / 72 * 2.54


def _ancho_medido_cm(
    texto: str, font_size: float, font_family: str | None, bold: bool
) -> float:
    """Ancho del texto tal como se va a dibujar, en centímetros.

    Se mide parte por parte porque el renderer pone en negrita las palabras en
    mayúsculas --la marca: "SER", "LA SERENÍSIMA"-- vía split_caps. Medir todo
    el texto con un único flag de negrita sobra o falta ancho según el caso, y
    en cajas ajustadas eso alcanza para errar por una línea entera, que es
    justo la diferencia entre "entra" y "se monta sobre el precio".
    """
    return sum(
        ancho_texto_cm(parte, font_size, font_family, bold or es_mayus)
        for parte, es_mayus in split_caps(texto)
    )


def _estimate_wrapped_lines(
    text: str, box_width_cm: float | None, font_size: float | None,
    bold: bool = False, font_family: str | None = None,
) -> int:
    """A cuántas líneas se parte el texto con word-wrap en una caja de ese ancho.

    Simula el criterio "voraz" de PowerPoint (agregar palabras hasta que no
    entran más) midiendo cada palabra con las métricas REALES de la tipografía
    (ver font_metrics.py). Antes se usaba un ancho de caracter promedio
    inventado y erraba de a una línea entera, que es justo la diferencia entre
    "entra" y "se le monta encima al precio".
    """
    if not text or not box_width_cm or not font_size:
        return 1
    usable_cm = max(0.1, box_width_cm - _INSET_CM)

    lineas = 1
    actual = ""
    for palabra in text.split():
        tentativa = palabra if not actual else actual + " " + palabra
        if _ancho_medido_cm(tentativa, font_size, font_family, bold) > usable_cm and actual:
            lineas += 1
            actual = palabra
        else:
            actual = tentativa
    return lineas


def _texto_resuelto(comp: dict, product: dict) -> str:
    """El texto que ese componente va a imprimir, ya con los valores puestos."""
    segs = comp.get("segments")
    if segs:
        partes = []
        for seg in segs:
            if seg.get("type") == "variable":
                partes.append(str(product.get(seg.get("value"), "") or ""))
            else:
                partes.append(str(seg.get("value", "") or ""))
        return "".join(partes)
    variable = comp.get("variable")
    if variable:
        return str(product.get(variable, "") or "")
    return str(comp.get("static_value", "") or "")


# Piso de achique: por debajo de esto el texto deja de ser legible en un cartel
# de góndola, y es preferible que se note el desborde a imprimir algo que nadie
# puede leer de lejos.

# PowerPoint no dibuja el texto pegado al borde del cuadro: deja un margen
# interno, 0,25 cm de cada lado por defecto. Medir contra el ancho DIBUJADO de
# la caja le hace creer al motor que tiene medio centimetro mas del que va a
# tener, y ese medio centimetro es justo lo que separa "entra en una linea" de
# "PowerPoint lo parte al medio": la cocarda de 2,60 cm del Rompe del Finde
# tiene 2,09 utiles, y "2x$299" mide 1,97 -- entraba por 0,12 cm segun el motor
# y salia impresa como "2x$29 / 9".

# Se achica cualquier cuadro que traiga DATO del Excel y no entre. Un cuadro de
# texto fijo del diseño ("OFERTA", "PRECIO REGULAR") no se toca nunca: su
# contenido no cambia entre productos, así que si el diseñador lo dejó justo,
# está justo a propósito.
#
# Antes la lista era sólo {descripción + precios} y por eso un código de varios
# SKU ("594879/80/81/82/83 -593838/39/40 - 621032 - ...", 86 caracteres) se
# partía en tres líneas y se montaba sobre la descripción.
#
# Los decimales YA NO se excluyen de este achique (hasta 09/2026 sí, con el
# argumento de que "son siempre dos dígitos, nunca desbordan" -- cierto
# mientras el decimal viviera SIEMPRE pegado a su entero en el mismo cuadro,
# donde el achique combinado de _segmentos_medibles ya los trata juntos).
# Con plantillas que separan cada variable en su propio cuadro (Preciazos de
# la Tienda, 09/2026) un decimal puede terminar solo en su cuadro, y esa
# garantía deja de valer: un decimal estilizado más grande que su entero
# ("$109,65" con la coma en tamaño destacado) no entraba en el cuadro medido
# para el diseño y PowerPoint lo recortaba ("109,6") sin que nada lo
# detectara ni lo achicara. Ver también _EMPAREJAR_DECIMAL más abajo: cuando
# entero y decimal son cada uno su propio cuadro, además de dejar de
# desbordar hace falta que se achiquen JUNTOS a la misma escala.


def _variables_del_componente(c: dict) -> set[str]:
    """Las variables que ese componente imprime, sea directo o por segmentos."""
    if c.get("variable"):
        return {c["variable"]}
    return {
        seg["value"] for seg in (c.get("segments") or [])
        if seg.get("type") == "variable" and seg.get("value")
    }


def _segmentos_medibles(comp: dict, product: dict, escala: float = 1.0) -> list[tuple[str, float]]:
    """(texto, tamaño) de cada pedazo del cuadro, ya resuelto contra el producto.

    Un cuadro de precio tiene tres pedazos con tamaños MUY distintos: el "$" a
    100 pt, el número a 180 y los centavos a 90. Medirlo todo con un solo
    tamaño --el del primer run, que es el "$"-- daba un ancho como la mitad del
    real: el motor creía que "$147,20" entraba en 12,35 cm, no achicaba, y
    PowerPoint terminaba partiendo los centavos en dos líneas que se caían
    sobre la cenefa de abajo (visto en la 3xA4 del 27/08).

    Devuelve [] cuando el cuadro no tiene tamaños por segmento; ahí la medición
    de siempre, con un único tamaño, es correcta.
    """
    segs = comp.get("segments") or []
    if not any((seg.get("style") or {}).get("font_size") for seg in segs):
        return []
    # 18 pt es el default real de PowerPoint cuando el cuadro no declara tamano.
    base = (comp.get("style") or {}).get("font_size") or 18.0
    salida: list[tuple[str, float]] = []
    for seg in segs:
        if seg.get("type") == "variable":
            texto = str(product.get(seg.get("value"), "") or "")
        else:
            texto = str(seg.get("value", "") or "")
        if not texto:
            continue
        # Un pedazo VOLADO (superíndice) lo dibuja PowerPoint a ~2/3 del cuerpo
        # que declara, sin cambiar el número. Medirlo por el declarado da un
        # rectángulo una vez y media más grande que el real. Ver pt_efectivo
        # en font_metrics.py. Mismo criterio en _piezas_con_tamano_manual.
        tam = ((seg.get("style") or {}).get("font_size") or base) * escala
        voladita = (seg.get("style") or {}).get("baseline",
                                                (comp.get("style") or {}).get("baseline"))
        salida.append((texto, pt_efectivo(tam, voladita) or tam))
    return salida


def _piezas_con_tamano_manual(comp: dict, product: dict) -> list[tuple[str, float]]:
    """(texto, tamaño) de cada pedazo de un cuadro con un tamaño puesto a MANO,
    en la caja o en alguno de sus segmentos.

    Al dibujar (_populate_text_frame), con tamaño manual en la caja cada
    segmento toma el cuerpo de la caja -- salvo el segmento que tiene su PROPIO
    tamaño puesto a mano (`_manual_font_override` en el segmento), que conserva
    el suyo. Medir tiene que dar exactamente lo mismo que dibujar, así que acá
    se aplica la misma regla.

    Criterio de Ivan (11/09/2026): lo que se pone a mano manda donde se pone.
    """
    fs = (comp.get("style") or {}).get("font_size") or 18.0
    salida: list[tuple[str, float]] = []
    for seg in comp.get("segments") or []:
        if seg.get("type") == "variable":
            texto = str(product.get(seg.get("value"), "") or "")
        else:
            texto = str(seg.get("value", "") or "")
        if not texto:
            continue
        propio = (seg.get("style") or {}).get("font_size")
        if seg.get("_manual_font_override") and propio:
            tam = propio
        elif comp.get("_manual_font_override"):
            tam = fs
        else:
            # Caja sin tamaño manual: cada segmento se dibuja con el suyo.
            tam = propio or fs
        # Y si el pedazo va VOLADO, PowerPoint lo dibuja a ~2/3 del cuerpo que
        # declara, sin cambiar el número. Medir con el declarado daba un
        # rectángulo una vez y media más grande que el real, así que un cuadro
        # con el "$" o los centavos volados parecía pisar a su vecino cuando
        # no lo pisaba. Ver pt_efectivo en font_metrics.py.
        seg_baseline = (seg.get("style") or {}).get("baseline",
                                                    (comp.get("style") or {}).get("baseline"))
        salida.append((texto, pt_efectivo(tam, seg_baseline) or tam))
    return salida


# Pares de variables que NUNCA se dibujan juntas: si la primera trae valor, la
# segunda no se dibuja aunque el diseno tenga su cuadro.
#
# `promoOferta` (el literal de la mecanica, "6x4") y `precioOferta` (el precio)
# ocupan EL MISMO lugar del cartel en las plantillas de Redexpres: el diseno
# pone el cuadro de promoOferta encima del del precio. Superponer dos cuadros de
# texto no tapa nada --se leen los dos encimados-- asi que la exclusion se
# resuelve acá: cuando hay mecanica se dibuja el literal, cuando no, el precio.
#
# OJO: esto vale para dos cuadros que compiten por EL MISMO lugar. Una cocarda
# (tipoOferta) tambien vive encimada al precio y NO compite con el: se lee
# junto, no en lugar de. Ver abajo por que salio de esta lista.
_EXCLUYENTES: dict[str, tuple[str, ...]] = {
    # Cuando promoOferta trae valor y el diseno TIENE su cuadro, tapa al
    # precio. Solo aplica si el cuadro de promoOferta existe de verdad:
    # Rompe del Finde no lo tiene y su precio sigue saliendo.
    #
    # `tipoOferta` estaba en esta lista desde el 2026-08-28 y se saco el
    # 17/09/2026: la cocarda de un COMBO se perdia. Entro cuando promoOferta
    # era solo de M x N, donde la cocarda y el cuadro grande llevan el MISMO
    # literal y la A4 REDEX imprimia "2X1" dos veces (mundo hogar, pag. 54).
    # Pero la geometria es la senal equivocada para ESTE par: una cocarda se
    # dibuja a proposito pisando el cuadro del precio, asi que el solape no
    # distingue "repetido" de "puesto ahi por el diseno". En un combo
    # tipoOferta="3x" y promoOferta="160" son cosas DISTINTAS que se leen
    # juntas ("3x $160"), y la regla borraba la cocarda en cuanto el diseno
    # las encimaba mas del 50%: la 3xA4 de Redexpres las encima 60-70% y
    # perdia el "3x" en toda fila de combo, mientras la A4 --mismo diseno,
    # 43% de solape-- lo imprimia bien (visto en vivo, Empanadas horneadas
    # congeladas, 17/09/2026).
    #
    # El literal duplicado de M x N que motivo la entrada ya no depende de
    # esto y queda cubierto dos veces: el Convertidor deja `tipoOferta` VACIA
    # en M x N desde el 16/09/2026 (ver resolver_mecanica), y el chequeo por
    # CONTENIDO de _render_slide (literales_repetidos, 07/09/2026) apaga la
    # cocarda cuando va a imprimir exactamente lo mismo que promoOferta,
    # esten las cajas donde esten.
    #
    # Los decimales siguen a su entero: sin esto, un M x N de "6x4" imprimia
    # el literal y al lado le quedaba colgado el ",33" del precio que ya no
    # se ve.
    "promoOferta": ("precioOferta", "decimalPrecioOferta"),
}


# Cuanto tiene que bajar otro cuadro para contar como "el de abajo" y no como
# un vecino puesto a la misma altura. Medio centimetro: menos que eso, en un
# diseno hecho a mano, es desprolijidad de posicionamiento, no una fila nueva.

# Cuánto del alto del más chico de los dos tiene que caer dentro del rango
# vertical del más grande para contar como "superpuesto a propósito", y
# cuánto más bajo tiene que ser el chico respecto del grande. No es 100%:
# los diseños reales no calzan al milímetro (caso real, "Comprando 2" contra
# precioBanco: 78,8% de solape, no lo agarraba un chequeo de bordes exacto).
_SOLAPE_MIN_DECORACION = 0.7
_ALTO_MAX_DECORACION = 0.6

# Variables que por vocabulario (variables.py) son SIEMPRE una etiqueta/leyenda
# chica pensada para flotar pegada a un precio, nunca contenido "de verdad"
# compitiendo por su propio espacio -- ver ancho/alto/relación de solape NO
# alcanza para distinguir esto de un vecino real: probado con números reales,
# "Comprando 2" sobre precioOferta (46,7% del ancho, 99,5% de solape vertical)
# y una descripción angosta al lado de un precio ancho y vacío (caso real
# "vecina chata", 42,5% del ancho, 100% de solape) dan proporciones casi
# idénticas -- geométricamente indistinguibles. La única señal confiable es
# CUÁL variable es, no cuánto mide su caja.
_VARIABLES_ETIQUETA_FLOTANTE = frozenset({"tipoOfertaComprando", "tipoOferta", "unidad"})


def _son_decoracion_superpuesta(a: dict, b: dict) -> bool:
    """True si uno de los dos cuadros es una etiqueta chica que vive
    superpuesta a propósito dentro del rango vertical del otro, mucho más
    grande -- señal de que el diseño la dibujó ahí a propósito (una cocarda
    o "Comprando 2" flotando sobre/dentro de un precio gigante), no una fila
    o columna vecina que compite por el mismo espacio. Da igual cuál de los
    dos se pase como `a` o `b`: la relación es simétrica.

    Caso real que motivó esto (Cenefas A4 Preciazos, 09/2026): la etiqueta
    "Comprando 2" (alto 2,82cm) vive superpuesta arriba del cuadro de
    precioOferta (alto 7,95cm) a propósito -- el diseño la dibuja ahí para
    que se lea "Comprando 2" arriba del número grande. _ancho_disponible_cm
    la tomaba como pared a la derecha del precio (ancho disponible 2,2cm en
    una caja de 17,5) y _alto_disponible_cm tomaba al precio como techo de la
    etiqueta chica (alto disponible 0,7cm) -- las dos cosas para el MISMO
    cartel, con el precio y la etiqueta achicándose al piso (180pt→99pt,
    30pt→16,5pt) sin que ninguno de los dos cuadros desbordara ni se
    superpusiera de verdad: el texto real ("129" a 180pt, "Comprando 2" a
    30pt) entraba perfecto en su caja, el problema era puramente esta
    detección de vecino.

    No reemplaza el resto de la heurística de vecinos -- solo la desactiva
    para ESTE par puntual cuando la geometría deja claro que uno vive adentro
    del otro. Un cuadro de decimal al lado del entero (caso legítimo, ver
    comentarios de _alto_disponible_cm/_ancho_disponible_cm) tiene alto
    parecido al del entero, así que "sensiblemente menos alto" no lo agarra
    y sigue bloqueando como corresponde.

    Requiere ADEMÁS que uno de los dos sea una de _VARIABLES_ETIQUETA_FLOTANTE
    -- la relación de alto/ancho/solape sola no alcanza para distinguir esto
    de un vecino real (ver el comentario de esa constante): sin este filtro
    de variable, cualquier caja chica y baja que cayera por casualidad dentro
    del rango vertical de una caja mucho más ancha (ej. una descripción al
    lado de un precio ancho y vacío, caso real "vecina chata") se confundía
    con una decoración y dejaba de contar como vecina de verdad -- rompía
    exactamente el chequeo que _ancho_disponible_cm existe para hacer.
    """
    if not ((_variables_del_componente(a) | _variables_del_componente(b)) & _VARIABLES_ETIQUETA_FLOTANTE):
        return False
    ba = a.get("computed_bounds") or a.get("base_bounds") or {}
    bb = b.get("computed_bounds") or b.get("base_bounds") or {}
    y1, h1 = ba.get("y"), ba.get("height")
    y2, h2 = bb.get("y"), bb.get("height")
    if y1 is None or h1 is None or y2 is None or h2 is None:
        return False
    if h1 <= h2:
        chico_y, chico_h, grande_h = y1, h1, h2
    else:
        chico_y, chico_h, grande_h = y2, h2, h1
    if grande_h <= 0 or chico_h <= 0 or chico_h >= grande_h * _ALTO_MAX_DECORACION:
        return False
    solape = min(y1 + h1, y2 + h2) - max(y1, y2)
    return solape / chico_h >= _SOLAPE_MIN_DECORACION


# Campo donde vive la relación EXPLÍCITA entre un cuadro fijo (el "$") y el
# cuadro cuyo valor acompaña. Lo escribe la persona en el editor, y es la
# ÚNICA forma de que dos cuadros queden emparejados: no se adivina nunca.
#
# Hubo una heurística geométrica que deducía la pareja por solape de cajas.
# Se eliminó el 07/09/2026 por pedido explícito de Ivan. Habia fallado de
# todas las formas posibles --emparejó un "$" con el decimal vacío en vez de
# con su precio, en la 6xA4 con el "$" de la celda de al lado, y en Gran
# Bretaña con un cuadro a 10 cm-- y lo peor es que fallaba EN SILENCIO: de
# una pareja equivocada salen un límite de ancho y una exención de choque que
# no corresponden, y nadie se entera.
#
# Sacarla mejoró los números: renderizando las 17 plantillas con 6 productos,
# cambian 20 de 559 cuadros -- 12 quedan MÁS GRANDES (el precio de banco de
# Preciazos A4 pasa de 38,5 a 60 pt en todas las hojas) y 8 bajan entre 0,4 y
# 3,5 pt.
#
# Para proponer relaciones está el botón "Detectar relaciones" del panel, que
# muestra sugerencias y espera confirmación de a una.
_CAMPO_RELACION = "vinculado_a"


def _parejas_declaradas(comps: list[dict]) -> dict[int, dict]:
    """{id(precio) -> bounds del "$"} según lo que la persona declaró."""
    por_uuid = {c.get("id"): c for c in comps if c.get("id")}
    salida: dict[int, dict] = {}
    for c in comps:
        destino_uuid = c.get(_CAMPO_RELACION)
        if not destino_uuid:
            continue
        destino = por_uuid.get(destino_uuid)
        if destino is None:
            continue
        # La relación se declara desde el "$" hacia el precio que acompaña,
        # y acá se indexa al revés (por precio), que es como la consultan
        # _fit_text_to_box y el resolver de solapes.
        salida[id(destino)] = c.get("computed_bounds") or c.get("base_bounds") or {}
    return salida


def _dollar_parejas(comps: list[dict]) -> dict[int, dict]:
    """Para cada precio, los bounds del "$" que lo acompaña -- SOLO si alguien
    lo declaró a mano en el panel de propiedades.

    Antes esto tenía además una heurística que ADIVINABA la pareja mirando
    cuánto se solapaban las cajas. Se saco por pedido explícito de Ivan
    (07/09/2026): "quita eso de la pareja automatica". Adivinar mal tiene
    consecuencias silenciosas y caras --el "$" del precio de banco de Gran
    Bretaña quedaba emparejado con un cuadro a 10 cm, y de esa pareja
    equivocada salían un límite de ancho y una exención de choque que no
    correspondían-- y no hay forma de que la persona se entere de que el motor
    eligió mal.

    Lo que queda es lo declarado: el desplegable "Acompaña al cuadro" del panel
    (`vinculado_a`), y el botón "Detectar relaciones", que PROPONE y espera
    confirmación. Nada se empareja solo.

    Un cuadro con <<unidadMoneda>> (o <<um>>) nunca hizo falta que entrara acá:
    quien lo pone como variable ya decidió dónde va, y se hermana solo entre
    las cenefas de la hoja.
    """
    return dict(_parejas_declaradas(comps))


def _rect_texto_real(comp: dict, product: dict) -> dict | None:
    """El rectángulo que el texto va a OCUPAR de verdad al dibujarse.

    No es la caja declarada: un número más ancho que su caja se dibuja igual,
    centrado, sobresaliendo a los costados. Para saber si un cuadro pisa a
    otro hay que comparar estos rectángulos, no las cajas.
    """
    if comp.get("type") != "text":
        return None
    texto = _texto_resuelto(comp, product).strip()
    if not texto:
        return None
    b = comp.get("computed_bounds") or comp.get("base_bounds") or {}
    if not b.get("width"):
        return None
    style = comp.get("style", {})
    fs    = style.get("font_size") or 12
    fam   = style.get("font_family")
    bold  = bool(style.get("font_bold"))

    piezas = _segmentos_medibles(comp, product)
    if piezas and comp.get("_manual_font_override"):
        # Con el tamaño puesto a mano, _populate_text_frame le fuerza a TODOS
        # los segmentos el cuerpo del componente; el que guarda cada segmento
        # suele estar desactualizado. Medir con ese viejo daba un rectángulo
        # ridículamente chico -- un "64" de 174 pt medido como si fuera de 29,
        # 1,1 cm en vez de 7 -- y ningún choque se detectaba.
        #
        # Salvo el segmento con tamaño propio puesto a mano, que conserva el
        # suyo al dibujar: se mide igual que se dibuja.
        piezas = _piezas_con_tamano_manual(comp, product)
    if piezas:
        ancho = sum(_ancho_medido_cm(t, sz, fam, bold) for t, sz in piezas)
        alto  = _alto_texto_cm(1, max(sz for _, sz in piezas), texto)
    else:
        lineas = _estimate_wrapped_lines(texto, b["width"], fs, bold, fam) if " " in texto else 1
        ancho  = min(_ancho_medido_cm(texto, fs, fam, bold), b["width"]) if lineas > 1 \
                 else _ancho_medido_cm(texto, fs, fam, bold)
        alto   = _alto_texto_cm(lineas, fs, texto)

    align = style.get("align", "center")
    if align == "left":
        x = b["x"]
    elif align == "right":
        x = b["x"] + b["width"] - ancho
    else:
        x = b["x"] + (b["width"] - ancho) / 2.0
    return {"x": x, "y": b["y"], "width": max(0.01, ancho), "height": max(0.01, alto)}


# Cuánto se tienen que pisar dos textos para contar como solape de verdad.
# No es cero: los diseños reales dejan los cuadros rozándose por décimas de
# milímetro y eso no se ve. Medio milímetro cuadrado ya es visible impreso.
_SOLAPE_TEXTO_MIN_CM2 = 0.05

# Para el par entero+decimal de un mismo precio hace falta un piso mas alto:
# el diseño los dibuja pegados y el roce lateral es normal. Medio centimetro
# cuadrado ya es el decimal montado sobre el numero, que es el caso real que
# hay que corregir (el ",50" cayendo debajo del "64" en la A4).
_SOLAPE_PAR_DECIMAL_MIN_CM2 = 0.25


def detectar_solapes(pares: list[tuple[dict, dict]]) -> list[dict]:
    """Los cuadros cuyo texto se va a imprimir ENCIMA de otro. Solo AVISA.

    Hasta el 14/09/2026 esta función no avisaba: achicaba. Bajaba de a 5% al
    cuadro más grande de cada par hasta despejar, con un piso propio de 0,55
    calculado sobre el cuerpo que ya venía achicado por _fit_text_to_box --o
    sea dos pisos multiplicados, 30% del cuerpo que puso el diseño-- y después
    _unificar_tamanos_entre_bandas copiaba ese peor caso a todas las cenefas de
    la hoja. De ahí que una corrida entera saliera impresa a un tercio del
    tamaño aprobado en pantalla.

    Ahora el cuerpo lo declara una regla explícita (ver `set_font_size` en
    rules_engine) y acá no se toca ningún tamaño: se reporta y listo.

    Se reporta --y no se ignora-- porque esto no es una cuestión de estética.
    Un precio impreso sobre otro texto es un cartel inservible, y enterarse en
    la góndola cuesta la corrida entera reimpresa. El aviso sale en el preview,
    antes de confirmar.

    El criterio de qué cuenta como choque se conserva tal cual del resolver
    viejo, que es lo que estaba bien de él: no cualquier roce es un choque. Los
    diseños reales dejan cuadros superpuestos a propósito (el "$" adentro de la
    caja del precio, el decimal pegado a su entero, una etiqueta flotante
    encima), y marcarlos daría un aviso por cartel que nadie leería.
    """
    avisos: list[dict] = []
    _parejas_dollar = _dollar_parejas([c for c, _ in pares])

    # Se guarda el producto de CADA cuadro, no solo el rectángulo: en una hoja
    # multi-cenefa cada celda va contra su propia fila, y el texto del aviso
    # tiene que ser el que de verdad se va a imprimir en ese cuadro.
    rects = []
    for c, prod in pares:
        r = _rect_texto_real(c, prod)
        if r:
            rects.append((c, r, prod))

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            ca, ra, pa = rects[i]
            cb, rb, pb = rects[j]
            ix = min(ra["x"] + ra["width"],  rb["x"] + rb["width"])  - max(ra["x"], rb["x"])
            iy = min(ra["y"] + ra["height"], rb["y"] + rb["height"]) - max(ra["y"], rb["y"])
            if ix <= 0 or iy <= 0 or ix * iy < _SOLAPE_TEXTO_MIN_CM2:
                continue
            # Cajas declaradas superpuestas a propósito por el diseño (el "$"
            # metido dentro del cuadro del precio, la etiqueta flotante encima)
            # no son un choque: el arte las dibujó así.
            va, vb = _variables_del_componente(ca), _variables_del_componente(cb)
            es_par_precio_decimal = any(
                (e in va and d in vb) or (e in vb and d in va)
                for e, d in DECIMAL_OF.items()
            )
            ba = ca.get("computed_bounds") or ca.get("base_bounds") or {}
            bb = cb.get("computed_bounds") or cb.get("base_bounds") or {}
            # El par entero+decimal va PEGADO por diseño: un roce lateral no es
            # un choque, es como se lee un precio. Solo cuenta si de verdad se
            # montan uno sobre otro.
            if es_par_precio_decimal and ix * iy < _SOLAPE_PAR_DECIMAL_MIN_CM2:
                continue
            if not es_par_precio_decimal and _rect_overlap_ratio(ba, bb) > 0.05:
                continue
            if _son_decoracion_superpuesta(ca, cb):
                continue
            if (_parejas_dollar.get(id(ca)) is bb) or (_parejas_dollar.get(id(cb)) is ba):
                continue

            # El que "invade" es el de texto más grande, que es el criterio con
            # el que el resolver elegía a quién achicar. Se conserva para que
            # el aviso señale el cuadro al que hay que ponerle la regla.
            fa = ca.get("style", {}).get("font_size") or 12
            fb = cb.get("style", {}).get("font_size") or 12
            invasor, invadido, suyo = (ca, cb, pa) if fa >= fb else (cb, ca, pb)
            avisos.append({
                "component_id":   invasor.get("id"),
                "contra_id":      invadido.get("id"),
                "area_cm2":       round(ix * iy, 3),
                "font_size":      invasor.get("style", {}).get("font_size"),
                "texto":          _texto_resuelto(invasor, suyo)[:40],
            })
    return avisos


def preparar_componentes(comps: list[dict], rules: list[dict], product: dict) -> list[dict]:
    """Los componentes listos para dibujar, para ESTE producto.

    Un solo lugar donde se decide qué se ve y de qué tamaño sale, para que el
    preview y el export no puedan diferir: los dos llaman acá. La divergencia
    que arrastrábamos venía justo de tener dos secuencias parecidas pero no
    iguales --el preview llamaba al achique sin el ancho de papel, así que en
    pantalla nada se achicaba y en el PPTX todo salía al piso.

    Devuelve copias (ver apply_font_sizes): el layout se arma una vez y se
    reusa para todos los productos de la corrida.
    """
    visibles = apply_visibility(
        comps,
        evaluate_rules(rules, product),
        evaluate_segment_rules(rules, product),
    )
    return apply_font_sizes(
        visibles,
        evaluate_font_size_rules(rules, product),
        evaluate_segment_font_size_rules(rules, product),
    )


def hex_to_rgb(hex_color: str | None) -> RGBColor:
    if not hex_color:
        return RGBColor(0x1E, 0x29, 0x3B)
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return RGBColor(0x1E, 0x29, 0x3B)


# ---------------------------------------------------------------------------
# Renderizado de componentes individuales
# ---------------------------------------------------------------------------

def _forzar_sin_autoajuste(tf) -> None:
    """Apaga el autoajuste de PowerPoint en este cuadro.

    Esto es lo que ANTES hacía lo contrario: si el PPTX del diseñador traía la
    caja con "Reducir el texto al desbordarse", el export se lo volvía a poner
    al archivo final (`style["auto_fit"]`, que arma el importer leyendo
    a:normAutofit / a:spAutoFit del original).

    Mientras el motor achicaba solo, no se notaba: para cuando PowerPoint
    abría el archivo el texto ya entraba y su autoajuste no tenía nada que
    hacer. Al eliminar el achique automático (14/09/2026) el de PowerPoint
    quedó como ÚNICO actor y achicó todo hasta meterlo en la caja -- con el
    agravante de que el canvas del preview no hace autofit, así que en pantalla
    se veía el cuerpo declarado y en el archivo salía cualquier otro. Era el
    mismo síntoma de siempre ("el preview lo veo divino y el export no tiene
    nada que ver") por una causa nueva.

    No alcanza con dejar de agregarlo. Con preserve_source --que es como se
    genera todo desde 08/2026-- el shape YA VIENE del archivo del diseñador con
    su propio a:normAutofit adentro, así que hay que sacarlo activamente y
    dejar a:noAutofit en su lugar.

    Consecuencia buscada: un texto que no entra DESBORDA, a la vista, en vez de
    encogerse solo. Que se note es el punto -- se corrige con una regla de
    tamaño (ver rules_engine.set_font_size) y mientras tanto lo avisa
    detectar_solapes.
    """
    body_pr = tf._txBody.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    # Se reemplaza EN EL LUGAR: el orden de los hijos de a:bodyPr lo fija el
    # esquema (el autoajuste va después de a:prstTxWarp y antes de a:scene3d),
    # y appendear al final lo dejaría fuera de lugar en un shape preservado que
    # traiga elementos posteriores.
    posicion = None
    for tag in (qn("a:normAutofit"), qn("a:spAutoFit"), qn("a:noAutofit")):
        for el in body_pr.findall(tag):
            if posicion is None:
                posicion = list(body_pr).index(el)
            body_pr.remove(el)
    sin_ajuste = etree.Element(qn("a:noAutofit"))
    if posicion is None:
        body_pr.append(sin_ajuste)
    else:
        body_pr.insert(posicion, sin_ajuste)


def _populate_text_frame(tf, comp: dict, value: str) -> None:
    """Arma el contenido de un text_frame ya existente — separado de
    add_text_component para poder reusarlo tanto al crear una caja de texto
    nueva como al reescribir el texto de un shape original preservado
    (ver _place_component)."""
    style    = comp.get("style", {})
    segments = comp.get("segments")

    tf.word_wrap = True

    # Vertical anchor (preserved from original PPTX)
    vertical_align = style.get("vertical_align")
    if vertical_align:
        try:
            body_pr = tf._txBody.find(qn("a:bodyPr"))
            if body_pr is not None:
                body_pr.set("anchor", vertical_align)
        except Exception:
            pass

    # SIEMPRE, no solo cuando el diseño lo pedía: el cuerpo lo decide una regla
    # y nadie más. Ver _forzar_sin_autoajuste.
    _forzar_sin_autoajuste(tf)

    tf.clear()  # saca cualquier texto previo (ej. "<<Descripción>>" del original)
    transform = comp.get("transform", "none")
    p = tf.paragraphs[0]
    p.alignment = ALIGN_MAP.get(style.get("align", "center"), PP_ALIGN.CENTER)

    if segments:
        # Multi-segment: each segment gets its own run with per-segment style overrides.
        # Variable segments have their value pre-resolved as "_resolved" by _render_slide.
        for seg in segments:
            seg_val = seg.get("_resolved", seg.get("value", ""))
            if not seg_val:
                continue
            seg_style = {**style}
            if seg.get("style"):
                seg_style.update(seg["style"])
            if (comp.get("_manual_font_override") and style.get("font_size")
                    and not seg.get("_manual_font_override")):
                # Salvo el segmento al que la persona le puso SU tamaño a mano
                # (campo "Tamaño (pt)" del segmento): ese manda en su pedazo.
                # Criterio de Ivan, 11/09/2026: "lo que ponés a mano manda donde
                # lo ponés". La marca del segmento existe para distinguir ese
                # tamaño del que el segmento trae copiado del PPTX al importar,
                # que es el que sí tiene que seguir a la caja (lo de abajo).
                #
                # La persona fijó un tamaño a mano para TODA la caja (panel
                # de propiedades, campo "Tamaño (pt)") -- ese valor manda
                # incluso en un componente multi-segmento, donde cada
                # segmento puede traer su propio font_size heredado de
                # cuando se importó el PPTX (a veces desactualizado). Sin
                # esto, fijar el tamaño en el panel se veía bien en el
                # preview (que lee el estilo del componente) pero el
                # export seguía usando el tamaño viejo guardado en el
                # segmento, sin que nadie lo hubiera tocado a mano ahí.
                seg_style["font_size"] = style["font_size"]
            seg_transform = seg.get("transform") or "none"
            # La negrita puesta a mano le gana a la automática: si el estilo
            # dice negrita, va TODO en negrita y smart_bold no se aplica.
            #
            # Antes smart_bold ignoraba `font_bold` por completo, así que en un
            # cuadro con negrita automática tildar la casilla del panel no
            # cambiaba absolutamente nada -- ni en el preview ni en el archivo.
            # Reportado por Ivan (14/09/2026): "no hay diferencia entre activa
            # o no activa". La automática existe para decidir por vos cuando no
            # decidiste; en cuanto decidís, manda lo tuyo.
            if seg_transform == "smart_bold" and not seg_style.get("font_bold"):
                for part, is_bold in split_caps(seg_val):
                    if part:
                        run = p.add_run()
                        run.text = part
                        _apply_run_style(run, seg_style, bold_override=is_bold)
            else:
                if seg_transform not in (None, "none"):
                    seg_val = apply_transform(seg_val, seg_transform)
                run = p.add_run()
                run.text = seg_val
                _apply_run_style(run, seg_style)
    elif transform == "smart_bold" and not style.get("font_bold"):
        # Ver el comentario gemelo más arriba: lo puesto a mano manda.
        for segment, is_bold in split_caps(value):
            if not segment:
                continue
            run = p.add_run()
            run.text = segment
            _apply_run_style(run, style, bold_override=is_bold)
    else:
        run_style = style
        run = p.add_run()
        run.text = value
        _apply_run_style(run, run_style)

    # Replicate empty spacer run used in original PPTX to set a larger line height.
    # Without this, anchor=b positions text much lower than the original.
    line_height_pt = style.get("line_height_pt")
    if line_height_pt and line_height_pt != style.get("font_size"):
        spacer = p.add_run()
        spacer.text = ""
        spacer.font.size = Pt(line_height_pt)


def add_text_component(slide, comp: dict, value: str) -> None:
    bounds = comp["computed_bounds"]
    txBox = slide.shapes.add_textbox(
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.3)),
    )
    _populate_text_frame(txBox.text_frame, comp, value)


def _apply_run_style(run, style: dict, bold_override: bool | None = None) -> None:
    font = run.font
    if style.get("font_size"):
        font.size = Pt(style["font_size"])
    font.bold = bold_override if bold_override is not None else style.get("font_bold", False)
    if style.get("color"):
        font.color.rgb = hex_to_rgb(style["color"])
    if style.get("font_family"):
        font.name = style["font_family"]
    # No existe concepto de "subrayado" en este vocabulario de estilos (nunca
    # se guarda ni se usa) -- se fuerza apagado siempre, por la misma razón
    # que el tachado de abajo: el run mutado es el del PPTX FUENTE, que puede
    # traer un subrayado heredado (de un placeholder tipeado encima de texto
    # ya subrayado, o de un estilo de lista/master) que nunca se pidió.
    font.underline = False
    # python-pptx no expone tachado en Font -- hay que bajar al XML crudo.
    # SIEMPRE se fija explícito (on u off), nunca se deja "como estaba": el
    # run mutado es el del PPTX FUENTE, que puede traer strike="sngStrike"
    # heredado de antes (ej. alguien tipeó el placeholder encima de un "$XXX"
    # que ya tenía tachado de caracter aplicado) -- sin el else, un template
    # con `strikethrough` en False/ausente en su definición pero con ese
    # atributo viejo en el XML seguía mostrando el tachado de todos modos,
    # sumado a cualquier línea diagonal de tachado que el diseño ya trajera.
    run._r.get_or_add_rPr().set("strike", "sngStrike" if style.get("strikethrough") else "noStrike")
    # Tampoco expone la voladita. Es lo que mantiene el "$" y los centavos
    # arriba de la línea de base del número grande.
    if style.get("baseline"):
        run._r.get_or_add_rPr().set("baseline", str(style["baseline"]))


def add_shape_component(slide, comp: dict) -> None:
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

    bounds = comp["computed_bounds"]
    style  = comp.get("style", {})

    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.3)),
    )
    # Sin borde visible
    shape.line.fill.background()

    if style.get("background_color"):
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(style["background_color"])
    else:
        shape.fill.background()


_WMF_EXTS = {"wmf", "emf"}

def add_image_from_data(slide, comp: dict) -> None:
    """Embebe una imagen base64 en el slide.
    Formatos web (JPEG/PNG): usa add_picture normal.
    Formatos vectoriales (WMF/EMF): embebe via XML directo, sin PIL."""
    import base64 as _b64
    bounds   = comp["computed_bounds"]
    img_ext  = (comp.get("image_ext") or "").lower()

    try:
        img_bytes = _b64.b64decode(comp["image_data"])
    except Exception:
        add_image_placeholder(slide, comp, comp.get("name", "imagen"))
        return

    if img_ext in _WMF_EXTS:
        try:
            _embed_vector_image(slide, img_bytes, img_ext, bounds)
        except Exception:
            # Only show placeholder for variable images (product images).
            # Decorative static images (no variable) are silently skipped.
            if comp.get("variable"):
                add_image_placeholder(slide, comp, comp.get("name", "imagen"))
    else:
        try:
            slide.shapes.add_picture(
                io.BytesIO(img_bytes),
                Cm(bounds["x"]),
                Cm(bounds["y"]),
                Cm(max(bounds["width"],  0.1)),
                Cm(max(bounds["height"], 0.1)),
            )
        except Exception:
            add_image_placeholder(slide, comp, comp.get("name", "imagen"))


def _embed_vector_image(slide, img_bytes: bytes, ext: str, bounds: dict) -> None:
    """Embebe WMF/EMF directamente en el XML del slide sin pasar por PIL."""
    import hashlib
    from pptx.opc.part import Part
    from pptx.opc.packuri import PackURI

    content_types = {"wmf": "image/x-wmf", "emf": "image/x-emf"}
    ct  = content_types.get(ext, "image/x-wmf")
    h   = hashlib.md5(img_bytes).hexdigest()[:12]
    uri = PackURI(f"/ppt/media/img_{h}.{ext}")

    img_part = Part(uri, ct, img_bytes)
    rId = slide.part.relate_to(
        img_part,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )

    x  = int(Cm(bounds["x"]))
    y  = int(Cm(bounds["y"]))
    cx = int(Cm(max(bounds["width"],  0.1)))
    cy = int(Cm(max(bounds["height"], 0.1)))
    pid = abs(hash(h)) % 8000 + 1000

    pic_xml = (
        f'<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        f' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        f' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<p:nvPicPr>'
        f'<p:cNvPr id="{pid}" name="img_{h[:8]}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        f'<p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rId}"/>'
        f'<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'</p:pic>'
    )
    slide.shapes._spTree.append(parse_xml(pic_xml.encode()))


def add_image_placeholder(slide, comp: dict, label: str) -> None:
    """Placeholder para imágenes — rectángulo gris con el nombre de la variable.

    Reemplazar por descarga real de URL cuando se soporte HTTP en el renderer.
    """
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

    bounds = comp["computed_bounds"]
    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.5)),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)  # slate-200
    shape.line.fill.background()

    # Label indicativo centrado
    tf = shape.text_frame
    tf.word_wrap = True
    p   = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = f"[{label}]"
    run.font.size  = Pt(9)
    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)  # slate-400


# ---------------------------------------------------------------------------
# Preservación del diseño original — reusar/mutar shapes reales del PPTX
# fuente en vez de reconstruir todo sobre una presentación en blanco.
# ---------------------------------------------------------------------------

def _shape_id_map(shapes) -> dict[int, object]:
    """Mapa shape_id -> shape, recorriendo grupos recursivamente (mismo
    criterio que _flatten_shapes en pptx_importer, para que el id capturado
    al importar siga siendo encontrable acá)."""
    result: dict[int, object] = {}
    for shape in shapes:
        if hasattr(shape, "shapes"):
            result.update(_shape_id_map(shape.shapes))
        else:
            try:
                result[shape.shape_id] = shape
            except Exception:
                pass
    return result


def _sacar_formas_eliminadas(slide, formas_eliminadas, components: list[dict]) -> None:
    """Saca del slide base las formas del PPTX fuente de los cuadros eliminados.

    El render parte del PPTX fuente: una forma que ningún cuadro reescribe
    sigue impresa tal cual vino del diseño, así que sacar el cuadro de la
    lista no alcanza para borrarlo (caso real, 11/09/2026: un "9" blanco
    olvidado en el diseño de Rompe Precios Congelados, que tapaba al cuadro de
    "PRECIO REGULAR" en el preview). Se hace sobre el slide base antes de
    duplicarlo, así ninguna hoja lo trae.

    Una forma que todavía usa otro cuadro no se toca: el PPTX puede traer dos
    shapes con el mismo id (ver el comentario de `oculto` en _render_slide).
    """
    if not formas_eliminadas:
        return
    en_uso = {c.get("_source_shape_id") for c in components if c.get("_source_shape_id") is not None}
    mapa = _shape_id_map(slide.shapes)
    for forma in formas_eliminadas:
        if forma in en_uso:
            continue
        shape = mapa.get(forma)
        if shape is None:
            continue
        padre = shape._element.getparent()
        if padre is not None:
            padre.remove(shape._element)


def _duplicate_slide(prs, source_slide):
    """Clona un slide completo (layout, shapes, relaciones de imagen y fondo
    propio si tiene) — python-pptx no trae esto de fábrica. Hace falta para
    generar N páginas iguales al diseño original cuando hay más de un grupo
    de productos por generar (ver render_template_to_pptx)."""
    new_slide = prs.slides.add_slide(source_slide.slide_layout)

    # add_slide ya pudo haber agregado placeholders heredados del layout —
    # los sacamos, vamos a clonar los shapes reales del slide fuente.
    for shape in list(new_slide.shapes):
        shape._element.getparent().remove(shape._element)

    # Fondo propio del slide (si el original no lo hereda del layout/master)
    src_bg = source_slide._element.find(qn("p:cSld")).find(qn("p:bg"))
    if src_bg is not None:
        new_cSld = new_slide._element.find(qn("p:cSld"))
        new_cSld.insert(0, copy.deepcopy(src_bg))

    # Relaciones de imagen — para que los r:embed de los shapes clonados
    # sigan resolviendo a la parte correcta en el slide nuevo.
    id_map: dict[str, str] = {}
    for rel_id, rel in source_slide.part.rels.items():
        if rel.is_external or "image" not in rel.reltype:
            continue
        id_map[rel_id] = new_slide.part.relate_to(rel.target_part, rel.reltype)

    for shape in source_slide.shapes:
        new_el = copy.deepcopy(shape._element)
        if id_map:
            for blip in new_el.iter(qn("a:blip")):
                old_rid = blip.get(qn("r:embed"))
                if old_rid and old_rid in id_map:
                    blip.set(qn("r:embed"), id_map[old_rid])
        new_slide.shapes._spTree.append(new_el)

    return new_slide


def _cadena_de_grupos(shape) -> list[tuple[float, float, float, float, float, float]]:
    """Transformaciones de los grupos que contienen a este shape, del MÁS
    EXTERNO al más interno.

    Cada una es (off.x, off.y, chOff.x, chOff.y, escalaX, escalaY) en EMU,
    igual que `_transformacion_de_grupo` del importer -- son las dos mitades
    de la misma cuenta y tienen que coincidir.
    """
    from pptx.oxml.ns import qn as _qn
    cadena: list[tuple[float, float, float, float, float, float]] = []
    try:
        el = shape._element.getparent()
    except Exception:
        return cadena
    while el is not None:
        if el.tag == _qn("p:grpSp"):
            try:
                xfrm = el.find(_qn("p:grpSpPr") + "/" + _qn("a:xfrm"))
                off, ext = xfrm.find(_qn("a:off")), xfrm.find(_qn("a:ext"))
                cho, che = xfrm.find(_qn("a:chOff")), xfrm.find(_qn("a:chExt"))
                cw, ch = int(che.get("cx")), int(che.get("cy"))
                if cw and ch:
                    cadena.append((
                        float(off.get("x")), float(off.get("y")),
                        float(cho.get("x")), float(cho.get("y")),
                        int(ext.get("cx")) / cw, int(ext.get("cy")) / ch,
                    ))
            except Exception:
                pass
        el = el.getparent()
    cadena.reverse()
    return cadena


def _a_coordenadas_internas(shape, x_emu, y_emu, w_emu, h_emu):
    """Pasa una posición de LA HOJA al sistema de coordenadas donde vive el
    shape.

    Un shape suelto ya está en coordenadas de hoja y esto no lo toca. Uno que
    está DENTRO DE UN GRUPO no: PowerPoint guarda su `off` en el sistema
    interno del grupo (chOff/chExt), y ponerle ahí una coordenada de hoja lo
    manda a cualquier lado.

    Bug real (Fiesta de Gran Bretaña A4, 07/09/2026). El importer ya convertía
    interno -> hoja al leer, así que la cocarda del "XX% OFF" se veía bien en
    el editor; pero al exportar el motor escribía la coordenada de hoja tal
    cual adentro del grupo y PowerPoint la volvía a transformar: la cocarda,
    guardada en (14,83 , 18,54), terminaba dibujada en (25,65 , 40,56) sobre
    una hoja de 21 x 29,7 -- fuera de la página, abajo y a la derecha.

    Con grupos anidados se invierte de afuera hacia adentro, en el orden
    inverso al que PowerPoint los aplica.
    """
    for ox, oy, cx, cy, sx, sy in _cadena_de_grupos(shape):
        if not sx or not sy:
            continue
        x_emu = cx + (x_emu - ox) / sx
        y_emu = cy + (y_emu - oy) / sy
        w_emu = w_emu / sx
        h_emu = h_emu / sy
    return x_emu, y_emu, w_emu, h_emu


def _escribir_xfrm(elemento, x_emu, y_emu, w_emu, h_emu) -> None:
    """Escribe posición y tamaño en el <a:xfrm> de un shape recién creado."""
    xfrm = elemento.find(".//" + qn("a:xfrm"))
    if xfrm is None:
        return
    off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
    if off is not None:
        off.set("x", str(int(round(x_emu))))
        off.set("y", str(int(round(y_emu))))
    if ext is not None:
        ext.set("cx", str(max(1, int(round(w_emu)))))
        ext.set("cy", str(max(1, int(round(h_emu)))))


def _place_component(slide, comp: dict, value: str, shape_map: dict[int, object]) -> None:
    """Coloca un componente en el slide. Si viene de una plantilla con
    diseño original preservado y matchea un shape real del archivo fuente
    (_source_shape_id), lo muta en el lugar — reposiciona y reescribe su
    contenido — en vez de crear uno nuevo, así el resto del diseño del
    archivo (fondos, logos, bordes que el importer no haya capturado como
    componente) queda intacto. Sin match, cae al comportamiento de siempre."""
    comp_type = comp.get("type", "text")
    source_id = comp.get("_source_shape_id")
    shape = shape_map.get(source_id) if source_id is not None else None

    if shape is not None:
        bounds = comp["computed_bounds"]
        interna = None
        try:
            # `computed_bounds` está SIEMPRE en coordenadas de hoja. Si el
            # shape vive adentro de un grupo hay que pasarlo a las internas
            # del grupo antes de escribirlo (ver _a_coordenadas_internas).
            x, y, w, h = _a_coordenadas_internas(
                shape,
                float(Cm(bounds["x"])), float(Cm(bounds["y"])),
                float(Cm(max(bounds["width"],  0.1))),
                float(Cm(max(bounds["height"], 0.1))),
            )
            shape.left   = int(round(x))
            shape.top    = int(round(y))
            shape.width  = max(1, int(round(w)))
            shape.height = max(1, int(round(h)))
            interna = (x, y, w, h)
        except Exception:
            pass

        if comp_type == "text" and shape.has_text_frame:
            _populate_text_frame(shape.text_frame, comp, value)
            return
        if comp_type == "shape":
            style = comp.get("style", {})
            if style.get("background_color"):
                try:
                    shape.fill.solid()
                    shape.fill.fore_color.rgb = hex_to_rgb(style["background_color"])
                except Exception:
                    pass
            return
        if comp_type == "image":
            if comp.get("image_data"):
                # Más simple/confiable reemplazar el shape entero que mutar el
                # blob de una <p:pic> ya existente -- pero hay que DEVOLVERLO A
                # SU LUGAR en el árbol.
                #
                # El orden del árbol es el orden de dibujado, y tanto
                # add_picture como el embebido vectorial agregan al FINAL. Una
                # imagen de fondo que termina última se dibuja ENCIMA de todo el
                # texto y la cenefa sale en blanco.
                #
                # Pasó de verdad en las dos plantillas HELVETICO de Redexpres,
                # que traen el arte como imagen DE LA HOJA. Las de Rompe del
                # Finde no se veían afectadas porque ahí el arte está en el
                # master, que se dibuja antes que cualquier shape del slide.
                #
                # add_picture agrega SIEMPRE al final de la HOJA, no del grupo
                # donde vivía la imagen. Hasta el 11/09/2026 se buscaba lo
                # agregado al final del padre: con una imagen dentro de un
                # grupo el padre no crecía, la imagen nueva quedaba suelta
                # arriba de todo y tapaba lo que el diseño pone encima (caso
                # real: el fondo rojo de Club Card de Rompe Precios Congelados
                # A4 tapando el precio, el decimal y "unidad"). Ahora se toma
                # del final de la hoja, se devuelve a su lugar en el padre y, si
                # el padre es un grupo, se le escribe la posición en las
                # coordenadas del grupo.
                padre = shape._element.getparent()
                if padre is not None:
                    indice = list(padre).index(shape._element)
                    raiz = slide.shapes._spTree
                    padre.remove(shape._element)
                    antes = len(raiz)
                    add_image_from_data(slide, comp)
                    if len(raiz) > antes:            # se agregó algo al final de la hoja
                        nuevo = list(raiz)[-1]
                        raiz.remove(nuevo)
                        padre.insert(indice, nuevo)
                        if padre.tag == qn("p:grpSp") and interna is not None:
                            _escribir_xfrm(nuevo, *interna)
            return
        return

    # Sin shape original que matchee (template armado en el editor, o
    # componente agregado a mano después de importar) -> comportamiento
    # de siempre: crear el shape desde cero.
    if comp_type == "text":
        add_text_component(slide, comp, value)
    elif comp_type == "shape":
        add_shape_component(slide, comp)
    elif comp_type == "image":
        if comp.get("image_data"):
            add_image_from_data(slide, comp)
        else:
            add_image_placeholder(slide, comp, comp.get("variable") or "imagen")


# ---------------------------------------------------------------------------
# Render de un slide completo
# ---------------------------------------------------------------------------

def _bounds_por_dominante(
    comp_layout: list[dict], dominantes_presentes: list[str],
) -> dict[str, list[dict]]:
    """Para cada variable dominante presente, los bounds de los cuadros que
    EFECTIVAMENTE la dibujan en este layout -- ver _excluido_por_dominante,
    que compara contra esto para decidir si de verdad hay una colisión de
    lugar, no solo coincidencia de variable."""
    resultado: dict[str, list[dict]] = {m: [] for m in dominantes_presentes}
    for c in comp_layout:
        usadas = _variables_del_componente(c)
        for m in dominantes_presentes:
            if m in usadas:
                resultado[m].append(c.get("computed_bounds") or c.get("base_bounds") or {})
    return resultado


# Cuánto tiene que solaparse un cuadro con el que dibuja la variable
# dominante para que la exclusión de _EXCLUYENTES aplique de verdad --
# ver el comentario de _EXCLUYENTES: la regla existe para cuando dos
# cuadros "ocupan EL MISMO lugar del cartel", no para cualquier plantilla
# que use ambas variables en cualquier parte de la hoja.
#
# Medido en los dos casos reales que existen hoy: Redexpres (A4 y 3xA4)
# diseña precioOferta y promoOferta literalmente superpuestos -- 91-100%
# de solape, el diseño los pone ahí a propósito para que solo se vea uno
# de los dos. Preciazos de la Tienda (09/2026) NO: su <<precioOferta>>
# grande y la cocarda con promoOferta comparten apenas ~20% de área
# (cajas vecinas, no superpuestas) -- el diseño real muestra los dos a la
# vez ("2x $129" en la cocarda Y "$64" grande más abajo). Sin este piso,
# agregarle promoOferta a la cocarda de Preciazos (pedido explícito de
# Ivan, para que las 4 plantillas mostraran lo mismo) apagaba precioOferta
# en toda la plantilla sin que nadie lo pidiera -- exclusión pensada para
# Redexpres, aplicada por error a un diseño que nunca la necesitó.
_SOLAPE_MIN_EXCLUSION_DOMINANTE = 0.5


def _excluido_por_dominante(
    comp: dict, product: dict, dominantes_presentes: list[str],
    bounds_por_dominante: dict[str, list[dict]],
) -> bool:
    """True si `comp` se tapa porque el producto trae valor en alguna
    variable "dominante" de _EXCLUYENTES, su par el diseño también la
    dibuja, Y ese par vive en el MISMO lugar del cartel (ver
    _SOLAPE_MIN_EXCLUSION_DOMINANTE) -- no en cualquier parte de la hoja.
    Extraído de _render_slide para poder consultarlo en una pasada previa
    (ver _rect_overlap_ratio más abajo: un "$" fijo sin variable propia
    que vive pegado a un precio excluido necesita saber que SU vecino se
    ocultó antes de decidir si se oculta también)."""
    usadas = _variables_del_componente(comp)
    propios = comp.get("computed_bounds") or comp.get("base_bounds") or {}
    for manda in dominantes_presentes:
        if manda in usadas:
            continue
        if not (usadas & set(_EXCLUYENTES[manda])):
            continue
        if not str(product.get(manda, "") or "").strip():
            continue
        # OJO: acá NO alcanza con mirar el contenido. Se probó "si promoOferta
        # trae el mismo literal que tipoOferta, tapá el precio" y le borraba el
        # precio a productos reales: en las cuatro plantillas Preciazos las
        # cajas de promoOferta y del precio están SEPARADAS (solape 0,00-0,07)
        # y Budweiser ("4x3") y Granny ("3x99") traen ese literal en las dos
        # variables -- el cartel se quedaba sin precio. Quién tapa a quién lo
        # dice el DISEÑO, o sea la geometría, y solo ella.
        bounds_dominante = bounds_por_dominante.get(manda) or []
        if any(_rect_overlap_ratio(propios, b) >= _SOLAPE_MIN_EXCLUSION_DOMINANTE
               for b in bounds_dominante):
            return True
    return False


# Cuánto de la caja MÁS CHICA tiene que caer dentro de la más grande para
# contar como "el mismo lugar del cartel" -- ver _EXCLUYENTES y el "$" fijo
# de Preciazos A4 (caso real: un <<precioOferta>> de 180pt tapado por
# promoOferta dejaba su "$" fijo de al lado solo en pantalla, sin ningún
# número, porque ese "$" no tiene variable propia y ninguna de las
# exclusiones de arriba lo alcanza). Medido en ese caso real: el "$" (caja
# 2,6x3,9cm) y el <<precioOferta>> (caja 11,4x2,8cm) solo se solapan 13,6%
# del área del "$" -- las cajas están pensadas para leerse juntas ("$" a la
# izquierda del número) pero no calzan como un rectángulo adentro del otro,
# así que el piso queda bajo a propósito. Un vecino real (otra fila/
# columna del diseño) no llega ni a este piso salvo que las cajas ya
# estuvieran mal puestas de por sí.
_SOLAPE_MIN_EXCLUSION_PAREJA = 0.1


# Qué fracción del ALTO del cuadro fijo (el "$" sin variable propia) cae
# dentro del rango vertical de un candidato -- usado para encontrarle su
# pareja de verdad entre los cuadros CON variable del mismo layout (ver más
# abajo, dentro de _render_slide). El área (_rect_overlap_ratio) sirve para
# _excluido_por_dominante porque ahí las dos cajas están pensadas para
# superponerse (Redexpres). Acá NO: precio y "$" van uno AL LADO del otro
# ("$" a la izquierda, número a la derecha), casi sin superponerse en X, así
# que el área da un número chico e inestable -- y en 3xA4 (09/2026) le daba
# más área a la cocarda de arriba (10%, apenas rozando la esquina del "$")
# que al propio <<precioOferta>> de al lado (0%, ni un pixel de solape en
# X), apagando el "$" en cualquier producto sin combo. El alto de las dos
# cajas SÍ se diseña igual a propósito (mismo renglón), así que cuánto del
# alto del "$" cae dentro del candidato es la señal que no falla -- siempre
# que el candidato se limite a cuadros de "contenido real" (ver el filtro de
# etiquetas flotantes Y de DECIMAL_VARS más abajo, en el llamado real: un
# decimal puede venir vacío --precio redondo-- mientras el ENTERO al lado
# tiene dato de sobra, y sin sacarlo de la lista ganaba por cobertura contra
# el propio precio: caso real, Alfajor en A4, "179" sin decimales, el "$"
# de <<precioOferta>> cubría 54% de <<decimalPrecioOferta>> vacío contra
# apenas 19% de <<precioOferta>> con dato -- se apagaba el "$" con el
# número completo al lado).
#
# Con ese filtro puesto, medido en los 4 formatos reales: la pareja
# correcta (siempre el precio en sí) va de 19% (A4, precioOferta -- su "$"
# es angosto y alto, el precio es una sola línea bien más baja) a 100%; el
# vecino más parecido que NO es la pareja (la descripción, en 3xA4) llega a
# 55% pero nunca gana el candidato correcto en ningún caso real. El piso
# queda bajo el mínimo verificado (19%) con margen, no al punto medio entre
# ganador y perdedor -- achicarlo de más vuelve a exponer al "$" a apagarse
# con un decimal vacío.
_COBERTURA_MIN_PAREJA = 0.1


def _cobertura_vertical(fijo: dict, candidato: dict) -> float:
    y1, h1 = fijo.get("y", 0), fijo.get("height", 0)
    y2, h2 = candidato.get("y", 0), candidato.get("height", 0)
    if h1 <= 0:
        return 0.0
    solape = min(y1 + h1, y2 + h2) - max(y1, y2)
    return max(0.0, solape / h1)


def _rect_overlap_ratio(a: dict, b: dict) -> float:
    ax, ay = a.get("x", 0), a.get("y", 0)
    aw, ah = a.get("width", 0), a.get("height", 0)
    bx, by = b.get("x", 0), b.get("y", 0)
    bw, bh = b.get("width", 0), b.get("height", 0)
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    area_i = ix * iy
    area_chica = min(aw * ah, bw * bh)
    if area_chica <= 0:
        return 0.0
    return area_i / area_chica


def _render_slide(
    slide,
    comp_layout: list[dict],
    product: dict,
    slot_offset_x: float = 0.0,
    slot_offset_y: float = 0.0,
    missing_vars: set | None = None,
    shape_map: dict[int, object] | None = None,
    slot_vacio: bool = False,
) -> None:
    shape_map = shape_map or {}
    # Que variables "que tapan" existen como cuadro en ESTE diseno. Se calcula
    # una vez por slide, no por componente.
    dibujadas = set()
    for c in comp_layout:
        dibujadas |= _variables_del_componente(c)
    dominantes_presentes = [m for m in _EXCLUYENTES if m in dibujadas]
    bounds_por_dominante = _bounds_por_dominante(comp_layout, dominantes_presentes)

    # El MISMO literal no se imprime dos veces en el mismo cartel.
    #
    # En un M x N (2x1, 4x3) `tipoOferta` y `promoOferta` traen el mismo
    # texto a proposito: el converter llena las dos porque cada diseño usa
    # una (ver resolver_mecanica, familia "mxn"). Un diseño que tenga los DOS
    # cuadros -- la A4 de Redexpres -- imprimia "2X1" dos veces, una en la
    # cocarda y otra tapando el precio (bug real, pag. 54 de mundo hogar).
    #
    # Esto NO se decide por geometria. Antes lo resolvia la regla de
    # excluyentes, que se apoya en cuanto se superponen las cajas, y eso
    # solo funciona cuando el diseño las dibuja encimadas: en Redexpres si,
    # en Preciazos no (ahi la cocarda y el precio son cajas vecinas y el
    # diseño muestra las dos, "2x $129" arriba y "$64" abajo). La señal
    # confiable es el CONTENIDO: si dos cuadros van a imprimir exactamente
    # lo mismo, sobra uno, esten donde esten. Se conserva el que tapa al
    # precio (promoOferta) y se apaga la cocarda, que es el criterio que ya
    # tenia _EXCLUYENTES.
    literales_repetidos: set[int] = set()
    if "promoOferta" in dibujadas and "tipoOferta" in dibujadas:
        texto_promo = str(product.get("promoOferta", "") or "").strip()
        texto_tipo  = str(product.get("tipoOferta", "") or "").strip()
        if texto_promo and texto_promo == texto_tipo:
            for c in comp_layout:
                usadas_c = _variables_del_componente(c)
                # solo el cuadro que imprime UNICAMENTE el literal de la
                # cocarda; uno compuesto que ademas lleve el precio no se toca
                if usadas_c == {"tipoOferta"}:
                    literales_repetidos.add(id(c))

    # Cuadros fijos (sin variable propia, ej. el "$" del diseño) que viven
    # pegados a un cuadro que se va a tapar -- por exclusión (_EXCLUYENTES)
    # O porque su dato vino vacío del Excel (precioOferta sin valor, caso
    # real: Durazno en almíbar, Puré de papas VIDA, Pulpa de tomates
    # Morixe -- traen precioRegular pero no precioOferta) -- se ocultan
    # junto con él, si no quedan solos en pantalla sin ningún número al
    # lado (ver _rect_overlap_ratio). Se resuelve en una pasada aparte
    # porque necesita conocer los bounds de TODOS los componentes que se
    # van a tapar antes de decidir, no solo el propio.
    def _var_sin_dato(c: dict) -> bool:
        usadas = _variables_del_componente(c)
        if not usadas or c.get("type") != "text":
            return False
        partes_fijas = any(
            str(seg.get("value", "")).strip()
            for seg in (c.get("segments") or []) if seg.get("type") == "static"
        )
        return not partes_fijas and not _texto_resuelto(c, product).strip()

    # Bounds + estado "se tapa" + variables de TODOS los cuadros con variable
    # propia (no solo los que se tapan). Un cuadro fijo sin variable (el "$"
    # del diseño) tiene que compararse contra su VECINO MÁS CERCANO
    # geométricamente, no contra "cualquiera que se haya tapado en la hoja"
    # -- caso real: el "$" de <<precioBanco>> (Preciazos A4) solapaba 11,8%
    # con <<tipoOfertaComprando>> (la etiqueta "Comprando 2" arriba del
    # precio, vacía en productos sin combo) y se apagaba junto con ella
    # aunque <<precioBanco>> -- su verdadero par, con 46% de solape -- tuviera
    # dato de sobra. Sin esto el "$" de precioBanco desaparecía en TODOS los
    # productos sin combo (48 de 56 en el listado real), y lo mismo le pasaba
    # al "$" de precioRegular en 3xA4.
    variables_bounds = [
        (
            c.get("computed_bounds") or c.get("base_bounds") or {},
            _excluido_por_dominante(c, product, dominantes_presentes, bounds_por_dominante) or _var_sin_dato(c),
            _variables_del_componente(c),
        )
        for c in comp_layout
        if _variables_del_componente(c)
    ]

    for comp in comp_layout:
        comp_type = comp.get("type", "text")
        source_id = comp.get("_source_shape_id")

        # Un slot SIN producto no imprime nada. No alcanza con sacar los
        # cuadros que quedaron vacios: uno que mezcla texto fijo con variable
        # --el "$" del diseno mas {precioOferta}-- sigue teniendo el simbolo, y
        # en la celda sobrante de una hoja parcial quedaba un "$" solo impreso
        # (3xA4 con 8 productos: 3 hojas x 3 celdas, la novena celda vacia).
        # Las dos: el ojito del panel (`visible`, decisión de una persona para
        # todos los productos) y la regla evaluada contra ESTE producto
        # (`_oculto_por_regla`). Ver apply_visibility.
        oculto = (slot_vacio or not comp.get("visible", True)
                  or comp.get("_oculto_por_regla", False))
        # Excluyentes: si la que manda del par trae valor, esta no se dibuja.
        # Solo aplica si el diseno TIENE de verdad el cuadro que tapa. Sin ese
        # chequeo, una plantilla que usa precioOferta y no tiene cuadro de
        # promoOferta escondia el precio y no dibujaba nada en su lugar: la
        # cenefa de un M x N salia con el hueco del precio en blanco (visto en
        # la A4 de Rompe del Finde, que muestra el literal en la cocarda de
        # tipoOferta y no necesita promoOferta).
        usadas = _variables_del_componente(comp)
        if not oculto and id(comp) in literales_repetidos:
            oculto = True
        if not oculto and dominantes_presentes and usadas:
            oculto = _excluido_por_dominante(comp, product, dominantes_presentes, bounds_por_dominante)
        # Un cuadro FIJO sin variable propia (el "$" del diseño) no entra en
        # la exclusión de arriba -- ninguna de sus "usadas" está en juego,
        # así que la condición de arriba nunca lo agarra. Si vive pegado a
        # un cuadro que SÍ se acaba de tapar por exclusión, se tapa junto
        # con él: si no, quedaba el símbolo solo en pantalla sin ningún
        # número al lado (caso real: <<precioOferta>> de Preciazos A4
        # tapado por promoOferta en un combo, con su "$" de 90pt fijo
        # sobreviviendo solo, sin nada que acompañar).
        if not oculto and not usadas and variables_bounds:
            propios = comp.get("computed_bounds") or comp.get("base_bounds") or {}
            # Etiquetas puramente flotantes (unidad, tipoOferta,
            # tipoOfertaComprando) quedan afuera de la búsqueda de pareja: no
            # son "el precio" que el "$" acompaña, son captions chicas que el
            # diseño pone cerca de cualquier precio -- si entraran a competir,
            # ganaban por casualidad de posición (ver comentario de
            # variables_bounds más arriba).
            #
            # El cuadro del DECIMAL de un precio (DECIMAL_VARS, ej.
            # decimalPrecioOferta) tampoco es válido como pareja: es un
            # sufijo del precio, nunca "el precio" en sí, y puede venir
            # vacío (precio redondo, sin centavos) mientras el ENTERO al
            # lado tiene dato de sobra -- caso real: Alfajor
            # (precioOferta="179", sin decimalPrecioOferta) tenía más
            # cobertura vertical contra el cuadro del decimal (54%) que
            # contra el propio precioOferta (19%, caja de una sola línea
            # bien más baja que el "$"), así que el "$" se apagaba con el
            # decimal vacío aunque el "179" completo estuviera ahí al lado.
            #
            # Si no queda ningún candidato de contenido real (plantilla
            # rarísima con solo etiquetas y decimales), se cae a la lista
            # completa antes que no comparar contra nada.
            candidatos = [
                (b, oc) for b, oc, vars_c in variables_bounds
                if not (vars_c <= _VARIABLES_ETIQUETA_FLOTANTE) and not (vars_c <= set(DECIMAL_VARS))
            ] or [(b, oc) for b, oc, _ in variables_bounds]
            mejor_bounds, mejor_oculto = max(
                candidatos, key=lambda par: _cobertura_vertical(propios, par[0])
            )
            if mejor_oculto and _cobertura_vertical(propios, mejor_bounds) >= _COBERTURA_MIN_PAREJA:
                oculto = True
        # Un cuadro cuyo contenido sale SOLO de variables y todas quedaron
        # vacías no tiene nada que imprimir. Borrarle el texto no alcanza: si
        # el shape tiene relleno propio --la cocarda roja de tipoOferta-- queda
        # un rectángulo de color impreso en el cartel de un producto que no
        # tiene mecánica. Se saca el shape entero.
        if not oculto and comp_type == "text" and _variables_del_componente(comp):
            partes_fijas = any(
                str(seg.get("value", "")).strip()
                for seg in (comp.get("segments") or []) if seg.get("type") == "static"
            )
            if not partes_fijas and not _texto_resuelto(comp, product).strip():
                oculto = True

        if oculto:
            shape = shape_map.get(source_id) if source_id is not None else None
            if shape is not None:
                # El padre puede ser None si este shape ya se saco: pasa cuando
                # el PPTX trae dos shapes con el MISMO id (PowerPoint lo evita,
                # pero copiar shapes entre archivos con python-pptx no) y dos
                # componentes distintos apuntan al mismo. Antes reventaba con un
                # AttributeError a mitad del render y no se generaba nada.
                padre = shape._element.getparent()
                if padre is not None:
                    padre.remove(shape._element)
            continue

        segments = comp.get("segments") if comp_type == "text" else None

        if segments:
            # Resolve variable segments from product data, store as "_resolved"
            resolved = []
            for i, seg in enumerate(segments):
                if seg.get("type") == "variable":
                    seg_var = seg.get("value", "")
                    seg_val = str(product.get(seg_var, "") or "") if seg_var else ""
                    if seg_var and seg_var not in product and missing_vars is not None:
                        missing_vars.add(seg_var)
                    # Guarda contra el símbolo de moneda duplicado. Desde
                    # 08/2026 los precios viajan SIN "$" (el símbolo es texto
                    # fijo del diseño), así que esto normalmente no se
                    # dispara; sigue acá para el caso de un Excel cargado a
                    # mano con "$899" en una plantilla que además tiene el
                    # "$" como run propio -- sin el chequeo queda "$$899".
                    # Solo saca un símbolo repetido, nunca reformatea nada.
                    if i > 0 and segments[i - 1].get("type") == "static":
                        prev = segments[i - 1].get("value", "").strip()
                        if prev in ("U$S", "$") and seg_val.strip().startswith(prev):
                            seg_val = seg_val.strip()[len(prev):].lstrip()
                else:
                    seg_val = seg.get("value", "")
                resolved.append({**seg, "_resolved": seg_val})

            # Guarda contra el literal repetido a los dos lados de un
            # separador fijo (ej. "<<tipoOferta>> $ <<promoOferta>>"). Ese
            # diseño asume que las dos variables son SIEMPRE distintas
            # (tipoOferta="2x" + promoOferta="129" -> "2x $129"), pero
            # promoOferta también puede venir IGUAL a tipoOferta a propósito
            # -- ver convertidor_variables.resolver_mecanica, familia "mxn":
            # para un M x N ("4x3", "3x99") el converter copia el mismo
            # literal en las dos variables porque Redexpres dibuja
            # promoOferta TAPANDO el cuadro del precio, sin necesitar un
            # separador. Caso real (Preciazos, 09/2026): Cerveza BUDWEISER
            # (tipoOferta=promoOferta="4x3") imprimía "4x3 $ 4x3". Si el
            # texto a los dos lados de un separador estático es idéntico,
            # se apaga el separador y la segunda copia -- nunca reformatea,
            # solo saca la repetición (mismo criterio que el guardado de
            # "$$" de arriba).
            for i, seg in enumerate(resolved):
                if seg.get("type") != "static" or i == 0 or i == len(resolved) - 1:
                    continue
                anterior, siguiente = resolved[i - 1], resolved[i + 1]
                if anterior.get("type") != "variable" or siguiente.get("type") != "variable":
                    continue
                val_anterior = anterior.get("_resolved", "").strip()
                val_siguiente = siguiente.get("_resolved", "").strip()
                if val_anterior and val_anterior == val_siguiente:
                    resolved[i] = {**seg, "_resolved": ""}
                    resolved[i + 1] = {**siguiente, "_resolved": ""}

            comp  = {**comp, "segments": resolved}
            value = ""  # unused when segments present
        else:
            variable     = comp.get("variable")
            static_value = comp.get("static_value", "")
            raw_value    = str(product.get(variable, "") or "") if variable else static_value
            transform    = comp.get("transform", "none")
            value        = apply_transform(raw_value, transform)

            # Collect variables that are used in the template but whose column is
            # entirely absent from the Excel (key not in product at all).
            # Empty cells produce key="" — that's valid data, not a missing column.
            if variable and variable not in product and missing_vars is not None:
                missing_vars.add(variable)

        # Offset 2D para layouts multi-slot (grilla horizontal × vertical)
        if slot_offset_x > 0 or slot_offset_y > 0:
            cb = comp["computed_bounds"].copy()
            cb["x"] = cb["x"] + slot_offset_x
            cb["y"] = cb["y"] + slot_offset_y
            comp = {**comp, "computed_bounds": cb}

        _place_component(slide, comp, value, shape_map)


# ---------------------------------------------------------------------------
# Multi-slot A4 detection
# ---------------------------------------------------------------------------

def _esquina(c: dict) -> tuple[float, float]:
    """Punto de referencia de un cuadro: su esquina superior izquierda.

    NO el centro. Los diseños reales traen cajas absurdamente altas --el
    cuadro de <<precioOferta>> de la 6xA4 mide 10,5 cm de alto para un texto
    de una línea-- y su centro cae en la fila de ABAJO. Con el centro, la
    cenefa de arriba perdía el precio y la de abajo terminaba con dos.
    El borde superior izquierdo es donde el texto realmente empieza.
    """
    b = c.get("base_bounds", {}) or {}
    return (b.get("x", 0.0), b.get("y", 0.0))


def _nombres_de_variable(c: dict) -> list[str]:
    """Qué variables usa un cuadro.

    Mira c["variable"] y, si no lo tiene, los segmentos: PowerPoint parte los
    placeholders en varios runs al editarlos, y una plantilla real puede tener
    TODOS sus componentes como multi-segmento.
    """
    if c.get("variable"):
        return [c["variable"]]
    return [seg["value"] for seg in (c.get("segments") or []) if seg.get("type") == "variable"]


def _cortar_por_huecos(valores: list[float], n_grupos: int) -> list[float]:
    """Límites que parten `valores` en n_grupos, cortando por los huecos mayores.

    Entre dos filas de cenefas hay aire; dentro de una fila los cuadros están
    pegados. Buscar los n-1 huecos más grandes encuentra esas separaciones sin
    depender de dónde esté el ancla ni de cuán alta sea cada caja.
    """
    if n_grupos <= 1 or len(valores) < n_grupos:
        return []
    ordenados = sorted(valores)
    huecos = sorted(
        ((ordenados[i + 1] - ordenados[i], i) for i in range(len(ordenados) - 1)),
        reverse=True,
    )[: n_grupos - 1]
    return sorted((ordenados[i] + ordenados[i + 1]) / 2.0 for _, i in huecos)


def _indice_por_limites(valor: float, limites: list[float]) -> int:
    for i, lim in enumerate(limites):
        if valor < lim:
            return i
    return len(limites)


# Tolerancia al ubicar un cuadro en su celda, como fracción del paso. Los
# diseños están hechos a mano: la fila 2 de la 6xA4 arranca en 7,01 cm cuando
# el paso exacto da 6,985, y sin margen ese cuadro cae en la fila de arriba.
_MARGEN_CELDA = 0.02


def _indice_por_paso(valor: float, origen: float, paso: float, n: int) -> int:
    """En qué celda de una grilla de paso fijo cae `valor`."""
    if n <= 1 or paso <= 0:
        return 0
    return max(0, min(n - 1, int((valor - origen) / paso + _MARGEN_CELDA)))


def _paso_de_grilla(valores: list[float], n_grupos: int) -> float | None:
    """Distancia entre celdas, deducida de dónde están las anclas.

    Las anclas se agrupan por los huecos grandes (una posición por celda) y el
    paso sale de la distancia entre la primera y la última. Devuelve None si
    las anclas no se separan en exactamente n_grupos posiciones.
    """
    if n_grupos <= 1:
        return 0.0
    limites = _cortar_por_huecos(valores, n_grupos)
    if len(limites) != n_grupos - 1:
        return None
    grupos: dict[int, list[float]] = {}
    for v in valores:
        grupos.setdefault(_indice_por_limites(v, limites), []).append(v)
    if len(grupos) != n_grupos:
        return None
    centros = [sum(grupos[i]) / len(grupos[i]) for i in range(n_grupos)]
    paso = (centros[-1] - centros[0]) / (n_grupos - 1)
    return paso if paso > 0 else None


def _indices_por_orden(comps: list[dict], n: int, paso: float, eje: int) -> dict[int, int]:
    """Celda de cada cuadro por ORDEN, para las variables que aparecen una vez por celda.

    Por qué existe: repartir por paso fijo (`_indice_por_paso`) es una división
    entera, y una división entera tiene un borde. Caso real (Ivan, 16/09/2026,
    plantilla "Cenefas 3xa4-202609-3xA4"): al editarla, el <<promoOferta>> de la
    tercera cenefa quedó en y=22,88 cm y el corte entre la banda 2 y la 3 caía
    en y=22,882. Por DOS CENTÉSIMAS DE MILÍMETRO ese cuadro se fue a la banda
    del medio: la banda 2 terminó con dos <<promoOferta>> y la 3 sin ninguno.
    Consecuencia medida sobre un mailing real de 440 filas: 17 de las 147 hojas
    salieron mal. La tercera cenefa sacó el precio UNITARIO de un combo en vez
    del total --un precio falso en góndola, $69 donde iba "2 por $139"-- y el
    cuadro de más se dibujó a 0,84 cm del precio del tercer producto, o sea
    encima. Nadie se enteró hasta que salió impreso.

    Si una variable aparece EXACTAMENTE n veces --una por celda, que es lo que
    significa-- no hace falta medir nada: la de más arriba va a la primera
    celda, la siguiente a la segunda, y así. Es ordinal, no métrico; ningún
    milímetro lo puede correr de lugar.

    El resguardo: solo se reparte por orden si las n apariciones están de
    verdad separadas, con un salto de al menos medio paso entre una y la
    siguiente. Una variable que aparece n veces pero TODAS dentro de la misma
    cenefa --por ejemplo un precio partido en varios cuadros-- se deja al
    camino por paso, porque ahí el orden mentiría.

    Devuelve {id(cuadro): índice}; los cuadros que no están en el diccionario
    se siguen ubicando como siempre.
    """
    if n <= 1 or paso <= 0:
        return {}

    por_variable: dict[str, list[dict]] = {}
    for c in comps:
        for var in _nombres_de_variable(c):
            por_variable.setdefault(var, []).append(c)

    propuestas: dict[int, set[int]] = {}
    for grupo in por_variable.values():
        if len(grupo) != n:
            continue
        ordenados = sorted(grupo, key=lambda c: _esquina(c)[eje])
        coords = [_esquina(c)[eje] for c in ordenados]
        if any(b - a < paso / 2 for a, b in zip(coords, coords[1:])):
            continue
        for i, c in enumerate(ordenados):
            propuestas.setdefault(id(c), set()).add(i)

    # Un mismo cuadro puede contar para dos variables (multi-segmento). Si las
    # dos lo mandan a la misma celda, listo; si se contradicen, no se decide
    # acá y queda para el reparto por paso.
    return {cid: next(iter(celdas)) for cid, celdas in propuestas.items() if len(celdas) == 1}


def _asignar_grilla(
    non_bg: list[dict], anclas: list[dict], n_filas: int, n_cols: int
) -> list[list[dict]] | None:
    """Reparte los componentes en una grilla de n_filas x n_cols, o None si no cierra.

    Primero se reparte por ORDEN (`_indices_por_orden`): las variables que
    aparecen una vez por celda se ubican contándolas, sin medir. Lo que ahí no
    se pueda decidir --cuadros fijos, imágenes, variables que aparecen varias
    veces por cenefa-- cae al reparto por paso, que es lo que sigue.

    El reparto por paso es por PASO FIJO, no por el punto medio entre anclas. Las celdas
    de una cenefa son rectángulos iguales y repetidos: el ancla marca dónde
    ARRANCA cada celda, y el contenido de esa celda se extiende hacia la
    derecha y hacia abajo hasta donde arranca la siguiente.

    Cortar por el punto medio entre anclas asumía que el contenido está
    centrado en su ancla, y no lo está. En la A5 las anclas caen en x=0,00 y
    x=15,07, así que el corte quedaba en 7,54 -- y el cuadro del decimal del
    precio de la cenefa IZQUIERDA, que vive en x=10,92, se iba a la celda de la
    derecha. Resultado visible: la cenefa de la izquierda imprimía el decimal
    del producto de la derecha ("175" del producto 1 con el ",80" del producto
    2) y encima quedaba mal plantado.
    """
    paso_x = _paso_de_grilla([_esquina(c)[0] for c in anclas], n_cols)
    if paso_x is None:
        return None
    origen_x = min(_esquina(c)[0] for c in non_bg)

    # Primero por orden (ver `_indices_por_orden`), y lo que ahí no se pueda
    # decidir --cuadros fijos, variables que no aparecen una vez por celda--
    # sigue cayendo por paso, como siempre.
    orden_x = _indices_por_orden(non_bg, n_cols, paso_x, 0)
    columnas: dict[int, list[dict]] = {}
    for c in non_bg:
        col = orden_x.get(id(c))
        if col is None:
            col = _indice_por_paso(_esquina(c)[0], origen_x, paso_x, n_cols)
        columnas.setdefault(col, []).append(c)
    if len(columnas) != n_cols:
        return None

    ids_ancla = {id(c) for c in anclas}
    celdas: dict[tuple[int, int], list[dict]] = {}
    for col, comps_col in columnas.items():
        ys_ancla = [_esquina(c)[1] for c in comps_col if id(c) in ids_ancla]
        if len(ys_ancla) != n_filas:
            return None
        # Las filas se resuelven DENTRO de cada columna: cada columna puede
        # tener su propio corrimiento vertical (en la 6xA4 la columna derecha
        # arranca 2 mm más abajo que la izquierda).
        paso_y = _paso_de_grilla(ys_ancla, n_filas)
        if paso_y is None:
            return None
        origen_y = min(_esquina(c)[1] for c in comps_col)
        orden_y = _indices_por_orden(comps_col, n_filas, paso_y, 1)
        for c in comps_col:
            fila = orden_y.get(id(c))
            if fila is None:
                fila = _indice_por_paso(_esquina(c)[1], origen_y, paso_y, n_filas)
            celdas.setdefault((fila, col), []).append(c)

    # Orden de lectura: izquierda a derecha, después hacia abajo.
    ordenadas = [celdas.get((f, col), []) for f in range(n_filas) for col in range(n_cols)]
    if not all(ordenadas):
        return None
    # Cada celda tiene que quedarse con exactamente un ancla. Si alguna quedó
    # con dos, la grilla propuesta no es la que tiene el diseño.
    if any(sum(1 for c in g if id(c) in ids_ancla) != 1 for g in ordenadas):
        return None

    # Red de seguridad para todo lo que el reparto por orden no pudo decidir:
    # una variable que aparece exactamente una vez por celda NO puede terminar
    # DOS veces en la misma celda. Si eso pasa, la grilla propuesta no es la
    # que tiene el diseño, y es preferible no repartir --que se note-- antes
    # que imprimir en una cenefa el dato de otro producto, que es lo que pasó
    # el 16/09/2026 con <<promoOferta>> y nadie vio hasta la impresión.
    from collections import Counter

    n_slots = n_filas * n_cols
    conteo: Counter = Counter()
    for c in non_bg:
        conteo.update(_nombres_de_variable(c))
    for grupo in ordenadas:
        vistas: set[str] = set()
        for c in grupo:
            for var in _nombres_de_variable(c):
                if var in vistas and conteo[var] == n_slots:
                    return None
                vistas.add(var)
    return ordenadas


def _detect_slot_bands(components: list[dict]) -> list[list[dict]] | None:
    """Agrupa los componentes de una plantilla multi-producto, un grupo por slot.

    n_slots = GCD de cuántas veces aparece cada variable -- NO el máximo. Una
    variable puede aparecer más de una vez POR slot (un precio partido en
    placeholder de entero + placeholder de decimal, ambos apuntando a la misma
    variable canónica) sin que eso signifique que hay más slots. Con max(), una
    plantilla de 3 slots donde cada precio tiene 2 placeholders se detectaba
    como 6, y de ahí salían grupos mezclando datos de dos productos distintos.

    El conteo mira tanto c["variable"] como c["segments"]: PowerPoint parte los
    placeholders en varios runs al editarlos, y una plantilla real puede tener
    TODOS sus componentes como multi-segmento. Contando solo c["variable"] el
    Counter quedaba vacío y la página entera se trataba como un solo producto.

    La distribución se resuelve como GRILLA (filas x columnas). Los tres
    diseños en uso son distintos:

        3xA4  ->  3 filas x 1 columna   (una debajo de otra)
        A5    ->  1 fila  x 2 columnas  (una al lado de la otra)
        6xA4  ->  3 filas x 2 columnas  (abajo y al costado)

    Ordenando solo por Y --como se hacía antes-- los dos cuadros de una misma
    fila quedan pegados en el orden y el corte los mandaba al mismo grupo: las
    cenefas de la derecha repetían el producto de la izquierda. Se veía en
    6xA4 y en A5; el 3xA4 zafaba por tener una sola columna.

    Devuelve None cuando hay un solo slot (render normal, un producto por
    página).
    """
    import math
    from collections import Counter
    from functools import reduce

    non_bg = [c for c in components if not c.get("locked")]
    var_counts: Counter = Counter()
    for c in non_bg:
        var_counts.update(_nombres_de_variable(c))
    if not var_counts:
        return None

    cuentas = list(var_counts.values())
    gcd_total = reduce(math.gcd, cuentas)

    # Cuántos slots puede tener la hoja, del más probable al menos.
    #
    # El GCD de TODOS los conteos era el único criterio, y un solo cuadro
    # suelto lo tiraba a 1 -- o sea, la hoja entera pasaba a tratarse como un
    # producto. Caso real de Ivan (14/09/2026), Rompe Precios Congelados 3xA4:
    # seis variables aparecían 3 veces cada una y `decimalPrecioBanco` UNA sola
    # (el diseño tiene ese cuadro en la primera cenefa y no en las otras dos).
    # GCD(3,3,3,3,3,3,1) = 1, y las tres cenefas de la hoja salían con el mismo
    # producto. De paso se caía el "muevo uno, muevo todos", que se apoya en
    # las bandas para saber quiénes son hermanos.
    #
    # Ahora el GCD sigue siendo el PRIMER candidato --así ninguna plantilla que
    # hoy anda cambia de comportamiento-- y detrás van los divisores que la
    # mayoría de las variables respeta. Elegir de más apoyo a menos, y no de
    # más grande a más chico, evita que un precio partido en dos placeholders
    # (una variable con el doble de apariciones) haga creer que hay el doble de
    # cenefas.
    #
    # Ser más permisivo acá no es riesgoso: _asignar_grilla valida en serio
    # --exige un ancla por celda, ninguna celda vacía y el paso de la grilla
    # consistente-- y descarta cualquier candidato que no cierre.
    candidatos: list[int] = [gcd_total] if gcd_total > 1 else []
    apoyo: dict[int, int] = {}
    for n in range(max(cuentas), 1, -1):
        soporte = sum(1 for k in cuentas if k % n == 0)
        # Hace falta una variable que aparezca EXACTAMENTE n veces: es la que
        # da las anclas. Y que la mayoría de las variables acompañe, para no
        # inventar una grilla a partir de un caso aislado.
        if any(k == n for k in cuentas) and soporte * 2 >= len(cuentas):
            apoyo[n] = soporte
    for n in sorted(apoyo, key=lambda k: (-apoyo[k], -k)):
        if n not in candidatos:
            candidatos.append(n)

    if not candidatos:
        return None

    for n_slots in candidatos:
        # Las ANCLAS son los cuadros de una variable que aparece exactamente
        # una vez por slot (descripcion, codigo...): marcan dónde está cada
        # cenefa.
        ancla = next((v for v, n in var_counts.items() if n == n_slots), None)
        if ancla is None:
            continue
        anclas = [c for c in non_bg if ancla in _nombres_de_variable(c)]
        xs_ancla = sorted({round(_esquina(c)[0], 1) for c in anclas})

        # Cuántas columnas hay: se prueba de más a menos, y se acepta la
        # primera grilla que reparta a todos los cuadros dejando un ancla por
        # celda.
        for n_cols in range(min(len(xs_ancla), n_slots), 0, -1):
            if n_slots % n_cols:
                continue
            grilla = _asignar_grilla(non_bg, anclas, n_slots // n_cols, n_cols)
            if grilla is not None:
                return grilla

    # Sin anclas utilizables o con una grilla que no cierra, se cae al criterio
    # viejo: ordenar por Y y cortar en grupos iguales. Solo con el GCD: repartir
    # a ciegas en N grupos iguales a partir de un candidato adivinado mezclaría
    # datos de productos distintos, que es peor que no agrupar.
    if gcd_total <= 1:
        return None
    n_slots = gcd_total
    sorted_comps = sorted(non_bg, key=lambda c: _esquina(c)[1])
    total = len(sorted_comps)
    group_size = total // n_slots
    remainder = total % n_slots

    bands: list[list[dict]] = []
    idx = 0
    for i in range(n_slots):
        size = group_size + (1 if i < remainder else 0)
        bands.append(sorted_comps[idx: idx + size])
        idx += size
    return bands


def patch_image_overrides(
    components: list[dict], image_overrides: dict[str, tuple[bytes, str]]
) -> list[dict]:
    """Inyecta imágenes subidas (ej. cocarda) en los componentes de imagen que
    referencien esa variable. Se usa tanto acá como en el paso de preview
    (jobs.py), para que la imagen ya esté horneada en el template_def antes
    de que el usuario llegue a reposicionar."""
    import base64 as _b64

    patched = []
    for c in components:
        var = c.get("variable")
        if c.get("type") == "image" and var and var in image_overrides:
            img_bytes, img_ext = image_overrides[var]
            patched.append({
                **c,
                "image_data": _b64.b64encode(img_bytes).decode(),
                "image_ext":  img_ext,
            })
        else:
            patched.append(c)
    return patched


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def render_template_to_pptx(
    template_def: dict,
    products: list[dict],
    target_format: str = "a4",
    image_overrides: dict[str, tuple[bytes, str]] | None = None,
    source_pptx_bytes: bytes | None = None,
) -> tuple[bytes, list[str]]:
    """Genera PPTX desde una definición v2 y una lista de productos.

    image_overrides: {variable_name: (image_bytes, ext)} — inyecta imágenes
    subidas en la página de generación como image_data de los componentes
    que usen esa variable.

    source_pptx_bytes: bytes del PPTX original del que se importó el
    template (si vino de un archivo subido, no armado a mano en el editor).
    Cuando está presente, el slide base se reusa/duplica desde ESE archivo
    en vez de reconstruirse desde una presentación en blanco — así se
    preserva el diseño (fondo, master, layout, cualquier shape que el
    importer no haya capturado como componente) tal cual estaba. Sin esto,
    el resultado solo tiene los shapes que SÍ se lograron extraer, y
    cualquier diseño que viva en el layout/master del archivo se pierde.

    Returns (pptx_bytes, missing_vars) donde missing_vars es la lista de
    variables que el template usa pero que no fueron encontradas en el Excel.
    """
    master_format = template_def.get("master_format", "a4")
    components    = template_def.get("components", [])
    rules         = template_def.get("rules", [])

    if image_overrides:
        components = patch_image_overrides(components, image_overrides)
    fmt_info      = get_format(target_format)
    slots         = fmt_info["slots"]

    missing_vars: set[str] = set()

    # ── Detect internal slots from variable repetition count ─────────────────
    # A template encodes N products per slide when its variables each appear N
    # times. Sort components by Y, split into N consecutive groups, and fill
    # each group with one product row — regardless of format or page size.
    slot_bands = _detect_slot_bands(components)

    # Preservar diseño original: solo cuando tenemos los bytes crudos Y el
    # layout no necesita tileo DENTRO de una misma página armado por el
    # motor (slot_bands ya trae sus N celdas pre-armadas en el archivo;
    # slots==1 es una celda por página, tampoco hace falta tilear). El caso
    # restante (una plantilla de una sola celda que el motor debe repetir
    # con offsets dentro de la página, ej. subir un solo pincho y pedirle al
    # sistema que arme la grilla de 6) sigue usando el canvas en blanco.
    preserve_source = source_pptx_bytes is not None and (slot_bands is not None or slots == 1)

    prs = None
    if preserve_source:
        try:
            prs = Presentation(io.BytesIO(source_pptx_bytes))
            if not prs.slides:
                prs = None
        except Exception:
            prs = None
        preserve_source = prs is not None

    if preserve_source:
        # Cuadros eliminados (en el preview o guardados así en la plantilla):
        # su forma del PPTX fuente sale de la hoja base ANTES de copiarla.
        _sacar_formas_eliminadas(prs.slides[0], template_def.get("formas_eliminadas"), components)

        # El fondo extraído del MASTER (pptx_importer.py, name="fondo",
        # _source_shape_id=None a propósito) no tiene un shape real en el
        # slide para mutar — cualquier slide que comparta layout/master ya lo
        # hereda visualmente solo con add_slide(), sin dibujar nada de nuevo.
        # Si no se filtra acá, _place_component nunca encuentra shape para
        # mutar y cae al fallback de "crear uno nuevo" en CADA render — y
        # como _duplicate_slide() copia lo que el slide base tenga en ese
        # momento, cada producto siguiente arrastra una copia extra apilada
        # sobre la anterior (bug real, visto con productos duplicando el
        # diseño 2-3 veces encimados).
        components = [
            c for c in components
            if not (c.get("type") == "image" and c.get("variable") is None and c.get("_source_shape_id") is None)
        ]

    if not preserve_source:
        slide_w, slide_h = FORMAT_SLIDES.get(target_format, FORMAT_SLIDES["a4"])
        prs = Presentation()
        prs.slide_width  = slide_w
        prs.slide_height = slide_h

    blank_layout = prs.slide_layouts[6] if not preserve_source else None
    base_slide   = prs.slides[0] if preserve_source else None

    def _next_slide(is_first: bool):
        if preserve_source:
            return base_slide if is_first else _duplicate_slide(prs, base_slide)
        return prs.slides.add_slide(blank_layout)

    if slot_bands:
        bg_comps    = [c for c in components if c.get("locked")]
        n_slots     = len(slot_bands)
        page_groups = [products[i:i + n_slots] for i in range(0, len(products), n_slots)]

        # Todas las hojas se crean ANTES de dibujar. _duplicate_slide copia el
        # slide base tal como está en ese momento, así que clonar después de
        # haber renderizado la página anterior arrastra sus mutaciones -- y
        # ahora que un cuadro vacío se saca del slide, la página 2 nacería sin
        # la cocarda solo porque el primer producto no tenía mecánica.
        hojas = [_next_slide(gi == 0) for gi in range(len(page_groups))]

        for pg, slide in zip(page_groups, hojas):
            shape_map = _shape_id_map(slide.shapes) if preserve_source else {}
            if bg_comps:
                # Los componentes de un slot_bands ya vienen en coordenadas
                # absolutas (una página con N celdas pre-armadas) — nunca hay
                # que re-escalarlos contra target_format, solo posicionarlos
                # tal cual quedaron en master_format. Ver bug histórico: esto
                # antes escalaba por target_format y comprimía la grilla.
                laid_bg = compute_layout(bg_comps, master_format, master_format)
                _render_slide(slide, laid_bg, {}, missing_vars=missing_vars, shape_map=shape_map)
            # Cada celda se resuelve contra SU producto. Ya no se unifican los
            # cuerpos entre celdas: eso lo hacía _unificar_tamanos_entre_bandas,
            # que copiaba a toda la hoja el cuerpo de la celda más exigida --un
            # solo producto con un precio de 5 cifras arrastraba las otras cinco
            # al mínimo. Con el cuerpo declarado por regla el problema no existe:
            # la regla se evalúa igual en las seis celdas, así que un mismo
            # largo de precio da el mismo cuerpo sin necesidad de emparejar nada
            # después.
            ajustadas: dict[int, list[dict]] = {}
            for band_idx, band_comps in enumerate(slot_bands):
                if band_idx >= len(pg):
                    continue
                laid_band = compute_layout(band_comps, master_format, master_format)
                ajustadas[band_idx] = preparar_componentes(laid_band, rules, pg[band_idx])

            for band_idx, band_comps in enumerate(slot_bands):
                if band_idx < len(pg):
                    _render_slide(slide, ajustadas[band_idx], pg[band_idx],
                                  missing_vars=missing_vars, shape_map=shape_map)
                elif preserve_source:
                    laid_band = compute_layout(band_comps, master_format, master_format)
                    # Página parcial (menos productos que celdas) y estamos
                    # preservando el diseño original: si no se limpia, la
                    # celda sin producto queda con lo que tuviera el archivo
                    # fuente (ej. datos de ejemplo del diseñador).
                    _render_slide(slide, laid_band, {}, shape_map=shape_map, slot_vacio=True)
                # Sin preserve_source: no hay nada que limpiar, la celda
                # simplemente nunca tuvo shapes creados (comportamiento
                # de siempre para el canvas en blanco).

        aplicar_autofit_de_pruebas(prs, template_def)
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue(), sorted(missing_vars)

    # ── Single-slot template: one product per format-cell, tiled by offset ───
    # Used for 3xa4 / pinchos / any format where the slide IS the unit cell
    # and multiple cells are arranged spatially on the output page. Cuando
    # preserve_source es True acá slots siempre es 1 (gateado más arriba),
    # así que el offset por slot da siempre 0 — un producto, un slide, sin
    # tileo interno.
    laid_out  = compute_layout(components, target_format, master_format)
    slot_cols = fmt_info.get("slot_cols", 1)
    cell_w    = fmt_info["width_cm"]
    cell_h    = fmt_info["height_cm"]
    groups    = [products[i:i + slots] for i in range(0, len(products), slots)]

    # Igual que en el camino de varias franjas: TODAS las hojas se crean antes
    # de dibujar. _duplicate_slide copia el slide base tal como esta en ese
    # momento, y desde que un cuadro vacio se saca del slide, clonar despues de
    # renderizar la hoja anterior arrastra sus faltantes. Sintoma real: 43
    # cenefas A4 salieron TODAS sin cocarda porque el primer producto no tenia
    # mecanica -- el resto se clono de esa base ya mutilada.
    hojas = [_next_slide(gi == 0) for gi in range(len(groups))]

    for group, slide in zip(groups, hojas):
        shape_map = _shape_id_map(slide.shapes) if preserve_source else {}

        for slot_idx, product in enumerate(group):
            col = slot_idx % slot_cols
            row = slot_idx // slot_cols
            slot_offset_x = col * cell_w
            slot_offset_y = row * cell_h

            visible_comps = preparar_componentes(laid_out, rules, product)

            _render_slide(slide, visible_comps, product, slot_offset_x, slot_offset_y, missing_vars=missing_vars, shape_map=shape_map)

    aplicar_autofit_de_pruebas(prs, template_def)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue(), sorted(missing_vars)


def generate_from_template_v2(
    template_def: dict,
    excel_bytes: bytes,
    target_format: str = "a4",
    vigencia: str = "",
    legales: str = "",
    usar_legales: bool = False,
    image_overrides: dict[str, tuple[bytes, str]] | None = None,
) -> tuple[bytes, list[str]]:
    """Parsea Excel y genera PPTX desde una definición de template.

    Camino directo sin jobs -- lo usa la generación sincrónica. El flujo
    normal de la plataforma pasa por jobs.py (preview + confirmación).
    """
    products = load_products_from_bytes(excel_bytes, vigencia, legales, usar_legales)
    return render_template_to_pptx(template_def, products, target_format, image_overrides)
