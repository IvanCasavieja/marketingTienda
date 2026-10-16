"""Las descripciones de Tinín se piden a Claude en paralelo, no un chunk atrás
de otro. Medido en producción el 16/10/2026: 20 productos tardan ~5 s y una
tanda de 80 (4 chunks en serie) tardaba 20,4 s con la pantalla "cargando".

Lo que fijan estos tests: los chunks salen juntos, las sugerencias vuelven en
el orden de siempre aunque Claude conteste desordenado, un chunk que falla se
reporta solo (fail-soft) y el uso se registra una vez por chunk que anduvo.
"""
import asyncio
import json
import re

from app.services.cenefas import convertidor_ai
from app.services.cenefas.convertidor_ai import _CHUNK_SIZE, generar_descripciones


def _items(n: int) -> list[dict]:
    return [
        {"row_id": i, "codigo": str(1000 + i), "nombreArticulo": f"PRODUCTO {i}",
         "descripcionWeb": "", "esFiambreKg": False, "unidadVenta": ""}
        for i in range(1, n + 1)
    ]


def _nombres_del_prompt(prompt: str) -> list[str]:
    return re.findall(r'nombre ERP: "([^"]+)"', prompt)


def _respuesta_para(prompt: str) -> str:
    """Claude de mentira: devuelve "Desc <nombre>" para cada producto del chunk."""
    nombres = _nombres_del_prompt(prompt)
    return json.dumps({"descripciones": {str(k): f"Desc {nom}" for k, nom in enumerate(nombres, start=1)}})


def _sin_log(monkeypatch):
    async def _nada(*_args, **_kwargs):
        return None
    monkeypatch.setattr(convertidor_ai, "log_ai_usage", _nada)


def test_los_chunks_salen_en_paralelo(monkeypatch):
    en_vuelo = 0
    pico = 0

    async def fake_ask(_system, prompt, **_kw):
        nonlocal en_vuelo, pico
        en_vuelo += 1
        pico = max(pico, en_vuelo)
        await asyncio.sleep(0.05)
        en_vuelo -= 1
        return _respuesta_para(prompt), 100, 50

    monkeypatch.setattr(convertidor_ai, "_ask_claude", fake_ask)
    _sin_log(monkeypatch)

    res = asyncio.run(generar_descripciones(_items(3 * _CHUNK_SIZE), db=None, user_id=1))

    assert pico == 3, f"los 3 chunks tenían que estar en vuelo a la vez, hubo {pico}"
    assert len(res["suggestions"]) == 3 * _CHUNK_SIZE
    assert res["failed_row_ids"] == [] and res["errores"] == []


def test_el_orden_de_las_sugerencias_no_depende_de_quien_contesta_primero(monkeypatch):
    async def fake_ask(_system, prompt, **_kw):
        # El primer chunk es el más lento: si el orden saliera por llegada,
        # PRODUCTO 1 quedaría último.
        primero = _nombres_del_prompt(prompt)[0]
        await asyncio.sleep(0.08 if primero == "PRODUCTO 1" else 0.01)
        return _respuesta_para(prompt), 100, 50

    monkeypatch.setattr(convertidor_ai, "_ask_claude", fake_ask)
    _sin_log(monkeypatch)

    res = asyncio.run(generar_descripciones(_items(3 * _CHUNK_SIZE), db=None, user_id=1))

    ids = [s["row_id"] for s in res["suggestions"]]
    assert ids == list(range(1, 3 * _CHUNK_SIZE + 1))
    assert all(s["descripcion"] == f"Desc PRODUCTO {s['row_id']}" for s in res["suggestions"])


def test_un_chunk_que_falla_no_tira_a_los_demas(monkeypatch):
    async def fake_ask(_system, prompt, **_kw):
        if "PRODUCTO 21" in _nombres_del_prompt(prompt):
            raise RuntimeError("boom")
        return _respuesta_para(prompt), 100, 50

    monkeypatch.setattr(convertidor_ai, "_ask_claude", fake_ask)
    _sin_log(monkeypatch)

    res = asyncio.run(generar_descripciones(_items(3 * _CHUNK_SIZE), db=None, user_id=1))

    assert res["failed_row_ids"] == list(range(_CHUNK_SIZE + 1, 2 * _CHUNK_SIZE + 1))
    assert [s["row_id"] for s in res["suggestions"]] == (
        list(range(1, _CHUNK_SIZE + 1)) + list(range(2 * _CHUNK_SIZE + 1, 3 * _CHUNK_SIZE + 1))
    )
    assert res["errores"] == ["RuntimeError: boom"]


def test_el_uso_se_registra_una_vez_por_chunk_que_anduvo(monkeypatch):
    async def fake_ask(_system, prompt, **_kw):
        if "PRODUCTO 41" in _nombres_del_prompt(prompt):
            raise RuntimeError("boom")
        return _respuesta_para(prompt), 111, 22

    registros = []

    async def fake_log(db, user_id, feature, _provider, _model, in_tok, out_tok):
        registros.append((user_id, feature, in_tok, out_tok))

    monkeypatch.setattr(convertidor_ai, "_ask_claude", fake_ask)
    monkeypatch.setattr(convertidor_ai, "log_ai_usage", fake_log)

    asyncio.run(generar_descripciones(_items(3 * _CHUNK_SIZE), db=None, user_id=7))

    assert registros == [(7, "convertidor_descripciones", 111, 22)] * 2


def test_un_json_cortado_falla_solo_ese_chunk(monkeypatch):
    async def fake_ask(_system, prompt, **_kw):
        if "PRODUCTO 1" in _nombres_del_prompt(prompt):
            return '{"descripciones": {"1": "Desc', 100, 50  # cortado por max_tokens
        return _respuesta_para(prompt), 100, 50

    monkeypatch.setattr(convertidor_ai, "_ask_claude", fake_ask)
    _sin_log(monkeypatch)

    res = asyncio.run(generar_descripciones(_items(2 * _CHUNK_SIZE), db=None, user_id=1))

    assert res["failed_row_ids"] == list(range(1, _CHUNK_SIZE + 1))
    assert [s["row_id"] for s in res["suggestions"]] == list(range(_CHUNK_SIZE + 1, 2 * _CHUNK_SIZE + 1))
    assert len(res["errores"]) == 1 and res["errores"][0].startswith("JSONDecodeError")
