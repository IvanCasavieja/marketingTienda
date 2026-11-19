"""Lo que la agencia entrega además de las imágenes —un ZIP o un link— para
que la IA lo revise también (19/11/2026).

Pedido de Ivan: "¿Qué pasaría si en vez de una imagen me hubieran pasado una
carpeta o un link? (…) cuando ellos le dan a enviar, vos directamente como
plataforma ya descargués todas las cosas, hagas todo el proceso y a nosotros ya
nos traigas un pantallazo con todas las cosas armadas". Lo que llega de las
agencias es, casi siempre, una carpeta comprimida (ZIP) o un link de
WeTransfer o de Smash; Drive no.

Qué hace, y con qué frenos:

- **Un ZIP** (subido con la entrega, o bajado de un link). Se abre SOLO en
  memoria con `zipfile`: nunca se escribe en disco. De adentro se toman las
  imágenes (JPG, PNG, WebP) y los PDF, subcarpetas incluidas; el resto se
  ignora y se lista por nombre, así el aprobador sabe qué venía. Un ZIP de
  Windows guarda los nombres con tildes y ñ en la codificación vieja (cp850):
  se convierten bien (ver `nombre_real`). Frenos: 40 MB el archivo, 60
  archivos adentro, 200 MB descomprimido y nada que se "infle" más de 100
  veces (una bomba zip); una ruta con «..» o absoluta rechaza el ZIP entero;
  y lo que se lee de verdad se corta en MAX_BYTES_ARCHIVO aunque el índice
  del ZIP mienta con el tamaño.
- **Un link.** Se baja con httpx: timeout corto, hasta 3 redirecciones, solo
  http/https y NUNCA a la red interna (`_host_publico`): se resuelve el
  nombre antes de conectar y se rechazan las IPs privadas, de loopback, de
  link-local, etc.; después de conectar se vuelve a mirar a qué IP se
  conectó de verdad (`_ip_del_servidor`), por si el nombre cambió entre
  medio. Tope de 40 MB. Si lo que llega es una página web y no un archivo
  (un link privado, uno que pide iniciar sesión), no es un error: se anota
  "no se pudo abrir" y la revisión sigue con lo que haya.
  - WeTransfer (we.tl, wetransfer.com) muestra una página, no el archivo: la
    descarga sale de su API (`_bajar_wetransfer`), sin credenciales, como lo
    hacen las herramientas de línea de comandos. Es una API no documentada:
    si WeTransfer la cambia, el link queda como "no se pudo abrir" y no se
    rompe nada más.
  - Smash (fromsmash.com) no se puede bajar sin su API con credenciales:
    queda anotado "no se pudo abrir: pasalo como ZIP".
- **Un PDF**: una imagen por página, hasta 10, con PyMuPDF (ya estaba en el
  servidor por la validación de RRSS), al mismo lado máximo que las imágenes
  que van a la IA.

Nada de esto levanta hacia afuera: lo que no se pudo abrir queda en
`Juntado.no_se_pudo_abrir` con el porqué, para la persona. Corre en segundo
plano, después de contestar la entrega (revision_ia.revisar_version): la
entrega no espera la descarga. Lo que sale de acá va a la IA como las
imágenes subidas, con el nombre del archivo en cada observación; NO se guarda
en la base (la base es chica, ver app/models/entregas.py): el aprobador ve
lo que subió la agencia y, de lo demás, lo que la IA encontró.
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import logging
import re
import socket
import struct
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote

import httpx

from app.services.entregas import tipo_de_imagen
from app.services.revision_ia import LADO_MAXIMO, ImagenParaIA, preparar_imagen

logger = logging.getLogger(__name__)

# El ZIP
MAX_BYTES_ZIP = 40 * 1024 * 1024
MAX_ARCHIVOS_ZIP = 60
MAX_BYTES_DESCOMPRIMIDO = 200 * 1024 * 1024
# Descomprimido / comprimido. Un JPG o un PDF casi no se comprimen (1x); un
# texto, unas 5x; una bomba zip, miles. Se mira solo en archivos de más de
# 1 MB: un .txt chico de espacios se infla 200x y no es ninguna bomba.
RELACION_MAXIMA = 100
_PISO_RELACION = 1024 * 1024
# Lo que se lee de verdad de cada archivo de adentro (el índice puede mentir).
MAX_BYTES_ARCHIVO = 40 * 1024 * 1024
EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png", ".webp")
EXTENSION_PDF = ".pdf"

# El link
MAX_BYTES_LINK = 40 * 1024 * 1024
ESPERA_LINK = 10.0           # segundos por operación (conectar, leer...)
ESPERA_TOTAL_LINK = 60.0     # todo el link, de punta a punta (varios pedidos)
MAX_REDIRECCIONES = 3
_MAX_BYTES_PAGINA = 2 * 1024 * 1024    # el HTML de WeTransfer (solo el token)
_MAX_BYTES_API = 256 * 1024
_AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/131.0.0.0 Safari/537.36 CoreTienda/1.0")

# El PDF
MAX_PAGINAS_PDF = 10


class NoSePudoAbrir(Exception):
    """El mensaje es para la persona: por qué no se pudo abrir el link o el
    archivo. Nunca sale como error: se anota en el resultado."""


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:g} MB"


# ---------------------------------------------------------------------------
# Lo juntado: lo que va a la IA y lo que hay que contarle a la persona
# ---------------------------------------------------------------------------

@dataclass
class Juntado:
    # Las imágenes para la IA, en el orden en que se van a mandar (las del
    # ZIP primero, después las del link).
    imagenes: list[ImagenParaIA] = field(default_factory=list)
    # Lo que se miró, para mostrarlo: {"nombre", "origen", "paginas"}.
    revisados: list[dict] = field(default_factory=list)
    # Lo que no se pudo abrir, con el porqué.
    no_se_pudo_abrir: list[str] = field(default_factory=list)
    # Lo que venía en el ZIP y no es una imagen ni un PDF (por nombre).
    ignorados: list[str] = field(default_factory=list)

    def resumen(self) -> dict:
        """Lo que se guarda con la revisión (calendario_revisiones_ia.materiales)."""
        return {"revisados": list(self.revisados), "noSePudoAbrir": list(self.no_se_pudo_abrir),
                "ignorados": list(self.ignorados)}


def _anotar_paginas(j: Juntado, nombre: str, origen: str, paginas: list[bytes], total: int, lugar: int) -> int:
    """Suma las páginas renderizadas de un PDF (ya al lado máximo) y anota el
    archivo. Devuelve cuántas imágenes agregó."""
    n = 0
    for i, datos in enumerate(paginas, 1):
        if n >= lugar:
            break
        j.imagenes.append(preparar_imagen(None, datos, "image/jpeg", nombre=nombre, origen=origen, pagina=i))
        n += 1
    j.revisados.append({"nombre": nombre, "origen": origen, "paginas": n})
    if n < total:
        j.no_se_pudo_abrir.append(
            f"«{nombre}»: se revisaron las primeras {n} páginas de {total}"
            + (f" (tope de {MAX_PAGINAS_PDF} páginas por PDF)" if n >= MAX_PAGINAS_PDF else " (tope de imágenes por entrega)")
        )
    return n


# ---------------------------------------------------------------------------
# El ZIP (puro, en memoria)
# ---------------------------------------------------------------------------

@dataclass
class Entrada:
    nombre: str         # la ruta adentro del ZIP, con «/» y bien decodificada
    clase: str          # 'imagen' | 'pdf' | 'otro'
    tamano: int         # el que declara el índice
    info: zipfile.ZipInfo
    # Su lugar en el índice del ZIP, contando todo (carpetas y basura
    # incluidas): es como el navegador nombra las imágenes que ya sacó del
    # ZIP para la ronda (ver `saltar` en extraer_del_zip).
    indice: int = -1


def nombre_real(info: zipfile.ZipInfo) -> str:
    """El nombre con sus tildes y ñ. zipfile decodifica con cp437 los nombres
    que no vienen marcados como UTF-8 (bit 11 de los flags), y el ZIP que arma
    el Explorador de Windows en español viene así: «cenefa_ñ.jpg» salía como
    «cenefa_ñ.jpg»... o peor. Se vuelve a los bytes y se prueba UTF-8 (muchas
    herramientas lo escriben sin marcarlo) y, si no, cp850 (la página de
    códigos OEM de Windows en español, que para las tildes y la ñ coincide
    con cp437). Si el ZIP trae el campo extra 0x7075 (Info-ZIP Unicode Path,
    lo agrega WinRAR), ese nombre manda."""
    nombre = info.filename
    if info.flag_bits & 0x800:
        return nombre
    extra = info.extra or b""
    i = 0
    while i + 4 <= len(extra):
        tipo, largo = struct.unpack("<HH", extra[i:i + 4])
        datos = extra[i + 4:i + 4 + largo]
        if tipo == 0x7075 and len(datos) > 5 and datos[0] == 1:
            try:
                return datos[5:].decode("utf-8")
            except UnicodeDecodeError:
                pass
        i += 4 + largo
    try:
        crudo = nombre.encode("cp437")
    except UnicodeEncodeError:
        return nombre
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("cp850")


def _ruta_insegura(nombre: str) -> bool:
    """Una ruta con «..», absoluta o con un nombre de unidad. No se escribe
    nada en disco, pero un ZIP armado así no es de una agencia."""
    n = nombre.replace("\\", "/")
    if "\x00" in n or n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return True
    return any(parte == ".." for parte in n.split("/"))


def _es_basura(nombre: str) -> bool:
    """Lo que agregan macOS y Windows solos y a nadie le interesa ver listado."""
    n = nombre.replace("\\", "/")
    base = n.rsplit("/", 1)[-1]
    return (n.casefold().startswith("__macosx/") or base.startswith("._")
            or base.casefold() in (".ds_store", "thumbs.db", "desktop.ini"))


def _clase(nombre: str) -> str:
    bajo = nombre.casefold()
    if bajo.endswith(EXTENSIONES_IMAGEN):
        return "imagen"
    if bajo.endswith(EXTENSION_PDF):
        return "pdf"
    return "otro"


def inspeccionar_zip(datos: bytes) -> list[Entrada]:
    """Qué hay adentro, sin descomprimir nada (solo el índice), o ValueError
    con el mensaje para la persona si el ZIP no sirve: no es un ZIP, pesa
    demasiado, tiene demasiados archivos, se infla demasiado o trae rutas que
    no van. Las entradas vienen en el orden del ZIP, con los directorios y la
    basura del sistema ya filtrados."""
    if not datos:
        raise ValueError("El ZIP llegó vacío")
    if len(datos) > MAX_BYTES_ZIP:
        raise ValueError(f"El ZIP pesa {_mb(len(datos))}: el máximo es {_mb(MAX_BYTES_ZIP)}")
    try:
        zf = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile:
        raise ValueError("El archivo no es un ZIP (o está dañado)")
    entradas: list[Entrada] = []
    total = 0
    with zf:
        for indice, info in enumerate(zf.infolist()):
            if info.is_dir():
                continue
            nombre = nombre_real(info).replace("\\", "/")
            if _ruta_insegura(nombre):
                raise ValueError("El ZIP tiene rutas que no van (con «..» o absolutas): no se puede abrir")
            if _es_basura(nombre):
                continue
            if len(entradas) >= MAX_ARCHIVOS_ZIP:
                raise ValueError(f"El ZIP tiene demasiados archivos adentro (máximo {MAX_ARCHIVOS_ZIP})")
            total += info.file_size
            if total > MAX_BYTES_DESCOMPRIMIDO:
                raise ValueError(f"Descomprimido, el ZIP pasa de {_mb(MAX_BYTES_DESCOMPRIMIDO)}: es demasiado")
            if info.file_size > _PISO_RELACION and info.file_size > RELACION_MAXIMA * max(1, info.compress_size):
                raise ValueError("El ZIP no parece sano: un archivo se descomprime a un tamaño absurdo")
            entradas.append(Entrada(nombre, _clase(nombre), info.file_size, info, indice))
    return entradas


def _leer_entrada(zf: zipfile.ZipFile, e: Entrada) -> bytes:
    """Los bytes de un archivo de adentro, cortando en MAX_BYTES_ARCHIVO sin
    importar lo que declare el índice (una bomba zip miente ahí)."""
    try:
        with zf.open(e.info) as f:
            contenido = f.read(MAX_BYTES_ARCHIVO + 1)
    except RuntimeError as exc:
        # zipfile levanta RuntimeError para un archivo cifrado.
        if "encrypted" in str(exc) or "password" in str(exc):
            raise NoSePudoAbrir("está protegido con contraseña") from exc
        raise NoSePudoAbrir("no se pudo descomprimir") from exc
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise NoSePudoAbrir("está dañado adentro del ZIP") from exc
    if len(contenido) > MAX_BYTES_ARCHIVO:
        raise NoSePudoAbrir(f"pesa más de {_mb(MAX_BYTES_ARCHIVO)}")
    return contenido


def extraer_del_zip(
    datos: bytes, juntado: Juntado, *, lugar: int, origen: str = "zip", saltar: frozenset[int] = frozenset(),
) -> int:
    """Saca del ZIP las imágenes y los PDF (como imágenes, una por página) y
    los suma a `juntado`, hasta `lugar` imágenes: lo que no entra queda
    anotado. Lo que no es imagen ni PDF va a `ignorados`. Devuelve cuántas
    imágenes agregó. `saltar`: los lugares en el índice de las imágenes que
    el navegador ya sacó del ZIP y subió como imágenes de la ronda: esas la
    IA ya las ve, no se miran dos veces. ValueError si el ZIP entero no sirve (ver
    inspeccionar_zip). Es sincrónica y pesada (descomprime, abre imágenes,
    renderiza PDF): se llama desde un hilo."""
    entradas = inspeccionar_zip(datos)
    agregadas = 0
    with zipfile.ZipFile(io.BytesIO(datos)) as zf:
        for e in entradas:
            if e.indice in saltar:
                continue
            if e.clase == "otro":
                juntado.ignorados.append(e.nombre)
                continue
            if agregadas >= lugar:
                juntado.no_se_pudo_abrir.append(f"«{e.nombre}»: quedó afuera por el tope de imágenes por entrega")
                continue
            try:
                contenido = _leer_entrada(zf, e)
                if e.clase == "imagen":
                    tipo = tipo_de_imagen(contenido)
                    if tipo is None:
                        raise NoSePudoAbrir("no es una imagen JPG, PNG ni WebP (aunque el nombre lo diga)")
                    juntado.imagenes.append(preparar_imagen(None, contenido, tipo, nombre=e.nombre, origen=origen))
                    juntado.revisados.append({"nombre": e.nombre, "origen": origen, "paginas": None})
                    agregadas += 1
                else:
                    paginas, total = paginas_de_pdf(contenido, max_paginas=min(MAX_PAGINAS_PDF, lugar - agregadas))
                    agregadas += _anotar_paginas(juntado, e.nombre, origen, paginas, total, lugar - agregadas)
            except (NoSePudoAbrir, ValueError) as exc:
                juntado.no_se_pudo_abrir.append(f"«{e.nombre}»: {exc}")
            except Exception as exc:  # un archivo roto no tira la revisión entera
                logger.warning("materiales: no se pudo abrir «%s» del ZIP — %s: %s", e.nombre, type(exc).__name__, exc)
                juntado.no_se_pudo_abrir.append(f"«{e.nombre}»: no se pudo abrir")
    return agregadas


# ---------------------------------------------------------------------------
# El PDF (puro)
# ---------------------------------------------------------------------------

def paginas_de_pdf(datos: bytes, *, max_paginas: int = MAX_PAGINAS_PDF, lado: int = LADO_MAXIMO) -> tuple[list[bytes], int]:
    """Las primeras `max_paginas` páginas como JPEG (lado mayor `lado`, como
    las imágenes que van a la IA) y cuántas páginas tiene en total. ValueError
    si no se puede leer o pide contraseña. De a una página en memoria."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=datos, filetype="pdf")
    except Exception as exc:
        raise ValueError("no se pudo leer el PDF (¿está dañado?)") from exc
    try:
        if doc.needs_pass:
            raise ValueError("el PDF está protegido con contraseña")
        total = doc.page_count
        salida: list[bytes] = []
        for i in range(min(total, max(0, max_paginas))):
            pagina = doc[i]
            mayor = max(pagina.rect.width, pagina.rect.height) or 1.0
            # Los puntos del PDF son 1/72 de pulgada: una A4 mide 842 de alto,
            # así que a 1600 px es ~1,9x (137 dpi). Un sello de 2 cm no se
            # agranda más de 8x: no tendría sentido mandar una imagen gigante.
            escala = min(lado / mayor, 8.0)
            pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
            salida.append(pix.tobytes("jpeg", jpg_quality=85))
            del pix
        return salida, total
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# El link
# ---------------------------------------------------------------------------

def cliente_http() -> httpx.AsyncClient:
    """El cliente con el que se baja. En un solo lugar para que las pruebas lo
    cambien por uno con respuestas grabadas (httpx.MockTransport), sin red.
    Las redirecciones se siguen a mano (`_pedir`): cada salto se controla."""
    return httpx.AsyncClient(timeout=httpx.Timeout(ESPERA_LINK), follow_redirects=False)


async def _resolver(host: str) -> list[str]:
    """Las IPs a las que apunta un nombre (o la IP misma, si ya lo es)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def _ip_privada(ip: str) -> bool:
    """Si una IP es de la red interna, loopback, link-local (169.254.x: la
    metadata de la nube), multicast, reservada o no ruteable: nada de eso se
    abre desde el servidor."""
    try:
        a = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return True
    if a.version == 6 and a.ipv4_mapped is not None:
        a = a.ipv4_mapped
    return bool(a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
                or a.is_unspecified or not a.is_global)


async def _host_publico(url: httpx.URL) -> None:
    """NoSePudoAbrir si el link no es http(s) o apunta a la red interna. Se
    resuelve el nombre ANTES de conectar: si alguna de sus IPs es privada, no
    se abre (para que nadie use esto para pegarle a la red interna de
    Render)."""
    if url.scheme not in ("http", "https"):
        raise NoSePudoAbrir("solo se abren links http o https")
    host = url.host
    if not host:
        raise NoSePudoAbrir("el link no tiene un servidor")
    try:
        ips = await _resolver(host)
    except (socket.gaierror, OSError, UnicodeError) as exc:
        raise NoSePudoAbrir(f"no se encontró el servidor {host}") from exc
    if not ips or any(_ip_privada(ip) for ip in ips):
        raise NoSePudoAbrir("el link apunta a una dirección interna y no se abre")


def _ip_del_servidor(respuesta: httpx.Response) -> str | None:
    """A qué IP se conectó de verdad (httpcore lo expone en la conexión), por
    si el nombre cambió entre que se controló y se conectó (DNS rebinding).
    None si no se sabe (un transporte simulado)."""
    stream = respuesta.extensions.get("network_stream")
    if stream is None:
        return None
    try:
        direccion = stream.get_extra_info("server_addr")
    except Exception:
        return None
    return str(direccion[0]) if direccion else None


@dataclass
class Respuesta:
    url: str                   # la final, después de las redirecciones
    estado: int
    cabeceras: httpx.Headers
    cuerpo: bytes


async def _pedir(cliente: httpx.AsyncClient, metodo: str, url: str | httpx.URL, *, tope: int,
                 json_cuerpo: dict | None = None, cabeceras: dict | None = None) -> Respuesta:
    """Un pedido con los cuidados: cada salto de redirección (hasta 3) pasa
    por `_host_publico`, se controla la IP real de la conexión y el cuerpo se
    corta en `tope` bytes."""
    actual = httpx.URL(url)
    for _ in range(MAX_REDIRECCIONES + 1):
        await _host_publico(actual)
        pedido = cliente.build_request(
            metodo, actual, json=json_cuerpo, headers={"User-Agent": _AGENTE, **(cabeceras or {})},
        )
        try:
            r = await cliente.send(pedido, stream=True)
        except httpx.TimeoutException as exc:
            raise NoSePudoAbrir("el servidor tardó demasiado en contestar") from exc
        except httpx.HTTPError as exc:
            raise NoSePudoAbrir(f"no se pudo conectar ({type(exc).__name__})") from exc
        try:
            ip = _ip_del_servidor(r)
            if ip and _ip_privada(ip):
                raise NoSePudoAbrir("el link apunta a una dirección interna y no se abre")
            if r.status_code in (301, 302, 303, 307, 308):
                destino = r.headers.get("location")
                if not destino:
                    raise NoSePudoAbrir("el link redirige a ningún lado")
                actual = actual.join(destino)
                if r.status_code in (301, 302, 303) and metodo != "GET":
                    metodo, json_cuerpo = "GET", None
                continue
            largo = r.headers.get("content-length", "")
            if largo.isdigit() and int(largo) > tope:
                raise NoSePudoAbrir(f"el archivo pesa más de {_mb(tope)}")
            cuerpo = bytearray()
            try:
                async for trozo in r.aiter_bytes():
                    cuerpo += trozo
                    if len(cuerpo) > tope:
                        raise NoSePudoAbrir(f"el archivo pesa más de {_mb(tope)}")
            except httpx.TimeoutException as exc:
                raise NoSePudoAbrir("la descarga tardó demasiado") from exc
            except httpx.HTTPError as exc:
                raise NoSePudoAbrir(f"se cortó la descarga ({type(exc).__name__})") from exc
            return Respuesta(str(actual), r.status_code, r.headers, bytes(cuerpo))
        finally:
            await r.aclose()
    raise NoSePudoAbrir("el link redirige demasiadas veces")


_HOSTS_WETRANSFER = ("we.tl", "wetransfer.com", "www.wetransfer.com")
_HOSTS_SMASH = ("fromsmash.com", "www.fromsmash.com", "fromsmash.co")
# /downloads/<transferencia>/<hash> o /downloads/<transferencia>/<destinatario>/<hash>
_DESCARGA_WETRANSFER = re.compile(r"^/downloads/([0-9a-f]{6,64})(?:/([0-9a-f]{6,64}))?/([0-9a-f]{4,64})/?$")
_CSRF = re.compile(r'name="csrf-token"\s+content="([^"]+)"')
_NOMBRE_ADJUNTO = re.compile(r"""filename\*?=(?:UTF-8'')?["']?([^"';]+)""", re.IGNORECASE)


def clase_de_link(url: str) -> str:
    """'wetransfer', 'smash' o 'directo' (cualquier otro: se baja tal cual)."""
    try:
        host = (httpx.URL(url).host or "").casefold()
    except Exception:
        return "directo"
    if host in _HOSTS_WETRANSFER:
        return "wetransfer"
    if host in _HOSTS_SMASH or host.endswith((".fromsmash.com", ".fromsmash.co")):
        return "smash"
    return "directo"


def _nombre_del_archivo(respuesta: Respuesta, por_defecto: str = "archivo del link") -> str:
    """El nombre que dice el servidor (Content-Disposition) o el último
    pedazo del link; corto y sin barras."""
    m = _NOMBRE_ADJUNTO.search(respuesta.cabeceras.get("content-disposition", ""))
    nombre = unquote(m.group(1)).strip() if m else ""
    if not nombre:
        nombre = unquote(httpx.URL(respuesta.url).path.rsplit("/", 1)[-1]).strip()
    nombre = nombre.replace("\\", "/").rsplit("/", 1)[-1]
    return nombre[:120] or por_defecto


async def _bajar_wetransfer(cliente: httpx.AsyncClient, url: str) -> Respuesta:
    """La descarga de WeTransfer, como la hacen las herramientas de línea de
    comandos (sin credenciales): la página del link trae un token CSRF y la
    cookie de sesión; con ellos, POST a api/v4/transfers/{id}/download con la
    security hash del link (y el id del destinatario, si el link es de un
    mail) devuelve `direct_link`, que es el archivo (un ZIP, si son varios).
    Un we.tl corto redirige a la página larga: lo resuelve `_pedir`."""
    pagina = await _pedir(cliente, "GET", url, tope=_MAX_BYTES_PAGINA, cabeceras={"Accept": "text/html"})
    final = httpx.URL(pagina.url)
    partes = _DESCARGA_WETRANSFER.match(final.path) if (final.host or "").casefold() in _HOSTS_WETRANSFER else None
    if pagina.estado != 200 or partes is None:
        raise NoSePudoAbrir("el link de WeTransfer venció o no es el de una transferencia")
    transferencia, destinatario, seguridad = partes.groups()
    cabeceras = {"x-requested-with": "XMLHttpRequest", "Accept": "application/json"}
    token = _CSRF.search(pagina.cuerpo.decode("utf-8", "replace"))
    if token:
        cabeceras["x-csrf-token"] = token.group(1)
    cuerpo = {"intent": "entire_transfer", "security_hash": seguridad}
    if destinatario:
        cuerpo["recipient_id"] = destinatario
    api = await _pedir(
        cliente, "POST", f"https://wetransfer.com/api/v4/transfers/{transferencia}/download",
        tope=_MAX_BYTES_API, json_cuerpo=cuerpo, cabeceras=cabeceras,
    )
    if api.estado != 200:
        raise NoSePudoAbrir(
            f"WeTransfer no dejó bajar la transferencia (contestó {api.estado}): venció, pide contraseña o "
            "cambió su página. Pasalo como ZIP"
        )
    try:
        directo = (json.loads(api.cuerpo) or {}).get("direct_link")
    except ValueError:
        directo = None
    if not isinstance(directo, str) or not directo:
        raise NoSePudoAbrir("WeTransfer no devolvió el link de descarga. Pasalo como ZIP")
    return await _pedir(cliente, "GET", directo, tope=MAX_BYTES_LINK)


def _parece_html(datos: bytes) -> bool:
    arranque = datos[:1024].lstrip().lower()
    return arranque.startswith((b"<!doctype", b"<html", b"<head", b"<?xml")) or b"<html" in arranque


async def _bajar_link(url: str) -> tuple[str, bytes, str]:
    """(nombre, bytes, clase) de lo que hay detrás de un link: 'imagen',
    'pdf' o 'zip'. NoSePudoAbrir con el porqué si no se puede."""
    clase = clase_de_link(url)
    if clase == "smash":
        raise NoSePudoAbrir(
            "los links de Smash no se pueden bajar desde la plataforma (su descarga necesita su API con "
            "credenciales): pedile a la agencia el ZIP o un link directo al archivo"
        )
    async with cliente_http() as cliente:
        if clase == "wetransfer":
            r = await _bajar_wetransfer(cliente, url)
        else:
            r = await _pedir(cliente, "GET", url, tope=MAX_BYTES_LINK)
    if r.estado != 200:
        raise NoSePudoAbrir(f"el servidor contestó {r.estado}")
    datos = r.cuerpo
    nombre = _nombre_del_archivo(r)
    if tipo_de_imagen(datos):
        return nombre, datos, "imagen"
    if datos[:5] == b"%PDF-":
        return nombre, datos, "pdf"
    if datos[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return nombre, datos, "zip"
    if _parece_html(datos):
        raise NoSePudoAbrir(
            "el link devolvió una página web y no un archivo (¿es privado, venció o pide iniciar sesión?). "
            "Pasalo como ZIP"
        )
    raise NoSePudoAbrir("lo que hay en el link no es una imagen, un PDF ni un ZIP")


def _sumar_descarga(j: Juntado, nombre: str, datos: bytes, clase: str, lugar: int) -> None:
    """Lo bajado del link, a la IA (sincrónico y pesado: en un hilo)."""
    if clase == "zip":
        extraer_del_zip(datos, j, lugar=lugar, origen="link")
        return
    if lugar <= 0:
        j.no_se_pudo_abrir.append(f"«{nombre}»: quedó afuera por el tope de imágenes por entrega")
        return
    if clase == "imagen":
        j.imagenes.append(preparar_imagen(None, datos, tipo_de_imagen(datos), nombre=nombre, origen="link"))
        j.revisados.append({"nombre": nombre, "origen": "link", "paginas": None})
        return
    paginas, total = paginas_de_pdf(datos, max_paginas=min(MAX_PAGINAS_PDF, lugar))
    _anotar_paginas(j, nombre, "link", paginas, total, lugar)


def _link_corto(url: str) -> str:
    try:
        u = httpx.URL(url)
        return f"{u.host}{u.path}"[:80]
    except Exception:
        return url[:80]


async def juntar(
    *, zip_datos: bytes | None, zip_nombre: str | None, link: str | None, lugar: int,
    zip_saltar: frozenset[int] = frozenset(),
) -> Juntado:
    """Todo lo que hay que sumarle a la IA además de las imágenes subidas: lo
    del ZIP y lo del link, hasta `lugar` imágenes en total. No levanta: lo
    que no se pudo abrir queda anotado con el porqué, para la persona. Lo
    pesado (descomprimir, renderizar) corre en un hilo, para no frenar al
    resto del servidor."""
    j = Juntado()
    if zip_datos:
        nombre = zip_nombre or "el ZIP"
        try:
            await asyncio.to_thread(
                extraer_del_zip, zip_datos, j, lugar=max(0, lugar - len(j.imagenes)), saltar=zip_saltar,
            )
        except ValueError as exc:
            j.no_se_pudo_abrir.append(f"No se pudo abrir el ZIP «{nombre}»: {exc}")
        except Exception as exc:
            logger.warning("materiales: falló el ZIP «%s» — %s: %s", nombre, type(exc).__name__, exc)
            j.no_se_pudo_abrir.append(f"No se pudo abrir el ZIP «{nombre}»")
    if link and link.strip():
        link = link.strip()
        try:
            nombre, datos, clase = await asyncio.wait_for(_bajar_link(link), timeout=ESPERA_TOTAL_LINK)
            await asyncio.to_thread(_sumar_descarga, j, nombre, datos, clase, max(0, lugar - len(j.imagenes)))
        except NoSePudoAbrir as exc:
            j.no_se_pudo_abrir.append(f"No se pudo abrir el link ({_link_corto(link)}): {exc}")
        except asyncio.TimeoutError:
            j.no_se_pudo_abrir.append(f"No se pudo abrir el link ({_link_corto(link)}): tardó demasiado")
        except ValueError as exc:
            j.no_se_pudo_abrir.append(f"No se pudo abrir el link ({_link_corto(link)}): {exc}")
        except Exception as exc:
            logger.warning("materiales: falló el link %s — %s: %s", _link_corto(link), type(exc).__name__, exc)
            j.no_se_pudo_abrir.append(f"No se pudo abrir el link ({_link_corto(link)})")
    return j
