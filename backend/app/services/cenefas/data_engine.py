"""Parseo de Excel/CSV — motor de datos para cenefas v2."""
import io
import re
import unicodedata

import openpyxl

from app.services.cenefas.formatters import fmt_price, parse_price_raw

# ---------------------------------------------------------------------------
# Variables canónicas del sistema — nomenclatura estándar camelCase
# ---------------------------------------------------------------------------
#
# Sistema unificado único (Rompe Precios, Parrilla y Vinos, Redexpres, desde
# 08/2026) -- a pedido explícito, reset completo: un solo listado de
# variables para TODOS los destinos, sin excepciones ni sistemas paralelos.
# El nombre de columna en el Excel, el placeholder <<...>> en el PPTX y la
# variable canónica son SIEMPRE el mismo string -- sin alias ni traducción de
# un nombre a otro. Todas son opcionales -- se usa lo que el Excel contenga.
#
CANONICAL_VARS: frozenset[str] = frozenset({
    "descripcion",           # nombre del producto
    "codigo",                # código de artículo
    "vigencia",               # texto de vigencia
    "precioAnterior",        # precio principal -- crudo, SIN auto-formato de "$"
                              # (el "$" va fijo como texto estático en el PPTX;
                              # si el valor también trajera "$" quedaría duplicado).
    "precioOferta",           # precio de oferta, mismo criterio sin "$"
    "oferta1",                # niveles de oferta genéricos (ej. 4x3/5x3/6x3 de
    "oferta2",                # una plantilla que no ata la oferta a un texto
    "oferta3",                # fijo tipo "4x3", cada diseño decide qué mostrar)
    "decimalPrecioP",         # parte decimal de precioAnterior/precioOferta/
    "decimalPrecioOferta",    # ofertaN como columna PROPIA del Excel (no un
    "decimalOferta1",         # transform sobre la misma columna) -- para
    "decimalOferta2",         # diseños que traen el entero y el decimal en
    "decimalOferta3",         # cuadros de texto separados.
})

# Todas las variables de precio del sistema se normalizan con
# parse_price_raw/fmt_price al formato uruguayo ("1.234,56"), SIN prefijo de
# moneda -- el "$"/"U$S" va fijo como texto estático en cada diseño PPTX. Sin
# este paso, una celda de Excel cargada como NÚMERO (no texto) le llega a
# Python como float y el "," se convierte en "." (101.5 en vez de 101,50) --
# el split entero/decimal de component_renderer.py::apply_transform busca una
# coma, así que sin normalizar acá el precio no se partía nunca (confirmado
# renderizando una plantilla real con datos de prueba).
_PRICE_VARS: frozenset[str] = frozenset({
    "precioAnterior", "precioOferta", "oferta1", "oferta2", "oferta3",
    "decimalPrecioP", "decimalPrecioOferta", "decimalOferta1", "decimalOferta2", "decimalOferta3",
})

# ---------------------------------------------------------------------------
# Normalización de headers Excel
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Normaliza para lookup: sin acentos, sin espacios/guiones, minúsculas."""
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", s).lower()


# Mapa: header normalizado → nombre canónico de variable -- mapeo directo
# (cada nombre de columna de Excel resuelve a la variable con el mismo
# nombre), sin alias ni nombres legacy.
_ALIASES: dict[str, str] = {
    "descripcion":         "descripcion",
    "codigo":              "codigo",
    "vigencia":            "vigencia",
    "precioanterior":      "precioAnterior",
    "preciooferta":        "precioOferta",
    "oferta1":             "oferta1",
    "oferta2":             "oferta2",
    "oferta3":             "oferta3",
    "decimalpreciop":      "decimalPrecioP",
    "decimalpreciooferta": "decimalPrecioOferta",
    "decimaloferta1":      "decimalOferta1",
    "decimaloferta2":      "decimalOferta2",
    "decimaloferta3":      "decimalOferta3",
}

# Columnas que, si están presentes, sirven para detectar la fila de headers
_DETECTION_NORMS = {"descripcion", "codigo", "vigencia", "precioanterior", "preciooferta"}


# ---------------------------------------------------------------------------
# Procesamiento de fila
# ---------------------------------------------------------------------------

def process_row(
    row:         tuple,
    h:           dict,       # var_name → col_idx
    vigencia:    str = "",
    aclaracion:  str = "",
    otra_alcohol:str = "",
    banco:       str = "",
) -> dict:
    """Convierte una fila de Excel en un dict de variables para el renderer.

    aclaracion/otra_alcohol/banco quedan en la firma sin usarse -- eran
    fallbacks globales de variables que ya no existen en el sistema
    unificado (aclaracion/banco). Se mantienen como parámetros para no tener
    que tocar todos los call sites (cenefas_v2.py/jobs.py/render_engine.py
    siguen llamando con la misma firma posicional de siempre)."""
    result: dict[str, str] = {}

    for var_name, col_idx in h.items():
        if col_idx >= len(row):
            continue
        val = row[col_idx]
        if val is None or (isinstance(val, str) and not val.strip()):
            result[var_name] = ""
        elif var_name in _PRICE_VARS:
            # parse_price_raw() solo matchea el run de dígitos inicial e
            # ignora en silencio lo que venga después -- si el valor crudo
            # de la celda no es un precio limpio de punta a punta, se deja
            # tal cual para que el error quede visible en vez de mostrar un
            # precio falso.
            val_str = str(val).strip()
            looks_like_price = isinstance(val, (int, float)) or bool(re.fullmatch(r"\d[\d.,]*", val_str))
            pv = parse_price_raw(val) if looks_like_price else 0.0
            result[var_name] = fmt_price(pv) if pv > 0 else val_str
        else:
            result[var_name] = str(val).strip()

    if not result.get("vigencia"):
        result["vigencia"] = vigencia

    return result


# ---------------------------------------------------------------------------
# Carga desde Excel
# ---------------------------------------------------------------------------

def load_products_from_bytes(
    excel_bytes:  bytes,
    vigencia:     str = "",
    aclaracion:   str = "",
    otra_alcohol: str = "",
    banco:        str = "",
    destino:      str | None = None,
) -> list[dict]:
    """destino/aclaracion/otra_alcohol/banco quedan en la firma sin usarse --
    ver process_row. El sistema unificado no tiene comportamiento distinto
    por destino: mismo listado de variables para todos."""
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb["Cenefas"] if "Cenefas" in wb.sheetnames else wb.active

    # ── Detectar fila de encabezados ──────────────────────────────────────
    header_row = None
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
        norms = {_norm(str(c)) for c in row if c is not None}
        if norms & _DETECTION_NORMS:
            header_row = i
            break
    if header_row is None:
        header_row = 1

    # ── Mapear columnas ───────────────────────────────────────────────────
    raw_headers = [cell.value for cell in ws[header_row]]
    h: dict[str, int] = {}
    for idx, raw in enumerate(raw_headers):
        if not raw:
            continue
        norm = _norm(str(raw))
        canonical = _ALIASES.get(norm)
        key = canonical if canonical else str(raw)  # pass through unknown columns as-is
        if key in h:
            continue  # primera columna con este nombre gana
        h[key] = idx

    # ── Detectar columna de descripción para skip de filas vacías ─────────
    desc_col = h.get("descripcion")

    products: list[dict] = []
    seen: set[str | tuple] = set()

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        # Saltar filas sin descripción
        if desc_col is not None and (desc_col >= len(row) or not row[desc_col]):
            continue

        data = process_row(row, h, vigencia, aclaracion, otra_alcohol, banco)

        # Deduplicación: codigo es la clave PRINCIPAL y suficiente por sí
        # sola cuando está presente -- es el identificador real de un
        # producto. Sin codigo (excels que no lo traen) cae al criterio por
        # combinación de campos, único identificador disponible.
        cod = (data.get("codigo") or "").strip()
        key = cod or (
            (data.get("descripcion") or "").lower().strip(),
            data.get("precioAnterior", ""),
        )
        if key not in seen:
            seen.add(key)
            products.append(data)

    return products


# ---------------------------------------------------------------------------
# Generación de plantilla Excel de descarga
# ---------------------------------------------------------------------------
#
# Un solo esquema de columnas para los tres destinos (Rompe Precios, Parrilla
# y Vinos, Redexpres) -- el sistema unificado no distingue entre ellos.
# `destino` se mantiene como parámetro solo para variar los productos de
# ejemplo (cosmético), no la estructura de columnas.

_VAR_DOCS = [
    ("descripcion",          "Nombre del producto",                  "Texto",  "Corresponde a <<descripcion>>. Palabras en MAYÚSCULAS se ven en negrita."),
    ("codigo",                "Código de artículo",                   "Texto",  "Corresponde a <<codigo>>."),
    ("vigencia",              "Texto de vigencia de la oferta",       "Texto",  "Corresponde a <<vigencia>>. Opcional."),
    ("precioAnterior",        "Precio principal (el que se muestra grande)", "Precio", "Corresponde a <<precioAnterior>>. El símbolo $ ya está fijo en la plantilla, no hace falta incluirlo acá."),
    ("precioOferta",          "Precio de oferta",                     "Precio", "Corresponde a <<precioOferta>>. Opcional."),
    ("oferta1",                "Nivel de oferta 1",                    "Precio", "Corresponde a <<oferta1>>. Opcional -- cada diseño decide qué mostrar (ej. 4x3)."),
    ("oferta2",                "Nivel de oferta 2",                    "Precio", "Corresponde a <<oferta2>>. Opcional."),
    ("oferta3",                "Nivel de oferta 3",                    "Precio", "Corresponde a <<oferta3>>. Opcional."),
    ("decimalPrecioP",         "Decimal de precioAnterior, en columna aparte", "Precio", "Corresponde a <<decimalPrecioP>>. Opcional -- solo si el diseño tiene un cuadro de texto separado para los centavos."),
    ("decimalPrecioOferta",    "Decimal de precioOferta, en columna aparte",  "Precio", "Corresponde a <<decimalPrecioOferta>>. Opcional."),
    ("decimalOferta1",         "Decimal de oferta1, en columna aparte",       "Precio", "Corresponde a <<decimalOferta1>>. Opcional."),
    ("decimalOferta2",         "Decimal de oferta2, en columna aparte",       "Precio", "Corresponde a <<decimalOferta2>>. Opcional."),
    ("decimalOferta3",         "Decimal de oferta3, en columna aparte",       "Precio", "Corresponde a <<decimalOferta3>>. Opcional."),
]

_HEADERS = [d[0] for d in _VAR_DOCS]
_COL_WIDTHS = [36, 14, 30] + [14] * (len(_HEADERS) - 3)

_EXAMPLES_BY_DESTINO: dict[str, list[tuple]] = {
    "rompe_precios": [
        ("ACEITE GIRASOL FAMILIA 1.5L", "84512", "Válido viernes 17 a domingo 19 de julio", 139, 119, "", "", "", "", "", "", "", ""),
        ("ARROZ BLUE PATNA 1KG",        "63321", "Válido viernes 17 a domingo 19 de julio",  55,  "", "", "", "", "", "", "", "", ""),
        ("CERVEZA PILSEN LATA 473ML",   "41207", "Válido viernes 17 a domingo 19 de julio",  59,  49, "", "", "", "", "", "", "", ""),
    ],
    "parrilla_y_vinos": [
        ("ASADO DE TIRA KG",           "84512", "Válido viernes 17 a domingo 19 de julio", 399, "", 379, 365, 349, "50", "", "50", "50", "50"),
        ("VINO TANNAT RESERVA 750ML",  "63321", "Válido viernes 17 a domingo 19 de julio", 349, "", 329, 319, 299, "", "", "50", "50", "50"),
        ("CHORIZO PARRILLERO KG",      "41207", "Válido viernes 17 a domingo 19 de julio", 289, "", 269, 259, 249, "", "", "50", "50", "50"),
    ],
    "redexpres": [
        ("ACEITE GIRASOL FAMILIA 1.5L", "84512", "Válido del 10 al 16 de julio", 139, "", "", "", "", "", "", "", "", ""),
        ("YOGUR CONAPROLE FRUTILLA 1KG", "63321", "Válido del 10 al 16 de julio",  99, "", "", "", "", "", "", "", "", ""),
        ("VINO TANNAT RESERVA 750ML",   "41207", "Válido del 10 al 16 de julio", 349, "", "", "", "", "", "", "", "", ""),
    ],
}


def generate_template_bytes(destino: str = "redexpres") -> bytes:
    examples = _EXAMPLES_BY_DESTINO.get(destino, _EXAMPLES_BY_DESTINO["redexpres"])
    return _build_template_workbook(
        headers=_HEADERS,
        col_widths=_COL_WIDTHS,
        examples=examples,
        var_docs=_VAR_DOCS,
    )


def _build_template_workbook(
    headers:    list[str],
    col_widths: list[int],
    examples:   list[tuple],
    var_docs:   list[tuple],
    dropdown:   dict[str, list[str]] | None = None,
) -> bytes:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cenefas"

    header_fill = PatternFill("solid", fgColor="1E3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    even_fill   = PatternFill("solid", fgColor="EEF2F7")

    for col, name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, data in enumerate(examples, 2):
        fill = even_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center")
            if fill:
                cell.fill = fill

    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    for header_name, options in (dropdown or {}).items():
        col_idx = headers.index(header_name) + 1
        col_letter = get_column_letter(col_idx)
        dv = DataValidation(type="list", formula1=f'"{",".join(options)}"', allow_blank=True)
        dv.sqref = f"{col_letter}2:{col_letter}5000"
        ws.add_data_validation(dv)

    # ── Hoja de referencia de variables ──────────────────────────────────────
    ws2 = wb.create_sheet("Variables")
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 42
    ws2.column_dimensions["C"].width = 20
    ws2.column_dimensions["D"].width = 46

    inst_font = Font(bold=True, color="FFFFFF", size=11)
    inst_fill = PatternFill("solid", fgColor="1E3A5F")

    for col, name in enumerate(["Variable", "Descripción", "Tipo", "Notas"], 1):
        cell = ws2.cell(row=1, column=col, value=name)
        cell.fill = inst_fill; cell.font = inst_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    for row_idx, data in enumerate(var_docs, 2):
        for col_idx, value in enumerate(data, 1):
            cell = ws2.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if row_idx % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="EEF2F7")
        ws2.row_dimensions[row_idx].height = 36

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
