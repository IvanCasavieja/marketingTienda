"""Dictar el brief por voz: la IA ordena el pedido en los campos del tipo de
pieza y avisa qué falta.

Pedido (15/11/2026): "necesito cenefas para el Ciberlunes, 2x1 en vinos, del
28 al 30, 40 locales..." tiene que volver como Medidas / Cantidad / Precio o
mecánica / Vigencia / Legales / Locales, con "Faltan las medidas" y lo que
corresponda.

Sin la API real: lo que contesta el modelo está grabado con la forma real de
la API (ver ia_simulada.py) y pasa por el SDK de verdad, salida estructurada
incluida. Se fija:
- qué campos lleva cada tipo y cómo se dice lo que falta (lo calcula el
  servidor, no el modelo);
- que la respuesta del modelo se valida contra el esquema y se limpia;
- qué se le pide a la API (modelo, salida estructurada, esfuerzo, el dictado
  entre etiquetas);
- el endpoint: tope de tamaño, permisos y registro del uso.
"""
import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest

import ia_simulada as sim
from app.services import brief_ia

HOY = date(2026, 11, 15)
DICTADO = "Necesito cenefas para el Ciberlunes, dos por uno en vinos, del 28 al 30, cuarenta locales."


def _respuesta_cenefa(**cambios):
    datos = {
        "resumen": "Cenefas Ciberlunes: 2x1 en vinos",
        "campos": {
            "medidas": None, "cantidad": None, "precio_mecanica": "2x1 en vinos",
            "vigencia": "del 28 al 30", "legales": None, "locales": "40 locales",
        },
        "notas": "Para el Ciberlunes.",
        "dudas": ["¿Del 28 al 30 de noviembre?"],
    }
    datos.update(cambios)
    return sim.mensaje([sim.pensamiento(), sim.texto(json.dumps(datos, ensure_ascii=False))], entrada=850, salida=140)


# ---------------------------------------------------------------------------
# Campos y lo que falta
# ---------------------------------------------------------------------------

def test_los_campos_de_cada_tipo():
    claves = {t: [c.clave for c in d.campos] for t, d in brief_ia.TIPOS.items()}
    assert claves == {
        "cenefa": ["medidas", "cantidad", "precio_mecanica", "vigencia", "legales", "locales"],
        "mailing": ["asunto", "segmento", "fecha_envio", "llamado_accion"],
        "banner_web": ["medidas", "link", "fechas"],
        "redes": ["formato", "copy", "fecha"],
        "otro": ["texto"],
    }


def test_lo_que_falta_lo_calcula_el_servidor_con_los_vacios():
    r = brief_ia.armar_resultado("cenefa", {
        "resumen": "Cenefas Ciberlunes",
        "campos": {"medidas": None, "cantidad": "  ", "precio_mecanica": "2x1 en vinos",
                   "vigencia": "null", "legales": "No lleva", "locales": "40 locales"},
        "notas": None, "dudas": [],
    })
    assert r["falta"] == ["Faltan las medidas", "Falta la cantidad", "Falta la vigencia"]
    assert [c["clave"] for c in r["campos"]] == ["medidas", "cantidad", "precio_mecanica", "vigencia", "legales", "locales"]
    assert r["campos"][2] == {"clave": "precio_mecanica", "etiqueta": "Precio / mecánica", "valor": "2x1 en vinos",
                              "falta": "Falta el precio o la mecánica"}
    assert r["campos"][1]["valor"] is None and r["campos"][3]["valor"] is None


def test_un_campo_que_el_modelo_no_mando_cuenta_como_faltante():
    r = brief_ia.armar_resultado("mailing", {"resumen": "Mail", "campos": {"asunto": "Ciberlunes"}})
    assert r["falta"] == ["Falta el segmento", "Falta la fecha de envío", "Falta el llamado a la acción"]
    assert r["dudas"] == [] and r["notas"] is None


def test_textos_largos_y_dudas_repetidas_se_limpian():
    r = brief_ia.armar_resultado("otro", {
        "resumen": "x" * 500, "campos": {"texto": "pedido " * 400},
        "notas": "  varias   palabras  ", "dudas": ["¿Mes?", "¿Mes?", "", None] + [f"Duda {i}" for i in range(10)],
    })
    assert len(r["resumen"]) == 120 and r["resumen"].endswith("…")
    assert len(r["campos"][0]["valor"]) == brief_ia.MAX_CAMPO
    assert r["notas"] == "varias palabras"
    assert r["dudas"][:2] == ["¿Mes?", "Duda 0"] and len(r["dudas"]) == brief_ia.MAX_DUDAS
    assert r["falta"] == []


def test_sin_resumen_usa_el_nombre_del_tipo():
    assert brief_ia.armar_resultado("banner_web", {"resumen": "", "campos": {}})["resumen"] == "Banner web"


def test_el_esquema_obliga_a_todas_las_claves_y_no_acepta_otras():
    from anthropic.lib._parse._transform import transform_schema
    from pydantic import TypeAdapter

    for tipo, definicion in brief_ia.TIPOS.items():
        esquema = transform_schema(TypeAdapter(brief_ia.MODELOS[tipo]).json_schema())
        assert esquema["additionalProperties"] is False
        assert set(esquema["required"]) == {"resumen", "campos", "notas", "dudas"}
        campos = esquema["$defs"][esquema["properties"]["campos"]["$ref"].split("/")[-1]]
        assert campos["additionalProperties"] is False
        assert campos["required"] == [c.clave for c in definicion.campos]  # "copy", no "c_copy"


# ---------------------------------------------------------------------------
# La llamada a la API (simulada con la forma real)
# ---------------------------------------------------------------------------

def _ordenar(api, texto=DICTADO, tipo="cenefa"):
    return asyncio.run(brief_ia.ordenar(texto, tipo, cliente=api.cliente(), hoy=HOY))


def test_ordena_el_dictado_y_dice_lo_que_falta():
    from app.core.config import settings

    api = sim.ApiGrabada([_respuesta_cenefa()])
    resultado, uso = _ordenar(api)
    assert resultado["resumen"] == "Cenefas Ciberlunes: 2x1 en vinos"
    assert {c["clave"]: c["valor"] for c in resultado["campos"]}["locales"] == "40 locales"
    assert resultado["falta"] == ["Faltan las medidas", "Falta la cantidad", "Faltan los legales"]
    assert resultado["dudas"] == ["¿Del 28 al 30 de noviembre?"]
    assert (uso.input_tokens, uso.output_tokens) == (850, 140)

    pedido = api.pedidos[0]
    assert pedido["model"] == settings.MODELO_IA
    assert pedido["max_tokens"] == brief_ia.MAX_TOKENS
    assert pedido["output_config"]["effort"] == "low"
    assert pedido["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in pedido
    contenido = pedido["messages"][0]["content"]
    assert f"<dictado>\n{DICTADO}\n</dictado>" in contenido
    assert "Tipo de pieza: Cenefa." in contenido and "Hoy es 15/11/2026." in contenido


def test_redes_devuelve_el_copy_con_su_clave():
    api = sim.ApiGrabada([sim.mensaje([sim.texto(json.dumps({
        "resumen": "Historia Ciberlunes", "campos": {"formato": "historia", "copy": "¡Llegó!", "fecha": None},
        "notas": None, "dudas": [],
    }))])])
    resultado, _ = _ordenar(api, "una historia que diga llegó", "redes")
    assert [(c["clave"], c["valor"]) for c in resultado["campos"]] == [
        ("formato", "historia"), ("copy", "¡Llegó!"), ("fecha", None),
    ]
    assert resultado["falta"] == ["Falta la fecha"]


def test_un_json_que_no_cumple_el_esquema_es_un_error_claro():
    api = sim.ApiGrabada([sim.mensaje([sim.texto('{"resumen": "x", "campos": {"medidas": 3}}')])])
    with pytest.raises(brief_ia.BriefNoOrdenado):
        _ordenar(api)


def test_si_se_niega_o_se_corta_no_devuelve_nada_a_medias():
    api = sim.ApiGrabada([sim.mensaje([], "refusal")])
    with pytest.raises(brief_ia.BriefNoOrdenado, match="no quiso"):
        _ordenar(api)
    api = sim.ApiGrabada([sim.mensaje([sim.texto('{"resumen": "Cenef')], "max_tokens")])
    with pytest.raises(brief_ia.BriefNoOrdenado):
        _ordenar(api)


def test_el_simulador_del_servidor_de_prueba_tambien_pasa_por_el_esquema():
    """El simulador que usa scripts/servidor_ia_simulada.py arma su JSON con
    reglas: igual tiene que pasar la validación del SDK."""
    cliente = sim.cliente_con(sim.SimuladorDeDonTino())
    resultado, _ = asyncio.run(brief_ia.ordenar(DICTADO, "cenefa", cliente=cliente, hoy=HOY))
    valores = {c["clave"]: c["valor"] for c in resultado["campos"]}
    assert valores["precio_mecanica"] == "2x1 en vinos"
    assert valores["locales"] == "40 locales"
    assert valores["vigencia"] == "del 28 al 30"
    assert "Faltan las medidas" in resultado["falta"]
    assert resultado["dudas"] == ["¿De qué mes son las fechas?"]


# ---------------------------------------------------------------------------
# El endpoint
# ---------------------------------------------------------------------------

def _app(usuario, monkeypatch, api):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.api.routes import ia_brief
    from app.core.config import settings
    from app.core.database import get_db
    from app.core.deps import get_current_user
    from app.core.rate_limit import limiter
    from app.services import ia_cliente

    agregados = []

    class SesionFalsa:
        def add(self, fila):
            agregados.append(fila)

    async def db_falsa():
        yield SesionFalsa()

    async def usuario_actual():
        return usuario

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-simulada")
    monkeypatch.setattr(ia_cliente, "cliente_anthropic", api.cliente)
    limiter.reset()
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(ia_brief.router)
    app.dependency_overrides[get_db] = db_falsa
    app.dependency_overrides[get_current_user] = usuario_actual
    return TestClient(app), agregados


def _persona(*permisos):
    return SimpleNamespace(id=7, is_superuser=False, is_active=True, permissions=list(permisos), mundos=["redexpres"])


def test_endpoint_ordena_y_registra_el_uso(monkeypatch):
    from app.models.ai_usage_log import AIUsageLog

    api = sim.ApiGrabada([_respuesta_cenefa()])
    cliente, agregados = _app(_persona("calendario.tareas"), monkeypatch, api)
    r = cliente.post("/ia/brief/ordenar", json={"texto": DICTADO, "tipo": "cenefa"})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["tipo"] == "cenefa" and datos["tipoNombre"] == "Cenefa"
    assert "Faltan las medidas" in datos["falta"]
    assert datos["usage"]["total_tokens"] == 990
    usos = [f for f in agregados if isinstance(f, AIUsageLog)]
    assert [(u.feature, u.user_id, u.input_tokens, u.output_tokens) for u in usos] == [("brief_dictado", 7, 850, 140)]


def test_endpoint_tope_de_tamano_y_tipo_valido(monkeypatch):
    api = sim.ApiGrabada([])
    cliente, _ = _app(_persona("calendario.edit"), monkeypatch, api)
    assert cliente.post("/ia/brief/ordenar", json={"texto": "x" * (brief_ia.MAX_TEXTO + 1), "tipo": "cenefa"}).status_code == 422
    assert cliente.post("/ia/brief/ordenar", json={"texto": "cenefas", "tipo": "afiche"}).status_code == 422
    assert cliente.post("/ia/brief/ordenar", json={"texto": "  a ", "tipo": "otro"}).status_code == 422
    assert api.pedidos == []  # nada de eso llegó a la IA


def test_endpoint_pide_poder_escribir_tareas_o_acciones(monkeypatch):
    api = sim.ApiGrabada([])
    cliente, _ = _app(_persona("calendario.view", "ai.don_tino"), monkeypatch, api)
    r = cliente.post("/ia/brief/ordenar", json={"texto": DICTADO, "tipo": "cenefa"})
    assert r.status_code == 403
    assert api.pedidos == []


def test_endpoint_si_la_ia_falla_es_502_con_mensaje(monkeypatch):
    api = sim.ApiGrabada([sim.mensaje([], "refusal")])
    cliente, agregados = _app(_persona("calendario.tareas"), monkeypatch, api)
    r = cliente.post("/ia/brief/ordenar", json={"texto": DICTADO, "tipo": "cenefa"})
    assert r.status_code == 502 and "no quiso" in r.json()["detail"]


def test_endpoint_tiene_limite_por_minuto(monkeypatch):
    api = sim.ApiGrabada([_respuesta_cenefa() for _ in range(10)])
    cliente, _ = _app(_persona("calendario.tareas"), monkeypatch, api)
    codigos = [cliente.post("/ia/brief/ordenar", json={"texto": DICTADO, "tipo": "cenefa"}).status_code
               for _ in range(11)]
    assert codigos[:10] == [200] * 10 and codigos[10] == 429
