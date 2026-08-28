"""Fija cómo el Convertidor resuelve las mecánicas de oferta.

Regla madre (decisión de Ivan, 2026-08-25/26, ver variables.py):
- tipoOferta (la cocarda) se llena SOLO con mecánicas de verdad: combo,
  M x N, 2da unidad. "Precio fijo"/"PVP"/"% descuento" no anuncian nada.
  (El passthrough directo de OFERTA se probó el 28/08 y se revirtió al día
  siguiente: imprimía "PVP" gigante en la cocarda.)
- precioOferta es SIEMPRE un precio; el literal que tapa al precio va en
  promoOferta.
- unidadMoneda ("$"/"U$S") se escribe SIEMPRE, desde la columna MONEDA.
"""
from app.services.cenefas.convertidor_variables import construir_variables, resolver_mecanica


def _fila(ofertaDet="", oferta="", precio=None, moneda="$", **extra):
    base = {"codigo": "1", "ofertaDet": ofertaDet, "oferta": oferta,
            "precio": precio, "moneda": moneda}
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Precio fijo — el caso del 90% de los listados
# ---------------------------------------------------------------------------

def test_precio_fijo_no_llena_la_cocarda():
    out, w = construir_variables(_fila("Precio fijo", "PVP", 1290), "Aspiradora", {})
    assert out["tipoOferta"] == ""          # ni "PVP" ni el precio repetido
    assert out["promoOferta"] == ""
    assert out["mecanica"] == "Precio Final"
    assert out["precioOferta"] == "1.290"
    assert w == []


def test_unidad_moneda_siempre_presente():
    out, _ = construir_variables(_fila("Precio fijo", "PVP", 1290, moneda="$"), "X", {})
    assert out["unidadMoneda"] == "$"
    out, _ = construir_variables(_fila("Precio fijo", "60", 60, moneda="U$S"), "X", {})
    assert out["unidadMoneda"] == "U$S"
    out, _ = construir_variables(_fila("Precio fijo", "", 100, moneda="USD"), "X", {})
    assert out["unidadMoneda"] == "U$S"
    # sin columna MONEDA: pesos por defecto
    out, _ = construir_variables({"codigo": "1", "precio": 100}, "X", {})
    assert out["unidadMoneda"] == "$"


# ---------------------------------------------------------------------------
# Combo ("3x99"): total ÷ cantidad = unitario
# ---------------------------------------------------------------------------

def test_combo_total_en_precio_y_cantidad_en_oferta_uno():
    # Correccion de Ivan (2026-08-29): en un combo el cartel dice "2x $299" --
    # la cantidad va en ofertaUno y el TOTAL grande en precioOferta. El
    # unitario (299/2) queda solo en la letra chica de `mecanica`.
    m, w = resolver_mecanica("Combo", "2x$299", precio=175.0)
    assert m["precioOferta"] == 299.0       # el TOTAL, ni el unitario ni la columna PRECIO
    assert m["tipoOferta"] == "2x"          # SOLO la cantidad: el cartel se lee "2x $299"
    assert m["ofertaUno"] == "2x"           # como siempre (anterior a esta semana)
    # promoOferta VACIA (decision de Ivan, 2026-08-29): el literal que tapa
    # al precio se usa SOLO en M x N. En un combo hay un precio que mostrar
    # (el unitario), asi que se muestra, con la cocarda arriba.
    assert m["promoOferta"] == ""
    assert m["mecanica"] == "Comprando 2, $149,50 la unidad."
    assert m["tipoOfertaComprando"] == "Comprando 2"
    assert m["unidad"] == "unidad"
    assert w == []


def test_combo_extrae_el_literal_de_una_frase():
    # Bug real: "Coca Cola Zero 2.25 L 2x$299" anclado con ^...$ no matcheaba
    # y la fila perdía TODO.
    m, _ = resolver_mecanica("Combo", "Coca Cola Zero 2.25 L 2x$299", precio=175.0)
    assert m["tipoOferta"] == "2x"          # la cantidad, extraida de la frase entera
    assert m["precioOferta"] == 299.0


def test_combo_sin_simbolo_tambien():
    m, _ = resolver_mecanica("Combo", "3x99", precio=None)
    assert m["precioOferta"] == 99.0        # el total; el unitario ($33) va en mecanica
    assert m["ofertaUno"] == "3x"
    assert m["mecanica"] == "Comprando 3, $33 la unidad."


# ---------------------------------------------------------------------------
# M x N ("2x1"): el unitario viene de la columna PRECIO
# ---------------------------------------------------------------------------

def test_mxn_precio_de_la_columna_y_literal_en_promo():
    m, w = resolver_mecanica("MxN", "2x1", precio=49.5)
    assert m["precioOferta"] == 49.5        # precioOferta ES un precio, SIEMPRE
    assert m["promoOferta"] == "2x1"        # SOLO M x N llena promoOferta
    assert m["tipoOferta"] == "2x1"
    assert m["mecanica"] == "$49,50 la unidad."
    assert w == []


# ---------------------------------------------------------------------------
# 2da unidad al X%
# ---------------------------------------------------------------------------

def test_segunda_unidad():
    m, _ = resolver_mecanica("Unidad al", "Sprite 2.25L 2da unidad al 50%", precio=90.0)
    assert m["tipoOferta"] == "2da al 50%"
    assert m["precioOferta"] == 90.0
    assert m["promoOferta"] == ""


def test_ordinal_sin_sufijo_no_inventa_4da():
    # Bug real: "5 unidad al 30%" salía "5da", que no existe en castellano.
    m, _ = resolver_mecanica("Unidad al", "5 unidad al 30%", precio=90.0)
    assert m["tipoOferta"] == "5ta al 30%"


# ---------------------------------------------------------------------------
# Prioridades
# ---------------------------------------------------------------------------

def test_lo_mapeado_pisa_lo_calculado():
    out, _ = construir_variables(
        _fila("Precio fijo", "PVP", 100), "X", {"tipoOferta": "25% OFF"})
    assert out["tipoOferta"] == "25% OFF"


def test_ofertadet_desconocido_avisa():
    # Una mecánica nueva de gestión no puede descartarse en silencio.
    _, w = resolver_mecanica("Invento Nuevo 2027", "3x2", precio=100.0)
    assert "ofertadet_desconocido" in w
