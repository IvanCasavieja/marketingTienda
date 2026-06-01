"""Motor de layout — calcula posiciones y tamaños de componentes por formato destino."""
import copy

# ---------------------------------------------------------------------------
# Registro de formatos (configuración del sistema, no por template)
# ---------------------------------------------------------------------------

FORMATS: dict[str, dict] = {
    "a4": {
        "label":     "A4",
        "width_cm":  21.0,
        "height_cm": 29.7,
        "slots":     1,
        "scale":     1.0,
    },
    "a3": {
        "label":     "A3",
        "width_cm":  29.7,
        "height_cm": 42.0,
        "slots":     1,
        "scale":     1.414,
    },
    "3xa4": {
        "label":     "3xA4",
        "width_cm":  63.0,
        "height_cm": 29.7,
        "slots":     3,
        "scale":     1.0,
    },
    "pinchos": {
        "label":     "Pinchos",
        "width_cm":  10.5,
        "height_cm": 29.7,
        "slots":     1,
        "scale":     0.5,
    },
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
