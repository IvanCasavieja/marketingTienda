"""La 0094 (26/11/2026): se borran las plantillas y los tipos de cenefa que no
son de Redexpres, y el informe de cenefas —lo que se factura— da exactamente lo
mismo antes y después. Ivan: «borres todas las plantillas de cenefas que no
sean de RedExpress. Las de RedExpress no las toques, pero el resto elimina
todos los submundos esos de cenefas porque no se van a usar».

Necesitan una base Postgres en la última migración (TEST_DATABASE_URL).
"""
import asyncio
import importlib.util
import os
import pathlib
import uuid
from datetime import date, datetime, timezone

import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")

_MIGRACION = (pathlib.Path(__file__).resolve().parent.parent
              / "migrations" / "versions" / "0094_cenefas_solo_redexpres_y_lugar_vip.py")


def _migracion():
    spec = importlib.util.spec_from_file_location("migracion_0094", _MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _corrida(slug, plantilla, cuando, filas, *, excel=None, criticos=0, verificado=False, estado="done"):
    from app.models.cenefa_job import CenefaJob

    resumen = {"total": filas, "correct": filas - criticos, "with_warnings": 1 if filas > 20 else 0,
               "critical_errors": criticos}
    return CenefaJob(
        status=estado, format="a4", export_type="pptx", row_count=filas, error_count=criticos,
        validation_report={"summary": resumen}, created_at=cuando, completed_at=cuando, verificado=verificado,
        template_id=plantilla.id if plantilla else None, template_nombre=plantilla.name if plantilla else None,
        excel_nombre=excel, categoria=slug,
    )


async def _todo_el_informe(db, plantilla_a4: str) -> dict:
    """El informe como lo pide la pantalla y sus descargas, para varios períodos."""
    from app.services.cenefas import informe

    periodos = {
        "sin_filtros": {}, "desde_2025": {"desde": date(2025, 1, 1)},
        "agosto": {"desde": date(2026, 8, 1), "hasta": date(2026, 8, 31)},
        "una_plantilla": {"template": plantilla_a4}, "otro_costo": {"costo": 60.0},
    }
    salida = {}
    for clave, filtro in periodos.items():
        filas = await informe.detalle(db, limite=100000, **filtro)
        salida[clave] = {"resumen": await informe.resumen(db, **filtro), "detalle": filas,
                         "intentos": informe.agrupar_intentos(filas)}
    salida["plantillas"] = await informe.plantillas_del_historial(db)
    return salida


def test_quedan_solo_las_de_redexpres_y_el_informe_da_lo_mismo():
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.models.cenefa_destino import CenefaDestino, CenefaDestinoBorrado
    from app.models.cenefa_job import CenefaJob
    from app.models.cenefa_template_v2 import CenefaTemplateV2

    migracion = _migracion()
    s = uuid.uuid4().hex[:6]
    # Los tipos de los dos mundos, como en producción: el de Redexpres sin
    # costo; en Tienda Inglesa uno cobrable, el de pruebas sin costo y uno con
    # producción declarada (como Parrilla y Vinos).
    tipos = {
        f"rx_{s}": dict(nombre=f"Redexpres {s}", mundo="redexpres", cobrable=False),
        f"mega_{s}": dict(nombre=f"Mega Rompe Precios {s}", mundo="tienda_inglesa", cobrable=True),
        f"pruebas_{s}": dict(nombre=f"Pruebas {s}", mundo="tienda_inglesa", cobrable=False),
        f"parrilla_{s}": dict(nombre=f"Parrilla y Vinos {s}", mundo="tienda_inglesa", cobrable=True,
                              cenefas_previas=1234, cenefas_previas_nota="Declarada en la prueba"),
    }
    rx, mega, pruebas, parrilla = tipos

    def cuando(mes, dia):
        return datetime(2026, mes, dia, 14, dia, mes, dia * 1000, tzinfo=timezone.utc)

    async def prueba():
        motor = create_async_engine(URL, poolclass=NullPool, connect_args={"statement_cache_size": 0})
        sesiones = async_sessionmaker(motor, expire_on_commit=False)
        ids_corridas, ids_plantillas = [], []
        try:
            async with sesiones() as db:
                for orden, (slug, datos) in enumerate(tipos.items()):
                    db.add(CenefaDestino(slug=slug, orden=900 + orden, **datos))
                plantillas = {}
                for slug in tipos:
                    for formato in ("A4", "3xA4"):
                        t = CenefaTemplateV2(name=f"{slug}-{formato}", definition={"components": []}, formats=["a4"],
                                             category=slug, source_pptx=b"pptx" * 5000)
                        db.add(t)
                        plantillas[slug, formato] = t
                sin_tipo = CenefaTemplateV2(name=f"sin tipo {s}", definition={}, formats=[], category=None)
                db.add(sin_tipo)
                await db.flush()
                ids_plantillas = [t.id for t in (*plantillas.values(), sin_tipo)]
                # Sin dos plantillas ni dos mundos con el mismo total en ningún
                # período: el informe los ordena por total, y entre empatados el
                # orden lo elige Postgres (puede cambiar de una consulta a otra).
                corridas = [
                    # Mega: un listado en dos formatos y reintentado, y otro aparte.
                    _corrida(mega, plantillas[mega, "A4"], cuando(8, 10), 40, excel="a.xlsx", criticos=2),
                    _corrida(mega, plantillas[mega, "3xA4"], cuando(8, 11), 40, excel="a.xlsx"),
                    _corrida(mega, plantillas[mega, "A4"], cuando(8, 12), 40, excel="a.xlsx"),
                    _corrida(mega, plantillas[mega, "A4"], cuando(10, 2), 30, excel="b.xlsx", verificado=True),
                    _corrida(pruebas, plantillas[pruebas, "A4"], cuando(9, 3), 25, excel="p.xlsx"),
                    _corrida(pruebas, plantillas[pruebas, "A4"], cuando(9, 4), 25, excel="p.xlsx"),
                    _corrida(parrilla, plantillas[parrilla, "3xA4"], cuando(7, 5), 15, excel="c.xlsx"),
                    _corrida(rx, plantillas[rx, "A4"], cuando(10, 20), 71, excel="rx.xlsx"),
                    _corrida(rx, plantillas[rx, "3xA4"], cuando(10, 21), 72, excel="rx.xlsx", verificado=True),
                    # Sin mundo: de antes de que el job lo guardara.
                    _corrida(None, None, cuando(6, 20), 9),
                    # Las que no cuentan: con error o sin confirmar.
                    _corrida(mega, plantillas[mega, "A4"], cuando(8, 13), 50, estado="error"),
                    _corrida(mega, plantillas[mega, "A4"], cuando(8, 14), 50, estado="preview"),
                ]
                db.add_all(corridas)
                await db.flush()
                ids_corridas = [c.id for c in corridas]
                await db.commit()

            async with sesiones() as db:
                antes = await _todo_el_informe(db, f"{mega}-A4")

            async with motor.begin() as conn:
                await conn.run_sync(migracion.guardar_y_borrar)

            async with sesiones() as db:
                despues = await _todo_el_informe(db, f"{mega}-A4")
                quedan = (await db.execute(select(CenefaTemplateV2.name).where(
                    CenefaTemplateV2.id.in_(ids_plantillas)))).scalars().all()
                vivos = set((await db.execute(select(CenefaDestino.slug))).scalars())
                borrados = {b.slug: b for b in (await db.execute(select(CenefaDestinoBorrado).where(
                    CenefaDestinoBorrado.slug.in_(tipos)))).scalars()}
                corridas = {c.id: c for c in (await db.execute(select(CenefaJob).where(
                    CenefaJob.id.in_(ids_corridas)))).scalars()}

            # Quedan solo las de Redexpres, y sus tipos.
            assert sorted(quedan) == [f"{rx}-3xA4", f"{rx}-A4"]
            assert rx in vivos and "redexpres" in vivos
            assert not vivos & {mega, pruebas, parrilla}
            assert set(borrados) == {mega, pruebas, parrilla}
            assert borrados[pruebas].cobrable is False and borrados[mega].cobrable is True
            assert borrados[parrilla].cenefas_previas == 1234

            # Las corridas siguen todas; las de Tienda Inglesa, sin plantilla.
            assert len(corridas) == len(ids_corridas)
            for c in corridas.values():
                if c.categoria == rx:
                    assert c.template_id is not None
                else:
                    assert c.template_id is None and (c.categoria is None or c.template_nombre)

            # El informe da exactamente lo mismo, período por período.
            for clave in antes:
                assert despues[clave] == antes[clave], clave

            # Y no es lo mismo por vacío: cada mundo con su nombre, si se cobra y su plata.
            r = despues["sin_filtros"]["resumen"]
            por_mundo = {m["mundo"]: m for m in r["por_mundo"]}
            assert por_mundo[mega]["nombre"] == f"Mega Rompe Precios {s}" and por_mundo[mega]["cobrable"] is True
            assert por_mundo[mega]["corridas"] == 4 and por_mundo[mega]["cenefas"] == 150
            assert por_mundo[mega]["costo"] == 150 * 49 and por_mundo[mega]["cenefas_reales"] == 40 * 2 + 30
            assert por_mundo[pruebas]["nombre"] == f"Pruebas {s}"
            assert por_mundo[pruebas]["cobrable"] is False and por_mundo[pruebas]["costo"] == 0
            assert por_mundo[parrilla]["cobrable"] is True and por_mundo[parrilla]["costo"] == 15 * 49
            assert por_mundo[rx]["cobrable"] is False
            declarada = next(d for d in r["declaradas"] if d["mundo"] == parrilla)
            assert declarada["cenefas"] == 1234 and declarada["costo"] == 1234 * 49
            assert declarada["nombre"] == f"Parrilla y Vinos {s}" and declarada["nota"] == "Declarada en la prueba"
        finally:
            async with sesiones() as db:
                await db.execute(delete(CenefaJob).where(CenefaJob.id.in_(ids_corridas)))
                await db.execute(delete(CenefaTemplateV2).where(CenefaTemplateV2.id.in_(ids_plantillas)))
                await db.execute(delete(CenefaDestino).where(CenefaDestino.slug.in_(tipos)))
                await db.execute(delete(CenefaDestinoBorrado).where(CenefaDestinoBorrado.slug.in_(tipos)))
                await db.commit()
            await motor.dispose()

    asyncio.run(prueba())


def test_un_mundo_borrado_desde_la_pantalla_no_cambia_el_informe():
    """Antes, borrar un tipo de cenefa (con el tacho del selector) cambiaba el
    informe: su nombre pasaba a ser el slug y sus corridas, aunque fueran de
    pruebas, pasaban a cobrarse."""
    from sqlalchemy import select

    from app.models.cenefa_destino import CenefaDestinoBorrado
    from app.services.cenefas import informe
    from test_tablero_agencia_api import Cliente, _persona, correr

    async def prueba(d):
        jefa = Cliente(d.http, await _persona(d, "Jefa Cenefas", permisos=("cenefas.view", "cenefas.edit")))
        nombre = f"Pruebas de pantalla {d.sufijo}"
        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "cobrable": False,
                                                                 "mundo": "tienda_inglesa"})
        assert r.status_code == 201, r.text
        slug = r.json()["slug"]
        async with d.Sesion() as s:
            s.add(_corrida(slug, None, datetime(2026, 11, 20, 10, tzinfo=timezone.utc), 12, excel="x.xlsx"))
            await s.commit()
        async with d.Sesion() as s:
            antes = await informe.resumen(s)

        assert (await jefa.delete(f"/tools/cenefas/v2/destinos/{slug}")).status_code == 204

        async with d.Sesion() as s:
            despues = await informe.resumen(s)
            guardado = await s.get(CenefaDestinoBorrado, slug)
        assert despues == antes
        fila = next(m for m in despues["por_mundo"] if m["mundo"] == slug)
        assert fila["nombre"] == nombre and fila["cobrable"] is False and fila["costo"] == 0
        assert guardado is not None and guardado.cobrable is False
        tipos = (await jefa.get("/tools/cenefas/v2/destinos", params={"mundo": "tienda_inglesa"})).json()
        assert slug not in {t["slug"] for t in tipos}
        # Volver a crearlo sin tildar la casilla (cobrable) pasaba a cobrar sus
        # corridas viejas: no se deja, y se dice qué hacer (Ramiro, 26/11/2026).
        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "mundo": "tienda_inglesa"})
        assert r.status_code == 409, r.text
        assert "tildá «No suma al informe de producción»" in r.json()["detail"]
        async with d.Sesion() as s:
            assert await informe.resumen(s) == antes
        # Sin costo, como era, sí: lo continúa, y lo facturado no se mueve ni al
        # crearlo ni al volver a borrarlo.
        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "cobrable": False,
                                                                 "mundo": "tienda_inglesa"})
        assert r.status_code == 201, r.text
        assert r.json()["slug"] == slug
        async with d.Sesion() as s:
            assert await informe.resumen(s) == antes
        assert (await jefa.delete(f"/tools/cenefas/v2/destinos/{slug}")).status_code == 204
        async with d.Sesion() as s:
            assert await informe.resumen(s) == antes
            assert (await s.execute(select(CenefaDestinoBorrado.cobrable).where(
                CenefaDestinoBorrado.slug == slug))).scalar_one() is False

    correr(prueba)


def test_volver_a_crear_un_tipo_cobrable_como_sin_costo_no_se_deja():
    """Lo mismo al revés: un tipo borrado que se cobraba (Mega Rompe Precios, el
    ejemplo del propio formulario) creado de nuevo «para probar», sin costo,
    dejaba sus corridas en cero pesos. El 409 no crea nada."""
    from app.models.cenefa_destino import CenefaDestino
    from app.services.cenefas import informe
    from test_tablero_agencia_api import Cliente, _persona, correr

    async def prueba(d):
        jefa = Cliente(d.http, await _persona(d, "Jefa Cenefas", permisos=("cenefas.view", "cenefas.edit")))
        nombre = f"Mega Rompe Precios {d.sufijo}"
        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "mundo": "tienda_inglesa"})
        assert r.status_code == 201, r.text
        slug = r.json()["slug"]
        async with d.Sesion() as s:
            s.add(_corrida(slug, None, datetime(2026, 10, 2, 10, tzinfo=timezone.utc), 30, excel="m.xlsx"))
            await s.commit()
        assert (await jefa.delete(f"/tools/cenefas/v2/destinos/{slug}")).status_code == 204
        async with d.Sesion() as s:
            antes = await informe.resumen(s)
        assert next(m for m in antes["por_mundo"] if m["mundo"] == slug)["costo"] == 30 * 49

        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "cobrable": False,
                                                                 "mundo": "tienda_inglesa"})
        assert r.status_code == 409, r.text
        assert "dejá sin tildar «No suma al informe de producción»" in r.json()["detail"]
        assert nombre in r.json()["detail"]
        async with d.Sesion() as s:
            assert await s.get(CenefaDestino, slug) is None
            assert await informe.resumen(s) == antes

        # Cobrable, como era: se crea y lo facturado sigue igual.
        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "mundo": "tienda_inglesa"})
        assert r.status_code == 201, r.text
        async with d.Sesion() as s:
            assert await informe.resumen(s) == antes

    correr(prueba)


def test_compactar_en_la_migracion_nunca_la_hace_fallar(monkeypatch):
    """Compactar no es imprescindible: si la tabla está en uso o algo falla, la
    migración sigue y queda para la próxima. Y no hace fila detrás de nadie."""
    import time

    from sqlalchemy import create_engine, text

    migracion = _migracion()
    monkeypatch.setattr(migracion, "PAUSA_SEGUNDOS", 0.01)
    monkeypatch.setattr(migracion, "ESPERA_SEGUNDOS", 3.0)
    motor = create_engine(URL.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        with motor.connect() as otra, motor.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            assert migracion.compactar(conn, "tabla_que_no_existe") is False
            assert migracion.compactar(conn, "vip_mes_dimension") is True

            otra.execute(text("SELECT count(*) FROM vip_mes_dimension"))  # la tiene tomada
            t0 = time.monotonic()
            assert migracion.compactar(conn, "vip_mes_dimension") is False
            assert time.monotonic() - t0 < 10, "no se quedó esperando"
            otra.rollback()

            # En una base sin nada no hay nada que valga la pena (ni se espera a nadie).
            xid = conn.execute(text("SELECT txid_current()")).scalar()
            monkeypatch.setattr(migracion, "A_COMPACTAR", ("vip_mes_dimension",))
            assert migracion.compactar_lo_que_vale_la_pena(conn, xid) == []
            monkeypatch.setattr(migracion, "MINIMO_A_COMPACTAR", 0)
            assert migracion.compactar_lo_que_vale_la_pena(conn, xid) == ["vip_mes_dimension"]
    finally:
        motor.dispose()


def test_volver_a_crear_un_tipo_borrado_conserva_su_nombre():
    """Un tipo que se vuelve a crear continúa al borrado (mismo slug) y el
    informe muestra sus corridas con el nombre del vivo. Escrito de otra forma
    —«GRAN BRETANA» por «Gran Bretaña», que da el mismo slug— le cambiaba el
    nombre a lo ya facturado (Ramiro, 26/11/2026). Nace con el que tenía."""
    from app.services.cenefas import informe
    from test_tablero_agencia_api import Cliente, _persona, correr

    async def prueba(d):
        jefa = Cliente(d.http, await _persona(d, "Jefa Cenefas", permisos=("cenefas.view", "cenefas.edit")))
        nombre = f"Gran Bretaña {d.sufijo}"
        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": nombre, "mundo": "tienda_inglesa"})
        assert r.status_code == 201, r.text
        slug = r.json()["slug"]
        async with d.Sesion() as s:
            s.add(_corrida(slug, None, datetime(2026, 9, 3, 10, tzinfo=timezone.utc), 25, excel="g.xlsx"))
            await s.commit()
        assert (await jefa.delete(f"/tools/cenefas/v2/destinos/{slug}")).status_code == 204
        async with d.Sesion() as s:
            antes = await informe.resumen(s)
        assert next(m for m in antes["por_mundo"] if m["mundo"] == slug)["nombre"] == nombre

        r = await jefa.post("/tools/cenefas/v2/destinos", json={"nombre": f"GRAN BRETANA {d.sufijo}",
                                                                 "mundo": "tienda_inglesa"})
        assert r.status_code == 201, r.text
        assert (r.json()["slug"], r.json()["nombre"]) == (slug, nombre)
        async with d.Sesion() as s:
            assert await informe.resumen(s) == antes

    correr(prueba)
