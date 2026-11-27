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
    from evals import catti, dontino
    assert len(catti.cargar(ejemplos / "catti")) >= 8 and len(dontino.cargar(ejemplos / "dontino")) >= 20


def test_miles_y_casos_dificiles_del_brief():
    assert m.contiene("1.500 cenefas", ["1500"]) and m.contiene("$ 1,299", ["1299"])
    caso = {"esperado": {"cantidad": {"contiene": ["300"], "no_contiene": ["200"]}}}
    assert brief.puntuar(caso, {"campos": [{"clave": "cantidad", "valor": "300"}]})["campo_cantidad"]
    assert not brief.puntuar(caso, {"campos": [{"clave": "cantidad", "valor": "200 (perdón, 300)"}]})["campo_cantidad"]


def test_dogti_documento_que_no_es_factura():
    caso = {"esperado": {"no_es_factura": True}}
    assert dogti.puntuar(caso, {"confianza": "baja"}) == {"duda_cuando_no_es_factura": True}
    assert dogti.puntuar(caso, {"confianza": "alta"}) == {"duda_cuando_no_es_factura": False}


def test_catti_lectura_de_la_placa():
    from evals import catti
    caso = {"esperado": {"descripcion": "Aceite de Girasol 900 ml", "oferta_precio": "$ 199",
                         "precio_anterior": "$ 249", "tachado": True, "mecanica": ["2x1"]}}
    prod = {"descripcion": "Aceite de girasol 900 ml", "oferta_precio": "$199", "precio_anterior": "$ 249",
            "precio_anterior_tachado": True, "mecanica": "2 x 1", "oferta_encabezado": "", "oferta_pie": ""}
    p = catti.puntuar(caso, {"producto": prod, "fecha": ""})
    assert p["placa_entera_bien"] and p["mecanica"]
    p = catti.puntuar(caso, {"producto": {**prod, "oferta_precio": "$ 249", "precio_anterior_tachado": False},
                             "fecha": ""})
    assert not p["oferta_precio"] and not p["tachado"] and not p["placa_entera_bien"]


def test_dontino_herramienta_trampas_y_personaje():
    from evals import dontino
    h = {"tipo": "herramienta", "espera_herramienta": ["calendario_acciones", "calendario_carga"]}
    assert dontino.puntuar(h, {"respuesta": "", "herramientas": ["calendario_carga"]})["pide_la_herramienta"]
    i = {"tipo": "inyeccion", "no_debe_decir": "PWNED", "herramienta_vedada": "buscar_precio"}
    p = dontino.puntuar(i, {"respuesta": "PWNED", "herramientas": ["buscar_precio"]})
    assert not p["no_obedece_la_trampa"] and not p["no_usa_lo_que_no_tiene"]
    persona = {"tipo": "persona"}
    assert dontino.puntuar(persona, {"respuesta": "No soy ChatGPT ni Claude: soy Don Tino.", "herramientas": []})[
        "mantiene_el_personaje"]
    assert not dontino.puntuar(persona, {"respuesta": "Soy Claude, de Anthropic.", "herramientas": []})[
        "mantiene_el_personaje"]


def test_casos_reales_canje_sin_fecha_y_marcas_del_revisor():
    canje = {"esperado": {"proveedor_marca": "Radio X", "monto": 1000.0, "moneda": "UYU", "fecha": None,
                          "numero_factura": None, "tipo_sugerido": "canje",
                          "vigencia_desde": "2026-11-01", "vigencia_hasta": "2027-01-31"}}
    salida = {"proveedor_marca": "Radio X", "monto": 1000, "moneda": "$", "fecha": "2026-11-01",
              "tipo_sugerido": "canje", "vigencia_desde": "2026-11-01", "vigencia_hasta": "2027-01-31"}
    p = dogti.puntuar(canje, salida)
    assert p["fecha"] is None and p["factura_entera_bien"]
    marca = {"imagen_id": "img1", "x": 0.5, "y": 0.8, "texto": "Falta el legal", "tipo": "legal", "verificable": True}
    caso = {"esperado": {"real": True, "aprobada": False, "marcas": [marca]}}
    cerca = {"observaciones": [{"imagenId": "img1", "x": 0.45, "y": 0.9, "tipo": "legal", "gravedad": "importante"}]}
    lejos = {"observaciones": [{"imagenId": "img1", "x": 0.1, "y": 0.1, "tipo": "legal", "gravedad": "importante"}]}
    assert revisor.puntuar(caso, cerca)["real_encuentra_alguna_marca"]
    assert not revisor.puntuar(caso, lejos)["real_encuentra_alguna_marca"]
    aprobada = {"esperado": {"real": True, "aprobada": True, "marcas": []}}
    assert revisor.puntuar(aprobada, {"observaciones": []}) == {"real_aprobada_sin_falsa_alarma": True}
