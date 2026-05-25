"""Cenefas PPTX generator — ported from generar_cenefas.py."""
import copy
import io
import re
import unicodedata
from typing import Any

import openpyxl
from lxml import etree
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Pt

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

P1_FONT_SIZE  = 16      # pt — "Precio Final" / "6X" label
P1_BOLD       = False   # label goes without bold
P1_MARGIN_EMU = 253200  # gap between P1 bottom and price shape top
                        # 16pt text ≈ 203200 EMU + ~50000 visual margin

PRICE_SYMBOL_PT = 55    # pt — $ / U$S symbol inside the price run

DELI_SUBCATS = {"FIAMBRES", "QUESOS"}
NO_UNIDAD_SUBCATS = {"CARNES", "FIAMBRES", "EMBUTIDOS CARNE", "QUESOS"}


# ---------------------------------------------------------------------------
# Price formatting
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


# ---------------------------------------------------------------------------
# Combo parsing
# ---------------------------------------------------------------------------

def parse_combo(oferta_str: str) -> tuple[str, float]:
    s = str(oferta_str or "").strip()
    m = re.match(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*$", s)
    if m:
        amount = float(m.group(2).replace(",", "."))
        return m.group(1) + "X", amount
    return "", 0.0


# ---------------------------------------------------------------------------
# Bold detection for brand names in ALL-CAPS
# ---------------------------------------------------------------------------

def split_caps(text: str) -> list[tuple[str, bool]]:
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


# ---------------------------------------------------------------------------
# Row processing
# ---------------------------------------------------------------------------

def process_row(row: tuple, h: dict, vigencia: str, aclaracion: str, otra_alcohol: str) -> dict:
    ofertadet = str(row[h["OFERTADET"]] or "").strip()
    precio_raw = row[h["PRECIO"]]
    oferta_raw = row[h["OFERTA"]]
    desc = str(row[h["DESCRIPCION"]] or "").strip()
    cat = str(row[h["Categoria"]] or "").strip()
    subcat = str(row[h["subcategoria"]] or "").strip()
    moneda = str(row[h["MONEDA"]] or "").strip()

    prefix = "U$S " if moneda == "U$S" else "$"
    precio = float(precio_raw) if precio_raw else 0.0

    p1 = ""
    precio_display = ""
    mecanica = ""

    if ofertadet == "Combo":
        p1, amount = parse_combo(oferta_raw)
        precio_display = prefix + fmt_price(amount)
        mecanica = f"Comprando 2, {prefix}{fmt_price(precio)} c/u"

    elif ofertadet == "M x N":
        precio_display = prefix + fmt_price(precio)
        mecanica = f"Comprando 2, {prefix}{fmt_price(precio)} c/u"

    else:
        precio_val = precio
        if subcat in DELI_SUBCATS:
            dl = desc.lower()
            if ". kg" in dl or " kg" in dl or dl.endswith("kg") or "100g" in dl:
                precio_val = precio / 10
                desc = re.sub(r"\.\s*[Kk]g\b", ". 100g", desc)
                desc = re.sub(r"\s+[Kk]g\b", " 100g", desc)
        precio_display = prefix + fmt_price(precio_val)

    if not p1:
        p1 = "Precio Final"

    if ofertadet in ("Precio fijo", "% descuento"):
        unidad = "" if subcat in NO_UNIDAD_SUBCATS else "unidad"
    else:
        unidad = ""

    otra = otra_alcohol if cat == "BEBIDAS CON ALCOHOL" else ""

    return {
        "p1": p1,
        "precio": precio_display,
        "mecanica": mecanica,
        "descripcion": desc,
        "unidad": unidad,
        "vigencia": vigencia,
        "aclaracion": aclaracion,
        "otra_aclaracion": otra,
    }


def _normalize_header(name: str) -> str:
    """Normaliza a mayúsculas sin tildes para matching flexible de columnas."""
    return unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode().upper().strip()


_EXPECTED_HEADERS = {
    _normalize_header(k): k
    for k in ["Categoria", "subcategoria", "OFERTADET", "DESCRIPCION", "PRECIO", "OFERTA", "MONEDA"]
}


def load_products_from_bytes(
    excel_bytes: bytes,
    vigencia: str,
    aclaracion: str,
    otra_alcohol: str,
) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    if "Cenefas" not in wb.sheetnames:
        raise ValueError("Hoja 'Cenefas' no encontrada. El archivo Excel debe tener una hoja llamada 'Cenefas'.")
    ws = wb["Cenefas"]
    raw_headers = [cell.value for cell in ws[1]]
    # Mapeo flexible: normaliza el header del Excel al nombre canónico esperado
    h = {}
    for idx, raw in enumerate(raw_headers):
        if not raw:
            continue
        canonical = _EXPECTED_HEADERS.get(_normalize_header(str(raw)))
        h[canonical or str(raw)] = idx

    products = []
    seen: set = set()

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[h["OFERTADET"]]:
            continue
        data = process_row(row, h, vigencia, aclaracion, otra_alcohol)
        key = (data["p1"], data["precio"], data["mecanica"], data["descripcion"].lower().strip())
        if key not in seen:
            seen.add(key)
            products.append(data)

    return products


# ---------------------------------------------------------------------------
# PPTX manipulation
# ---------------------------------------------------------------------------

def _shape_text(shape) -> str:
    if not shape.has_text_frame:
        return ""
    return "".join(r.text for p in shape.text_frame.paragraphs for r in p.runs)


def _set_text(shape, text: str) -> None:
    if not shape.has_text_frame:
        return
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            run.text = text
            return
    if shape.text_frame.paragraphs:
        para = shape.text_frame.paragraphs[0]
        run = para.add_run()
        run.text = text


def _set_price(shape, text: str) -> None:
    if not shape.has_text_frame:
        return

    if text.startswith("U$S "):
        symbol, number = "U$S ", text[4:]
    elif text.startswith("$"):
        symbol, number = "$", text[1:]
    else:
        _set_text(shape, text)
        return

    target_para = None
    for para in shape.text_frame.paragraphs:
        if para.runs:
            target_para = para
            break
    if target_para is None:
        return

    p_elem = target_para._p
    tmpl_r = copy.deepcopy(target_para.runs[0]._r)

    for r_elem in list(p_elem.findall(qn("a:r"))):
        p_elem.remove(r_elem)

    sym_r = copy.deepcopy(tmpl_r)
    sym_r.find(qn("a:t")).text = symbol
    rPr = sym_r.find(qn("a:rPr"))
    if rPr is not None:
        rPr.set("sz", str(PRICE_SYMBOL_PT * 100))

    num_r = copy.deepcopy(tmpl_r)
    num_r.find(qn("a:t")).text = number

    # Insert runs BEFORE <a:endParaRPr> to maintain valid OOXML element order.
    # Appending after endParaRPr causes PowerPoint to silently ignore the runs.
    end_rpr = p_elem.find(qn("a:endParaRPr"))
    if end_rpr is not None:
        idx = list(p_elem).index(end_rpr)
        p_elem.insert(idx, num_r)
        p_elem.insert(idx, sym_r)
    else:
        p_elem.append(sym_r)
        p_elem.append(num_r)


def _set_desc(shape, text: str) -> None:
    if not shape.has_text_frame:
        return
    tf = shape.text_frame
    target_para = None
    for para in tf.paragraphs:
        if para.runs:
            target_para = para
            break
    if target_para is None:
        return

    parts = split_caps(text)
    first_seg, first_bold = parts[0]
    first_run = target_para.runs[0]
    first_run.text = first_seg
    first_run.font.bold = True if first_bold else None

    p_elem = target_para._p
    all_r = list(p_elem.findall(qn("a:r")))
    for r_elem in all_r[1:]:
        p_elem.remove(r_elem)

    for seg, bold in parts[1:]:
        if not seg:
            continue
        new_run = target_para.add_run()
        new_run.text = seg
        if bold:
            new_run.font.bold = True


def _set_p1(shape, text: str) -> None:
    _set_text(shape, text)
    if not shape.has_text_frame:
        return
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            run.font.size = Pt(P1_FONT_SIZE)
            run.font.bold = P1_BOLD


def _fill_slot(shapes, data: dict, adjust_p1: bool = True) -> None:
    p1_shape = None
    price_shape = None

    for shape in shapes:
        t = _shape_text(shape)
        if re.search(r"<<P\d+>>", t):
            p1_shape = shape
            _set_p1(shape, data["p1"])
        elif re.search(r"Precio\s+\d+", t) or re.search(r"<<Precio\d+>>", t):
            price_shape = shape
            _set_price(shape, data["precio"])
        elif re.search(r"<<Mecanica\d+>>", t):
            _set_text(shape, data["mecanica"])
        elif "<<" in t and "Descripci" in t:
            _set_desc(shape, data["descripcion"])
        elif re.search(r"<<UnidadMedida\d+>>", t):
            _set_text(shape, data["unidad"])
        elif re.search(r"<<Vigencia\d+>>", t):
            _set_text(shape, data["vigencia"])
        elif re.search(r"<<Aclaracion\d+>>", t):
            _set_text(shape, data["aclaracion"])
        elif re.search(r"<<OtraAclaracion\d+>>", t):
            _set_text(shape, data["otra_aclaracion"])

    # Ajuste dinámico de P1 solo para plantillas de 1 producto por hoja (A4).
    # En multi-producto, P1 queda en la posición fija de la plantilla.
    if adjust_p1 and p1_shape is not None and price_shape is not None:
        p1_shape.top = price_shape.top - P1_MARGIN_EMU


def _clear_slot(shapes) -> None:
    for shape in shapes:
        if not shape.has_text_frame:
            continue
        t = _shape_text(shape)
        if "<<" in t or re.search(r"Precio\s+\d", t):
            _set_text(shape, "")


def _slot_num(shape) -> int | None:
    """Return the slot number (1–9) if the shape belongs to a numbered product slot."""
    t = _shape_text(shape)
    for n in range(1, 10):
        if (f"<<P{n}>>" in t
                or f"Precio {n}" in t
                or f"<<Precio{n}>>" in t
                or f"<<Mecanica{n}>>" in t
                or f"<<UnidadMedida{n}>>" in t
                or f"<<Vigencia{n}>>" in t
                or f"<<Aclaracion{n}>>" in t
                or f"<<OtraAclaracion{n}>>" in t
                or ("<<" in t and "Descripci" in t and str(n) in t)):
            return n
    return None


def _get_slots(shapes) -> list[list]:
    """Group shapes by product slot. Supports 1–9 products per slide.

    Strategy:
    - If multiple distinct slot numbers are detected (e.g. <<P1>>/<<P2>>/…), use
      those buckets directly (standard numbered templates, Pinchos 1-9).
    - If all shapes map to slot 1 (templates where every placeholder is labelled
      "1" regardless of position, like Bases cenefas BLACK), count the price/P1
      anchors to determine how many product copies are present, then split by
      index into equal groups.
    """
    buckets: dict[int, list] = {n: [] for n in range(1, 10)}
    for shape in shapes:
        n = _slot_num(shape)
        if n:
            buckets[n].append(shape)

    present = sorted(n for n in range(1, 10) if buckets[n])

    if len(present) > 1:
        return [buckets[n] for n in present]

    # All shapes land in slot 1 — count "P1 label" anchors to find product count.
    # Use price shapes as fallback only if no P1 labels exist (e.g. Pinchos-style).
    all_shapes = list(shapes)
    p1_count = sum(1 for s in all_shapes if re.search(r"<<P\d+>>", _shape_text(s)))
    price_count = sum(
        1 for s in all_shapes
        if re.search(r"Precio\s+\d+|<<Precio\d+>>", _shape_text(s))
    )
    products = max(p1_count if p1_count > 0 else price_count, 1)
    if products <= 1:
        return [all_shapes]
    per_slot = len(all_shapes) // products
    return [all_shapes[i * per_slot:(i + 1) * per_slot] for i in range(products)]



def _center_content_a4(slide, slide_width: int) -> None:
    """Centra el contenido en plantillas de 1 producto por hoja.

    El shape del precio en la plantilla A4 tiene width > slide_width (se extiende
    fuera del slide). En lugar de mover shapes, ponemos cada text-shape a ancho
    completo y alineación CENTER para que el contenido quede centrado en la hoja.
    """
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        shape.left = 0
        shape.width = slide_width
        for para in shape.text_frame.paragraphs:
            para.alignment = PP_ALIGN.CENTER


def _add_slide_from_template(prs, layout, template_shape_xmls):
    new_slide = prs.slides.add_slide(layout)
    sp_tree = new_slide.shapes._spTree
    for child in list(sp_tree):
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag not in ("nvGrpSpPr", "grpSpPr"):
            sp_tree.remove(child)
    for xml_elem in template_shape_xmls:
        sp_tree.append(copy.deepcopy(xml_elem))
    return new_slide


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_pptx_bytes(
    excel_bytes: bytes,
    template_bytes: bytes,
    vigencia: str,
    aclaracion: str,
    otra_alcohol: str,
) -> bytes:
    products = load_products_from_bytes(excel_bytes, vigencia, aclaracion, otra_alcohol)

    prs = Presentation(io.BytesIO(template_bytes))
    if not prs.slides:
        raise ValueError("La plantilla PPTX está vacía.")

    # Single-slide templates: slide 0 is the product template.
    # Multi-slide templates: slide 0 is a cover kept as-is, slide 1 is the template.
    template_slide = prs.slides[0] if len(prs.slides) == 1 else prs.slides[1]
    layout = template_slide.slide_layout

    template_shape_xmls = [copy.deepcopy(shape._element) for shape in template_slide.shapes]

    # Detect products per slide from the template's slot structure
    initial_slots = _get_slots(list(template_slide.shapes))
    products_per_slide = max(len(initial_slots), 1)

    groups = [products[i:i + products_per_slide] for i in range(0, len(products), products_per_slide)]

    for idx, group in enumerate(groups):
        slide = template_slide if idx == 0 else _add_slide_from_template(prs, layout, template_shape_xmls)
        cur_slots = _get_slots(list(slide.shapes))
        for i, product in enumerate(group):
            if i < len(cur_slots):
                _fill_slot(cur_slots[i], product, adjust_p1=(products_per_slide == 1))
        for i in range(len(group), products_per_slide):
            if i < len(cur_slots):
                _clear_slot(cur_slots[i])
        if products_per_slide == 1:
            _center_content_a4(slide, prs.slide_width)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Excel template generation
# ---------------------------------------------------------------------------

def generate_template_bytes() -> bytes:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    HEADERS = ["Categoria", "subcategoria", "OFERTADET", "DESCRIPCION", "PRECIO", "OFERTA", "MONEDA"]
    EXAMPLES: list[tuple] = [
        ("ALIMENTOS",           "GALLETITAS",        "Precio fijo",  "Galletitas OREO 117g",          1500,  "",       "$"),
        ("BEBIDAS SIN ALCOHOL", "GASEOSAS",           "Combo",        "Coca-Cola 2.25L",               2500,  "2X4500", "$"),
        ("BEBIDAS SIN ALCOHOL", "AGUA",               "M x N",        "Agua SALUS 1.5L",               800,   "",       "$"),
        ("LIMPIEZA",            "LIMPIADORES",        "% descuento",  "Lavandina AYUDIN 2L",           850,   "",       "$"),
        ("FIAMBRES Y QUESOS",   "QUESOS",             "Precio fijo",  "Queso Barra por Kg.",           12000, "",       "$"),
        ("BEBIDAS CON ALCOHOL", "VINOS",              "Precio fijo",  "Vino NORTON Malbec 750ml",      3200,  "",       "$"),
        ("ELECTRODOMESTICOS",   "ELECTRODOMESTICOS",  "Precio fijo",  "Licuadora PHILIPS HR2100",      45,    "",       "U$S"),
    ]

    wb = openpyxl.Workbook()

    # ── Cenefas sheet ──────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Cenefas"

    header_fill = PatternFill("solid", fgColor="1E3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    even_fill   = PatternFill("solid", fgColor="EEF2F7")

    for col, name in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, data in enumerate(EXAMPLES, 2):
        fill = even_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(vertical="center")
            if fill:
                cell.fill = fill

    col_widths = [22, 20, 14, 36, 10, 12, 10]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    dv_tipo = DataValidation(type="list", formula1='"Precio fijo,% descuento,Combo,M x N"', allow_blank=True)
    dv_tipo.sqref = "C2:C5000"
    ws.add_data_validation(dv_tipo)

    dv_moneda = DataValidation(type="list", formula1='"$,U$S"', allow_blank=True)
    dv_moneda.sqref = "G2:G5000"
    ws.add_data_validation(dv_moneda)

    # ── Instrucciones sheet ────────────────────────────────────────────────
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
        cell.fill = inst_header_fill
        cell.font = inst_header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    rows = [
        ("Categoria",    "Categoría del producto",              "Texto libre",                     "Ej: ALIMENTOS, BEBIDAS CON ALCOHOL, CARNES"),
        ("subcategoria", "Subcategoría del producto",           "Texto libre",                     "QUESOS y FIAMBRES: precio por 100g si desc tiene 'kg'. CARNES/FIAMBRES/QUESOS: sin unidad."),
        ("OFERTADET",    "Tipo de oferta",                      "Precio fijo / % descuento / Combo / M x N", "Determina cómo se muestra el precio en la cenefa"),
        ("DESCRIPCION",  "Nombre del producto tal como aparece","Texto libre",                     "Las palabras en MAYÚSCULAS se muestran en negrita"),
        ("PRECIO",       "Precio unitario (número)",            "Número (ej: 1500, 45.90)",        "Para Combo: precio individual. Para dólares usa MONEDA=U$S"),
        ("OFERTA",       "Solo para Combo: cantidad y precio total", "Formato: 2X4500",            "2X4500 = 2 unidades por $4500. Vacío para otros tipos."),
        ("MONEDA",       "Moneda del precio",                   "$ o U$S",                         "$ = pesos uruguayos. U$S = dólares."),
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
