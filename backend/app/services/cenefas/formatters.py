"""Pure formatting utilities — sin dependencias de I/O ni PPTX."""
import re
from typing import Any

# ---------------------------------------------------------------------------
# Layout constants (usados por render_engine)
# ---------------------------------------------------------------------------

P1_FONT_SIZE  = 32      # pt — label "Precio Final" / "6X"
P1_BOLD       = False
P1_MARGIN_EMU = 466400  # distancia top de P1 al top del shape de precio

PRICE_SYMBOL_PT   = 199 # pt — símbolo de moneda ($, U$S) en precio principal
PRICE_INT_PT      = 239 # pt — entero del precio principal
PRICE_DECIMAL_PT  = 20  # pt — parte decimal (,90 / ,20)
PBANCO_INT_PT     = 40  # pt — entero/símbolo de precio bancario
UNIDAD_PRECIO_PT  = 16  # pt — "unidad" debajo de Precio1 en multi-SKU
UNIDAD_PBANCO_PT  = 10  # pt — "unidad" debajo de pBanco en multi-SKU
DESC_PT           = 40  # pt — descripción del producto
DESC_MIN_PT       = 24  # pt — tamaño mínimo para descripción al achicar por overflow

# ---------------------------------------------------------------------------
# Subcategorías especiales
# ---------------------------------------------------------------------------

DELI_SUBCATS      = {"FIAMBRES", "QUESOS"}
NO_UNIDAD_SUBCATS = {"CARNES", "FIAMBRES", "EMBUTIDOS CARNE", "QUESOS"}

# ---------------------------------------------------------------------------
# Precio
# ---------------------------------------------------------------------------

def fmt_price(value: Any) -> str:
    if value is None:
        return "0"
    value = float(value)
    if value == int(value):
        val = int(value)
        return f"{val:,}".replace(",", ".") if val >= 1000 else str(val)
    int_part = int(value)
    dec_str = f"{value:.2f}".split(".")[1]
    int_str = f"{int_part:,}".replace(",", ".") if int_part >= 1000 else str(int_part)
    return int_str + "," + dec_str


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
# Combos
# ---------------------------------------------------------------------------

def parse_combo(oferta_str: str) -> tuple[str, float]:
    """Parsea '3x$50' → ('3X', 50.0). Devuelve ('', 0.0) si no matchea."""
    s = str(oferta_str or "").strip()
    m = re.match(r"(\d+)\s*[xX]\s*\$?\s*(\d+(?:[.,]\d+)?)\s*$", s)
    if m:
        amount = float(m.group(2).replace(",", "."))
        return m.group(1) + "X", amount
    return "", 0.0


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
