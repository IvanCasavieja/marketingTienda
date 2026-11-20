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
  - WeTransfer (we.tl, go.wetransfer.com, wetransfer.com y las páginas de
    marca, <marca>.wetransfer.com) muestra una página, no el archivo: la
    descarga sale de su API (`_bajar_wetransfer`), sin cuenta, con los
    mismos dos pedidos que hace el botón Descargar de su página. Un link de
    download.wetransfer.com ya es el archivo y se baja directo.
  - Smash (fromsmash.com y <equipo>.fromsmash.com) tampoco pide cuenta para
    bajar (19/11/2026, Ivan: «yo bajo sin smash los links»): su página crea
    sola un invitado, sin datos, y con ese token resuelve el link y pide el
    link firmado de descarga. `_bajar_smash` hace lo mismo.
  Las dos son APIs sin documentar para terceros (se revisaron el 19/11/2026
  contra lo que hacen hoy sus páginas): si cambian, el link queda como "no
  se pudo abrir" y no se rompe nada más. Lo que no se puede bajar sin
  cuenta (con contraseña, vencido, borrado, más pesado que el tope, que pide
  el mail de quien baja) queda anotado con el porqué.
- **Un PDF**: una imagen por página, hasta 10, con PyMuPDF (ya estaba en el
  servidor por la validación de RRSS), al mismo lado máximo que las imágenes
  que van a la IA.

Nada de esto levanta hacia afuera: lo que no se pudo abrir queda en
`Juntado.no_se_pudo_abrir` con el porqué, para la persona. Corre en segundo
plano, después de contestar la entrega (revision_ia.revisar_version): la
entrega no espera la descarga. Lo que sale de acá va a la IA como las
imágenes subidas, con el nombre del archivo en cada observación; lo que la
IA mira de acá NO se guarda como imagen: el aprobador ve las imágenes de la
ronda y, de lo demás, lo que la IA encontró.

**El ZIP, desde el 19/11/2026, se guarda tal cual** como el original de la
ronda (calendario_version_zips, ver app/models/entregas.py: Ivan, "cuando lo
subís deberías de subir la carpeta comprimida, no los archivos sueltos"). Y
al entregar, lo que el navegador no pudo mostrar sale de acá como imágenes de
la ronda (`imagenes_para_la_ronda`): sobre todo las páginas de los PDF (un
folleto), que antes no se veían y hacían rechazar un ZIP con solo PDF. Esas
se guardan como cualquier imagen de la ronda, achicadas igual que en el
navegador, y la IA no las vuelve a mirar (`saltar` y `paginas_hechas` en
`extraer_del_zip`).
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import logging
import math
import re
import socket
import struct
import threading
import time
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, quote, unquote, urlsplit

import httpcore
import httpx

from app.services.entregas import (
    CALIDAD_JPEG, LADO_MAYOR, LADO_MINIATURA, MAX_BYTES_IMAGEN, MAX_BYTES_MINIATURA, tipo_de_imagen,
)
from app.services.revision_ia import LADO_MAXIMO, MAX_PIXELES, ImagenParaIA, preparar_imagen

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
_MAX_BYTES_API = 256 * 1024            # lo que contestan las APIs de WeTransfer y Smash
_AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/131.0.0.0 Safari/537.36 CoreTienda/1.0")

# El PDF
MAX_PAGINAS_PDF = 10

# Lo pesado (un PDF abierto, una imagen grande decodificada), de a uno en todo
# el proceso: PyMuPDF no se puede usar desde dos hilos a la vez (su
# documentación avisa que puede tirar abajo el proceso), y dos imágenes
# grandes juntas en 512 MB son demasiado. Lo usan la entrega, en el pedido
# (imagenes_para_la_ronda), y la IA, en segundo plano (extraer_del_zip), cada
# una desde su hilo. Reentrante, por si una función de acá llama a otra.
_DE_A_UNO = threading.RLock()


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


def _anotar_paginas(
    j: Juntado, nombre: str, origen: str, paginas: list[bytes], total: int, lugar: int, desde: int = 0,
) -> int:
    """Suma las páginas renderizadas de un PDF (ya al lado máximo) y anota el
    archivo. `desde`: cuántas páginas, de la 1 en adelante, ya van como
    imágenes de la ronda (la IA las ve ahí): estas son las que siguen, y se
    numeran como en el PDF. Devuelve cuántas imágenes agregó."""
    n = 0
    for i, datos in enumerate(paginas, desde + 1):
        if n >= lugar:
            break
        j.imagenes.append(preparar_imagen(None, datos, "image/jpeg", nombre=nombre, origen=origen, pagina=i))
        n += 1
    if n:
        j.revisados.append({"nombre": nombre, "origen": origen, "paginas": n})
    vistas = desde + n
    if vistas < total:
        j.no_se_pudo_abrir.append(
            f"«{nombre}»: se revisaron las primeras {vistas} páginas de {total}"
            + (f" (tope de {MAX_PAGINAS_PDF} páginas por PDF)" if vistas >= MAX_PAGINAS_PDF else " (tope de imágenes por entrega)")
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
    paginas_hechas: Mapping[int, int] | None = None,
) -> int:
    """Saca del ZIP las imágenes y los PDF (como imágenes, una por página) y
    los suma a `juntado`, hasta `lugar` imágenes: lo que no entra queda
    anotado. Lo que no es imagen ni PDF va a `ignorados`. Devuelve cuántas
    imágenes agregó. ValueError si el ZIP entero no sirve (ver
    inspeccionar_zip). Es sincrónica y pesada (descomprime, abre imágenes,
    renderiza PDF): se llama desde un hilo.

    Lo que ya es imagen de la ronda la IA lo ve ahí, y no se mira dos veces:
    - `saltar`: los lugares en el índice de lo que ya está entero en la ronda
      (las imágenes que subió el navegador, las que la persona sacó a
      propósito, y lo que el servidor pasó a la ronda al entregar, ver
      `imagenes_para_la_ronda`);
    - `paginas_hechas`: de un PDF que pasó a la ronda solo en parte, cuántas
      páginas (de la 1 en adelante): se miran las que siguen."""
    entradas = inspeccionar_zip(datos)
    hechas_por_pdf = paginas_hechas or {}
    agregadas = 0
    with zipfile.ZipFile(io.BytesIO(datos)) as zf:
        for e in entradas:
            if e.indice in saltar:
                continue
            if e.clase == "otro":
                juntado.ignorados.append(e.nombre)
                continue
            hechas = hechas_por_pdf.get(e.indice, 0) if e.clase == "pdf" else 0
            if agregadas >= lugar:
                juntado.no_se_pudo_abrir.append(
                    f"«{e.nombre}»: se revisaron solo las páginas que van como imágenes de la ronda "
                    "(tope de imágenes por entrega)" if hechas
                    else f"«{e.nombre}»: quedó afuera por el tope de imágenes por entrega"
                )
                continue
            try:
                contenido = _leer_entrada(zf, e)
                if e.clase == "imagen":
                    tipo = tipo_de_imagen(contenido)
                    if tipo is None:
                        raise NoSePudoAbrir("no es una imagen JPG, PNG ni WebP (aunque el nombre lo diga)")
                    with _DE_A_UNO:
                        juntado.imagenes.append(preparar_imagen(None, contenido, tipo, nombre=e.nombre, origen=origen))
                    juntado.revisados.append({"nombre": e.nombre, "origen": origen, "paginas": None})
                    agregadas += 1
                else:
                    paginas, total = paginas_de_pdf(
                        contenido, desde=hechas, max_paginas=min(MAX_PAGINAS_PDF - hechas, lugar - agregadas),
                    )
                    agregadas += _anotar_paginas(juntado, e.nombre, origen, paginas, total, lugar - agregadas, desde=hechas)
            except (NoSePudoAbrir, ValueError) as exc:
                juntado.no_se_pudo_abrir.append(f"«{e.nombre}»: {exc}")
            except Exception as exc:  # un archivo roto no tira la revisión entera
                logger.warning("materiales: no se pudo abrir «%s» del ZIP — %s: %s", e.nombre, type(exc).__name__, exc)
                juntado.no_se_pudo_abrir.append(f"«{e.nombre}»: no se pudo abrir")
    return agregadas


# ---------------------------------------------------------------------------
# El PDF (puro)
# ---------------------------------------------------------------------------

def _abrir_pdf(datos: bytes):
    """El PDF abierto con PyMuPDF, o ValueError con el porqué para la persona
    (dañado, o pide contraseña). Quien lo abre lo cierra."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=datos, filetype="pdf")
    except Exception as exc:
        raise ValueError("no se pudo leer el PDF (¿está dañado?)") from exc
    if doc.needs_pass:
        doc.close()
        raise ValueError("el PDF está protegido con contraseña")
    return doc


def _pixmap_de_pagina(pagina, lado: int):
    """La página dibujada, con su lado mayor en `lado` píxeles, sobre blanco."""
    import pymupdf

    mayor = max(pagina.rect.width, pagina.rect.height) or 1.0
    # Los puntos del PDF son 1/72 de pulgada: una A4 mide 842 de alto, así
    # que a 1600 px es ~1,9x (137 dpi). Un sello de 2 cm no se agranda más de
    # 8x: no tendría sentido una imagen gigante.
    escala = min(lado / mayor, 8.0)
    return pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)


def _soltar_memoria_del_pdf() -> None:
    """PyMuPDF guarda lo que decodifica (las fotos de adentro de un PDF) en
    un depósito que puede llegar a 256 MB, y el servidor tiene 512: se vacía
    después de cada página."""
    import pymupdf

    try:
        pymupdf.TOOLS.store_shrink(100)
    except Exception:  # una versión que no lo tenga: no es para cortar nada
        pass


def paginas_de_pdf(
    datos: bytes, *, max_paginas: int = MAX_PAGINAS_PDF, lado: int = LADO_MAXIMO, desde: int = 0,
) -> tuple[list[bytes], int]:
    """Hasta `max_paginas` páginas como JPEG (lado mayor `lado`, como las
    imágenes que van a la IA), empezando por la página `desde` + 1 (las
    anteriores ya van como imágenes de la ronda), y cuántas páginas tiene en
    total. ValueError si no se puede leer o pide contraseña. De a una página
    en memoria, y un PDF por vez en todo el proceso (`_DE_A_UNO`)."""
    with _DE_A_UNO:
        doc = _abrir_pdf(datos)
        try:
            total = doc.page_count
            salida: list[bytes] = []
            for i in range(max(0, desde), min(total, max(0, desde) + max(0, max_paginas))):
                pix = _pixmap_de_pagina(doc[i], lado)
                salida.append(pix.tobytes("jpeg", jpg_quality=85))
                del pix
                _soltar_memoria_del_pdf()
            return salida, total
        finally:
            doc.close()
            _soltar_memoria_del_pdf()


# ---------------------------------------------------------------------------
# Lo del ZIP que pasa a ser imagen de la ronda, al entregar (puro)
# ---------------------------------------------------------------------------
# Ivan (19/11/2026) no entendía por qué un ZIP con solo el PDF del folleto no
# alcanzaba para entregar: "no debería pasar". El navegador saca las imágenes
# del ZIP, pero un PDF no lo puede dibujar sin una librería. Así que al
# entregar, si quedan lugares de imagen en la ronda (MAX_IMAGENES menos las
# subidas), el servidor los llena con lo del ZIP, en su orden: las imágenes
# que el navegador no subió (no pudo abrir el ZIP, o esa imagen) y las páginas
# de los PDF. Quedan guardadas como cualquier imagen de la ronda, con su
# miniatura, achicadas igual que en el navegador (LADO_MAYOR, LADO_MINIATURA y
# CALIDAD_JPEG en app/services/entregas.py), así quien aprueba las ve y las
# marca. Una cosa por vez y una página por vez: el servidor tiene 512 MB.

@dataclass
class ImagenDeLaRonda:
    datos: bytes        # JPEG, lado mayor LADO_MAYOR
    miniatura: bytes    # JPEG, lado mayor LADO_MINIATURA
    indice: int         # de qué entrada del ZIP salió (su lugar en el índice)
    nombre: str
    pagina: int | None  # si es la página de un PDF, cuál (desde 1)


@dataclass
class SacadoDelZip:
    imagenes: list[ImagenDeLaRonda] = field(default_factory=list)
    # Lo que ya quedó entero en la ronda (imágenes, y PDF con todas sus
    # páginas adentro): la IA no lo vuelve a mirar.
    entradas: set[int] = field(default_factory=set)
    # De los PDF que entraron en parte: cuántas páginas, de la 1 en adelante.
    paginas: dict[int, int] = field(default_factory=dict)
    # Lo que no se pudo pasar a la ronda, con el porqué (para la persona, si
    # del ZIP no sale nada).
    no_se_pudo: list[str] = field(default_factory=list)


def _a_rgb(img):
    """La imagen en RGB; lo transparente, sobre blanco (como el navegador: un
    PNG transparente en JPEG saldría con el fondo negro)."""
    from PIL import Image

    if img.has_transparency_data:
        con_alfa = img.convert("RGBA")
        fondo = Image.new("RGB", con_alfa.size, "white")
        fondo.paste(con_alfa, mask=con_alfa.getchannel("A"))
        return fondo
    return img if img.mode == "RGB" else img.convert("RGB")


def _jpeg(img, lado: int) -> bytes:
    """Como `aJpeg` del navegador: lado mayor `lado` (nunca se agranda, y con
    el mismo redondeo), JPEG con CALIDAD_JPEG. `img` ya en RGB; no se toca."""
    from PIL import Image

    escala = min(1.0, lado / max(img.width, img.height, 1))
    if escala < 1.0:
        img = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))), Image.LANCZOS)
    salida = io.BytesIO()
    img.save(salida, "JPEG", quality=CALIDAD_JPEG)
    return salida.getvalue()


def _grande_y_miniatura(img) -> tuple[bytes, bytes]:
    """La imagen de la ronda y su miniatura, con los mismos topes que una que
    sube el navegador (ValueError si se pasa, que con 1600 px no pasa)."""
    grande = _jpeg(img, LADO_MAYOR)
    if len(grande) > MAX_BYTES_IMAGEN:
        raise ValueError("sigue pesando demasiado después de achicarla")
    mini = _jpeg(img, LADO_MINIATURA)
    if len(mini) > MAX_BYTES_MINIATURA:
        raise ValueError("su miniatura pesa demasiado")
    return grande, mini


def _imagen_de_la_ronda(contenido: bytes) -> tuple[bytes, bytes]:
    """Una imagen del ZIP, achicada para la ronda y derecha según su EXIF
    (el navegador la muestra derecha). Un JPG grande se lee ya achicado
    (`draft` decodifica a 1/2, 1/4 u 1/8 sin bajar de LADO_MAYOR): una foto
    de 24 MP no llega a ocupar su tamaño entero en memoria."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if tipo_de_imagen(contenido) is None:
        raise NoSePudoAbrir("no es una imagen JPG, PNG ni WebP (aunque el nombre lo diga)")
    with _DE_A_UNO:
        try:
            img = Image.open(io.BytesIO(contenido))  # solo el encabezado
            if img.width * img.height > MAX_PIXELES:
                raise NoSePudoAbrir(f"es demasiado grande ({img.width} x {img.height})")
            img.draft(None, (LADO_MAYOR, LADO_MAYOR))
            img.thumbnail((LADO_MAYOR, LADO_MAYOR), Image.LANCZOS)
            img = _a_rgb(ImageOps.exif_transpose(img))
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise NoSePudoAbrir("no se pudo leer la imagen") from exc
        return _grande_y_miniatura(img)


def _paginas_de_la_ronda(contenido: bytes, cuantas: int) -> tuple[list[tuple[bytes, bytes]], int]:
    """Las primeras `cuantas` páginas de un PDF como imágenes de la ronda
    (grande y miniatura), dibujadas de a una, y cuántas páginas tiene. Un PDF
    por vez en todo el proceso (`_DE_A_UNO`)."""
    from PIL import Image

    with _DE_A_UNO:
        doc = _abrir_pdf(contenido)
        try:
            total = doc.page_count
            salida: list[tuple[bytes, bytes]] = []
            for i in range(min(total, max(0, cuantas))):
                pix = _pixmap_de_pagina(doc[i], LADO_MAYOR)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                del pix
                salida.append(_grande_y_miniatura(img))
                del img
                _soltar_memoria_del_pdf()
            return salida, total
        finally:
            doc.close()
            _soltar_memoria_del_pdf()


def imagenes_para_la_ronda(datos: bytes, *, lugar: int, saltar: frozenset[int] = frozenset()) -> SacadoDelZip:
    """Lo del ZIP que pasa a la ronda al entregar, hasta `lugar` imágenes y en
    el orden del ZIP: las imágenes que no están en `saltar` (las que el
    navegador ya subió, o la persona sacó a propósito) y las páginas de los
    PDF. Lo que no se puede abrir se anota y se sigue con lo próximo; nunca
    levanta por un archivo de adentro (ValueError solo si el ZIP entero no
    sirve, ver inspeccionar_zip). Sincrónica y pesada: se llama en un hilo."""
    s = SacadoDelZip()
    if lugar <= 0:
        return s
    entradas = inspeccionar_zip(datos)
    with zipfile.ZipFile(io.BytesIO(datos)) as zf:
        for e in entradas:
            if len(s.imagenes) >= lugar:
                break
            if e.clase == "otro" or e.indice in saltar:
                continue
            contenido = None
            try:
                contenido = _leer_entrada(zf, e)
                if e.clase == "imagen":
                    grande, mini = _imagen_de_la_ronda(contenido)
                    s.imagenes.append(ImagenDeLaRonda(grande, mini, e.indice, e.nombre, None))
                    s.entradas.add(e.indice)
                else:
                    paginas, total = _paginas_de_la_ronda(contenido, lugar - len(s.imagenes))
                    for n, (grande, mini) in enumerate(paginas, 1):
                        s.imagenes.append(ImagenDeLaRonda(grande, mini, e.indice, e.nombre, n))
                    if paginas and len(paginas) >= total:
                        s.entradas.add(e.indice)
                    elif paginas:
                        s.paginas[e.indice] = len(paginas)
            except (NoSePudoAbrir, ValueError) as exc:
                s.no_se_pudo.append(f"«{e.nombre}»: {exc}")
            except Exception as exc:  # un archivo raro no tira la entrega
                logger.warning("materiales: no se pudo pasar «%s» del ZIP a la ronda — %s: %s",
                               e.nombre, type(exc).__name__, exc)
                s.no_se_pudo.append(f"«{e.nombre}»: no se pudo abrir")
            finally:
                # Que el archivo de adentro (hasta 40 MB) se suelte antes de
                # abrir el siguiente.
                contenido = None
    return s


# ---------------------------------------------------------------------------
# El link
# ---------------------------------------------------------------------------

class _RedPublica(httpcore.AsyncNetworkBackend):
    """La red con la que se conecta el cliente de los links: resuelve el
    nombre, controla que TODAS sus IPs sean públicas y se conecta a una de
    esas mismas IPs (19/11/2026). Así el control y la conexión no pueden
    separarse: antes se controlaba el nombre y httpx resolvía otra vez al
    conectar, y un DNS que cambia en el medio (o dos formas de escribir el
    nombre) llegaba a la red interna antes de que se cortara. Lo de TLS no
    cambia: el certificado se controla contra el nombre del link."""

    def __init__(self) -> None:
        self._red = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            ips = await _resolver(host)
        except (socket.gaierror, OSError, UnicodeError) as exc:
            raise NoSePudoAbrir(f"no se encontró el servidor {host}") from exc
        if not ips or any(_ip_privada(ip) for ip in ips):
            raise NoSePudoAbrir("el link apunta a una dirección interna y no se abre")
        ultimo: Exception | None = None
        for ip in ips:
            try:
                return await self._red.connect_tcp(
                    ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                ultimo = exc
        raise ultimo or httpcore.ConnectError("no se pudo conectar")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise NoSePudoAbrir("solo se abren links http o https")

    async def sleep(self, seconds: float) -> None:
        await self._red.sleep(seconds)


def cliente_http() -> httpx.AsyncClient:
    """El cliente con el que se baja. En un solo lugar para que las pruebas lo
    cambien por uno con respuestas grabadas (httpx.MockTransport), sin red.
    Las redirecciones se siguen a mano (`_pedir`): cada salto se controla.
    Se conecta con `_RedPublica`: httpx no deja pasarle la red, así que se
    pone en su pileta de conexiones; si una versión nueva de httpx la
    cambiara, esto falla (y el link queda anotado como que no se abrió),
    nunca se conecta sin el control. Hay una prueba que lo vigila."""
    transporte = httpx.AsyncHTTPTransport()
    pileta = transporte._pool
    if not hasattr(pileta, "_network_backend"):
        raise NoSePudoAbrir("la plataforma no puede abrir links con esta versión de httpx")
    pileta._network_backend = _RedPublica()
    return httpx.AsyncClient(transport=transporte, timeout=httpx.Timeout(ESPERA_LINK), follow_redirects=False)


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
    # Se resuelve el nombre como lo usa la conexión (raw_host, con IDNA):
    # url.host puede ser otro («faß» vs «xn--fa-hia»), y con dos nombres un
    # atacante pasaba el control con uno y conectaba con el otro (19/11/2026).
    try:
        ips = await _resolver(url.raw_host.decode("ascii"))
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


# Lo que no pasa a otro servidor si un pedido redirige, como en los
# navegadores: el token de invitado de Smash y su contraseña (19/11/2026).
_CABECERAS_PRIVADAS = frozenset({"authorization", "smash-authorization", "cookie"})


async def _pedir(cliente: httpx.AsyncClient, metodo: str, url: str | httpx.URL, *, tope: int,
                 json_cuerpo: dict | None = None, cabeceras: dict | None = None,
                 solo_destino: bool = False) -> Respuesta:
    """Un pedido con los cuidados: cada salto de redirección (hasta 3) pasa
    por `_host_publico`, se controla la IP real de la conexión y el cuerpo se
    corta en `tope` bytes. Si un salto lleva a otro servidor, el token no
    viaja (`_CABECERAS_PRIVADAS`). `solo_destino`: solo importa adónde lleva
    (la página de un link de WeTransfer): el cuerpo no se lee."""
    actual = httpx.URL(url)
    cabeceras = dict(cabeceras or {})
    for _ in range(MAX_REDIRECCIONES + 1):
        await _host_publico(actual)
        # identity: que el servidor no mande nada comprimido. Si lo manda igual,
        # se abre una sola capa y con tope (ver abajo): unos pocos bytes
        # comprimidos dos veces inflaban cientos de MB de una (19/11/2026).
        pedido = cliente.build_request(
            metodo, actual, json=json_cuerpo,
            headers={"User-Agent": _AGENTE, "Accept-Encoding": "identity", **cabeceras},
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
                siguiente = actual.join(destino)
                if (siguiente.scheme, siguiente.host, siguiente.port) != (actual.scheme, actual.host, actual.port):
                    cabeceras = {k: v for k, v in cabeceras.items() if k.casefold() not in _CABECERAS_PRIVADAS}
                actual = siguiente
                if r.status_code in (301, 302, 303) and metodo != "GET":
                    metodo, json_cuerpo = "GET", None
                continue
            if solo_destino:
                return Respuesta(str(actual), r.status_code, r.headers, b"")
            largo = r.headers.get("content-length", "")
            if largo.isdigit() and int(largo) > tope:
                raise NoSePudoAbrir(f"el archivo pesa más de {_mb(tope)}")
            cuerpo = await _leer_con_tope(r, tope)
            return Respuesta(str(actual), r.status_code, r.headers, cuerpo)
        finally:
            await r.aclose()
    raise NoSePudoAbrir("el link redirige demasiadas veces")


async def _leer_con_tope(r: httpx.Response, tope: int) -> bytes:
    """El cuerpo, cortado en `tope` bytes YA descomprimidos. Se lee crudo
    (aiter_raw): httpx descomprime solo y sin tope, así que una «bomba» de
    pocos bytes (gzip dentro de gzip) se comía la memoria antes de cualquier
    control (revisión del 19/11/2026). Se acepta una sola capa de gzip o
    deflate, abierta de a pedazos y con tope; cualquier otra cosa se anota."""
    demasiado = NoSePudoAbrir(f"el archivo pesa más de {_mb(tope)}")
    if r.is_stream_consumed:
        # Ya leída: solo pasa con respuestas armadas en memoria (las pruebas);
        # una de la red llega sin leer (send con stream=True).
        if len(r.content) > tope:
            raise demasiado
        return r.content
    capas = [c.strip().casefold() for c in r.headers.get("content-encoding", "").split(",")]
    capas = [c for c in capas if c and c != "identity"]
    if len(capas) > 1 or (capas and capas[0] not in ("gzip", "x-gzip", "deflate")):
        raise NoSePudoAbrir("el servidor mandó el archivo comprimido de una forma que no se abre")
    # wbits 47: gzip o zlib, lo que venga, una sola capa.
    abrir = zlib.decompressobj(wbits=47) if capas else None
    cuerpo = bytearray()
    try:
        async for trozo in r.aiter_raw():
            if abrir is not None:
                trozo = abrir.decompress(trozo, tope + 1 - len(cuerpo))
                if abrir.unconsumed_tail:
                    raise demasiado
            cuerpo += trozo
            if len(cuerpo) > tope:
                raise demasiado
        if abrir is not None:
            cuerpo += abrir.flush(tope + 1 - len(cuerpo))
            if len(cuerpo) > tope or abrir.unconsumed_tail:
                raise demasiado
    except zlib.error as exc:
        raise NoSePudoAbrir("el archivo llegó dañado") from exc
    except httpx.TimeoutException as exc:
        raise NoSePudoAbrir("la descarga tardó demasiado") from exc
    except httpx.HTTPError as exc:
        raise NoSePudoAbrir(f"se cortó la descarga ({type(exc).__name__})") from exc
    return bytes(cuerpo)


# WeTransfer (revisado el 19/11/2026 contra lo que hace hoy su página). Los
# links cortos redirigen a la página larga. download.wetransfer.com ya es el
# archivo (un link firmado): se baja directo. collect.wetransfer.com (los
# tableros) usa otra API: queda como "no es el de una transferencia".
_CORTOS_WETRANSFER = ("we.tl", "go.wetransfer.com", "shorturls.wetransfer.com")
_ARCHIVO_WETRANSFER = "download.wetransfer.com"
# .../downloads/<transferencia>/<hash> o .../downloads/<transferencia>/<destinatario>/<hash>
_DESCARGA_WETRANSFER = re.compile(r"/downloads/([0-9a-f]{6,64})(?:/([0-9a-f]{6,64}))?/([0-9a-f]{4,64})/?$")
_NOMBRE_ADJUNTO = re.compile(r"""filename\*?=(?:UTF-8'')?["']?([^"';]+)""", re.IGNORECASE)

# Smash (19/11/2026): los servidores y las versiones de su API, como los usa
# hoy fromsmash.com. Las regiones son las de sus SDK: la penúltima letra del
# id de una transferencia dice en cuál está.
_REGIONES_SMASH = {
    "a": "eu-west-1", "b": "eu-west-2", "c": "eu-west-3", "d": "eu-central-1", "e": "us-east-1",
    "f": "us-east-2", "g": "us-west-1", "h": "us-west-2", "i": "ca-central-1",
}
# Si no contesta la que elige su página: la que usa JDownloader desde 2021.
_REGION_SMASH = "eu-central-1"
_CABECERAS_SMASH = {
    # Sin este Accept, algunas respuestas vienen en XML (JDownloader, 2021).
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://fromsmash.com",
    "Referer": "https://fromsmash.com/",
}
_ID_SMASH = re.compile(r"[A-Za-z0-9_-]{4,128}")
# El token del invitado de Smash: dura un día y se reusa hasta 5 minutos
# antes de que venza, para no crear un invitado nuevo por cada link.
_TOKEN_SMASH: dict = {}
_ESTADOS_SMASH = {
    "Expired": "la transferencia de Smash venció: pedile a la agencia que la mande de nuevo",
    "Deleted": "la transferencia de Smash fue borrada",
    "Deleting": "la transferencia de Smash fue borrada",
    "Suspended": "Smash suspendió esa transferencia",
    "Uploading": "la transferencia de Smash todavía se estaba subiendo",
}
_SMASH_RARO = "Smash contestó algo que la plataforma no entiende (¿cambió su página?)"


def clase_de_link(url: str) -> str:
    """'wetransfer', 'smash' o 'directo' (cualquier otro: se baja tal cual,
    también un link firmado de download.wetransfer.com o uno de fromsmash.co,
    que es la API de Smash y no una página para compartir)."""
    try:
        host = (httpx.URL(url).host or "").casefold()
    except Exception:
        return "directo"
    if host == _ARCHIVO_WETRANSFER or host.endswith("." + _ARCHIVO_WETRANSFER):
        return "directo"
    if host in _CORTOS_WETRANSFER or host == "wetransfer.com" or host.endswith(".wetransfer.com"):
        return "wetransfer"
    if host == "fromsmash.com" or host.endswith(".fromsmash.com"):
        return "smash"
    return "directo"


def _nombre_del_archivo(respuesta: Respuesta, por_defecto: str = "archivo del link", *,
                        sugerido: str | None = None) -> str:
    """El nombre que dice el servidor (Content-Disposition), el que sugiere
    WeTransfer o Smash, o el último pedazo del link; corto y sin barras."""
    m = _NOMBRE_ADJUNTO.search(respuesta.cabeceras.get("content-disposition", ""))
    nombre = unquote(m.group(1)).strip() if m else ""
    if not nombre and sugerido:
        nombre = sugerido.strip()
    if not nombre:
        nombre = unquote(httpx.URL(respuesta.url).path.rsplit("/", 1)[-1]).strip()
    nombre = nombre.replace("\\", "/").rsplit("/", 1)[-1]
    return nombre[:120] or por_defecto


def _json(r: Respuesta) -> dict:
    """Lo que contestó una API, como objeto JSON ({} si no lo es)."""
    try:
        datos = json.loads(r.cuerpo)
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def _con_contrasena(servicio: str) -> NoSePudoAbrir:
    return NoSePudoAbrir(
        f"la transferencia de {servicio} tiene contraseña: pedile a la agencia un link sin contraseña o el ZIP"
    )


def _controlar_peso(tamano: object, servicio: str) -> None:
    """Si WeTransfer o Smash ya dicen que la transferencia pesa más que el
    tope, no se baja para cortarla a la mitad: se anota."""
    if isinstance(tamano, (int, float)) and not isinstance(tamano, bool) and tamano > MAX_BYTES_LINK:
        raise NoSePudoAbrir(
            # Para arriba: 40,05 MB no puede decir «pesa 40 MB» si el tope es 40.
            f"la transferencia de {servicio} pesa {math.ceil(tamano / 1024 / 1024)} MB y la plataforma baja "
            f"hasta {_mb(MAX_BYTES_LINK)}"
        )


def _motivo_wetransfer(r: Respuesta) -> NoSePudoAbrir:
    """Por qué WeTransfer no deja bajar, en palabras de la persona (los
    mensajes de su API son los que distingue su página)."""
    cuerpo = _json(r)
    mensaje = str(cuerpo.get("message") or cuerpo.get("error") or "")
    if mensaje == "invalid_transfer_password":
        return _con_contrasena("WeTransfer")
    if mensaje == "No download access to this Transfer":
        return NoSePudoAbrir(
            "WeTransfer pide una cuenta o verificar el mail de quien baja esa transferencia: pedile a la "
            "agencia un link sin ese control o el ZIP"
        )
    if r.estado == 404 or mensaje == "invalid_transfer":
        return NoSePudoAbrir("la transferencia de WeTransfer venció o la borraron")
    if r.estado == 429:
        return NoSePudoAbrir("WeTransfer pidió esperar: hubo demasiados pedidos seguidos")
    return NoSePudoAbrir(f"WeTransfer no dejó bajar la transferencia (contestó {r.estado})")


async def _bajar_wetransfer(cliente: httpx.AsyncClient, url: str) -> tuple[Respuesta, str | None]:
    """La descarga de WeTransfer sin cuenta, con los dos pedidos que hace el
    botón Descargar de su página (revisado el 19/11/2026):
    POST api/v4/transfers/{id}/prepare-download, con la hash del link (y el
    id del destinatario si el link es de un mail), dice si se puede bajar,
    si tiene contraseña y cuánto pesa; POST .../download devuelve
    `direct_link`, un link firmado que dura unos minutos y es el archivo (un
    ZIP, si son varios).

    Su página ya no trae el token CSRF que se mandaba antes (su web no lo
    usa más): no hace falta abrirla. Solo se abre la de un link corto, de
    marca o con www, y sin leerla: para saber en qué servidor termina, que
    es donde está la API (como en el navegador). Devuelve la descarga y el
    nombre que sugiere WeTransfer."""
    pagina = httpx.URL(url)
    if (pagina.host or "").casefold() != "wetransfer.com":
        pagina = httpx.URL((await _pedir(cliente, "GET", pagina, tope=0, solo_destino=True)).url)
    host = (pagina.host or "").casefold()
    es_pagina = host == "wetransfer.com" or host.endswith(".wetransfer.com")
    partes = _DESCARGA_WETRANSFER.search(pagina.path) if es_pagina else None
    if partes is None:
        raise NoSePudoAbrir("el link de WeTransfer venció o no es el de una transferencia")
    transferencia, destinatario, seguridad = partes.groups()
    origen = f"https://{host}"
    cabeceras = {"Accept": "application/json", "Origin": origen, "Referer": str(pagina)}
    cuerpo = {"security_hash": seguridad}
    if destinatario:
        cuerpo["recipient_id"] = destinatario
    api = f"{origen}/api/v4/transfers/{transferencia}"
    r = await _pedir(cliente, "POST", f"{api}/prepare-download", tope=_MAX_BYTES_API, json_cuerpo=cuerpo,
                     cabeceras=cabeceras)
    if r.estado != 200:
        raise _motivo_wetransfer(r)
    info = _json(r)
    if not info:
        # Una página en vez del JSON (¿una verificación de "no soy un robot"?
        # no se vio nunca, pero su web la tiene): que no diga "venció".
        raise NoSePudoAbrir("WeTransfer contestó algo que la plataforma no entiende (¿cambió su página?)")
    # Con contraseña contesta 200 igual, pero sin la lista de archivos.
    if info.get("password_protected"):
        raise _con_contrasena("WeTransfer")
    if info.get("state") != "downloadable":
        raise NoSePudoAbrir("la transferencia de WeTransfer venció o ya no se puede bajar")
    _controlar_peso(info.get("size"), "WeTransfer")
    r = await _pedir(cliente, "POST", f"{api}/download", tope=_MAX_BYTES_API,
                     json_cuerpo={**cuerpo, "intent": "entire_transfer"}, cabeceras=cabeceras)
    if r.estado != 200:
        raise _motivo_wetransfer(r)
    directo = _json(r).get("direct_link")
    if not isinstance(directo, str) or not directo:
        raise NoSePudoAbrir("WeTransfer no devolvió el link de descarga (¿cambió su página?)")
    sugerido = info.get("recommended_filename")
    descarga = await _pedir(cliente, "GET", directo, tope=MAX_BYTES_LINK)
    return descarga, sugerido if isinstance(sugerido, str) else None


def _uri(texto: str) -> str:
    """Como encodeURIComponent de JavaScript (la «/» pasa a %2F)."""
    return quote(texto, safe="-_.!~*'()")


def _vence(expiracion: object, ahora: float) -> float:
    """Cuándo vence el token de Smash (viene como "2026-11-20T18:00:00.000Z");
    si no se entiende, se usa una hora."""
    try:
        return datetime.fromisoformat(str(expiracion).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return ahora + 3600


async def _region_smash(cliente: httpx.AsyncClient) -> str:
    """Dónde pedir el invitado: la región que elige la página de Smash (su
    discovery, que redirige al de cada región); si no contesta, una fija."""
    try:
        r = await _pedir(cliente, "GET", "https://discovery.fromsmash.co/namespace/public/services?version=02-2023",
                         tope=_MAX_BYTES_API, cabeceras=_CABECERAS_SMASH)
    except NoSePudoAbrir:
        return _REGION_SMASH
    region = _json(r).get("region") if r.estado == 200 else None
    return region if region in _REGIONES_SMASH.values() else _REGION_SMASH


async def _token_smash(cliente: httpx.AsyncClient, *, nuevo: bool = False) -> str:
    """El token del invitado, como lo crea la página de Smash para cualquiera
    que abre un link: POST /account sin datos ({}) y sin credenciales. Se
    guarda hasta que vence (`_TOKEN_SMASH`); `nuevo` pide otro igual."""
    ahora = time.time()
    if not nuevo and _TOKEN_SMASH.get("vence", 0) > ahora + 300:
        return _TOKEN_SMASH["token"]
    region = await _region_smash(cliente)
    r = await _pedir(cliente, "POST", f"https://iam.{region}.fromsmash.co/account", tope=_MAX_BYTES_API,
                     json_cuerpo={}, cabeceras=_CABECERAS_SMASH)
    cuenta = _json(r).get("account")
    token = cuenta.get("token") if isinstance(cuenta, dict) else None
    valor = token.get("token") if isinstance(token, dict) else None
    if r.estado not in (200, 201) or not isinstance(valor, str) or not valor:
        raise NoSePudoAbrir(f"Smash no dejó entrar como invitado (contestó {r.estado})")
    _TOKEN_SMASH.clear()
    _TOKEN_SMASH.update(token=valor, vence=_vence(token.get("expiration"), ahora))
    return valor


def _motivo_smash(r: Respuesta) -> NoSePudoAbrir:
    """Por qué Smash no deja bajar, en palabras de la persona. Sus errores
    vienen como {name, code, error, ...}: manda el `name` (como en su SDK) y,
    por las dudas, el texto."""
    cuerpo = _json(r)
    nombre = str(cuerpo.get("name") or "")
    texto = str(cuerpo.get("error") or "").casefold()
    if r.estado == 404:
        return NoSePudoAbrir(
            "Smash dice que esa transferencia no existe (venció, la borraron o el link está mal copiado)"
        )
    if r.estado == 403:
        if nombre.startswith("PasswordDoesNotMatch") or "password" in texto:
            return _con_contrasena("Smash")
        if nombre.startswith("InvalidEmail") or "email" in texto:
            return NoSePudoAbrir(
                "Smash pide el mail de quien baja esa transferencia: pedile a la agencia un link sin ese "
                "control o el ZIP"
            )
        if nombre.startswith(("OwnerUsageExceeded", "AccessorUsageExceeded")):
            return NoSePudoAbrir("la transferencia de Smash llegó a su límite de descargas")
    if r.estado == 401:
        return NoSePudoAbrir("Smash no dejó entrar como invitado (contestó 401)")
    if r.estado == 429:
        return NoSePudoAbrir("Smash pidió esperar: hubo demasiados pedidos seguidos")
    return NoSePudoAbrir(f"Smash no dejó bajar la transferencia (contestó {r.estado})")


async def _api_smash(cliente: httpx.AsyncClient, metodo: str, url: str, *, json_cuerpo: dict | None = None,
                     de_transferencia: bool = False) -> dict:
    """Un pedido a la API de Smash como invitado: el JSON de la respuesta, o
    NoSePudoAbrir con el porqué. Si contesta 401 (el token guardado venció
    o lo dieron de baja), se pide otro y se repite una vez."""

    async def pedir(token: str) -> Respuesta:
        cabeceras = {**_CABECERAS_SMASH, "Authorization": f"Bearer {token}"}
        if de_transferencia:
            # La contraseña de la transferencia: su página la manda vacía
            # cuando no hay. Las que tienen se anotan (_motivo_smash).
            cabeceras["smash-authorization"] = ""
        return await _pedir(cliente, metodo, url, tope=_MAX_BYTES_API, json_cuerpo=json_cuerpo,
                            cabeceras=cabeceras)

    r = await pedir(await _token_smash(cliente))
    if r.estado == 401:
        r = await pedir(await _token_smash(cliente, nuevo=True))
    if r.estado != 200:
        raise _motivo_smash(r)
    return _json(r)


async def _bajar_smash(cliente: httpx.AsyncClient, url: str) -> tuple[Respuesta, str | None]:
    """La descarga de Smash sin cuenta, con los pedidos que hace su página
    para quien recibe el link (revisado el 19/11/2026 contra fromsmash.com,
    su SDK y JDownloader), con el token del invitado (`_token_smash`):

    1. el link (servidor y ruta, sin la consulta) dice qué transferencia es
       y en qué región está (link.fromsmash.co/target);
    2. la transferencia dice si se puede bajar (vencida, borrada...) y
       cuánto pesa (/preview);
    3. como el botón Descargar: si es un archivo solo, se pide el link
       firmado de ese archivo (su id sale de /files/preview); si son
       varios, el de todos juntos en un ZIP (/urls);
    4. el link firmado dura unos minutos y se baja sin el token.

    Devuelve la descarga y el nombre del archivo, si es uno solo."""
    partes = urlsplit(url.strip())
    host = (partes.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]  # www.fromsmash.com redirige a fromsmash.com
    ruta = partes.path.rstrip("/")
    if not ruta:
        raise NoSePudoAbrir("el link de Smash no es el de una transferencia")
    datos = await _api_smash(cliente, "GET", f"https://link.fromsmash.co/target/{_uri(host + ruta)}?version=10-2019")
    target = datos.get("target") if isinstance(datos.get("target"), dict) else {}
    transferencia = target.get("target")
    if not isinstance(transferencia, str) or not _ID_SMASH.fullmatch(transferencia):
        raise NoSePudoAbrir(_SMASH_RARO)
    region = target.get("region")
    if region not in _REGIONES_SMASH.values():
        region = _REGIONES_SMASH.get(transferencia[-2])
        if region is None:
            raise NoSePudoAbrir(_SMASH_RARO)
    base = f"https://transfer.{region}.fromsmash.co/transfer/{transferencia}"
    # Los links que manda Smash por mail traen `e` (el mail de quien lo
    # recibe): va tal cual, como en su página.
    e = parse_qs(partes.query).get("e", [""])[0]
    consulta = "version=01-2024" + (f"&e={_uri(e)}" if e else "")

    transfer = (await _api_smash(cliente, "GET", f"{base}/preview?{consulta}", de_transferencia=True)).get("transfer")
    if not isinstance(transfer, dict):
        raise NoSePudoAbrir(_SMASH_RARO)
    estado = str(transfer.get("status") or "")
    if estado not in ("Uploaded", "Processing"):
        raise NoSePudoAbrir(_ESTADOS_SMASH.get(estado, "Smash no deja bajar esa transferencia ahora"))
    _controlar_peso(transfer.get("size"), "Smash")

    nombre = None
    if transfer.get("filesNumber") == 1:
        lista = (await _api_smash(cliente, "GET", f"{base}/files/preview?{consulta}&limit=1",
                                  de_transferencia=True)).get("files")
        archivo = lista[0] if isinstance(lista, list) and lista and isinstance(lista[0], dict) else {}
        if not isinstance(archivo.get("id"), str):
            raise NoSePudoAbrir(_SMASH_RARO)
        nombre = archivo.get("name") if isinstance(archivo.get("name"), str) else None
        pedido = {"files": [{"id": archivo["id"]}]}
    else:
        pedido = {"files": []}
    firmados = (await _api_smash(cliente, "PUT", f"{base}/urls?{consulta}", json_cuerpo=pedido,
                                 de_transferencia=True)).get("transfer")
    firmados = firmados if isinstance(firmados, dict) else {}
    if pedido["files"]:
        lista = firmados.get("files")
        firmado = lista[0].get("url") if isinstance(lista, list) and lista and isinstance(lista[0], dict) else None
    else:
        firmado = firmados.get("url")
    if not isinstance(firmado, str) or not firmado:
        raise NoSePudoAbrir(_SMASH_RARO)
    return await _pedir(cliente, "GET", firmado, tope=MAX_BYTES_LINK), nombre


def _parece_html(datos: bytes) -> bool:
    arranque = datos[:1024].lstrip().lower()
    return arranque.startswith((b"<!doctype", b"<html", b"<head", b"<?xml")) or b"<html" in arranque


async def _bajar_link(url: str) -> tuple[str, bytes, str]:
    """(nombre, bytes, clase) de lo que hay detrás de un link: 'imagen',
    'pdf' o 'zip'. NoSePudoAbrir con el porqué si no se puede."""
    clase = clase_de_link(url)
    sugerido = None
    async with cliente_http() as cliente:
        if clase == "wetransfer":
            r, sugerido = await _bajar_wetransfer(cliente, url)
        elif clase == "smash":
            r, sugerido = await _bajar_smash(cliente, url)
        else:
            r = await _pedir(cliente, "GET", url, tope=MAX_BYTES_LINK)
    if r.estado != 200:
        raise NoSePudoAbrir(f"el servidor contestó {r.estado}")
    datos = r.cuerpo
    nombre = _nombre_del_archivo(r, sugerido=sugerido)
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
        with _DE_A_UNO:
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
    zip_saltar: frozenset[int] = frozenset(), zip_paginas: Mapping[int, int] | None = None,
) -> Juntado:
    """Todo lo que hay que sumarle a la IA además de las imágenes de la
    ronda: lo del ZIP (menos lo que ya es imagen de la ronda: `zip_saltar` y
    `zip_paginas`, ver extraer_del_zip) y lo del link, hasta `lugar` imágenes
    en total. No levanta: lo que no se pudo abrir queda anotado con el
    porqué, para la persona. Lo pesado (descomprimir, renderizar) corre en un
    hilo, para no frenar al resto del servidor."""
    j = Juntado()
    if zip_datos:
        nombre = zip_nombre or "el ZIP"
        try:
            await asyncio.to_thread(
                extraer_del_zip, zip_datos, j, lugar=max(0, lugar - len(j.imagenes)), saltar=zip_saltar,
                paginas_hechas=zip_paginas,
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
