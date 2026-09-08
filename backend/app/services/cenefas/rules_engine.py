"""Motor de reglas — evalúa condiciones por fila y determina visibilidad de componentes."""
from typing import Any

from app.services.cenefas.variables import resolve


def _valor_de_campo(values: dict[str, Any], field: str) -> Any:
    """El valor del campo que mira una condición.

    Primero por el nombre tal cual vino, que es lo que hace falta para una
    columna suelta del Excel ("DESCUENTO 20"): esas no son variables y no
    resuelven a nada.

    Si no está, se resuelve como nombre de variable. El formulario de reglas
    pasa a MAYÚSCULAS lo que se escribe en "Columna del Excel", así que
    escribir `codigo` llegaba acá como `CODIGO` y no matcheaba nunca contra la
    fila, que trae la clave canónica en camelCase. Con esto, el campo de una
    regla tolera los mismos nombres que ya toleran el encabezado del Excel y
    el placeholder del PPTX -- mayúsculas, separadores y alias corto.
    """
    if field in values:
        return values[field]
    canonica = resolve(field)
    if canonica is not None and canonica in values:
        return values[canonica]
    return None


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
    value  = _valor_de_campo(values, field)
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

def _resolver_visibilidad(rules, values, clave_de) -> dict:
    """Modelo de visibilidad, para la clave que devuelva `clave_de`.

    - Sin reglas       → visible (no aparece en el dict devuelto)
    - Con regla show   → visible solo si al menos una show matchea
    - Con regla hide   → oculto si alguna hide matchea (tiene precedencia sobre show)

    La clave sale de una función porque el mismo modelo se aplica a dos cosas
    distintas: al cuadro entero y a un segmento suelto de un cuadro. `clave_de`
    devuelve None para las reglas que no le corresponden.
    """
    has_show: set = set()
    has_hide: set = set()
    show_ok:  set = set()
    hide_ok:  set = set()

    for rule in rules:
        clave = clave_de(rule)
        if clave is None:
            continue
        action  = rule.get("action", {}).get("type", "show")
        matched = _evaluate_condition(rule.get("condition", {}), values)

        if action == "show":
            has_show.add(clave)
            if matched:
                show_ok.add(clave)
        elif action == "hide":
            has_hide.add(clave)
            if matched:
                hide_ok.add(clave)

    result: dict = {}
    for clave in has_show | has_hide:
        if clave in hide_ok:
            result[clave] = False
        elif clave in has_show:
            result[clave] = clave in show_ok
        else:
            result[clave] = True

    return result


def _clave_componente(rule: dict):
    """El cuadro entero — solo para las reglas que NO apuntan a un segmento."""
    if rule.get("target_segment_index") is not None:
        return None
    return rule.get("target_component_id") or None


def _clave_segmento(rule: dict):
    """(cuadro, índice de segmento) — solo para las reglas que sí lo apuntan."""
    idx = rule.get("target_segment_index")
    comp_id = rule.get("target_component_id")
    if idx is None or not comp_id:
        return None
    return (comp_id, idx)


def evaluate_rules(rules: list[dict], values: dict[str, Any]) -> dict[str, bool]:
    """Devuelve {component_id: visible} para los componentes con reglas.

    Las reglas que apuntan a un segmento NO entran acá: se resuelven en
    `evaluate_segment_rules`. Si entraran, una regla de "ocultá la palabra
    'unidad'" ocultaría el cuadro entero del precio.
    """
    return _resolver_visibilidad(rules, values, _clave_componente)


def evaluate_segment_rules(
    rules: list[dict], values: dict[str, Any],
) -> dict[str, dict[int, bool]]:
    """Devuelve {component_id: {índice de segmento: visible}}.

    Para condicionar UN pedazo de un cuadro de texto compuesto sin tocar el
    resto. El caso que lo motivó: la palabra "unidad" al lado del precio, que
    solo corresponde cuando la cenefa es de una categoría unificada (varios
    SKU) -- ponerla en un cuadro aparte la dejaba desalineada del precio, y
    una regla sobre el cuadro se llevaba también al precio.
    """
    plano = _resolver_visibilidad(rules, values, _clave_segmento)
    salida: dict[str, dict[int, bool]] = {}
    for (comp_id, idx), visible in plano.items():
        salida.setdefault(comp_id, {})[idx] = visible
    return salida


def apply_visibility(
    components: list[dict],
    visibility: dict[str, bool],
    segment_visibility: dict[str, dict[int, bool]] | None = None,
) -> list[dict]:
    """Marca los componentes ocultos, sin sacarlos de la lista.

    Componentes sin entrada en `visibility` quedan visibles por defecto.

    Un segmento oculto (`segment_visibility`) se reemplaza por un segmento
    estático VACÍO en vez de sacarlo de la lista. Así todo lo que viene
    después --el texto que se arma, la medición por segmento, el achique, el
    chequeo de "partes fijas"-- lo ve vacío sin enterarse de que hubo una
    regla, exactamente igual que si la variable hubiera venido sin dato. Es
    una sola forma de estar vacío en todo el motor, no dos.

    Sacarlos de la lista parece equivalente y no lo es. Con `preserve_source`
    --que es como se genera todo desde 08/2026-- el shape YA EXISTE en el
    slide, puesto ahí por el archivo del diseñador. Un componente ausente de
    la lista significa "no lo toques", no "no lo dibujes": el shape sobrevive
    con lo que trajera el diseño. Asi, una regla de ocultar no ocultaba nada,
    dejaba impreso el contenido original.

    No se habia notado porque hasta ahora ninguna plantilla tenia reglas.

    Marcandolo, _render_slide lo saca del slide. En el camino sin
    preserve_source el resultado es el mismo que antes: un componente oculto
    no tiene shape que mutar y no se dibuja nada.
    """
    salida = []
    for c in components:
        if not visibility.get(c["id"], True):
            salida.append({**c, "visible": False})
            continue

        ocultos = (segment_visibility or {}).get(c["id"])
        segs = c.get("segments")
        if ocultos and segs:
            salida.append({**c, "segments": [
                {**seg, "type": "static", "value": ""}
                if ocultos.get(i) is False else seg
                for i, seg in enumerate(segs)
            ]})
            continue

        salida.append(c)
    return salida
