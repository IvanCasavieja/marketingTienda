"""Lo que se le pide a CatTi y la segunda lectura del lado del MAILING
(rrss/catti.py y rrss/validador.py). Sin llamar a la API: se prueba el
contrato (la tool, las instrucciones) y el flujo con el modelo reemplazado.

Viene del análisis del 22/09/2026 sobre las 67 placas de producción: la
lectura de la PLACA fue estable (31 de 33 idénticas entre dos corridas) y la
del MAILING no: la Jarra INHAUS salió '$1090', '$1.090' y '$7799' en tres
corridas del mismo PDF, y dos de esas tres acusaron a las placas de un error
de precio que no tenían.
"""
import asyncio
import pathlib

from PIL import Image

from app.services.rrss import catti, validador

_RRSS = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "rrss"


# ---------------------------------------------------------------- la tool

def test_todo_lo_que_pide_el_informe_es_obligatorio_para_catti():
    """CatTi no "decide" si rellena una columna: la tool exige cada campo
    (tool_choice forzado + required), y el vacío es una respuesta explícita."""
    props = catti._TOOL_PLACA["input_schema"]["properties"]
    assert set(catti._TOOL_PLACA["input_schema"]["required"]) >= {
        "producto", "fecha", "legal_bases", "legal_alcohol", "cta", "otros_textos",
    }
    assert set(props["producto"]["required"]) == {
        "descripcion", "precio_anterior", "precio_anterior_tachado", "mecanica",
        "oferta_encabezado", "oferta_precio", "oferta_pie", "es_alcohol",
    }


def test_el_logo_de_la_campana_no_es_otro_texto():
    """4 de 67 placas transcribían 'LOS' / 'ROMPE del finde' como "otro texto"
    con logo_campana_presente=true al lado: el mismo dato dos veces, una de
    ellas como texto suelto que iría a la hoja ancha."""
    desc = catti._TOOL_PLACA["input_schema"]["properties"]["otros_textos"]["description"]
    assert "logo de la campaña" in desc and "logo_campana_presente" in desc


def test_los_digitos_van_una_sola_vez():
    """'$7799' por '$799' y '$1.090' por '$1090' salieron de lecturas reales del
    mismo mailing. Se le dice explícito en los dos campos de precio."""
    props = catti._PROPIEDADES_PRODUCTO
    for campo in ("precio_anterior", "oferta_precio"):
        assert "UNA sola vez" in props[campo]["description"], campo
        assert "'$799' no es '$7799'" in props[campo]["description"]


def test_la_tool_de_un_producto_pide_lo_mismo_que_la_del_mailing():
    """La relectura del recorte tiene que devolver EXACTAMENTE las mismas claves
    que la lectura de la página, si no la comparación campo a campo no cierra."""
    assert catti._TOOL_PRODUCTO["input_schema"]["properties"] is catti._PROPIEDADES_PRODUCTO
    assert catti._TOOL_PRODUCTO["input_schema"]["required"] == catti._REQUERIDOS_PRODUCTO
    assert "confirmar una lectura anterior" in catti._INSTRUCCION_PRODUCTO


# ---------------------------------------------------------------- el flujo

def _mailing(precio_anterior: str) -> dict:
    return {
        "origen": "mailing", "fecha": "DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE", "fecha_pagina": 0,
        "legal_alcohol": "", "legal_alcohol_pagina": None,
        "productos": [{
            "descripcion": "Jarra eléctrica INHAUS negra. 1.7 L", "precio_anterior": precio_anterior,
            "precio_anterior_tachado": True, "mecanica": "", "oferta_encabezado": "Oferta",
            "oferta_precio": "$799", "oferta_pie": "", "es_alcohol": False, "pagina": 0,
            "cajas": {"producto": [0.1, 0.1, 0.6, 0.6]}, "recorte": None,
        }],
    }


def _lectura(precio_anterior: str) -> dict:
    return catti.normalizar_placa({
        "producto": {
            "descripcion": "Jarra eléctrica INHAUS negra. 1.7 L", "precio_anterior": precio_anterior,
            "precio_anterior_tachado": True, "mecanica": "", "oferta_encabezado": "Oferta",
            "oferta_precio": "$799", "oferta_pie": "", "es_alcohol": False,
        },
        "fecha": "DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE", "logo_campana_presente": True,
        "isotipo_presente": True, "legal_bases": "Bases y condiciones en tiendainglesa.com.uy",
        "legal_alcohol": "", "cta": "", "otros_textos": [],
        "imagen_producto": {"presente": True, "que_se_ve": "jarra", "coincide_con_descripcion": True, "motivo": ""},
    })


def _placa_jpeg() -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (30, 60, 150)).save(buf, format="JPEG")
    return buf.getvalue()


def _correr(monkeypatch, mailing: dict, releido: str | None, placa_lee: str = "$1090"):
    """validar_placa con el modelo reemplazado: la placa lee `placa_lee` las dos
    veces y el recorte del mailing lee `releido`. Devuelve (resultado, llamadas)."""
    llamadas = {"placa": 0, "producto": 0, "localizar": 0}

    async def leer_placa(prep):
        llamadas["placa"] += 1
        return _lectura(placa_lee), 10, 5

    async def leer_producto(recorte):
        llamadas["producto"] += 1
        # el recorte llega AMPLIADO: de ~460 px CatTi leía '$1.090'; a 1400, '$1090'
        assert recorte.width == validador._ANCHO_RELECTURA
        return catti._producto({
            "descripcion": "Jarra eléctrica INHAUS negra. 1.7 L", "precio_anterior": releido,
            "precio_anterior_tachado": True, "mecanica": "", "oferta_encabezado": "Oferta",
            "oferta_precio": "$799", "oferta_pie": "", "es_alcohol": False,
        }), 7, 3

    async def localizar(datos, lectura):
        llamadas["localizar"] += 1
        return {}, 0, 0

    monkeypatch.setattr(catti, "leer_placa", leer_placa)
    monkeypatch.setattr(catti, "leer_producto_del_mailing", leer_producto)
    monkeypatch.setattr(catti, "localizar_placa", localizar)

    async def paginas():
        return [Image.new("RGB", (400, 600), "white")]

    r = asyncio.run(validador.validar_placa(_placa_jpeg(), "jarra_10.jpg", mailing, paginas, validador.CONFIG_DEFECTO))
    return r, llamadas


def test_si_el_recorte_del_mailing_dice_lo_que_dice_la_placa_no_hay_error(monkeypatch):
    """El caso real: la página entera se leyó '$1.090', la placa dice '$1090'
    (dos veces) y el recorte ampliado también '$1090'. Tres lecturas contra una:
    la fila baja a ok y lo dice."""
    r, llamadas = _correr(monkeypatch, _mailing("$1.090"), releido="$1090")
    fila = next(f for f in r.resultado["filas"] if f["campo"] == "precio_anterior")
    assert r.estado == "ok"
    assert fila["estado"] == "ok" and fila["severidad"] is None
    assert "recorte ampliado" in fila["nota"] and "'$1.090'" in fila["nota"]
    assert llamadas == {"placa": 2, "producto": 1, "localizar": 0}
    assert "relectura_mailing" in r.resultado["tiempos_ms"]
    # y los tokens de la relectura se cuentan
    assert r.tokens_in == 27 and r.tokens_out == 13


def test_si_el_recorte_repite_la_primera_lectura_el_error_se_sostiene(monkeypatch):
    r, llamadas = _correr(monkeypatch, _mailing("$1.090"), releido="$1.090")
    fila = next(f for f in r.resultado["filas"] if f["campo"] == "precio_anterior")
    assert r.estado == "diferencias" and fila["severidad"] == "error"
    assert llamadas["producto"] == 1


def test_si_el_recorte_dice_una_tercera_cosa_baja_a_aviso(monkeypatch):
    r, _ = _correr(monkeypatch, _mailing("$1.090"), releido="$1O90")
    fila = next(f for f in r.resultado["filas"] if f["campo"] == "precio_anterior")
    assert r.estado == "avisos" and fila["severidad"] == "aviso" and fila["estado"] == "revisar"
    assert "dos lecturas" in fila["nota"]


def test_sin_error_de_precio_no_se_relee_el_mailing(monkeypatch):
    """La relectura cuesta una llamada: solo cuando hace falta."""
    r, llamadas = _correr(monkeypatch, _mailing("$1090"), releido="$1090")
    assert r.estado == "ok"
    assert llamadas == {"placa": 1, "producto": 0, "localizar": 0}


def test_contra_una_planilla_no_hay_nada_que_releer(monkeypatch):
    """Una planilla no se lee, se abre: el precio ya se compara por importe."""
    mailing = {**_mailing("$1.090"), "origen": "planilla", "campos": ["descripcion", "precio_anterior"], "precios_con_cola": []}
    mailing["productos"][0]["fila"] = {"numero": 2, "valores": {"descripcion": "Jarra eléctrica INHAUS negra. 1.7 L"}}
    mailing["planilla"] = {"archivo": "x.xlsx", "hoja": "", "titulos": {"descripcion": "DESCRIPCION"}, "avisos": []}
    r, llamadas = _correr(monkeypatch, mailing, releido="$1090")
    assert r.estado == "ok"  # $1.090 y $1090 valen lo mismo
    assert llamadas["producto"] == 0


def test_el_validador_usa_el_recorte_ancho_para_releer():
    """El recorte que se muestra en pantalla es de 520 px; el que se relee tiene
    que ser más ancho, si no la relectura hereda el mismo problema."""
    src = (_RRSS / "validador.py").read_text(encoding="utf-8")
    assert "_ANCHO_RELECTURA = 1400" in src
    assert "confirmar_con_relectura_de_la_fuente" in src
    # y se agranda de verdad: una página de 1600 px da un producto de ~460 px
    pagina = Image.new("RGB", (1600, 2183), "white")
    recorte = validador._recorte_ampliado(pagina, [0.09, 0.73, 0.30, 0.88])
    assert recorte.width == 1400 and recorte.height > 1400


def test_un_tachado_que_la_segunda_lectura_desmiente_baja_a_aviso(monkeypatch):
    """La placa dice el precio tachado; la primera lectura no vio la línea y la
    segunda sí: no se acusa, se pide mirar."""
    lecturas = iter([False, True])
    llamadas = {"placa": 0}

    async def leer_placa(prep):
        llamadas["placa"] += 1
        lectura = _lectura("$1090")
        lectura["producto"]["precio_anterior_tachado"] = next(lecturas)
        return lectura, 1, 1

    async def localizar(datos, lectura):
        return {}, 0, 0

    monkeypatch.setattr(catti, "leer_placa", leer_placa)
    monkeypatch.setattr(catti, "localizar_placa", localizar)

    async def paginas():
        return [Image.new("RGB", (400, 600), "white")]

    r = asyncio.run(validador.validar_placa(_placa_jpeg(), "jarra_21.jpg", _mailing("$1090"), paginas, validador.CONFIG_DEFECTO))
    fila = next(f for f in r.resultado["filas"] if f["campo"] == "precio_anterior_tachado")
    assert llamadas["placa"] == 2
    assert r.estado == "avisos" and fila["severidad"] == "aviso"
