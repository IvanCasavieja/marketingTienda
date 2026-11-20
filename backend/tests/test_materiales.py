"""Lo que la agencia entrega en un ZIP o en un link, para la IA (19/11/2026).

Pedido de Ivan: "¿Qué pasaría si en vez de una imagen me hubieran pasado una
carpeta o un link? (…) vos directamente como plataforma ya descargués todas
las cosas, hagas todo el proceso". Lo que llega es casi siempre un ZIP, o un
link de WeTransfer o de Smash.

Todo sin red y sin disco: el ZIP se arma en memoria, el link se contesta con
un transporte simulado de httpx (`cliente_http` se pisa) y el nombre del
servidor se "resuelve" con una tabla (`_resolver` se pisa). Lo que se fija:

- del ZIP salen las imágenes y los PDF (por página), subcarpetas incluidas,
  con los nombres bien (también los de un ZIP de Windows con tildes y ñ); lo
  demás se lista por nombre; la basura de macOS y Windows ni aparece;
- un ZIP con rutas «..» o absolutas, demasiados archivos, demasiado grande o
  una bomba zip se rechaza sin reventar, y un archivo roto adentro no tira
  el resto;
- un link a la red interna (IP privada, localhost, la metadata de la nube,
  una redirección hacia ahí, o una conexión que termina ahí) no se abre;
- un link que devuelve una página web, pesa de más, tarda, redirige de más o
  no existe se ANOTA ("no se pudo abrir: …") y nunca es un error;
- WeTransfer (19/11/2026, como el botón Descargar de su página): el link
  corto se resuelve sin leer la página, prepare-download y download con la
  hash, y la descarga del `direct_link`; también los links de marca y los
  firmados de download.wetransfer.com;
- Smash (19/11/2026, Ivan: «yo bajo sin smash los links»), como su página
  para quien recibe el link: el invitado sin datos, el link, la
  transferencia, el link firmado y la descarga sin el token;
- lo que no se puede bajar sin cuenta (con contraseña, vencido, borrado,
  más pesado que el tope, que pide el mail) se anota con el porqué y no se
  baja nada;
- el tope de imágenes por entrega se respeta entre el ZIP y el link.

Y al entregar (19/11/2026), lo que el navegador no pudo mostrar del ZIP pasa
a imágenes de la ronda (`imagenes_para_la_ronda`): las páginas de los PDF y
las imágenes que no subió, en el orden del ZIP, achicadas igual que en el
navegador (1600 px y 320 la miniatura, JPEG 75, derechas y sobre blanco), y
la IA no vuelve a mirar lo que ya quedó en la ronda.
"""
from __future__ import annotations

import asyncio
import io
import json
import socket
import struct
import zipfile
import zlib

import httpx
import pytest
from PIL import Image

from app.services import materiales as m
from app.services.revision_ia import LADO_MAXIMO

TRANSFER = "1b2c3d4e5f60718293a4b5c6d7e8f901"
HASH = "a1b2c3"
DESTINATARIO = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


# ---------------------------------------------------------------------------
# Ayudas: imágenes, PDF y ZIP en memoria
# ---------------------------------------------------------------------------

def _jpeg(ancho=800, alto=600, color="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(buf, "JPEG", quality=75)
    return buf.getvalue()


def _png(ancho=400, alto=300) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), "red").save(buf, "PNG")
    return buf.getvalue()


def _pdf(paginas=2, *, clave: str | None = None) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for i in range(paginas):
        pagina = doc.new_page()
        pagina.insert_text((72, 72), f"Página {i + 1}")
    if clave:
        datos = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=clave, owner_pw=clave)
    else:
        datos = doc.tobytes()
    doc.close()
    return datos


def _zip(archivos: dict[str, bytes], *, comprimir=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED if comprimir else zipfile.ZIP_STORED) as zf:
        for nombre, datos in archivos.items():
            zf.writestr(nombre, datos)
    return buf.getvalue()


def _juntar(**kw) -> m.Juntado:
    kw.setdefault("zip_datos", None)
    kw.setdefault("zip_nombre", None)
    kw.setdefault("link", None)
    kw.setdefault("lugar", 12)
    return asyncio.run(m.juntar(**kw))


def _extraer(datos: bytes, lugar=12) -> m.Juntado:
    j = m.Juntado()
    m.extraer_del_zip(datos, j, lugar=lugar)
    return j


# ---------------------------------------------------------------------------
# El ZIP
# ---------------------------------------------------------------------------

def test_del_zip_salen_las_imagenes_y_los_pdf_y_lo_demas_se_lista():
    datos = _zip({
        "cenefa.jpg": _jpeg(), "adaptaciones/banner.png": _png(), "notas.txt": b"hola",
        "fuentes/Gotham.ttf": b"\x00" * 10, "__MACOSX/._cenefa.jpg": b"junk", ".DS_Store": b"junk",
        "adaptaciones/Thumbs.db": b"junk", "carpeta/": b"",
    })
    j = _extraer(datos)
    assert [(i.nombre, i.origen, i.pagina) for i in j.imagenes] == [
        ("cenefa.jpg", "zip", None), ("adaptaciones/banner.png", "zip", None)]
    assert j.imagenes[0].tipo_mime == "image/jpeg" and (j.imagenes[0].ancho, j.imagenes[0].alto) == (800, 600)
    assert j.imagenes[0].imagen_id is None  # no está en la base
    assert j.revisados == [{"nombre": "cenefa.jpg", "origen": "zip", "paginas": None},
                           {"nombre": "adaptaciones/banner.png", "origen": "zip", "paginas": None}]
    assert j.ignorados == ["notas.txt", "fuentes/Gotham.ttf"]
    assert j.no_se_pudo_abrir == []


def test_lo_que_el_navegador_ya_subio_como_imagen_no_se_mira_dos_veces():
    """El navegador saca las imágenes del ZIP y las sube como imágenes de la
    ronda (las ve quien aprueba); dice cuáles por su lugar en el índice del
    ZIP (contando carpetas y basura), y esas la IA no las vuelve a mirar."""
    datos = _zip({"carpeta/": b"", "a.jpg": _jpeg(), "__MACOSX/._a.jpg": b"junk", "b.png": _png(),
                  "folleto.pdf": _pdf(1)})
    assert [(e.indice, e.nombre) for e in m.inspeccionar_zip(datos)] == [(1, "a.jpg"), (3, "b.png"), (4, "folleto.pdf")]
    j = m.Juntado()
    assert m.extraer_del_zip(datos, j, lugar=12, saltar=frozenset({1, 3})) == 1
    assert [(i.nombre, i.pagina) for i in j.imagenes] == [("folleto.pdf", 1)]
    assert [r["nombre"] for r in j.revisados] == ["folleto.pdf"] and j.ignorados == []
    # Por juntar (lo que usa la revisión), igual.
    j = _juntar(zip_datos=datos, zip_nombre="piezas.zip", zip_saltar=frozenset({1}))
    assert [i.nombre for i in j.imagenes] == ["b.png", "folleto.pdf"]


def test_una_imagen_grande_del_zip_se_achica_al_lado_de_la_ia():
    j = _extraer(_zip({"grande.jpg": _jpeg(3200, 2400)}))
    assert (j.imagenes[0].ancho, j.imagenes[0].alto) == (LADO_MAXIMO, 1200)


def test_un_pdf_adentro_del_zip_va_por_paginas():
    j = _extraer(_zip({"folleto.pdf": _pdf(3), "foto.jpg": _jpeg()}))
    assert [(i.nombre, i.pagina) for i in j.imagenes] == [("folleto.pdf", 1), ("folleto.pdf", 2), ("folleto.pdf", 3), ("foto.jpg", None)]
    assert all(i.tipo_mime == "image/jpeg" and max(i.ancho, i.alto) == LADO_MAXIMO for i in j.imagenes[:3])
    assert j.revisados[0] == {"nombre": "folleto.pdf", "origen": "zip", "paginas": 3}


def test_un_pdf_largo_se_corta_en_diez_paginas_y_se_avisa():
    j = _extraer(_zip({"catalogo.pdf": _pdf(12)}))
    assert len(j.imagenes) == m.MAX_PAGINAS_PDF
    assert j.revisados == [{"nombre": "catalogo.pdf", "origen": "zip", "paginas": 10}]
    assert j.no_se_pudo_abrir == ["«catalogo.pdf»: se revisaron las primeras 10 páginas de 12 (tope de 10 páginas por PDF)"]


def test_un_pdf_con_contrasena_o_roto_se_anota_y_el_resto_sigue():
    j = _extraer(_zip({"cerrado.pdf": _pdf(1, clave="secreta"), "roto.pdf": b"%PDF-1.4 nada", "ok.jpg": _jpeg()}))
    assert [i.nombre for i in j.imagenes] == ["ok.jpg"]
    assert any("cerrado.pdf" in t and "contraseña" in t for t in j.no_se_pudo_abrir)
    assert any("roto.pdf" in t for t in j.no_se_pudo_abrir)


def test_lo_que_se_llama_jpg_pero_no_es_imagen_se_anota():
    j = _extraer(_zip({"trucho.jpg": b"esto es texto", "ok.png": _png()}))
    assert [i.nombre for i in j.imagenes] == ["ok.png"]
    assert j.no_se_pudo_abrir == ["«trucho.jpg»: no es una imagen JPG, PNG ni WebP (aunque el nombre lo diga)"]


def _con_nombre_crudo(datos: bytes, relleno: str, crudo: bytes) -> bytes:
    """Reemplaza el nombre ASCII de relleno por los bytes crudos (mismo largo:
    los offsets del ZIP no cambian) en el encabezado local y en el índice.
    Así queda como lo deja el Explorador de Windows: sin el bit de UTF-8."""
    assert len(relleno.encode("ascii")) == len(crudo)
    return datos.replace(relleno.encode("ascii"), crudo)


def test_los_nombres_con_tildes_y_enie_de_un_zip_de_windows():
    # El Explorador de Windows en español: cp850, sin marcar UTF-8.
    datos = _con_nombre_crudo(_zip({"cenefa_n.jpg": _jpeg()}), "cenefa_n.jpg", "cenefa_ñ.jpg".encode("cp850"))
    assert [e.nombre for e in m.inspeccionar_zip(datos)] == ["cenefa_ñ.jpg"]
    datos = _con_nombre_crudo(_zip({"promo_a.jpg": _jpeg()}), "promo_a.jpg", "promo_á.jpg".encode("cp850"))
    assert [e.nombre for e in m.inspeccionar_zip(datos)] == ["promo_á.jpg"]
    # Una herramienta que escribe UTF-8 sin marcarlo (zip de Linux viejo).
    datos = _con_nombre_crudo(_zip({"cenefa_nn.jpg": _jpeg()}), "cenefa_nn.jpg", "cenefa_ñ.jpg".encode("utf-8"))
    assert [e.nombre for e in m.inspeccionar_zip(datos)] == ["cenefa_ñ.jpg"]
    # Marcado como UTF-8 (7-Zip, macOS): tal cual.
    assert [e.nombre for e in m.inspeccionar_zip(_zip({"sub/año_ñ.jpg": _jpeg()}))] == ["sub/año_ñ.jpg"]
    # Con el campo extra 0x7075 (WinRAR): manda ese nombre.
    utf8 = "cenefa_ñ.jpg".encode("utf-8")
    zi = zipfile.ZipInfo("cenefa_n.jpg")
    zi.extra = struct.pack("<HHBI", 0x7075, 5 + len(utf8), 1, zlib.crc32(b"cenefa_n.jpg")) + utf8
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zi, _jpeg())
    assert [e.nombre for e in m.inspeccionar_zip(buf.getvalue())] == ["cenefa_ñ.jpg"]
    # Y de punta a punta: el nombre llega a la imagen para la IA.
    j = _extraer(_con_nombre_crudo(_zip({"cenefa_n.jpg": _jpeg()}), "cenefa_n.jpg", "cenefa_ñ.jpg".encode("cp850")))
    assert j.imagenes[0].nombre == "cenefa_ñ.jpg"


def test_un_zip_con_rutas_raras_se_rechaza_sin_reventar():
    for nombre in ("../afuera.jpg", "sub/../../afuera.jpg", "/absoluta.jpg", "C:/windows/x.jpg", "..\\arriba.jpg"):
        with pytest.raises(ValueError, match="rutas que no van"):
            m.inspeccionar_zip(_zip({nombre: _jpeg(), "ok.jpg": _jpeg()}))
    # Lo mismo desde `juntar`: se anota, no levanta.
    j = _juntar(zip_datos=_zip({"../afuera.jpg": _jpeg()}), zip_nombre="malo.zip")
    assert j.imagenes == [] and j.no_se_pudo_abrir == ["No se pudo abrir el ZIP «malo.zip»: El ZIP tiene rutas que no van (con «..» o absolutas): no se puede abrir"]


def test_lo_que_no_es_un_zip_se_rechaza():
    with pytest.raises(ValueError, match="no es un ZIP"):
        m.inspeccionar_zip(b"PK\x03\x04 esto no es un zip de verdad")
    with pytest.raises(ValueError, match="no es un ZIP"):
        m.inspeccionar_zip(_jpeg())
    with pytest.raises(ValueError, match="vacío"):
        m.inspeccionar_zip(b"")
    assert m.inspeccionar_zip(_zip({})) == []


def test_una_bomba_zip_se_rechaza_sin_reventar(monkeypatch):
    # Un archivo que se "infla" mil veces (2 MB de ceros son 2 KB comprimidos).
    with pytest.raises(ValueError, match="no parece sano"):
        m.inspeccionar_zip(_zip({"bomba.jpg": bytes(2 * 1024 * 1024)}))
    # Demasiado descomprimido en total (el tope bajado para la prueba): dos
    # "fotos" de 600 KB que no se comprimen (bytes al azar).
    import os
    monkeypatch.setattr(m, "MAX_BYTES_DESCOMPRIMIDO", 1024 * 1024)
    with pytest.raises(ValueError, match="pasa de 1 MB"):
        m.inspeccionar_zip(_zip({"a.jpg": os.urandom(600 * 1024), "b.jpg": os.urandom(600 * 1024)}, comprimir=False))
    # El ZIP mismo demasiado pesado.
    monkeypatch.setattr(m, "MAX_BYTES_ZIP", 1000)
    with pytest.raises(ValueError, match="el máximo es"):
        m.inspeccionar_zip(_zip({"a.jpg": os.urandom(2000)}))


def test_un_archivo_mas_pesado_que_el_tope_se_corta_al_leerlo(monkeypatch):
    """Aunque el índice dijera otra cosa, lo que se lee de verdad se corta."""
    monkeypatch.setattr(m, "MAX_BYTES_ARCHIVO", 50 * 1024)
    import os
    j = _extraer(_zip({"ruido.jpg": b"\xff\xd8\xff" + os.urandom(100 * 1024), "ok.jpg": _jpeg(100, 100)}))
    assert [i.nombre for i in j.imagenes] == ["ok.jpg"]
    assert j.no_se_pudo_abrir == ["«ruido.jpg»: pesa más de 0.05 MB".replace("0.05", "0.0488281")] or \
        j.no_se_pudo_abrir[0].startswith("«ruido.jpg»: pesa más de")


def test_demasiados_archivos_adentro(monkeypatch):
    monkeypatch.setattr(m, "MAX_ARCHIVOS_ZIP", 3)
    with pytest.raises(ValueError, match="demasiados archivos"):
        m.inspeccionar_zip(_zip({f"{i}.txt": b"x" for i in range(4)}))
    assert len(m.inspeccionar_zip(_zip({f"{i}.txt": b"x" for i in range(3)}))) == 3


def test_el_tope_de_imagenes_por_entrega_deja_afuera_lo_que_no_entra():
    datos = _zip({f"{i}.jpg": _jpeg(100, 100) for i in range(1, 6)})
    j = _extraer(datos, lugar=2)
    assert [i.nombre for i in j.imagenes] == ["1.jpg", "2.jpg"]
    assert j.no_se_pudo_abrir == [f"«{i}.jpg»: quedó afuera por el tope de imágenes por entrega" for i in (3, 4, 5)]
    # Un PDF cuando queda poco lugar: solo las páginas que entran.
    j = _extraer(_zip({"a.jpg": _jpeg(100, 100), "f.pdf": _pdf(4)}), lugar=3)
    assert [(i.nombre, i.pagina) for i in j.imagenes] == [("a.jpg", None), ("f.pdf", 1), ("f.pdf", 2)]
    assert j.no_se_pudo_abrir == ["«f.pdf»: se revisaron las primeras 2 páginas de 4 (tope de imágenes por entrega)"]


def _con_bit_de_cifrado(datos: bytes, nombre: str) -> bytes:
    """Prende el bit de cifrado (flag 0) de `nombre` en el encabezado local
    y en el índice: zipfile no deja escribirlo, pero sí lo respeta al leer."""
    b = bytearray(datos)
    n = nombre.encode("ascii")
    for firma, flags_en, largo_en, nombre_en in ((b"PK\x03\x04", 6, 26, 30), (b"PK\x01\x02", 8, 28, 46)):
        i = b.find(firma)
        while i != -1:
            largo = struct.unpack_from("<H", b, i + largo_en)[0]
            if b[i + nombre_en:i + nombre_en + largo] == n:
                struct.pack_into("<H", b, i + flags_en, struct.unpack_from("<H", b, i + flags_en)[0] | 0x1)
            i = b.find(firma, i + 4)
    return bytes(b)


def test_un_zip_cifrado_se_anota():
    # Un archivo con el bit de cifrado puesto: zipfile se niega a abrirlo.
    datos = _con_bit_de_cifrado(_zip({"secreto.jpg": _jpeg(50, 50), "ok.jpg": _jpeg(50, 50)}), "secreto.jpg")
    j = _extraer(datos)
    assert [i.nombre for i in j.imagenes] == ["ok.jpg"]
    assert j.no_se_pudo_abrir == ["«secreto.jpg»: está protegido con contraseña"]


# ---------------------------------------------------------------------------
# El link (red simulada)
# ---------------------------------------------------------------------------

PUBLICA = "93.184.216.34"
_NOMBRES = {
    "interno.example": ["10.0.0.5"],
    "mixto.example": [PUBLICA, "192.168.1.20"],
    "localhost": ["127.0.0.1", "::1"],
    "v6.example": ["2606:2800:220:1:248:1893:25c8:1946"],
}


class Red:
    """El transporte simulado: `rutas` es {(método, url) -> respuesta o
    función(request) -> respuesta}. Cuenta los pedidos. Cada red arranca sin
    el token de invitado de Smash guardado."""

    def __init__(self, monkeypatch, rutas=None):
        self.rutas = dict(rutas or {})
        self.pedidos: list[httpx.Request] = []
        monkeypatch.setattr(m, "cliente_http", self.cliente)
        monkeypatch.setattr(m, "_resolver", self.resolver)
        monkeypatch.setattr(m, "_TOKEN_SMASH", {})

    async def resolver(self, host):
        if host == "noexiste.example":
            raise socket.gaierror(-2, "Name or service not known")
        if host in _NOMBRES:
            return _NOMBRES[host]
        try:
            import ipaddress
            ipaddress.ip_address(host)
            return [host]
        except ValueError:
            return [PUBLICA]

    def manejar(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        clave = (request.method, str(request.url))
        if clave not in self.rutas:
            return httpx.Response(404, text="no hay nada acá")
        r = self.rutas[clave]
        return r(request) if callable(r) else r

    def cliente(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.manejar), follow_redirects=False)


def _imagen(datos=None, **cabeceras) -> httpx.Response:
    return httpx.Response(200, content=datos or _jpeg(), headers={"content-type": "image/jpeg", **cabeceras})


@pytest.mark.parametrize("url", [
    "http://10.0.0.5/pieza.jpg", "http://127.0.0.1:8000/pieza.jpg", "http://localhost/pieza.jpg",
    "http://169.254.169.254/latest/meta-data/", "http://interno.example/pieza.jpg", "https://mixto.example/pieza.jpg",
    "http://[::1]/pieza.jpg", "http://0.0.0.0/x", "http://100.64.0.1/x", "http://[::ffff:10.0.0.1]/x",
])
def test_un_link_a_la_red_interna_no_se_abre(monkeypatch, url):
    red = Red(monkeypatch, {("GET", url): _imagen()})
    j = _juntar(link=url)
    assert j.imagenes == [] and red.pedidos == []  # ni se conectó
    assert len(j.no_se_pudo_abrir) == 1 and "dirección interna" in j.no_se_pudo_abrir[0]


def test_solo_http_y_https(monkeypatch):
    red = Red(monkeypatch)
    j = _juntar(link="ftp://archivos.example/pieza.jpg")
    assert red.pedidos == [] and "http o https" in j.no_se_pudo_abrir[0]


# ---------------------------------------------------------------------------
# Revisión de seguridad del 19/11/2026: la bomba comprimida y el DNS
# ---------------------------------------------------------------------------

class _Crudo(httpx.AsyncByteStream):
    """Un cuerpo que llega de a pedazos y sin leer, como de la red: así httpx
    no lo abre solo al armar la respuesta (con content= sí lo haría)."""

    def __init__(self, datos: bytes, pedazo: int = 65536):
        self.datos, self.pedazo = datos, pedazo

    async def __aiter__(self):
        for i in range(0, len(self.datos), self.pedazo):
            yield self.datos[i:i + self.pedazo]


def _gzip(datos: bytes) -> bytes:
    c = zlib.compressobj(9, zlib.DEFLATED, 31)
    return c.compress(datos) + c.flush()


def test_una_bomba_comprimida_no_se_abre_entera(monkeypatch):
    """Unos pocos bytes comprimidos dos veces (o una capa que se infla de más)
    se comían la memoria del servidor antes de cualquier tope, porque httpx
    descomprime solo. Ahora se pide sin comprimir, se lee crudo y se abre una
    sola capa, con tope."""
    url = "https://bomba.example/pieza.jpg"
    doble = _gzip(_gzip(b"\x00" * 50_000_000))
    red = Red(monkeypatch, {("GET", url): lambda r: httpx.Response(
        200, headers={"content-encoding": "gzip, gzip", "content-type": "image/jpeg"}, stream=_Crudo(doble))})
    j = _juntar(link=url)
    assert red.pedidos[0].headers["accept-encoding"] == "identity"
    assert j.imagenes == [] and "comprimido de una forma que no se abre" in j.no_se_pudo_abrir[0]
    # Una sola capa que se infla más que el tope: se corta en el tope.
    una = _gzip(b"\x00" * (m.MAX_BYTES_LINK + 5_000_000))
    Red(monkeypatch, {("GET", url): lambda r: httpx.Response(
        200, headers={"content-encoding": "gzip", "content-type": "image/jpeg"}, stream=_Crudo(una))})
    j = _juntar(link=url)
    assert j.imagenes == [] and "pesa más de" in j.no_se_pudo_abrir[0]
    # Otra forma de comprimir (br): no se abre.
    Red(monkeypatch, {("GET", url): lambda r: httpx.Response(
        200, headers={"content-encoding": "br"}, stream=_Crudo(b"xx"))})
    assert "comprimido de una forma que no se abre" in _juntar(link=url).no_se_pudo_abrir[0]


def test_una_imagen_comprimida_una_vez_se_abre(monkeypatch):
    url = "https://comprime.example/pieza.jpg"
    Red(monkeypatch, {("GET", url): lambda r: httpx.Response(
        200, headers={"content-encoding": "gzip", "content-type": "image/jpeg"}, stream=_Crudo(_gzip(_jpeg())))})
    j = _juntar(link=url)
    assert len(j.imagenes) == 1 and j.no_se_pudo_abrir == []


def test_el_nombre_se_controla_como_lo_usa_la_conexion(monkeypatch):
    """url.host y el nombre con el que conecta httpx (raw_host, en IDNA)
    pueden ser distintos: «faß» se controlaba como «fass» y se conectaba a
    «xn--fa-hia». Con dos nombres, uno pasaba el control y el otro llevaba
    a la red interna."""
    controlados = []

    async def resolver(host):
        controlados.append(host)
        return [PUBLICA]

    monkeypatch.setattr(m, "_resolver", resolver)
    url = httpx.URL("https://faß.example/pieza.jpg")
    asyncio.run(m._host_publico(url))
    assert controlados == [url.raw_host.decode("ascii")] and controlados[0].startswith("xn--")


def test_la_conexion_va_a_la_misma_ip_que_se_controlo(monkeypatch):
    conectadas = []

    class RedFalsa:
        async def connect_tcp(self, host, port, **kw):
            conectadas.append((host, port))
            return "conexión"

    nombres = {"publico.example": [PUBLICA], "rebind.example": ["127.0.0.1"], "mixto.example": [PUBLICA, "10.0.0.1"]}

    async def resolver(host):
        return nombres[host]

    monkeypatch.setattr(m, "_resolver", resolver)
    red = m._RedPublica()
    red._red = RedFalsa()
    assert asyncio.run(red.connect_tcp("publico.example", 443)) == "conexión"
    assert conectadas == [(PUBLICA, 443)]
    for host in ("rebind.example", "mixto.example"):
        with pytest.raises(m.NoSePudoAbrir, match="dirección interna"):
            asyncio.run(red.connect_tcp(host, 443))
    assert conectadas == [(PUBLICA, 443)]  # a la interna ni se intentó


def test_el_cliente_de_los_links_usa_la_red_controlada():
    """Si una versión nueva de httpx cambiara cómo arma la conexión, que salte
    acá y no que se conecte sin el control."""
    cliente = m.cliente_http()
    try:
        assert isinstance(cliente._transport._pool._network_backend, m._RedPublica)
    finally:
        asyncio.run(cliente.aclose())


def test_un_dns_que_cambia_entre_el_control_y_la_conexion_no_llega_a_la_red_interna(monkeypatch):
    """De punta a punta, con un servidor de verdad en 127.0.0.1: el nombre da
    una IP pública al controlarlo y la interna al conectar (DNS rebinding).
    Antes el pedido llegaba al servidor interno y recién después se cortaba."""
    import threading

    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(5)
    servidor.settimeout(2)
    puerto = servidor.getsockname()[1]
    aceptadas = []

    def escuchar():
        try:
            c, _ = servidor.accept()
            aceptadas.append(1)
            c.close()
        except OSError:
            pass

    hilo = threading.Thread(target=escuchar, daemon=True)
    hilo.start()
    vueltas = []

    async def resolver(host):
        vueltas.append(host)
        return [PUBLICA] if len(vueltas) == 1 else ["127.0.0.1"]

    monkeypatch.setattr(m, "_resolver", resolver)
    j = _juntar(link=f"http://rebind.example:{puerto}/pieza.jpg")
    hilo.join(3)
    servidor.close()
    assert len(vueltas) == 2  # se controló y se volvió a controlar al conectar
    assert aceptadas == [] and "dirección interna" in j.no_se_pudo_abrir[0]


def test_el_peso_de_una_transferencia_se_redondea_para_arriba():
    # 42.000.000 bytes son 40,05 MB: no puede decir «pesa 40 MB» si el tope es 40.
    with pytest.raises(m.NoSePudoAbrir, match="pesa 41 MB"):
        m._controlar_peso(42_000_000, "Smash")


def test_un_servidor_que_no_existe_se_anota(monkeypatch):
    Red(monkeypatch)
    j = _juntar(link="https://noexiste.example/pieza.jpg")
    assert j.no_se_pudo_abrir == ["No se pudo abrir el link (noexiste.example/pieza.jpg): no se encontró el servidor noexiste.example"]


def test_un_link_que_devuelve_una_pagina_web_se_anota_y_no_falla(monkeypatch):
    Red(monkeypatch, {("GET", "https://drive.example/privado"): httpx.Response(
        200, text="<!DOCTYPE html><html><body>Iniciá sesión</body></html>", headers={"content-type": "text/html"})})
    j = _juntar(link="https://drive.example/privado")
    assert j.imagenes == [] and j.revisados == []
    assert len(j.no_se_pudo_abrir) == 1
    assert j.no_se_pudo_abrir[0].startswith("No se pudo abrir el link (drive.example/privado): el link devolvió una página web")
    assert "Pasalo como ZIP" in j.no_se_pudo_abrir[0]


def test_un_link_directo_a_una_imagen(monkeypatch):
    red = Red(monkeypatch, {("GET", "https://cdn.example/piezas/cenefa%20final.jpg"): _imagen()})
    j = _juntar(link="https://cdn.example/piezas/cenefa%20final.jpg")
    assert [(i.nombre, i.origen, i.pagina, i.imagen_id) for i in j.imagenes] == [("cenefa final.jpg", "link", None, None)]
    assert j.revisados == [{"nombre": "cenefa final.jpg", "origen": "link", "paginas": None}]
    assert j.no_se_pudo_abrir == [] and j.ignorados == []
    assert red.pedidos[0].headers["user-agent"].startswith("Mozilla/5.0")


def test_un_link_a_un_pdf_va_por_paginas(monkeypatch):
    Red(monkeypatch, {("GET", "https://cdn.example/d?id=9"): httpx.Response(
        200, content=_pdf(2), headers={"content-type": "application/pdf",
                                       "content-disposition": 'attachment; filename="folleto navidad.pdf"'})})
    j = _juntar(link="https://cdn.example/d?id=9")
    assert [(i.nombre, i.pagina) for i in j.imagenes] == [("folleto navidad.pdf", 1), ("folleto navidad.pdf", 2)]
    assert j.revisados == [{"nombre": "folleto navidad.pdf", "origen": "link", "paginas": 2}]


def test_un_link_a_un_zip(monkeypatch):
    Red(monkeypatch, {("GET", "https://cdn.example/piezas.zip"): httpx.Response(
        200, content=_zip({"a.jpg": _jpeg(), "sub/b.png": _png(), "leeme.txt": b"x"}), headers={"content-type": "application/zip"})})
    j = _juntar(link="https://cdn.example/piezas.zip")
    assert [(i.nombre, i.origen) for i in j.imagenes] == [("a.jpg", "link"), ("sub/b.png", "link")]
    assert j.ignorados == ["leeme.txt"]


def test_lo_que_no_es_imagen_pdf_ni_zip_se_anota(monkeypatch):
    Red(monkeypatch, {("GET", "https://cdn.example/pieza.psd"): httpx.Response(200, content=b"8BPS" + b"\x00" * 100)})
    j = _juntar(link="https://cdn.example/pieza.psd")
    assert "no es una imagen, un PDF ni un ZIP" in j.no_se_pudo_abrir[0]


def test_las_redirecciones_se_siguen_hasta_tres_y_cada_salto_se_controla(monkeypatch):
    red = Red(monkeypatch, {
        ("GET", "https://corto.example/x"): httpx.Response(302, headers={"location": "https://cdn.example/a"}),
        ("GET", "https://cdn.example/a"): httpx.Response(301, headers={"location": "/b/pieza.jpg"}),
        ("GET", "https://cdn.example/b/pieza.jpg"): _imagen(),
        ("GET", "https://loop.example/1"): httpx.Response(302, headers={"location": "https://loop.example/2"}),
        ("GET", "https://loop.example/2"): httpx.Response(302, headers={"location": "https://loop.example/3"}),
        ("GET", "https://loop.example/3"): httpx.Response(302, headers={"location": "https://loop.example/4"}),
        ("GET", "https://loop.example/4"): httpx.Response(302, headers={"location": "https://loop.example/5"}),
        ("GET", "https://trampa.example/x"): httpx.Response(302, headers={"location": "http://10.0.0.5/admin"}),
        ("GET", "https://sinlugar.example/x"): httpx.Response(302),
    })
    j = _juntar(link="https://corto.example/x")
    assert [i.nombre for i in j.imagenes] == ["pieza.jpg"]
    assert "redirige demasiadas veces" in _juntar(link="https://loop.example/1").no_se_pudo_abrir[0]
    antes = len(red.pedidos)
    j = _juntar(link="https://trampa.example/x")
    assert "dirección interna" in j.no_se_pudo_abrir[0] and len(red.pedidos) == antes + 1  # el salto interno no se pidió
    assert "redirige a ningún lado" in _juntar(link="https://sinlugar.example/x").no_se_pudo_abrir[0]


def test_un_archivo_mas_pesado_que_el_tope_se_corta(monkeypatch):
    monkeypatch.setattr(m, "MAX_BYTES_LINK", 1000)
    grande = _jpeg(600, 600, "blue")
    assert len(grande) > 1000
    Red(monkeypatch, {
        ("GET", "https://cdn.example/dice.jpg"): _imagen(grande, **{"content-length": str(len(grande))}),
        ("GET", "https://cdn.example/calla.jpg"): _imagen(grande),
    })
    assert "pesa más de" in _juntar(link="https://cdn.example/dice.jpg").no_se_pudo_abrir[0]
    assert "pesa más de" in _juntar(link="https://cdn.example/calla.jpg").no_se_pudo_abrir[0]


class _Conexion:
    def __init__(self, ip):
        self.ip = ip

    def get_extra_info(self, nombre):
        return (self.ip, 443) if nombre == "server_addr" else None


def test_la_ip_a_la_que_se_conecto_de_verdad_tambien_se_controla(monkeypatch):
    """Si entre resolver el nombre y conectar la respuesta de DNS cambió a una
    IP interna (DNS rebinding), se corta antes de leer nada."""
    Red(monkeypatch, {
        ("GET", "https://rebind.example/x"): httpx.Response(
            200, content=_jpeg(), extensions={"network_stream": _Conexion("10.0.0.7")}),
        ("GET", "https://sana.example/x"): httpx.Response(
            200, content=_jpeg(), extensions={"network_stream": _Conexion(PUBLICA)}),
    })
    assert "dirección interna" in _juntar(link="https://rebind.example/x").no_se_pudo_abrir[0]
    assert len(_juntar(link="https://sana.example/x").imagenes) == 1


def test_un_servidor_que_tarda_o_se_cae_se_anota(monkeypatch):
    def tarda(_request):
        raise httpx.ReadTimeout("tarde")

    def cae(_request):
        raise httpx.ConnectError("se cayó")

    Red(monkeypatch, {("GET", "https://lento.example/x"): tarda, ("GET", "https://caido.example/x"): cae})
    assert "tardó demasiado" in _juntar(link="https://lento.example/x").no_se_pudo_abrir[0]
    assert "no se pudo conectar" in _juntar(link="https://caido.example/x").no_se_pudo_abrir[0]
    Red(monkeypatch, {("GET", "https://cdn.example/x"): httpx.Response(403, text="prohibido")})
    assert "contestó 403" in _juntar(link="https://cdn.example/x").no_se_pudo_abrir[0]


@pytest.mark.parametrize("url, clase", [
    ("https://we.tl/t-AbCdEf12", "wetransfer"), ("https://go.wetransfer.com/t-AbCdEf12", "wetransfer"),
    ("https://shorturls.wetransfer.com/AbCdEf12", "wetransfer"), ("https://wetransfer.com/downloads/a1/b2", "wetransfer"),
    ("https://WWW.WeTransfer.com/downloads/a1/b2", "wetransfer"),
    ("https://tiendainglesa.wetransfer.com/downloads/a1/b2", "wetransfer"),  # una página de marca
    ("https://download.wetransfer.com/eu/archivo.zip?token=abc", "directo"),  # ya es el archivo
    ("https://fromsmash.com/AbCdEfGhIj-dt", "smash"), ("https://www.fromsmash.com/AbCdEfGhIj-dt", "smash"),
    ("https://agencia.fromsmash.com/Cenefas-Navidad", "smash"),  # el de un equipo
    ("https://link.fromsmash.co/target/x", "directo"),  # su API, no una página para compartir
    ("https://fromsmash.com.trucho.example/x", "directo"), ("https://nowetransfer.com/downloads/a1/b2", "directo"),
    ("https://cdn.example/pieza.jpg", "directo"),
])
def test_que_clase_de_link_es(url, clase):
    assert m.clase_de_link(url) == clase


def test_el_token_no_pasa_a_otro_servidor_si_el_pedido_redirige(monkeypatch):
    """Como en los navegadores: si un pedido con el token redirige a otro
    servidor, el token (y la contraseña de Smash) no viajan; dentro del
    mismo servidor, sí."""
    red = Red(monkeypatch, {
        ("GET", "https://api.example/a"): httpx.Response(307, headers={"location": "/b"}),
        ("GET", "https://api.example/b"): httpx.Response(307, headers={"location": "https://otro.example/c"}),
        ("GET", "https://otro.example/c"): httpx.Response(200, json={}),
    })
    cabeceras = {"Authorization": "Bearer t0ken", "smash-authorization": "", "Accept": "application/json"}

    async def pedir():
        async with m.cliente_http() as cliente:
            return await m._pedir(cliente, "GET", "https://api.example/a", tope=1000, cabeceras=cabeceras)

    assert asyncio.run(pedir()).estado == 200
    assert [r.headers.get("authorization") for r in red.pedidos] == ["Bearer t0ken", "Bearer t0ken", None]
    assert "smash-authorization" not in red.pedidos[2].headers and red.pedidos[2].headers["accept"] == "application/json"


# ---------------------------------------------------------------------------
# Smash (red simulada, con la forma que tiene hoy su API)
# ---------------------------------------------------------------------------

SMASH = "AbCdEfGhIj-dt"  # la penúltima letra (d) es la región: eu-central-1
SMASH_LINK = f"https://link.fromsmash.co/target/fromsmash.com%2F{SMASH}?version=10-2019"
SMASH_API = f"https://transfer.eu-central-1.fromsmash.co/transfer/{SMASH}"
SMASH_ZIP = f"https://descargas.example/smash/{SMASH}.zip?Expires=1763575200&Signature=f1rma"
SMASH_PDF = "https://descargas.example/smash/fi-1?Expires=1763575200&Signature=f1rma"
DESCUBRIR = "https://discovery.fromsmash.co/namespace/public/services?version=02-2023"
DESCUBRIR_REGION = "https://discovery.us-east-1.fromsmash.co/namespace/public/services?version=02-2023"
INVITADO = "eyJhbGciOiJIUzI1NiIs.invitado-"


def _smash(monkeypatch, *, transferencia=None, rutas=None, link=SMASH_LINK, consulta="version=01-2024"):
    """Smash como lo ve su página (19/11/2026): discovery redirige al de la
    región, /account crea el invitado (con un token nuevo cada vez: …-1,
    …-2), el link dice qué transferencia es, /preview cómo está, /urls da el
    link firmado y ahí está el archivo (un ZIP con todo, si son varios).
    `transferencia` pisa campos de /preview y `rutas`, rutas enteras. Un
    token en `visto["vencidos"]` recibe 401, como uno vencido."""
    visto = {"invitados": 0, "vencidos": set()}

    def invitado(request):
        visto["invitados"] += 1
        visto["cuenta"] = request
        return httpx.Response(201, json={"account": {
            "id": f"an-{visto['invitados']}", "region": "us-east-1", "refreshToken": {"token": "r3fresh"},
            "token": {"type": "Bearer", "token": f"{INVITADO}{visto['invitados']}",
                      "expiration": "2099-11-20T18:00:00.000Z"}}})

    def urls(request):
        visto["urls"] = json.loads(request.content)
        return httpx.Response(200, json={"transfer": {"id": SMASH, "url": SMASH_ZIP, "files": []},
                                         "urlsExpiredAt": "2026-11-19T18:10:00.000Z"})

    def con_token(respuesta):
        def contestar(request):
            if request.headers.get("authorization") in visto["vencidos"]:
                return httpx.Response(401, json={"name": "Unauthorized", "code": 401, "error": "Token expired"})
            return respuesta(request) if callable(respuesta) else respuesta
        return contestar

    todas = {
        ("GET", DESCUBRIR): httpx.Response(307, headers={"location": DESCUBRIR_REGION}),
        ("GET", DESCUBRIR_REGION): httpx.Response(200, json={
            "services": [], "region": "us-east-1", "country": "Uruguay", "countryCode": "UY"}),
        ("POST", "https://iam.us-east-1.fromsmash.co/account"): invitado,
        ("POST", "https://iam.eu-central-1.fromsmash.co/account"): invitado,
        ("GET", link): httpx.Response(200, json={"target": {
            "url": f"https://transfer.eu-central-1.fromsmash.co/transfer/{SMASH}", "source": f"fromsmash.com/{SMASH}",
            "target": SMASH, "region": "eu-central-1"}}),
        ("GET", f"{SMASH_API}/preview?{consulta}"): httpx.Response(200, json={"transfer": {
            "id": SMASH, "title": "Cenefas Ciberlunes", "status": "Uploaded", "filesNumber": 3, "size": 2_400_000,
            "region": "eu-central-1", "availabilityEndDate": "2026-11-26T18:00:00.000Z", **(transferencia or {})},
            "urlsExpiredAt": "2026-11-19T18:10:00.000Z"}),
        ("PUT", f"{SMASH_API}/urls?{consulta}"): urls,
        ("GET", SMASH_ZIP): httpx.Response(
            200, content=_zip({"Cenefas/cenefa 1.jpg": _jpeg(), "Cenefas/cenefa 2.jpg": _jpeg(), "brief.docx": b"x"}),
            headers={"content-type": "application/zip",
                     "content-disposition": "attachment; filename*=UTF-8''Cenefas%20Ciberlunes.zip"}),
        **(rutas or {}),
    }
    api = ("https://link.fromsmash.co/", "https://transfer.")
    return Red(monkeypatch, {k: con_token(v) if k[1].startswith(api) else v for k, v in todas.items()}), visto


def test_smash_se_baja_como_lo_hace_su_pagina_sin_cuenta(monkeypatch):
    """Ivan (19/11/2026): «yo bajo sin smash los links». La página de Smash
    no pide cuenta: crea sola un invitado sin datos y con ese token pide el
    link firmado. Acá, los mismos pedidos y en el mismo orden."""
    red, visto = _smash(monkeypatch)
    j = _juntar(link=f"https://fromsmash.com/{SMASH}")
    assert [(i.nombre, i.origen) for i in j.imagenes] == [("Cenefas/cenefa 1.jpg", "link"), ("Cenefas/cenefa 2.jpg", "link")]
    assert j.ignorados == ["brief.docx"] and j.no_se_pudo_abrir == []
    assert [(r.method, str(r.url)) for r in red.pedidos] == [
        ("GET", DESCUBRIR), ("GET", DESCUBRIR_REGION),           # la región más cercana (sigue el 307)
        ("POST", "https://iam.us-east-1.fromsmash.co/account"),  # el invitado
        ("GET", SMASH_LINK),                                     # qué transferencia es el link
        ("GET", f"{SMASH_API}/preview?version=01-2024"),         # cómo está y cuánto pesa
        ("PUT", f"{SMASH_API}/urls?version=01-2024"),            # el link firmado
        ("GET", SMASH_ZIP),                                      # la descarga
    ]
    # El invitado: sin datos y sin credenciales.
    cuenta = visto["cuenta"]
    assert cuenta.content == b"{}" and cuenta.headers["content-type"] == "application/json"
    assert "authorization" not in cuenta.headers
    # La API, con el token del invitado y en JSON (sin ese Accept, a veces contesta XML).
    api = red.pedidos[3:6]
    assert all(r.headers["authorization"] == f"Bearer {INVITADO}1" for r in api)
    assert all(r.headers["accept"] == "application/json, text/plain, */*" for r in api)
    # La contraseña va vacía, como en su página, y solo a la transferencia.
    assert [r.headers.get("smash-authorization") for r in api] == [None, "", ""]
    # Varios archivos: todos juntos, en un ZIP. El link firmado se baja sin el token.
    assert visto["urls"] == {"files": []}
    assert "authorization" not in red.pedidos[-1].headers


def test_smash_de_un_solo_archivo_pide_ese_archivo(monkeypatch):
    """Como el botón Descargar: un archivo solo se pide por su id, no en un
    ZIP. Y el link puede venir con www, con «/» al final o del mail de Smash
    (con ?e=, el mail de quien lo recibe en base64, que va tal cual)."""
    consulta = "version=01-2024&e=cXVpZW5AZWplbXBsby5jb20%3D"
    pedido = {}

    def urls(request):
        pedido["urls"] = json.loads(request.content)
        return httpx.Response(200, json={"transfer": {"id": SMASH, "url": SMASH_ZIP,
                                                      "files": [{"id": "fi-1", "url": SMASH_PDF}]}})

    red, _ = _smash(monkeypatch, consulta=consulta, transferencia={"filesNumber": 1, "size": 180_000}, rutas={
        ("GET", f"{SMASH_API}/files/preview?{consulta}&limit=1"): httpx.Response(200, json={"files": [
            {"id": "fi-1", "name": "Folletos/folleto navidad.pdf", "ext": "pdf", "size": 180_000}], "next": None}),
        ("PUT", f"{SMASH_API}/urls?{consulta}"): urls,
        ("GET", SMASH_PDF): httpx.Response(200, content=_pdf(2), headers={"content-type": "application/pdf"}),
    })
    j = _juntar(link=f"https://www.fromsmash.com/{SMASH}/?e=cXVpZW5AZWplbXBsby5jb20=")
    assert [(i.nombre, i.pagina) for i in j.imagenes] == [("folleto navidad.pdf", 1), ("folleto navidad.pdf", 2)]
    assert j.revisados == [{"nombre": "folleto navidad.pdf", "origen": "link", "paginas": 2}]
    assert pedido["urls"] == {"files": [{"id": "fi-1"}]}
    assert str(red.pedidos[3].url) == SMASH_LINK  # sin www, sin «/» al final y sin la consulta
    assert str(red.pedidos[-1].url) == SMASH_PDF and not any(r.url == SMASH_ZIP for r in red.pedidos)


def test_smash_links_de_un_equipo_y_con_nombre_elegido(monkeypatch):
    """Un link de equipo (<equipo>.fromsmash.com) o con nombre elegido se
    resuelve igual: el servidor y la ruta, con la «/» como %2F."""
    _smash(monkeypatch, link="https://link.fromsmash.co/target/agencia.fromsmash.com%2FCenefas-Navidad?version=10-2019")
    j = _juntar(link="https://agencia.fromsmash.com/Cenefas-Navidad#descargar")
    assert len(j.imagenes) == 2 and j.no_se_pudo_abrir == []
    # Sin nada después del servidor no es una transferencia: ni se pregunta.
    red = Red(monkeypatch)
    assert _juntar(link="https://fromsmash.com/").no_se_pudo_abrir == [
        "No se pudo abrir el link (fromsmash.com/): el link de Smash no es el de una transferencia"]
    assert red.pedidos == []


def test_smash_reusa_el_invitado_y_pide_otro_si_se_vencio(monkeypatch):
    red, visto = _smash(monkeypatch)
    link = f"https://fromsmash.com/{SMASH}"
    assert len(_juntar(link=link).imagenes) == 2
    antes = len(red.pedidos)
    assert len(_juntar(link=link).imagenes) == 2
    # El segundo link usa el mismo invitado: ni discovery ni /account.
    assert visto["invitados"] == 1 and str(red.pedidos[antes].url) == SMASH_LINK
    # Si Smash dice que el token venció (401), se pide otro y se repite una vez.
    visto["vencidos"].add(f"Bearer {INVITADO}1")
    antes = len(red.pedidos)
    j = _juntar(link=link)
    assert len(j.imagenes) == 2 and j.no_se_pudo_abrir == []
    assert [(r.method, str(r.url)) for r in red.pedidos[antes:]] == [
        ("GET", SMASH_LINK), ("GET", DESCUBRIR), ("GET", DESCUBRIR_REGION),
        ("POST", "https://iam.us-east-1.fromsmash.co/account"), ("GET", SMASH_LINK),
        ("GET", f"{SMASH_API}/preview?version=01-2024"), ("PUT", f"{SMASH_API}/urls?version=01-2024"), ("GET", SMASH_ZIP),
    ]
    assert visto["invitados"] == 2 and red.pedidos[antes + 4].headers["authorization"] == f"Bearer {INVITADO}2"
    # Si el nuevo tampoco sirve, no insiste: se anota.
    red, visto = _smash(monkeypatch, rutas={("GET", SMASH_LINK): httpx.Response(401, json={"code": 401})})
    j = _juntar(link=link)
    assert j.no_se_pudo_abrir == [f"No se pudo abrir el link (fromsmash.com/{SMASH}): Smash no dejó entrar como invitado (contestó 401)"]
    assert visto["invitados"] == 2


@pytest.mark.parametrize("discovery", [
    httpx.Response(503, text="Service Unavailable"),
    httpx.Response(200, json={"services": [], "region": "trucho.example/x"}),  # una región que no es suya
])
def test_smash_sin_discovery_pide_el_invitado_en_una_region_fija(monkeypatch, discovery):
    _, visto = _smash(monkeypatch, rutas={("GET", DESCUBRIR): discovery})
    assert len(_juntar(link=f"https://fromsmash.com/{SMASH}").imagenes) == 2
    assert visto["cuenta"].url.host == "iam.eu-central-1.fromsmash.co"


_PREVIEW = ("GET", f"{SMASH_API}/preview?version=01-2024")


@pytest.mark.parametrize("ruta, respuesta, esperado", [
    # Con contraseña: con el nombre del error (su SDK) o solo con el texto (JDownloader).
    (_PREVIEW, httpx.Response(403, json={"name": "PasswordDoesNotMatch", "code": 403, "error": "Password does not match"}),
     "la transferencia de Smash tiene contraseña: pedile a la agencia un link sin contraseña o el ZIP"),
    (_PREVIEW, httpx.Response(403, json={"code": 403, "error": f"Password does not match for {SMASH}", "requestId": "h4sh"}),
     "la transferencia de Smash tiene contraseña"),
    (_PREVIEW, httpx.Response(403, json={"name": "InvalidEmail", "code": 403, "error": "Invalid email"}),
     "Smash pide el mail de quien baja esa transferencia"),
    (_PREVIEW, httpx.Response(403, json={"name": "OwnerUsageExceeded", "code": 403}),
     "la transferencia de Smash llegó a su límite de descargas"),
    (_PREVIEW, httpx.Response(403, json={"name": "Forbidden", "code": 403}),
     "Smash no dejó bajar la transferencia (contestó 403)"),
    (_PREVIEW, {"status": "Expired"}, "la transferencia de Smash venció: pedile a la agencia que la mande de nuevo"),
    (_PREVIEW, {"status": "Deleted"}, "la transferencia de Smash fue borrada"),
    (_PREVIEW, {"status": "Suspended"}, "Smash suspendió esa transferencia"),
    (_PREVIEW, {"status": "Uploading"}, "la transferencia de Smash todavía se estaba subiendo"),
    (_PREVIEW, {"status": "Dirty"}, "Smash no deja bajar esa transferencia ahora"),
    (_PREVIEW, {"size": 120 * 1024 * 1024}, "la transferencia de Smash pesa 120 MB y la plataforma baja hasta 40 MB"),
    (_PREVIEW, httpx.Response(404, json={"code": 404, "error": f"Transfer {SMASH} not found",
                                         "details": {"name": "Transfer", "primary": SMASH}}),
     "Smash dice que esa transferencia no existe"),
    (("GET", SMASH_LINK), httpx.Response(404, json={"name": "NotFound", "code": 404}), "Smash dice que esa transferencia no existe"),
    (_PREVIEW, httpx.Response(502, text="Bad Gateway"), "Smash no dejó bajar la transferencia (contestó 502)"),
    (_PREVIEW, httpx.Response(200, text="<xml>no es JSON</xml>"), "Smash contestó algo que la plataforma no entiende"),
    (("PUT", f"{SMASH_API}/urls?version=01-2024"), httpx.Response(429, json={"code": 429}), "Smash pidió esperar"),
    (("POST", "https://iam.us-east-1.fromsmash.co/account"), httpx.Response(500, text="no"),
     "Smash no dejó entrar como invitado (contestó 500)"),
])
def test_smash_lo_que_no_se_puede_bajar_se_anota(monkeypatch, ruta, respuesta, esperado):
    """Nunca es un error de la entrega: se anota con el porqué, para la
    persona, y no se baja nada."""
    if isinstance(respuesta, dict):
        red, _ = _smash(monkeypatch, transferencia=respuesta)
    else:
        red, _ = _smash(monkeypatch, rutas={ruta: respuesta})
    j = _juntar(link=f"https://fromsmash.com/{SMASH}")
    assert j.imagenes == [] and j.revisados == [] and len(j.no_se_pudo_abrir) == 1
    assert j.no_se_pudo_abrir[0].startswith(f"No se pudo abrir el link (fromsmash.com/{SMASH}): ")
    assert esperado in j.no_se_pudo_abrir[0]
    assert not any(r.url.host == "descargas.example" for r in red.pedidos)


def test_smash_no_arma_servidores_con_lo_que_contesta(monkeypatch):
    """La región y el id salen de lo que contesta Smash: una región que no es
    de las suyas no se usa (sale del id, como en su SDK), un id raro no se
    pide y un link firmado a la red interna no se abre."""
    red, _ = _smash(monkeypatch, rutas={("GET", SMASH_LINK): httpx.Response(200, json={
        "target": {"target": SMASH, "region": "trucho.example/x"}})})
    assert len(_juntar(link=f"https://fromsmash.com/{SMASH}").imagenes) == 2
    assert all(r.url.host.endswith((".fromsmash.co", "descargas.example")) for r in red.pedidos)
    for raro in ("../../admin", "AbC/../x", "", None):
        red, _ = _smash(monkeypatch, rutas={("GET", SMASH_LINK): httpx.Response(200, json={
            "target": {"target": raro, "region": "eu-central-1"}})})
        j = _juntar(link=f"https://fromsmash.com/{SMASH}")
        assert "Smash contestó algo que la plataforma no entiende" in j.no_se_pudo_abrir[0]
        assert not any(r.url.host.startswith("transfer.") for r in red.pedidos)
    red, _ = _smash(monkeypatch, rutas={("PUT", f"{SMASH_API}/urls?version=01-2024"): httpx.Response(200, json={
        "transfer": {"url": "http://169.254.169.254/latest/meta-data/"}})})
    j = _juntar(link=f"https://fromsmash.com/{SMASH}")
    assert "dirección interna" in j.no_se_pudo_abrir[0]
    assert not any(r.url.host == "169.254.169.254" for r in red.pedidos)


# ---------------------------------------------------------------------------
# WeTransfer (red simulada, como el botón Descargar de su página)
# ---------------------------------------------------------------------------

def _wetransfer(monkeypatch, *, con_destinatario=False, preparar=None, api=None, origen="https://wetransfer.com"):
    """WeTransfer como lo ve su página (19/11/2026): los links cortos (y el
    de www) redirigen a la página larga, que no hace falta leer;
    prepare-download dice si se puede bajar, download devuelve el
    direct_link y ahí está el archivo (un ZIP). La API está en el servidor
    de la página (`origen`: wetransfer.com o el de una marca)."""
    larga = f"{origen}/downloads/{TRANSFER}/{DESTINATARIO}/{HASH}" if con_destinatario \
        else f"{origen}/downloads/{TRANSFER}/{HASH}"
    visto = {}

    def preparar_por_defecto(request: httpx.Request) -> httpx.Response:
        visto["preparar"] = request
        return httpx.Response(200, json={
            "id": TRANSFER, "state": "downloadable", "password_protected": False,
            "downloader_email_verification": "anonymous", "recommended_filename": "WeTransfer_cenefas.zip",
            "size": 2_400_000, "expires_at": "2026-11-26T18:00:00Z", "display_name": "Cenefas",
            "items": [{"id": "it-1", "name": "Cenefas/cenefa 1.jpg", "size": 1_200_000}]})

    def api_por_defecto(request: httpx.Request) -> httpx.Response:
        visto["bajar"] = request
        return httpx.Response(200, json={"direct_link": "https://download.wetransfer.com/eu/archivo.zip?token=abc"})

    rutas = {
        ("GET", "https://we.tl/t-AbCdEf12"): httpx.Response(301, headers={"location": larga}),
        ("GET", "https://go.wetransfer.com/t-AbCdEf12"): httpx.Response(302, headers={"location": larga}),
        ("GET", "https://shorturls.wetransfer.com/AbCdEf12"): httpx.Response(302, headers={"location": larga}),
        ("GET", f"https://www.wetransfer.com/downloads/{TRANSFER}/{HASH}"): httpx.Response(
            301, headers={"location": larga}),
        # La página no se lee (se pide con tope 0: si se leyera, no entraría).
        ("GET", larga): httpx.Response(200, text="<!DOCTYPE html><html><body>Descargá</body></html>",
                                       headers={"content-type": "text/html"}),
        ("POST", f"{origen}/api/v4/transfers/{TRANSFER}/prepare-download"): preparar or preparar_por_defecto,
        ("POST", f"{origen}/api/v4/transfers/{TRANSFER}/download"): api or api_por_defecto,
        ("GET", "https://download.wetransfer.com/eu/archivo.zip?token=abc"): httpx.Response(
            302, headers={"location": "https://storage.example/firmado/archivo.zip?sig=1"}),
        ("GET", "https://storage.example/firmado/archivo.zip?sig=1"): httpx.Response(
            200, content=_zip({"Cenefas/cenefa 1.jpg": _jpeg(), "Cenefas/cenefa 2.jpg": _jpeg(), "brief.docx": b"x"}),
            headers={"content-type": "application/zip"}),
    }
    return Red(monkeypatch, rutas), visto


def test_wetransfer_se_baja_como_el_boton_descargar_de_su_pagina(monkeypatch):
    red, visto = _wetransfer(monkeypatch)
    j = _juntar(link="https://we.tl/t-AbCdEf12")
    assert [(i.nombre, i.origen) for i in j.imagenes] == [("Cenefas/cenefa 1.jpg", "link"), ("Cenefas/cenefa 2.jpg", "link")]
    assert j.ignorados == ["brief.docx"] and j.no_se_pudo_abrir == []
    larga = f"https://wetransfer.com/downloads/{TRANSFER}/{HASH}"
    assert [(r.method, str(r.url)) for r in red.pedidos] == [
        ("GET", "https://we.tl/t-AbCdEf12"), ("GET", larga),  # el link corto: solo adónde lleva
        ("POST", f"https://wetransfer.com/api/v4/transfers/{TRANSFER}/prepare-download"),
        ("POST", f"https://wetransfer.com/api/v4/transfers/{TRANSFER}/download"),
        ("GET", "https://download.wetransfer.com/eu/archivo.zip?token=abc"),
        ("GET", "https://storage.example/firmado/archivo.zip?sig=1"),
    ]
    assert json.loads(visto["preparar"].content) == {"security_hash": HASH}
    assert json.loads(visto["bajar"].content) == {"security_hash": HASH, "intent": "entire_transfer"}
    for pedido in (visto["preparar"], visto["bajar"]):
        assert pedido.headers["content-type"] == "application/json" and pedido.headers["accept"] == "application/json"
        assert pedido.headers["origin"] == "https://wetransfer.com" and pedido.headers["referer"] == larga
        assert pedido.headers["user-agent"].startswith("Mozilla/5.0")
        # Lo de antes ya no va: su página no usa más el token CSRF (ni la cookie de la página).
        assert not {"x-csrf-token", "x-requested-with", "cookie"} & set(pedido.headers)


def test_wetransfer_con_destinatario_y_la_pagina_larga_directa(monkeypatch):
    """El link largo (el del mail) no abre la página: va derecho a la API."""
    red, visto = _wetransfer(monkeypatch, con_destinatario=True)
    j = _juntar(link=f"https://wetransfer.com/downloads/{TRANSFER}/{DESTINATARIO}/{HASH}?t_s=email&t_lsid=x")
    assert len(j.imagenes) == 2
    assert str(red.pedidos[0].url) == f"https://wetransfer.com/api/v4/transfers/{TRANSFER}/prepare-download"
    cuerpo = {"security_hash": HASH, "recipient_id": DESTINATARIO}
    assert json.loads(visto["preparar"].content) == cuerpo
    assert json.loads(visto["bajar"].content) == {**cuerpo, "intent": "entire_transfer"}


@pytest.mark.parametrize("link", [
    "https://go.wetransfer.com/t-AbCdEf12", "https://shorturls.wetransfer.com/AbCdEf12",
    f"https://www.wetransfer.com/downloads/{TRANSFER}/{HASH}",
])
def test_wetransfer_los_otros_links_cortos_y_el_de_www(monkeypatch, link):
    red, _ = _wetransfer(monkeypatch)
    j = _juntar(link=link)
    assert len(j.imagenes) == 2 and j.no_se_pudo_abrir == []
    assert str(red.pedidos[2].url) == f"https://wetransfer.com/api/v4/transfers/{TRANSFER}/prepare-download"


def test_wetransfer_de_una_marca_usa_la_api_de_su_pagina(monkeypatch):
    """<marca>.wetransfer.com: la API está en el mismo servidor que la página
    (su web la llama con una ruta relativa)."""
    origen = "https://tiendainglesa.wetransfer.com"
    red, visto = _wetransfer(monkeypatch, origen=origen)
    j = _juntar(link=f"{origen}/downloads/{TRANSFER}/{HASH}")
    assert len(j.imagenes) == 2 and j.no_se_pudo_abrir == []
    assert [str(r.url) for r in red.pedidos[:3]] == [
        f"{origen}/downloads/{TRANSFER}/{HASH}", f"{origen}/api/v4/transfers/{TRANSFER}/prepare-download",
        f"{origen}/api/v4/transfers/{TRANSFER}/download"]
    assert visto["preparar"].headers["origin"] == origen


def test_un_link_firmado_de_wetransfer_se_baja_directo(monkeypatch):
    red, _ = _wetransfer(monkeypatch)
    j = _juntar(link="https://download.wetransfer.com/eu/archivo.zip?token=abc")
    assert len(j.imagenes) == 2
    assert [str(r.url) for r in red.pedidos] == [
        "https://download.wetransfer.com/eu/archivo.zip?token=abc", "https://storage.example/firmado/archivo.zip?sig=1"]


_CON_CONTRASENA = "la transferencia de WeTransfer tiene contraseña: pedile a la agencia un link sin contraseña o el ZIP"


@pytest.mark.parametrize("preparar, bajar, esperado", [
    # Con contraseña contesta 200 igual, pero lo dice (y sin la lista de archivos).
    (httpx.Response(200, json={"state": "downloadable", "password_protected": True}), None, _CON_CONTRASENA),
    (httpx.Response(403, json={"message": "invalid_transfer_password"}), None, _CON_CONTRASENA),
    (httpx.Response(403, json={"message": "No download access to this Transfer"}), None,
     "WeTransfer pide una cuenta o verificar el mail de quien baja esa transferencia"),
    (httpx.Response(404, json={"message": "Transfer not found"}), None, "la transferencia de WeTransfer venció o la borraron"),
    (httpx.Response(200, json={"state": "expired", "password_protected": False}), None,
     "la transferencia de WeTransfer venció o ya no se puede bajar"),
    (httpx.Response(200, json={"state": "downloadable", "size": 150 * 1024 * 1024}), None,
     "la transferencia de WeTransfer pesa 150 MB y la plataforma baja hasta 40 MB"),
    (httpx.Response(429, headers={"retry-after": "30"}), None, "WeTransfer pidió esperar"),
    # Una página en vez del JSON: no se dice que venció.
    (httpx.Response(200, text="<html>¿Sos un robot?</html>"), None,
     "WeTransfer contestó algo que la plataforma no entiende"),
    (None, httpx.Response(403, json={"message": "No download access to this Transfer"}),
     "WeTransfer pide una cuenta o verificar el mail"),
    (None, httpx.Response(400, json={"error": "invalid_transfer"}), "la transferencia de WeTransfer venció o la borraron"),
    (None, httpx.Response(200, json={"status": "ok"}), "WeTransfer no devolvió el link de descarga"),
    (None, httpx.Response(500, text="error"), "WeTransfer no dejó bajar la transferencia (contestó 500)"),
])
def test_wetransfer_lo_que_no_se_puede_bajar_se_anota(monkeypatch, preparar, bajar, esperado):
    """Nunca es un error de la entrega: se anota con el porqué, para la
    persona, y no se baja nada."""
    red, _ = _wetransfer(monkeypatch, preparar=preparar, api=bajar)
    j = _juntar(link="https://we.tl/t-AbCdEf12")
    assert j.imagenes == [] and len(j.no_se_pudo_abrir) == 1
    assert j.no_se_pudo_abrir[0].startswith("No se pudo abrir el link (we.tl/t-AbCdEf12): ")
    assert esperado in j.no_se_pudo_abrir[0]
    assert not any(r.url.host in ("download.wetransfer.com", "storage.example") for r in red.pedidos)


def test_un_link_de_wetransfer_que_no_lleva_a_una_transferencia(monkeypatch):
    # Un link corto viejo que manda a la portada.
    red = Red(monkeypatch, {("GET", "https://we.tl/t-viejo"): httpx.Response(301, headers={"location": "https://wetransfer.com/"}),
                            ("GET", "https://wetransfer.com/"): httpx.Response(200, text="<html>portada</html>")})
    j = _juntar(link="https://we.tl/t-viejo")
    assert j.no_se_pudo_abrir == [
        "No se pudo abrir el link (we.tl/t-viejo): el link de WeTransfer venció o no es el de una transferencia"]
    assert len(red.pedidos) == 2
    # La portada o un tablero (collect.wetransfer.com, que usa otra API): no se le pide nada a la API.
    for link in ("https://wetransfer.com/", "https://collect.wetransfer.com/board/abc123"):
        red = Red(monkeypatch)
        assert "no es el de una transferencia" in _juntar(link=link).no_se_pudo_abrir[0]
        assert not any("/api/" in r.url.path for r in red.pedidos)


def test_juntar_con_zip_y_link_respeta_el_tope_total(monkeypatch):
    Red(monkeypatch, {("GET", "https://cdn.example/c.jpg"): _imagen()})
    j = _juntar(zip_datos=_zip({"a.jpg": _jpeg(100, 100), "b.jpg": _jpeg(100, 100)}), zip_nombre="piezas.zip",
                link="https://cdn.example/c.jpg", lugar=2)
    assert [(i.nombre, i.origen) for i in j.imagenes] == [("a.jpg", "zip"), ("b.jpg", "zip")]
    assert j.no_se_pudo_abrir == ["«c.jpg»: quedó afuera por el tope de imágenes por entrega"]
    j = _juntar(zip_datos=_zip({"a.jpg": _jpeg(100, 100)}), zip_nombre="piezas.zip", link="https://cdn.example/c.jpg", lugar=5)
    assert [(i.nombre, i.origen) for i in j.imagenes] == [("a.jpg", "zip"), ("c.jpg", "link")]
    assert j.resumen() == {
        "revisados": [{"nombre": "a.jpg", "origen": "zip", "paginas": None}, {"nombre": "c.jpg", "origen": "link", "paginas": None}],
        "noSePudoAbrir": [], "ignorados": [],
    }


def test_sin_zip_ni_link_no_hay_nada_que_hacer(monkeypatch):
    red = Red(monkeypatch)
    j = _juntar()
    assert j.imagenes == [] and j.resumen() == {"revisados": [], "noSePudoAbrir": [], "ignorados": []}
    assert red.pedidos == []
    assert _juntar(link="   ").no_se_pudo_abrir == []


def test_el_nombre_del_archivo_bajado():
    def r(url, **cab):
        return m.Respuesta(url, 200, httpx.Headers(cab), b"")

    assert m._nombre_del_archivo(r("https://x.example/a/b/pieza%20final.jpg")) == "pieza final.jpg"
    assert m._nombre_del_archivo(r("https://x.example/d?id=1", **{"content-disposition": 'attachment; filename="f.pdf"'})) == "f.pdf"
    assert m._nombre_del_archivo(r("https://x.example/d", **{"content-disposition": "attachment; filename*=UTF-8''se%C3%B1al.pdf"})) == "señal.pdf"
    assert m._nombre_del_archivo(r("https://x.example/")) == "archivo del link"
    assert m._nombre_del_archivo(r("https://x.example/" + "a" * 300 + ".jpg")).endswith("a") and len(m._nombre_del_archivo(r("https://x.example/" + "a" * 300))) == 120


# ---------------------------------------------------------------------------
# Lo del ZIP que pasa a la ronda al entregar (19/11/2026)
# ---------------------------------------------------------------------------
# Ivan no entendía por qué un ZIP con solo el PDF del folleto no alcanzaba
# para entregar: "no debería pasar". Ahora el servidor dibuja las páginas y
# las guarda como imágenes de la ronda, para que quien aprueba las vea y las
# marque como cualquier imagen.

def _abrir(datos: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(datos))
    img.load()
    return img


def _calidad_75() -> dict:
    """Las tablas de cuantización de un JPEG guardado con calidad 75: si son
    las mismas, se guardó con la calidad del navegador."""
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(buf, "JPEG", quality=75)
    return _abrir(buf.getvalue()).quantization


def test_un_zip_con_solo_un_pdf_sale_como_imagenes_de_la_ronda():
    s = m.imagenes_para_la_ronda(_zip({"folleto.pdf": _pdf(3), "leeme.txt": b"x"}), lugar=4)
    assert [(i.nombre, i.pagina, i.indice) for i in s.imagenes] == [("folleto.pdf", 1, 0), ("folleto.pdf", 2, 0), ("folleto.pdf", 3, 0)]
    # Achicadas como en el navegador: 1600 px de lado mayor (una A4 en vertical
    # sale de 1131 x 1600), la miniatura de 320 y JPEG con calidad 75.
    for im in s.imagenes:
        grande, mini = _abrir(im.datos), _abrir(im.miniatura)
        assert grande.format == mini.format == "JPEG" and grande.mode == "RGB"
        assert grande.size == (1131, 1600) and max(mini.size) == 320
        assert grande.quantization == _calidad_75()
        assert len(im.datos) <= m.MAX_BYTES_IMAGEN and len(im.miniatura) <= m.MAX_BYTES_MINIATURA
    # Entró entero: la IA no lo vuelve a mirar.
    assert s.entradas == {0} and s.paginas == {} and s.no_se_pudo == []


def test_un_pdf_largo_llena_los_lugares_que_quedan_y_la_ia_sigue_desde_ahi():
    datos = _zip({"folleto.pdf": _pdf(6)})
    s = m.imagenes_para_la_ronda(datos, lugar=3)
    assert [i.pagina for i in s.imagenes] == [1, 2, 3]
    # Entró en parte: no se salta entero, se dice hasta qué página.
    assert s.entradas == set() and s.paginas == {0: 3}
    # La IA mira las que siguen (4, 5 y 6), con su número de página de verdad.
    j = m.Juntado()
    assert m.extraer_del_zip(datos, j, lugar=12, saltar=frozenset(s.entradas), paginas_hechas=s.paginas) == 3
    assert [(i.nombre, i.pagina) for i in j.imagenes] == [("folleto.pdf", 4), ("folleto.pdf", 5), ("folleto.pdf", 6)]
    assert j.revisados == [{"nombre": "folleto.pdf", "origen": "zip", "paginas": 3}] and j.no_se_pudo_abrir == []
    # Por juntar (lo que usa la revisión), igual.
    j = _juntar(zip_datos=datos, zip_nombre="piezas.zip", zip_saltar=frozenset(s.entradas), zip_paginas=s.paginas)
    assert [i.pagina for i in j.imagenes] == [4, 5, 6]


def test_el_tope_de_paginas_por_pdf_de_la_ia_cuenta_las_que_ya_estan_en_la_ronda():
    j = m.Juntado()
    m.extraer_del_zip(_zip({"catalogo.pdf": _pdf(12)}), j, lugar=12, paginas_hechas={0: 4})
    assert [i.pagina for i in j.imagenes] == [5, 6, 7, 8, 9, 10]
    assert j.no_se_pudo_abrir == ["«catalogo.pdf»: se revisaron las primeras 10 páginas de 12 (tope de 10 páginas por PDF)"]
    # Sin lugar para la IA, el PDF no "quedó afuera": sus primeras páginas están en la ronda.
    j = m.Juntado()
    m.extraer_del_zip(_zip({"a.jpg": _jpeg(50, 50), "catalogo.pdf": _pdf(5)}), j, lugar=1, paginas_hechas={1: 4})
    assert j.no_se_pudo_abrir == ["«catalogo.pdf»: se revisaron solo las páginas que van como imágenes de la ronda "
                                  "(tope de imágenes por entrega)"]


def test_van_en_el_orden_del_zip_sin_las_que_subio_el_navegador():
    transparente = io.BytesIO()
    Image.new("RGBA", (300, 200), (0, 0, 0, 0)).save(transparente, "PNG")
    datos = _zip({"a.jpg": _jpeg(), "b.png": transparente.getvalue(), "folleto.pdf": _pdf(2), "c.jpg": _jpeg()})
    s = m.imagenes_para_la_ronda(datos, lugar=3, saltar=frozenset({0}))
    assert [(i.nombre, i.pagina) for i in s.imagenes] == [("b.png", None), ("folleto.pdf", 1), ("folleto.pdf", 2)]
    assert s.entradas == {1, 2}
    # Lo transparente queda sobre blanco, como en el navegador (en JPEG
    # saldría negro), y una imagen chica no se agranda.
    b = _abrir(s.imagenes[0].datos)
    assert b.size == (300, 200) and all(v > 245 for v in b.getpixel((150, 100)))
    # Sin lugar, no se abre nada.
    assert m.imagenes_para_la_ronda(datos, lugar=0).imagenes == []


def test_una_imagen_del_zip_se_achica_y_queda_derecha():
    grande = m.imagenes_para_la_ronda(_zip({"foto.jpg": _jpeg(3200, 3200, "blue")}), lugar=1).imagenes[0]
    assert _abrir(grande.datos).size == (1600, 1600) and _abrir(grande.miniatura).size == (320, 320)
    # Una foto del teléfono, guardada acostada con la orientación en el EXIF:
    # el navegador la muestra derecha, y la de la ronda también tiene que estarlo.
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    Image.new("RGB", (800, 400), "green").save(buf, "JPEG", exif=exif.tobytes())
    derecha = m.imagenes_para_la_ronda(_zip({"celular.jpg": buf.getvalue()}), lugar=1).imagenes[0]
    assert _abrir(derecha.datos).size == (400, 800)


def test_lo_que_no_se_puede_pasar_a_la_ronda_se_anota_y_sigue_con_lo_proximo():
    gigante = io.BytesIO()
    Image.new("1", (8000, 8000)).save(gigante, "PNG")
    datos = _zip({"cerrado.pdf": _pdf(1, clave="secreta"), "roto.pdf": b"%PDF-1.4 nada", "trucho.jpg": b"texto",
                  "gigante.png": gigante.getvalue(), "ok.jpg": _jpeg(100, 100)})
    s = m.imagenes_para_la_ronda(datos, lugar=4)
    assert [i.nombre for i in s.imagenes] == ["ok.jpg"]
    assert s.no_se_pudo == [
        "«cerrado.pdf»: el PDF está protegido con contraseña",
        "«roto.pdf»: no se pudo leer el PDF (¿está dañado?)",
        "«trucho.jpg»: no es una imagen JPG, PNG ni WebP (aunque el nombre lo diga)",
        "«gigante.png»: es demasiado grande (8000 x 8000)",
    ]


def test_las_paginas_se_dibujan_de_a_una_y_se_suelta_la_memoria(monkeypatch):
    """El servidor tiene 512 MB: PyMuPDF guarda lo que decodifica (hasta 256
    MB) y se vacía después de cada página y al cerrar el PDF. Y un PDF por
    vez en todo el proceso: PyMuPDF no se puede usar desde dos hilos a la vez."""
    import threading

    import pymupdf

    vaciadas = []
    original = pymupdf.TOOLS.store_shrink

    def vaciar(n):
        # Mientras se dibuja, el candado está tomado: otro hilo no puede entrar.
        tomado = []

        def probar():
            pude = m._DE_A_UNO.acquire(blocking=False)
            if pude:
                m._DE_A_UNO.release()
            tomado.append(not pude)

        otro = threading.Thread(target=probar)
        otro.start()
        otro.join()
        vaciadas.append((n, tomado[0]))
        return original(n)

    monkeypatch.setattr(pymupdf.TOOLS, "store_shrink", vaciar)
    m.imagenes_para_la_ronda(_zip({"folleto.pdf": _pdf(3)}), lugar=4)
    assert vaciadas == [(100, True)] * 4  # 3 páginas y el cierre
    vaciadas.clear()
    m.paginas_de_pdf(_pdf(2))  # lo de la IA, igual
    assert vaciadas == [(100, True)] * 3


def test_el_servidor_achica_igual_que_el_navegador():
    """Las medidas y la calidad tienen que ser las de
    frontend/lib/calendario/entregas.ts: si cambian allá, cambian acá."""
    import pathlib
    import re

    from app.services import entregas as reglas

    ts = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "calendario" / "entregas.ts").read_text(encoding="utf-8")

    def constante(nombre):
        return float(re.search(rf"export const {nombre} = ([0-9.]+)", ts).group(1))

    assert constante("LADO_MAYOR") == reglas.LADO_MAYOR
    assert constante("LADO_MINIATURA") == reglas.LADO_MINIATURA
    assert round(constante("CALIDAD") * 100) == reglas.CALIDAD_JPEG
