"""Las piezas del pedido y las que faltan en una entrega (0087, 21/11/2026).

Ivan: "la IA a veces encuentra un problema y a veces no. Si yo pido 4
banners y me pasan uno (...) cuando son todos los banners ahí es donde tiene
que analizar y decir 'che, pará, acá faltan también los banners X o Y'. Y
quizás estaría bueno que le des el espacio a la agencia ahí de escribir por
qué no los manda."

Que falte una pieza lo dice la plataforma sola, por las medidas: acá, lo
que se pidió, una pieza por medida (tipos_de_tarea.piezas_del_pedido), y lo
que viaja con la entrega (reglas.faltan_validas y por_que_faltan_valido). La
comparación con las imágenes es de la pantalla: frontend/lib/calendario/
piezas.test.ts. Puras: no tocan la base.
"""
import json

import pytest

from app.services import entregas as reglas
from app.services import tipos_de_tarea as tipos


def _texto(p: dict) -> str:
    """Como las lee la pantalla: «Header (web) 1920×416», «Redes 4:5»."""
    return p["nombre"] if p["proporcion"] else f"{p['nombre']} {p['ancho']}×{p['alto']}"


def test_un_banner_con_web_y_mobile_son_dos_piezas_y_uno_sin_mobile_una():
    piezas = tipos.piezas_del_pedido("banners", ["Header", "Checkout"])
    assert [_texto(p) for p in piezas] == ["Header (web) 1920×416", "Header (mobile) 640×260", "Checkout 412×157"]
    assert piezas[0] == {"nombre": "Header (web)", "ancho": 1920, "alto": 416, "proporcion": False}


def test_van_en_el_orden_de_lo_tildado_y_cada_foto_es_una_pieza_aparte():
    piezas = tipos.piezas_del_pedido("banners", ["Foto receta", "Foto producto", "Dobles"])
    assert [_texto(p) for p in piezas] == [
        "Foto receta 1200×900", "Foto producto 1200×900", "Dobles (web) 590×240", "Dobles (mobile) 315×405",
    ]


def test_las_escritas_a_mano_no_entran_porque_no_tienen_medida():
    # Banners deja agregar opciones a mano ("Banner de prueba"): sin medida, no se pueden controlar.
    assert [p["nombre"] for p in tipos.piezas_del_pedido("banners", ["Banner de prueba", "Carrito"])] == ["Carrito"]


def test_una_opcion_guardada_con_otras_mayusculas_igual_cuenta():
    assert [p["nombre"] for p in tipos.piezas_del_pedido("banners", ["  checkout "])] == ["Checkout"]


def test_redes_se_pide_por_proporcion():
    piezas = tipos.piezas_del_pedido("redes", ["4:5", "9:16"])
    assert [_texto(p) for p in piezas] == ["Redes 4:5", "Redes 9:16"]
    assert piezas[0] == {"nombre": "Redes 4:5", "ancho": 4, "alto": 5, "proporcion": True}


def test_whatsapp_es_una_pieza_de_1080_por_1350():
    assert [_texto(p) for p in tipos.piezas_del_pedido("whatsapp", [])] == ["Envío WhatsApp 1080×1350"]


@pytest.mark.parametrize("clave,opciones", [
    ("emm", ["Una sola imagen", "En bloques"]),  # 600 de ancho y el alto libre
    ("mailing", ["Digital", "Físico (impreso)"]),
    ("cenefas", ["A4", "A6"]),  # en milímetros, y se entregan en PDF
    ("pantallas", ["Horizontal"]),
    ("material", ["Stopper", "Un vinilo"]),
    ("push", []), ("totem", []), ("otro", []),
    ("no-existe", ["Header"]), (None, None),
])
def test_lo_que_no_tiene_medida_en_px_ni_proporcion_no_entra(clave, opciones):
    assert tipos.piezas_del_pedido(clave, opciones) == []


def test_sin_tildar_nada_no_hay_piezas():
    assert tipos.piezas_del_pedido("banners", []) == []
    assert tipos.piezas_del_pedido("banners", None) == []


def test_todo_el_catalogo_de_banners_tiene_su_medida_en_numeros():
    # Si alguien agrega un banner al catálogo, entra solo: una pieza por medida.
    banners = tipos.tipo_de("banners")
    todas = tipos.piezas_del_pedido("banners", [o["nombre"] for o in banners["opciones"]])
    con_mobile = [o for o in banners["opciones"] if o["mobile"]]
    assert len(todas) == len(banners["opciones"]) + len(con_mobile)
    assert len(todas) <= reglas.MAX_FALTAN
    assert all(p["ancho"] > 0 and p["alto"] > 0 for p in todas)


def test_la_pantalla_recibe_el_catalogo_como_siempre():
    # Los números de las medidas son para piezas_del_pedido: el catálogo que
    # pide la pantalla sigue con el nombre y la medida para leer.
    por_clave = {t["clave"]: t for t in tipos.para_la_pantalla()}
    assert por_clave["banners"]["opciones"][0] == {"nombre": "Header", "medida": "web 1920×416 · mobile 640×260"}
    assert por_clave["redes"]["opciones"][1] == {"nombre": "4:5", "medida": None}
    assert "px" not in por_clave["whatsapp"]
    json.dumps(tipos.para_la_pantalla())


# ---------------------------------------------------------------------------
# Lo que viaja con la entrega
# ---------------------------------------------------------------------------

def test_lo_que_falta_se_guarda_limpio_y_sin_repetidos():
    assert reglas.faltan_validas(json.dumps(["Header (mobile)", "  Checkout ", "Header (mobile)", ""])) == [
        "Header (mobile)", "Checkout",
    ]


def test_no_falta_nada_no_es_lo_mismo_que_no_se_pudo_medir():
    """H-035 (25/11/2026): al revisar decía «Ya están todas las piezas del
    pedido» con el carrito sin venir. La lista vacía es que la pantalla midió
    y no falta ninguna; si no vino (un ZIP que no se lee, un PDF), no se sabe."""
    assert reglas.faltan_validas("[]") == []
    assert reglas.faltan_validas(json.dumps(["", "  "])) == []
    assert reglas.faltan_validas("") is None
    assert reglas.faltan_validas(None) is None


@pytest.mark.parametrize("malo", ["{", '{"a": 1}', '"Header"', "[1, 2]", '["Header", null]'])
def test_lo_que_falta_con_otra_forma_no_va(malo):
    with pytest.raises(ValueError, match="forma esperada"):
        reglas.faltan_validas(malo)


def test_lo_que_falta_tiene_topes():
    assert len(reglas.faltan_validas(json.dumps([f"Pieza {i}" for i in range(40)]))) == 40
    with pytest.raises(ValueError, match="hasta 40"):
        reglas.faltan_validas(json.dumps([f"Pieza {i}" for i in range(41)]))
    assert reglas.faltan_validas(json.dumps(["x" * 120])) == ["x" * 120]
    with pytest.raises(ValueError, match="demasiado largo"):
        reglas.faltan_validas(json.dumps(["x" * 121]))


def test_por_que_falta_es_opcional_va_en_una_linea_y_hasta_500():
    faltan = ["Checkout"]
    assert reglas.por_que_faltan_valido("  Es el KV,\npara aprobarlo   antes ", faltan) == "Es el KV, para aprobarlo antes"
    assert reglas.por_que_faltan_valido("", faltan) is None
    assert reglas.por_que_faltan_valido(None, faltan) is None
    assert reglas.por_que_faltan_valido("a" * 500, faltan) == "a" * 500
    with pytest.raises(ValueError, match="hasta 500"):
        reglas.por_que_faltan_valido("a" * 501, faltan)


def test_sin_piezas_que_falten_no_hay_por_que():
    assert reglas.por_que_faltan_valido("Es el KV", None) is None
    assert reglas.por_que_faltan_valido("Es el KV", []) is None
