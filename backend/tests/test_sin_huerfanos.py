"""La regla de los huérfanos: solo en la descripción, ningún renglón con una,
dos o tres letras solas (Ivan, 08/10/2026).

"Nos pasa muchas veces que en las descripciones queda un renglón con una letra
únicamente, o dos letras, o tres letras... las dos letras de gramos quedan en el
renglón de abajo del todo, solitas. Queda feo." Se aplica después de todas las
reglas de tamaño y de ancho, bajando el cuerpo de a un paso hasta que el pedazo
se junte, con un tope. Los números viven en reglas_de_medicion.json.
"""
import pathlib
import re

from app.services.cenefas.component_renderer import (
    _ancho_medido_cm, _renglones_de_texto, _tiene_renglon_huerfano, apply_sin_huerfanos, preparar_componentes,
)
from app.services.cenefas.reglas_medicion import REGLAS

_ESPEJO = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "cenefas" / "huerfanos.ts"
_CANVAS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "components" / "cenefas" / "editor" / "Canvas.tsx"
_REGLAS_TS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "cenefas" / "reglasDeMedicion.ts"

TEXTO = "Queso colonia PEPITO ERNESTO. Semiduro. 100 g"


def _ancho_para_huerfano(pt, fam="Franklin Gothic Heavy"):
    """Un ancho de caja en el que, a ese cuerpo, la "g" final queda sola."""
    sin_g = TEXTO[: -len(" g")]
    return _ancho_medido_cm(sin_g, pt, fam, False) + 0.508 + 0.02  # entra todo menos la " g"


def _desc(pt=40.0, ancho=None, variable="descripcion", fam="Franklin Gothic Heavy"):
    return {"id": "d", "type": "text", "variable": variable,
            "base_bounds": {"x": 1, "y": 1, "width": ancho if ancho is not None else _ancho_para_huerfano(pt, fam), "height": 6},
            "style": {"font_size": pt, "font_family": fam, "align": "center"}}


def test_los_renglones_se_cortan_con_el_mismo_criterio_voraz():
    r = _renglones_de_texto(TEXTO, _ancho_para_huerfano(40.0), 40.0, False, "Franklin Gothic Heavy")
    assert len(r) >= 2 and r[-1] == "g", r
    assert " ".join(r) == TEXTO


def test_que_es_un_huerfano():
    assert _tiene_renglon_huerfano(["Queso colonia PEPITO. 100", "g"])
    assert _tiene_renglon_huerfano(["Queso colonia PEPITO.", "ml"])
    assert _tiene_renglon_huerfano(["Queso colonia", "x 4"])          # 2 caracteres sin el espacio
    assert not _tiene_renglon_huerfano(["Queso colonia PEPITO.", "100 g"])
    assert not _tiene_renglon_huerfano(["g"])                          # un solo renglón no es huérfano
    assert REGLAS.huerfano_max_caracteres == 3


def test_baja_el_cuerpo_hasta_que_la_g_se_junta():
    comp = _desc(40.0)
    salida = apply_sin_huerfanos([comp], {"descripcion": TEXTO})[0]
    pt = salida["style"]["font_size"]
    assert pt < 40.0 and 40.0 - pt <= REGLAS.huerfano_bajada_max_pt
    renglones = _renglones_de_texto(TEXTO, comp["base_bounds"]["width"], pt, False, "Franklin Gothic Heavy")
    assert not _tiene_renglon_huerfano(renglones), renglones
    assert renglones[-1].endswith("100 g")
    assert salida["_huerfano_bajada_pt"] == 40.0 - pt
    assert comp["style"]["font_size"] == 40.0, "tiene que devolver copias"


def test_sin_huerfano_no_toca_nada():
    comp = _desc(40.0, ancho=30.0)   # entra todo en un renglón
    salida = apply_sin_huerfanos([comp], {"descripcion": TEXTO})[0]
    assert salida["style"]["font_size"] == 40.0 and "_huerfano_bajada_pt" not in salida


def test_solo_la_descripcion():
    # El mismo texto en un cuadro de precio o de código no se toca, aunque quede huérfano.
    for variable in ("precioOferta", "codigo", "aclaracionUno"):
        comp = _desc(40.0, variable=variable)
        salida = apply_sin_huerfanos([comp], {variable: TEXTO})[0]
        assert salida["style"]["font_size"] == 40.0, variable
    # Un cuadro que mezcla la descripción con otra variable tampoco.
    comp = {"id": "m", "type": "text", "base_bounds": {"x": 1, "y": 1, "width": _ancho_para_huerfano(40.0), "height": 6},
            "style": {"font_size": 40.0, "font_family": "Franklin Gothic Heavy"},
            "segments": [{"type": "variable", "value": "descripcion"}, {"type": "static", "value": " "}, {"type": "variable", "value": "unidad"}]}
    assert apply_sin_huerfanos([comp], {"descripcion": TEXTO, "unidad": ""})[0]["style"]["font_size"] == 40.0


def test_el_tope_de_bajada_se_respeta():
    # Una caja tan angosta que la "g" nunca se junta: baja hasta el tope y para.
    comp = _desc(40.0, ancho=3.0)
    salida = apply_sin_huerfanos([comp], {"descripcion": "Queso g"})[0]
    assert salida["style"]["font_size"] == 40.0 - REGLAS.huerfano_bajada_max_pt


def test_es_la_ultima_regla_de_preparar_componentes():
    # Con una regla de tamaño que deja la descripción justo con la "g" suelta,
    # preparar_componentes baja un poco más que la regla.
    comp = _desc(50.0)
    regla = [{"id": "r", "target_component_id": "d", "condition": {"field": "descripcion", "operator": "is_not_empty"},
              "action": {"type": "set_font_size", "value": 40.0}}]
    comp["base_bounds"]["width"] = _ancho_para_huerfano(40.0)
    pt = preparar_componentes([comp], regla, {"descripcion": TEXTO})[0]["style"]["font_size"]
    assert pt < 40.0


def test_un_cuadro_oculto_por_regla_no_se_mide():
    comp = {**_desc(40.0), "_oculto_por_regla": True}
    assert apply_sin_huerfanos([comp], {"descripcion": TEXTO})[0]["style"]["font_size"] == 40.0


def test_el_preview_tiene_el_mismo_espejo():
    fuente = _ESPEJO.read_text(encoding="utf-8")
    for nombre in ("renglonesDeTexto", "tieneRenglonHuerfano", "esDescripcionPura", "ptSinHuerfanos"):
        assert f"function {nombre}" in fuente, f"huerfanos.ts no tiene {nombre}"
    assert "renglones.length < 2" in fuente, "el espejo tiene que exigir más de un renglón, como _tiene_renglon_huerfano"
    canvas = _CANVAS.read_text(encoding="utf-8")
    assert "ptSinHuerfanos(" in canvas and "esDescripcionPura(comp)" in canvas, "el Canvas no aplica la regla"
    reglas_ts = _REGLAS_TS.read_text(encoding="utf-8")
    for clave in ("huerfano_max_caracteres", "huerfano_paso_pt", "huerfano_bajada_max_pt"):
        assert clave in reglas_ts, f"reglasDeMedicion.ts no pide {clave} al backend"
    for numero in ("maxCaracteres: 3", "pasoPt: 1", "bajadaMaxPt: 6"):
        assert numero not in fuente and numero not in canvas, f"número escrito a mano en el preview: {numero}"
