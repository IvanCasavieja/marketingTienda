"""Motor de reglas — evalúa condiciones por fila y determina visibilidad de componentes."""
from typing import Any


# ---------------------------------------------------------------------------
# Evaluación de condiciones
# ---------------------------------------------------------------------------

def _evaluate_condition(condition: dict, values: dict[str, Any]) -> bool:
    """Evalúa una condición simple o compuesta de forma recursiva."""
    op = condition.get("operator", "")

    # Compuestas
    if op == "and":
        return all(_evaluate_condition(c, values) for c in condition.get("conditions", []))
    if op == "or":
        return any(_evaluate_condition(c, values) for c in condition.get("conditions", []))
    if op == "not":
        return not _evaluate_condition(condition.get("condition", {}), values)

    # Simples
    field  = condition.get("field", "")
    value  = values.get(field)
    target = condition.get("value")

    if op == "equals":
        return str(value or "").strip() == str(target or "").strip()
    if op == "not_equals":
        return str(value or "").strip() != str(target or "").strip()
    if op == "greater_than":
        try:
            return float(value or 0) > float(target or 0)
        except (ValueError, TypeError):
            return False
    if op == "less_than":
        try:
            return float(value or 0) < float(target or 0)
        except (ValueError, TypeError):
            return False
    if op == "contains":
        return str(target or "").lower() in str(value or "").lower()
    if op == "is_empty":
        return not value or str(value).strip() == ""
    if op == "is_not_empty":
        return bool(value and str(value).strip())

    return True  # operador desconocido no filtra


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def evaluate_rules(rules: list[dict], values: dict[str, Any]) -> dict[str, bool]:
    """Devuelve {component_id: visible} para todos los componentes con reglas.

    Modelo de visibilidad:
    - Sin reglas       → visible (no aparece en el dict devuelto)
    - Con regla show   → visible solo si al menos una show matchea
    - Con regla hide   → oculto si alguna hide matchea (tiene precedencia sobre show)
    """
    has_show: set[str] = set()
    has_hide: set[str] = set()
    show_ok:  set[str] = set()
    hide_ok:  set[str] = set()

    for rule in rules:
        comp_id = rule.get("target_component_id")
        if not comp_id:
            continue
        action  = rule.get("action", {}).get("type", "show")
        matched = _evaluate_condition(rule.get("condition", {}), values)

        if action == "show":
            has_show.add(comp_id)
            if matched:
                show_ok.add(comp_id)
        elif action == "hide":
            has_hide.add(comp_id)
            if matched:
                hide_ok.add(comp_id)

    result: dict[str, bool] = {}
    for comp_id in has_show | has_hide:
        if comp_id in hide_ok:
            result[comp_id] = False
        elif comp_id in has_show:
            result[comp_id] = comp_id in show_ok
        else:
            result[comp_id] = True

    return result


def apply_visibility(components: list[dict], visibility: dict[str, bool]) -> list[dict]:
    """Filtra la lista de componentes según el dict de visibilidad.

    Componentes sin entrada en `visibility` quedan visibles por defecto.
    """
    return [c for c in components if visibility.get(c["id"], True)]
