"""Renderer de componentes v2 — genera PPTX desde definición JSON de componentes."""
import copy
import io
import re

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml import parse_xml
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
    "3xa4":    (Cm(21.0),  Cm(29.7)),   # A4 portrait completo, 3 franjas verticales
    "pinchos": (Cm(21.0),  Cm(29.7)),   # A4 portrait completo, grilla 3×2
    "a5":      (Cm(14.85), Cm(21.0)),
    "6xa4":    (Cm(21.0),  Cm(29.7)),   # A4 portrait completo, grilla 3×2 (arte propio)
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


# NOTA (08/2026): acá vivía también el achique automático de la fuente del
# PRECIO (_fit_price_font_size) y el corrimiento vertical del cuadro de precio
# cuando la descripción se desbordaba. Esos dos siguen eliminados: el motor no
# agranda, no achica precios y no mueve ninguna caja de donde la puso el
# diseño. El achique de la DESCRIPCIÓN sí volvió, a pedido explícito -- ver
# abajo.

# ---------------------------------------------------------------------------
# Achique automático de la descripción
# ---------------------------------------------------------------------------
#
# Única excepción a la regla de "el motor respeta el PPTX tal cual": cuando el
# nombre del producto no entra en su cuadro, se achica la fuente. Se restauró
# a pedido explícito (08/2026) después de haberla sacado, porque los nombres
# reales de gestión pasan seguido de los 60 caracteres y desbordan sobre el
# precio de al lado.
#
# Lo que NO volvió: el corrimiento del cuadro de precio hacia abajo. Acá solo
# se achica texto; ninguna caja se mueve de donde la puso el diseño.


def _estimate_wrapped_lines(
    text: str, box_width_cm: float | None, font_size: float | None, bold: bool = False,
) -> int:
    """Estima a cuántas líneas se parte un texto con word-wrap en una caja de
    cierto ancho, simulando el mismo criterio "voraz" (agregar palabras hasta
    que no entran más) que usa PowerPoint.

    No es exacto -- no hay métricas reales de la fuente en el servidor -- pero
    está calibrado contra descripciones reales que se superponían con el
    precio. Antes de tocar las constantes, mirar el historial de este archivo:
    ya se recalibraron dos veces contra casos concretos.

    bold=True ensancha el ancho de caracter asumido: las fuentes de titular de
    estas plantillas son bold y ocupan bastante más por caracter.
    """
    if not text or not box_width_cm or not font_size:
        return 1
    # Inset interno de PowerPoint (izquierdo + derecho) que hay que descontar
    # del ancho disponible; sin esto se sobreestima cuánto entra por línea.
    usable_width_cm = max(0.1, box_width_cm - 0.4)
    box_width_pt = usable_width_cm / 2.54 * 72
    # Ancho promedio de caracter, calibrado contra casos reales -- no es un
    # valor "de catálogo" de ninguna fuente.
    char_width_em = 0.52 if bold else 0.38
    chars_per_line = max(1, int(box_width_pt / (font_size * char_width_em)))
    lines = 1
    current_len = 0
    for word in text.split():
        add_len = len(word) if current_len == 0 else current_len + 1 + len(word)
        if add_len > chars_per_line and current_len > 0:
            lines += 1
            current_len = len(word)
        else:
            current_len = add_len
    return lines


def _comp_uses_variable(c: dict, var_name: str) -> bool:
    """True si el componente usa esa variable, sea directo o en un segmento.

    El caso de segmento importa: "COD: <<codigo>>" o
    "PRECIO REGULAR: $ <<precioRegular>>" se importan como un componente con
    varios segmentos, no como una variable de nivel superior.
    """
    if c.get("variable") == var_name:
        return True
    return any(
        seg.get("type") == "variable" and seg.get("value") == var_name
        for seg in (c.get("segments") or [])
    )


# Piso de achique: por debajo de esto la descripción deja de ser legible en un
# cartel de góndola, y es preferible que se note el desborde a imprimir algo
# que nadie puede leer.
_DESC_FONT_FIT_MIN_SCALE = 0.6


def _fit_description_font_size(
    text: str, box_width_cm: float | None, box_height_cm: float | None,
    base_font_size: float | None, bold: bool = False,
) -> float | None:
    """Tamaño de fuente al que la descripción entra en su cuadro.

    Una sola pasada: no reestima cuántas líneas hacen falta AL tamaño ya
    achicado (un caracter más angosto entra más por línea, así que podría
    alcanzar con achicar menos). Es a propósito -- mismo nivel de precisión
    que el resto de las heurísticas de este archivo, y conservador para el
    lado seguro: prefiere achicar un poco de más antes que arriesgar que la
    descripción siga invadiendo lo que tiene al lado.
    """
    if not text or not box_width_cm or not box_height_cm or not base_font_size:
        return base_font_size
    lines = _estimate_wrapped_lines(text, box_width_cm, base_font_size, bold)
    if lines <= 1:
        return base_font_size
    line_height_cm = base_font_size / 72 * 2.54 * 1.2   # 1.2 = interlineado típico
    needed_height_cm = lines * line_height_cm
    if needed_height_cm <= box_height_cm:
        return base_font_size
    scale = box_height_cm / needed_height_cm
    return max(base_font_size * scale, base_font_size * _DESC_FONT_FIT_MIN_SCALE)


def _fit_description_to_box(comps: list[dict], product: dict) -> list[dict]:
    """Achica la fuente de la descripción cuando el nombre no entra en su caja.

    Aplica a todos los mundos: descripcion y precio suelen ser dos cuadros de
    texto independientes apilados, sin auto-layout compartido, así que uno
    desborda sobre el otro si no se achica.
    """
    desc_comp = next((c for c in comps if _comp_uses_variable(c, "descripcion")), None)
    if not desc_comp:
        return comps

    style = desc_comp.get("style", {})
    base_font_size = style.get("font_size")
    bold = bool(style.get("font_bold"))
    # computed_bounds ya tiene el tamaño con el que se va a dibujar; base_bounds
    # es el del diseño. Se prefiere el primero y se cae al segundo.
    bounds = desc_comp.get("computed_bounds") or desc_comp.get("base_bounds") or {}
    box_width, box_height = bounds.get("width"), bounds.get("height")
    text = str(product.get("descripcion", "") or "")

    fitted = _fit_description_font_size(text, box_width, box_height, base_font_size, bold)
    if fitted == base_font_size:
        return comps

    result = []
    for c in comps:
        if c is desc_comp:
            c = {**c, "style": {**c["style"], "font_size": fitted}}
            # En un componente multi-segmento cada segmento lleva su propio
            # font_size, que pisa al del componente en _populate_text_frame.
            # Sin esto el achique se descartaba en silencio para cualquier
            # cuadro importado como multi-segmento (que ahora son casi todos).
            segs = c.get("segments")
            if segs:
                c["segments"] = [
                    {**seg, "style": {**seg["style"], "font_size": fitted}}
                    if seg.get("style", {}).get("font_size") else seg
                    for seg in segs
                ]
        result.append(c)
    return result



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


def _populate_text_frame(tf, comp: dict, value: str) -> None:
    """Arma el contenido de un text_frame ya existente — separado de
    add_text_component para poder reusarlo tanto al crear una caja de texto
    nueva como al reescribir el texto de un shape original preservado
    (ver _place_component)."""
    style    = comp.get("style", {})
    segments = comp.get("segments")

    tf.word_wrap = True

    # Vertical anchor (preserved from original PPTX)
    vertical_align = style.get("vertical_align")
    if vertical_align:
        try:
            body_pr = tf._txBody.find(qn("a:bodyPr"))
            if body_pr is not None:
                body_pr.set("anchor", vertical_align)
        except Exception:
            pass

    if style.get("auto_fit", False):
        _enable_normAutofit(tf)

    tf.clear()  # saca cualquier texto previo (ej. "<<Descripción>>" del original)
    transform = comp.get("transform", "none")
    p = tf.paragraphs[0]
    p.alignment = ALIGN_MAP.get(style.get("align", "center"), PP_ALIGN.CENTER)

    if segments:
        # Multi-segment: each segment gets its own run with per-segment style overrides.
        # Variable segments have their value pre-resolved as "_resolved" by _render_slide.
        for seg in segments:
            seg_val = seg.get("_resolved", seg.get("value", ""))
            if not seg_val:
                continue
            seg_style = {**style}
            if seg.get("style"):
                seg_style.update(seg["style"])
            seg_transform = seg.get("transform") or "none"
            if seg_transform == "smart_bold":
                for part, is_bold in split_caps(seg_val):
                    if part:
                        run = p.add_run()
                        run.text = part
                        _apply_run_style(run, seg_style, bold_override=is_bold)
            else:
                if seg_transform not in (None, "none"):
                    seg_val = apply_transform(seg_val, seg_transform)
                run = p.add_run()
                run.text = seg_val
                _apply_run_style(run, seg_style)
    elif transform == "smart_bold":
        for segment, is_bold in split_caps(value):
            if not segment:
                continue
            run = p.add_run()
            run.text = segment
            _apply_run_style(run, style, bold_override=is_bold)
    else:
        run_style = style
        run = p.add_run()
        run.text = value
        _apply_run_style(run, run_style)

    # Replicate empty spacer run used in original PPTX to set a larger line height.
    # Without this, anchor=b positions text much lower than the original.
    line_height_pt = style.get("line_height_pt")
    if line_height_pt and line_height_pt != style.get("font_size"):
        spacer = p.add_run()
        spacer.text = ""
        spacer.font.size = Pt(line_height_pt)


def add_text_component(slide, comp: dict, value: str) -> None:
    bounds = comp["computed_bounds"]
    txBox = slide.shapes.add_textbox(
        Cm(bounds["x"]), Cm(bounds["y"]),
        Cm(max(bounds["width"],  0.5)),
        Cm(max(bounds["height"], 0.3)),
    )
    _populate_text_frame(txBox.text_frame, comp, value)


def _apply_run_style(run, style: dict, bold_override: bool | None = None) -> None:
    font = run.font
    if style.get("font_size"):
        font.size = Pt(style["font_size"])
    font.bold = bold_override if bold_override is not None else style.get("font_bold", False)
    if style.get("color"):
        font.color.rgb = hex_to_rgb(style["color"])
    if style.get("font_family"):
        font.name = style["font_family"]
    # python-pptx no expone tachado en Font — hay que bajar al XML crudo.
    if style.get("strikethrough"):
        run._r.get_or_add_rPr().set("strike", "sngStrike")


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


_WMF_EXTS = {"wmf", "emf"}

def add_image_from_data(slide, comp: dict) -> None:
    """Embebe una imagen base64 en el slide.
    Formatos web (JPEG/PNG): usa add_picture normal.
    Formatos vectoriales (WMF/EMF): embebe via XML directo, sin PIL."""
    import base64 as _b64
    bounds   = comp["computed_bounds"]
    img_ext  = (comp.get("image_ext") or "").lower()

    try:
        img_bytes = _b64.b64decode(comp["image_data"])
    except Exception:
        add_image_placeholder(slide, comp, comp.get("name", "imagen"))
        return

    if img_ext in _WMF_EXTS:
        try:
            _embed_vector_image(slide, img_bytes, img_ext, bounds)
        except Exception:
            # Only show placeholder for variable images (product images).
            # Decorative static images (no variable) are silently skipped.
            if comp.get("variable"):
                add_image_placeholder(slide, comp, comp.get("name", "imagen"))
    else:
        try:
            slide.shapes.add_picture(
                io.BytesIO(img_bytes),
                Cm(bounds["x"]),
                Cm(bounds["y"]),
                Cm(max(bounds["width"],  0.1)),
                Cm(max(bounds["height"], 0.1)),
            )
        except Exception:
            add_image_placeholder(slide, comp, comp.get("name", "imagen"))


def _embed_vector_image(slide, img_bytes: bytes, ext: str, bounds: dict) -> None:
    """Embebe WMF/EMF directamente en el XML del slide sin pasar por PIL."""
    import hashlib
    from pptx.opc.part import Part
    from pptx.opc.packuri import PackURI

    content_types = {"wmf": "image/x-wmf", "emf": "image/x-emf"}
    ct  = content_types.get(ext, "image/x-wmf")
    h   = hashlib.md5(img_bytes).hexdigest()[:12]
    uri = PackURI(f"/ppt/media/img_{h}.{ext}")

    img_part = Part(uri, ct, img_bytes)
    rId = slide.part.relate_to(
        img_part,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )

    x  = int(Cm(bounds["x"]))
    y  = int(Cm(bounds["y"]))
    cx = int(Cm(max(bounds["width"],  0.1)))
    cy = int(Cm(max(bounds["height"], 0.1)))
    pid = abs(hash(h)) % 8000 + 1000

    pic_xml = (
        f'<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        f' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        f' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<p:nvPicPr>'
        f'<p:cNvPr id="{pid}" name="img_{h[:8]}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        f'<p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rId}"/>'
        f'<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'</p:pic>'
    )
    slide.shapes._spTree.append(parse_xml(pic_xml.encode()))


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
# Preservación del diseño original — reusar/mutar shapes reales del PPTX
# fuente en vez de reconstruir todo sobre una presentación en blanco.
# ---------------------------------------------------------------------------

def _shape_id_map(shapes) -> dict[int, object]:
    """Mapa shape_id -> shape, recorriendo grupos recursivamente (mismo
    criterio que _flatten_shapes en pptx_importer, para que el id capturado
    al importar siga siendo encontrable acá)."""
    result: dict[int, object] = {}
    for shape in shapes:
        if hasattr(shape, "shapes"):
            result.update(_shape_id_map(shape.shapes))
        else:
            try:
                result[shape.shape_id] = shape
            except Exception:
                pass
    return result


def _duplicate_slide(prs, source_slide):
    """Clona un slide completo (layout, shapes, relaciones de imagen y fondo
    propio si tiene) — python-pptx no trae esto de fábrica. Hace falta para
    generar N páginas iguales al diseño original cuando hay más de un grupo
    de productos por generar (ver render_template_to_pptx)."""
    new_slide = prs.slides.add_slide(source_slide.slide_layout)

    # add_slide ya pudo haber agregado placeholders heredados del layout —
    # los sacamos, vamos a clonar los shapes reales del slide fuente.
    for shape in list(new_slide.shapes):
        shape._element.getparent().remove(shape._element)

    # Fondo propio del slide (si el original no lo hereda del layout/master)
    src_bg = source_slide._element.find(qn("p:cSld")).find(qn("p:bg"))
    if src_bg is not None:
        new_cSld = new_slide._element.find(qn("p:cSld"))
        new_cSld.insert(0, copy.deepcopy(src_bg))

    # Relaciones de imagen — para que los r:embed de los shapes clonados
    # sigan resolviendo a la parte correcta en el slide nuevo.
    id_map: dict[str, str] = {}
    for rel_id, rel in source_slide.part.rels.items():
        if rel.is_external or "image" not in rel.reltype:
            continue
        id_map[rel_id] = new_slide.part.relate_to(rel.target_part, rel.reltype)

    for shape in source_slide.shapes:
        new_el = copy.deepcopy(shape._element)
        if id_map:
            for blip in new_el.iter(qn("a:blip")):
                old_rid = blip.get(qn("r:embed"))
                if old_rid and old_rid in id_map:
                    blip.set(qn("r:embed"), id_map[old_rid])
        new_slide.shapes._spTree.append(new_el)

    return new_slide


def _place_component(slide, comp: dict, value: str, shape_map: dict[int, object]) -> None:
    """Coloca un componente en el slide. Si viene de una plantilla con
    diseño original preservado y matchea un shape real del archivo fuente
    (_source_shape_id), lo muta en el lugar — reposiciona y reescribe su
    contenido — en vez de crear uno nuevo, así el resto del diseño del
    archivo (fondos, logos, bordes que el importer no haya capturado como
    componente) queda intacto. Sin match, cae al comportamiento de siempre."""
    comp_type = comp.get("type", "text")
    source_id = comp.get("_source_shape_id")
    shape = shape_map.get(source_id) if source_id is not None else None

    if shape is not None:
        bounds = comp["computed_bounds"]
        try:
            shape.left   = Cm(bounds["x"])
            shape.top    = Cm(bounds["y"])
            shape.width  = Cm(max(bounds["width"],  0.1))
            shape.height = Cm(max(bounds["height"], 0.1))
        except Exception:
            pass

        if comp_type == "text" and shape.has_text_frame:
            _populate_text_frame(shape.text_frame, comp, value)
            return
        if comp_type == "shape":
            style = comp.get("style", {})
            if style.get("background_color"):
                try:
                    shape.fill.solid()
                    shape.fill.fore_color.rgb = hex_to_rgb(style["background_color"])
                except Exception:
                    pass
            return
        if comp_type == "image":
            if comp.get("image_data"):
                # Más simple/confiable reemplazar el shape entero que mutar
                # el blob de una <p:pic> ya existente.
                shape._element.getparent().remove(shape._element)
                add_image_from_data(slide, comp)
            return
        return

    # Sin shape original que matchee (template armado en el editor, o
    # componente agregado a mano después de importar) -> comportamiento
    # de siempre: crear el shape desde cero.
    if comp_type == "text":
        add_text_component(slide, comp, value)
    elif comp_type == "shape":
        add_shape_component(slide, comp)
    elif comp_type == "image":
        if comp.get("image_data"):
            add_image_from_data(slide, comp)
        else:
            add_image_placeholder(slide, comp, comp.get("variable") or "imagen")


# ---------------------------------------------------------------------------
# Render de un slide completo
# ---------------------------------------------------------------------------

def _render_slide(
    slide,
    comp_layout: list[dict],
    product: dict,
    slot_offset_x: float = 0.0,
    slot_offset_y: float = 0.0,
    missing_vars: set | None = None,
    shape_map: dict[int, object] | None = None,
) -> None:
    shape_map = shape_map or {}
    for comp in comp_layout:
        comp_type = comp.get("type", "text")
        source_id = comp.get("_source_shape_id")

        if not comp.get("visible", True):
            # Componente oculto por una regla: si matchea un shape original
            # preservado, limpiarle el texto (si no, quedaría el placeholder
            # del archivo fuente, ej. "<<Descripción>>", visible por error).
            shape = shape_map.get(source_id) if source_id is not None else None
            if shape is not None and comp_type == "text" and shape.has_text_frame:
                shape.text_frame.clear()
            continue

        segments = comp.get("segments") if comp_type == "text" else None

        if segments:
            # Resolve variable segments from product data, store as "_resolved"
            resolved = []
            for i, seg in enumerate(segments):
                if seg.get("type") == "variable":
                    seg_var = seg.get("value", "")
                    seg_val = str(product.get(seg_var, "") or "") if seg_var else ""
                    if seg_var and seg_var not in product and missing_vars is not None:
                        missing_vars.add(seg_var)
                    # Guarda contra el símbolo de moneda duplicado. Desde
                    # 08/2026 los precios viajan SIN "$" (el símbolo es texto
                    # fijo del diseño), así que esto normalmente no se
                    # dispara; sigue acá para el caso de un Excel cargado a
                    # mano con "$899" en una plantilla que además tiene el
                    # "$" como run propio -- sin el chequeo queda "$$899".
                    # Solo saca un símbolo repetido, nunca reformatea nada.
                    if i > 0 and segments[i - 1].get("type") == "static":
                        prev = segments[i - 1].get("value", "").strip()
                        if prev in ("U$S", "$") and seg_val.strip().startswith(prev):
                            seg_val = seg_val.strip()[len(prev):].lstrip()
                else:
                    seg_val = seg.get("value", "")
                resolved.append({**seg, "_resolved": seg_val})
            comp  = {**comp, "segments": resolved}
            value = ""  # unused when segments present
        else:
            variable     = comp.get("variable")
            static_value = comp.get("static_value", "")
            raw_value    = str(product.get(variable, "") or "") if variable else static_value
            transform    = comp.get("transform", "none")
            value        = apply_transform(raw_value, transform)

            # Collect variables that are used in the template but whose column is
            # entirely absent from the Excel (key not in product at all).
            # Empty cells produce key="" — that's valid data, not a missing column.
            if variable and variable not in product and missing_vars is not None:
                missing_vars.add(variable)

        # Offset 2D para layouts multi-slot (grilla horizontal × vertical)
        if slot_offset_x > 0 or slot_offset_y > 0:
            cb = comp["computed_bounds"].copy()
            cb["x"] = cb["x"] + slot_offset_x
            cb["y"] = cb["y"] + slot_offset_y
            comp = {**comp, "computed_bounds": cb}

        _place_component(slide, comp, value, shape_map)


# ---------------------------------------------------------------------------
# Multi-slot A4 detection
# ---------------------------------------------------------------------------

def _detect_slot_bands(components: list[dict]) -> list[list[dict]] | None:
    """Detect how many product slots are encoded in one slide of a template.

    n_slots = GCD de cuántas veces aparece cada variable -- NO el máximo.
    Un variable puede aparecer más de una vez POR banda (ej. un precio
    partido en placeholder de entero + placeholder de decimal, ambos
    apuntando a la misma variable canónica, ver ofertaUno/Dos/Tres en
    Parrilla y Vinos) sin que eso signifique que hay más bandas. Con max(),
    un template de 3 bandas donde cada precio tiene 2 placeholders (entero+
    decimal) se detectaba como 6 bandas -- de ahí se armaban grupos de Y mal
    alineados con las bandas reales, mezclando datos de dos productos
    distintos dentro de una misma banda visual (bug real, visto con
    <<4x3P>>/<<decimal4x3>> mostrando el precio de OTRO producto). El GCD es
    correcto mientras al menos una variable aparezca una sola vez por banda
    (ej. codigo/descripcion) -- caso normal en cualquier plantilla real.

    El conteo tiene que mirar tanto c["variable"] (componente de un solo
    placeholder) como c["segments"] (componente multi-segmento, ej. "$" +
    <<precioP>> como dos runs del mismo cuadro -- variable=None en ese caso,
    ver allow_single_placeholder_segments en pptx_importer.py). Un bug real
    visto con una plantilla real de Parrilla y Vinos: TODOS sus componentes
    -- incluso <<descripcion>> y <<codigo>> solos, sin texto estático al
    lado -- quedaron como multi-segmento (PowerPoint partió el placeholder
    en más de un run internamente al editar el archivo). Contando solo
    c["variable"] el Counter quedaba vacío, esta función devolvía None
    siempre, y el render trataba la página entera (3 franjas reales) como
    un solo producto -- de ahí que las 3 franjas terminaran mostrando
    siempre el mismo.
    Splits non-background components by Y order into that many groups.
    Returns None when n_slots == 1 (single-slot → standard per-product render).
    """
    import math
    from collections import Counter
    from functools import reduce

    def _comp_variable_names(c: dict) -> list[str]:
        if c.get("variable"):
            return [c["variable"]]
        return [seg["value"] for seg in (c.get("segments") or []) if seg.get("type") == "variable"]

    non_bg = [c for c in components if not c.get("locked")]
    var_counts: Counter = Counter()
    for c in non_bg:
        var_counts.update(_comp_variable_names(c))
    if not var_counts:
        return None

    n_slots = reduce(math.gcd, var_counts.values())
    if n_slots <= 1:
        return None  # single-slot template

    # Sort by Y, then split into n_slots consecutive groups
    sorted_comps = sorted(non_bg, key=lambda c: c.get("base_bounds", {}).get("y", 0))
    total      = len(sorted_comps)
    group_size = total // n_slots
    remainder  = total % n_slots

    bands: list[list[dict]] = []
    idx = 0
    for i in range(n_slots):
        size = group_size + (1 if i < remainder else 0)
        bands.append(sorted_comps[idx : idx + size])
        idx += size

    return bands


def patch_image_overrides(
    components: list[dict], image_overrides: dict[str, tuple[bytes, str]]
) -> list[dict]:
    """Inyecta imágenes subidas (ej. cocarda) en los componentes de imagen que
    referencien esa variable. Se usa tanto acá como en el paso de preview
    (jobs.py), para que la imagen ya esté horneada en el template_def antes
    de que el usuario llegue a reposicionar."""
    import base64 as _b64

    patched = []
    for c in components:
        var = c.get("variable")
        if c.get("type") == "image" and var and var in image_overrides:
            img_bytes, img_ext = image_overrides[var]
            patched.append({
                **c,
                "image_data": _b64.b64encode(img_bytes).decode(),
                "image_ext":  img_ext,
            })
        else:
            patched.append(c)
    return patched


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def render_template_to_pptx(
    template_def: dict,
    products: list[dict],
    target_format: str = "a4",
    image_overrides: dict[str, tuple[bytes, str]] | None = None,
    source_pptx_bytes: bytes | None = None,
) -> tuple[bytes, list[str]]:
    """Genera PPTX desde una definición v2 y una lista de productos.

    image_overrides: {variable_name: (image_bytes, ext)} — inyecta imágenes
    subidas en la página de generación como image_data de los componentes
    que usen esa variable.

    source_pptx_bytes: bytes del PPTX original del que se importó el
    template (si vino de un archivo subido, no armado a mano en el editor).
    Cuando está presente, el slide base se reusa/duplica desde ESE archivo
    en vez de reconstruirse desde una presentación en blanco — así se
    preserva el diseño (fondo, master, layout, cualquier shape que el
    importer no haya capturado como componente) tal cual estaba. Sin esto,
    el resultado solo tiene los shapes que SÍ se lograron extraer, y
    cualquier diseño que viva en el layout/master del archivo se pierde.

    Returns (pptx_bytes, missing_vars) donde missing_vars es la lista de
    variables que el template usa pero que no fueron encontradas en el Excel.
    """
    master_format = template_def.get("master_format", "a4")
    components    = template_def.get("components", [])
    rules         = template_def.get("rules", [])

    if image_overrides:
        components = patch_image_overrides(components, image_overrides)
    fmt_info      = get_format(target_format)
    slots         = fmt_info["slots"]

    missing_vars: set[str] = set()

    # ── Detect internal slots from variable repetition count ─────────────────
    # A template encodes N products per slide when its variables each appear N
    # times. Sort components by Y, split into N consecutive groups, and fill
    # each group with one product row — regardless of format or page size.
    slot_bands = _detect_slot_bands(components)

    # Preservar diseño original: solo cuando tenemos los bytes crudos Y el
    # layout no necesita tileo DENTRO de una misma página armado por el
    # motor (slot_bands ya trae sus N celdas pre-armadas en el archivo;
    # slots==1 es una celda por página, tampoco hace falta tilear). El caso
    # restante (una plantilla de una sola celda que el motor debe repetir
    # con offsets dentro de la página, ej. subir un solo pincho y pedirle al
    # sistema que arme la grilla de 6) sigue usando el canvas en blanco.
    preserve_source = source_pptx_bytes is not None and (slot_bands is not None or slots == 1)

    prs = None
    if preserve_source:
        try:
            prs = Presentation(io.BytesIO(source_pptx_bytes))
            if not prs.slides:
                prs = None
        except Exception:
            prs = None
        preserve_source = prs is not None

    if preserve_source:
        # El fondo extraído del MASTER (pptx_importer.py, name="fondo",
        # _source_shape_id=None a propósito) no tiene un shape real en el
        # slide para mutar — cualquier slide que comparta layout/master ya lo
        # hereda visualmente solo con add_slide(), sin dibujar nada de nuevo.
        # Si no se filtra acá, _place_component nunca encuentra shape para
        # mutar y cae al fallback de "crear uno nuevo" en CADA render — y
        # como _duplicate_slide() copia lo que el slide base tenga en ese
        # momento, cada producto siguiente arrastra una copia extra apilada
        # sobre la anterior (bug real, visto con productos duplicando el
        # diseño 2-3 veces encimados).
        components = [
            c for c in components
            if not (c.get("type") == "image" and c.get("variable") is None and c.get("_source_shape_id") is None)
        ]

    if not preserve_source:
        slide_w, slide_h = FORMAT_SLIDES.get(target_format, FORMAT_SLIDES["a4"])
        prs = Presentation()
        prs.slide_width  = slide_w
        prs.slide_height = slide_h

    blank_layout = prs.slide_layouts[6] if not preserve_source else None
    base_slide   = prs.slides[0] if preserve_source else None

    def _next_slide(is_first: bool):
        if preserve_source:
            return base_slide if is_first else _duplicate_slide(prs, base_slide)
        return prs.slides.add_slide(blank_layout)

    if slot_bands:
        bg_comps    = [c for c in components if c.get("locked")]
        n_slots     = len(slot_bands)
        page_groups = [products[i:i + n_slots] for i in range(0, len(products), n_slots)]

        for gi, pg in enumerate(page_groups):
            slide     = _next_slide(gi == 0)
            shape_map = _shape_id_map(slide.shapes) if preserve_source else {}
            if bg_comps:
                # Los componentes de un slot_bands ya vienen en coordenadas
                # absolutas (una página con N celdas pre-armadas) — nunca hay
                # que re-escalarlos contra target_format, solo posicionarlos
                # tal cual quedaron en master_format. Ver bug histórico: esto
                # antes escalaba por target_format y comprimía la grilla.
                laid_bg = compute_layout(bg_comps, master_format, master_format)
                _render_slide(slide, laid_bg, {}, missing_vars=missing_vars, shape_map=shape_map)
            for band_idx, band_comps in enumerate(slot_bands):
                laid_band = compute_layout(band_comps, master_format, master_format)
                if band_idx < len(pg):
                    product       = pg[band_idx]
                    visibility    = evaluate_rules(rules, product)
                    visible_comps = apply_visibility(laid_band, visibility)
                    visible_comps = _fit_description_to_box(visible_comps, product)
                    _render_slide(slide, visible_comps, product, missing_vars=missing_vars, shape_map=shape_map)
                elif preserve_source:
                    # Página parcial (menos productos que celdas) y estamos
                    # preservando el diseño original: si no se limpia, la
                    # celda sin producto queda con lo que tuviera el archivo
                    # fuente (ej. datos de ejemplo del diseñador).
                    _render_slide(slide, laid_band, {}, shape_map=shape_map)
                # Sin preserve_source: no hay nada que limpiar, la celda
                # simplemente nunca tuvo shapes creados (comportamiento
                # de siempre para el canvas en blanco).

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue(), sorted(missing_vars)

    # ── Single-slot template: one product per format-cell, tiled by offset ───
    # Used for 3xa4 / pinchos / any format where the slide IS the unit cell
    # and multiple cells are arranged spatially on the output page. Cuando
    # preserve_source es True acá slots siempre es 1 (gateado más arriba),
    # así que el offset por slot da siempre 0 — un producto, un slide, sin
    # tileo interno.
    laid_out  = compute_layout(components, target_format, master_format)
    slot_cols = fmt_info.get("slot_cols", 1)
    cell_w    = fmt_info["width_cm"]
    cell_h    = fmt_info["height_cm"]
    groups    = [products[i:i + slots] for i in range(0, len(products), slots)]

    for gi, group in enumerate(groups):
        slide     = _next_slide(gi == 0)
        shape_map = _shape_id_map(slide.shapes) if preserve_source else {}

        for slot_idx, product in enumerate(group):
            col = slot_idx % slot_cols
            row = slot_idx // slot_cols
            slot_offset_x = col * cell_w
            slot_offset_y = row * cell_h

            visibility    = evaluate_rules(rules, product)
            visible_comps = apply_visibility(laid_out, visibility)
            visible_comps = _fit_description_to_box(visible_comps, product)

            _render_slide(slide, visible_comps, product, slot_offset_x, slot_offset_y, missing_vars=missing_vars, shape_map=shape_map)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue(), sorted(missing_vars)


def generate_from_template_v2(
    template_def: dict,
    excel_bytes: bytes,
    target_format: str = "a4",
    vigencia: str = "",
    legales: str = "",
    usar_legales: bool = False,
    image_overrides: dict[str, tuple[bytes, str]] | None = None,
) -> tuple[bytes, list[str]]:
    """Parsea Excel y genera PPTX desde una definición de template.

    Camino directo sin jobs -- lo usa la generación sincrónica. El flujo
    normal de la plataforma pasa por jobs.py (preview + confirmación).
    """
    products = load_products_from_bytes(excel_bytes, vigencia, legales, usar_legales)
    return render_template_to_pptx(template_def, products, target_format, image_overrides)
