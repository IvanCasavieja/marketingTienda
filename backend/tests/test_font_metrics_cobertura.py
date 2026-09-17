"""Que la tabla de anchos mida lo que dice medir.

El caso que lo motivó (17/09/2026, cenefas de la Fiesta de Alemania): "Arial
Black" no estaba en la tabla y `_metricas` la hacía caer POR PREFIJO en
"arial". Arial Black es ~17 % más ancha, así que el motor la medía de menos --
del lado peligroso: creía que entraba texto que no entra. Se usa 12 veces solo
en esos dos archivos.
"""
import pytest

from app.services.cenefas.font_metrics import _TABLA, _metricas, ancho_texto_cm

# Lo que las 22 plantillas guardadas usan de verdad (medido el 17/09/2026).
FAMILIAS_EN_USO = [
    "Impact", "Franklin Gothic Heavy", "Aptos", "Franklin Gothic Demi",
    "Calibri", "Arial Black", "Franklin Gothic Medium Cond",
    "Libre Franklin Medium", "Arial", "Libre Franklin", "Libre Franklin Black",
]


def test_arial_black_esta_medida_y_no_cae_en_arial():
    assert "arial black" in _TABLA, "Arial Black tiene que estar medida, no caer por prefijo"
    assert _metricas("Arial Black") is not _metricas("Arial")
    # Y tiene que dar MÁS ancha que Arial, que es todo el punto.
    negra = ancho_texto_cm("1.299,90", 40, "Arial Black")
    normal = ancho_texto_cm("1.299,90", 40, "Arial")
    assert negra > normal * 1.10, f"Arial Black {negra:.2f} vs Arial {normal:.2f}: no la distingue"


@pytest.mark.parametrize("familia", ["Impact", "Arial", "Arial Black", "Calibri",
                                     "Franklin Gothic Medium"])
def test_las_medidas_de_verdad_estan_en_la_tabla(familia):
    # Sin esto, agregar una fuente al generador y olvidarse de regenerar el
    # JSON pasa desapercibido: el motor sigue usando el ancho de reserva.
    assert familia.strip().lower() in _TABLA, f"{familia} no está medida"


def test_un_prefijo_que_lleva_a_una_familia_MAS_ANGOSTA_es_el_caso_peligroso():
    # Documenta el riesgo que sigue vivo para cualquier familia futura: el
    # match por prefijo es seguro cuando lleva a una MÁS ANCHA (sobreestima) y
    # peligroso cuando lleva a una más angosta. "Franklin Gothic Medium Cond"
    # -> "Franklin Gothic Medium" es del lado seguro: la condensada es más
    # angosta que su base, así que se sobreestima.
    cond = ancho_texto_cm("1.299,90", 40, "Franklin Gothic Medium Cond")
    base = ancho_texto_cm("1.299,90", 40, "Franklin Gothic Medium")
    assert cond == pytest.approx(base), "hoy la condensada se mide como su base"


def test_una_familia_desconocida_no_revienta():
    assert ancho_texto_cm("1.299,90", 40, "Una Fuente Que No Existe") > 0
    assert ancho_texto_cm("1.299,90", 40, None) > 0


def test_cuantas_de_las_familias_en_uso_estan_medidas():
    # No es un umbral arbitrario: es el inventario. Si baja, alguien sacó una
    # fuente de la tabla; si sube, alguien la agregó y este número se actualiza.
    medidas = [f for f in FAMILIAS_EN_USO if f.strip().lower() in _TABLA]
    assert sorted(medidas) == ["Arial", "Arial Black", "Calibri", "Impact"], (
        f"cambió la cobertura de la tabla: medidas={sorted(medidas)}. "
        "Si agregaste fuentes (las Franklin de Office, Aptos), actualizá esta lista."
    )
