"""Formateo puro — sin I/O ni PPTX.

Quedaron solo tres funciones. Las constantes de layout (tamanos de fuente en
pt del precio, la descripcion y demas) y parse_combo vivian acá para el motor
de render viejo y la lógica de combos del generador; los dos se eliminaron en
08/2026 -- el motor respeta el PPTX tal cual y los combos los resuelve el
Convertidor (ver convertidor_variables.py).
"""
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

# ---------------------------------------------------------------------------
# Precio
# ---------------------------------------------------------------------------

def fmt_price(value: Any) -> str:
    """Precio en formato uruguayo: "899", "1.234", "1.234,50".

    Se redondea a centavos ANTES de partir entero y decimales. Antes la parte
    entera se tomaba por truncamiento --int(value)-- y los decimales por
    redondeo --f"{value:.2f}"--, así que cuando el redondeo se llevaba uno, el
    entero no se enteraba: un precio de Excel salido de una fórmula
    (729 x 0,7 = 510.9999999999999) se imprimía **$510** en un cartel que
    tenía que decir **$511**. Se ve poco porque hace falta que el valor caiga
    justo debajo de un entero, pero cuando pasa es plata mal impresa.

    Se usa Decimal sobre la representación decimal del número, no float: en
    binario 0,1 + 0,2 no da 0,3 y el redondeo a mitad queda al azar.
    """
    if value is None:
        return "0"
    d = Decimal(str(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    signo = "-" if d < 0 else ""
    d = abs(d)
    entero = int(d)
    centavos = int((d - entero) * 100)
    ent_str = f"{entero:,}".replace(",", ".") if entero >= 1000 else str(entero)
    if centavos == 0:
        return signo + ent_str
    return f"{signo}{ent_str},{centavos:02d}"


def parse_price_raw(value: Any) -> float:
    """Convierte valor crudo a float. Soporta formatos europeos y strings con texto."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    m = re.match(r"^(\d[\d.,]*)", str(value).strip())
    if not m:
        return 0.0
    num_str = m.group(1)
    if "." in num_str and "," in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        num_str = num_str.replace(",", ".")
    try:
        return float(num_str)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Bold detection para marcas en ALL-CAPS
# ---------------------------------------------------------------------------

def split_caps(text: str) -> list[tuple[str, bool]]:
    """Divide texto en segmentos (texto, es_bold). Las palabras ALL-CAPS van en bold."""
    pattern = r"([A-Z]{2,}[A-Z0-9\-/]*(?:\s+[A-Z]{2,}[A-Z0-9\-/]*)*)"
    parts = re.split(pattern, text)
    result = []
    for part in parts:
        if not part:
            continue
        is_bold = bool(re.fullmatch(
            r"[A-Z]{2,}[A-Z0-9\-/]*(?:\s+[A-Z]{2,}[A-Z0-9\-/]*)*", part
        ))
        result.append((part, is_bold))
    return result
