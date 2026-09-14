"""Fija el motor de reglas de visibilidad.

Dos niveles: la regla apunta al CUADRO entero o a UN SEGMENTO de un cuadro de
texto compuesto. El segundo existe por un caso concreto (Ivan, 2026-09-08): la
palabra "unidad" al lado del precio, que solo corresponde cuando la cenefa es
de una categoría unificada. En un cuadro aparte quedaba desalineada del
precio, y una regla sobre el cuadro se llevaba puesto también al precio.
"""
from app.services.cenefas.component_renderer import _texto_resuelto
from app.services.cenefas.rules_engine import (
    apply_visibility,
    evaluate_rules,
    evaluate_segment_rules,
)

# El cuadro del precio con la palabra "unidad" adentro del MISMO texto.
CUADRO_PRECIO = {
    "id": "precio",
    "type": "text",
    "segments": [
        {"type": "static",   "value": "$"},
        {"type": "variable", "value": "precioOferta"},
        {"type": "static",   "value": " unidad"},   # índice 2
    ],
}

# Una fila unificada queda con el código combinado que arma commitUnificacion
# (skus.join(" - ")), y esa es justamente la señal de "esta cenefa es de varios
# SKU".
REGLA_UNIDAD = {
    "id": "r1",
    "target_component_id": "precio",
    "target_segment_index": 2,
    "condition": {"field": "codigo", "operator": "contains", "value": " - "},
    "action": {"type": "show"},
}

UN_SKU    = {"codigo": "580735", "precioOferta": "321"}
UNIFICADA = {"codigo": "580735 - 590183", "precioOferta": "321"}


def _render(comps, reglas, fila):
    visibles = apply_visibility(
        comps, evaluate_rules(reglas, fila), evaluate_segment_rules(reglas, fila))
    return {
        # Las dos condiciones que mira _render_slide: el ojito del panel y lo
        # que derivaron las reglas para esta fila. Ver apply_visibility.
        c["id"]: (_texto_resuelto(c, fila)
                  if c.get("visible", True) and not c.get("_oculto_por_regla", False)
                  else None)
        for c in visibles
    }


def test_regla_de_segmento_oculta_solo_ese_pedazo():
    assert _render([CUADRO_PRECIO], [REGLA_UNIDAD], UN_SKU)    == {"precio": "$321"}
    assert _render([CUADRO_PRECIO], [REGLA_UNIDAD], UNIFICADA) == {"precio": "$321 unidad"}


def test_la_misma_regla_sin_indice_se_lleva_el_cuadro_entero():
    # El comportamiento de antes, intacto: sin target_segment_index la regla
    # apunta al cuadro. Es lo que hacía inservible poner "unidad" adentro del
    # cuadro del precio.
    regla = {k: v for k, v in REGLA_UNIDAD.items() if k != "target_segment_index"}
    assert _render([CUADRO_PRECIO], [regla], UN_SKU)    == {"precio": None}
    assert _render([CUADRO_PRECIO], [regla], UNIFICADA) == {"precio": "$321 unidad"}


def test_una_regla_de_segmento_no_oculta_el_cuadro():
    # Regresión: si las reglas de segmento entraran a evaluate_rules, el cuadro
    # entero quedaría con "regla show que no matchea" y se apagaría.
    assert evaluate_rules([REGLA_UNIDAD], UN_SKU) == {}
    assert evaluate_segment_rules([REGLA_UNIDAD], UN_SKU) == {"precio": {2: False}}


def test_sin_reglas_no_cambia_nada():
    assert _render([CUADRO_PRECIO], [], UN_SKU) == {"precio": "$321 unidad"}


def test_ocultar_gana_sobre_mostrar_tambien_en_un_segmento():
    # Misma precedencia que a nivel de cuadro: si una hide matchea, se oculta.
    reglas = [
        REGLA_UNIDAD,
        {**REGLA_UNIDAD, "id": "r2", "action": {"type": "hide"},
         "condition": {"field": "codigo", "operator": "is_not_empty"}},
    ]
    assert _render([CUADRO_PRECIO], reglas, UNIFICADA) == {"precio": "$321"}


def test_regla_de_segmento_sobre_un_cuadro_sin_segmentos_no_rompe():
    simple = {"id": "precio", "type": "text", "variable": "precioOferta"}
    assert _render([simple], [REGLA_UNIDAD], UN_SKU) == {"precio": "321"}


def test_el_campo_de_la_condicion_tolera_las_mismas_grafias_que_el_resto():
    # El formulario pasa a MAYÚSCULAS lo que se escribe en "Columna del
    # Excel", así que escribir `codigo` llegaba como `CODIGO` y no matcheaba
    # nunca contra la fila, que trae la clave canónica en camelCase.
    for escrito in ("codigo", "CODIGO", "Codigo", "c"):  # "c" es el alias corto
        regla = {**REGLA_UNIDAD, "condition": {
            "field": escrito, "operator": "contains", "value": " - "}}
        assert _render([CUADRO_PRECIO], [regla], UNIFICADA) == {"precio": "$321 unidad"}, escrito
        assert _render([CUADRO_PRECIO], [regla], UN_SKU) == {"precio": "$321"}, escrito


def test_una_columna_suelta_del_excel_sigue_matcheando_por_su_nombre_crudo():
    # Una columna que NO es variable no resuelve a nada: tiene que seguir
    # encontrándose por el nombre tal cual vino.
    fila = {**UN_SKU, "DESCUENTO 20": "si"}
    regla = {**REGLA_UNIDAD, "condition": {
        "field": "DESCUENTO 20", "operator": "is_not_empty"}}
    assert _render([CUADRO_PRECIO], [regla], fila) == {"precio": "$321 unidad"}


# ---------------------------------------------------------------------------
# `visible` es de la persona, no del motor
# ---------------------------------------------------------------------------
#
# Caso real de Ivan (14/09/2026). Los dos cuadros "unidad" de Rompe Precios
# Congelados tenían la regla correcta ("mostrar si codigo contiene '-'"), el
# canvas del preview los dibujaba y el PPTX salía sin ellos.
#
# La causa: apply_visibility escribía el resultado derivado en `visible`, que es
# el MISMO campo del ojito de "Ocultar" del panel de componentes. Ese valor
# viajaba en el template_def del preview y "Guardar en la plantilla" lo horneaba
# como decisión de una persona. Desde ahí el cuadro quedaba muerto: _render_slide
# mira `visible` y apply_visibility solo sabía APAGAR, nunca encender.

def test_una_regla_que_matchea_revive_un_cuadro_ya_marcado_oculto():
    # Un cuadro que quedó con visible=False guardado de una corrida anterior:
    # la regla que SÍ matchea tiene que poder mostrarlo de nuevo.
    comp = {**CUADRO_PRECIO, "_oculto_por_regla": True}
    salida = apply_visibility([comp], evaluate_rules([], UNIFICADA), {})
    assert salida[0]["_oculto_por_regla"] is False, (
        "el valor derivado se quedó pegado del render anterior: ninguna regla "
        "puede volver a encender el cuadro")


def test_el_motor_nunca_escribe_el_campo_visible():
    # `visible` es dato de la persona (el ojito del panel). Si el motor lo toca,
    # vuelve a filtrarse al template_def del preview y "Guardar en la plantilla"
    # lo hornea.
    regla = {k: v for k, v in REGLA_UNIDAD.items() if k != "target_segment_index"}
    for fila in (UN_SKU, UNIFICADA):
        salida = apply_visibility(
            [dict(CUADRO_PRECIO)], evaluate_rules([regla], fila), {})
        assert "visible" not in salida[0], f"el motor escribió `visible` con {fila}"


def test_el_ojito_del_panel_sigue_mandando():
    # Lo apagado a mano no lo enciende ninguna regla: son decisiones distintas.
    # (Lo aplica _render_slide, que mira las dos; acá se fija que apply_visibility
    # no le pise el valor.)
    comp = {**CUADRO_PRECIO, "visible": False}
    salida = apply_visibility([comp], evaluate_rules([], UNIFICADA), {})
    assert salida[0]["visible"] is False
