"""Motor de layout — calcula posiciones y tamaños de componentes por formato destino."""
import copy

from app.services.cenefas.formatos_de_hoja import FORMATOS as _FORMATOS

# ---------------------------------------------------------------------------
# Registro de formatos
# ---------------------------------------------------------------------------
#
# ACA NO HAY NINGUN NUMERO, Y ES A PROPOSITO. Hasta el 22/09/2026 esta tabla
# estaba escrita a mano, y habia otras cuatro iguales-pero-distintas
# (component_renderer.FORMAT_SLIDES, pptx_importer._FORMATS_DIM,
# Canvas.FORMAT_DIMS y las etiquetas del panel de importacion). Tres de los
# seis formatos tenian medidas DISTINTAS segun a cual se le preguntara, porque
# algunas decian el PAPEL y otras la CELDA y las dos cosas se llamaban igual.
# Ahora el tamano vive en app/data/formatos_de_hoja.json y solo se lee.
#
# `width_cm`/`height_cm` de esta tabla son la CELDA: lo que ocupa UNA cenefa.
# Es lo que compute_layout necesita para escalar un diseno de un formato a
# otro, y lo que /formats le muestra a la persona. El PAPEL que sale de la
# impresora se pide con formatos_de_hoja.papel_cm(), y el papel de una
# plantilla IMPORTADA con formatos_de_hoja.hoja_de_definicion(), que lee la
# medida exacta del PPTX original.

FORMATS: dict[str, dict] = {
    fmt_id: {
        "label":     fmt["label"],
        "width_cm":  fmt["celda_cm"]["ancho"],
        "height_cm": fmt["celda_cm"]["alto"],
        "slots":     fmt["slots"],
        "slot_cols": fmt.get("slot_cols", 1),
        "slot_rows": fmt.get("slot_rows", 1),
        "scale":     fmt["scale"],
    }
    for fmt_id, fmt in _FORMATOS.items()
}


def get_format(format_id: str) -> dict:
    fmt = FORMATS.get(format_id)
    if not fmt:
        raise ValueError(f"Formato desconocido: {format_id!r}. Disponibles: {list(FORMATS)}")
    return fmt


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def compute_layout(
    components: list[dict],
    format_id: str,
    master_format: str = "a4",
) -> list[dict]:
    """Calcula computed_bounds para cada componente en el formato destino.

    Prioridad de aplicación:
    1. Si format_id == master_format → base_bounds sin transformación
    2. Si el componente tiene format_overrides[format_id] → aplica overrides
       (los campos omitidos se calculan por escala automática)
    3. Sin overrides → escala proporcional master → target

    base_bounds y computed_bounds siempre en centímetros.
    """
    master = get_format(master_format)
    target = get_format(format_id)

    scale_x = target["width_cm"]  / master["width_cm"]
    scale_y = target["height_cm"] / master["height_cm"]

    result = []
    for comp in components:
        c    = copy.deepcopy(comp)
        base = comp.get("base_bounds", {})
        overrides = comp.get("format_overrides", {}).get(format_id, {})

        if format_id == master_format:
            computed = {
                "x":      base.get("x", 0),
                "y":      base.get("y", 0),
                "width":  base.get("width", 0),
                "height": base.get("height", 0),
            }
        elif overrides:
            # Overrides explícitos: solo sobreescriben los campos presentes;
            # los ausentes se escalan automáticamente desde base_bounds.
            computed = {
                "x":      overrides.get("x",      base.get("x", 0)      * scale_x),
                "y":      overrides.get("y",      base.get("y", 0)      * scale_y),
                "width":  overrides.get("width",  base.get("width", 0)  * scale_x),
                "height": overrides.get("height", base.get("height", 0) * scale_y),
            }
            # Overrides de estilo (font_size, color, etc.) se fusionan
            style_keys = {k: v for k, v in overrides.items()
                          if k not in ("x", "y", "width", "height")}
            if style_keys:
                c.setdefault("style", {}).update(style_keys)
        else:
            computed = {
                "x":      base.get("x", 0)      * scale_x,
                "y":      base.get("y", 0)      * scale_y,
                "width":  base.get("width", 0)  * scale_x,
                "height": base.get("height", 0) * scale_y,
            }

        c["computed_bounds"] = computed
        result.append(c)

    return result


def cm_to_emu(cm: float) -> int:
    """Convierte centímetros a EMU (unidad interna de python-pptx)."""
    return int(cm * 360_000)
