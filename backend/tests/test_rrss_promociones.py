"""La fecha es de la promoción, no de la página.

El caso real (23/09/2026): el mailing del 24 al 27 era un díptico. Tapa y
las dos carillas interiores eran "Los Rompe del Finde" (24 al 27); en la
contratapa venía pegado "Rompe Precios" (23 al 30). Las carillas interiores
no repiten ni el nombre ni la fecha. Leído por página, un producto del interior
no tenía fecha y heredaba la primera del mailing —la de la contratapa— y la
placa del aceite, que estaba perfecta, salía con "Fecha: Distinto".

Encima, la fecha por carilla del arreglo anterior no se aplicaba en producción:
las claves int de fechas_por_pagina vuelven de la base (JSONB) como str.

Lo que fija este archivo:
  - cada carilla hereda la vigencia de SU promoción, tenga o no la fecha impresa;
  - una promoción sin fecha escrita la toma de alguna de sus carillas;
  - una carilla con promociones de fechas distintas queda ambigua, y ambigua
    NO se compara: se avisa, en vez de acusar contra la fecha equivocada;
  - las claves str de la base valen igual que las int.
"""
from app.services.rrss.catti import vigencias_por_carilla
from app.services.rrss import reglas
from app.services.rrss.comparador import comparar_elementos

FINDE = "DEL JUEVES 24 AL DOMINGO 27 DE SETIEMBRE"
ROMPE = "Del 23 al 30 de setiembre"


# ---------------------------------------------------------------------------
# vigencias_por_carilla
# ---------------------------------------------------------------------------

def test_el_diptico_real_cada_carilla_con_su_promocion():
    # carilla 0 contratapa (Rompe Precios), 1 tapa del finde, 2 y 3 interior del finde
    promos = [
        {"nombre": "Rompe Precios", "vigencia": ROMPE, "carillas": [0]},
        {"nombre": "Los Rompe del Finde", "vigencia": FINDE, "carillas": [1, 2, 3]},
    ]
    fechas = {0: ROMPE, 1: FINDE}   # el interior no trae fecha
    v = vigencias_por_carilla(promos, fechas, 4)
    assert v == {0: ROMPE, 1: FINDE, 2: FINDE, 3: FINDE}


def test_una_promocion_sin_fecha_escrita_la_toma_de_sus_carillas():
    promos = [{"nombre": "Finde", "vigencia": "", "carillas": [0, 1, 2]}]
    v = vigencias_por_carilla(promos, {1: FINDE}, 3)
    assert v == {0: FINDE, 1: FINDE, 2: FINDE}


def test_dos_promociones_con_la_misma_fecha_en_una_carilla_no_es_ambiguo():
    # Congelados y Limpieza en la misma carilla, las dos del 23 al 30
    promos = [
        {"nombre": "Congelados", "vigencia": ROMPE, "carillas": [0]},
        {"nombre": "Limpieza", "vigencia": ROMPE, "carillas": [0]},
    ]
    assert vigencias_por_carilla(promos, {}, 1) == {0: ROMPE}


def test_dos_promociones_con_fechas_distintas_en_una_carilla_queda_ambigua():
    promos = [
        {"nombre": "A", "vigencia": ROMPE, "carillas": [0]},
        {"nombre": "B", "vigencia": FINDE, "carillas": [0]},
    ]
    assert vigencias_por_carilla(promos, {}, 1) == {0: None}


def test_una_carilla_sin_promocion_se_queda_con_su_propia_fecha():
    v = vigencias_por_carilla([], {0: ROMPE}, 2)
    assert v == {0: ROMPE, 1: None}


def test_las_claves_str_de_la_base_valen_igual():
    promos = [{"nombre": "Finde", "vigencia": "", "carillas": [0, 1]}]
    v = vigencias_por_carilla(promos, {"1": FINDE}, 2)
    assert v == {0: FINDE, 1: FINDE}


def test_sin_pasada_de_promociones_es_la_fecha_por_carilla_de_antes():
    v = vigencias_por_carilla([], {"0": ROMPE, "1": FINDE}, 3)
    assert v == {0: ROMPE, 1: FINDE, 2: None}


# ---------------------------------------------------------------------------
# comparar_elementos: qué fecha se le exige a la placa
# ---------------------------------------------------------------------------

def _placa(fecha: str) -> dict:
    return {
        "fecha": fecha,
        "legal_bases": reglas.LEGAL_BASES,
        "legal_alcohol": "",
        "logo_campana_presente": True,
        "isotipo_presente": True,
        "imagen_producto": {"presente": True, "coincide_con_descripcion": True, "que_se_ve": "", "motivo": ""},
        "producto": {"descripcion": "Aceite de Oliva Extra Virgen TIENDA INGLESA. 500 ml"},
        "cta": "", "otros_textos": [],
    }


def _fila_fecha(filas):
    return next((f for f in filas if f["campo"] == "fecha"), None)


_MAILING = {
    "fecha": ROMPE,                       # la primera del mailing: la de la contratapa
    "fechas_por_pagina": {"0": ROMPE, "1": FINDE},     # como vuelve de la base
    "vigencia_por_pagina": {"0": ROMPE, "1": FINDE, "2": FINDE, "3": FINDE},
    "productos": [],
}


def test_el_aceite_del_interior_se_compara_contra_la_fecha_del_finde():
    """El caso que estaba mal: carilla 3, sin fecha impresa, del finde."""
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), _MAILING, {}, False, pagina=3))
    assert fila is None or fila["estado"] == "ok"


def test_un_producto_de_la_contratapa_si_se_compara_contra_rompe_precios():
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), _MAILING, {}, False, pagina=0))
    assert fila is not None and fila["estado"] != "ok"


def test_una_carilla_ambigua_no_acusa_avisa():
    mailing = {**_MAILING, "vigencia_por_pagina": {"0": None}}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), mailing, {}, False, pagina=0))
    assert fila is not None
    assert fila["estado"] == "info"
    assert "no se compar" in fila["nota"]


def test_si_el_mailing_tiene_una_sola_fecha_esa_vale_para_todos():
    mailing = {"fecha": FINDE, "fechas_por_pagina": {"0": FINDE}, "vigencia_por_pagina": {"0": FINDE}, "productos": []}
    # pagina=5 no existe en el mapa: cae a la única fecha del mailing
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), mailing, {}, False, pagina=5))
    assert fila is None or fila["estado"] == "ok"


def test_sin_pasada_de_promociones_sigue_valiendo_la_fecha_por_carilla():
    mailing = {"fecha": ROMPE, "fechas_por_pagina": {"0": ROMPE, "1": FINDE}, "productos": []}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), mailing, {}, False, pagina=1))
    assert fila is None or fila["estado"] == "ok"


def test_la_fecha_escrita_a_mano_le_gana_a_todo():
    config = {"fecha": FINDE}
    fila = _fila_fecha(comparar_elementos(_placa(FINDE), _MAILING, config, False, pagina=0))
    assert fila is None or fila["estado"] == "ok"
