"""Importador PPTX → definición v2 de componentes."""
import base64
import re
import uuid
from io import BytesIO

from pptx import Presentation
from pptx.enum.text import PP_ALIGN

_EMU_PER_CM = 360_000

_RE_PLACEHOLDER = re.compile(r"<<(\w+?)(\d*)>>", re.IGNORECASE)

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
    "a4":      (21.0,  29.7,  1),
    "a3":      (29.7,  42.0,  1),
    "3xa4":    (21.0,  9.9,   3),   # slide de una franja; 3 en A4 portrait
    "pinchos": (7.0,   14.85, 6),   # slide de un pincho; grilla 3×2 en A4
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _emu_to_cm(emu: int) -> float:
    return round(emu / _EMU_PER_CM, 3)


def _detect_format(width_cm: float, height_cm: float) -> tuple[str, int]:
    best = "a4"
    best_dist = float("inf")
    for fmt_id, (w, h, _slots) in _FORMATS_DIM.items():
        dist = abs(width_cm - w) + abs(height_cm - h)
        if dist < best_dist:
            best_dist = dist
            best = fmt_id
    _, _, slots = _FORMATS_DIM[best]
    return best, slots


_MAX_IMAGE_BYTES = 300_000  # ~300 KB antes de comprimir

# Formatos que los navegadores entienden nativamente
_WEB_EXTS = {"jpeg", "jpg", "png", "gif", "webp"}


def _extract_image_b64(shape) -> tuple[str, str] | None:
    """Extrae la imagen de un shape Picture como base64 web-compatible.
    WMF/EMF/BMP/TIFF se convierten a PNG/JPEG con Pillow.
    Devuelve (base64_str, ext) o None."""
    try:
        img_obj = shape.image
        raw = img_obj.blob
        ext = img_obj.ext.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"

        if ext not in _WEB_EXTS:
            # Intentar convertir a PNG (funciona en Windows/GDI+)
            converted = _to_web_image(raw)
            if converted is not None:
                raw, ext = converted
            # Si PIL falla (Linux): guardar raw con ext original.
            # El renderer lo embebe en el PPTX directamente sin PIL.
        elif len(raw) > _MAX_IMAGE_BYTES:
            raw, ext = _compress_image(raw, ext)

        return base64.b64encode(raw).decode("utf-8"), ext
    except Exception:
        return None


def _to_web_image(raw: bytes) -> tuple[bytes, str] | None:
    """Intenta convertir WMF/EMF/BMP/TIFF → PNG usando PIL.
    Funciona en Windows (GDI+). En Linux devuelve None → el renderer embebe raw."""
    try:
        from PIL import Image as PILImage
        import io as _io

        img = PILImage.open(_io.BytesIO(raw))

        # Verificar que PIL realmente pudo rasterizar (no solo abrir el header)
        img.load()

        max_dim = 800
        if max(img.width, img.height) > max_dim:
            ratio = max_dim / max(img.width, img.height)
            img = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                PILImage.LANCZOS,
            )

        has_alpha = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )
        buf = _io.BytesIO()
        img.convert("RGBA" if has_alpha else "RGB").save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "png"
    except Exception:
        return None


def _compress_image(raw: bytes, ext: str) -> tuple[bytes, str]:
    """Comprime una imagen web existente (JPEG/PNG). Preserva transparencia."""
    try:
        from PIL import Image as PILImage
        import io as _io

        img = PILImage.open(_io.BytesIO(raw))
        has_alpha = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )

        max_dim = 1500
        if max(img.width, img.height) > max_dim:
            ratio = max_dim / max(img.width, img.height)
            img = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                PILImage.LANCZOS,
            )

        buf = _io.BytesIO()
        if has_alpha:
            img.convert("RGBA").save(buf, format="PNG", optimize=True)
            return buf.getvalue(), "png"
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=85, optimize=True)
            return buf.getvalue(), "jpeg"
    except Exception:
        return raw, ext


def _extract_fill_color(shape) -> str | None:
    try:
        fill = shape.fill
        if fill.type is None:
            return None
        # Try python-pptx direct RGB (works for explicit fills)
        try:
            rgb = fill.fore_color.rgb
            return f"#{rgb.red:02X}{rgb.green:02X}{rgb.blue:02X}"
        except (TypeError, AttributeError):
            pass
        # Fallback: parse XML for srgbClr (explicit RGB embedded in XML)
        from lxml import etree
        from pptx.oxml.ns import qn
        solidFill = shape.element.find('.//' + qn('a:solidFill'))
        if solidFill is not None:
            srgbClr = solidFill.find(qn('a:srgbClr'))
            if srgbClr is not None:
                val = srgbClr.get('val', '')
                if val:
                    return f"#{val.upper()}"
            # Theme color: try to resolve from presentation theme XML
            schemeClr = solidFill.find(qn('a:schemeClr'))
            if schemeClr is not None:
                return _resolve_theme_color(shape, schemeClr)
        return None
    except Exception:
        return None


def _resolve_theme_color(shape, schemeClr) -> str | None:
    """Resolve a theme color reference (schemeClr) to an explicit hex RGB."""
    try:
        from pptx.oxml.ns import qn
        val = schemeClr.get('val', '')
        _COLOR_ELEM = {
            'dk1': 'a:dk1', 'lt1': 'a:lt1',
            'dk2': 'a:dk2', 'lt2': 'a:lt2',
            'accent1': 'a:accent1', 'accent2': 'a:accent2',
            'accent3': 'a:accent3', 'accent4': 'a:accent4',
            'accent5': 'a:accent5', 'accent6': 'a:accent6',
        }
        tag = _COLOR_ELEM.get(val)
        if not tag:
            return None
        # Walk up to find the theme part
        part = shape.part
        theme_part = None
        for rel in part.rels.values():
            if 'theme' in rel.reltype:
                theme_part = rel._target
                break
        if theme_part is None:
            # Try slide layout → slide master → theme
            try:
                layout = part.slide_layout
                for rel in layout.slide_master.part.rels.values():
                    if 'theme' in rel.reltype:
                        theme_part = rel._target
                        break
            except Exception:
                pass
        if theme_part is None:
            return None
        theme_el = theme_part._element
        ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
        # Path: a:theme/a:themeElements/a:clrScheme/a:accent1/a:srgbClr
        node = theme_el.find(f'.//a:clrScheme/{tag}/a:srgbClr', ns)
        if node is None:
            node = theme_el.find(f'.//a:clrScheme/{tag}/a:sysClr', ns)
        if node is not None:
            hex_val = node.get('val') or node.get('lastClr')
            if hex_val:
                # Apply luminance modifier if present
                lum_mod = schemeClr.find(qn('a:lumMod'))
                lum_off = schemeClr.find(qn('a:lumOff'))
                r = int(hex_val[0:2], 16)
                g = int(hex_val[2:4], 16)
                b = int(hex_val[4:6], 16)
                if lum_mod is not None:
                    factor = int(lum_mod.get('val', '100000')) / 100000
                    r = int(r * factor); g = int(g * factor); b = int(b * factor)
                if lum_off is not None:
                    offset = int(lum_off.get('val', '0')) / 100000 * 255
                    r = int(min(255, r + offset))
                    g = int(min(255, g + offset))
                    b = int(min(255, b + offset))
                return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        pass
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
    m = _RE_PLACEHOLDER.search(text)
    if not m:
        return None
    root = m.group(1).lower()
    if root in _PLACEHOLDER_MAP:
        return _PLACEHOLDER_MAP[root]
    for key, value in _PLACEHOLDER_MAP.items():
        if root.startswith(key) or key.startswith(root):
            return value
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


def _make_common(shape, z_index: int) -> dict | None:
    try:
        left   = _emu_to_cm(shape.left   or 0)
        top    = _emu_to_cm(shape.top    or 0)
        width  = _emu_to_cm(shape.width  or 0)
        height = _emu_to_cm(shape.height or 0)
    except Exception:
        return None
    if width < 0.1 or height < 0.1:
        return None
    return {
        "id":               str(uuid.uuid4()),
        "base_bounds":      {"x": left, "y": top, "width": width, "height": height},
        "format_overrides": {},
        "z_index":          z_index,
        "locked":           False,
        "visible":          True,
    }


# ---------------------------------------------------------------------------
# Parseo de shapes individuales
# ---------------------------------------------------------------------------

def _parse_shape(shape, z_index: int) -> dict | None:
    common = _make_common(shape, z_index)
    if common is None:
        return None

    # Imagen embebida (foto, cocarde, logo)
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            comp = {**common, "type": "image", "name": f"imagen_{z_index}",
                    "variable": None, "style": {}, "_var_type": "image_url"}
            result = _extract_image_b64(shape)
            if result:
                comp["image_data"], comp["image_ext"] = result
            return comp
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
        if not text:
            return None
        label = text[:30]
        return {**common, "type": "text", "name": label,
                "variable": None, "static_value": text,
                "transform": "none", "style": style, "_var_type": "text"}

    # Shape sin texto → fondo/decorativo con color
    style = {}
    bg = _extract_fill_color(shape)
    if bg:
        style["background_color"] = bg
    return {**common, "type": "shape", "name": f"fondo_{z_index}", "style": style}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _detect_vertical_slots(all_comps: list[dict], page_height: float) -> str | None:
    """Detecta si un slide A4 tiene múltiples franjas verticales (mismo layout repetido).

    Compara la distribución Y de los componentes variable:
    - Si hay componentes en los 3 tercios de la página → '3xa4' (3 franjas de 9.9cm)
    - Retorna None si no se detecta patrón multi-franja.
    """
    # Solo considerar shapes con variable (los que tienen datos reales)
    y_centers = []
    for c in all_comps:
        if not c.get("variable"):
            continue
        bb = c["base_bounds"]
        y_centers.append(bb["y"] + bb["height"] / 2)

    if not y_centers:
        return None

    band_h = page_height / 3
    in_band2 = any(band_h <= y < 2 * band_h for y in y_centers)
    in_band3 = any(2 * band_h <= y for y in y_centers)
    if in_band2 and in_band3:
        return "3xa4"
    return None


def import_pptx(pptx_bytes: bytes, name: str = "Template importado") -> dict:
    """Parsea el primer slide de un PPTX y devuelve una definición v2."""
    prs = Presentation(BytesIO(pptx_bytes))
    if not prs.slides:
        raise ValueError("El archivo PPTX no tiene slides")

    slide = prs.slides[0]
    width_cm  = _emu_to_cm(prs.slide_width)
    height_cm = _emu_to_cm(prs.slide_height)
    format_id, _slots = _detect_format(width_cm, height_cm)

    components: list[dict]          = []
    variables_seen: dict[str, dict] = {}
    z_index = 0

    # ── 1. Imágenes del slide master (fondo visual del template) ──────────
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        master = slide.slide_layout.slide_master
        for shape in master.shapes:
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            common = _make_common(shape, z_index)
            if common is None:
                continue
            result = _extract_image_b64(shape)
            if not result:
                continue
            b64, ext = result
            components.append({
                **common,
                "type":       "image",
                "name":       "fondo",
                "variable":   None,
                "image_data": b64,
                "image_ext":  ext,
                "style":      {},
                "locked":     True,
            })
            z_index += 1
    except Exception:
        pass

    # ── 2. Shapes del slide — importar TODOS primero ──────────────────────
    all_raw: list[dict] = []
    for shape in _flatten_shapes(slide.shapes):
        comp = _parse_shape(shape, z_index)
        if comp is None:
            continue
        all_raw.append(comp)
        z_index += 1

    # ── 3. Detectar layout vertical multi-franja en slides A4 ─────────────
    # Un PPTX de "Plato del día 3 franjas" es A4 completo (21×29.7) con 3 filas
    # repetidas de ~9.9cm. El renderer espera UN slot por formato; hay que importar
    # solo la primera franja y usar master_format='3xa4'.
    if format_id == "a4":
        detected = _detect_vertical_slots(all_raw, height_cm)
        if detected:
            format_id = detected

    # ── 4. Filtrar al primer slot según formato ───────────────────────────
    slot_w, slot_h, _n = _FORMATS_DIM[format_id]

    def _in_first_slot(comp: dict) -> bool:
        bb = comp["base_bounds"]
        if format_id == "3xa4":
            # Vertical: primera franja Y < slot_h (con margen de 1cm)
            return bb["y"] < slot_h + 1.0
        elif format_id == "pinchos":
            # Horizontal: primera columna X < slot_w
            return bb["x"] < slot_w
        return True

    for comp in all_raw:
        if not _in_first_slot(comp):
            continue

        components.append(comp)
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
