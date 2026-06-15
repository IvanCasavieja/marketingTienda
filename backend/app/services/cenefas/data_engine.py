"""Parseo de Excel/CSV y generación de plantilla de carga."""
import io
import re
import unicodedata

import openpyxl

from app.services.cenefas.formatters import (
    fmt_price,
    parse_price_raw,
    parse_combo,
    DELI_SUBCATS,
    NO_UNIDAD_SUBCATS,
)

# ---------------------------------------------------------------------------
# Mapeo de columnas
# ---------------------------------------------------------------------------

_CANONICAL_COLUMNS = [
    "Categoria", "subcategoria", "OFERTADET", "DESCRIPCION", "PRECIO",
    "OFERTA", "MONEDA", "CODIGO", "PRECIO_BANCO", "DIA", "ACLARACION",
]

_HEADER_ALIASES: dict[str, str] = {
    "PRECIOS":      "PRECIO",
    "SCOTLAND 20%": "PRECIO_BANCO",
    "SCOTIA 20%":   "PRECIO_BANCO",
    "PRECIO BANCO": "PRECIO_BANCO",
    "PBANCO":       "PRECIO_BANCO",
    "DIA SEMANA":   "DIA",
    "DIA_SEMANA":   "DIA",
    "PLATO DIA":    "DIA",
    "PLATO DEL DIA":"DIA",
}

_OPTIONAL_HEADERS  = {"Categoria", "subcategoria", "OFERTADET", "OFERTA", "CODIGO", "PRECIO_BANCO", "DIA"}
_REQUIRED_HEADERS  = {"DESCRIPCION", "PRECIO"}
_DETECTION_COLS    = {"OFERTADET", "DESCRIPCION", "PRECIOS", "PRECIO", "CODIGO", "MONEDA", "DIA"}


def _normalize_header(name: str) -> str:
    return unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode().upper().strip()


_EXPECTED_HEADERS: dict[str, str] = {_normalize_header(k): k for k in _CANONICAL_COLUMNS}
_EXPECTED_HEADERS.update({
    _normalize_header(alias): canonical
    for alias, canonical in _HEADER_ALIASES.items()
})

# ---------------------------------------------------------------------------
# Procesamiento de fila
# ---------------------------------------------------------------------------

def process_row(row: tuple, h: dict, vigencia: str, aclaracion: str, otra_alcohol: str, banco: str = "") -> dict:
    ofertadet    = str(row[h["OFERTADET"]] or "").strip() if "OFERTADET" in h else "Precio fijo"
    precio_raw   = row[h["PRECIO"]] if "PRECIO" in h else 0
    oferta_raw   = row[h["OFERTA"]] if "OFERTA" in h else ""
    desc         = str(row[h["DESCRIPCION"]] or "").strip() if "DESCRIPCION" in h else ""
    cat          = str(row[h["Categoria"]] or "").strip() if "Categoria" in h else ""
    subcat       = str(row[h["subcategoria"]] or "").strip() if "subcategoria" in h else ""
    moneda       = str(row[h["MONEDA"]] or "").strip() if "MONEDA" in h else "$"
    code         = str(row[h["CODIGO"]] or "").strip() if "CODIGO" in h else ""
    precio_banco_raw = row[h["PRECIO_BANCO"]] if "PRECIO_BANCO" in h else None
    dia          = str(row[h["DIA"]] or "").strip() if "DIA" in h else ""

    aclaracion_col = str(row[h["ACLARACION"]] or "").strip() if "ACLARACION" in h else ""

    prefix  = "U$S " if moneda == "U$S" else "$"
    precio  = parse_price_raw(precio_raw)

    p1 = ""
    precio_display = ""
    mecanica = ""

    if ofertadet == "Combo":
        p1, amount = parse_combo(oferta_raw)
        precio_display = prefix + fmt_price(amount)
        qty = p1[:-1] if p1.endswith("X") else "2"
        mecanica = f"Comprando {qty}, {prefix}{fmt_price(precio)} c/u"

    elif ofertadet == "M x N":
        precio_display = prefix + fmt_price(precio)
        mecanica = f"Comprando 2, {prefix}{fmt_price(precio)} c/u"
        p1 = "M x N"

    elif re.search(r"2da\s+al\s+50|2da\s+50", ofertadet, re.IGNORECASE):
        precio_display = prefix + fmt_price(precio)
        mecanica = "Comprando 2, la 2da al 50% OFF"
        p1 = "2DA AL 50%"

    else:
        precio_val = precio
        if subcat in DELI_SUBCATS:
            dl = desc.lower()
            has_kg = ". kg" in dl or " kg" in dl or dl.endswith("kg") or "100g" in dl
            if has_kg or subcat == "FIAMBRES":
                precio_val = precio / 10
                if has_kg:
                    desc = re.sub(r"\.\s*[Kk]g\b", ". 100g", desc)
                    desc = re.sub(r"\s+[Kk]g\b", " 100g", desc)
        precio_display = prefix + fmt_price(precio_val)

    if not p1:
        p1 = "Precio Final"

    is_multi_sku = bool(code and ("/" in code or re.search(r"\d\s*[-–—]\s*\d", code)))

    if is_multi_sku and ofertadet in ("Precio fijo", "% descuento"):
        unidad = "" if subcat in NO_UNIDAD_SUBCATS else "unidad"
    else:
        unidad = ""

    otra = otra_alcohol if cat == "BEBIDAS CON ALCOHOL" else ""

    pbanco_display = ""
    if precio_banco_raw is not None and precio_banco_raw != "":
        pbanco_val = parse_price_raw(precio_banco_raw)
        if pbanco_val > 0:
            pbanco_display = prefix + fmt_price(pbanco_val)

    return {
        "p1":              p1,
        "precio":          precio_display,
        "mecanica":        mecanica,
        "descripcion":     desc,
        "dia":             dia,
        "unidad":          unidad,
        "vigencia":        vigencia,
        "aclaracion":      aclaracion_col or aclaracion,
        "otra_aclaracion": otra,
        "code":            code,
        "pbanco":          pbanco_display,
        "banco":           banco,
        "unidad_precio":   unidad,
        "unidad_pbanco":   "unidad" if is_multi_sku else "",
    }


# ---------------------------------------------------------------------------
# Carga desde Excel
# ---------------------------------------------------------------------------

def load_products_from_bytes(
    excel_bytes: bytes,
    vigencia: str,
    aclaracion: str,
    otra_alcohol: str,
    banco: str = "",
) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb["Cenefas"] if "Cenefas" in wb.sheetnames else wb.active

    header_row = None
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
        normalized = {_normalize_header(str(c)) for c in row if c is not None}
        if "OFERTADET" in normalized or len(normalized & _DETECTION_COLS) >= 2:
            header_row = i
            break
    if header_row is None:
        header_row = 1

    raw_headers = [cell.value for cell in ws[header_row]]
    h = {}
    for idx, raw in enumerate(raw_headers):
        if not raw:
            continue
        canonical = _EXPECTED_HEADERS.get(_normalize_header(str(raw)))
        h[canonical or str(raw)] = idx

    # Extra columns: anything not in the canonical set gets passed through to the product dict
    _canonical_set = set(_CANONICAL_COLUMNS)
    extra_cols = {key: idx for key, idx in h.items() if key not in _canonical_set}

    products = []
    seen: set = set()

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if "DESCRIPCION" in h and not row[h["DESCRIPCION"]]:
            continue
        if "OFERTADET" in h and not row[h["OFERTADET"]]:
            continue
        data = process_row(row, h, vigencia, aclaracion, otra_alcohol, banco)
        for col_name, col_idx in extra_cols.items():
            if col_idx < len(row):
                val = row[col_idx]
                data[col_name] = str(val).strip() if val is not None and val != "" else ""
        key = (data["p1"], data["precio"], data["mecanica"], data["descripcion"].lower().strip() if data["descripcion"] else "", data.get("code", ""), data.get("dia", ""))
        if key not in seen:
            seen.add(key)
            products.append(data)

    return products


# ---------------------------------------------------------------------------
# Generación de plantilla Excel de carga
# ---------------------------------------------------------------------------

def generate_template_bytes() -> bytes:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    HEADERS = ["Categoria", "subcategoria", "OFERTADET", "DESCRIPCION", "PRECIO", "OFERTA", "MONEDA", "CODIGO", "PRECIO_BANCO"]
    EXAMPLES: list[tuple] = [
        ("ALIMENTOS",           "GALLETITAS",       "Precio fijo",       "Galletitas OREO 117g",          1500,  "",       "$",    "7790001",  ""),
        ("BEBIDAS SIN ALCOHOL", "GASEOSAS",         "Combo",             "Coca-Cola 2.25L",               2500,  "2x$4500","$",    "7790002",  ""),
        ("BEBIDAS SIN ALCOHOL", "AGUA",             "M x N",             "Agua SALUS 1.5L",               800,   "",       "$",    "7790003",  ""),
        ("LIMPIEZA",            "LIMPIADORES",      "% descuento",       "Lavandina AYUDIN 2L",           850,   "",       "$",    "7790004",  ""),
        ("FIAMBRES Y QUESOS",   "QUESOS",           "Precio fijo",       "Queso Barra por Kg.",           12000, "",       "$",    "7790005",  ""),
        ("BEBIDAS CON ALCOHOL", "VINOS",            "Precio fijo",       "Vino NORTON Malbec 750ml",      3200,  "",       "$",    "7790006",  2560),
        ("ELECTRODOMESTICOS",   "ELECTRODOMESTICOS","Precio fijo",       "Licuadora PHILIPS HR2100",      45,    "",       "U$S",  "7790007",  ""),
        ("ALIMENTOS",           "GALLETITAS",       "Precio fijo",       "Galletitas OREO 117g + Chips AHOY 120g", 2800, "", "$", "7790001/7790008", 2240),
    ]

    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Cenefas"

    header_fill = PatternFill("solid", fgColor="1E3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    even_fill   = PatternFill("solid", fgColor="EEF2F7")

    for col, name in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill  = header_fill
        cell.font  = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, data in enumerate(EXAMPLES, 2):
        fill = even_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center")
            if fill:
                cell.fill = fill

    col_widths = [22, 20, 14, 36, 10, 12, 10, 14, 14]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    dv_tipo = DataValidation(
        type="list",
        formula1='"Precio fijo,% descuento,Combo,M x N,2da al 50% OFF"',
        allow_blank=True,
    )
    dv_tipo.sqref = "C2:C5000"
    ws.add_data_validation(dv_tipo)

    dv_moneda = DataValidation(type="list", formula1='"$,U$S"', allow_blank=True)
    dv_moneda.sqref = "G2:G5000"
    ws.add_data_validation(dv_moneda)

    # Formato numérico para PRECIO_BANCO
    from openpyxl.styles import numbers
    for row_idx in range(2, 5002):
        ws.cell(row=row_idx, column=9).number_format = "#,##0.##"

    ws2 = wb.create_sheet("Instrucciones")
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 45
    ws2.column_dimensions["C"].width = 32
    ws2.column_dimensions["D"].width = 35

    inst_header_font = Font(bold=True, color="FFFFFF", size=11)
    inst_header_fill = PatternFill("solid", fgColor="1E3A5F")
    inst_even_fill   = PatternFill("solid", fgColor="EEF2F7")

    inst_cols = ["Columna", "Descripción", "Valores aceptados", "Notas"]
    for col, name in enumerate(inst_cols, 1):
        cell = ws2.cell(row=1, column=col, value=name)
        cell.fill  = inst_header_fill
        cell.font  = inst_header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    rows = [
        ("Categoria",    "Categoría del producto",              "Texto libre",
         "Ej: ALIMENTOS, BEBIDAS CON ALCOHOL, CARNES"),
        ("subcategoria", "Subcategoría del producto",           "Texto libre",
         "QUESOS y FIAMBRES: precio por 100g si desc tiene 'kg'. CARNES/FIAMBRES/QUESOS: sin unidad."),
        ("OFERTADET",    "Tipo de oferta",
         "Precio fijo / % descuento / Combo / M x N / 2da al 50% OFF",
         "Determina cómo se muestra el precio en la cenefa"),
        ("DESCRIPCION",  "Nombre del producto tal como aparece","Texto libre",
         "Las palabras en MAYÚSCULAS se muestran en negrita"),
        ("PRECIO",       "Precio unitario (número)",            "Número (ej: 1500, 45.90)",
         "Para Combo: precio individual. Para dólares usa MONEDA=U$S"),
        ("OFERTA",       "Solo para Combo: cantidad y precio total", "Formato: 2X4500 o 2x$4500",
         "2X4500 = 2 unidades por $4500. También acepta 2x$4500. Vacío para otros tipos."),
        ("MONEDA",       "Moneda del precio",                   "$ o U$S",
         "$ = pesos uruguayos. U$S = dólares."),
        ("CODIGO",       "Código de artículo (opcional)",       "Texto o número",
         "Si contiene '/' (ej: 7790001/7790002) activa modo MULTI-SKU: muestra 'unidad' bajo el precio"),
        ("PRECIO_BANCO", "Precio con beneficio bancario (opcional)", "Número (ej: 2560)",
         "Se muestra en el bloque de banco de la plantilla (placeholder <<PBanco>>)"),
    ]
    for row_idx, data in enumerate(rows, 2):
        fill = inst_even_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(data, 1):
            cell = ws2.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if fill:
                cell.fill = fill
        ws2.row_dimensions[row_idx].height = 36

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
