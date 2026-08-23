"""Motor de validación — detecta problemas en los datos antes de exportar."""
import re

# ---------------------------------------------------------------------------
# Umbrales
# ---------------------------------------------------------------------------

DESCRIPTION_WARN_CHARS = 60   # warning: posible truncado según template
DESCRIPTION_MAX_CHARS  = 100  # error: muy probable overflow

# ---------------------------------------------------------------------------
# Validación de lista de productos
# ---------------------------------------------------------------------------

def validate_products(products: list[dict]) -> dict:
    """Valida la lista de productos (output de data_engine) y devuelve un reporte.

    Devuelve:
    {
        "total":    int,
        "errors":   [{"row": int, "product": str, "type": str, "detail": str}],
        "warnings": [{"row": int, "product": str, "type": str, "detail": str}],
        "status":   "ok" | "warning" | "error"
    }
    """
    errors:   list[dict] = []
    warnings: list[dict] = []

    for i, p in enumerate(products):
        row  = i + 1
        name = p.get("descripcion") or f"Fila {row}"

        _check_price(p, row, name, warnings)
        _check_description(p, row, name, warnings)
        _check_bank(p, row, name, warnings)

    return {
        "total":    len(products),
        "errors":   errors,
        "warnings": warnings,
        "status":   "error" if errors else ("warning" if warnings else "ok"),
    }


# ---------------------------------------------------------------------------
# Checks individuales
# ---------------------------------------------------------------------------

def _check_price(p: dict, row: int, name: str, warnings: list) -> None:
    """Aviso si la fila no muestra ningún precio.

    Es un WARNING, no un error: ninguna variable es obligatoria desde
    08/2026, y hay diseños legítimos sin precio (un cartel de mecánica pura,
    una cenefa institucional). Solo se avisa para que nadie imprima 200
    carteles con el cuadro de precio en blanco sin haberlo decidido.
    """
    tiene_precio = any(
        str(p.get(v, "") or "").strip()
        for v in ("precioOferta", "precioRegular", "ofertaUno", "precioBanco")
    )
    if not tiene_precio:
        warnings.append({
            "row":     row,
            "product": name,
            "type":    "sin_precio",
            "detail":  "La fila no tiene ningún precio cargado",
        })


def _check_description(p: dict, row: int, name: str, warnings: list) -> None:
    desc = str(p.get("descripcion", "") or "").strip()
    if not desc:
        warnings.append({
            "row":     row,
            "product": f"Fila {row}",
            "type":    "sin_descripcion",
            "detail":  "Descripción vacía",
        })
        return

    if len(desc) > DESCRIPTION_MAX_CHARS:
        warnings.append({
            "row":     row,
            "product": name,
            "type":    "descripcion_muy_larga",
            "detail":  f"Descripción de {len(desc)} caracteres (máx recomendado: {DESCRIPTION_MAX_CHARS}). "
                        "El motor ya no la achica solo: revisá que entre en el cuadro.",
        })
    elif len(desc) > DESCRIPTION_WARN_CHARS:
        warnings.append({
            "row":     row,
            "product": name,
            "type":    "descripcion_larga",
            "detail":  f"Descripción de {len(desc)} caracteres (recomendado < {DESCRIPTION_WARN_CHARS})",
        })


def _check_bank(p: dict, row: int, name: str, warnings: list) -> None:
    if p.get("precioBanco") and not p.get("banco"):
        warnings.append({
            "row":     row,
            "product": name,
            "type":    "pbanco_without_banco",
            "detail":  "Precio bancario presente sin nombre de banco",
        })


# ---------------------------------------------------------------------------
# Resumen agregado para el dashboard
# ---------------------------------------------------------------------------

def build_summary(report: dict) -> dict:
    """Construye el resumen para el dashboard de validación final."""
    total    = report["total"]
    n_errors = len(report["errors"])
    n_warns  = len(report["warnings"])

    # Agrupar errores por tipo
    error_types: dict[str, int] = {}
    for e in report["errors"]:
        error_types[e["type"]] = error_types.get(e["type"], 0) + 1

    warn_types: dict[str, int] = {}
    for w in report["warnings"]:
        warn_types[w["type"]] = warn_types.get(w["type"], 0) + 1

    return {
        "total":             total,
        "correct":           total - n_errors,
        "with_warnings":     n_warns,
        "critical_errors":   n_errors,
        "status":            report["status"],
        "error_breakdown":   error_types,
        "warning_breakdown": warn_types,
    }
