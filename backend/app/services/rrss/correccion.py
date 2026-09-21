"""Cómo se le cuenta una diferencia al diseñador que tiene que corregir la placa.

Dos cosas distintas, a propósito:
- `instruccion` dice QUÉ HACER en una frase corta ("sobra el punto final"). Va
  por carácter, porque ahí la precisión importa: un espacio es un espacio.
- `diferenciar_palabras` dice DÓNDE está, resaltando la palabra entera. Por
  carácter no se ve: lo que más se repite ("300g" contra "300 g") es un espacio,
  y un espacio resaltado es invisible.

Sin IA y sin base: funciones puras.
"""
import os
import re


def diferenciar(placa: str, mailing: str) -> tuple[list[tuple[str, bool]], list[tuple[str, bool]]]:
    """Diferencia carácter a carácter (LCS). Devuelve los segmentos de cada lado
    como [(texto, distinto)]. Es el mismo criterio que la pantalla (rrssUtils.ts)."""
    a, b = list(placa), list(mailing)
    n, m = len(a), len(b)
    largos = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            largos[i][j] = largos[i + 1][j + 1] + 1 if a[i] == b[j] else max(largos[i + 1][j], largos[i][j + 1])
    seg_a: list[tuple[str, bool]] = []
    seg_b: list[tuple[str, bool]] = []

    def agregar(seg, c, distinto):
        if seg and seg[-1][1] == distinto:
            seg[-1] = (seg[-1][0] + c, distinto)
        else:
            seg.append((c, distinto))

    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            agregar(seg_a, a[i], False)
            agregar(seg_b, b[j], False)
            i += 1
            j += 1
        elif largos[i + 1][j] >= largos[i][j + 1]:
            agregar(seg_a, a[i], True)
            i += 1
        else:
            agregar(seg_b, b[j], True)
            j += 1
    while i < n:
        agregar(seg_a, a[i], True)
        i += 1
    while j < m:
        agregar(seg_b, b[j], True)
        j += 1
    return seg_a, seg_b


def diferenciar_palabras(placa: str, mailing: str) -> tuple[list[tuple[str, bool]], list[tuple[str, bool]]]:
    """Como `diferenciar`, pero marca la PALABRA entera que cambia: **300g** contra
    **300 g**, **Kg** contra **kg**. Es para mostrárselo a una persona; el detalle
    exacto lo da `instruccion`, que sí va por carácter."""
    a, b = placa.split(" "), mailing.split(" ")
    n, m = len(a), len(b)
    largos = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            largos[i][j] = largos[i + 1][j + 1] + 1 if a[i] == b[j] else max(largos[i + 1][j], largos[i][j + 1])
    marca_a, marca_b = [False] * n, [False] * m
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif largos[i + 1][j] >= largos[i][j + 1]:
            marca_a[i] = True
            i += 1
        else:
            marca_b[j] = True
            j += 1
    for k in range(i, n):
        marca_a[k] = True
    for k in range(j, m):
        marca_b[k] = True

    def segmentos(palabras, marcas):
        seg: list[tuple[str, bool]] = []
        for k, (p, d) in enumerate(zip(palabras, marcas)):
            if k > 0:
                # el espacio entre dos palabras marcadas va marcado: "300 g" se lee como una unidad
                espacio = d and marcas[k - 1]
                if seg and seg[-1][1] == espacio:
                    seg[-1] = (seg[-1][0] + " ", espacio)
                else:
                    seg.append((" ", espacio))
            if seg and seg[-1][1] == d:
                seg[-1] = (seg[-1][0] + p, d)
            else:
                seg.append((p, d))
        return seg

    return segmentos(a, marca_a), segmentos(b, marca_b)


# ── La instrucción ────────────────────────────────────────────────────────

_NOMBRE = {".": "el punto", ",": "la coma", ";": "el punto y coma", ":": "los dos puntos"}


def _describir(trozos) -> str:
    """Cómo se nombra en voz alta lo que sobra o falta."""
    partes = []
    for t in trozos:
        if not t:
            continue
        if t.strip() == "":
            partes.append("el espacio")
        elif t.strip() in _NOMBRE:
            partes.append(_NOMBRE[t.strip()])
        else:
            partes.append(f"«{t.strip()}»")
    vistos = list(dict.fromkeys(partes))
    if not vistos:
        return ""
    if len(vistos) == 1:
        return vistos[0]
    return ", ".join(vistos[:-1]) + " y " + vistos[-1]


def _mayuscula_inicial(s: str) -> str:
    """Solo la primera letra. `str.capitalize()` además BAJA todo el resto: eso
    convertía "«Colonia» va en mayúscula" en "«colonia» va en mayúscula", o sea
    la instrucción decía justo lo contrario de lo que hay que hacer."""
    return s[:1].upper() + s[1:] if s else s


def _unir(frases: list[str]) -> str:
    frases = [f for f in frases if f]
    if len(frases) <= 1:
        return frases[0] if frases else ""
    return frases[0] + ", y " + ". ".join(frases[1:])


def _palabra_antes(texto: str, pos: int) -> str:
    """La última palabra completa antes de `pos`: para decir DÓNDE va algo."""
    izq = texto[:pos].rstrip(" .,;:")
    return izq.split(" ")[-1].strip(" .,;:") if izq else ""


def _posiciones(segmentos) -> list[tuple[str, int]]:
    """[(texto_distinto, posición_donde_empieza)] de un lado del diff."""
    salida, pos = [], 0
    for texto, distinto in segmentos:
        if distinto:
            salida.append((texto, pos))
        pos += len(texto)
    return salida


def _cambios_de_caja(placa: str, mailing: str) -> list[str]:
    """Palabras del mailing que en la placa están escritas con otra caja."""
    sueltas = set(placa.split(" "))
    minusculas = {p.lower() for p in sueltas}
    return [p for p in mailing.split(" ") if p and p not in sueltas and p.lower() in minusculas]


def _espacios_faltantes(placa: str, mailing: str) -> list[str]:
    """Pares de palabras del mailing que en la placa vienen pegadas ("100 g")."""
    palabras = mailing.split(" ")
    return [f"{a} {b}" for a, b in zip(palabras, palabras[1:]) if a and b and (a + b) in placa]


def instruccion(estado: str, placa: str, mailing: str) -> str:
    """Qué hacer, en una frase que se pueda decir en voz alta en dos segundos."""
    placa, mailing = placa or "", mailing or ""
    if estado == "falta_en_placa":
        return f"Falta {_describir([mailing])}: agregalo"
    if estado == "sobra_en_placa":
        return f"Sobra {_describir([placa])}: sacalo"
    if estado == "revisar":
        return "Miralo a mano contra el mailing"
    if estado != "diferente" or placa == mailing:
        return ""

    seg_p, seg_m = diferenciar(placa, mailing)
    pos_sobra, pos_falta = _posiciones(seg_p), _posiciones(seg_m)
    sobra = [t for t, _ in pos_sobra]
    falta = [t for t, _ in pos_falta]
    sin_espacios = (placa.replace(" ", ""), mailing.replace(" ", ""))

    # Solo cambian mayúsculas/minúsculas
    if placa.lower() == mailing.lower():
        cambios = _cambios_de_caja(placa, mailing)
        if cambios:
            caja = "minúscula" if cambios[0].islower() else "mayúscula"
            return f"Va en {caja}: «{cambios[0]}»"
        return f"Es cuestión de mayúsculas: tiene que decir «{mailing}»"

    # Solo cambian espacios, o espacios y mayúsculas
    if sin_espacios[0] == sin_espacios[1] or sin_espacios[0].lower() == sin_espacios[1].lower():
        frases = [f"falta el espacio: «{par}»" for par in _espacios_faltantes(placa, mailing)[:2]]
        if not frases:
            frases.append("sobra un espacio" if len(placa) > len(mailing) else "falta un espacio")
        for palabra in _cambios_de_caja(placa, mailing)[:1]:
            caja = "minúscula" if palabra.islower() else "mayúscula"
            frases.append(f"«{palabra}» va en {caja}")
        return _mayuscula_inicial(_unir(frases))

    # Lo mismo, pero en otro lugar (el clásico: el punto se corrió)
    if sobra and falta and "".join(sobra).strip() == "".join(falta).strip():
        que = _describir(sobra)
        donde_va = _palabra_antes(mailing, pos_falta[0][1])
        donde_esta = _palabra_antes(placa, pos_sobra[0][1])
        if donde_va and donde_esta:
            return f"{_mayuscula_inicial(que)} va después de «{donde_va}», no de «{donde_esta}»"
        return f"{_mayuscula_inicial(que)} está en otro lugar"

    if sobra and not falta:
        return f"Sobra {_describir(sobra)}: sacalo"
    if falta and not sobra:
        return f"Falta {_describir(falta)}: agregalo"

    # Las dos cosas: si es poco se dice; si no, se da el texto final
    if sum(len(t.strip()) for t in sobra + falta) <= 12:
        return f"Sacá {_describir(sobra)} y agregá {_describir(falta)}"
    return f"Escribilo así: «{mailing}»"


# ── Nombres para una persona ──────────────────────────────────────────────

_CAMPOS = {
    "descripcion": "Descripción",
    "precio_anterior": "Precio anterior (tachado)",
    "precio_anterior_tachado": "El precio anterior va tachado",
    "mecanica": "Mecánica (2x$75, 4x3…)",
    "oferta_encabezado": "Texto arriba del precio",
    "oferta_precio": "Precio de oferta",
    "oferta_pie": "Texto abajo del precio",
    "fecha": "Fecha de la campaña",
    "legal_bases": "Legal: bases y condiciones",
    "legal_alcohol": "Legal: alcohol",
    "logo_campana": "Logo de la campaña",
    "isotipo": "Isotipo de la tienda",
    "imagen_producto": "Foto del producto",
    "imagen_coincide": "La foto no parece del producto",
    "cta": "CTA",
    "sin_match": "No está en el mailing",
    "lectura": "No se pudo leer",
}


def nombre_campo(campo: str) -> str:
    return _CAMPOS.get(campo, campo.replace("_", " ").capitalize())


def etiquetas(nombres: list[str]) -> dict[str, str]:
    """El nombre corto de cada placa: lo que las distingue entre sí.

    Las placas de una campaña suelen compartir un prefijo largo
    ("TI-Los Rompes del Finde-RRSS 17-20_10 copia.jpg"), que no entra debajo de
    una miniatura y no dice nada. Se saca el prefijo común --cortando en un
    separador, para no llevarse un dígito del número-- y la extensión: queda
    "10 copia", que es como el equipo las nombra."""
    tallos = {n: re.sub(r"\.[A-Za-z0-9]+$", "", n) for n in nombres}
    if len(set(tallos.values())) < 2:
        return tallos
    prefijo = os.path.commonprefix(list(tallos.values()))
    corte = max(prefijo.rfind(s) for s in "_- ") + 1
    return {n: (t[corte:].strip() or t) for n, t in tallos.items()}
