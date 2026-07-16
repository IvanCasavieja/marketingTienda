"""Convertidor de Excel — matchea el export crudo de gestión contra el
catálogo compartido de descripciones (sku_descripciones) y arma un Excel
limpio, listo para subir directo al generador de Cenefas existente.

Deliberadamente separado de data_engine.py: esta herramienta no interpreta
la mecánica de oferta/oferta det (eso sigue siendo trabajo exclusivo del
generador de Cenefas cuando el Excel de salida se vuelva a subir ahí) —
solo transporta esas columnas tal cual del input al output.
"""
import io
import re
import unicodedata

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku_descripcion import SkuDescripcion
from app.services.cenefas.formatters import parse_price_raw

# ---------------------------------------------------------------------------
# Normalización de headers del Excel de entrada
# ---------------------------------------------------------------------------

class ConvertidorParseError(ValueError):
    """El Excel no tiene una columna CODIGO reconocible."""


def _norm(name) -> str:
    """Copia intencional de data_engine._norm — no importamos ese símbolo
    privado entre módulos para no acoplar convertidor.py a los internos de
    data_engine.py; son 3 líneas, duplicarlas es más barato que el acople."""
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", s).lower()


_INPUT_ALIASES: dict[str, str] = {
    "codigo":         "codigo",
    "nombrearticulo": "nombre_articulo",
    "moneda":         "moneda",
    "precioant":      "precio_anterior",
    "precio":         "precio",
    "oferta":         "oferta",
    "ofertadet":      "oferta_det",
    "descripcionweb": "descripcion_web",
}

_HEADER_SCAN_ROWS = 10


def normalize_sku(raw) -> str:
    """int/float/str crudo de la celda CODIGO -> string canónico ('17780.0' -> '17780')."""
    if raw is None:
        return ""
    if isinstance(raw, float):
        raw = int(raw) if raw.is_integer() else raw
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _parse_price_or_none(raw) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    return parse_price_raw(raw)


def _clean_str(raw) -> str:
    return str(raw).strip() if raw is not None else ""


# Monedas válidas conocidas del sistema (ver CANONICAL_VARS en data_engine.py:
# "moneda: prefijo de moneda '$' o 'U$S'"). Cualquier otra cosa no vacía en
# esa columna es sospechosa.
_VALID_MONEDAS = {"$", "u$s", "us$", "usd", "uyu"}
# OFERTADET nunca debería ser un número puro — es una categoría ("Combo",
# "M x N", "Precio fijo", vacío) o texto legado ("2da al 50%", "% descuento").
_NUMERIC_RE = re.compile(r"^\d+([.,]\d+)?$")


def _looks_shifted(row: dict) -> bool:
    """Señal de que el Excel de origen trae las columnas corridas para esta
    fila — ej. SKU 551406 real: "TERMO 1" con "1L C/PICO SELECTA" colado en
    la columna MONEDA y "649" (un precio) colado en OFERTADET. No intenta
    "arreglar" la fila, solo avisar: con las columnas corridas, cualquier
    otro campo de la fila puede estar mal aunque no dispare su propio
    warning de "vacío"."""
    moneda = row["moneda"].strip().lower()
    if moneda and moneda not in _VALID_MONEDAS:
        return True
    oferta_det = row["oferta_det"].strip()
    if oferta_det and _NUMERIC_RE.match(oferta_det):
        return True
    return False


# ---------------------------------------------------------------------------
# Parseo del Excel de entrada
# ---------------------------------------------------------------------------

def parse_input_excel(excel_bytes: bytes) -> list[dict]:
    """Detecta la fila de headers real (puede no ser la fila 1 — el export
    real de gestión trae una fila de título + una fila en blanco antes),
    mapea columnas por nombre normalizado, y extrae por fila: codigo,
    nombre_articulo, moneda, precio_anterior, precio, oferta, oferta_det,
    descripcion_web. Columnas no reconocidas se ignoran."""
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(min_row=1, max_row=None, values_only=True))

    header_row_idx: int | None = None
    col_map: dict[int, str] = {}
    for i, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        candidate: dict[int, str] = {}
        found_codigo = False
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            norm = _norm(cell)
            var_name = _INPUT_ALIASES.get(norm)
            if var_name:
                candidate[col_idx] = var_name
                if var_name == "codigo":
                    found_codigo = True
        if found_codigo:
            header_row_idx = i
            col_map = candidate
            break

    if header_row_idx is None:
        raise ConvertidorParseError(
            "No encontré una columna 'CODIGO' reconocible en las primeras "
            f"{_HEADER_SCAN_ROWS} filas del Excel — verificá que sea el export crudo de gestión."
        )

    # col_map es col_idx -> var_name; invertido una sola vez, no por fila.
    col_by_var = {var: c for c, var in col_map.items()}
    codigo_col = col_by_var["codigo"]

    def cell(row: tuple, var: str):
        c = col_by_var.get(var)
        return row[c] if c is not None and c < len(row) else None

    parsed: list[dict] = []
    for row in rows[header_row_idx + 1:]:
        if codigo_col >= len(row) or row[codigo_col] is None:
            continue
        codigo = normalize_sku(row[codigo_col])
        if not codigo:
            continue

        parsed.append({
            "codigo":           codigo,
            "nombre_articulo":  _clean_str(cell(row, "nombre_articulo")),
            "moneda":           _clean_str(cell(row, "moneda")) or "$",
            "precio_anterior":  _parse_price_or_none(cell(row, "precio_anterior")),
            "precio":           _parse_price_or_none(cell(row, "precio")),
            "oferta":           _clean_str(cell(row, "oferta")),
            "oferta_det":       _clean_str(cell(row, "oferta_det")),
            "descripcion_web":  _clean_str(cell(row, "descripcion_web")),
        })
    return parsed


# ---------------------------------------------------------------------------
# Matching contra el catálogo + warnings
# ---------------------------------------------------------------------------

def _compute_warnings(row: dict) -> list[str]:
    w = []
    if _looks_shifted(row):
        w.append("shifted_columns")
    if not row["descripcion"].strip():
        w.append("missing_description")
    if not row["precio"]:
        w.append("missing_price")
    if not row["precio_anterior"]:
        w.append("missing_precio_anterior")
    if not row["oferta"]:
        w.append("missing_oferta")
    if not row["oferta_det"]:
        w.append("missing_oferta_det")
    if not row["descripcion_web"]:
        w.append("missing_descripcion_web")
    return w


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


async def match_rows(parsed: list[dict], db: AsyncSession) -> list[dict]:
    """Bulk lookup por SKU (un SELECT por cada 1000 códigos distintos, no
    N queries) + cómputo de warnings por fila."""
    skus = sorted({r["codigo"] for r in parsed if r["codigo"]})
    catalogo: dict[str, str] = {}
    for chunk in _chunks(skus, 1000):
        result = await db.execute(
            select(SkuDescripcion.sku, SkuDescripcion.descripcion)
            .where(SkuDescripcion.sku.in_(chunk))
        )
        catalogo.update(dict(result.all()))

    rows = []
    for i, r in enumerate(parsed):
        descripcion = catalogo.get(r["codigo"], "")
        row = {**r, "descripcion": descripcion}
        rows.append({
            "row_id":    i,
            "matched":   r["codigo"] in catalogo,
            "warnings":  _compute_warnings(row),
            **row,
        })
    return rows


# ---------------------------------------------------------------------------
# Generación del Excel de salida
# ---------------------------------------------------------------------------

_OUTPUT_HEADERS = [
    "Código", "Nombre Artículo", "Descripción", "Moneda",
    "Precio Anterior", "Precio", "Oferta", "Oferta Det", "Descripción Web",
]
_OUTPUT_FIELDS = [
    "codigo", "nombre_articulo", "descripcion", "moneda",
    "precio_anterior", "precio", "oferta", "oferta_det", "descripcion_web",
]
# warning code -> índice de columna 1-based que se resalta
_WARN_COL = {
    "missing_description":     3,
    "missing_precio_anterior": 5,
    "missing_price":           6,
    "missing_oferta":          7,
    "missing_oferta_det":      8,
    "missing_descripcion_web": 9,
}


def build_output_workbook(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cenefas"

    header_fill    = PatternFill("solid", fgColor="1E3A5F")
    header_font    = Font(bold=True, color="FFFFFF", size=11)
    even_fill      = PatternFill("solid", fgColor="EEF2F7")
    warn_fill      = PatternFill("solid", fgColor="FDE68A")  # ámbar — advertencia informativa
    no_match_fill  = PatternFill("solid", fgColor="FCA5A5")  # rojo — sin descripción, acción obligatoria
    shifted_fill   = PatternFill("solid", fgColor="DDD6FE")  # violeta — fila con columnas posiblemente corridas

    for col, name in enumerate(_OUTPUT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, r in enumerate(rows, 2):
        # Recalculado server-side, no confía en lo que mandó el cliente —
        # única fuente de verdad, compartida con match_rows() en preview.
        warnings = _compute_warnings(r)
        shifted = "shifted_columns" in warnings
        zebra = even_fill if row_idx % 2 == 0 else None
        for col_idx, field in enumerate(_OUTPUT_FIELDS, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=r.get(field))
            cell.alignment = Alignment(vertical="center")
            warn_code = next((w for w, c in _WARN_COL.items() if c == col_idx and w in warnings), None)
            if warn_code == "missing_description":
                cell.fill = no_match_fill
            elif warn_code:
                cell.fill = warn_fill
            elif shifted:
                # Violeta para toda la fila: con las columnas corridas
                # cualquier campo puede estar mal, no solo el que dispara
                # su propio warning de "vacío".
                cell.fill = shifted_fill
            elif zebra:
                cell.fill = zebra

    for col, width in enumerate([16, 36, 36, 10, 14, 12, 14, 14, 40], 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
