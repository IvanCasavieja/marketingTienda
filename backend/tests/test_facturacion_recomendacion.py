"""La cuenta recomendada por proveedor recurrente: normalizacion y match.

Fija la regla con los casos reales del historial 2026: los nombres de
proveedor vienen de sistemas distintos ("CREATIVAS S A" / "CREATIVAS S.A")
y el match tiene que unificarlos SIN inventar matches entre proveedores
que no tienen nada que ver.
"""
from app.services.facturacion.recomendacion import elegir_cuenta, normalizar_proveedor

MAPEO = [
    (normalizar_proveedor("CREATIVAS S A"), "MEDIOS"),
    (normalizar_proveedor("CEPPELINI GATTO FIORELLA"), "MARCA"),
    (normalizar_proveedor("GARCIA DEL CAMPO MARIO EDEBER"), "IMPRESOS"),
    (normalizar_proveedor("SALESFORCE.COM INC. (ROWH)"), "LOYALTY"),
    (normalizar_proveedor("MONITOR DE REPUTACIÓN CORPORATIVA(MERCO)"), "MEDIOS"),
]


def test_normalizar_unifica_puntuacion_tildes_y_espacios():
    assert normalizar_proveedor("Creativas  S.A.") == "CREATIVAS S A"
    assert normalizar_proveedor("MONITOR DE REPUTACIÓN CORPORATIVA(MERCO)") \
        == "MONITOR DE REPUTACION CORPORATIVA MERCO"
    assert normalizar_proveedor("  agadu ") == "AGADU"
    assert normalizar_proveedor("") == ""


def test_match_exacto_tras_normalizar():
    assert elegir_cuenta("Creativas S.A", MAPEO) == "MEDIOS"
    assert elegir_cuenta("salesforce.com inc. (rowh)", MAPEO) == "LOYALTY"


def test_match_por_similitud_para_variantes_reales():
    # Variante con una palabra de menos y una letra cambiada (82.9): entra.
    assert elegir_cuenta("CEPELINI FIORELLA", MAPEO) == "MARCA"
    # Subconjunto del nombre completo: token_set_ratio lo da 100.
    assert elegir_cuenta(
        "HENDERSON",
        [(normalizar_proveedor("HENDERSON Y CIA S.A"), "MARCA")],
    ) == "MARCA"


def test_sin_match_no_inventa():
    assert elegir_cuenta("PROVEEDOR NUEVO QUE NADIE VIO", MAPEO) is None
    assert elegir_cuenta("", MAPEO) is None
    assert elegir_cuenta("KAFKA FILMS S.R.L.", []) is None
    # El peor par real de proveedores DISTINTOS (76.2) queda bajo el umbral:
    # comparten "URUGUAY S A" pero no tienen nada que ver.
    assert elegir_cuenta(
        "GEOCOM URUGUAY S.A.",
        [(normalizar_proveedor("INFONEGOCIOS URUGUAY S.A"), "MEDIOS")],
    ) is None
