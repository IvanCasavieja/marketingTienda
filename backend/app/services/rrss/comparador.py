"""Compara, con código, lo que CatTi leyó de cada placa contra lo que leyó del
mailing. Sin IA y sin base: funciones puras que se pueden probar con datos.

La regla de Ivan es ESTRICTA: lo que dice la placa tiene que ser
exactamente lo que dice el mailing. Eso quiere decir igualdad de texto
carácter por carácter -- "kg" no es "Kg", "100g" no es "100 g", una palabra
de más ("unidad") es una diferencia. Lo único que se normaliza es el corte de
renglones (ver catti.limpiar_texto): una descripción que en el mailing ocupa
cuatro renglones y en la placa dos es el mismo texto.

Emparejar una placa con su producto del mailing es OTRA cosa: ahí sí hay que
ser tolerante (una placa con la descripción mal escrita tiene que igual
encontrar su producto para poder mostrar la diferencia), por eso usa
similitud difusa y no igualdad.
"""
import math
import re
import unicodedata

from rapidfuzz import fuzz

from app.services.rrss import imagenes

# Cuánto se parecen dos descripciones para tomarlas por el mismo producto.
UMBRAL_EMPAREJAR = 72

# Formatos que las redes usan de verdad; cualquier otro es "otro" y se avisa.
FORMATOS_ESTANDAR = [nombre for nombre, _ in imagenes.FORMATOS]

# (campo, etiqueta) de lo que se compara producto contra producto, en el orden
# en que se muestra.
CAMPOS_PRODUCTO: tuple[tuple[str, str], ...] = (
    ("descripcion", "Descripción"),
    ("precio_anterior", "Precio anterior"),
    ("precio_anterior_tachado", "Precio anterior tachado"),
    ("mecanica", "Mecánica"),
    ("oferta_encabezado", "Encabezado de la oferta"),
    ("oferta_precio", "Precio de oferta"),
    ("oferta_pie", "Pie de la oferta"),
)

# Qué parte de la imagen hay que recortar para mostrar cada campo.
CAJA_DEL_CAMPO = {
    "descripcion": "descripcion",
    "precio_anterior": "descripcion",
    "precio_anterior_tachado": "descripcion",
    "mecanica": "mecanica",
    "oferta_encabezado": "oferta",
    "oferta_precio": "oferta",
    "oferta_pie": "oferta",
    "fecha": "fecha",
    "legal_bases": "legales",
    "legal_alcohol": "legales",
    "imagen_producto": "imagen",
}

# Campos que son un texto leído (los que la segunda lectura puede desmentir).
CAMPOS_DE_TEXTO = {c for c, _ in CAMPOS_PRODUCTO if c != "precio_anterior_tachado"} | {
    "fecha", "legal_bases", "legal_alcohol",
}


# --------------------------------------------------------------------------
# Emparejar placa <-> producto del mailing
# --------------------------------------------------------------------------

def clave(texto: str) -> str:
    """Forma de comparar descripciones para EMPAREJAR (no para validar): sin
    tildes, sin mayúsculas ni puntuación."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).split())


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def puntaje_producto(placa: dict, item: dict) -> float:
    """Qué tan probable es que `placa` sea el producto `item` (0 a ~115).

    Manda la descripción; el precio de oferta desempata entre productos de
    nombre parecido (dos cervezas de 710 ml), sin poder por sí solo
    convertir en pareja a dos productos que no se parecen en nada."""
    base = fuzz.token_set_ratio(clave(placa["descripcion"]), clave(item["descripcion"]))
    if _digitos(placa["oferta_precio"]) and _digitos(placa["oferta_precio"]) == _digitos(item["oferta_precio"]):
        base += 10
    if _digitos(placa["precio_anterior"]) and _digitos(placa["precio_anterior"]) == _digitos(item["precio_anterior"]):
        base += 5
    return base


def emparejar(placa: dict, productos: list[dict]) -> tuple[int | None, float]:
    """(índice del producto del mailing, puntaje) o (None, mejor_puntaje) si
    ninguno se parece lo suficiente. Si dos productos empatan casi en puntaje
    no se adivina: sin pareja, y que lo mire una persona."""
    if not productos:
        return None, 0.0
    puntajes = sorted(
        ((puntaje_producto(placa, p), i) for i, p in enumerate(productos)), reverse=True,
    )
    mejor, idx = puntajes[0]
    if mejor < UMBRAL_EMPAREJAR:
        return None, mejor
    if len(puntajes) > 1 and mejor - puntajes[1][0] < 3:
        return None, mejor
    return idx, mejor


# --------------------------------------------------------------------------
# Filas de comparación
# --------------------------------------------------------------------------

def _fila(campo: str, etiqueta: str, grupo: str, placa, mailing, estado: str,
          severidad: str | None, nota: str = "") -> dict:
    return {
        "campo": campo, "etiqueta": etiqueta, "grupo": grupo,
        "placa": placa, "mailing": mailing,
        "estado": estado, "severidad": severidad, "nota": nota,
        "caja": CAJA_DEL_CAMPO.get(campo),
    }


def _comparar_texto(campo: str, etiqueta: str, grupo: str, placa: str, esperado: str) -> dict | None:
    """Comparación ESTRICTA. None si ninguno de los dos lados tiene nada."""
    if not placa and not esperado:
        return None
    if placa == esperado:
        return _fila(campo, etiqueta, grupo, placa, esperado, "ok", None)
    if esperado and not placa:
        return _fila(campo, etiqueta, grupo, "", esperado, "falta_en_placa", "error")
    if placa and not esperado:
        return _fila(campo, etiqueta, grupo, placa, "", "sobra_en_placa", "error")
    return _fila(campo, etiqueta, grupo, placa, esperado, "diferente", "error")


def comparar_producto(placa: dict, item: dict) -> list[dict]:
    """El producto de la placa contra el del mailing, campo por campo."""
    filas = []
    for campo, etiqueta in CAMPOS_PRODUCTO:
        if campo == "precio_anterior_tachado":
            # Tachado o no solo tiene sentido si hay un precio de los dos lados.
            if placa["precio_anterior"] and item["precio_anterior"]:
                p, m = placa[campo], item[campo]
                texto = lambda t: "tachado" if t else "sin tachar"  # noqa: E731
                filas.append(_fila(
                    campo, etiqueta, "producto", texto(p), texto(m),
                    "ok" if p == m else "diferente", None if p == m else "error",
                ))
            continue
        fila = _comparar_texto(campo, etiqueta, "producto", placa[campo], item[campo])
        if fila:
            filas.append(fila)
    return filas


def comparar_elementos(placa: dict, mailing: dict, config: dict, es_alcohol: bool) -> list[dict]:
    """Lo que no es el producto: fecha, logo, isotipo, foto, leyendas y CTA."""
    filas: list[dict] = []

    # Fecha: contra la que dice el mailing.
    fila = _comparar_texto("fecha", "Fecha de la campaña", "placa", placa["fecha"], mailing.get("fecha", ""))
    if fila and mailing.get("fecha") == "":
        fila = None  # el mailing no trae fecha: no hay contra qué comparar
    if fila:
        filas.append(fila)

    filas.append(_presencia("logo_campana", "Logo de la campaña", placa["logo_campana_presente"]))
    filas.append(_presencia("isotipo", "Isotipo de la tienda", placa["isotipo_presente"]))

    img = placa["imagen_producto"]
    filas.append(_presencia("imagen_producto", "Foto del producto", img["presente"]))
    if img["presente"] and not img["coincide_con_descripcion"]:
        filas.append(_fila(
            "imagen_coincide", "La foto es del producto", "placa", img["que_se_ve"], placa["producto"]["descripcion"],
            "revisar", "aviso", img["motivo"] or "CatTi duda de que la foto sea de este producto",
        ))

    # Leyendas: bases y condiciones siempre; alcohol solo si el producto lo es.
    bases = (config.get("legal_bases") or "").strip()
    if bases:
        fila = _comparar_texto("legal_bases", "Bases y condiciones", "placa", placa["legal_bases"], bases)
        if fila:
            filas.append(fila)
    if es_alcohol:
        esperado = (config.get("legal_alcohol") or "").strip() or mailing.get("legal_alcohol", "")
        if esperado:
            fila = _comparar_texto("legal_alcohol", "Leyenda de alcohol", "placa", placa["legal_alcohol"], esperado)
            if fila:
                filas.append(fila)
    elif placa["legal_alcohol"]:
        filas.append(_fila(
            "legal_alcohol", "Leyenda de alcohol", "placa", placa["legal_alcohol"], "",
            "sobra_en_placa", "aviso", "La placa lleva la leyenda de alcohol pero el producto no parece ser alcohol",
        ))

    filas.append(_fila(
        "cta", "CTA (botón)", "placa", placa["cta"] or "sin CTA", None, "info", None,
    ))
    if placa["otros_textos"]:
        filas.append(_fila(
            "otros_textos", "Otros textos en la placa", "placa", " · ".join(placa["otros_textos"]), None,
            "info", None,
        ))
    return filas


def _presencia(campo: str, etiqueta: str, presente: bool) -> dict:
    if presente:
        return _fila(campo, etiqueta, "placa", "está", "debe estar", "ok", None)
    return _fila(campo, etiqueta, "placa", "no está", "debe estar", "falta_en_placa", "error")


def comparar_placa(placa: dict, mailing: dict, config: dict) -> tuple[int | None, float, list[dict]]:
    """Todo junto: empareja la placa con su producto y arma las filas.
    Devuelve (índice_en_mailing | None, puntaje, filas)."""
    idx, puntaje = emparejar(placa["producto"], mailing["productos"])
    filas: list[dict] = []
    es_alcohol = placa["producto"]["es_alcohol"]
    if idx is not None:
        item = mailing["productos"][idx]
        filas += comparar_producto(placa["producto"], item)
        es_alcohol = es_alcohol or item["es_alcohol"]
    filas += comparar_elementos(placa, mailing, config, es_alcohol)
    return idx, puntaje, filas


def confirmar_con_segunda_lectura(filas: list[dict], segunda: dict) -> list[dict]:
    """Un error de texto solo se sostiene si una SEGUNDA lectura de la misma
    placa lee lo mismo. Si CatTi lee distinto la segunda vez, lo que se
    "encontró" pudo ser un error de lectura y no de la placa: se degrada a un
    aviso para que una persona lo mire, en vez de acusar a la placa.

    `segunda` es {campo: valor_leído} de la segunda lectura."""
    for fila in filas:
        if fila["severidad"] != "error" or fila["campo"] not in CAMPOS_DE_TEXTO:
            continue
        if fila["estado"] == "falta_en_placa":
            leido = segunda.get(fila["campo"], "")
            if leido == "":
                continue  # las dos lecturas coinciden en que no está
        else:
            leido = segunda.get(fila["campo"], "")
            if leido == fila["placa"]:
                continue
        fila["estado"] = "revisar"
        fila["severidad"] = "aviso"
        fila["nota"] = f"CatTi leyó distinto en dos lecturas ({fila['placa']!r} y {leido!r}): confirmalo mirando la placa"
    return filas


def campos_leidos(placa: dict) -> dict:
    """Los campos de texto de una lectura, aplanados: lo que se compara entre
    la primera y la segunda lectura."""
    salida = {c: placa["producto"][c] for c in CAMPOS_DE_TEXTO if c in placa["producto"]}
    salida.update(fecha=placa["fecha"], legal_bases=placa["legal_bases"], legal_alcohol=placa["legal_alcohol"])
    return salida


def estado_de_la_placa(filas: list[dict], idx: int | None) -> str:
    """'sin_match' | 'diferencias' | 'avisos' | 'ok'."""
    if idx is None:
        return "sin_match"
    if any(f["severidad"] == "error" for f in filas):
        return "diferencias"
    if any(f["severidad"] == "aviso" for f in filas):
        return "avisos"
    return "ok"


# --------------------------------------------------------------------------
# Chequeos del lote: adaptaciones de un mismo producto, CTA
# --------------------------------------------------------------------------

def _agrupar(imgs: list[dict]) -> list[dict]:
    """Junta las placas del mismo producto (sus adaptaciones). Las que
    emparejaron con un producto del mailing van juntas por índice; las que no,
    se juntan por parecido de descripción entre sí."""
    grupos: dict[str, dict] = {}
    sueltos: list[dict] = []
    for img in imgs:
        if img["match_indice"] is not None:
            g = grupos.setdefault(f"m{img['match_indice']}", {
                "clave": f"m{img['match_indice']}", "match_indice": img["match_indice"], "imagenes": [],
            })
            g["imagenes"].append(img)
        else:
            sueltos.append(img)
    for img in sueltos:
        desc = clave(img["lectura"]["producto"]["descripcion"])
        for g in grupos.values():
            if g["match_indice"] is None and fuzz.token_set_ratio(desc, g["_desc"]) >= 85:
                g["imagenes"].append(img)
                break
        else:
            k = f"s{len(grupos)}"
            grupos[k] = {"clave": k, "match_indice": None, "imagenes": [img], "_desc": desc}
    return list(grupos.values())


def chequeos_del_lote(imgs: list[dict], productos_mailing: list[dict]) -> dict:
    """Lo que solo se ve mirando el conjunto.

    `imgs`: por placa {"id", "nombre_archivo", "formato", "match_indice",
    "lectura"} (la lectura normalizada de CatTi). Devuelve los grupos por
    producto con sus adaptaciones y los avisos del lote (CTA)."""
    grupos = _agrupar(imgs)

    # Formatos esperados: los que trae al menos la mitad de los productos.
    # Con un solo producto no hay con qué comparar y no se marca nada.
    conteo: dict[str, int] = {}
    for g in grupos:
        for f in {i["formato"] for i in g["imagenes"]}:
            conteo[f] = conteo.get(f, 0) + 1
    minimo = max(1, math.ceil(len(grupos) / 2))
    esperados = sorted(
        (f for f, n in conteo.items() if n >= minimo and f in FORMATOS_ESTANDAR),
        key=FORMATOS_ESTANDAR.index,
    )

    salida_grupos = []
    for g in grupos:
        imgs_g = g["imagenes"]
        presentes = [i["formato"] for i in imgs_g]
        repetidas = sorted({f for f in presentes if presentes.count(f) > 1})
        avisos = []
        for f in repetidas:
            ids = [i["id"] for i in imgs_g if i["formato"] == f]
            avisos.append({"tipo": "repetida", "formato": f, "imagenes": ids,
                           "texto": f"Hay {len(ids)} placas de este producto en formato {f}"})
        for f in sorted({i["formato"] for i in imgs_g if i["formato"] not in FORMATOS_ESTANDAR}):
            avisos.append({"tipo": "formato_raro", "formato": f, "imagenes": [i["id"] for i in imgs_g if i["formato"] == f],
                           "texto": f"Formato no reconocido ({f}): no es 1:1, 4:5 ni 9:16"})
        faltan = [f for f in esperados if f not in presentes]
        for f in faltan:
            avisos.append({"tipo": "falta_formato", "formato": f, "imagenes": [],
                           "texto": f"Le falta la adaptación {f}"})

        inconsistencias = []
        if g["match_indice"] is None and len(imgs_g) > 1:
            # Sin mailing con qué compararlas, lo único que se puede exigir es que
            # sus adaptaciones digan lo mismo entre sí.
            for campo, etiqueta in CAMPOS_PRODUCTO:
                valores = {i["id"]: i["lectura"]["producto"][campo] for i in imgs_g}
                if len({str(v) for v in valores.values()}) > 1:
                    inconsistencias.append({
                        "campo": campo, "etiqueta": etiqueta,
                        "valores": [
                            {"imagen": i["id"], "formato": i["formato"], "valor": valores[i["id"]]} for i in imgs_g
                        ],
                    })
        if inconsistencias:
            avisos.append({"tipo": "inconsistente", "formato": None, "imagenes": [i["id"] for i in imgs_g],
                           "texto": "Las adaptaciones de este producto no dicen lo mismo entre sí"})

        titulo = (
            productos_mailing[g["match_indice"]]["descripcion"]
            if g["match_indice"] is not None
            else imgs_g[0]["lectura"]["producto"]["descripcion"]
        )
        salida_grupos.append({
            "clave": g["clave"], "titulo": titulo, "match_indice": g["match_indice"],
            "imagenes": [i["id"] for i in imgs_g], "formatos": presentes,
            "avisos": avisos, "inconsistencias": inconsistencias,
        })

    return {
        "grupos": salida_grupos,
        "formatos_esperados": esperados,
        "cta": _chequeo_cta(imgs),
        "productos_mailing": len(productos_mailing),
        "productos_con_placa": len({g["match_indice"] for g in grupos if g["match_indice"] is not None}),
    }


def _chequeo_cta(imgs: list[dict]) -> dict:
    """¿Todas las placas traen el mismo CTA (o ninguna lo trae)? Si unas dicen
    'Comprar' y otras 'Ver más', o unas lo tienen y otras no, es un descuido."""
    por_cta: dict[str, list[int]] = {}
    for img in imgs:
        texto = img["lectura"]["cta"] or ""
        por_cta.setdefault(texto, []).append(img["id"])
    mezcla = len(por_cta) > 1
    return {
        "hay_mezcla": mezcla,
        "variantes": [
            {"cta": texto or None, "cantidad": len(ids), "imagenes": ids}
            for texto, ids in sorted(por_cta.items(), key=lambda kv: -len(kv[1]))
        ],
    }
