"""Importador PPTX → definición v2 de componentes."""
import re
import uuid
from io import BytesIO

from pptx import Presentation
from pptx.enum.text import PP_ALIGN

_EMU_PER_CM = 360_000

# Regex: <<PLACEHOLDER>> con número de slot opcional
_RE_PLACEHOLDER = re.compile(r"<<(\w+?)(\d*)>>", re.IGNORECASE)

# Mapping placeholder root (lowercase) → (var_name, var_type, transform)
_PLACEHOLDER_MAP: dict[str, tuple[str, str, str]] = {
    "p":               ("precio",          "price", "price_full"),
    "precio":          ("precio",          "price", "price_full"),
    "descripcion":     ("descripcion",     "text",  "smart_bold"),
    "descripci":       ("descripcion",     "text",  "smart_bold"),
    "mecanica":        ("tipo_promocion",  "text",  "none"),
    "unidadmedida":    ("unidad",          "text",  "none"),
    "vigencia":        ("vigencia",        "text",  "none"),
    "aclaracion":      ("aclaracion",      "text",  "none"),
    "otraaclaracion":  ("otra_aclaracion", "text",  "none"),
    "code":            ("codigo",          "text",  "none"),
    "pbanco":          ("precio_banco",    "price", "price_full"),
    "banco":           ("banco",           "text",  "none"),
    "unidadprecio":    ("unidad_precio",   "text",  "none"),
    "unidadpbanco":    ("unidad_pbanco",   "text",  "none"),
}

_CSV_COLUMN_MAP: dict[str, str] = {
    "precio":          "PRECIO",
    "descripcion":     "DESCRIPCION",
    "tipo_promocion":  "OFERTADET",
    "unidad":          "UNIDAD",
    "vigencia":        "VIGENCIA",
    "aclaracion":      "ACLARACION",
    "otra_aclaracion": "ACLARACION",
    "codigo":          "CODIGO",
    "precio_banco":    "PRECIO_BANCO",
    "banco":           "BANCO",
    "unidad_precio":   "UNIDAD",
    "unidad_pbanco":   "UNIDAD",
}

_REQUIRED_VARS = {"descripcion", "precio"}

_FORMATS_DIM = {
    "a4":      (21.0,  29.7, 1),
    "a3":      (29.7,  42.0, 1),
    "3xa4":    (63.0,  29.7, 3),
    "pinchos": (10.5,  29.7, 1),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _emu_to_cm(emu: int) -> float:
    return round(emu / _EMU_PER_CM, 3)


def _detect_format(width_cm: float, height_cm: float) -> tuple[str, int]:
    """Devuelve (format_id, slots) para las dimensiones dadas."""
    best = "a4"
    best_dist = float("inf")
    for fmt_id, (w, h, _slots) in _FORMATS_DIM.items():
        dist = abs(width_cm - w) + abs(height_cm - h)
        if dist < best_dist:
            best_dist = dist
            best = fmt_id
    _, _, slots = _FORMATS_DIM[best]
    return best, slots


def _extract_fill_color(shape) -> str | None:
    try:
        fill = shape.fill
        if fill.type is None:
            return None
        rgb = fill.fore_color.rgb
        return f"#{rgb.red:02X}{rgb.green:02X}{rgb.blue:02X}"
    except Exception:
        return None


def _extract_font_color(run) -> str | None:
    try:
        rgb = run.font.color.rgb
        return f"#{rgb.red:02X}{rgb.green:02X}{rgb.blue:02X}"
    except Exception:
        return None


def _get_shape_text(shape) -> str:
    if not shape.has_text_frame:
        return ""
    return "".join(r.text for p in shape.text_frame.paragraphs for r in p.runs)


def _detect_placeholder(text: str) -> tuple[str, str, str] | None:
    """Devuelve (var_name, var_type, transform) o None si no hay placeholder."""
    m = _RE_PLACEHOLDER.search(text)
    if not m:
        return None
    root = m.group(1).lower()

    if root in _PLACEHOLDER_MAP:
        return _PLACEHOLDER_MAP[root]

    # Coincidencia parcial por prefijo
    for key, value in _PLACEHOLDER_MAP.items():
        if root.startswith(key) or key.startswith(root):
            return value

    # Fallback: usar el nombre tal cual
    return (root, "text", "none")


def _extract_style(shape) -> dict:
    style: dict = {}
    if not shape.has_text_frame:
        return style

    tf = shape.text_frame

    for para in tf.paragraphs:
        if para.alignment is not None:
            _align = {PP_ALIGN.LEFT: "left", PP_ALIGN.CENTER: "center", PP_ALIGN.RIGHT: "right"}
            style["align"] = _align.get(para.alignment, "center")
            break

    first_run = None
    for para in tf.paragraphs:
        for run in para.runs:
            if run.text.strip():
                first_run = run
                break
        if first_run:
            break

    if first_run:
        font = first_run.font
        try:
            if font.size:
                style["font_size"] = round(font.size.pt, 1)
        except Exception:
            pass
        try:
            if font.bold is not None:
                style["font_bold"] = bool(font.bold)
        except Exception:
            pass
        try:
            if font.name:
                style["font_family"] = font.name
        except Exception:
            pass
        color = _extract_font_color(first_run)
        if color:
            style["color"] = color

    style.setdefault("align", "center")
    style["auto_fit"] = True
    return style


def _flatten_shapes(shapes) -> list:
    result = []
    for shape in shapes:
        if hasattr(shape, "shapes"):
            result.extend(_flatten_shapes(shape.shapes))
        else:
            result.append(shape)
    return result


# ---------------------------------------------------------------------------
# Parseo de shapes individuales
# ---------------------------------------------------------------------------

def _parse_shape(shape, z_index: int) -> dict | None:
    try:
        left   = _emu_to_cm(shape.left   or 0)
        top    = _emu_to_cm(shape.top    or 0)
        width  = _emu_to_cm(shape.width  or 0)
        height = _emu_to_cm(shape.height or 0)
    except Exception:
        return None

    if width < 0.1 or height < 0.1:
        return None

    base = {"x": left, "y": top, "width": width, "height": height}
    common = {
        "id":             str(uuid.uuid4()),
        "base_bounds":    base,
        "format_overrides": {},
        "z_index":        z_index,
        "locked":         False,
        "visible":        True,
    }

    # Imagen
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            return {**common, "type": "image", "name": f"imagen_{z_index}",
                    "variable": "imagen", "style": {}, "_var_type": "image_url"}
    except Exception:
        pass

    # Shape con texto
    if shape.has_text_frame:
        text = _get_shape_text(shape).strip()
        style = _extract_style(shape)
        ph = _detect_placeholder(text)
        if ph:
            var_name, var_type, transform = ph
            return {**common, "type": "text", "name": var_name,
                    "variable": var_name, "transform": transform,
                    "style": style, "_var_type": var_type}
        # Texto estático (etiquetas, aclaraciones fijas, etc.)
        label = text[:30] if text else f"texto_{z_index}"
        return {**common, "type": "text", "name": label,
                "variable": None, "transform": "none",
                "style": style, "_var_type": "text"}

    # Shape sin texto → fondo/decorativo
    style = {}
    bg = _extract_fill_color(shape)
    if bg:
        style["background_color"] = bg
    return {**common, "type": "shape", "name": f"fondo_{z_index}", "style": style}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def import_pptx(pptx_bytes: bytes, name: str = "Template importado") -> dict:
    """Parsea el primer slide de un PPTX y devuelve una definición v2."""
    prs = Presentation(BytesIO(pptx_bytes))
    if not prs.slides:
        raise ValueError("El archivo PPTX no tiene slides")

    slide = prs.slides[0]
    width_cm  = _emu_to_cm(prs.slide_width)
    height_cm = _emu_to_cm(prs.slide_height)

    format_id, slots = _detect_format(width_cm, height_cm)
    slot_width = width_cm / slots  # 21cm para 3xa4, igual al total para 1-slot

    all_shapes = _flatten_shapes(slide.shapes)

    components: list[dict]     = []
    variables_seen: dict[str, dict] = {}
    z_index = 0

    for shape in all_shapes:
        comp = _parse_shape(shape, z_index)
        if comp is None:
            continue

        # Para formatos multi-slot: conservar solo las shapes del primer slot
        if slots > 1 and comp["base_bounds"]["x"] >= slot_width:
            continue

        components.append(comp)
        z_index += 1

        var_name = comp.get("variable")
        if var_name and var_name not in variables_seen:
            variables_seen[var_name] = {
                "type":       comp.pop("_var_type", "text"),
                "csv_column": _CSV_COLUMN_MAP.get(var_name, var_name.upper()),
            }
        else:
            comp.pop("_var_type", None)

    variables = [
        {
            "name":       vname,
            "type":       vinfo["type"],
            "required":   vname in _REQUIRED_VARS,
            "csv_column": vinfo["csv_column"],
        }
        for vname, vinfo in variables_seen.items()
    ]

    return {
        "version":       "2.0",
        "name":          name,
        "master_format": format_id,
        "formats":       [format_id],
        "variables":     variables,
        "components":    components,
        "rules":         [],
    }
