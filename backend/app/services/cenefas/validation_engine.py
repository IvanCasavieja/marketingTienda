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

        _check_price(p, row, name, errors)
        _check_description(p, row, name, errors, warnings)
        _check_combo(p, row, name, errors)
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

def _check_price(p: dict, row: int, name: str, errors: list) -> None:
    price_str = p.get("precio", "")
    # Extraer parte numérica: quitar símbolo de moneda y separadores de miles
    num_str = re.sub(r"[^\d,.]", "", price_str).replace(".", "").replace(",", ".")
    try:
        if not num_str or float(num_str) == 0:
            errors.append({
                "row":     row,
                "product": name,
                "type":    "missing_price",
                "detail":  f"Precio vacío o cero: {price_str!r}",
            })
    except ValueError:
        errors.append({
            "row":     row,
            "product": name,
            "type":    "invalid_price",
            "detail":  f"Precio no parseable: {price_str!r}",
        })


def _check_description(p: dict, row: int, name: str, errors: list, warnings: list) -> None:
    desc     = p.get("descripcion", "").strip()
    desc_len = len(desc)

    if not desc:
        errors.append({
            "row":     row,
            "product": f"Fila {row}",
            "type":    "empty_description",
            "detail":  "Descripción vacía",
        })
        return

    if desc_len > DESCRIPTION_MAX_CHARS:
        errors.append({
            "row":     row,
            "product": name,
            "type":    "description_too_long",
            "detail":  f"Descripción de {desc_len} caracteres (máx recomendado: {DESCRIPTION_MAX_CHARS})",
        })
    elif desc_len > DESCRIPTION_WARN_CHARS:
        warnings.append({
            "row":     row,
            "product": name,
            "type":    "description_long",
            "detail":  f"Descripción de {desc_len} caracteres (recomendado < {DESCRIPTION_WARN_CHARS})",
        })


def _check_combo(p: dict, row: int, name: str, errors: list) -> None:
    p1 = p.get("p1", "")
    if re.match(r"^\d+X$", p1) and not p.get("mecanica"):
        errors.append({
            "row":     row,
            "product": name,
            "type":    "combo_missing_mecanica",
            "detail":  f"Producto combo ({p1}) sin mecánica de precio",
        })


def _check_bank(p: dict, row: int, name: str, warnings: list) -> None:
    if p.get("pbanco") and not p.get("banco"):
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
