"""Los archivos del pedido de una tarea (0089, 24/11/2026).

Ivan: "en el brief de las tareas deberíamos poder adjuntar archivos, como el
Excel por ejemplo". Lo puro (qué se acepta) corre siempre; lo de punta a
punta con la API usa la base de TEST_DATABASE_URL, con las mismas ayudas que
test_tablero_agencia_api.py.
"""
import io
import os
import zipfile

import openpyxl
import pytest

from app.services import adjuntos as reglas

URL = os.environ.get("TEST_DATABASE_URL")


def _xlsx() -> bytes:
    wb = openpyxl.Workbook()
    wb.active.append(["codigo", "descripcion", "precioOferta"])
    wb.active.append(["97051", "Bizcochos x12", 199])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zip(archivos: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, contenido)
    return buf.getvalue()


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"x" * 64
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
EXE = b"MZ\x90\x00" + b"\x00" * 64


# ---------------------------------------------------------------------------
# Qué se acepta (puro)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre,datos,tipo", [
    ("Listado ciberlunes.xlsx", _xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("viejo.XLS", OLE, "application/vnd.ms-excel"),
    ("productos.csv", "codigo;descripción\n97051;Bizcochos\n".encode("utf-8"), "text/csv"),
    ("referencias.pdf", PDF, "application/pdf"),
    ("textos.docx", _zip({"word/document.xml": "<w/>", "[Content_Types].xml": "<x/>"}),
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("textos.doc", OLE, "application/msword"),
    ("logo.png", PNG, "image/png"),
    ("foto.jpeg", JPG, "image/jpeg"),
    ("referencias.zip", _zip({"a.txt": "hola"}), "application/zip"),
])
def test_se_aceptan_excel_csv_pdf_word_imagenes_y_zip(nombre, datos, tipo):
    assert reglas.validar(nombre, datos) == (nombre, tipo)


@pytest.mark.parametrize("nombre,datos,dice", [
    # Un programa renombrado: la extensión dice Excel, adentro no lo es.
    ("listado.xlsx", EXE, "dice ser un Excel"),
    # Un ZIP cualquiera renombrado a .xlsx tampoco.
    ("listado.xlsx", _zip({"a.txt": "hola"}), "dice ser un Excel"),
    ("listado.csv", _xlsx(), "dice ser un CSV"),
    ("foto.png", JPG, "dice ser una imagen PNG"),
    ("programa.exe", EXE, "ese tipo de archivo no se puede adjuntar"),
    ("sin extension", b"hola", "ese tipo de archivo no se puede adjuntar"),
    ("vacio.pdf", b"", "está vacío"),
])
def test_lo_que_no_es_lo_que_dice_no_pasa(nombre, datos, dice):
    with pytest.raises(ValueError, match=dice):
        reglas.validar(nombre, datos)


def test_mas_grande_que_el_tope_no_pasa_y_dice_que_hacer():
    with pytest.raises(ValueError, match="link en el detalle"):
        reglas.validar("grande.pdf", PDF + b"x" * 200, maximo=100)


def test_el_nombre_queda_sin_carpeta_ni_caracteres_raros():
    assert reglas.nombre_limpio("C:\\Users\\ivan\\Escritorio\\Listado.xlsx") == "Listado.xlsx"
    assert reglas.nombre_limpio("../../etc/listado\n.csv") == "listado.csv"
    assert reglas.nombre_limpio("  Listado   diciembre .xlsx ") == "Listado diciembre .xlsx"
    assert reglas.nombre_limpio("") == "archivo"
    largo = reglas.nombre_limpio("a" * 400 + ".xlsx")
    assert len(largo) == 255 and largo.endswith(".xlsx")


def test_adjunta_quien_gestiona_o_quien_creo_la_tarea_si_pide_piezas():
    assert reglas.puede_adjuntar(1, 2, gestiona=True, pide=False)
    assert reglas.puede_adjuntar(1, 1, gestiona=False, pide=True)
    assert not reglas.puede_adjuntar(1, 2, gestiona=False, pide=True)
    # Quien la creó pero ya no pide piezas (o una agencia: nunca pide).
    assert not reglas.puede_adjuntar(1, 1, gestiona=False, pide=False)
    assert not reglas.puede_adjuntar(1, None, gestiona=False, pide=True)


# ---------------------------------------------------------------------------
# De punta a punta, con la API y una base de verdad
# ---------------------------------------------------------------------------

if URL:
    from sqlalchemy import select

    from app.core.config import settings
    from app.models.adjuntos import CalendarioAdjunto
    from test_tablero_agencia_api import Cliente, _pedir_banners, correr

_con_base = pytest.mark.skipif(not URL, reason="Sin TEST_DATABASE_URL: estas pruebas necesitan una base Postgres")


async def _adjuntar(cliente, tarea_id, *archivos):
    return await cliente.post(f"/calendario/tareas/{tarea_id}/adjuntos", files=[
        ("archivos", (nombre, datos, "application/octet-stream")) for nombre, datos in archivos
    ])


async def _detalle(cliente, tarea_id) -> dict:
    r = await cliente.get(f"/calendario/tareas/{tarea_id}/entregas")
    assert r.status_code == 200, r.text
    return r.json()


@_con_base
def test_lucia_adjunta_el_excel_y_la_agencia_lo_ve_y_lo_baja():
    async def prueba(d):
        lucia, lider = Cliente(d.http, d.lucia), Cliente(d.http, d.lider)
        ana, bruno = Cliente(d.http, d.a1), Cliente(d.http, d.b1)
        tarea_id, _ = await _pedir_banners(d, d.lucia)
        antes = (await _detalle(lucia, tarea_id))["huella"]
        excel = _xlsx()

        r = await _adjuntar(lucia, tarea_id, ("Listado ciberlunes.xlsx", excel))
        assert r.status_code == 201, r.text
        [adj] = r.json()["adjuntos"]
        assert adj["nombre"] == "Listado ciberlunes.xlsx" and adj["tamano"] == len(excel)
        assert adj["puedoSacar"]
        # La tarjeta abierta se entera sola: la huella cambió.
        sigue = await lucia.get(f"/calendario/tareas/{tarea_id}/entregas", params={"huella": antes})
        assert not sigue.json().get("sinCambios")

        # La agencia de la pieza lo ve en la tarjeta y lo baja, con su nombre.
        det = await _detalle(ana, tarea_id)
        assert [a["nombre"] for a in det["adjuntos"]] == ["Listado ciberlunes.xlsx"]
        assert det["puedoAdjuntar"] is False and det["adjuntos"][0]["puedoSacar"] is False
        r = await ana.get(f"/calendario/adjuntos/{adj['id']}")
        assert r.status_code == 200, r.text
        assert r.content == excel
        assert "Listado%20ciberlunes.xlsx" in r.headers["content-disposition"]
        assert r.headers["x-content-type-options"] == "nosniff"
        # Otra agencia, ni sabe que existe.
        assert (await bruno.get(f"/calendario/adjuntos/{adj['id']}")).status_code == 404
        assert (await bruno.get(f"/calendario/tareas/{tarea_id}/adjuntos")).status_code == 404

        # La agencia no adjunta al pedido ni saca nada.
        assert (await _adjuntar(ana, tarea_id, ("otro.csv", b"a;b\n"))).status_code == 403
        assert (await ana.delete(f"/calendario/adjuntos/{adj['id']}")).status_code == 403
        # Alguien del equipo que no la pidió ni gestiona tareas, tampoco.
        aprob = Cliente(d.http, d.aprob2)
        assert (await _adjuntar(aprob, tarea_id, ("otro.csv", b"a;b\n"))).status_code == 403

        # Quien gestiona las tareas lo saca; ya no está para nadie.
        r = await lider.delete(f"/calendario/adjuntos/{adj['id']}")
        assert r.status_code == 200, r.text
        assert (await _detalle(ana, tarea_id))["adjuntos"] == []
        assert (await ana.get(f"/calendario/adjuntos/{adj['id']}")).status_code == 404
    correr(prueba)


@_con_base
def test_los_topes_y_los_tipos_se_controlan_en_el_servidor(monkeypatch):
    async def prueba(d):
        lucia = Cliente(d.http, d.lucia)
        tarea_id, _ = await _pedir_banners(d, d.lucia)

        # Un programa renombrado a .xlsx no pasa, y no se guarda nada.
        r = await _adjuntar(lucia, tarea_id, ("bien.csv", b"a;b\n"), ("listado.xlsx", EXE))
        assert r.status_code == 422 and "dice ser un Excel" in r.json()["detail"]
        r = await _adjuntar(lucia, tarea_id, ("programa.exe", EXE))
        assert r.status_code == 422 and "no se puede adjuntar" in r.json()["detail"]
        async with d.Sesion() as s:
            assert (await s.execute(select(CalendarioAdjunto).where(CalendarioAdjunto.tarea_id == tarea_id))).first() is None

        # Más pesado que el tope por archivo.
        monkeypatch.setattr(reglas, "MAX_BYTES_ADJUNTO", 1000)
        r = await _adjuntar(lucia, tarea_id, ("referencias.pdf", PDF + b"x" * 2000))
        assert r.status_code == 422 and "lo máximo por archivo" in r.json()["detail"]
        monkeypatch.undo()

        # Hasta 5 por tarea.
        r = await _adjuntar(lucia, tarea_id, *[(f"lista {i}.csv", f"a;{i}\n".encode()) for i in range(4)])
        assert r.status_code == 201, r.text
        r = await _adjuntar(lucia, tarea_id, ("quinto.csv", b"a;5\n"), ("sexto.csv", b"a;6\n"))
        assert r.status_code == 422 and "podés sumar 1 más" in r.json()["detail"]
        assert (await _adjuntar(lucia, tarea_id, ("quinto.csv", b"a;5\n"))).status_code == 201

        # Entre todos, el tope de los adjuntos: no se guarda y se dice qué hacer.
        otra, _ = await _pedir_banners(d, d.lucia)
        monkeypatch.setattr(settings, "ADJUNTOS_TOPE_MB", 1)
        r = await _adjuntar(lucia, otra, ("grande.csv", b"a;b\n" * 300_000))
        assert r.status_code == 507 and "avisale a quien administra" in r.json()["detail"]
    correr(prueba)


@_con_base
def test_cada_tarea_tiene_sus_archivos():
    # 0090: una tarea = un pedido. Ya no hay tarea de afuera de la que una
    # pieza herede el Excel: cada una tiene los suyos (si se piden dos cosas
    # juntas, la pantalla sube el archivo a cada una).
    async def prueba(d):
        lider, ana, bruno = (Cliente(d.http, u) for u in (d.lider, d.a1, d.b1))
        banners, _ = await _pedir_banners(d, d.lider)
        otra, _ = await _pedir_banners(d, d.lider, agencia=f"Estudio Sur {d.sufijo}")
        r = await _adjuntar(lider, banners, ("Listado.xlsx", _xlsx()))
        assert r.status_code == 201, r.text
        adj = r.json()["adjuntos"][0]["id"]
        assert [a["id"] for a in (await _detalle(ana, banners))["adjuntos"]] == [adj]
        assert (await _detalle(lider, otra))["adjuntos"] == []
        # La otra agencia no lo baja ni diciendo que mira desde su tarjeta.
        assert (await bruno.get(f"/calendario/adjuntos/{adj}", params={"desde": otra})).status_code == 404
    correr(prueba)
