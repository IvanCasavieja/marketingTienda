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
    if op in ("length_greater_than", "length_less_than"):
        # Largo del texto, no su valor numérico: "tiene más de 3 caracteres"
        # es la condición con la que se declara a mano el cuerpo de un precio
        # (ver `set_font_size`). `greater_than` no sirve para eso -- compara
        # 1.599 > 3 como números y da verdadero para CUALQUIER precio.
        largo = len(str(value or "").strip())
        try:
            objetivo = float(str(target).strip())
        except (TypeError, ValueError):
            return False
        return largo > objetivo if op == "length_greater_than" else largo < objetivo

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


# ---------------------------------------------------------------------------
# Cuerpo declarado por regla
# ---------------------------------------------------------------------------
#
# Reemplaza al achique automático que había hasta el 14/09/2026 (criterio de
# Ivan). Aquel medía el texto con las métricas de la tipografía, lo comparaba
# contra la caja y contra los vecinos, y decidía solo: cuatro pasos encadenados
# --_fit_font_size, _AGRUPAR_POR_FILA, _resolver_solapes y
# _unificar_tamanos_entre_bandas-- de los cuales dos multiplicaban sus pisos
# (0,55 sobre 0,55 = 30% del cuerpo de diseño) y los otros dos propagaban el
# peor resultado a toda la hoja.
#
# Pero el problema de fondo no era el compounding: era que ese cálculo dependía
# de métricas de fuente, geometría de los vecinos y ancho de papel, o sea de
# tres cosas que había que replicar IDÉNTICAS en el navegador para que el
# preview no mintiera. Nunca se logró: el preview llamaba al motor sin el ancho
# de página y mostraba cuerpos que el PPTX no respetaba.
#
# Una condición sobre el LARGO del texto no depende de nada de eso. `len()` da
# lo mismo en Python que en TypeScript, así que la divergencia preview/export
# deja de ser algo que hay que mantener sincronizado y pasa a ser imposible.
#
# Ojo con una cosa al declarar las reglas: cantidad de caracteres NO es ancho.
# En Impact --la tipografía de los precios-- el "1" mide 0,38 em y el "6" 0,54:
# "$111" y "$666" tienen los mismos 4 caracteres y se llevan 2,37 cm a 140 pt.
# El cuerpo que se escribe en la regla hay que elegirlo para el PEOR caso (todo
# seises), que es justamente lo que muestra el relleno de capacidad
# (capacidad.py). En las otras siete tipografías de la tabla los dígitos son
# tabulares --todos el mismo ancho-- y la cuenta por caracteres es exacta.


def _resolver_tamanos(rules, values, clave_de) -> dict:
    """El cuerpo en pt que las reglas le imponen a cada clave.

    Si matchean varias, **gana la más chica**. No gana "la última" ni "la más
    abajo en la lista": el orden de las reglas no importa, igual que en
    `_resolver_visibilidad`. Así, escribir

        si precioOferta tiene más de 3 caracteres -> 90 pt
        si precioOferta tiene más de 4 caracteres -> 70 pt

    hace lo obvio para un precio de 5 cifras (matchean las dos, sale 70) sin
    que haya que pensar en qué orden quedaron guardadas.

    Una clave sin ninguna regla que matchee no aparece en el dict: conserva el
    cuerpo que le dio el diseño.
    """
    salida: dict = {}
    for rule in rules:
        clave = clave_de(rule)
        if clave is None:
            continue
        accion = rule.get("action", {}) or {}
        if accion.get("type") != "set_font_size":
            continue
        try:
            pt = float(accion.get("value"))
        except (TypeError, ValueError):
            continue
        if pt <= 0:
            continue
        if not _evaluate_condition(rule.get("condition", {}), values):
            continue
        anterior = salida.get(clave)
        salida[clave] = pt if anterior is None else min(anterior, pt)
    return salida


def evaluate_font_size_rules(rules: list[dict], values: dict[str, Any]) -> dict[str, float]:
    """Devuelve {component_id: cuerpo en pt} para los cuadros con regla de tamaño."""
    return _resolver_tamanos(rules, values, _clave_componente)


def evaluate_segment_font_size_rules(
    rules: list[dict], values: dict[str, Any],
) -> dict[str, dict[int, float]]:
    """Devuelve {component_id: {índice de segmento: cuerpo en pt}}."""
    plano = _resolver_tamanos(rules, values, _clave_segmento)
    salida: dict[str, dict[int, float]] = {}
    for (comp_id, idx), pt in plano.items():
        salida.setdefault(comp_id, {})[idx] = pt
    return salida


def apply_font_sizes(
    components: list[dict],
    sizes: dict[str, float],
    segment_sizes: dict[str, dict[int, float]] | None = None,
) -> list[dict]:
    """Aplica los cuerpos declarados por regla. SIEMPRE devuelve copias.

    Lo de las copias no es prolijidad. El layout se arma UNA vez y se reusa
    para todos los productos de la corrida: si se devolviera el diccionario
    original, el cuerpo que le tocó a un producto se le quedaría pegado al
    siguiente. Bug real de 09/2026, cuando esto lo hacía el achique automático:
    con <<precioOferta>> fijado en 140 pt salieron seis hojas seguidas en
    120 / 88,3 / 88,3 / 88,3 / 83,9 / 83,9, cada una arrancando del tamaño que
    le dejó la anterior.

    En un cuadro multi-segmento cada segmento lleva SU font_size y ese pisa al
    del componente al dibujar (ver _populate_text_frame). Por eso una regla
    sobre el cuadro entero escala también a sus segmentos: sin eso el cuerpo
    declarado se descartaba en silencio en casi todas las plantillas, que se
    importan multi-segmento.
    """
    segment_sizes = segment_sizes or {}
    salida = []
    for c in components:
        nueva = dict(c)
        if isinstance(c.get("style"), dict):
            nueva["style"] = dict(c["style"])

        pt = sizes.get(c.get("id"))
        if pt:
            # El cuerpo contra el que se calcula la escala de los segmentos.
            # Un cuadro puede no tener font_size propio y llevar el tamaño solo
            # en sus segmentos (pasa con los importados); ahí la referencia es
            # el segmento más grande, mismo criterio que usa capacidad.py. Sin
            # esto la escala quedaba en 1 y la regla no movía ningún segmento,
            # o sea no hacía nada visible.
            base = (c.get("style") or {}).get("font_size")
            if not base and c.get("segments"):
                tam = [(s.get("style") or {}).get("font_size") for s in c["segments"]]
                tam = [t for t in tam if t]
                base = max(tam) if tam else None
            nueva["style"] = {**nueva.get("style", {}), "font_size": pt}
            escala = (pt / base) if base else 1.0
            if nueva["style"].get("line_height_pt"):
                nueva["style"]["line_height_pt"] = round(
                    nueva["style"]["line_height_pt"] * escala, 1)
            if nueva.get("segments"):
                nueva["segments"] = [
                    {**seg, "style": {**seg["style"],
                                      "font_size": round(seg["style"]["font_size"] * escala, 1)}}
                    if (seg.get("style") or {}).get("font_size") else seg
                    for seg in nueva["segments"]
                ]

        por_segmento = segment_sizes.get(c.get("id"))
        if por_segmento and nueva.get("segments"):
            nueva["segments"] = [
                {**seg, "style": {**(seg.get("style") or {}), "font_size": por_segmento[i]}}
                if i in por_segmento else seg
                for i, seg in enumerate(nueva["segments"])
            ]

        salida.append(nueva)
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
