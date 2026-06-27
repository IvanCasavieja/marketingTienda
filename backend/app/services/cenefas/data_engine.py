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

    # ── Lógica de oferta según OFERTADET ─────────────────────────────────
    _nx_applied = False

    _ofertadet_raw = ""
    if "_ofertadet" in h and h["_ofertadet"] < len(row):
        _ofertadet_raw = str(row[h["_ofertadet"]] or "").strip()

    _oferta_raw = ""
    if "_oferta" in h and h["_oferta"] < len(row):
        _oferta_raw = str(row[h["_oferta"]] or "").strip()

    if "_ofertadet" in h:
        if _ofertadet_raw.lower() == "combo":
            # Combo: OFERTA "6x160" → precio grande=160 (de OFERTA), mecanica usa columna precio
            _m_nx = re.match(r"^(\d+)\s*[xX]\s*\$?\s*([\d.,]+)\s*$", _oferta_raw)
            if _m_nx:
                _cantidad        = _m_nx.group(1)
                _precio_oferta   = parse_price_raw(_m_nx.group(2))   # 160 — precio grande
                _precio_columna  = result.get("precioActual", "")    # $53 — para mecanica
                result["oferta"]       = f"{_cantidad}x"
                result["precioActual"] = prefix + fmt_price(_precio_oferta)
                result["mecanica"]     = f"Comprando {_cantidad}, {_precio_columna} la unidad."
                _nx_applied = True

        elif re.search(r"m\s*[xX×]\s*n", _ofertadet_raw, re.IGNORECASE):
            # M x N: "3x2"/"2x1" va en el slot de precio; oferta queda vacío
            _precio_original  = result.get("precioActual", "")
            result["oferta"]       = ""
            result["precioActual"] = _oferta_raw   # "3x2" ocupa el lugar del precio
            _m_first = re.match(r"^(\d+)", _oferta_raw)
            if _m_first:
                _cantidad = _m_first.group(1)
                result["mecanica"] = f"Comprando {_cantidad}, {_precio_original} la unidad."
            _nx_applied = True

        elif not _ofertadet_raw:
            # Vacío: solo precio de columna, sin oferta ni mecanica
            result["oferta"]   = ""
            result["mecanica"] = ""
            _nx_applied = True

        if result.get("categoria") == "BEBIDAS CON ALCOHOL" and _nx_applied:
            result["segundaAclaracion"] = result.get("segundaAclaracion") or otra_alcohol

    elif "_oferta" in h:
        # Sin OFERTADET: backward compat — intentar Nx$precio en OFERTA
        _m_nx = re.match(r"^(\d+)\s*[xX]\s*\$?\s*([\d.,]+)\s*$", _oferta_raw)
        if _m_nx:
            _cantidad   = _m_nx.group(1)
            _unit_price = parse_price_raw(_m_nx.group(2))
            if not result.get("precioActual"):
                result["precioActual"] = prefix + fmt_price(_unit_price)
            result["oferta"]   = f"{_cantidad}x"
            result["mecanica"] = f"Comprando {_cantidad}, {result['precioActual']} la unidad."
            if result.get("categoria") == "BEBIDAS CON ALCOHOL":
                result["segundaAclaracion"] = result.get("segundaAclaracion") or otra_alcohol
            _nx_applied = True

    # ── Otros valores de OFERTADET → lógica legacy ────────────────────────
    if "_ofertadet" in h and not _nx_applied:
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

    # Columnas canónicas para cenefas de plato del día / precio por producto
    HEADERS = [
        "DIA", "DESCRIPCION", "precioActual",
        "ACLARACION", "ACLARACION2", "DESCUENTO", "codigoSKU",
    ]

    EXAMPLES: list[tuple] = [
        ("LUNES 1",      "STROGONOFF DE POLLO CON ARROZ",      189,  "Descuento aplicado en caja.", "",                                          "FALSE", "72187"),
        ("MARTES 2",     "FELIPE JAMÓN Y QUESO",               199,  "Descuento aplicado en caja.", "",                                          "FALSE", "1332"),
        ("MIÉRCOLES 3",  "RAVIOLES CON SALSA CARUSO",          199,  "Descuento aplicado en caja.", "Precio final con el 30% ya aplicado.",       "FALSE", "12736"),
        ("JUEVES 4",     "MILANESA DE POLLO CON PURÉ",         249,  "Descuento aplicado en caja.", "",                                          "FALSE", "52508"),
        ("VIERNES 5",    "FEIJOADA CON ARROZ",                 215,  "Descuento aplicado en caja.", "",                                          "FALSE", "17876"),
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cenefas"

    header_fill = PatternFill("solid", fgColor="1E3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    even_fill   = PatternFill("solid", fgColor="EEF2F7")

    for col, name in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, data in enumerate(EXAMPLES, 2):
        fill = even_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center")
            if fill:
                cell.fill = fill

    # DIA, DESCRIPCION, precioActual, ACLARACION, ACLARACION2, DESCUENTO, codigoSKU
    col_widths = [14, 36, 14, 32, 40, 10, 12]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    # Validación: DESCUENTO (columna F = 6)
    dv_desc = DataValidation(type="list", formula1='"TRUE,FALSE"', allow_blank=True)
    dv_desc.sqref = "F2:F5000"
    ws.add_data_validation(dv_desc)

    # ── Hoja de referencia de variables ──────────────────────────────────────
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
        ("DIA",          "Día, número o fecha",                             "Texto",     "Ej: LUNES 1 / MARTES 2 / 01/06/2026. Cualquier texto funciona."),
        ("DESCRIPCION",  "Nombre del plato / producto",                     "Texto",     "Palabras en MAYÚSCULAS se renderizan en negrita."),
        ("precioActual", "Precio del producto",                             "Precio",    "Número (189) o texto ($189). Con número se auto-formatea con $."),
        ("ACLARACION",   "Aclaración principal por producto",               "Texto",     "Ej: 'Descuento aplicado en caja.' Si vacío, usa la aclaración global."),
        ("ACLARACION2",  "Segunda aclaración (opcional)",                   "Texto",     "Ej: 'Precio final con el 30% ya aplicado.' Dejar vacío si no aplica."),
        ("DESCUENTO",    "Indica si el producto tiene descuento activo",    "TRUE/FALSE","Controla visibilidad de elementos como cocarda o badge. TRUE = mostrar."),
        ("codigoSKU",    "Código de artículo",                              "Texto",     "Identificador interno del producto."),
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
