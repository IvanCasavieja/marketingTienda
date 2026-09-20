"""Fija que el aviso de "un texto se imprime encima de otro" vea los dos casos
que se le escapaban (20/09/2026).

Los dos aparecieron auditando la plantilla de Alemania con un listado de 14
filas, y ninguno era de esa plantilla en particular: son del motor, y le pasaban
a todas.

1. **Un cuadro con segmentos se medía como UN renglón.** `_rect_texto_real`
   sumaba el ancho de los pedazos y daba el alto de una sola línea. Y los
   cuadros con segmentos son casi todos, porque el importador los crea así. La
   descripción del pack de cervezas de Alemania necesita 5 renglones de 40 pt
   --8,5 cm-- en una caja de 5,39: se imprime encima de "PRECIO REGULAR" y de
   "OFERTA", y el detector no decía nada porque la medía como un renglón de
   1,62 cm de alto.

2. **Solo se miraba la PRIMERA fila del Excel.** Un desborde que aparece en la
   fila 7 no daba ningún aviso: la pantalla mostraba la fila 1 limpia y se
   mandaba a imprimir. En Alemania, la fila 1 no tiene ningún choque y hay dos
   filas que sí.

Y el efecto colateral que hubo que resolver para que el arreglo 1 no fuera peor
que el problema: al empezar a cortar renglones, un ancho medido de MÁS inventaba
cortes que en el papel no existen. "PRECIO REGULAR: $320 unidad" a 25 pt en
Franklin Gothic Medium Cond se mide 8% más ancho que su caja --porque la
condensada no está en la tabla y cae en la no condensada, que es más ancha-- así
que el detector avisaba un choque en los 14 carteles. De ahí
`font_metrics.margen_de_error`: el corte de línea se declara solo si el exceso
supera el error posible de medición de esa tipografía.
"""
from app.services.cenefas.component_renderer import (
    _rect_texto_real,
    detectar_solapes,
    detectar_solapes_del_lote,
)
from app.services.cenefas.font_metrics import margen_de_error


def _cuadro(id_, y, alto, pt, segmentos, x=1.0, ancho=19.0, familia="Impact"):
    """Un cuadro con segmentos, que es como los crea el importador."""
    return {
        "id": id_, "type": "text", "name": id_, "visible": True,
        "base_bounds": {"x": x, "y": y, "width": ancho, "height": alto},
        "style": {"font_size": pt, "align": "center", "font_family": familia},
        "segments": [
            {"type": t, "value": v, "style": {"font_size": p, "font_family": familia}}
            for t, v, p in segmentos
        ],
    }


LARGA = ("Pack degustación de cervezas alemanas importadas surtidas, "
         "incluye rubia, roja y negra, 6 unidades")


# ------------------------------------------- 1) los renglones de verdad


def test_un_cuadro_con_segmentos_se_mide_con_sus_renglones():
    comp = _cuadro("desc", y=9.39, alto=5.39, pt=40, segmentos=[("variable", "descripcion", 40)])
    r = _rect_texto_real(comp, {"descripcion": LARGA})
    assert r["width"] <= 19.0, "un texto que se corta en renglones no puede ser más ancho que su caja"
    assert r["height"] > 5.39, (
        "una descripción que necesita 5 renglones en una caja de 3 tiene que "
        "medirse más alta que la caja; si no, nadie se entera de que desborda")


def test_un_precio_largo_sigue_saliendo_de_una_sola_linea():
    # "14.990" no tiene por dónde cortarse: se dibuja en una línea y sobresale
    # a los costados. Ese comportamiento no cambia.
    comp = _cuadro("precio", y=18.0, alto=6.2, pt=140, ancho=12.213,
                   segmentos=[("variable", "unidadMoneda", 80), ("variable", "precioOferta", 140)])
    r = _rect_texto_real(comp, {"unidadMoneda": "$", "precioOferta": "14.990"})
    assert r["width"] > 12.213, "el precio largo tiene que salir más ancho que su caja"
    assert r["height"] < 6.2, "y en un solo renglón"


def test_la_descripcion_larga_pisa_a_los_cuadros_de_abajo():
    desc = _cuadro("desc", y=9.39, alto=5.39, pt=40, segmentos=[("variable", "descripcion", 40)])
    regular = _cuadro("regular", y=15.01, alto=1.33, pt=25, x=3.7, ancho=12.2,
                      segmentos=[("static", "PRECIO REGULAR: ", 25), ("variable", "precioRegular", 25)])
    fila = {"descripcion": LARGA, "precioRegular": "890"}
    avisos = detectar_solapes([(desc, fila), (regular, fila)])
    assert avisos, "la descripción se imprime sobre el precio regular y no se avisaba"
    assert avisos[0]["component_id"] == "desc"


def test_no_se_inventa_un_corte_de_linea_con_una_tipografia_que_no_medimos_exacto():
    # El renglón real de Alemania. Se mide 8% más ancho que su caja porque la
    # condensada cae en la no condensada; con la fuente de verdad entra.
    assert margen_de_error("Franklin Gothic Medium Cond") == 0.20
    assert margen_de_error("Impact") == 0.0
    assert margen_de_error("Aptos") == 0.25
    comp = _cuadro("regular", y=15.01, alto=1.33, pt=25, x=3.738, ancho=12.213,
                   familia="Franklin Gothic Medium Cond",
                   segmentos=[("static", "PRECIO REGULAR: ", 25), ("variable", "unidadMoneda", 25),
                              ("variable", "precioRegular", 25), ("static", " unidad", 25)])
    r = _rect_texto_real(comp, {"unidadMoneda": "$", "precioRegular": "320"})
    assert r["height"] < 1.1, (
        "se partió en dos renglones por un 8% de exceso medido con una fuente "
        "sustituta: eso daba un aviso falso en los 14 carteles de Alemania")


# ------------------------------------------- 2) todas las filas del Excel


def _plantilla_con_descripcion():
    return [
        _cuadro("desc", y=9.39, alto=5.39, pt=40, segmentos=[("variable", "descripcion", 40)]),
        _cuadro("regular", y=15.01, alto=1.33, pt=25, x=3.7, ancho=12.2,
                segmentos=[("static", "PRECIO REGULAR: ", 25), ("variable", "precioRegular", 25)]),
    ]


def test_un_desborde_de_la_fila_7_tambien_avisa():
    productos = [{"descripcion": "Pretzel. 100 g", "precioRegular": "85"} for _ in range(6)]
    productos.append({"descripcion": LARGA, "precioRegular": "890"})
    assert not detectar_solapes([(c, productos[0]) for c in _plantilla_con_descripcion()]), \
        "la fila 1 está limpia: es justo por eso que mirar solo la primera no alcanzaba"
    avisos = detectar_solapes_del_lote(_plantilla_con_descripcion(), [], productos)
    assert avisos, "el desborde de la fila 7 tiene que avisar"
    assert avisos[0]["fila"] == 7, "y tiene que decir en qué fila pasa"


def test_el_mismo_choque_en_muchas_filas_es_un_solo_aviso():
    productos = [{"descripcion": LARGA, "precioRegular": "890"} for _ in range(30)]
    avisos = detectar_solapes_del_lote(_plantilla_con_descripcion(), [], productos)
    pares = {(a["component_id"], a["contra_id"]) for a in avisos}
    assert len(avisos) == len(pares), "un par de cuadros = un aviso, no uno por fila"
    peor = next(a for a in avisos if a["component_id"] == "desc" and a["contra_id"] == "regular")
    assert peor["filas"] == 30, "pero tiene que decir en cuántas filas pasa"


def test_una_corrida_limpia_no_avisa_nada():
    productos = [{"descripcion": "Pretzel. 100 g", "precioRegular": "85"} for _ in range(50)]
    assert detectar_solapes_del_lote(_plantilla_con_descripcion(), [], productos) == []


def test_sin_productos_no_avisa_ni_explota():
    assert detectar_solapes_del_lote(_plantilla_con_descripcion(), [], []) == []


def test_en_una_hoja_de_varias_cenefas_cada_celda_va_con_su_fila():
    # Una 3xA4: tres bandas, cada una con su producto. La fila que desborda es
    # la 5, o sea la segunda celda de la segunda hoja.
    bandas = []
    for i in range(3):
        bandas.append([
            _cuadro(f"desc{i}", y=9.39 + i * 9.9, alto=5.39, pt=40,
                    segmentos=[("variable", "descripcion", 40)]),
            _cuadro(f"regular{i}", y=15.01 + i * 9.9, alto=1.33, pt=25, x=3.7, ancho=12.2,
                    segmentos=[("static", "PRECIO REGULAR: ", 25), ("variable", "precioRegular", 25)]),
        ])
    productos = [{"descripcion": "Pretzel. 100 g", "precioRegular": "85"} for _ in range(6)]
    productos[4] = {"descripcion": LARGA, "precioRegular": "890"}
    avisos = detectar_solapes_del_lote([], [], productos, slot_bands=bandas)
    assert avisos, "el desborde de la celda del medio de la segunda hoja tiene que avisar"
    assert avisos[0]["fila"] == 5
    assert avisos[0]["component_id"] == "desc1", "y señalar la banda correcta"
