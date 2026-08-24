"""Revision del Excel ANTES de generar la cenefa.

`validation_engine` mira fila por fila: a este producto le falta el precio, a
aquel la descripcion. Esto mira el ARCHIVO ENTERO contra la plantilla elegida,
que es donde estan los errores que arruinan una corrida completa y que fila
por fila no se ven.

El caso que motivo esto: un listado con la columna llamada "Precio Anterior"
en vez de "precioRegular". Fila por fila no hay nada raro --ninguna tiene el
dato-- y sin embargo las 10 cenefas salen sin precio. Visto desde arriba es
obvio: hay una columna que el motor no reconocio y una variable que quedo
vacia en el 100% de las filas.

NUNCA bloquea. Avisa y la persona decide: hay casos donde el que sabe es el
que esta mirando y la revision se equivoca (una campana donde el precio
regular no va a proposito, por ejemplo).

Cada hallazgo trae:
    nivel      "alto" (va a salir roto) | "medio" (revisar) | "info"
    titulo     una linea, lo que pasa
    detalle    el dato concreto: que columna, cuantas filas
    sugerencia que hacer, en imperativo y concreto
"""
from __future__ import annotations

import difflib
from typing import Any

from app.services.cenefas.variables import (
    CANONICAL_VARS,
    DECIMAL_OF,
    INTERNAL_SET,
    PRICE_VARS,
    resolve,
)

# Variables sin las que una cenefa no se sostiene. Si alguna queda vacia en
# TODAS las filas, es casi seguro un problema de la columna y no del dato.
_IMPRESCINDIBLES = ("codigo", "descripcion", "precioOferta")

# Columnas del export de gestion que se ignoran a proposito: no son variables,
# el Convertidor ya las interpreta, y avisar por ellas seria solo ruido.
_IGNORADAS = {
    "moneda", "seccion", "nrooferta", "nombrearticulo", "proveedor", "usuario",
    "rol", "comprador", "oferta", "ofertadet", "descuentoprov", "descuentoprovdet",
    "forecastuni", "exhibicion", "objetivo", "destacadomailing", "aporte",
    "descripcionweb", "comentarios", "comentarios2", "categoria", "subcategoria",
}

# Como suele llamarse cada variable cuando NO se llama como debe. Se consulta
# antes que el parecido por letras, que se equivoca feo: "Precio Anterior" se
# parece tanto a "precioRegular" como a "precioBanco", y difflib elegia el
# segundo. Esto no hace que la columna funcione --para eso hay que renombrarla
# igual-- solo sirve para sugerir bien.
_SINONIMOS: dict[str, str] = {
    "precioanterior":   "precioRegular",
    "preciosanterior":  "precioRegular",
    "precioant":        "precioRegular",
    "precioregular":    "precioRegular",
    "pvpregular":       "precioRegular",
    "regular":          "precioRegular",
    "anterior":         "precioRegular",
    "precio":           "precioOferta",
    "preciooferta":     "precioOferta",
    "pvpoferta":        "precioOferta",
    "preciofinal":      "precioOferta",
    "oferta":           "precioOferta",
    "sku":              "codigo",
    "codigoarticulo":   "codigo",
    "codigosku":        "codigo",
    "articulo":         "descripcion",
    "producto":         "descripcion",
    "nombre":           "descripcion",
    "detalle":          "descripcion",
    "vigencia":         "vigencia",
    "validez":          "vigencia",
    "periodo":          "vigencia",
    "legal":            "legales",
    "legales":          "legales",
    "aclaracion":       "aclaracionUno",
    "mecanica":         "mecanica",
    "tipooferta":       "tipoOferta",
    "banco":            "banco",
}


def _norm(t: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFD", str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _parecida(nombre: str) -> str | None:
    """Qué variable quiso ser este encabezado, si se puede saber.

    Primero la tabla de sinónimos, que es la que sabe que "Precio Anterior" es
    precioRegular. Recién si no está ahí se busca por parecido de letras, y con
    un corte alto: una sugerencia equivocada es peor que ninguna.
    """
    objetivo = _norm(nombre)
    if not objetivo:
        return None
    if objetivo in _SINONIMOS:
        return _SINONIMOS[objetivo]
    candidatas = {_norm(v): v for v in CANONICAL_VARS}
    cerca = difflib.get_close_matches(objetivo, candidatas, n=1, cutoff=0.85)
    return candidatas[cerca[0]] if cerca else None


def revisar(
    headers: list[str],
    productos: list[dict[str, Any]],
    variables_plantilla: set[str] | None = None,
) -> list[dict[str, str]]:
    """Revisa el Excel ya leido contra la plantilla elegida.

    `headers` son los encabezados crudos del Excel, `productos` lo que el
    motor entendio, y `variables_plantilla` las variables que la plantilla
    tiene cuadro para imprimir (None si no se sabe cual se va a usar).
    """
    hallazgos: list[dict[str, str]] = []
    n = len(productos)
    if not n:
        return hallazgos

    # ── 1. Columnas que el motor no reconocio ────────────────────────────
    for h in headers:
        crudo = str(h or "").strip()
        if not crudo or resolve(crudo) or _norm(crudo) in _IGNORADAS:
            continue
        parecida = _parecida(crudo)
        hallazgos.append({
            "nivel":      "medio" if not parecida else "alto",
            "tipo":       "columna_no_reconocida",
            "titulo":     f'La columna «{crudo}» no se usa',
            "detalle":    "El motor no la reconoce como ninguna de las variables, "
                          "así que su contenido no llega a la cenefa.",
            "sugerencia": (f'Si es esa, renombrala a «{parecida}».' if parecida
                           else "Si tiene que salir en el cartel, renombrala con el "
                                "nombre exacto de la variable."),
        })

    # ── 2. Variables clave vacias en TODAS las filas ─────────────────────
    for var in _IMPRESCINDIBLES:
        con_dato = sum(1 for p in productos if str(p.get(var, "") or "").strip())
        if con_dato:
            continue
        # ¿Hay una columna que se le parece y no se reconocio? Ahí está la causa.
        culpable = next(
            (str(h).strip() for h in headers
             if str(h or "").strip() and not resolve(str(h).strip())
             and _parecida(str(h).strip()) == var),
            None,
        )
        hallazgos.append({
            "nivel":      "alto",
            "tipo":       "variable_vacia",
            "titulo":     f'Las {n} cenefas van a salir sin {var}',
            "detalle":    (f'Ninguna de las {n} filas tiene {var}.'
                           + (f' La columna «{culpable}» parece ser esa.' if culpable else "")),
            "sugerencia": (f'Renombrá la columna «{culpable}» a «{var}».' if culpable
                           else f'Agregá una columna llamada «{var}».'),
        })

    # ── 3. Datos que la plantilla no tiene donde imprimir ────────────────
    if variables_plantilla is not None:
        for var in CANONICAL_VARS:
            if var in variables_plantilla or var in INTERNAL_SET:
                continue
            con_dato = sum(1 for p in productos if str(p.get(var, "") or "").strip())
            if not con_dato:
                continue
            # El decimal viaja con su precio: si el precio no se imprime, que el
            # decimal tampoco es esperable y avisar por los dos es ruido.
            if var in DECIMAL_OF.values():
                continue
            hallazgos.append({
                "nivel":      "medio",
                "tipo":       "dato_sin_cuadro",
                "titulo":     f'«{var}» tiene datos pero no se va a imprimir',
                "detalle":    f'{con_dato} de {n} filas traen {var}, y esta plantilla '
                              f'no tiene un cuadro <<{var}>>.',
                "sugerencia": f'Agregá el cuadro <<{var}>> al PPTX, o ignoralo si '
                              f'en esta cenefa no va.',
            })

        # Al revés: cuadros de la plantilla que van a quedar vacíos.
        #
        # Va en UNA sola línea y como "info", no uno por variable: casi todas
        # las plantillas tienen cuadros opcionales que este listado no llena, y
        # eso es lo normal, no un problema. Separados eran cuatro avisos de ocho
        # para un archivo perfecto -- y una revisión que avisa de más se
        # empieza a ignorar entera, incluidos los avisos que sí importan.
        #
        # Lo ya reportado como "las N cenefas van a salir sin X" no se repite:
        # es el mismo problema contado de otra forma.
        ya_dicho = {h["titulo"].rsplit(" ", 1)[-1] for h in hallazgos
                    if h["tipo"] == "variable_vacia"}
        vacios = [
            var for var in sorted(variables_plantilla - INTERNAL_SET)
            if var in CANONICAL_VARS and var not in ya_dicho
            and var not in DECIMAL_OF.values()
            and not any(str(p.get(var, "") or "").strip() for p in productos)
        ]
        if vacios:
            hallazgos.append({
                "nivel":      "info",
                "tipo":       "cuadro_sin_dato",
                "titulo":     (f'{len(vacios)} cuadros de la plantilla van a quedar vacíos'
                               if len(vacios) > 1
                               else f'El cuadro <<{vacios[0]}>> va a quedar vacío'),
                "detalle":    "La plantilla los tiene pero el Excel no trae esas columnas: "
                              + ", ".join(vacios) + ".",
                "sugerencia": "Si alguno tiene que salir, agregá esa columna al Excel. "
                              "Si no, está bien así: ningún cuadro es obligatorio.",
            })

    # ── 4. Precios que quedaron como texto ───────────────────────────────
    # Un precio que no es un numero se imprime tal cual. A veces es correcto
    # --"2x1" en una mecanica M x N ocupa el cuadro del precio a proposito--
    # pero cuando pasa en una sola fila suelta suele ser un dato sucio.
    for var in PRICE_VARS:
        raros = [
            (i, str(p.get(var, "")).strip())
            for i, p in enumerate(productos, 1)
            if str(p.get(var, "") or "").strip()
            and not str(p.get(var, "")).strip().replace(".", "").replace(",", "").isdigit()
        ]
        if not raros or len(raros) == n:
            continue          # ninguna, o todas: es la mecánica del listado
        muestras = ", ".join(f'fila {i}: «{v}»' for i, v in raros[:3])
        hallazgos.append({
            "nivel":      "medio",
            "tipo":       "precio_no_numerico",
            "titulo":     f'{len(raros)} de {n} filas tienen {var} con texto',
            "detalle":    f'Se va a imprimir tal cual en el cuadro del precio. {muestras}.',
            "sugerencia": 'Si es una mecánica (2x1) está bien; si no, dejá solo el número.',
        })

    # Primero lo grave.
    orden = {"alto": 0, "medio": 1, "info": 2}
    hallazgos.sort(key=lambda h: orden.get(h["nivel"], 9))
    return hallazgos
