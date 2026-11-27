"""«Reintentar las que fallaron» en la Validación de RRSS (H-122, 27/11/2026).

Cuando CatTi no podía leer una placa, el lote se cerraba igual y el botón
«Reintentar las que fallaron» mandaba de nuevo esas placas: el servidor las
rechazaba todas con «Esta validación ya está cerrada» y la única salida era
rehacer la validación entera. Lo que se fija acá, contra Postgres:

- con el lote cerrado, una placa que dio error se puede volver a mirar: la
  nueva reemplaza a la anterior y, al volver a cerrar, el resumen queda al día;
- una placa nueva no se suma a un lote cerrado (400);
- una placa que ya salió bien no se reenvía (400), así no se gastan tokens
  de nuevo, y CatTi ni se entera.

La validación sigue durando 24 horas y no se guarda historial: si venció
mientras tanto, la placa dice que ya no está (test_rrss_retencion_sin_trabar).
"""
import asyncio

# El molde (la app contra la base de prueba, con una persona y una validación
# en curso) es el de la purga sin trabar: pytest pone esta carpeta en el path.
from test_rrss_retencion_sin_trabar import _con_la_app, _jpeg, con_base


def _resultado(estado: str):
    from app.services.rrss.validador import ResultadoPlaca

    return ResultadoPlaca(
        resultado={"filas": [], "tiempos_ms": {}, "error": "No se pudo leer" if estado == "error" else None},
        vista=None, ancho=20, alto=20, formato="cuadrada", estado=estado, tokens_in=10, tokens_out=2)


def _placa(http, cabeza, vid, orden: int):
    return http.post(f"/api/v1/rrss/validaciones/{vid}/imagenes", headers=cabeza,
                     files={"archivo": (f"placa{orden}.jpg", _jpeg(), "image/jpeg")}, data={"orden": str(orden)})


@con_base
def test_con_el_lote_cerrado_se_reintentan_solo_las_que_fallaron(monkeypatch):
    from app.services.rrss import validador

    # Lo que va a decir CatTi de cada placa, en orden de llamada.
    respuestas = ["error", "ok", "ok"]
    llamadas = []

    async def validar_placa(datos, nombre, mailing, cargar_paginas, config):
        llamadas.append(nombre)
        return _resultado(respuestas[len(llamadas) - 1])

    monkeypatch.setattr(validador, "validar_placa", validar_placa)

    async def prueba(http, cabeza, motor, sesiones, vid, uid):
        # Primera pasada: la placa 0 da error, la 1 sale bien, y el lote se cierra.
        assert (await _placa(http, cabeza, vid, 0)).json()["estado"] == "error"
        assert (await _placa(http, cabeza, vid, 1)).json()["estado"] == "ok"
        r = await http.post(f"/api/v1/rrss/validaciones/{vid}/cerrar", headers=cabeza)
        assert r.status_code == 200, r.text
        assert (r.json()["resumen"]["error"], r.json()["resumen"]["ok"]) == (1, 1)

        # «Reintentar las que fallaron»: la 0 se vuelve a mirar y reemplaza a la anterior.
        r = await _placa(http, cabeza, vid, 0)
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "ok"
        r = await http.post(f"/api/v1/rrss/validaciones/{vid}/cerrar", headers=cabeza)
        assert r.status_code == 200, r.text
        resumen = r.json()["resumen"]
        assert (resumen["total"], resumen["error"], resumen["ok"]) == (2, 0, 2), resumen

        detalle = (await http.get(f"/api/v1/rrss/validaciones/{vid}", headers=cabeza)).json()
        assert sorted(i["orden"] for i in detalle["imagenes"]) == [0, 1], "la placa reintentada se duplicó"
        assert detalle["estado"] == "completada"

        # Una placa nueva no se suma a un lote cerrado.
        r = await _placa(http, cabeza, vid, 2)
        assert r.status_code == 400
        assert "cerrada" in r.json()["detail"]
        # Y una que ya salió bien no se reenvía.
        r = await _placa(http, cabeza, vid, 1)
        assert r.status_code == 400
        assert "cerrada" in r.json()["detail"]
        # Un `orden` fuera del rango de la columna no llega a la base (daba 500).
        for fuera in (2**40, -1):
            r = await _placa(http, cabeza, vid, fuera)
            assert r.status_code == 422, (fuera, r.status_code, r.text)
        assert llamadas == ["placa0.jpg", "placa1.jpg", "placa0.jpg"], "CatTi miró placas que no tocaba"

    asyncio.run(_con_la_app(prueba))


@con_base
def test_mientras_el_lote_sigue_abierto_todo_anda_como_antes(monkeypatch):
    """Sin cerrar, se pueden sumar placas y reemplazar cualquiera (el navegador
    reintenta una request cortada aunque la placa hubiera salido bien)."""
    from app.services.rrss import validador

    async def validar_placa(datos, nombre, mailing, cargar_paginas, config):
        return _resultado("ok")

    monkeypatch.setattr(validador, "validar_placa", validar_placa)

    async def prueba(http, cabeza, motor, sesiones, vid, uid):
        for orden in (0, 1, 1):
            r = await _placa(http, cabeza, vid, orden)
            assert r.status_code == 200, r.text
        detalle = (await http.get(f"/api/v1/rrss/validaciones/{vid}", headers=cabeza)).json()
        assert sorted(i["orden"] for i in detalle["imagenes"]) == [0, 1]

    asyncio.run(_con_la_app(prueba))
