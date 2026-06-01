"""Motor de renderizado PPTX — genera presentaciones desde datos de productos."""
import copy
import io
import re

from lxml import etree
from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Pt

from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.formatters import (
    split_caps,
    P1_FONT_SIZE,
    P1_BOLD,
    P1_MARGIN_EMU,
    PRICE_DECIMAL_PT,
    PBANCO_INT_PT,
    UNIDAD_PRECIO_PT,
    UNIDAD_PBANCO_PT,
)

# ---------------------------------------------------------------------------
# Helpers de texto
# ---------------------------------------------------------------------------

def _shape_text(shape) -> str:
    if not shape.has_text_frame:
        return ""
    return "".join(r.text for p in shape.text_frame.paragraphs for r in p.runs)


def _set_text(shape, text: str) -> None:
    if not shape.has_text_frame:
        return
    for para in shape.text_frame.paragraphs:
        runs = para.runs
        if runs:
            runs[0].text = text
            for run in runs[1:]:
                run.text = ""
            return
    if shape.text_frame.paragraphs:
        para = shape.text_frame.paragraphs[0]
        run = para.add_run()
        run.text = text


def _set_text_sized(shape, text: str, pt: int) -> None:
    _set_text(shape, text)
    if not shape.has_text_frame:
        return
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            run.font.size = Pt(pt)


def _set_price(shape, text: str, int_pt: int | None = None) -> None:
    """Renderiza precio con símbolo, entero y decimal en runs separados.

    El decimal se fuerza a PRICE_DECIMAL_PT; símbolo e entero heredan el template.
    """
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
    tmpl_r_sym = copy.deepcopy(target_para.runs[0]._r)
    tmpl_r_int = copy.deepcopy(target_para.runs[-1]._r)

    for r_elem in list(p_elem.findall(qn("a:r"))):
        p_elem.remove(r_elem)

    if "," in number:
        num_int, num_dec_digits = number.rsplit(",", 1)
        num_dec = "," + num_dec_digits
    else:
        num_int = number
        num_dec = None

    sym_r = copy.deepcopy(tmpl_r_sym)
    sym_r.find(qn("a:t")).text = symbol

    int_r = copy.deepcopy(tmpl_r_int)
    int_r.find(qn("a:t")).text = num_int

    runs = [sym_r, int_r]

    if num_dec:
        dec_r = copy.deepcopy(tmpl_r_int)
        dec_r.find(qn("a:t")).text = num_dec
        dec_rPr = dec_r.find(qn("a:rPr"))
        if dec_rPr is not None:
            dec_rPr.set("sz", str(PRICE_DECIMAL_PT * 100))
        runs.append(dec_r)

    end_rpr = p_elem.find(qn("a:endParaRPr"))
    if end_rpr is not None:
        idx = list(p_elem).index(end_rpr)
        for r in reversed(runs):
            p_elem.insert(idx, r)
    else:
        for r in runs:
            p_elem.append(r)


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
    tmpl_r = copy.deepcopy(first_run._r)
    first_run.text = first_seg
    first_run.font.bold = first_bold

    p_elem = target_para._p
    all_r = list(p_elem.findall(qn("a:r")))
    for r_elem in all_r[1:]:
        p_elem.remove(r_elem)

    for seg, bold in parts[1:]:
        if not seg:
            continue
        new_r = copy.deepcopy(tmpl_r)
        new_r.find(qn("a:t")).text = seg
        rPr = new_r.find(qn("a:rPr"))
        if rPr is not None:
            rPr.set("b", "1" if bold else "0")
        end_rpr = p_elem.find(qn("a:endParaRPr"))
        if end_rpr is not None:
            p_elem.insert(list(p_elem).index(end_rpr), new_r)
        else:
            p_elem.append(new_r)


def _set_normAutofit(shape) -> None:
    """Cambia spAutoFit → normAutofit para que el texto se achique en vez de expandir el cuadro."""
    if not shape.has_text_frame:
        return
    body_pr = shape.text_frame._txBody.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    for tag in (qn("a:spAutoFit"), qn("a:noAutofit")):
        child = body_pr.find(tag)
        if child is not None:
            body_pr.remove(child)
    if body_pr.find(qn("a:normAutofit")) is None:
        body_pr.append(etree.Element(qn("a:normAutofit")))


def _set_p1(shape, text: str) -> None:
    _set_text(shape, text)
    if not shape.has_text_frame:
        return
    is_combo_label = bool(re.match(r"^\d+X$", text.strip()))
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if not is_combo_label:
                run.font.size = Pt(P1_FONT_SIZE)
            run.font.bold = P1_BOLD


def _is_multi_sku(code: str) -> bool:
    return bool(code and ("/" in code or re.search(r"\d\s*[-–—]\s*\d", code)))


# ---------------------------------------------------------------------------
# Llenado de slots
# ---------------------------------------------------------------------------

def _fill_slot(shapes, data: dict, adjust_p1: bool = True) -> None:
    expanded = list(shapes)
    for shape in list(shapes):
        if hasattr(shape, "shapes"):
            expanded.extend(shape.shapes)

    p1_shape    = None
    price_shape = None
    code  = data.get("code", "")
    multi = _is_multi_sku(code)

    for shape in expanded:
        t = _shape_text(shape)
        if re.search(r"<<P\d+>>", t):
            p1_shape = shape
            _set_p1(shape, data["p1"])
        elif re.search(r"Precio\s+\d+", t) or re.search(r"<<Precio\d*>>", t):
            price_shape = shape
            _set_price(shape, data["precio"])
        elif re.search(r"<<Mecanica\d+>>", t):
            _set_text(shape, data["mecanica"])
        elif "<<" in t and "Descripci" in t:
            _set_desc(shape, data["descripcion"])
            _set_normAutofit(shape)
        elif re.search(r"<<UnidadMedida\d+>>", t):
            _set_text(shape, data["unidad"] if multi else "")
        elif re.search(r"<<Vigencia\d*>>", t):
            _set_text(shape, data["vigencia"])
        elif re.search(r"<<Aclaracion\d*>>", t):
            _set_text(shape, data["aclaracion"])
        elif re.search(r"<<OtraAclaracion\d*>>", t):
            _set_text(shape, data["otra_aclaracion"])
        elif re.search(r"<<[Cc]ode\d*>>", t):
            _set_text(shape, code)
        elif re.search(r"<<[Pp][Bb]anco\d*>>", t):
            _set_price(shape, data.get("pbanco", ""), int_pt=PBANCO_INT_PT)
        elif re.search(r"<<[Bb]anco\d*>>", t):
            _set_text(shape, data.get("banco", ""))
        elif re.search(r"<<UnidadPrecio\d*>>", t):
            _set_text_sized(shape, "unidad" if multi else "", UNIDAD_PRECIO_PT)
        elif re.search(r"<<UnidadPBanco\d*>>", t):
            _set_text_sized(shape, "unidad" if multi else "", UNIDAD_PBANCO_PT)
        elif t.strip().lower() == "unidad":
            _set_text(shape, "unidad" if multi else "")

    if adjust_p1 and p1_shape is not None and price_shape is not None:
        p1_shape.top = price_shape.top - P1_MARGIN_EMU


def _clear_slot(shapes) -> None:
    for shape in shapes:
        if not shape.has_text_frame:
            continue
        t = _shape_text(shape)
        if "<<" in t or re.search(r"Precio\s+\d", t):
            _set_text(shape, "")


# ---------------------------------------------------------------------------
# Detección de slots
# ---------------------------------------------------------------------------

def _slot_num(shape) -> int | None:
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
                or f"<<UnidadPrecio{n}>>" in t
                or f"<<UnidadPBanco{n}>>" in t
                or ("<<" in t and "Descripci" in t and str(n) in t)):
            return n
    return None


def _buckets_coherent(buckets: dict, present: list) -> bool:
    """True si las shapes de cada bucket están en la misma región visual (spread vertical < 3M EMU)."""
    for n in present:
        shapes_in_bucket = buckets[n]
        if len(shapes_in_bucket) < 2:
            continue
        tops = [s.top for s in shapes_in_bucket]
        if max(tops) - min(tops) > 3_000_000:
            return False
    return True


def _assign_by_nearest_anchor(anchors: list, all_shapes: list) -> list[list]:
    """Asigna cada shape al slot cuyo anchor es espacialmente más cercano (para plantillas Pinchos)."""
    products = len(anchors)
    anchors_sorted = sorted(
        anchors,
        key=lambda s: (s.top + s.height // 2, s.left + s.width // 2),
    )

    def _ctr(s):
        return (s.left + s.width / 2, s.top + s.height / 2)

    anchor_centers = [_ctr(a) for a in anchors_sorted]
    slots: list[list] = [[] for _ in range(products)]
    for shape in all_shapes:
        cx, cy = _ctr(shape)
        best = min(
            range(products),
            key=lambda i: (cx - anchor_centers[i][0]) ** 2 + (cy - anchor_centers[i][1]) ** 2,
        )
        slots[best].append(shape)
    return slots


def _get_slots(shapes) -> list[list]:
    """Agrupa shapes por slot de producto. Soporta 1–9 productos por slide."""
    buckets: dict[int, list] = {n: [] for n in range(1, 10)}
    for shape in shapes:
        n = _slot_num(shape)
        if n:
            buckets[n].append(shape)

    present = sorted(n for n in range(1, 10) if buckets[n])

    if len(present) > 1:
        if _buckets_coherent(buckets, present):
            return [buckets[n] for n in present]
        all_shapes = list(shapes)
        anchors = [s for s in all_shapes if re.search(r"Precio\s+\d+|<<Precio\d*>>", _shape_text(s))]
        if not anchors:
            anchors = [s for s in all_shapes if re.search(r"<<P\d+>>", _shape_text(s))]
        if anchors:
            return _assign_by_nearest_anchor(anchors, all_shapes)
        return [buckets[n] for n in present]

    all_shapes = list(shapes)
    anchors = [s for s in all_shapes if re.search(r"<<P\d+>>", _shape_text(s))]
    if not anchors:
        anchors = [s for s in all_shapes if re.search(r"Precio\s+\d+|<<Precio\d*>>", _shape_text(s))]

    products = len(anchors)
    if products <= 1:
        return [all_shapes]

    xs = [s.left for s in anchors]
    ys = [s.top  for s in anchors]
    horizontal = (max(xs) - min(xs)) >= (max(ys) - min(ys))

    key = (lambda s: s.left + s.width // 2) if horizontal else (lambda s: s.top + s.height // 2)
    sorted_shapes = sorted(all_shapes, key=key)
    per_slot  = len(sorted_shapes) // products
    slots     = [sorted_shapes[i * per_slot:(i + 1) * per_slot] for i in range(products)]
    remainder = sorted_shapes[products * per_slot:]
    if remainder:
        slots[-1].extend(remainder)
    return slots


# ---------------------------------------------------------------------------
# Layout A4
# ---------------------------------------------------------------------------

def _center_content_a4(slide, slide_width: int) -> None:
    """Centra shapes de texto en slides A4 sin GroupShapes."""
    if any(hasattr(s, "shapes") for s in slide.shapes):
        return
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        shape.left  = 0
        shape.width = slide_width
        for para in shape.text_frame.paragraphs:
            para.alignment = PP_ALIGN.CENTER


def _align_bank_group_a4(slide) -> None:
    """Recorta el ancho del precio para que no invada la columna del GROUP bancario."""
    price_shape = None
    group_shape = None
    for shape in slide.shapes:
        if hasattr(shape, "shapes"):
            group_shape = shape
        elif shape.has_text_frame:
            t = _shape_text(shape)
            if re.search(r"<<Precio\d*>>", t) or re.search(r"Precio\s+\d+", t):
                price_shape = shape
    if price_shape is None or group_shape is None:
        return
    gap = 150000  # ~4mm
    price_right_max = group_shape.left - gap
    if price_shape.left + price_shape.width > price_right_max:
        price_shape.width = price_right_max - price_shape.left


# ---------------------------------------------------------------------------
# Construcción de slides
# ---------------------------------------------------------------------------

def _add_slide_from_template(prs, layout, template_shape_xmls):
    new_slide = prs.slides.add_slide(layout)
    sp_tree   = new_slide.shapes._spTree
    for child in list(sp_tree):
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag not in ("nvGrpSpPr", "grpSpPr"):
            sp_tree.remove(child)
    for xml_elem in template_shape_xmls:
        sp_tree.append(copy.deepcopy(xml_elem))
    return new_slide


# ---------------------------------------------------------------------------
# Entry point principal
# ---------------------------------------------------------------------------

def generate_pptx_bytes(
    excel_bytes: bytes,
    template_bytes: bytes,
    vigencia: str,
    aclaracion: str,
    otra_alcohol: str,
    banco: str = "",
) -> bytes:
    products = load_products_from_bytes(excel_bytes, vigencia, aclaracion, otra_alcohol, banco)

    prs = Presentation(io.BytesIO(template_bytes))
    if not prs.slides:
        raise ValueError("La plantilla PPTX está vacía.")

    template_slide     = prs.slides[0] if len(prs.slides) == 1 else prs.slides[1]
    layout             = template_slide.slide_layout
    template_shape_xmls = [copy.deepcopy(shape._element) for shape in template_slide.shapes]

    initial_slots      = _get_slots(list(template_slide.shapes))
    products_per_slide = max(len(initial_slots), 1)

    groups = [products[i:i + products_per_slide] for i in range(0, len(products), products_per_slide)]

    for idx, group in enumerate(groups):
        slide     = template_slide if idx == 0 else _add_slide_from_template(prs, layout, template_shape_xmls)
        cur_slots = _get_slots(list(slide.shapes))
        for i, product in enumerate(group):
            if i < len(cur_slots):
                _fill_slot(cur_slots[i], product, adjust_p1=(products_per_slide == 1))
        for i in range(len(group), products_per_slide):
            if i < len(cur_slots):
                _clear_slot(cur_slots[i])
        if products_per_slide == 1:
            _center_content_a4(slide, prs.slide_width)
            _align_bank_group_a4(slide)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
