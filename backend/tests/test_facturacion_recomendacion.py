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
    # Pares reales de proveedores DISTINTOS que comparten palabras genericas
    # ("URUGUAY", el sufijo "S A") quedan bajo el umbral.
    assert elegir_cuenta(
        "GEOCOM URUGUAY S.A.",
        [(normalizar_proveedor("INFONEGOCIOS URUGUAY S.A"), "MEDIOS")],
    ) is None
    # DENA y DEVON son dos empresas distintas: sin recortar el sufijo "S A"
    # daban 82.4 y DENA (multi-cuenta, excluida a proposito) heredaba la
    # cuenta de DEVON.
    assert elegir_cuenta(
        "DENA S.A",
        [(normalizar_proveedor("DEVON S.A"), "MEDIOS")],
    ) is None
    # Un token generico solo no puede matchear por subconjunto: "FILMS" esta
    # adentro de "KAFKA FILMS" pero no identifica al proveedor.
    assert elegir_cuenta(
        "FILMS S.R.L.",
        [(normalizar_proveedor("KAFKA FILMS S.R.L."), "MEDIOS")],
    ) is None
    # Dos personas que solo comparten el nombre de pila dan 80.0 clavado:
    # el umbral es estricto (>80) justamente para dejarlas afuera.
    assert elegir_cuenta(
        "PEREZ MAXIMILIANO",
        [(normalizar_proveedor("PASTOR MAXIMILIANO"), "LOYALTY")],
    ) is None
