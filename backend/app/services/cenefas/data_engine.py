"""Parseo de Excel/CSV — motor de datos para cenefas v2."""
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
# Variables canónicas del sistema — nomenclatura estándar camelCase
# ---------------------------------------------------------------------------
#
# Estas son TODAS las variables que el sistema reconoce.
# En el Excel, usar estos nombres como títulos de columna.
# En los PPTX, usar <<variableName>> con el mismo nombre.
# Todas son opcionales — se usa lo que el Excel contenga.
#
CANONICAL_VARS: frozenset[str] = frozenset({
    "precioActual",       # precio principal formateado ("$1.234")
    "precioAnterior",     # precio tachado / anterior ("$1.500")
    "precioBanco",        # precio con beneficio bancario ("$1.000")
    "banco",              # nombre o logo del banco (texto o imagen)
    "descripcion",        # nombre del producto
    "mecanica",           # mecánica / tipo de oferta ("Precio Final", "2X$X"...)
    "aclaracion",         # texto de aclaración por producto
    "aclaracion2",        # segunda aclaración (alias Excel-friendly de segundaAclaracion)
    "segundaAclaracion",  # segunda aclaración (ej: aviso de alcohol)
    "vigencia",           # texto de vigencia
    "codigoSKU",          # código de artículo
    "dia",                # día de la semana
    "mes",                # mes
    "año",                # año
    "moneda",             # prefijo de moneda ("$" o "U$S")
    "categoria",          # categoría del producto
    "subCategoria",       # subcategoría del producto
    "descuento",          # TRUE/FALSE para reglas de visibilidad
})

# Variables que contienen precios — los números se auto-formatean con prefix de moneda
_PRICE_VARS: frozenset[str] = frozenset({"precioActual", "precioAnterior", "precioBanco"})

# ---------------------------------------------------------------------------
# Normalización de headers Excel
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Normaliza para lookup: sin acentos, sin espacios/guiones, minúsculas."""
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", s).lower()


# Mapa: header normalizado → nombre canónico de variable
# Soporta tanto nombres nuevos como legacy para backward compat
_ALIASES: dict[str, str] = {
    # ── Nuevos nombres canónicos (pasan directo) ──────────────────────────
    "precioactual":       "precioActual",
    "precioanterior":     "precioAnterior",
    "preciobanco":        "precioBanco",
    "banco":              "banco",
    "descripcion":        "descripcion",
    "titulo":             "mecanica",    # backward compat: columna "titulo" → var "mecanica"
    "mecanica":           "mecanica",
    "aclaracion":         "aclaracion",
    "aclaracion2":        "aclaracion2",
    "segundaaclaracion":  "segundaAclaracion",
    "vigencia":           "vigencia",
    "codigosku":          "codigoSKU",
    "dia":                "dia",
    "mes":                "mes",
    "ano":                "año",        # ñ → n tras strip de acentos
    "moneda":             "moneda",
    "categoria":          "categoria",
    "subcategoria":       "subCategoria",
    "descuento":          "descuento",

    # ── Legacy Excel → canónico ───────────────────────────────────────────
    "precio":             "precioActual",
    "precios":            "precioActual",
    "scotland20%":        "precioBanco",
    "scotia20%":          "precioBanco",
    "pbanco":             "precioBanco",
    "preciobanco":        "precioBanco",
    "codigo":             "codigoSKU",
    "diasemana":          "dia",
    "diasemana":          "dia",
    "platodia":           "dia",
    "platodeldia":        "dia",
    "otraaclaracion":     "segundaAclaracion",

    # ── Triggers internos para compatibilidad con lógica legacy ───────────
    # (las columnas OFERTADET y OFERTA activan el compute de mecanica/titulo)
    "ofertadet":          "_ofertadet",
    "oferta":             "_oferta",
    "subcategoria":       "_subcategoria_legacy",  # needed for DELI logic
}

# Columnas que, si están presentes, sirven para detectar la fila de headers
_DETECTION_NORMS = {"ofertadet", "descripcion", "precios", "precio", "precioactual", "codigo", "moneda", "dia"}


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
    """Convierte una fila de Excel en un dict de variables para el renderer."""

    # Leer moneda primero (necesaria para formatear precios)
    moneda  = "$"
    if "moneda" in h:
        m = h["moneda"]
        if m < len(row) and row[m]:
            moneda = str(row[m]).strip()
    prefix = "U$S " if moneda == "U$S" else "$"

    result: dict[str, str] = {}

    # ── Passthrough + auto-formato para columnas canónicas ─────────────────
    for var_name, col_idx in h.items():
        if var_name.startswith("_"):
            continue  # columna interna — se procesa abajo
        if col_idx >= len(row):
            continue
        val = row[col_idx]
        if val is None or (isinstance(val, str) and not val.strip()):
            result[var_name] = ""
        elif var_name in _PRICE_VARS:
            pv = parse_price_raw(val)
            result[var_name] = (prefix + fmt_price(pv)) if pv > 0 else str(val).strip()
        else:
            result[var_name] = str(val).strip()

    # ── Compute legacy para plantillas con OFERTADET ──────────────────────
    if "_ofertadet" in h:
        _apply_legacy_compute(row, h, result, prefix, moneda, otra_alcohol)

    # ── Fallback a parámetros globales ────────────────────────────────────
    if not result.get("vigencia"):
        result["vigencia"] = vigencia
    if not result.get("aclaracion"):
        result["aclaracion"] = aclaracion
    if not result.get("banco"):
        result["banco"] = banco

    # ── Aliases backward compat (para templates ya importados con nombres viejos) ──
    _backfill_legacy_keys(result)

    return result


def _apply_legacy_compute(
    row: tuple, h: dict, result: dict, prefix: str, moneda: str, otra_alcohol: str
) -> None:
    """Computa título y mecánica de oferta a partir de OFERTADET/OFERTA/PRECIO."""
    ofertadet     = str(row[h["_ofertadet"]] or "").strip() if h["_ofertadet"] < len(row) else "Precio fijo"
    precio_raw    = row[h.get("precioActual", -1)] if "precioActual" in h and h["precioActual"] < len(row) else 0
    oferta_raw    = str(row[h["_oferta"]] or "").strip() if "_oferta" in h and h["_oferta"] < len(row) else ""
    precio        = parse_price_raw(precio_raw)
    desc          = result.get("descripcion", "")
    cat           = result.get("categoria", "")
    subcat        = result.get("subCategoria", "") or (
        str(row[h["_subcategoria_legacy"]] or "").strip() if "_subcategoria_legacy" in h else ""
    )
    cod           = result.get("codigoSKU", "")

    titulo_val  = ""
    mecanica    = ""
    unidad      = ""

    if ofertadet == "Combo":
        p1_str, amount = parse_combo(oferta_raw)
        result["precioActual"] = prefix + fmt_price(amount)
        qty = p1_str[:-1] if p1_str.endswith("X") else "2"
        mecanica = f"Comprando {qty}, {prefix}{fmt_price(precio)} c/u"
        titulo_val = p1_str

    elif ofertadet == "M x N":
        result["precioActual"] = prefix + fmt_price(precio)
        mecanica = f"Comprando 2, {prefix}{fmt_price(precio)} c/u"
        titulo_val = "M x N"

    elif re.search(r"2da\s+al\s+50|2da\s+50", ofertadet, re.IGNORECASE):
        result["precioActual"] = prefix + fmt_price(precio)
        mecanica = "Comprando 2, la 2da al 50% OFF"
        titulo_val = "2DA AL 50%"

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
                    result["descripcion"] = desc
        result["precioActual"] = prefix + fmt_price(precio_val)
        titulo_val = "Precio Final"

    is_multi_sku = bool(cod and ("/" in cod or re.search(r"\d\s*[-–—]\s*\d", cod)))
    if is_multi_sku and ofertadet in ("Precio fijo", "% descuento"):
        if subcat not in NO_UNIDAD_SUBCATS:
            unidad = "unidad"

    if not result.get("mecanica"):
        result["mecanica"] = titulo_val
    result["unidadPrecio"]    = unidad
    result["unidadPBanco"]    = "unidad" if is_multi_sku else ""
    if cat == "BEBIDAS CON ALCOHOL":
        result["segundaAclaracion"] = result.get("segundaAclaracion") or "Prohibida la venta de bebidas alcohólicas a menores de 18 años"


def _backfill_legacy_keys(result: dict) -> None:
    """Agrega claves con nombres legacy para que templates viejos sigan funcionando."""
    _map = {
        # old key          canonical key
        "precio":          "precioActual",
        "precio_banco":    "precioBanco",
        "p1":              "mecanica",    # legacy P1 → mecanica
        "titulo":          "mecanica",   # legacy titulo → mecanica
        "code":            "codigoSKU",
        "otra_aclaracion": "segundaAclaracion",
        "unidad":          "unidadPrecio",
        "unidad_precio":   "unidadPrecio",
        "unidad_pbanco":   "unidadPBanco",
    }
    for old, new in _map.items():
        if old not in result:
            result[old] = result.get(new, "")


# ---------------------------------------------------------------------------
# Carga desde Excel
# ---------------------------------------------------------------------------

def load_products_from_bytes(
    excel_bytes:  bytes,
    vigencia:     str = "",
    aclaracion:   str = "",
    otra_alcohol: str = "",
    banco:        str = "",
) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb["Cenefas"] if "Cenefas" in wb.sheetnames else wb.active

    # ── Detectar fila de encabezados ──────────────────────────────────────
    header_row = None
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
        norms = {_norm(str(c)) for c in row if c is not None}
        if len(norms & _DETECTION_NORMS) >= 1 or "ofertadet" in norms:
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
        canonical = _ALIASES.get(_norm(str(raw)))
        key = canonical if canonical else str(raw)  # pass through unknown columns as-is
        h[key] = idx

    # ── Detectar columna de descripción para skip de filas vacías ─────────
    desc_col = h.get("descripcion")
    titulo_col = h.get("_ofertadet")

    products: list[dict] = []
    seen: set[tuple] = set()

    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        # Saltar filas sin descripción
        if desc_col is not None and (desc_col >= len(row) or not row[desc_col]):
            continue
        # Si hay OFERTADET legacy, saltar filas sin él también
        if titulo_col is not None and (titulo_col >= len(row) or not row[titulo_col]):
            continue

        data = process_row(row, h, vigencia, aclaracion, otra_alcohol, banco)

        # Deduplicación por clave natural
        key = (
            data.get("mecanica", ""),
            data.get("precioActual", ""),
            (data.get("descripcion") or "").lower().strip(),
            data.get("codigoSKU", ""),
            data.get("dia", ""),
        )
        if key not in seen:
            seen.add(key)
            products.append(data)

    return products


# ---------------------------------------------------------------------------
# Generación de plantilla Excel de descarga
# ---------------------------------------------------------------------------

def generate_template_bytes() -> bytes:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    # Columnas estándar en orden lógico
    HEADERS = [
        "descripcion", "precioActual", "precioAnterior", "precioBanco",
        "mecanica", "banco", "moneda", "codigoSKU",
        "dia", "mes", "año",
        "aclaracion", "segundaAclaracion", "vigencia",
        "categoria", "subCategoria", "descuento",
    ]

    EXAMPLES: list[tuple] = [
        ("Galletitas OREO 117g",          "$1.500",  "",       "",     "Precio Final", "",  "$",    "7790001", "",       "", "", "",    "", "", "ALIMENTOS",           "GALLETITAS",  "FALSE"),
        ("Coca-Cola 2.25L",               "$4.500",  "",       "",     "2X$4.500",     "",  "$",    "7790002", "",       "", "", "",    "", "", "BEBIDAS SIN ALCOHOL", "GASEOSAS",    "FALSE"),
        ("Agua SALUS 1.5L",               "$800",    "",       "",     "M x N",        "",  "$",    "7790003", "",       "", "", "",    "", "", "BEBIDAS SIN ALCOHOL", "AGUA",        "FALSE"),
        ("Vino NORTON Malbec 750ml",       "$3.200",  "",       "$2.560","Precio Final","Scotiabank","$","7790006","",  "", "", "",    "", "Del 1 al 30 de junio", "BEBIDAS CON ALCOHOL", "VINOS", "TRUE"),
        ("Licuadora PHILIPS HR2100",       "U$S 45",  "",       "",     "Precio Final", "",  "U$S",  "7790007", "",       "", "", "",    "", "", "ELECTRODOMESTICOS",   "ELECTRODOMESTICOS","FALSE"),
        ("Asado de Tira por Kg.",          "$890",    "",       "",     "Precio Final", "",  "$",    "7790009", "LUNES",  "", "", "Precio válido solo los lunes","","","ALIMENTOS","CARNES","FALSE"),
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

    col_widths = [36, 14, 14, 14, 16, 14, 8, 14, 10, 8, 6, 28, 28, 22, 22, 16, 10]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    # Validación: moneda
    dv_moneda = DataValidation(type="list", formula1='"$,U$S"', allow_blank=True)
    dv_moneda.sqref = "G2:G5000"
    ws.add_data_validation(dv_moneda)

    # Validación: descuento
    dv_desc = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
    dv_desc.sqref = "Q2:Q5000"
    ws.add_data_validation(dv_desc)

    # ── Hoja de instrucciones ─────────────────────────────────────────────
    ws2 = wb.create_sheet("Variables")
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 42
    ws2.column_dimensions["C"].width = 18
    ws2.column_dimensions["D"].width = 40

    inst_font = Font(bold=True, color="FFFFFF", size=11)
    inst_fill = PatternFill("solid", fgColor="1E3A5F")

    for col, name in enumerate(["Variable", "Descripción", "Tipo", "Notas"], 1):
        cell = ws2.cell(row=1, column=col, value=name)
        cell.fill = inst_fill; cell.font = inst_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    VAR_DOCS = [
        ("descripcion",       "Nombre del producto tal como aparece",               "Texto",    "Palabras en MAYÚSCULAS se renderizan en negrita"),
        ("precioActual",      "Precio principal del producto",                       "Precio",   "Puede ser número (1500) o texto formateado ($1.500). Con número se auto-formatea."),
        ("precioAnterior",    "Precio anterior / tachado",                           "Precio",   "Opcional. Se usa para mostrar precio original antes del descuento."),
        ("precioBanco",       "Precio con beneficio bancario",                       "Precio",   "Opcional. Se muestra en bloque de banco (<<precioBanco>>). También acepta: PBANCO, SCOTLAND 20%, SCOTIA 20%."),
        ("mecanica",          "Mecánica o tipo de oferta",                           "Texto",    "Ej: 'Precio Final', '2X$4.500', 'M x N'. También acepta: titulo, OFERTADET (nombres legacy)."),
        ("banco",             "Nombre o logo del banco",                             "Texto",    "Texto o nombre del banco. Pasado como parámetro global al generar."),
        ("moneda",            "Prefijo de moneda",                                   "Texto",    "$ (defecto) o U$S. Afecta el prefijo de todos los precios."),
        ("codigoSKU",         "Código de artículo",                                  "Texto",    "Si contiene '/' activa modo MULTI-SKU y muestra 'unidad' bajo el precio."),
        ("dia",               "Día de la semana",                                    "Texto",    "Ej: LUNES, MARTES. Para plantillas tipo 'Plato del día'."),
        ("mes",               "Mes",                                                 "Texto",    "Opcional. Ej: JUNIO."),
        ("año",               "Año",                                                 "Texto",    "Opcional. Ej: 2026."),
        ("aclaracion",        "Aclaración por producto",                             "Texto",    "Si vacío, usa la aclaración global del formulario de generación."),
        ("segundaAclaracion", "Segunda aclaración",                                  "Texto",    "Para BEBIDAS CON ALCOHOL se llena automáticamente con el aviso legal."),
        ("vigencia",          "Texto de vigencia",                                   "Texto",    "Si vacío, usa la vigencia global del formulario de generación."),
        ("categoria",         "Categoría del producto",                              "Texto",    "BEBIDAS CON ALCOHOL activa el aviso legal automáticamente."),
        ("subCategoria",      "Subcategoría",                                        "Texto",    "FIAMBRES/QUESOS/DELI activan precio por 100g si la descripción incluye 'kg'."),
        ("descuento",         "Indica si el producto tiene descuento bancario",      "TRUE/FALSE","Controla visibilidad de elementos como cocarda. TRUE = mostrar."),
    ]
    for row_idx, data in enumerate(VAR_DOCS, 2):
        for col_idx, value in enumerate(data, 1):
            cell = ws2.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if row_idx % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="EEF2F7")
        ws2.row_dimensions[row_idx].height = 36

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
