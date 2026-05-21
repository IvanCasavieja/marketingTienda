"""Cenefas PPTX generator — ported from generar_cenefas.py."""
import copy
import io
import re
from typing import Any

import openpyxl
from lxml import etree
from pptx import Presentation
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
    desc = str(row[4] or "").strip()
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


def load_products_from_bytes(
    excel_bytes: bytes,
    vigencia: str,
    aclaracion: str,
    otra_alcohol: str,
) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb["Cenefas"]
    headers = [cell.value for cell in ws[1]]
    h = {name: idx for idx, name in enumerate(headers) if name}

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
    p_elem.append(sym_r)

    num_r = copy.deepcopy(tmpl_r)
    num_r.find(qn("a:t")).text = number
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


def _fill_slot(shapes, data: dict) -> None:
    p1_shape = None
    price_shape = None

    for shape in shapes:
        t = _shape_text(shape)
        if "<<P1>>" in t:
            p1_shape = shape
            _set_p1(shape, data["p1"])
        elif "Precio 1" in t:
            price_shape = shape
            _set_price(shape, data["precio"])
        elif "<<Mecanica1>>" in t:
            _set_text(shape, data["mecanica"])
        elif "<<" in t and "Descripci" in t:
            _set_desc(shape, data["descripcion"])
        elif "<<UnidadMedida1>>" in t:
            _set_text(shape, data["unidad"])
        elif "<<Vigencia1>>" in t:
            _set_text(shape, data["vigencia"])
        elif "<<Aclaracion1>>" in t:
            _set_text(shape, data["aclaracion"])
        elif "<<OtraAclaracion1>>" in t:
            _set_text(shape, data["otra_aclaracion"])

    # Position P1 label dynamically above the price shape
    if p1_shape is not None and price_shape is not None:
        p1_shape.top = price_shape.top - P1_MARGIN_EMU


def _clear_slot(shapes) -> None:
    for shape in shapes:
        if not shape.has_text_frame:
            continue
        t = _shape_text(shape)
        if "<<" in t or "Precio 1" in t:
            _set_text(shape, "")


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
    template_slide = prs.slides[1]
    layout = template_slide.slide_layout

    template_shape_xmls = [copy.deepcopy(shape._element) for shape in template_slide.shapes]
    groups = [products[i:i + 3] for i in range(0, len(products), 3)]

    for idx, group in enumerate(groups):
        slide = template_slide if idx == 0 else _add_slide_from_template(prs, layout, template_shape_xmls)
        shapes = list(slide.shapes)
        slots = [shapes[0:8], shapes[8:16], shapes[16:24]]
        for i, product in enumerate(group):
            _fill_slot(slots[i], product)
        for i in range(len(group), 3):
            _clear_slot(slots[i])

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
