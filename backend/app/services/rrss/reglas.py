"""Las reglas FIJAS de la Validación de RRSS, leídas del ÚNICO lugar donde viven.

Ese lugar es ``app/data/rrss_reglas.json`` (ver su "_porque"). Son las que se
exigen siempre, contra un mailing o contra una planilla: el legal de bases y
condiciones, la leyenda de alcohol, y cómo va el precio de un combo.

NO HAY VALOR DE RESERVA, igual que en archivos.py: si el archivo no está o le
falta un texto, esto revienta al importar. Un legal por defecto escrito acá
sería una segunda copia del que está en el JSON, que es justo lo que no tiene
que existir.
"""
from __future__ import annotations

import json
import pathlib
import re

_RUTA = pathlib.Path(__file__).parent.parent.parent / "data" / "rrss_reglas.json"


def _cargar() -> dict:
    try:
        crudo = json.loads(_RUTA.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - se ve en el arranque
        raise RuntimeError(
            f"no está {_RUTA}. Ese archivo es la ÚNICA fuente de las reglas fijas de la "
            f"Validación de RRSS (legales y combos)."
        ) from exc
    for clave, campo in (
        ("legal_bases", "texto"), ("legal_alcohol", "texto"), ("combo", "unidad"),
        ("adaptaciones", "cantidad"),
    ):
        if not (crudo.get(clave) or {}).get(campo):
            raise RuntimeError(f"{_RUTA}: falta {clave}.{campo}")
    return crudo


REGLAS = _cargar()

LEGAL_BASES: str = REGLAS["legal_bases"]["texto"]
LEGAL_ALCOHOL: str = REGLAS["legal_alcohol"]["texto"]
UNIDAD: str = REGLAS["combo"]["unidad"]
# Cuántas adaptaciones tiene que tener cada producto destacado. Menos es un
# error; más, una advertencia (ver el "porque" en el JSON).
ADAPTACIONES: int = int(REGLAS["adaptaciones"]["cantidad"])

# "Comprando 2", "comprando 3": el texto de arriba del precio de un combo.
_RE_COMPRANDO = re.compile(r"^\s*comprando\s+\d+", re.IGNORECASE)


def es_combo(mecanica: str, encabezado: str) -> bool:
    """¿Es un combo? Lo es si tiene mecánica ('2x$75', '4x3 Combinables', '2x1')
    o si arriba del precio dice 'Comprando N'. Cualquiera de las dos alcanza:
    Ivan lo dijo así ("cuando son combos o dicen comprando 2 o comprando 3")."""
    return bool((mecanica or "").strip()) or bool(_RE_COMPRANDO.match(encabezado or ""))
