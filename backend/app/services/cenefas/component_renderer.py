"""Renderer de componentes v2 — genera PPTX desde definición JSON de componentes."""
import io
import re

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Cm, Pt

from app.services.cenefas.data_engine import load_products_from_bytes
from app.services.cenefas.formatters import split_caps
from app.services.cenefas.layout_engine import compute_layout, get_format
from app.services.cenefas.rules_engine import apply_visibility, evaluate_rules

# ---------------------------------------------------------------------------
# Dimensiones de slide por formato
# ---------------------------------------------------------------------------

FORMAT_SLIDES: dict[str, tuple] = {
    "a4":      (Cm(21.0),  Cm(29.7)),
    "a3":      (Cm(29.7),  Cm(42.0)),
    "3xa4":    (Cm(63.0),  Cm(29.7)),
    "pinchos": (Cm(10.5),  Cm(29.7)),
}

ALIGN_MAP = {
    "left":   PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right":  PP_ALIGN.RIGHT,
}

# ---------------------------------------------------------------------------
# Transforms de valores
# ---------------------------------------------------------------------------

def apply_transform(value: str, transform: str | None) -> str:
    """Aplica la transformación al valor del campo."""
    if not value or not transform or transform in ("none", "smart_bold"):
        return value or ""

    if transform in ("price_full", "price_integer", "price_decimal"):
        # value ya viene formateado como "$1.250,90" desde data_engine
        num = re.sub(r"[^\d.,]", "", value)
        if transform == "price_full":
            return value
        if transform == "price_integer":
            return num.rsplit(",", 1)[0] if "," in num else num
        if transform == "price_decimal":
            return ("," + num.rsplit(",", 1)[1]) if "," in num else ""

    if transform == "combo_quantity":
        m = re.match(r"(\d+X)", value.upper())
        return m.group(1) if m else value

    if transform == "combo_price":
        return value  # ya es el precio formateado

    if transform == "uppercase":
        return value.upper()

    return value


def hex_to_rgb(hex_color: str | None) -> RGBColor:
    if not hex_color:
        return RGBColor(0x1E, 0x29, 0x3B)
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return RGBColor(0x1E, 0x29, 0x3B)


# ---------------------------------------------------------------------------
# Renderizado de componentes individuales
# ---------------------------------------------------------------------------

def _enable_normAutofit(tf) -> None:
    body_pr = tf._txBody.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    for tag in (qn("a:spAutoFit"), qn("a:noAutofit")):
        el = body_pr.find(tag)
        if el is not None:
            body_pr.remove(el)
    if body_pr.find(qn("a:normAutofit")) is None:
        body_pr.append(etree.Element(qn("a:normAutofit")))


def add_text_component(slide, comp: dict, value: str) -> None:
    bounds = comp["computed_bounds"]
    style  = comp.get("style", {})

    txBox = slide.shapes.add_textbox(
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.3)),
    )
    tf = txBox.text_frame
    tf.word_wrap = True

    if style.get("auto_fit", True):
        _enable_normAutofit(tf)

    transform = comp.get("transform", "none")
    p = tf.paragraphs[0]
    p.alignment = ALIGN_MAP.get(style.get("align", "center"), PP_ALIGN.CENTER)

    if transform == "smart_bold":
        for segment, is_bold in split_caps(value):
            if not segment:
                continue
            run = p.add_run()
            run.text = segment
            _apply_run_style(run, style, bold_override=is_bold)
    else:
        run = p.add_run()
        run.text = value
        _apply_run_style(run, style)


def _apply_run_style(run, style: dict, bold_override: bool | None = None) -> None:
    font = run.font
    if style.get("font_size"):
        font.size = Pt(style["font_size"])
    font.bold = bold_override if bold_override is not None else style.get("font_bold", False)
    if style.get("color"):
        font.color.rgb = hex_to_rgb(style["color"])
    if style.get("font_family"):
        font.name = style["font_family"]


def add_shape_component(slide, comp: dict) -> None:
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

    bounds = comp["computed_bounds"]
    style  = comp.get("style", {})

    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.3)),
    )
    # Sin borde visible
    shape.line.fill.background()

    if style.get("background_color"):
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(style["background_color"])
    else:
        shape.fill.background()


def add_image_placeholder(slide, comp: dict, label: str) -> None:
    """Placeholder para imágenes — rectángulo gris con el nombre de la variable.

    Reemplazar por descarga real de URL cuando se soporte HTTP en el renderer.
    """
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

    bounds = comp["computed_bounds"]
    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.5)),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)  # slate-200
    shape.line.fill.background()

    # Label indicativo centrado
    tf = shape.text_frame
    tf.word_wrap = True
    p   = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = f"[{label}]"
    run.font.size  = Pt(9)
    run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)  # slate-400


# ---------------------------------------------------------------------------
# Render de un slide completo
# ---------------------------------------------------------------------------

def _render_slide(slide, comp_layout: list[dict], product: dict, slot_offset_x: float = 0.0) -> None:
    for comp in comp_layout:
        if not comp.get("visible", True):
            continue

        variable  = comp.get("variable")
        raw_value = str(product.get(variable, "") or "") if variable else ""
        transform = comp.get("transform", "none")
        value     = apply_transform(raw_value, transform)

        # Offset horizontal para layouts multi-slot
        if slot_offset_x > 0:
            cb  = comp["computed_bounds"].copy()
            cb["x"] = cb["x"] + slot_offset_x
            comp = {**comp, "computed_bounds": cb}

        comp_type = comp.get("type", "text")
        if comp_type == "text":
            add_text_component(slide, comp, value)
        elif comp_type == "shape":
            add_shape_component(slide, comp)
        elif comp_type == "image":
            add_image_placeholder(slide, comp, variable or "imagen")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def render_template_to_pptx(
    template_def: dict,
    products: list[dict],
    target_format: str = "a4",
) -> bytes:
    """Genera PPTX desde una definición v2 y una lista de productos procesados."""
    master_format = template_def.get("master_format", "a4")
    components    = template_def.get("components", [])
    rules         = template_def.get("rules", [])
    fmt_info      = get_format(target_format)
    slots         = fmt_info["slots"]

    slide_w, slide_h = FORMAT_SLIDES.get(target_format, FORMAT_SLIDES["a4"])

    prs = Presentation()
    prs.slide_width  = slide_w
    prs.slide_height = slide_h
    blank_layout     = prs.slide_layouts[6]

    # Calcular layout base una vez (posiciones en el formato destino)
    laid_out = compute_layout(components, target_format, master_format)

    groups = [products[i:i + slots] for i in range(0, len(products), slots)]

    for group in groups:
        slide = prs.slides.add_slide(blank_layout)

        for slot_idx, product in enumerate(group):
            slot_offset_x = 0.0
            if slots > 1:
                slot_offset_x = slot_idx * (fmt_info["width_cm"] / slots)

            visibility    = evaluate_rules(rules, product)
            visible_comps = apply_visibility(laid_out, visibility)

            _render_slide(slide, visible_comps, product, slot_offset_x)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def generate_from_template_v2(
    template_def: dict,
    excel_bytes: bytes,
    target_format: str = "a4",
    vigencia: str = "",
    aclaracion: str = "",
    otra_alcohol: str = "Prohibida la venta de bebidas alcohólicas a menores de 18 años",
    banco: str = "",
) -> bytes:
    """Parsea Excel y genera PPTX desde template v2."""
    products = load_products_from_bytes(
        excel_bytes, vigencia, aclaracion, otra_alcohol, banco
    )
    return render_template_to_pptx(template_def, products, target_format)
