"""Don Tino lee el tablero y los pedidos de Redexpres, con una base de verdad.

Ivan (25/11/2026): "fijarse que Don Tino pueda manejar toda la app". Las dos
herramientas nuevas (app/services/don_tino_consultas.py) son de solo lectura
y ven lo mismo que la pantalla de quien pregunta: una agencia, solo sus
tarjetas; un local, solo su pedido.

Necesita TEST_DATABASE_URL; corre adentro de una transacción que se deshace.
"""
import asyncio
import json
import os
import uuid

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

if URL:
    from test_tablero_agencia_api import JPEG, Cliente, _pedir_banners, correr

    from app.services import don_tino_consultas as dtc


def _leer(salida: str) -> dict:
    return json.loads(salida)


async def _tablero(d, usuario, **args):
    async with d.Sesion() as s:
        return _leer(await dtc.tablero(usuario, args, s, hoy=d.hoy))


def test_el_tablero_que_ve_cada_uno():
    async def prueba(d):
        # Una para Pampa (la entrega Ana: queda para revisar) y otra para Sur.
        pampa, _ = await _pedir_banners(d, d.lider)
        r = await Cliente(d.http, d.lider).put(f"/calendario/tareas/{pampa}/entregas", json={
            "tipoPieza": "banner", "aprobadores": [d.lider.id], "fases": [{"nombre": "Entrega"}]})
        assert r.status_code == 200, r.text
        archivos = [("imagenes", ("a.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg"))]
        r = await Cliente(d.http, d.a1).post(f"/calendario/tareas/{pampa}/versiones",
                                             data={"versionId": f"ve-dt-{d.sufijo}"}, files=archivos)
        assert r.status_code == 201, r.text
        sur, _ = await _pedir_banners(d, d.lider, tarea_id=f"ta-{uuid.uuid4().hex[:10]}",
                                      agencia=f"Estudio Sur {d.sufijo}")

        # El equipo ve las dos, con en qué está cada una y su link.
        todo = await _tablero(d, d.lider, texto=d.sufijo)
        por_link = {t["link"]: t for t in todo["tarjetas"]}
        assert {f"/entregas?tarea={pampa}", f"/entregas?tarea={sur}"} <= set(por_link)
        en_revision = por_link[f"/entregas?tarea={pampa}"]
        assert en_revision["columna"] == "Esperando feedback" and en_revision["le_toca"].startswith("revisar la ronda 1")
        assert por_link[f"/entregas?tarea={sur}"]["le_toca"].startswith("entregar")

        # "¿Qué me toca revisar?": la de Pampa (él es el aprobador).
        revisar = await _tablero(d, d.lider, para_mi="revisar", texto=d.sufijo)
        assert [t["link"] for t in revisar["tarjetas"]] == [f"/entregas?tarea={pampa}"]
        # Por agencia.
        solo_sur = await _tablero(d, d.lider, la_hace="Estudio Sur", texto=d.sufijo)
        assert [t["link"] for t in solo_sur["tarjetas"]] == [f"/entregas?tarea={sur}"]

        # Una agencia: solo lo suyo, nunca lo de otra.
        ana = await _tablero(d, d.a1)
        links = [t["link"] for t in ana["tarjetas"]]
        assert f"/entregas?tarea={pampa}" in links and f"/entregas?tarea={sur}" not in links
        assert "solo_las_suyas" in ana
        # Bruno (Sur) tiene que entregar la suya.
        bruno = await _tablero(d, d.b1, para_mi="entregar")
        assert [t["link"] for t in bruno["tarjetas"]] == [f"/entregas?tarea={sur}"]

        # Un pedido raro vuelve como error, no rompe.
        assert "error" in await _tablero(d, d.lider, columna="cualquiera")
        assert "error" in await _tablero(d, d.lider, mundo="un_mundo_que_no_existe")

    correr(prueba)


def test_los_pedidos_de_redexpres():
    async def prueba(d):
        from app.api.routes.redexpres import LOCALES
        from app.models.local_asignacion import LocalAsignacion
        from app.models.planilla_pedido import PlanillaPedido

        uno, dos = LOCALES[0], LOCALES[1]
        async with d.Sesion() as s:
            s.add_all([
                PlanillaPedido(local_nombre=uno, year=2030, month=3, confirmado=True),
                PlanillaPedido(local_nombre=dos, year=2030, month=3, confirmado=False),
                LocalAsignacion(user_id=d.a2.id, local_nombre=dos),  # cualquier cuenta sirve como "local"
            ])
            await s.commit()

        async def pedidos(usuario, **args):
            async with d.Sesion() as s:
                return _leer(await dtc.pedidos_redexpres(usuario, {"anio": 2030, "mes": 3, **args}, s))

        # Quien tiene la planilla: todos los locales del mes.
        gestor = await pedidos(d.promo)
        assert gestor["abierto"] and gestor["confirmados"] == 1 and gestor["sin_confirmar"] == 1
        assert dos in gestor["locales_sin_confirmar"]
        # Un local: solo el suyo.
        suyo = await pedidos(d.a2)
        assert suyo["locales"] == 1 and suyo["locales_sin_confirmar"] == [dos] and "solo_el_suyo" in suyo
        # Sin planilla ni local: nada.
        assert "error" in await pedidos(d.lider)
        # Un mes sin abrir.
        cerrado = await pedidos(d.promo, mes=4)
        assert cerrado["abierto"] is False
        # Un mes mal escrito.
        assert "error" in await pedidos(d.promo, mes=13)

    correr(prueba)
