"""Qué archivos acepta la Validación de RRSS, leído del ÚNICO lugar donde vive.

Ese lugar es ``app/data/rrss_archivos.json``. Acá se lee para el backend; el
navegador lo recibe en ``GET /rrss/config`` y arma con eso el ``accept`` de los
inputs y los textos de la pantalla. Ni un tipo escrito a mano de este lado ni
del otro (ver el "_porque" del JSON).

NO HAY VALOR DE RESERVA, igual que en cenefas/reglas_medicion.py: si el archivo
no está o le falta una clave, esto revienta al importar. Una lista de tipos por
defecto sería aceptar en silencio algo que nadie decidió aceptar, y el arranque
del backend (``python -c "import app.main"`` en CI) es el lugar bueno para que
se note.
"""
from __future__ import annotations

import json
import pathlib

_RUTA = pathlib.Path(__file__).parent.parent.parent / "data" / "rrss_archivos.json"


def _cargar() -> dict:
    try:
        crudo = json.loads(_RUTA.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - se ve en el arranque
        raise RuntimeError(
            f"no está {_RUTA}. Ese archivo es la ÚNICA fuente de los tipos de archivo "
            f"que acepta la Validación de RRSS: sin él el backend y la pantalla "
            f"aceptarían cada uno lo suyo."
        ) from exc
    for clave in ("placas", "fuentes"):
        if clave not in crudo:
            raise RuntimeError(f"{_RUTA} no tiene la clave {clave!r}")
    for nombre in ("mailing", "planilla"):
        if nombre not in crudo["fuentes"]:
            raise RuntimeError(f"{_RUTA} no tiene la fuente {nombre!r}")
    for nombre, tipo in [("placas", crudo["placas"]), *crudo["fuentes"].items()]:
        if not isinstance(tipo.get("max_mb"), int):
            raise RuntimeError(f"{_RUTA}: {nombre!r} no tiene un 'max_mb' entero")
    if not isinstance(crudo["fuentes"]["planilla"].get("max_filas"), int):
        raise RuntimeError(f"{_RUTA}: la planilla no tiene un 'max_filas' entero")
    return crudo


TIPOS: dict = _cargar()

# Los content_type de las planillas son un desastre según el navegador y el
# sistema: Chrome en Windows manda a veces application/vnd.ms-excel para un
# .xlsx, y un .csv puede llegar como text/plain o directamente vacío. Por eso la
# EXTENSIÓN manda y el content_type es solo un respaldo -- mismo criterio que ya
# tenía imagenes.paginas_del_mailing, que reconocía el PDF por sus bytes y no
# por lo que dijera el navegador.


def _extension(filename: str) -> str:
    nombre = (filename or "").lower()
    punto = nombre.rfind(".")
    return nombre[punto:] if punto > 0 else ""


def etiqueta_placas() -> str:
    return TIPOS["placas"]["etiqueta"]


def etiqueta_fuente(nombre: str) -> str:
    return TIPOS["fuentes"][nombre]["etiqueta"]


def acepta_placa(filename: str, content_type: str) -> bool:
    placas = TIPOS["placas"]
    return _extension(filename) in placas["extensiones"] or (content_type or "") in placas["content_types"]


def acepta_fuente(filename: str, content_type: str) -> bool:
    """¿Este archivo se puede usar como fuente, sea mailing o planilla?

    `origen_de` no sirve para esto: contesta CUÁL de los dos caminos, y manda
    todo lo que no reconoce al camino del mailing. Un .docx arrastrado entraba
    por ahí y terminaba en un 400 que hablaba de imágenes."""
    ext = _extension(filename)
    tipo = content_type or ""
    return any(
        ext in fuente["extensiones"] or tipo in fuente["content_types"]
        for fuente in TIPOS["fuentes"].values()
    )


def max_mb(nombre: str) -> int:
    """Cuántos MB puede pesar un archivo de este tipo ('placas', 'mailing' o
    'planilla'). Sale del mismo JSON que los tipos aceptados, y la pantalla lo
    recibe en GET /rrss/config: el tamaño máximo estaba escrito a mano en la
    ruta y en ningún lado del navegador."""
    tipo = TIPOS["placas"] if nombre == "placas" else TIPOS["fuentes"][nombre]
    return tipo["max_mb"]


def max_bytes(nombre: str) -> int:
    return max_mb(nombre) * 1024 * 1024


def max_filas(nombre: str) -> int:
    """Cuántas filas puede traer una fuente de datos. Hoy solo la planilla tiene
    filas; vive en el mismo JSON que el resto de las reglas de archivo porque lo
    usan los DOS lados: el backend para rechazar (planilla.MAX_FILAS) y la
    pantalla para decir el número antes de que alguien suba el catálogo
    entero."""
    return TIPOS["fuentes"][nombre]["max_filas"]


def origen_de(filename: str, content_type: str) -> str:
    """'planilla' o 'mailing' para el archivo que se subió como fuente.

    Lo que no es reconocible como planilla se trata como mailing: ese camino ya
    sabe rechazar con un motivo entendible lo que no puede abrir
    (imagenes.ArchivoInvalido), y así un .pdf con un content_type raro sigue
    entrando como siempre."""
    planilla = TIPOS["fuentes"]["planilla"]
    if _extension(filename) in planilla["extensiones"]:
        return "planilla"
    if (content_type or "") in planilla["content_types"] and _extension(filename) not in TIPOS["fuentes"]["mailing"]["extensiones"]:
        return "planilla"
    return "mailing"
