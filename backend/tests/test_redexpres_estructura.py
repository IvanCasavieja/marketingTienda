"""La planilla de pedidos editable (Ivan, 08/10/2026)."""
import pytest

from app.services import redexpres_estructura as est


def test_la_estructura_por_defecto_es_valida_y_cubre_los_campos_historicos():
    e = est.validar(est.por_defecto())
    assert set(est.columnas(e)) == set(est.BUILTIN)
    assert est.columnas(e)["hojas_amarillas"].get("texto") is True
    assert est.columnas(e)["afiche_54x74"]["max"] == 20


def test_agregar_una_columna_nueva_le_pone_clave_propia_sin_chocar():
    e = est.por_defecto()
    e["grupos"][0]["cols"] += [{"label": "Pinchos Nuevos", "max": "50"}, {"label": "Pinchos Nuevos", "max": 5}]
    sal = est.validar(e)
    claves = [c["key"] for c in sal["grupos"][0]["cols"]]
    assert claves[-2:] == ["x_pinchos_nuevos", "x_pinchos_nuevos_2"]
    assert est.columnas(sal)["x_pinchos_nuevos"]["max"] == 50


def test_rechaza_nombres_vacios_claves_repetidas_y_topes_raros():
    e = est.por_defecto(); e["grupos"][0]["label"] = " "
    with pytest.raises(est.EstructuraInvalida): est.validar(e)
    e = est.por_defecto(); e["grupos"][0]["cols"][1]["key"] = "a4_oferta_vertical"
    with pytest.raises(est.EstructuraInvalida): est.validar(e)
    e = est.por_defecto(); e["grupos"][0]["cols"][0]["max"] = -3
    with pytest.raises(est.EstructuraInvalida): est.validar(e)
    e = est.por_defecto(); e["grupos"][0]["cols"][0]["max"] = "mucho"
    with pytest.raises(est.EstructuraInvalida): est.validar(e)
    with pytest.raises(est.EstructuraInvalida): est.validar({"grupos": "x"})


def test_un_campo_historico_conserva_su_tipo_aunque_el_editor_diga_otra_cosa():
    e = est.por_defecto()
    for c in e["grupos"][-1]["cols"]:
        if c["key"] == "hojas_amarillas": c.pop("texto")
        if c["key"] == "pinchos_dias_expres": c["texto"] = True
    cols = est.columnas(est.validar(e))
    assert cols["hojas_amarillas"].get("texto") is True
    assert not cols["pinchos_dias_expres"].get("texto")


def test_un_color_desconocido_cae_a_gris():
    e = est.por_defecto(); e["grupos"][0]["color"] = "fucsia"
    assert est.validar(e)["grupos"][0]["color"] == "slate"
