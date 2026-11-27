"""Las evals (backend/evals): cómo se compara lo que contestó la IA con lo
esperado. Sin la API: acá se fija solo la cuenta, que es pura."""
from pathlib import Path

from evals import brief, dogti, metricas as m, revisor


def test_montos_monedas_y_fechas():
    assert m.mismo_monto(1250.5, "1250.50") and not m.mismo_monto(1250.5, 1250.6)
    assert not m.mismo_monto(None, 10)
    assert m.moneda("$") == m.moneda("UYU") == "UYU"
    assert m.moneda("U$S") == m.moneda("usd") == "USD"
    assert m.fecha_iso("03/11/2026") == m.fecha_iso("2026-11-03") == "2026-11-03"
    assert m.fecha_iso("mañana") is None


def test_textos():
    assert m.parecido("Lácteos del Sur S.A.", "LACTEOS DEL SUR")
    assert not m.parecido("Lácteos del Sur", "Bodega Cerro Alto")
    assert m.solo_letras_y_numeros("A-001 234") == "a001234"
    assert m.contiene("2x1 en Vinos", ["2x1", "vinos"]) and not m.contiene("2x1 en vinos", ["3x2"])
    assert m.vacio(None) and m.vacio(" - ") and not m.vacio("0")


def test_resumir_saltea_lo_que_no_aplica():
    r = m.resumir([{"a": True, "b": None}, {"a": False, "b": True}, {}])
    assert r["a"] == {"aciertos": 1, "casos": 2, "porcentaje": 50.0}
    assert r["b"] == {"aciertos": 1, "casos": 1, "porcentaje": 100.0}


ESPERADO = {"proveedor_marca": "Lácteos del Sur S.A.", "numero_factura": "A 001234", "fecha": "2026-11-03",
            "monto": 103700.0, "moneda": "UYU", "tipo_sugerido": "movimiento",
            "vigencia_desde": None, "vigencia_hasta": None}


def test_dogti_factura_bien_leida():
    salida = {"proveedor_marca": "Lacteos del Sur", "numero_factura": "A-001234", "fecha": "2026-11-03",
              "monto": 103700, "moneda": "$", "tipo_sugerido": "movimiento", "confianza": "alta"}
    p = dogti.puntuar({"esperado": ESPERADO}, salida)
    assert p["factura_entera_bien"] and p["no_inventa"] and p["confianza_alta_acierta"]


def test_dogti_monto_mal_e_invento():
    salida = {"proveedor_marca": "Lácteos del Sur S.A.", "numero_factura": "A 001234", "fecha": "2026-11-03",
              "monto": 85000, "moneda": "UYU", "tipo_sugerido": "movimiento", "confianza": "alta",
              "vigencia_desde": "2026-11-01"}
    p = dogti.puntuar({"esperado": ESPERADO}, salida)
    assert p["monto"] is False and p["factura_entera_bien"] is False
    assert p["no_inventa"] is False and p["confianza_alta_acierta"] is False


def test_brief_campos_dichos_e_inventos():
    caso = {"esperado": {"precio_mecanica": ["2x1", "vinos"], "locales": ["40"], "medidas": None}}
    bien = {"campos": [{"clave": "precio_mecanica", "valor": "2x1 en vinos"},
                       {"clave": "locales", "valor": "40 locales"}, {"clave": "medidas", "valor": None}]}
    assert brief.puntuar(caso, bien) == {"campo_precio_mecanica": True, "campo_locales": True,
                                          "todos_los_campos_dichos": True, "no_inventa": True}
    inventa = {"campos": [{"clave": "precio_mecanica", "valor": "2x1 en vinos"},
                          {"clave": "locales", "valor": None}, {"clave": "medidas", "valor": "30 x 10 cm"}]}
    p = brief.puntuar(caso, inventa)
    assert p["campo_locales"] is False and p["todos_los_campos_dichos"] is False and p["no_inventa"] is False


def test_revisor_error_plantado_y_falsa_alarma():
    plantado = {"esperado": {"sana": False, "tipo": "ortografia"}}
    assert revisor.puntuar(plantado, {"observaciones": [{"tipo": "ortografia", "gravedad": "importante"}]}) == {
        "encuentra_el_error": True, "encuentra_ortografia": True, "lo_marca_importante": True}
    assert revisor.puntuar(plantado, {"observaciones": [{"tipo": "legal", "gravedad": "importante"}]})[
        "encuentra_el_error"] is False
    sana = {"esperado": {"sana": True}}
    assert revisor.puntuar(sana, {"observaciones": []})["sana_sin_falsa_alarma"]
    assert revisor.puntuar(sana, {"observaciones": [{"tipo": "otro", "gravedad": "a_revisar"}]}) == {
        "sana_sin_falsa_alarma": True, "sana_sin_ninguna_observacion": False}
    assert not revisor.puntuar(sana, {"observaciones": [{"tipo": "legal", "gravedad": "importante"}]})[
        "sana_sin_falsa_alarma"]


def test_los_ejemplos_del_repo_se_cargan():
    ejemplos = Path(__file__).parent.parent / "evals" / "ejemplos"
    assert len(brief.cargar(ejemplos / "brief")) >= 10
    assert len(dogti.cargar(ejemplos / "dogti")) >= 6
    assert len(revisor.cargar(ejemplos / "revisor")) >= 6
