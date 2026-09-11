"""Fija qué ajustes del preview llegan de verdad al PPTX.

El template_def de un job es una FOTO tomada al armar el preview. Lo que la
persona ajusta después viaja aparte, como overrides por id de componente, y se
mergea sobre esa foto al confirmar. Si un campo no está en el merge, el cambio
se ve en pantalla y no sale en el archivo -- sin ningún aviso.

Eso es lo que pasaba hasta el 09/09/2026 con todo lo que no fuera caja, estilo
o segmentos: cambiarle la variable a un cuadro en el preview era un cambio que
se aplicaba en el canvas y se descartaba en silencio al generar.
"""
from app.services.cenefas.jobs import aplicar_overrides

TEMPLATE = {
    "name": "test",
    "components": [
        {
            "id": "precio",
            "type": "text",
            "variable": "precioOferta",
            "transform": "none",
            "base_bounds": {"x": 1.0, "y": 2.0, "width": 5.0, "height": 2.0},
            "style": {"font_size": 60, "color": "#000000", "align": "center"},
            "_source_shape_id": 7,
        },
        {
            "id": "cocarda",
            "type": "text",
            "segments": [
                {"type": "variable", "value": "tipoOferta"},
                {"type": "static", "value": " $ "},
            ],
            "base_bounds": {"x": 1.0, "y": 8.0, "width": 4.0, "height": 1.6},
            "style": {"font_size": 30},
        },
    ],
}


def _comp(defin: dict, comp_id: str) -> dict:
    return next(c for c in defin["components"] if c["id"] == comp_id)


def test_sin_override_no_toca_nada():
    salida = aplicar_overrides(TEMPLATE, [])
    assert _comp(salida, "precio") == _comp(TEMPLATE, "precio")


def test_caja_y_estilo_se_mergean_sin_pisar_el_resto():
    salida = aplicar_overrides(TEMPLATE, [{
        "id": "precio",
        "base_bounds": {"x": 3.0, "y": 2.0, "width": 5.0, "height": 2.0},
        "style": {"font_size": 40},
    }])
    precio = _comp(salida, "precio")
    assert precio["base_bounds"]["x"] == 3.0
    assert precio["style"]["font_size"] == 40
    # El merge de style es superficial: lo que el override no manda sobrevive.
    assert precio["style"]["color"] == "#000000"
    assert precio["style"]["align"] == "center"
    # Un tamaño elegido a mano es un techo, no algo para re-escalar contra la
    # pareja entero/decimal.
    assert precio["_manual_font_override"] is True


def test_font_size_sin_tocar_no_marca_override_manual():
    salida = aplicar_overrides(TEMPLATE, [{"id": "precio", "style": {"color": "#ff0000"}}])
    assert "_manual_font_override" not in _comp(salida, "precio")


def test_cambiar_la_variable_llega_al_archivo():
    """El bug del 09/09/2026: se veía en el canvas y no salía en el PPTX."""
    salida = aplicar_overrides(TEMPLATE, [{"id": "precio", "variable": "precioRegular"}])
    assert _comp(salida, "precio")["variable"] == "precioRegular"


def test_texto_fijo_y_transformacion_llegan_al_archivo():
    salida = aplicar_overrides(TEMPLATE, [{
        "id": "precio", "variable": None, "static_value": "OFERTA", "transform": "uppercase",
    }])
    precio = _comp(salida, "precio")
    # Borrar la variable (volver el cuadro a texto fijo) tiene que poder
    # expresarse: el valor "apagado" viaja como null, no como campo ausente.
    assert precio["variable"] is None
    assert precio["static_value"] == "OFERTA"
    assert precio["transform"] == "uppercase"


def test_relacion_declarada_llega_al_archivo():
    """`vinculado_a` es lo que declara que un "$" acompaña a ESE precio, y de
    ahí salen el límite de ancho y la exención de choque del motor."""
    salida = aplicar_overrides(TEMPLATE, [{"id": "precio", "vinculado_a": "cocarda"}])
    assert _comp(salida, "precio")["vinculado_a"] == "cocarda"


def test_apagar_texto_compuesto_llega_al_archivo():
    """Volver un cuadro compuesto a modo simple manda segments en null.

    Un `if ov.get("segments")` lo leía como "no vino nada" y el cuadro salía
    compuesto en el archivo aunque en pantalla ya estuviera simple.
    """
    for apagado in (None, []):
        salida = aplicar_overrides(TEMPLATE, [{"id": "cocarda", "segments": apagado}])
        assert _comp(salida, "cocarda")["segments"] is None


def test_segmentos_nuevos_reemplazan_a_los_viejos():
    nuevos = [{"type": "variable", "value": "promoOferta"}]
    salida = aplicar_overrides(TEMPLATE, [{"id": "cocarda", "segments": nuevos}])
    assert _comp(salida, "cocarda")["segments"] == nuevos


def test_un_override_no_puede_inyectar_claves_internas():
    """Los overrides llegan del navegador. Si el merge fuera a ciegas, uno
    podría pisar `_source_shape_id` (con qué shape del PPTX se corresponde el
    cuadro) o `computed_bounds`, y el render saldría mal o directamente
    reventaría."""
    salida = aplicar_overrides(TEMPLATE, [{
        "id": "precio",
        "_source_shape_id": 999,
        "computed_bounds": {"x": 0, "y": 0, "width": 1, "height": 1},
        "group_id": "cnf-grupo-9",
        "locked": True,
    }])
    precio = _comp(salida, "precio")
    assert precio["_source_shape_id"] == 7
    assert "computed_bounds" not in precio
    assert "group_id" not in precio
    assert "locked" not in precio


def test_override_de_un_id_que_no_existe_se_ignora():
    salida = aplicar_overrides(TEMPLATE, [{"id": "fantasma", "variable": "x"}])
    assert len(salida["components"]) == 2
    assert _comp(salida, "precio")["variable"] == "precioOferta"


def test_override_sin_id_no_rompe():
    salida = aplicar_overrides(TEMPLATE, [{"variable": "x"}, {"id": "precio", "variable": "banco"}])
    assert _comp(salida, "precio")["variable"] == "banco"


def test_no_muta_el_template_original():
    """El template_def viene del staged_data del job: mutarlo acá dejaría el
    job con la foto cambiada si el render falla y se reintenta."""
    antes = _comp(TEMPLATE, "precio")["base_bounds"]["x"]
    aplicar_overrides(TEMPLATE, [{
        "id": "precio", "base_bounds": {"x": 99.0, "y": 2.0, "width": 5.0, "height": 2.0},
    }])
    assert _comp(TEMPLATE, "precio")["base_bounds"]["x"] == antes


# ---------------------------------------------------------------------------
# Eliminar un cuadro desde el preview (11/09/2026)
# ---------------------------------------------------------------------------

def test_eliminar_saca_el_cuadro_y_anota_su_forma():
    salida = aplicar_overrides(TEMPLATE, [{"id": "precio", "eliminado": True}])
    assert [c["id"] for c in salida["components"]] == ["cocarda"]
    # Sin anotar la forma, el render la seguiría imprimiendo desde el PPTX fuente.
    assert salida["formas_eliminadas"] == [7]


def test_eliminar_suelta_relaciones_y_reglas_de_ese_cuadro():
    plantilla = {
        **TEMPLATE,
        "components": [
            TEMPLATE["components"][0],
            {**TEMPLATE["components"][1], "vinculado_a": "precio"},
        ],
        "rules": [
            {"id": "r1", "target_component_id": "precio", "conditions": []},
            {"id": "r2", "target_component_id": "cocarda", "conditions": []},
        ],
    }
    salida = aplicar_overrides(plantilla, [{"id": "precio", "eliminado": True}])
    assert _comp(salida, "cocarda")["vinculado_a"] is None
    assert [r["id"] for r in salida["rules"]] == ["r2"]


def test_eliminar_un_cuadro_sin_forma_de_origen_no_rompe():
    salida = aplicar_overrides(TEMPLATE, [{"id": "cocarda", "eliminado": True}])
    assert [c["id"] for c in salida["components"]] == ["precio"]
    assert salida["formas_eliminadas"] == []


def test_eliminar_no_muta_el_template_original():
    aplicar_overrides(TEMPLATE, [{"id": "precio", "eliminado": True}])
    assert len(TEMPLATE["components"]) == 2
    assert "formas_eliminadas" not in TEMPLATE
