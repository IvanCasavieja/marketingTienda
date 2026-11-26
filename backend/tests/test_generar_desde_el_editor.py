"""Generar cenefas con una plantilla del editor, de punta a punta con la API y
una base de verdad (H-008, 26/11/2026).

La pantalla de Generar del editor (/materiales/cenefas/v2/generar) terminaba
siempre en «Error en la generación — Error desconocido» y la corrida quedaba
«Esperando confirmación» en el Historial. El servidor no fallaba: desde el
14/07/2026 genera en dos tiempos --la corrida queda lista para revisar
("preview") y el archivo se arma recién cuando alguien confirma-- y la
pantalla no lo entendía. Ahora el paso 3 es la revisión de una corrida
(PreviewStep), y esto fija lo que esa revisión necesita del servidor:

- la corrida llega a "preview" con lo que dibuja el lienzo (la definición y
  los datos de la primera fila del Excel), aunque la plantilla no tenga PPTX
  de origen, como las que se arman en el editor, y aunque tenga un cuadro
  sumado a mano;
- al confirmarla termina en "done" y el archivo se baja; confirmarla de nuevo
  da 409 (por eso «Descargar de nuevo» no vuelve a confirmar);
- si falla, el motivo viaja en validation_report.error, que es lo que la
  pantalla muestra en vez de «Error desconocido».

Necesita una base Postgres en la última migración (TEST_DATABASE_URL); sin
ella se saltea. Todo corre adentro de una transacción que se deshace al final.
"""
import asyncio
import io
import os
import uuid
from datetime import datetime, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

if URL:
    import httpx
    import openpyxl
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.database import get_db
    from app.core.rate_limit import limiter
    from app.core.security import create_access_token, hash_password
    from app.main import app
    from app.models.user import User
    from app.services.cenefas import jobs

API = "/api/v1/tools/cenefas"
PERMISOS_CENEFAS = ["cenefas.view", "cenefas.generate", "cenefas.edit"]


def correr(prueba):
    asyncio.run(_correr(prueba))


async def _correr(prueba):
    engine = create_async_engine(URL, poolclass=NullPool, connect_args={"statement_cache_size": 0})
    conn = await engine.connect()
    trans = await conn.begin()
    Sesion = async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

    async def get_db_de_prueba():
        async with Sesion() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = get_db_de_prueba
    # La corrida se arma y se genera en segundo plano, con sesiones propias
    # (ver jobs.py): que lean y escriban en esta misma base de prueba.
    sesiones_antes = jobs.AsyncSessionLocal
    jobs.AsyncSessionLocal = Sesion
    limite_antes = limiter.enabled
    limiter.enabled = False
    try:
        async with Sesion() as s:
            persona = User(
                email=f"equipo.{uuid.uuid4().hex[:8]}@prueba-cenefas.test", full_name="Equipo Cenefas",
                hashed_password=hash_password("Clave-de-prueba-1"), permissions=PERMISOS_CENEFAS,
                mundos=["tienda_inglesa"], is_active=True, must_change_password=False,
                password_changed_at=datetime.now(timezone.utc),
            )
            s.add(persona)
            await s.commit()
        headers = {"Authorization": f"Bearer {create_access_token(persona.id)}"}
        # Las tareas en segundo plano corren dentro del mismo pedido: cuando
        # vuelve la respuesta, la corrida ya avanzó lo que tenía que avanzar.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as http:
            await prueba(http, headers)
    finally:
        limiter.enabled = limite_antes
        jobs.AsyncSessionLocal = sesiones_antes
        app.dependency_overrides.pop(get_db, None)
        await trans.rollback()
        await conn.close()
        await engine.dispose()


def _cuadro_sumado_en_el_editor(z_index: int) -> dict:
    """Un «Precio oferta» del panel de componentes, tal como lo arma el editor
    (ComponentPanel.tsx): un cuadro que no viene de ningún PPTX."""
    return {
        "id": str(uuid.uuid4()), "type": "text", "name": "Precio oferta",
        "variable": "precioOferta", "transform": "price_full",
        "style": {"font_size": 72, "font_bold": True, "color": "#E31E24", "align": "center"},
        "base_bounds": {"x": 1, "y": 8, "width": 8, "height": 3.5},
        "format_overrides": {}, "z_index": z_index, "locked": False, "visible": True,
    }


async def _plantilla_del_editor(http, headers, *, sumar_cuadro: bool) -> tuple[str, dict]:
    """Lo que guarda el editor al elegir «Cenefa A4» (y, si se pide, sumarle un
    cuadro) y tocar Guardar: la definición, sin el PPTX de origen y sin tipo
    de cenefa. Devuelve el id y la definición que se mandó."""
    r = await http.get(f"{API}/v2/builtin-definitions", headers=headers)
    assert r.status_code == 200, r.text
    a4 = next(d for d in r.json() if d["slug"] == "a4")
    definicion = {**a4["definition"], "name": "Cenefa A4 del editor"}
    if sumar_cuadro:
        cuadros = definicion["components"]
        definicion["components"] = [*cuadros, _cuadro_sumado_en_el_editor(len(cuadros) + 1)]
    r = await http.post(f"{API}/v2/templates", headers=headers, json=definicion)
    assert r.status_code == 201, r.text
    return r.json()["id"], definicion


async def _excel_de_ejemplo(http, headers) -> bytes:
    """El de «Descargar plantilla Excel», que sirve tal cual para generar."""
    r = await http.get(f"{API}/template", headers=headers, params={"destino": "cenefas"})
    assert r.status_code == 200, r.text
    return r.content


async def _generar(http, headers, excel: bytes, **plantilla) -> str:
    r = await http.post(f"{API}/v2/jobs", headers=headers,
                        files={"excel": ("plantilla_cenefas.xlsx", excel)},
                        data={"format_id": "a4", "vigencia": "", "usar_legales": "false", "legales": "", **plantilla})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


async def _corrida(http, headers, job_id: str) -> dict:
    r = await http.get(f"{API}/v2/jobs/{job_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# Los pasos del recorrido del 26/11 (proceso P34): «Cenefa A4», sumar un
# cuadro, Guardar y Generar con el Excel de ejemplo. Y la plantilla tal cual.
@pytest.mark.parametrize("sumar_cuadro", [False, True], ids=["tal_cual", "con_un_cuadro_sumado"])
def test_la_corrida_del_editor_queda_para_revisar_y_termina_al_confirmar(sumar_cuadro):
    async def prueba(http, headers):
        plantilla, definicion = await _plantilla_del_editor(http, headers, sumar_cuadro=sumar_cuadro)
        excel = await _excel_de_ejemplo(http, headers)

        r = await http.post(f"{API}/v2/validate", headers=headers,
                            files={"excel": ("plantilla_cenefas.xlsx", excel)},
                            data={"template_id": plantilla, "usar_legales": "false"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ok" and r.json()["total_rows"] > 0

        job_id = await _generar(http, headers, excel, template_id=plantilla)
        corrida = await _corrida(http, headers, job_id)
        # Lo que la pantalla leía como «Error desconocido»: no es un error, es
        # la corrida lista para revisar, con lo que necesita el lienzo.
        assert corrida["status"] == "preview", corrida.get("validation_report")
        assert "validation_report" not in corrida
        assert corrida["template_id"] == plantilla
        ids_de_la_revision = {c["id"] for c in corrida["template_def"]["components"]}
        assert ids_de_la_revision and ids_de_la_revision >= {c["id"] for c in definicion["components"]}, (
            "la revisión muestra todos los cuadros, también el sumado a mano")
        assert corrida["preview_product"].get("descripcion"), "el lienzo muestra la primera fila del Excel"
        assert corrida["hoja"]["ancho_cm"] > 0 and corrida["hoja"]["alto_cm"] > 0

        # «Confirmar y descargar» de la revisión.
        r = await http.post(f"{API}/v2/jobs/{job_id}/confirm", headers=headers, json={"components": []})
        assert r.status_code == 202, r.text
        corrida = await _corrida(http, headers, job_id)
        assert corrida["status"] == "done", corrida.get("validation_report")

        r = await http.get(f"{API}/v2/jobs/{job_id}/download", headers=headers)
        assert r.status_code == 200, r.text
        assert r.content[:2] == b"PK", "un PPTX es un ZIP"
        assert "Cenefa A4 del editor" in r.headers["content-disposition"]

        # Una corrida confirmada no se confirma dos veces: «Descargar de
        # nuevo» tiene que volver a pedir el archivo, no confirmar.
        r = await http.post(f"{API}/v2/jobs/{job_id}/confirm", headers=headers, json={"components": []})
        assert r.status_code == 409, r.text

    correr(prueba)


def test_si_la_corrida_falla_el_motivo_viaja_para_mostrarlo():
    """El listado de gestión sin pasar por el Convertidor: con una plantilla
    predeterminada no hay paso de validación, así que el freno llega en la
    corrida, y la pantalla tiene que poder decir por qué."""
    gestion = openpyxl.Workbook()
    gestion.active.append(["CODIGO", "SECCION", "NOMBREARTICULO", "MONEDA", "PRECIO", "OFERTA"])
    gestion.active.append(["97051", 21, ".BIZCOCHOS 12 UNS.", "$", 199, "Precio fijo"])
    buf = io.BytesIO()
    gestion.save(buf)

    async def prueba(http, headers):
        job_id = await _generar(http, headers, buf.getvalue(), builtin_slug="a4")
        corrida = await _corrida(http, headers, job_id)
        assert corrida["status"] == "error"
        assert "Convertidor de Excel" in corrida["validation_report"]["error"]

    correr(prueba)
