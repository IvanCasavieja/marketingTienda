"""La IA revisa la pieza antes que el aprobador (idea 5 de Ivan, 16/11/2026).

Sin la API real ni la base: la IA es `tests/ia_simulada.py` (el SDK de verdad
arma el pedido y parsea la respuesta, solo el modelo está grabado) y la base
es una de mentira que usa la misma regla de reclamo que la de Postgres
(`decidir_reclamo`). Lo que se fija:

- el pedido: las imágenes con la forma documentada de la API, el pedido a la
  agencia y el mundo, el modelo, el esfuerzo y la salida estructurada tal
  como la arma el SDK (additionalProperties false, sin mínimos ni máximos);
- la respuesta: se valida y se limpia (ubicación de píxeles a 0-1, topes);
- que un fallo de la IA (o de la base) no levante nunca: la entrega ya está;
- el tope por día, el apagado y que una versión no se pague dos veces;
- quién ve las observaciones: los aprobadores y quien gestiona, nunca quien
  entrega.

Lo que hace la consulta de Postgres de verdad (el reclamo con su candado,
cargar la versión, guardar y registrar el uso) se probó contra una copia
local de la base: ver el informe del 16/11/2026.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

import ia_simulada as sim
from app.core.config import settings
from app.services import revision_ia as rv
from app.services.revision_ia import Contexto, ImagenParaIA

HOY = date(2026, 11, 16)
CONTEXTO = Contexto(
    tipo_pieza="cenefa",
    brief={"precio": "$ 199", "vigenciaDesde": "2026-11-28", "vigenciaHasta": "2026-11-30",
           "legales": "Válido hasta agotar stock. No acumulable.", "medidas": "A4 apaisada"},
    mundo="tienda_inglesa", accion="Ciberlunes", accion_desde=date(2026, 11, 28), accion_hasta=date(2026, 11, 30),
    tarea="Cenefas de vinos", fase="Arte final", ronda=2, comentario="Ahí van los cambios", hoy=HOY,
)


def _jpeg(ancho=1600, alto=1131, color="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(buf, "JPEG", quality=75)
    return buf.getvalue()


def _png(ancho, alto, modo="RGBA") -> bytes:
    buf = io.BytesIO()
    Image.new(modo, (ancho, alto), (255, 0, 0, 128) if modo == "RGBA" else "red").save(buf, "PNG")
    return buf.getvalue()


def _imagenes(*tamanos) -> list[ImagenParaIA]:
    return [rv.preparar_imagen(f"im-{i}", _jpeg(a, h), "image/jpeg") for i, (a, h) in enumerate(tamanos, 1)]


def _obs(**kw) -> dict:
    base = {"tipo": "ortografia", "texto": "Dice «OFERAT»: debería ser «OFERTA».", "gravedad": "importante",
            "imagen": 1, "x": 480, "y": 136}
    return {**base, **kw}


def _respuesta(*observaciones, **kw) -> dict:
    return sim.mensaje([sim.pensamiento(), sim.texto(json.dumps({"observaciones": list(observaciones)}))],
                       entrada=4_800, salida=1_350, **kw)


def _pedir(api, imagenes=None, contexto=CONTEXTO):
    imagenes = imagenes if imagenes is not None else _imagenes((1600, 1131))
    return asyncio.run(rv.pedir_revision(api.cliente(), imagenes, contexto, "claude-opus-5-5"))


# ---------------------------------------------------------------------------
# El pedido
# ---------------------------------------------------------------------------

def test_el_pedido_lleva_las_imagenes_el_pedido_y_el_mundo():
    a, b = _jpeg(1600, 1131), _jpeg(900, 1600, "black")
    imagenes = [rv.preparar_imagen("im-a", a, "image/jpeg"), rv.preparar_imagen("im-b", b, "image/jpeg")]
    api = sim.ApiGrabada([_respuesta(_obs())])
    observaciones, uso = _pedir(api, imagenes)

    assert len(api.pedidos) == 1
    p = api.pedidos[0]
    assert p["model"] == "claude-opus-5-5"
    assert p["max_tokens"] == rv.MAX_TOKENS
    assert p["system"] == rv.SISTEMA
    # Opus 5.5 piensa siempre y rechaza apagarlo; la familia 5 rechaza temperature.
    assert "thinking" not in p and "temperature" not in p and "top_p" not in p
    assert p["output_config"]["effort"] == "medium"

    [mensaje] = p["messages"]
    assert mensaje["role"] == "user"
    c = mensaje["content"]
    assert [b["type"] for b in c] == ["text", "image", "text", "image", "text"]
    assert c[0]["text"] == "Imagen 1 de 2 (1600 × 1131 px):"
    assert c[2]["text"] == "Imagen 2 de 2 (900 × 1600 px):"
    # La forma documentada de un bloque de imagen en base64.
    for bloque, original in ((c[1], a), (c[3], b)):
        assert set(bloque) == {"type", "source"}
        assert set(bloque["source"]) == {"type", "media_type", "data"}
        assert bloque["source"]["type"] == "base64" and bloque["source"]["media_type"] == "image/jpeg"
        assert "\n" not in bloque["source"]["data"]
        assert base64.b64decode(bloque["source"]["data"]) == original  # tal cual: no se recomprime
    pedido = c[4]["text"]
    for esperado in ("Mundo de la acción: Tienda Inglesa", "Acción: Ciberlunes (del 28/11/2026 al 30/11/2026)",
                     "Tipo de pieza: Cenefa", "Fase: Arte final, ronda 2", "- Precio: $ 199",
                     "- Vigencia: del 28/11/2026 al 30/11/2026", "- Legales: Válido hasta agotar stock. No acumulable.",
                     "<comentario_de_la_agencia>\nAhí van los cambios\n</comentario_de_la_agencia>", "Hoy es 16/11/2026"):
        assert esperado in pedido, esperado
    assert observaciones[0]["imagenId"] == "im-a"
    assert (uso.input_tokens, uso.output_tokens) == (4_800, 1_350)


def _todos_los_esquemas(s):
    if isinstance(s, dict):
        yield s
        for v in s.values():
            yield from _todos_los_esquemas(v)
    elif isinstance(s, list):
        for v in s:
            yield from _todos_los_esquemas(v)


def test_la_salida_estructurada_es_la_que_acepta_la_api():
    """El esquema tal como lo arma el SDK 0.116 (messages.parse con
    output_format → output_config.format): todo objeto con
    additionalProperties false y todos sus campos obligatorios, y nada de lo
    que la API no acepta (mínimos, máximos, largos, valores por defecto)."""
    api = sim.ApiGrabada([_respuesta()])
    _pedir(api)
    formato = api.pedidos[0]["output_config"]["format"]
    assert formato["type"] == "json_schema"
    esquema = formato["schema"]
    objetos = [s for s in _todos_los_esquemas(esquema) if s.get("type") == "object"]
    assert len(objetos) == 2  # la respuesta y cada observación
    for o in objetos:
        assert o["additionalProperties"] is False
        assert sorted(o["required"]) == sorted(o["properties"])
    for s in _todos_los_esquemas(esquema):
        assert not {"minimum", "maximum", "minLength", "maxLength", "default", "exclusiveMinimum"} & set(s), s
    obs = esquema["$defs"]["ObservacionDeLaIA"]["properties"]
    assert obs["tipo"]["enum"] == list(rv.TIPOS)
    assert obs["gravedad"]["enum"] == list(rv.GRAVEDADES)
    assert obs["x"]["anyOf"] == [{"type": "integer"}, {"type": "null"}]
    assert esquema["properties"]["observaciones"]["items"] == {"$ref": "#/$defs/ObservacionDeLaIA"}


def test_el_formato_es_el_mismo_que_arma_messages_parse_del_sdk():
    """Va por messages.create (para no perder el uso de una respuesta
    cortada), pero output_config sale idéntico al de messages.parse con el
    mismo modelo de Pydantic: la transformación es la del SDK."""
    api = sim.ApiGrabada([_respuesta(), _respuesta()])
    _pedir(api)
    asyncio.run(api.cliente().messages.parse(
        model="claude-opus-5-5", max_tokens=100, messages=[{"role": "user", "content": "x"}],
        output_format=rv.RespuestaDeLaIA, output_config={"effort": "medium"},
    ))
    assert api.pedidos[0]["output_config"] == api.pedidos[1]["output_config"]


def test_un_pedido_sin_datos_lo_dice_y_sin_comentario_no_lleva_la_etiqueta():
    contexto = Contexto(**{**CONTEXTO.__dict__, "brief": {}, "comentario": None, "mundo": "tienda_farma"})
    texto = rv.texto_del_pedido(contexto)
    assert "Mundo de la acción: Tienda Farma" in texto
    assert "el pedido no tiene datos cargados" in texto
    assert "comentario_de_la_agencia" not in texto


def test_el_brief_va_con_las_etiquetas_del_formulario():
    assert rv.lineas_del_brief("mailing", {"asunto": "  ¡Llegó  la Navidad! ", "fechaEnvio": "2026-12-01",
                                           "llamado": "Comprá online", "detalle": "Línea 1\nLínea 2"}) == [
        "Asunto: ¡Llegó la Navidad!", "Fecha de envío: 01/12/2026", "Llamado a la acción: Comprá online",
        "Qué se necesita: Línea 1\nLínea 2",
    ]
    assert rv.lineas_del_brief("banner", {"desde": "2026-11-01", "link": "https://x.uy"}) == [
        "Link de destino: https://x.uy", "Fechas: del 01/11/2026 al ?",
    ]
    # En el orden del formulario de la cenefa: medidas, precio, vigencia, legales.
    assert rv.lineas_del_brief("cenefa", CONTEXTO.brief) == [
        "Medidas: A4 apaisada", "Precio: $ 199", "Vigencia: del 28/11/2026 al 30/11/2026",
        "Legales: Válido hasta agotar stock. No acumulable.",
    ]


# ---------------------------------------------------------------------------
# Las imágenes
# ---------------------------------------------------------------------------

def test_la_imagen_del_navegador_va_tal_cual():
    datos = _jpeg(1600, 1131)
    im = rv.preparar_imagen("im-1", datos, "image/jpeg")
    assert (im.datos, im.tipo_mime, im.ancho, im.alto) == (datos, "image/jpeg", 1600, 1131)
    png = _png(800, 600)
    assert rv.preparar_imagen("im-2", png, "image/png").datos == png


def test_una_imagen_mas_grande_que_1600_se_achica():
    im = rv.preparar_imagen("im-1", _png(2400, 1600, "RGB"), "image/png")
    assert (im.ancho, im.alto, im.tipo_mime) == (1600, 1067, "image/jpeg")
    assert Image.open(io.BytesIO(im.datos)).size == (1600, 1067)


def test_una_foto_girada_por_el_exif_va_derecha():
    """La pantalla la muestra derecha (el navegador respeta el EXIF): la IA
    tiene que ver lo mismo, si no los pins caen en otro lado."""
    img = Image.new("RGB", (800, 600), "white")
    exif = img.getexif()
    exif[0x0112] = 6  # girada 90°
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    im = rv.preparar_imagen("im-1", buf.getvalue(), "image/jpeg")
    assert (im.ancho, im.alto) == (600, 800)


def test_lo_que_no_es_imagen_no_pasa():
    with pytest.raises(ValueError):
        rv.preparar_imagen("im-1", b"esto no es una imagen", "image/jpeg")


def test_una_imagen_de_demasiados_pixeles_no_se_abre():
    """Un PNG plano de 2 MB puede medir 8.000 x 8.000: abierto ocuparía ~190 MB
    (el servidor tiene 512). Se corta antes de descomprimirlo."""
    buf = io.BytesIO()
    Image.new("1", (8000, 8000)).save(buf, "PNG")
    assert len(buf.getvalue()) < 2 * 1024 * 1024
    with pytest.raises(ValueError, match="demasiado grande"):
        rv.preparar_imagen("im-1", buf.getvalue(), "image/png")


def test_el_pedido_tiene_un_tope_de_espera():
    api = sim.ApiGrabada([_respuesta()])
    capturado = {}
    cliente = api.cliente()
    original = cliente.messages.create

    async def con_espia(**kw):
        capturado.update(kw)
        return await original(**kw)

    cliente.messages.create = con_espia
    asyncio.run(rv.pedir_revision(cliente, _imagenes((1600, 1131)), CONTEXTO, "claude-opus-5-5"))
    assert capturado["timeout"] == rv.ESPERA_SEGUNDOS


# ---------------------------------------------------------------------------
# La respuesta
# ---------------------------------------------------------------------------

def test_la_ubicacion_pasa_de_pixeles_a_0_1_y_cae_adentro():
    imagenes = _imagenes((1600, 1131), (800, 800))
    obs = rv.limpiar_observaciones({"observaciones": [
        _obs(texto="a", x=800, y=1131),
        _obs(texto="b", imagen=2, x=5000, y=-3),
        _obs(texto="c", imagen=3, x=10, y=10),       # no hay imagen 3
        _obs(texto="d", imagen=None, x=10, y=10),    # con dos imágenes, no se sabe cuál
        _obs(texto="e", imagen=1, x=None, y=40),     # sin las dos coordenadas no hay lugar
    ]}, imagenes)
    lugares = [(o["texto"], o["imagenId"], o["x"], o["y"]) for o in obs]
    assert lugares == [
        ("a", "im-1", 0.5, 1.0), ("b", "im-2", 1.0, 0.0), ("c", None, None, None), ("d", None, None, None),
        ("e", "im-1", None, None),
    ]


def test_con_una_sola_imagen_la_ubicacion_sin_numero_es_de_esa():
    [o] = rv.limpiar_observaciones({"observaciones": [_obs(imagen=None, x=160, y=113)]}, _imagenes((1600, 1131)))
    assert (o["imagenId"], o["x"], o["y"]) == ("im-1", 0.1, 0.1)


def test_la_respuesta_se_limpia():
    largo = "palabra " * 100
    obs = rv.limpiar_observaciones({"observaciones": [
        _obs(texto="   ", gravedad="importante"),
        _obs(texto="Un  dato   dudoso", gravedad="a_revisar", tipo="inventado"),
        _obs(texto="un dato dudoso", gravedad="importante"),  # repetida (sin importar mayúsculas)
        _obs(texto=largo, gravedad="rarísima"),
        _obs(texto="El precio es $ 249 y en el pedido es $ 199.", tipo="precio_vigencia"),
    ]}, _imagenes((1600, 1131)))
    assert [o["texto"][:20] for o in obs] == ["El precio es $ 249 y", "Un dato dudoso", "palabra palabra pala"]
    assert obs[1]["tipo"] == "otro" and obs[2]["gravedad"] == "a_revisar"
    assert len(obs[2]["texto"]) == rv.MAX_TEXTO and obs[2]["texto"].endswith("…")
    assert all(o["estado"] == "nueva" and o["id"].startswith("ob-") for o in obs)
    assert len({o["id"] for o in obs}) == 3


def test_como_mucho_diez_y_las_importantes_primero():
    muchas = [_obs(texto=f"dudosa {i}", gravedad="a_revisar") for i in range(8)]
    muchas += [_obs(texto=f"segura {i}") for i in range(5)]
    obs = rv.limpiar_observaciones({"observaciones": muchas}, _imagenes((1600, 1131)))
    assert len(obs) == rv.MAX_OBSERVACIONES
    assert [o["texto"] for o in obs[:5]] == [f"segura {i}" for i in range(5)]
    assert [o["texto"] for o in obs[5:]] == [f"dudosa {i}" for i in range(5)]


def test_sin_observaciones_es_una_respuesta_valida():
    observaciones, _ = _pedir(sim.ApiGrabada([_respuesta()]))
    assert observaciones == []


@pytest.mark.parametrize("respuesta, motivo", [
    (sim.mensaje([], "refusal"), "no quiso"),
    (sim.mensaje([sim.texto('{"observaciones": [')], "max_tokens"), "se cortó"),
    (sim.mensaje([sim.texto("Encontré dos errores de ortografía.")]), "esquema"),
    (sim.mensaje([sim.texto(json.dumps({"observaciones": [{"tipo": "ortografia"}]}))]), "esquema"),
])
def test_si_la_ia_contesta_algo_que_no_sirve_es_revision_fallida(respuesta, motivo):
    with pytest.raises(rv.RevisionFallida) as e:
        _pedir(sim.ApiGrabada([respuesta]))
    assert motivo in str(e.value)


def test_una_revision_fallida_lleva_lo_que_se_uso():
    """Una negativa o una respuesta cortada se pagan igual: el uso tiene que
    llegar al registro (la cortada es la más cara)."""
    with pytest.raises(rv.RevisionFallida) as e:
        _pedir(sim.ApiGrabada([sim.mensaje([], "refusal", entrada=4_000, salida=12)]))
    assert (e.value.uso.input_tokens, e.value.uso.output_tokens) == (4_000, 12)
    with pytest.raises(rv.RevisionFallida) as e:
        _pedir(sim.ApiGrabada([sim.mensaje([sim.texto('{"obse')], "max_tokens", entrada=4_000, salida=16_000)]))
    assert (e.value.uso.input_tokens, e.value.uso.output_tokens) == (4_000, 16_000)


def test_lo_que_contesta_la_ia_simulada_pasa_la_validacion_del_sdk():
    """La revisión del servidor de prueba (scripts/servidor_ia_simulada.py):
    observaciones de ejemplo, con ubicación, que el SDK valida igual."""
    cliente = sim.cliente_con(sim.SimuladorDeDonTino())
    obs, uso = asyncio.run(rv.pedir_revision(cliente, _imagenes((1600, 1131)), CONTEXTO, "claude-opus-5-5"))
    assert [o["tipo"] for o in obs] == ["ortografia", "precio_vigencia", "legal"]
    assert "$ 199" in obs[1]["texto"]
    assert all(o["imagenId"] == "im-1" and 0 <= o["x"] <= 1 and 0 <= o["y"] <= 1 for o in obs)
    sin = Contexto(**{**CONTEXTO.__dict__, "brief": {"detalle": "Sin observaciones, por favor"}})
    obs, _ = asyncio.run(rv.pedir_revision(cliente, _imagenes((1600, 1131)), sin, "claude-opus-5-5"))
    assert obs == []


# ---------------------------------------------------------------------------
# La revisión de una versión, de punta a punta
# ---------------------------------------------------------------------------

class BaseFalsa:
    """La base de mentira: la misma regla de reclamo que la de Postgres."""

    def __init__(self, versiones: list[str], *, falla_al_cargar=False):
        self.versiones = {v: (CONTEXTO, [(f"im-{v}", _jpeg(), "image/jpeg")]) for v in versiones}
        self.filas: dict[str, dict] = {}
        self.falla_al_cargar = falla_al_cargar

    async def reclamar(self, version_id, tope, desde, modelo):
        decision = rv.decidir_reclamo(
            ya_reclamada=version_id in self.filas, version_existe=version_id in self.versiones,
            hechas_hoy=sum(1 for f in self.filas.values() if f["estado"] != "tope"), tope=tope,
        )
        if decision in ("ok", "tope"):
            self.filas[version_id] = {"estado": "pendiente" if decision == "ok" else "tope", "modelo": modelo}
        return decision

    async def cargar(self, version_id):
        if self.falla_al_cargar:
            raise RuntimeError("se cortó la conexión con la base")
        return self.versiones[version_id]

    async def terminar(self, version_id, *, estado, observaciones, motivo, modelo, uso):
        self.filas[version_id].update(estado=estado, observaciones=observaciones, motivo=motivo, modelo=modelo, uso=uso)


@pytest.fixture
def ia_prendida(monkeypatch):
    monkeypatch.setattr(settings, "IA_REVISION_ACTIVA", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-simulada")
    monkeypatch.setattr(settings, "MODELO_IA_REVISION", "claude-opus-5-5")
    monkeypatch.setattr(settings, "IA_REVISION_POR_DIA", 200)


def _revisar(version_id, base, api):
    return asyncio.run(rv.revisar_version(version_id, base=base, cliente=api.cliente()))


def test_revisa_la_version_y_guarda_lo_que_encontro_con_el_uso(ia_prendida):
    base, api = BaseFalsa(["ve-1"]), sim.ApiGrabada([_respuesta(_obs(), _obs(texto="otra", gravedad="a_revisar"))])
    assert _revisar("ve-1", base, api) == "lista"
    fila = base.filas["ve-1"]
    assert fila["estado"] == "lista" and fila["modelo"] == "claude-opus-5-5"
    assert [o["texto"] for o in fila["observaciones"]] == ["Dice «OFERAT»: debería ser «OFERTA».", "otra"]
    assert (fila["uso"].input_tokens, fila["uso"].output_tokens) == (4_800, 1_350)


def test_la_misma_version_no_se_paga_dos_veces(ia_prendida):
    base, api = BaseFalsa(["ve-1"]), sim.ApiGrabada([_respuesta(_obs())])
    assert _revisar("ve-1", base, api) == "lista"
    assert _revisar("ve-1", base, api) == "ya"
    assert len(api.pedidos) == 1


def test_una_que_fallo_tampoco_se_vuelve_a_mandar(ia_prendida):
    base = BaseFalsa(["ve-1"])
    assert _revisar("ve-1", base, sim.ApiGrabada([sim.mensaje([], "refusal")])) == "error"
    api = sim.ApiGrabada([_respuesta(_obs())])
    assert _revisar("ve-1", base, api) == "ya"
    assert api.pedidos == []


def test_el_tope_por_dia(ia_prendida, monkeypatch):
    monkeypatch.setattr(settings, "IA_REVISION_POR_DIA", 2)
    base, api = BaseFalsa(["ve-1", "ve-2", "ve-3", "ve-4"]), sim.ApiGrabada([_respuesta(), _respuesta()])
    assert [_revisar(v, base, api) for v in ("ve-1", "ve-2", "ve-3", "ve-4")] == ["lista", "lista", "tope", "tope"]
    assert len(api.pedidos) == 2
    assert base.filas["ve-3"]["estado"] == "tope"
    # Las que quedaron afuera por el tope no cuentan como revisadas.
    assert rv.decidir_reclamo(ya_reclamada=False, version_existe=True, hechas_hoy=1, tope=2) == "ok"


def test_con_tope_cero_no_se_manda_ninguna(ia_prendida, monkeypatch):
    monkeypatch.setattr(settings, "IA_REVISION_POR_DIA", 0)
    api = sim.ApiGrabada([])
    assert _revisar("ve-1", BaseFalsa(["ve-1"]), api) == "tope"
    assert api.pedidos == []


def test_apagada_no_llama_a_la_ia_ni_toca_la_base(ia_prendida, monkeypatch):
    monkeypatch.setattr(settings, "IA_REVISION_ACTIVA", False)
    base, api = BaseFalsa(["ve-1"]), sim.ApiGrabada([])
    assert _revisar("ve-1", base, api) == "apagada"
    assert base.filas == {} and api.pedidos == []
    assert rv.activa() is False


def test_sin_clave_no_llama_a_la_ia(ia_prendida, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    base, api = BaseFalsa(["ve-1"]), sim.ApiGrabada([])
    assert _revisar("ve-1", base, api) == "sin_clave"
    assert base.filas == {} and api.pedidos == []
    assert rv.activa() is False


def test_una_version_borrada_no_se_manda(ia_prendida):
    api = sim.ApiGrabada([])
    assert _revisar("ve-x", BaseFalsa(["ve-1"]), api) == "no_existe"
    assert api.pedidos == []


def test_si_la_ia_falla_no_levanta_y_no_se_muestra_nada(ia_prendida, monkeypatch):
    """La IA caída (error de conexión, con los reintentos de siempre): la
    revisión termina en error, sin observaciones, y la pantalla no muestra
    nada. `revisar_version` no levanta: la entrega ya se guardó y contestó."""
    async def sin_espera(_):
        return None

    monkeypatch.setattr("app.core.llm_retry.asyncio.sleep", sin_espera)

    def caida(_cuerpo):
        raise httpx.ConnectError("la API no contesta")

    base = BaseFalsa(["ve-1"])
    assert asyncio.run(rv.revisar_version("ve-1", base=base, cliente=sim.cliente_con(caida))) == "error"
    fila = base.filas["ve-1"]
    assert fila["estado"] == "error" and fila["observaciones"] == [] and "APIConnectionError" in fila["motivo"]
    assert rv.para_mostrar("error", datetime.now(timezone.utc), [], datetime.now(timezone.utc))["estado"] == "nada"


def test_si_la_api_rechaza_el_pedido_tampoco_levanta(ia_prendida):
    def rechazo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                      "message": "algo no le gustó"}})

    import anthropic
    cliente = anthropic.AsyncAnthropic(api_key="sk-ant-simulada", max_retries=0,
                                       http_client=httpx.AsyncClient(transport=httpx.MockTransport(rechazo)))
    base = BaseFalsa(["ve-1"])
    assert asyncio.run(rv.revisar_version("ve-1", base=base, cliente=cliente)) == "error"
    assert "BadRequestError" in base.filas["ve-1"]["motivo"]


def test_una_negativa_queda_en_error_pero_registra_el_uso(ia_prendida):
    base = BaseFalsa(["ve-1"])
    assert _revisar("ve-1", base, sim.ApiGrabada([sim.mensaje([], "refusal", entrada=3_900, salida=8)])) == "error"
    assert (base.filas["ve-1"]["uso"].input_tokens, base.filas["ve-1"]["uso"].output_tokens) == (3_900, 8)


def test_si_la_base_falla_tampoco_levanta(ia_prendida):
    base = BaseFalsa(["ve-1"], falla_al_cargar=True)
    api = sim.ApiGrabada([])
    assert _revisar("ve-1", base, api) == "error"
    assert base.filas["ve-1"]["estado"] == "error" and api.pedidos == []

    class Rota(BaseFalsa):
        async def reclamar(self, *a):
            raise RuntimeError("no hay base")

    assert _revisar("ve-1", Rota(["ve-1"]), api) == "error"


def test_el_dia_del_tope_es_el_de_uruguay():
    # 16/11 a las 02:00 UTC son las 23:00 del 15/11 en Montevideo (UTC-3).
    assert rv.inicio_del_dia(datetime(2026, 11, 16, 2, 0, tzinfo=timezone.utc)) == datetime(
        2026, 11, 15, 3, 0, tzinfo=timezone.utc)
    assert rv.inicio_del_dia(datetime(2026, 11, 16, 3, 30, tzinfo=timezone.utc)) == datetime(
        2026, 11, 16, 3, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Quién la ve y qué se muestra
# ---------------------------------------------------------------------------

PROMO, MARCA, AGENCIA, LIDER, OTRO = 1, 2, 4, 5, 9


def _ve(usuario, *, gestor=False, activa=True, subida_por=AGENCIA):
    return rv.puede_ver(usuario, es_gestor=gestor, aprobadores=[PROMO, MARCA], responsable_id=AGENCIA,
                        subida_por_id=subida_por, activa=activa)


def test_la_ven_los_aprobadores_y_quien_gestiona():
    assert _ve(PROMO) and _ve(MARCA)
    assert _ve(LIDER, gestor=True)


def test_no_la_ve_la_agencia_aunque_gestione():
    """Quien entrega (el responsable, o quien subió esa versión) nunca: para
    la agencia se leería como una decisión."""
    assert not _ve(AGENCIA)
    assert not _ve(AGENCIA, gestor=True)
    assert not _ve(LIDER, gestor=True, subida_por=LIDER)


def test_no_la_ve_quien_solo_mira_el_calendario():
    assert not _ve(OTRO)
    assert not _ve(None)


def test_apagada_no_la_ve_nadie():
    assert not _ve(PROMO, activa=False)
    assert not _ve(LIDER, gestor=True, activa=False)


def test_puede_ver_revision_de_la_ruta_usa_la_tarea_y_la_version(monkeypatch):
    from app.api.routes.entregas import puede_ver_revision

    monkeypatch.setattr(settings, "IA_REVISION_ACTIVA", True)
    entrega = SimpleNamespace(aprobadores=[PROMO, MARCA])
    tarea = SimpleNamespace(asignado_a_id=AGENCIA)
    version = SimpleNamespace(subida_por_id=AGENCIA)

    def persona(uid, *permisos, superusuario=False):
        return SimpleNamespace(id=uid, permissions=list(permisos), is_superuser=superusuario)

    assert puede_ver_revision(persona(PROMO, "calendario.view"), entrega, tarea, version)
    assert puede_ver_revision(persona(LIDER, "calendario.view", "calendario.tareas"), entrega, tarea, version)
    assert puede_ver_revision(persona(LIDER, superusuario=True), entrega, tarea, None)
    assert not puede_ver_revision(persona(AGENCIA, "calendario.view", "calendario.tareas"), entrega, tarea, version)
    assert not puede_ver_revision(persona(OTRO, "calendario.view"), entrega, tarea, version)
    monkeypatch.setattr(settings, "IA_REVISION_ACTIVA", False)
    assert not puede_ver_revision(persona(PROMO, "calendario.view"), entrega, tarea, version)


def test_que_se_muestra_segun_como_termino():
    ahora = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)
    recien = ahora - timedelta(minutes=1)
    assert rv.para_mostrar(None, None, None, ahora) == {"estado": "nada", "observaciones": []}
    assert rv.para_mostrar("pendiente", recien, [], ahora)["estado"] == "pendiente"
    # Pendiente hace mucho: se cayó el proceso a mitad de camino. Nada.
    assert rv.para_mostrar("pendiente", ahora - timedelta(minutes=30), [], ahora)["estado"] == "nada"
    assert rv.para_mostrar("error", recien, [], ahora)["estado"] == "nada"
    assert rv.para_mostrar("tope", recien, [], ahora)["estado"] == "nada"
    assert rv.para_mostrar("lista", recien, [], ahora) == {"estado": "lista", "observaciones": []}
    assert rv.para_mostrar("lista", recien, [{"id": "ob-1"}], ahora)["observaciones"] == [{"id": "ob-1"}]


# ---------------------------------------------------------------------------
# Descartar y convertir en marca
# ---------------------------------------------------------------------------

def _lista():
    return rv.limpiar_observaciones({"observaciones": [_obs(texto="uno"), _obs(texto="dos")]}, _imagenes((1600, 1131)))


def test_descartar_y_traer_de_vuelta():
    ahora = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)
    obs = _lista()
    nuevas = rv.descartar(obs, obs[0]["id"], True, PROMO, ahora)
    assert nuevas is not obs and obs[0]["estado"] == "nueva"  # lista nueva: JSONB solo se guarda si cambia
    assert (nuevas[0]["estado"], nuevas[0]["por"], nuevas[0]["fecha"]) == ("descartada", PROMO, ahora.isoformat())
    assert nuevas[1]["estado"] == "nueva"
    vuelta = rv.descartar(nuevas, obs[0]["id"], False, MARCA, ahora)
    assert (vuelta[0]["estado"], vuelta[0]["por"]) == ("nueva", None)


def test_no_se_descarta_una_que_ya_es_marca_ni_una_que_no_existe():
    ahora = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)
    obs = rv.marcar_convertidas(_lista(), {}, PROMO, ahora)
    obs = rv.marcar_convertidas(obs, {obs[0]["id"]: ("mk-1", 3)}, PROMO, ahora)
    with pytest.raises(rv.NoSePuede) as e:
        rv.descartar(obs, obs[0]["id"], True, PROMO, ahora)
    assert e.value.codigo == 409
    with pytest.raises(rv.NoSePuede) as e:
        rv.descartar(obs, "ob-inventada", True, PROMO, ahora)
    assert e.value.codigo == 404


def test_convertidas_en_marca_quedan_con_su_numero():
    ahora = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)
    obs = _lista()
    nuevas = rv.marcar_convertidas(obs, {obs[1]["id"]: ("mk-9", 4), "ob-inventada": ("mk-0", 5)}, MARCA, ahora)
    assert nuevas[0]["estado"] == "nueva"
    assert {k: nuevas[1][k] for k in ("estado", "marcaId", "numero", "por")} == {
        "estado": "marca", "marcaId": "mk-9", "numero": 4, "por": MARCA}


def test_la_marca_puede_venir_de_una_observacion_de_la_ia():
    from app.api.routes.entregas import DecisionNueva, MarcaNueva

    m = MarcaNueva(imagenId="im-1", x=0.3, y=0.12, texto="Dice «OFERAT»", observacionIA="ob-0123456789ab")
    assert m.observacionIA == "ob-0123456789ab"
    assert MarcaNueva(imagenId="im-1", x=0.3, y=0.1, texto="sin IA").observacionIA is None
    with pytest.raises(ValidationError):
        MarcaNueva(imagenId="im-1", x=0.3, y=0.1, texto="x", observacionIA="ob/../../algo")
    DecisionNueva(decision="cambios", marcas=[m])
