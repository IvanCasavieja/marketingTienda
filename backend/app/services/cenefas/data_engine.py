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
# ─────────────────────────────────────────────────────────────────────────────
# ESTÁNDAR: 21 VARIABLES NORMALIZADAS (v2026-09)
# ─────────────────────────────────────────────────────────────────────────────
# Todas las cenefas usan este conjunto estándar. Cada una toma solo las que
# necesita; ninguna es obligatoria.
#
# Mappeo: Excel column (normalizado) → variable canónica en PPTX <<...>>
#
CANONICAL_VARS: frozenset[str] = frozenset({
    # 1. Precios
    "precioRegular",       # Precio base (SIN decimales — usar decimalRegular aparte si se necesita)
    "precioOferta",        # Precio de oferta nivel 1
    "precioOferta2",       # Precio de oferta nivel 2
    "precioOferta3",       # Precio de oferta nivel 3
    "precioOferta4",       # Precio de oferta nivel 4

    # 2. Decimales de precios (usar estos en un cuadro aparte si el diseño lo requiere)
    "decimalRegular",
    "decimalOferta",
    "decimalOferta2",
    "decimalOferta3",
    "decimalOferta4",

    # 3. Identificación y texto
    "codigo",              # Código SKU / código de producto
    "descripcion",         # Nombre del producto
    "vigencia",            # Período de validez de la promo
    "mecanica",            # Descripción de la mecánica (ej: "Comprando 3, la 3ra con 50% OFF")
    "aclaracion1",         # Primera aclaración/aviso legal
    "aclaracion2",         # Segunda aclaración/aviso legal
    "aclaracion3",         # Tercera aclaración/aviso legal
    "legales",             # Legales/disclaimer general

    # 4. Banco/medio de pago
    "precioBanco",         # Precio con descuento bancario
    "decimalBanco",        # Decimal del precio bancario
    "banco",               # Nombre del banco / medio de pago
})

# Variables numéricas que necesitan normalización de formato (uruguayo "1.234,56")
_PRICE_VARS: frozenset[str] = frozenset({
    "precioRegular", "precioOferta", "precioOferta2", "precioOferta3", "precioOferta4",
    "precioBanco",
})

_DECIMAL_VARS: frozenset[str] = frozenset({
    "decimalRegular", "decimalOferta", "decimalOferta2", "decimalOferta3", "decimalOferta4",
    "decimalBanco",
})

# ---------------------------------------------------------------------------
# Normalización de headers Excel
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    """Normaliza para lookup: sin acentos, sin espacios/guiones, minúsculas."""
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", s).lower()


# Mapa: header normalizado (sin acentos, espacios, minúsculas) → variable canónica
# SOLO 21 variables estándares + triggers internos para lógica Redexpress
_ALIASES: dict[str, str] = {
    # Precios
    "precioregular":      "precioRegular",
    "preciooferta":       "precioOferta",
    "preciooferta2":      "precioOferta2",
    "preciooferta3":      "precioOferta3",
    "preciooferta4":      "precioOferta4",

    # Decimales
    "decimalregular":     "decimalRegular",
    "decimaloferta":      "decimalOferta",
    "decimaloferta2":     "decimalOferta2",
    "decimaloferta3":     "decimalOferta3",
    "decimaloferta4":     "decimalOferta4",

    # Identificación y texto
    "codigo":             "codigo",
    "codigosku":          "codigo",          # variante común
    "descripcion":        "descripcion",
    "nombre":             "descripcion",     # alias alternativo
    "nombredelproducto":  "descripcion",     # variantes
    "producto":           "descripcion",
    "vigencia":           "vigencia",
    "mecanica":           "mecanica",
    "aclaracion1":        "aclaracion1",
    "aclaracion2":        "aclaracion2",
    "aclaracion3":        "aclaracion3",
    "legales":            "legales",

    # Banco
    "preciobanco":        "precioBanco",
    "decimalbanco":       "decimalBanco",
    "banco":              "banco",

    # Triggers internos para lógica Redexpress (Combo/M×N)
    "ofertadet":          "_ofertadet",
    "oferta":             "_oferta",
}

# Columnas mínimas para detectar si la primera fila es header (normalización estándar)
_DETECTION_NORMS = {"descripcion", "codigo", "precioregular", "mecanica"}


# ---------------------------------------------------------------------------
# Procesamiento de fila
# ---------------------------------------------------------------------------

def process_row(
    row: tuple,
    h: dict,
) -> dict:
    """Convierte una fila de Excel en un dict de variables para el renderer.

    Entrada: fila de Excel + mapeo (var_name → col_idx).
    Salida: dict con variables canónicas (21 estándares).

    Lógica Redexpress:
    - Precio Fijo: sin cambios
    - Combo: precio normal, oferta = "3x", mecanica = "Comprando 3, $PRECIO la unidad"
    - M×N: precio = "3x2", mecanica = "Comprando 3, $PRECIO la unidad"
    """
    result: dict[str, str] = {}

    # Passthrough inicial
    for var_name, col_idx in h.items():
        if var_name.startswith("_"):
            continue  # Triggers internos, se procesan abajo
        if col_idx >= len(row):
            continue
        val = row[col_idx]
        if val is None or (isinstance(val, str) and not val.strip()):
            result[var_name] = ""
        elif var_name in _PRICE_VARS:
            pv = parse_price_raw(val)
            result[var_name] = ("$" + fmt_price(pv)) if pv > 0 else str(val).strip()
        elif var_name in _DECIMAL_VARS:
            pv = parse_price_raw(val)
            result[var_name] = fmt_price(pv) if pv > 0 else str(val).strip()
        else:
            result[var_name] = str(val).strip()

    # Lógica Redexpress: detectar tipo de oferta por OFERTADET
    ofertadet_raw = ""
    if "_ofertadet" in h and h["_ofertadet"] < len(row):
        ofertadet_raw = str(row[h["_ofertadet"]] or "").strip().lower()

    oferta_raw = ""
    if "_oferta" in h and h["_oferta"] < len(row):
        oferta_raw = str(row[h["_oferta"]] or "").strip()

    if ofertadet_raw == "combo":
        # Combo: "3x150" en OFERTA → precio en precioOferta, mecanica = "Comprando X, $PRECIO la unidad"
        m = re.match(r"^(\d+)\s*[xX]\s*\$?\s*([\d.,]+)\s*$", oferta_raw)
        if m:
            cantidad = m.group(1)
            precio_combo = parse_price_raw(m.group(2))
            result["precioOferta"] = "$" + fmt_price(precio_combo)
            # Si existe variable "oferta" en el template, llenarla con cantidad + "x"
            if "oferta" in h:
                result["oferta"] = f"{cantidad}x"
            precio_unitario = result.get("precioRegular", "")
            result["mecanica"] = f"Comprando {cantidad}, {precio_unitario} la unidad"

    elif "m x n" in ofertadet_raw or "mxn" in ofertadet_raw:
        # M×N: "3x2" en OFERTA → precio = "3x2", mecanica = "Comprando X, $PRECIO la unidad"
        m = re.match(r"^(\d+)", oferta_raw)
        cantidad = m.group(1) if m else "2"
        precio_unitario = result.get("precioRegular", "")
        result["precioOferta"] = oferta_raw  # "3x2" ocupa lugar del precio
        result["mecanica"] = f"Comprando {cantidad}, {precio_unitario} la unidad"

    # Si OFERTADET está vacío o es "Precio fijo": sin cambios, valores por defecto

    return result


# ---------------------------------------------------------------------------
# Carga desde Excel
# ---------------------------------------------------------------------------

def load_products_from_bytes(
    excel_bytes: bytes,
) -> list[dict]:
    """Carga productos desde Excel. Usa las 21 variables estándares."""
    aliases = _ALIASES

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

    # Paso 1: una columna cuyo nombre coincide EXACTO con la variable
    # canónica (ej. una columna literalmente llamada "descripcion") siempre
    # gana, sin importar el orden -- antes, con un excel que trae tanto
    # "descripcion" como "Nombre del Articulo" (alias legacy de la misma
    # variable), ganaba la que apareciera primero de izquierda a derecha en
    # la planilla, así que "Nombre del Articulo" podía pisar en silencio a
    # una columna "descripcion" real solo por estar más a la izquierda (bug
    # real, visto con un excel real que traía las dos).
    for idx, raw in enumerate(raw_headers):
        if not raw:
            continue
        norm = _norm(str(raw))
        canonical = aliases.get(norm)
        if canonical and norm == _norm(canonical):
            h[canonical] = idx

    # Paso 2: el resto -- alias no exactos (ej. "Nombre del Producto")
    for idx, raw in enumerate(raw_headers):
        if not raw:
            continue
        norm = _norm(str(raw))
        canonical = aliases.get(norm)
        key = canonical if canonical else str(raw)
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

        data = process_row(row, h)

        # Deduplicación: codigoSKU es la clave PRINCIPAL y suficiente por sí
        # sola cuando está presente -- es el identificador real de un
        # producto, no hace falta que descripción/mecanica/precioActual/dia
        # también coincidan (esos campos ni siquiera se popultan en Parrilla
        # y Vinos). Comparar por combinación de campos era demasiado
        # estricto: bastaba con que la descripción viniera escrita distinto
        # entre filas del mismo código para NO deduplicar filas repetidas.
        # Sin codigoSKU (destinos/excels que no lo traen) cae al criterio
        # viejo por combinación de campos, único identificador disponible.
        sku = (data.get("codigoSKU") or "").strip()
        key = sku or (
            data.get("mecanica", ""),
            data.get("precioActual", ""),
            (data.get("descripcion") or "").lower().strip(),
            data.get("dia", ""),
        )
        if key not in seen:
            seen.add(key)
            products.append(data)

    return products


# ---------------------------------------------------------------------------
# Generación de plantilla Excel de descarga
# ---------------------------------------------------------------------------
#
# Tres plantillas, una por destino de Cenefas — comparten estilo pero tienen
# columnas distintas porque cada destino soporta variables distintas
# (Rompe Precios explícitamente no tiene mecánica de combo/M x N).
#
# Parrilla y Vinos tiene su PROPIO esquema, calcado del Excel real que ya
# usa el equipo (no el de Rompe Precios): "regular" es el precio principal,
# "oferta"/"5x3"/"6x3" son tres niveles de precio por cantidad que en el
# PPTX aparecen partidos en entero+decimal (ver _ALIASES_PARRILLA_VINOS_OVERRIDE
# y pptx_importer.py). vigencia/aclaraciones quedan como columnas opcionales
# al final por si una plantilla futura (ej. la versión A4) las necesita —
# process_row ya trata todo como opcional, no molestan si quedan vacías.

def generate_template_bytes(destino: str = "redexpres") -> bytes:
    if destino == "rompe_precios":
        return _build_template_workbook(
            headers=["descripcion", "precio", "precioAnterior", "vigencia", "aclaracion1", "aclaracion2", "aclaracion3"],
            col_widths=[36, 12, 14, 30, 30, 30, 30],
            examples=[
                ("ACEITE GIRASOL FAMILIA 1.5L",  139, 169, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.",                                                ""),
                ("ARROZ BLUE PATNA 1KG",          55,  69, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "",                                                                ""),
                ("CERVEZA PILSEN LATA 473ML",     59,  75, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", "Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
                ("YOGUR CONAPROLE FRUTILLA 1KG",  89, 109, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "",                                                                ""),
                ("DETERGENTE OMO LÍQUIDO 3L",    229, 279, "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.",                                                ""),
            ],
            var_docs=[
                ("descripcion",    "Nombre del producto",                       "Texto",  "Corresponde a <<Descripcion>> en la plantilla PPTX. Palabras en MAYÚSCULAS se ven en negrita."),
                ("precio",         "Precio actual (el que se muestra grande)",  "Precio", "Corresponde a <<Precio>>. Número (139) o texto ($139) — con número se auto-formatea con $."),
                ("precioAnterior", "Precio anterior — se muestra tachado",      "Precio", "Corresponde a <<precioAnterior>>. Dejar vacío si el producto no tenía un precio previo."),
                ("vigencia",       "Texto de vigencia de la oferta",            "Texto",  "Corresponde a <<Vigencia>>. Si se deja vacío acá, usa la vigencia general de la pantalla de este destino."),
                ("aclaracion1",    "Primera aclaración / legal",                "Texto",  "Corresponde a <<Aclaracion1>>."),
                ("aclaracion2",    "Segunda aclaración",                        "Texto",  "Corresponde a <<Aclaracion2>>. Dejar vacío si no aplica."),
                ("aclaracion3",    "Tercera aclaración (ej. alcohol)",          "Texto",  "Corresponde a <<Aclaracion3>>. Dejar vacío si no aplica."),
                ("imagen (cocarda)", "Sello/badge de la promo",                 "Imagen — NO es columna", "Se sube UNA sola vez desde la pantalla de este destino (no por producto) — no hace falta agregarla acá."),
            ],
        )

    if destino == "parrilla_y_vinos":
        return _build_template_workbook(
            headers=["codigo", "nombre de articulo", "regular", "oferta", "5x3", "6x3", "vigencia", "aclaracion1", "aclaracion2", "aclaracion3"],
            col_widths=[14, 36, 12, 12, 12, 12, 30, 30, 30, 30],
            examples=[
                ("84512", "ASADO DE TIRA KG",          399, "379,50", "365,50", "349,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", ""),
                ("63321", "VINO TANNAT RESERVA 750ML", 349, "329,50", "319,50", "299,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "", "Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
                ("41207", "CHORIZO PARRILLERO KG",     289, "269,50", "259,50", "249,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", ""),
                ("55890", "CARBÓN VEGETAL 3KG",         99,       "",       "",       "", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "", ""),
                ("67788", "ESPUMANTE BRUT 750ML",      259, "239,50", "229,50", "219,50", "Válido viernes 17 a domingo 19 de julio", "Precio válido en todos los locales.", "Stock limitado.", "Prohibida la venta de bebidas alcohólicas a menores de 18 años"),
            ],
            var_docs=[
                ("codigo",              "Código de artículo",                          "Texto",  "Corresponde a <<codigo>> en la plantilla PPTX."),
                ("nombre de articulo",  "Nombre del producto",                         "Texto",  "Corresponde a <<descripcion>>."),
                ("regular",             "Precio principal (el que se muestra grande)", "Precio", "Corresponde a <<precioP>>. El signo $ ya está fijo en la plantilla, no hace falta incluirlo acá."),
                ("oferta",              "Precio del nivel 4x3",                        "Precio", "Corresponde a <<4x3P>> (entero) y <<decimal4x3>> (decimal, con la coma) — se parte automáticamente. Dejar vacío si el producto no tiene este nivel."),
                ("5x3",                 "Precio del nivel 5x3",                        "Precio", "Corresponde a <<5x3P>>/<<decimal5x3>>, igual que la columna oferta. Dejar vacío si no aplica."),
                ("6x3",                 "Precio del nivel 6x3",                        "Precio", "Corresponde a <<6x3P>>/<<decimal6x3>>, igual que la columna oferta. Dejar vacío si no aplica."),
                ("vigencia",            "Texto de vigencia de la oferta",              "Texto",  "Corresponde a <<Vigencia>>, si la plantilla la usa. Opcional."),
                ("aclaracion1",         "Primera aclaración / legal",                  "Texto",  "Corresponde a <<Aclaracion1>>, si la plantilla la usa. Opcional."),
                ("aclaracion2",         "Segunda aclaración",                          "Texto",  "Opcional."),
                ("aclaracion3",         "Tercera aclaración (ej. alcohol)",            "Texto",  "Opcional."),
            ],
        )

    # Redexpres — columnas y ejemplos extraídos del Excel real de referencia
    # (planilla ya usada con la plantilla A4 REDEX.pptx), no inventados.
    return _build_template_workbook(
        headers=["DESCRIPCION", "precioActual", "OFERTADET", "OFERTA", "ACLARACION", "OTRA ACLARACION", "VIGENCIA", "CODIGO"],
        col_widths=[36, 14, 14, 14, 32, 40, 30, 16],
        examples=[
            ("ACEITE GIRASOL FAMILIA 1.5L",   139, "",      "",      "Precio válido en todos los locales.", "",                                                                "Válido del 10 al 16 de julio", "84512"),
            ("ARROZ BLUE PATNA 1KG",           59, "Combo", "3x150", "Descuento aplicado en caja.",         "",                                                                "Válido del 10 al 16 de julio", "63321"),
            ("GASEOSA COCA-COLA 1.5L",         89, "M x N", "3x2",   "Llevando 3 pagás 2.",                 "",                                                                "Válido del 10 al 16 de julio", "41207"),
            ("CERVEZA PILSEN LATA 473ML",      69, "Combo", "6x360", "Descuento aplicado en caja.",         "Prohibida la venta de bebidas alcohólicas a menores de 18 años", "Válido del 10 al 16 de julio", "55890/55891"),
            ("YOGUR CONAPROLE FRUTILLA 1KG",   99, "",      "",      "Precio válido en todos los locales.", "",                                                                "Válido del 10 al 16 de julio", "72190"),
            ("PAPEL HIGIÉNICO SCOTT X4",      119, "M x N", "2x1",   "Llevando 2 pagás 1.",                 "",                                                                "Válido del 10 al 16 de julio", "30044"),
            ("JAMÓN COOK FUD FETEADO 200G",   149, "",      "",      "Descuento aplicado en caja.",         "",                                                                "Válido del 10 al 16 de julio", "18765-18770"),
            ("DETERGENTE OMO LÍQUIDO 3L",     259, "Combo", "2x460", "Descuento aplicado en caja.",         "",                                                                "Válido del 10 al 16 de julio", "91002"),
            ("VINO TANNAT RESERVA 750ML",     349, "",      "",      "Precio válido en todos los locales.", "Prohibida la venta de bebidas alcohólicas a menores de 18 años", "Válido del 10 al 16 de julio", "67788"),
            ("GALLETITAS TITA CHOCOLATE X6",   79, "M x N", "3x2",   "Llevando 3 pagás 2.",                 "",                                                                "Válido del 10 al 16 de julio", "20456"),
        ],
        var_docs=[
            ("DESCRIPCION",     "Nombre del producto",                                     "Texto",  "Corresponde a <<Descripcion>>. Palabras en MAYÚSCULAS se ven en negrita."),
            ("precioActual",    "Precio unitario del producto",                            "Precio", "Corresponde a <<Precio>>. Si OFERTADET=Combo o M x N, se usa como precio 'la unidad' en la mecánica, y el precio grande final sale de OFERTA."),
            ("OFERTADET",       "Tipo de mecánica: 'Combo', 'M x N', o vacío = precio fijo","Lista",  "Vacío = OFERTA y la mecánica quedan en blanco (solo precio)."),
            ("OFERTA",          "Detalle de la mecánica según OFERTADET",                  "Texto",  "Combo: 'CANTIDADxPRECIO_TOTAL' (ej. '3x150'). M x N: 'CANTIDADxPAGADAS' (ej. '3x2')."),
            ("ACLARACION",      "Aclaración principal debajo del producto",                "Texto",  "Corresponde a <<Aclaracion1>>. Ej: 'Descuento aplicado en caja.'"),
            ("OTRA ACLARACION", "Segunda aclaración (legales, restricciones)",             "Texto",  "Corresponde a <<OtraAclaracion1>>. Usar para el disclaimer de alcohol en bebidas."),
            ("VIGENCIA",        "Texto de vigencia de la oferta",                          "Texto",  "Corresponde a <<Vigencia1>>. Ej: 'Válido del 10 al 16 de julio'."),
            ("CODIGO",          "Código de artículo",                                      "Texto",  "No se muestra directo, pero si tiene '/' o un rango ('123-456') activa el texto 'unidad' junto al precio."),
        ],
        dropdown={"OFERTADET": ["Combo", "M x N", ""]},
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
