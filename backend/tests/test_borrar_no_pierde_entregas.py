"""Borrar una tarea o una acción no se lleva lo que entregó la agencia (H-001).

El Escuadrón Lechuza, recorriendo la plataforma (26/11/2026): «Borrar una
acción o una tarea borra las imágenes y los ZIP que entregó la agencia», y el
aviso decía solo «Se va con ella 1 tarea» o «Borrar con sus entregas». Las
tareas cuelgan de la acción, y sus entregas de ellas, con ON DELETE CASCADE;
y las imágenes de las entregas no se borran nunca (Ivan, 19/11/2026: son el
histórico de piezas). Ahora el servidor no deja borrar una tarea, ni su
acción, si ya se entregó algo: contesta 409 diciendo cuántos archivos hay y
qué hacer en su lugar, y no toca nada.

Lo puro (qué se dice) corre siempre; lo de punta a punta usa la base de
TEST_DATABASE_URL, con las ayudas de test_tablero_agencia_api.py.
"""
import io
import os
import zipfile

import pytest

from app.services import entregas as reglas

URL = os.environ.get("TEST_DATABASE_URL")

if URL:
    from sqlalchemy import func, select

    from app.models.calendario import CalendarioBarra, CalendarioTarea
    from app.models.entregas import CalendarioEntrega, CalendarioVersion, CalendarioVersionImagen, CalendarioVersionZip
    from test_tablero_agencia_api import JPEG, Cliente, _entregar_link, _pedir_banners, correr

_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")


# ---------------------------------------------------------------------------
# Qué se le dice a quien quiere borrar (puro)
# ---------------------------------------------------------------------------

def test_sin_nada_entregado_se_puede_borrar():
    assert reglas.por_que_no_se_borra(0, 0, accion=False) is None
    assert reglas.por_que_no_se_borra(0, 0, accion=True) is None


@pytest.mark.parametrize("archivos,tiene", [
    (3, "ya tiene 3 archivos entregados"),
    (1, "ya tiene 1 archivo entregado"),
    # Solo un link: no hay archivos, pero sí una historia de rondas que se perdería.
    (0, "ya tiene entregas"),
])
def test_una_tarea_con_entregas_dice_cuantos_archivos_y_que_hacer(archivos, tiene):
    assert reglas.por_que_no_se_borra(1, archivos, accion=False) == (
        f"Esta tarea no se puede borrar: {tiene}, y lo entregado no se borra nunca porque es el histórico de "
        "las piezas. Si ya no va, dala por hecha: su tarjeta pasa a Archivado con todo lo entregado."
    )


def test_una_accion_con_entregas_dice_en_cuantas_tareas_y_quien_las_cierra():
    # Quien elimina acciones (calendario.edit) puede no gestionar tareas: se
    # le dice quién las puede dar por hechas.
    assert reglas.por_que_no_se_borra(1, 3, accion=True) == (
        "Esta acción no se puede eliminar: una de sus tareas ya tiene entregas (3 archivos), y lo entregado no "
        "se borra nunca porque es el histórico de las piezas. Si ya no va, quien gestiona las tareas la puede "
        "dar por hecha: su tarjeta pasa a Archivado con todo lo entregado."
    )
    assert reglas.por_que_no_se_borra(2, 1, accion=True).startswith(
        "Esta acción no se puede eliminar: 2 de sus tareas ya tienen entregas (1 archivo), y lo entregado"
    )
    solo_links = reglas.por_que_no_se_borra(2, 0, accion=True)
    assert "2 de sus tareas ya tienen entregas, y lo entregado" in solo_links
    assert solo_links.endswith("las puede dar por hechas: sus tarjetas pasan a Archivado con todo lo entregado.")


# ---------------------------------------------------------------------------
# De punta a punta, con la base
# ---------------------------------------------------------------------------

def _zip(archivos: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, datos in archivos.items():
            z.writestr(nombre, datos)
    return buf.getvalue()


async def _entregar_imagen_y_zip(d, tarea_id: str, version_id: str) -> None:
    """La agencia entrega una ronda con una imagen y el ZIP original (la
    imagen de adentro ya la subió el navegador: `zipYaSubidas`)."""
    archivos = [
        ("imagenes", ("pieza.jpg", JPEG, "image/jpeg")), ("miniaturas", ("m.jpg", JPEG, "image/jpeg")),
        ("zip", ("piezas navidad.zip", _zip({"pieza.jpg": JPEG}), "application/zip")),
    ]
    r = await Cliente(d.http, d.a1).post(
        f"/calendario/tareas/{tarea_id}/versiones", data={"versionId": version_id, "zipYaSubidas": "[0]"},
        files=archivos,
    )
    assert r.status_code == 201, r.text
    assert r.json()["zip"]["guardado"] is True


async def _lo_entregado_en(d, tarea_id: str) -> dict:
    """Lo que hay guardado de la tarea: ella, sus versiones, sus imágenes y sus ZIP."""
    async with d.Sesion() as s:
        de_la_tarea = CalendarioVersion.tarea_id == tarea_id

        async def cuantos(modelo, *junta):
            q = select(func.count()).select_from(modelo)
            if junta:
                q = q.join(CalendarioVersion, *junta)
            return (await s.execute(q.where(de_la_tarea))).scalar_one()

        return {
            "tarea": await s.get(CalendarioTarea, tarea_id) is not None,
            "versiones": await cuantos(CalendarioVersion),
            "imagenes": await cuantos(CalendarioVersionImagen, CalendarioVersion.id == CalendarioVersionImagen.version_id),
            "zips": await cuantos(CalendarioVersionZip, CalendarioVersion.id == CalendarioVersionZip.version_id),
        }


@_con_base
def test_una_tarea_con_imagenes_y_zip_entregados_no_se_borra():
    async def prueba(d):
        lider = Cliente(d.http, d.lider)
        tarea_id, _ = await _pedir_banners(d, d.lider)
        await _entregar_imagen_y_zip(d, tarea_id, f"ve-b1-{d.sufijo}")
        antes = await _lo_entregado_en(d, tarea_id)
        assert antes == {"tarea": True, "versiones": 1, "imagenes": 1, "zips": 1}

        r = await lider.delete(f"/calendario/tareas/{tarea_id}")
        assert r.status_code == 409, r.text
        assert r.json()["detail"].startswith("Esta tarea no se puede borrar: ya tiene 2 archivos entregados, ")
        assert await _lo_entregado_en(d, tarea_id) == antes

        # Lo que le dice que haga sí anda: darla por hecha la manda a
        # Archivado, con todo lo entregado adentro.
        r = await lider.patch(f"/calendario/tareas/{tarea_id}", json={"estado": "hecha"})
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            assert (await s.get(CalendarioEntrega, tarea_id)).archivada_at is not None
        assert await _lo_entregado_en(d, tarea_id) == antes
    correr(prueba)


@_con_base
def test_aunque_sea_solo_un_link_la_tarea_no_se_borra():
    async def prueba(d):
        tarea_id, _ = await _pedir_banners(d, d.lider)
        assert (await _entregar_link(Cliente(d.http, d.a1), tarea_id, f"ve-b2-{d.sufijo}")).status_code == 201

        r = await Cliente(d.http, d.lider).delete(f"/calendario/tareas/{tarea_id}")
        assert r.status_code == 409, r.text
        assert r.json()["detail"].startswith("Esta tarea no se puede borrar: ya tiene entregas, ")
        assert (await _lo_entregado_en(d, tarea_id))["versiones"] == 1
    correr(prueba)


@_con_base
def test_una_accion_con_una_tarea_entregada_no_se_elimina_ni_a_medias():
    async def prueba(d):
        entregada, _ = await _pedir_banners(d, d.lider)
        sin_entregar, _ = await _pedir_banners(d, d.lider)
        await _entregar_imagen_y_zip(d, entregada, f"ve-b3-{d.sufijo}")
        antes = await _lo_entregado_en(d, entregada)

        # Lucía elimina acciones (calendario.edit) aunque no gestione tareas.
        r = await Cliente(d.http, d.lucia).delete(f"/calendario/barras/{d.ciber.id}")
        assert r.status_code == 409, r.text
        assert r.json()["detail"].startswith(
            "Esta acción no se puede eliminar: una de sus tareas ya tiene entregas (2 archivos), ")
        async with d.Sesion() as s:
            assert await s.get(CalendarioBarra, d.ciber.id) is not None
            assert await s.get(CalendarioTarea, sin_entregar) is not None
        assert await _lo_entregado_en(d, entregada) == antes
    correr(prueba)


@_con_base
def test_sin_nada_entregado_se_sigue_borrando_como_siempre():
    async def prueba(d):
        # Una tarea con su tarjeta, sin nada entregado: se borra con ella.
        tarea_id, _ = await _pedir_banners(d, d.lider)
        r = await Cliente(d.http, d.lider).delete(f"/calendario/tareas/{tarea_id}")
        assert r.status_code == 200, r.text
        # Una acción cuya tarjeta todavía no recibió nada: se elimina entera.
        de_la_accion, _ = await _pedir_banners(d, d.lider, barra=d.ahora)
        r = await Cliente(d.http, d.lucia).delete(f"/calendario/barras/{d.ahora.id}")
        assert r.status_code == 200, r.text
        async with d.Sesion() as s:
            assert await s.get(CalendarioTarea, tarea_id) is None
            assert await s.get(CalendarioTarea, de_la_accion) is None
            assert await s.get(CalendarioBarra, d.ahora.id) is None
    correr(prueba)
