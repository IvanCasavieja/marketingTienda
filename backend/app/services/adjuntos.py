"""Los archivos del pedido de una tarea: qué se acepta, cuánto, y de qué
tareas se ven (0089, ver app/models/adjuntos.py).

Pedido de Ivan (24/11/2026): "en el brief de las tareas deberíamos poder
adjuntar archivos, como el Excel por ejemplo".

Qué se acepta: Excel (.xlsx, .xls), CSV, PDF, Word (.docx, .doc), imágenes
(.jpg, .png, .webp, .gif) y ZIP. Se mira la extensión Y lo que hay adentro
(`validar`): un .exe renombrado a .xlsx no pasa. Cuánto: hasta
MAX_BYTES_ADJUNTO por archivo y MAX_ADJUNTOS por tarea; entre todos, el tope
ADJUNTOS_TOPE_MB de app/core/config.py.

Lo de la base (`cadena_de`, `lista`) y lo puro (`validar`, `nombre_limpio`,
`puede_adjuntar`) están juntos; lo puro se prueba sin base
(tests/test_adjuntos_del_pedido.py). Las rutas están en
app/api/routes/adjuntos.py.
"""
from __future__ import annotations

import io
import secrets
import zipfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adjuntos import CalendarioAdjunto
from app.models.calendario import CalendarioTarea

MB = 1024 * 1024
# Un Excel de 1.000 productos pesa unos 140 KB; un PDF con referencias, unos
# pocos MB. Más grande que esto, va como link en el detalle.
MAX_BYTES_ADJUNTO = 10 * MB
# Por tarea (los que se le adjuntaron a ella; los que vienen de la tarea de
# la que cuelga no cuentan acá).
MAX_ADJUNTOS = 5
# Tarea → subtarea → sub-subtarea (calendario._NIVELES_DE_TAREA).
_NIVELES = 3

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # .xls y .doc (los de antes de 2007)


def _zip_con(datos: bytes, carpeta: str | None) -> bool:
    """Si es un ZIP de verdad y, con `carpeta`, si trae algo adentro de ella
    (un .xlsx es un ZIP con xl/, un .docx uno con word/). Lee solo el índice
    del ZIP: no descomprime nada."""
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            nombres = z.namelist()
    except Exception:  # noqa: BLE001 — cualquier cosa que no se pueda abrir no es un ZIP
        return False
    return carpeta is None or any(n.startswith(carpeta) for n in nombres)


def _es_texto(datos: bytes) -> bool:
    # Un CSV es texto: sin bytes en cero. Un Excel, un PDF o una imagen
    # renombrados a .csv los tienen enseguida.
    return b"\x00" not in datos[:65536]


# extensión → (tipo, cómo se dice, si lo que tiene adentro es eso)
TIPOS: dict[str, tuple[str, str, object]] = {
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "un Excel",
             lambda d: _zip_con(d, "xl/")),
    "xls": ("application/vnd.ms-excel", "un Excel", lambda d: d[:8] == _OLE),
    "csv": ("text/csv", "un CSV", _es_texto),
    "pdf": ("application/pdf", "un PDF", lambda d: b"%PDF-" in d[:1024]),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "un Word",
             lambda d: _zip_con(d, "word/")),
    "doc": ("application/msword", "un Word", lambda d: d[:8] == _OLE),
    "jpg": ("image/jpeg", "una imagen JPG", lambda d: d[:3] == b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", "una imagen JPG", lambda d: d[:3] == b"\xff\xd8\xff"),
    "png": ("image/png", "una imagen PNG", lambda d: d[:8] == b"\x89PNG\r\n\x1a\n"),
    "webp": ("image/webp", "una imagen WEBP", lambda d: d[:4] == b"RIFF" and d[8:12] == b"WEBP"),
    "gif": ("image/gif", "una imagen GIF", lambda d: d[:6] in (b"GIF87a", b"GIF89a")),
    "zip": ("application/zip", "un ZIP", lambda d: _zip_con(d, None)),
}

QUE_SE_PUEDE = "Excel, CSV, PDF, Word, imágenes (JPG, PNG, WEBP o GIF) y ZIP"


def _mb(n: int) -> str:
    return f"{n / MB:.1f}".replace(".", ",")


def extension(nombre: str) -> str:
    return nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""


def nombre_limpio(nombre: str | None) -> str:
    """El nombre con el que se guarda y se baja: sin la carpeta, sin
    caracteres de control y de hasta 255 (cortando antes de la extensión).
    Pura."""
    n = (nombre or "").replace("\\", "/").split("/")[-1]
    n = " ".join("".join(c for c in n if c.isprintable()).split())
    if not n:
        return "archivo"
    if len(n) > 255:
        ext = extension(n)
        # El nombre se corta antes de la extensión, así se sigue abriendo.
        n = f"{n[: 254 - len(ext)]}.{ext}" if ext and len(ext) <= 10 else n[:255]
    return n


def validar(nombre: str | None, datos: bytes, maximo: int = MAX_BYTES_ADJUNTO) -> tuple[str, str]:
    """(nombre limpio, tipo) si el archivo se puede adjuntar; si no, un
    ValueError con qué hacer, para la persona. Mira la extensión y además
    que adentro sea eso. Pura."""
    limpio = nombre_limpio(nombre)
    if not datos:
        raise ValueError(f"«{limpio}» está vacío.")
    if len(datos) > maximo:
        raise ValueError(
            f"«{limpio}» pesa más de {_mb(maximo)} MB, que es lo máximo por archivo. "
            "Si es más grande, dejá el link en el detalle."
        )
    tipo = TIPOS.get(extension(limpio))
    if tipo is None:
        raise ValueError(f"«{limpio}»: ese tipo de archivo no se puede adjuntar. Se puede: {QUE_SE_PUEDE}.")
    mime, como, es = tipo
    if not es(datos):  # type: ignore[operator]
        raise ValueError(
            f"«{limpio}» dice ser {como} pero adentro es otra cosa (¿le cambiaron la extensión?). "
            "Guardalo de nuevo desde el programa con el que se hizo."
        )
    return limpio, mime


def puede_adjuntar(usuario_id: int, creado_por_id: int | None, *, gestiona: bool, pide: bool) -> bool:
    """Quién adjunta y saca archivos del pedido de una tarea: quien gestiona
    las tareas (calendario.tareas), y quien la creó si pide piezas
    (calendario.pedidos), que es quien las crea y edita. La agencia nunca
    (ni `gestiona` ni `pide` le dan true: externos.puede_tener). Pura."""
    return gestiona or (pide and creado_por_id is not None and creado_por_id == usuario_id)


def nuevo_id() -> str:
    return f"ad-{secrets.token_hex(8)}"


async def cadena_de(db: AsyncSession, tarea: CalendarioTarea) -> list[CalendarioTarea]:
    """La tarea y las tareas de las que cuelga, de abajo para arriba: sus
    adjuntos son los que ve quien mira esta tarea. El Excel de una tarea lo
    ven sus piezas (las tarjetas de las agencias)."""
    cadena = [tarea]
    actual = tarea
    while actual.parent_id and len(cadena) < _NIVELES:
        actual = await db.get(CalendarioTarea, actual.parent_id)
        if actual is None:
            break
        cadena.append(actual)
    return cadena


async def lista(
    db: AsyncSession, tarea: CalendarioTarea, usuario_id: int, *, gestiona: bool, pide: bool, externo: bool,
) -> list[dict]:
    """Los adjuntos que se ven en `tarea`: los suyos primero y después los de
    las tareas de las que cuelga (`heredado`), sin los bytes. A una cuenta
    externa no le viaja el nombre de la tarea de la que viene (es del
    equipo)."""
    cadena = await cadena_de(db, tarea)
    de = {t.id: t for t in cadena}
    filas = (await db.execute(
        select(CalendarioAdjunto.id, CalendarioAdjunto.tarea_id, CalendarioAdjunto.nombre,
               CalendarioAdjunto.tipo_mime, CalendarioAdjunto.tamano, CalendarioAdjunto.created_at)
        .where(CalendarioAdjunto.tarea_id.in_(list(de)))
        .order_by(CalendarioAdjunto.created_at, CalendarioAdjunto.id)
    )).all()
    out = []
    for aid, tid, nombre, mime, tamano, fecha in filas:
        heredado = tid != tarea.id
        out.append({
            "id": aid, "nombre": nombre, "tipo": mime, "tamano": tamano,
            "fecha": fecha.isoformat() if fecha else None,
            "heredado": heredado,
            "deLaTarea": de[tid].titulo if heredado and not externo else None,
            "puedoSacar": puede_adjuntar(usuario_id, de[tid].creado_por_id, gestiona=gestiona, pide=pide),
        })
    out.sort(key=lambda a: a["heredado"])
    return out
