"""Dos mejoras pedidas por Ivan el 23/09/2026, después del mailing del 24-27.

1. FECHA POR BLOQUE. Una página puede traer dos promociones con dos vigencias
   ("Rompe Precios Congelados" arriba, "Rompe Precios Limpieza" abajo). Hasta
   ahora esa carilla quedaba ambigua y la fecha no se comparaba. Ahora el
   lector dice bajo qué encabezado está cada producto (`promocion`) y la
   pasada de promociones dice qué vigencia tiene cada encabezado: la fecha que
   se le exige a la placa es la de SU bloque. "Esto no puede pasar", dijo Ivan.

2. LECTURA POR MITADES. Una carilla muy densa no entraba en una respuesta y
   salía "hay demasiado contenido para leer de una vez". Ahora se lee por
   mitades y se juntan, sin contar dos veces lo que cae en el solape.
"""
from app.services.rrss import reglas
from app.services.rrss.catti import (
    _fusionar_lecturas, _mismo_producto, vigencias_por_promocion,
)
from app.services.rrss.comparador import _vigencia_por_nombre, comparar_elementos

CONGELADOS = "Del 23 al 30 de setiembre"
FINDE = "DEL JUEVES 24 AL DOMINGO 27 DE SETIEMBRE"


# ---------------------------------------------------------------------------
# 1. La vigencia de cada bloque
# ---------------------------------------------------------------------------

def test_cada_promocion_con_su_vigencia():
    promos = [
        {"nombre": "Rompe Precios Congelados", "vigencia": CONGELADOS, "carillas": [0]},
        {"nombre": "Los Rompe del Finde", "vigencia": FINDE, "carillas": [1, 2, 3]},
    ]
    assert vigencias_por_promocion(promos, {}) == {
        "Rompe Precios Congelados": CONGELADOS, "Los Rompe del Finde": FINDE,
    }


def test_una_promocion_sin_fecha_escrita_la_toma_de_su_carilla():
    promos = [{"nombre": "Finde", "vigencia": "", "carillas": [1, 2]}]
    assert vigencias_por_promocion(promos, {"1": FINDE}) == {"Finde": FINDE}


def test_una_promocion_sin_ninguna_fecha_no_entra():
    promos = [{"nombre": "Sin fecha", "vigencia": "", "carillas": [5]}]
    assert vigencias_por_promocion(promos, {}) == {}


def test_una_promocion_sin_nombre_no_entra():
    assert vigencias_por_promocion([{"nombre": "", "vigencia": FINDE, "carillas": [0]}], {}) == {}


# ---------------------------------------------------------------------------
# 1. Buscar el bloque por su nombre, con tolerancia
# ---------------------------------------------------------------------------

TABLA = {"Rompe Precios Congelados": CONGELADOS, "Los Rompe del Finde": FINDE}


def test_el_nombre_exacto_encuentra_su_vigencia():
    assert _vigencia_por_nombre(TABLA, "Rompe Precios Congelados") == CONGELADOS


def test_otra_mayuscula_o_una_tilde_no_lo_pierde():
    assert _vigencia_por_nombre(TABLA, "ROMPE PRECIOS CONGELADOS") == CONGELADOS
    assert _vigencia_por_nombre(TABLA, "Los Rompe del Findé") == FINDE


def test_un_nombre_que_no_se_parece_a_ninguno_no_inventa():
    assert _vigencia_por_nombre(TABLA, "Semana del Vino") == ""


def test_un_nombre_vacio_no_encuentra_nada():
    assert _vigencia_por_nombre(TABLA, "") == ""


# ---------------------------------------------------------------------------
# 1. La placa se compara contra la fecha de SU bloque
# ---------------------------------------------------------------------------

def _placa(fecha: str) -> dict:
    return {
        "fecha": fecha, "legal_bases": reglas.LEGAL_BASES, "legal_alcohol": "",
        "logo_campana_presente": True, "isotipo_presente": True,
        "imagen_producto": {"presente": True, "coincide_con_descripcion": True, "que_se_ve": "", "motivo": ""},
        "producto": {"descripcion": "Nuggets de pollo SEARA. 900 g"},
        "cta": "", "otros_textos": [],
    }


def _fila_fecha(filas):
    return next((f for f in filas if f["campo"] == "fecha"), None)


# Una carilla (la 0) con DOS bloques de fechas distintas: por carilla es ambigua.
_MAILING = {
    "fecha": CONGELADOS,
    "fechas_por_pagina": {"0": CONGELADOS},
    "vigencia_por_pagina": {"0": None},
    "vigencia_por_promocion": {"Rompe Precios Congelados": CONGELADOS, "Especiales del Finde": FINDE},
    "productos": [],
}


def test_en_una_carilla_con_dos_bloques_manda_el_bloque_del_producto():
    item = {"promocion": "Especiales del Finde", "pagina": 0}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), _MAILING, {}, False, pagina=0, item=item))
    assert fila is None or fila["estado"] == "ok"


def test_y_el_otro_bloque_de_la_misma_carilla_tiene_la_otra_fecha():
    item = {"promocion": "Rompe Precios Congelados", "pagina": 0}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), _MAILING, {}, False, pagina=0, item=item))
    assert fila is not None and fila["estado"] != "ok"


def test_sin_bloque_en_una_carilla_ambigua_sigue_sin_acusar():
    item = {"promocion": "", "pagina": 0}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), _MAILING, {}, False, pagina=0, item=item))
    assert fila is not None and fila["estado"] == "info"


def test_un_bloque_que_no_esta_en_la_tabla_cae_a_la_carilla():
    mailing = {**_MAILING, "vigencia_por_pagina": {"0": FINDE}}
    item = {"promocion": "Bloque que nadie vio", "pagina": 0}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), mailing, {}, False, pagina=0, item=item))
    assert fila is None or fila["estado"] == "ok"


# ---------------------------------------------------------------------------
# 2. Juntar las mitades de una página
# ---------------------------------------------------------------------------

def _prod(desc: str, precio: str = "$99") -> dict:
    return {"descripcion": desc, "oferta_precio": precio, "promocion": "", "pagina": 0}


def _lectura(productos, fecha="", legal=""):
    return {"fecha": fecha, "legal_alcohol": legal, "pagina": 0, "productos": productos}


def test_los_productos_de_las_dos_mitades_se_suman():
    arriba = _lectura([_prod("Yerba TIENDA INGLESA. 1 Kg")])
    abajo = _lectura([_prod("Refresco SCHWEPPES Citrus. 3 L", "$150")])
    assert len(_fusionar_lecturas([arriba, abajo])["productos"]) == 2


def test_un_producto_del_solape_queda_una_sola_vez():
    p = _prod("Yerba TIENDA INGLESA. 1 Kg")
    junto = _fusionar_lecturas([_lectura([p]), _lectura([dict(p)])])
    assert len(junto["productos"]) == 1


def test_una_letra_de_diferencia_en_el_solape_sigue_siendo_el_mismo():
    a = _prod("Yerba TIENDA INGLESA. 1 Kg")
    b = _prod("Yerba TIENDA INGLESA 1 Kg")     # sin el punto
    assert _mismo_producto(a, b)
    assert len(_fusionar_lecturas([_lectura([a]), _lectura([b])])["productos"]) == 1


def test_mismo_texto_con_otro_precio_son_dos_productos():
    # "Cerveza X lata" a $92 y a $125 son dos ofertas distintas, no un solape.
    a = _prod("Cerveza HEINEKEN. Lata", "$92")
    b = _prod("Cerveza HEINEKEN. Lata", "$125")
    assert not _mismo_producto(a, b)
    assert len(_fusionar_lecturas([_lectura([a]), _lectura([b])])["productos"]) == 2


def test_la_fecha_y_la_leyenda_salen_de_la_mitad_que_las_tenga():
    arriba = _lectura([], fecha="", legal="")
    abajo = _lectura([], fecha=FINDE, legal="Beber con moderación.")
    junto = _fusionar_lecturas([arriba, abajo])
    assert junto["fecha"] == FINDE
    assert junto["legal_alcohol"] == "Beber con moderación."


def test_la_primera_mitad_con_fecha_gana():
    junto = _fusionar_lecturas([_lectura([], fecha=CONGELADOS), _lectura([], fecha=FINDE)])
    assert junto["fecha"] == CONGELADOS


def test_la_pagina_se_conserva():
    assert _fusionar_lecturas([_lectura([]), _lectura([])])["pagina"] == 0
