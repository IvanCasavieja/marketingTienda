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

La fuente contra la que se compara puede ser un mailing leído por CatTi o una
PLANILLA (ver rrss/planilla.py). Este módulo no sabe de dónde salió el dict:
lo único que cambia es lo que la fuente PUEDE exigir, y eso viaja en el propio
dict -- ver `reglas_de_la_fuente`.
"""
import math
import re
import unicodedata

from rapidfuzz import fuzz

from app.services.rrss import imagenes

# CUÁNDO DOS DESCRIPCIONES SON EL MISMO PRODUCTO
#
# Lo que separa un acierto de una acusación equivocada NO es el umbral: es el
# MARGEN entre la primera candidata y la segunda. Medido con este mismo
# `puntaje_producto` sobre los casos que aparecieron de verdad:
#
#   caso                                           mejor  segundo  margen
#   PATRICIA: la placa es la botella y dice "lata"  98,37    93,33    5,04
#   WARSTEINER botella contra WARSTEINER lata      110,00   110,00    0,00
#   Galletitas MARIA (la fila correcta existe)     110,00    94,44   15,56
#   Galletitas MARIA (la fila correcta NO existe)   94,44    39,13   55,31
#   Bondiola contra Chorizo TI                     110,00    92,35   17,65
#   Suprema contra Chorizo (el peor falso: 81)      80,95     0,00   80,95
#   Shampoo que no está en la campaña               35,48    33,33    2,15
#
# Con un umbral de 90 y un margen único de 8, el caso PATRICIA --el que preguntó
# Ivan, y el más importante: la descripción es JUSTO lo que está mal-- se perdía.
# Emparejaba bien con el umbral viejo (72) y decía exactamente qué corregir; con
# 90/8 se encogía de hombros. Y bajar el margen a 0 devolvía el problema del otro
# lado: WARSTEINER botella y lata EMPATAN en 110,00 y ahí elegir es tirar una
# moneda, que es lo que Ivan pidió que no se hiciera.
#
# Por eso son TRES números y no dos, y cada uno resuelve una pregunta distinta:
#
#   UMBRAL_EMPAREJAR (90)  ¿se parece lo suficiente como para ser esta fila?
#                          Por debajo no hay pareja: "ninguna". Queda 9 puntos
#                          por encima del peor falso positivo medido (81,0).
#   MARGEN_EMPATE (1)      ¿hay una MEJOR? Con dos filas a menos de un punto no
#                          la hay: sin pareja, "ambiguo", y que lo mire una
#                          persona. WARSTEINER cae acá (margen 0,00).
#   PARECIDO_SEGURO (95)   ¿la calza del todo? Es sobre la descripción SOLA (sin
#                          el empujón del precio). El peor acierto real sacó
#                          98,2; el peor falso, 81,0. Por debajo de 95 se
#                          empareja IGUAL pero se marca la duda y se muestran las
#                          candidatas con su puntaje.
#   MARGEN_DUDA (8)        ¿había otra que se le parecía casi igual? También se
#                          empareja y también se marca la duda.
#
# Así el caso PATRICIA vuelve a emparejar (98,37 > 90, margen 5,04 > 1) y encima
# sale marcado como dudoso (parecido de la descripción sola: 88,4 < 95), con la
# segunda candidata y su puntaje a la vista. Y el falso de Galletitas VAINILLA
# (94,44, sin la fila correcta en la planilla) --que con cualquier umbral y
# cualquier margen emparejaba igual-- ahora al menos avisa que no está seguro,
# en vez de mandar a reescribir la placa con la confianza de un acierto.
UMBRAL_EMPAREJAR = 90
MARGEN_EMPATE = 1.0
MARGEN_DUDA = 8
PARECIDO_SEGURO = 95

# Nombre viejo, que era el margen único. Queda para no romper a nadie que lo
# importe; el que manda ahora es MARGEN_DUDA.
MARGEN_AMBIGUEDAD = MARGEN_DUDA

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
# Los que una segunda lectura puede confirmar o desmentir: los de texto y si el
# precio va tachado. El tachado es un booleano y quedaba afuera, así que era
# el ÚNICO error que se acusaba con una sola lectura: en la corrida real del
# 22/09/2026 una placa 9:16 salió acusada de "sin tachar" por una línea de un
# píxel que la lectura no vio, y nada la volvió a mirar.
CAMPOS_CONFIRMABLES = CAMPOS_DE_TEXTO | {"precio_anterior_tachado"}


def texto_tachado(tachado: bool) -> str:
    """Cómo se escribe el booleano del tachado en una fila: es lo que se compara
    entre lecturas y lo que se le muestra a la persona."""
    return "tachado" if tachado else "sin tachar"

# Los que son plata. Contra un mailing se comparan como cualquier otro texto;
# contra una planilla, por importe (ver `_comparar_precio`).
CAMPOS_DE_PRECIO = {"precio_anterior", "oferta_precio"}


# --------------------------------------------------------------------------
# Emparejar placa <-> producto del mailing
# --------------------------------------------------------------------------

# El espacio entre el número y la unidad. En 32 de las 67 placas reales de
# producción la ÚNICA diferencia entre la descripción de la placa y la del
# mailing era ese espacio ("300g" contra "300 g", "710ml." contra "710 ml",
# "1.7L" contra "1.7 L"), y en una planilla convive escrito de las dos formas:
# el catálogo de producción tiene "Jugo BAGGIO manzana roja. 1 l" al lado de
# "Chupetín PICO DULCE. 14g". Pegarlos SOLO acá sube el peor acierto real de
# 98,2 a 100. Va únicamente en la clave de emparejar: si esta normalización se
# filtrara a `_comparar_texto`, el motor dejaría de ver el error más frecuente
# que encuentra, que es exactamente ese espacio.
_UNIDAD_PEGADA = re.compile(r"(\d) (g|kg|mg|ml|l|cc|mm|cm|m|w|kw|un|u)\b")


def clave(texto: str) -> str:
    """Forma de comparar descripciones para EMPAREJAR (no para validar): sin
    tildes, sin mayúsculas ni puntuación, y con la unidad pegada al número."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    limpio = " ".join(re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).split())
    return _UNIDAD_PEGADA.sub(r"\1\2", limpio)


# --------------------------------------------------------------------------
# Precios
# --------------------------------------------------------------------------

_RE_NUMERO = re.compile(r"\d[\d.,]*")


def importe(texto: str) -> float | None:
    """El número que hay adentro de un texto de precio, leído a la uruguaya.
    None si no hay ninguno.

    Hace falta porque una planilla trae el precio como NÚMERO y la placa como
    TEXTO impreso, y ahí lo que se compara es el importe (ver
    `reglas_de_la_fuente`). No sirve `formatters.parse_price_raw`: su regex
    exige que el texto EMPIECE con un dígito, y "U$S149" empieza con una U.

    La coma es siempre decimal; el punto es separador de miles salvo que lo que
    venga después no sean tres dígitos ("1.7 L" es uno coma siete)."""
    if not texto:
        return None
    m = _RE_NUMERO.search(str(texto))
    if not m:
        return None
    crudo = m.group(0).rstrip(".,")
    if "," in crudo:
        crudo = crudo.replace(".", "").replace(",", ".")
    elif crudo.count(".") == 1 and len(crudo.rsplit(".", 1)[1]) == 3:
        crudo = crudo.replace(".", "")   # 1.090 son mil noventa
    elif crudo.count(".") > 1:
        crudo = crudo.replace(".", "")
    try:
        return float(crudo)
    except ValueError:
        return None


def mismo_importe(a: str, b: str) -> bool:
    """Dos textos de precio que valen lo mismo. Medio centavo de tolerancia:
    los precios son plata, no medidas.

    Ojo: esto es el NÚMERO. La moneda se compara aparte (ver `moneda`), porque
    149 pesos y 149 dólares tienen el mismo número y no son lo mismo."""
    va, vb = importe(a), importe(b)
    return va is not None and vb is not None and abs(va - vb) < 0.005


# Cómo se escribe cada moneda en una planilla de gestión y en una placa. El
# listado trae la columna MONEDA con "$" o "U$S"; el diseñador escribe "U$S",
# "US$" o "u$s" según el día.
_MONEDAS: dict[str, str] = {
    "$": "UYU", "$u": "UYU", "u$": "USD", "u$s": "USD", "us$": "USD",
    "usd": "USD", "uss": "USD", "dolares": "USD", "€": "EUR", "eur": "EUR",
}
# Lo que rodea al número y no es la moneda: "Precio", "desde", "c/u".
_RE_ANTES_DEL_NUMERO = re.compile(r"^(.*?)\d")


def moneda(texto: str) -> str:
    """'UYU' | 'USD' | ... o '' si el texto no trae ninguna marca reconocible.

    Existe porque la planilla TRAE la columna MONEDA --se lee desde el primer
    día-- pero solo se usaba para pintar el texto: una placa que decía "$149"
    contra una fila en "U$S149" pasaba como correcta, porque lo único que se
    comparaba era el 149."""
    m = _RE_ANTES_DEL_NUMERO.match(texto or "")
    if not m:
        return ""
    marca = re.sub(r"[\s.]+", "", m.group(1)).lower()
    return _MONEDAS.get(marca, "")


def misma_moneda(a: str, b: str) -> bool:
    """Si alguno de los dos lados no trae una marca reconocible NO se afirma
    nada: no se puede acusar a una placa de estar en la moneda equivocada
    cuando no se sabe en cuál está."""
    ma, mb = moneda(a), moneda(b)
    return not ma or not mb or ma == mb


_NOMBRE_MONEDA = {"UYU": "pesos", "USD": "dólares", "EUR": "euros"}


def nombre_moneda(codigo: str) -> str:
    return _NOMBRE_MONEDA.get(codigo, codigo)


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def parecido_descripcion(placa: dict, item: dict) -> float:
    """Cuánto se parecen las DESCRIPCIONES solas (0 a 100), sin el empujón de
    los precios. Es lo que decide si el emparejamiento es seguro o dudoso: dos
    productos hermanos que comparten el precio se van arriba de 100 en
    `puntaje_producto` aunque la descripción los separe."""
    return fuzz.token_set_ratio(clave(placa["descripcion"]), clave(item["descripcion"]))


def puntaje_producto(placa: dict, item: dict) -> float:
    """Qué tan probable es que `placa` sea el producto `item` (0 a ~115).

    Manda la descripción; el precio de oferta desempata entre productos de
    nombre parecido (dos cervezas de 710 ml), sin poder por sí solo
    convertir en pareja a dos productos que no se parecen en nada."""
    base = parecido_descripcion(placa, item)
    if _mismo_precio(placa["oferta_precio"], item["oferta_precio"]):
        base += 10
    if _mismo_precio(placa["precio_anterior"], item["precio_anterior"]):
        base += 5
    return base


def _mismo_precio(a: str, b: str) -> bool:
    """Para desempatar alcanza con que valgan lo mismo: contra una planilla el
    precio viene de un número y se escribe canónico ("$74,50"), y la placa puede
    decir "$74,5". Si alguno de los dos no trae un número se cae a comparar los
    dígitos, que es como venía siendo."""
    if importe(a) is not None and importe(b) is not None:
        return mismo_importe(a, b)
    return bool(_digitos(a)) and _digitos(a) == _digitos(b)


def emparejamiento(placa: dict, productos: list[dict]) -> dict:
    """Con qué fila se emparejó esta placa, y con cuánta confianza.

    Devuelve {indice, puntaje, segundo, margen, parecido, duda, motivo_duda,
    motivo_sin_pareja}. `indice` es None solo en dos casos, y son los dos que
    Ivan pidió que se vieran por separado:
      - "ninguna": no hay ninguna fila que se parezca lo suficiente.
      - "ambiguo": hay DOS que empatan (a menos de MARGEN_EMPATE) y elegir sería
        tirar una moneda.
    Cuando hay pareja pero el motor no está seguro, `duda` viene en True con el
    motivo: se empareja igual --para no perder el diagnóstico, que es lo caro--
    y la duda se MUESTRA con las candidatas y sus puntajes. Ver el comentario de
    los umbrales, arriba."""
    vacio = {
        "indice": None, "puntaje": 0.0, "segundo": None, "margen": None,
        "parecido": 0.0, "duda": False, "motivo_duda": None, "motivo_sin_pareja": "ninguna",
    }
    if not productos:
        return vacio
    puntajes = sorted(
        ((puntaje_producto(placa, p), i) for i, p in enumerate(productos)), reverse=True,
    )
    mejor, idx = puntajes[0]
    segundo = puntajes[1][0] if len(puntajes) > 1 else None
    margen = None if segundo is None else mejor - segundo
    parecido = parecido_descripcion(placa, productos[idx])
    base = {
        "indice": idx, "puntaje": mejor, "segundo": segundo, "margen": margen,
        "parecido": parecido, "duda": False, "motivo_duda": None, "motivo_sin_pareja": None,
    }
    if mejor < UMBRAL_EMPAREJAR:
        return {**base, "indice": None, "motivo_sin_pareja": "ninguna"}
    if margen is not None and margen < MARGEN_EMPATE:
        return {**base, "indice": None, "motivo_sin_pareja": "ambiguo"}
    if margen is not None and margen < MARGEN_DUDA:
        return {**base, "duda": True, "motivo_duda": "otra_parecida"}
    if parecido < PARECIDO_SEGURO:
        return {**base, "duda": True, "motivo_duda": "no_la_calza"}
    return base


def emparejar(placa: dict, productos: list[dict]) -> tuple[int | None, float]:
    """(índice del producto del mailing, puntaje) o (None, mejor_puntaje) si no
    hay pareja. La cara corta de `emparejamiento`, para quien no necesita saber
    con cuánta confianza fue."""
    par = emparejamiento(placa, productos)
    return par["indice"], par["puntaje"]


def candidatos(placa: dict, productos: list[dict], cuantos: int = 3) -> list[dict]:
    """Las filas que MÁS se parecieron, con su puntaje. Es la prueba de un
    "sin pareja": sin esto, no encontrar el producto es una acusación sin
    pruebas, y la persona no tiene cómo saber si el problema es que la placa
    no está en la campaña o que la descripción está tan mal escrita que no la
    reconoció nadie."""
    puntajes = sorted(
        ((puntaje_producto(placa, p), i) for i, p in enumerate(productos)), reverse=True,
    )[:cuantos]
    return [
        {"indice": i, "descripcion": productos[i]["descripcion"], "puntaje": round(p, 1)}
        for p, i in puntajes
    ]


def motivo_sin_pareja(candidatas: list[dict]) -> str:
    """'ambiguo' (dos filas EMPATAN y elegir sería tirar una moneda) o 'ninguna'
    (no hay ninguna que se parezca lo suficiente). Son los dos casos que Ivan
    pidió que fueran visibles, y hasta ahora los dos se veían igual.

    Desde que el margen se partió en dos (ver los umbrales, arriba), "ambiguo"
    quedó para el empate de verdad: cuando hay una mejor aunque sea por poco, se
    empareja con ella y la duda se muestra al lado. Lo dice `emparejamiento`;
    esto lo deduce de las candidatas, para quien solo tiene eso a mano."""
    if not candidatas:
        return "ninguna"
    if candidatas[0]["puntaje"] >= UMBRAL_EMPAREJAR:
        return "ambiguo"
    return "ninguna"


# --------------------------------------------------------------------------
# Qué puede exigir la fuente
# --------------------------------------------------------------------------

CAMPOS_TODOS: tuple[str, ...] = tuple(c for c, _ in CAMPOS_PRODUCTO)


def reglas_de_la_fuente(mailing: dict) -> dict:
    """Qué campos puede exigir esta fuente y cómo se comparan los precios.

    Un mailing dicta TODO y letra por letra: del otro lado hay un texto
    impreso, y "$1090" contra "$1.090" son dos decisiones distintas.

    Una planilla dicta solo las columnas que trae (ver rrss/planilla.py) y los
    precios POR IMPORTE: una celda no trae un texto, trae un número, así que
    exigir un formato sería inventar una regla que nadie escribió. Lo que la
    planilla no trae no se compara -- y se dice cuál, no se esconde."""
    if mailing.get("origen") == "planilla":
        return {
            "campos": tuple(mailing.get("campos") or ()), "precios": "importe",
            # Las columnas de precio en las que la planilla escribió lo que
            # acompaña al número (ver planilla.leer y `_comparar_precio`).
            "colas": tuple(mailing.get("precios_con_cola") or ()),
        }
    return {"campos": CAMPOS_TODOS, "precios": "texto", "colas": ()}


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


def cola_del_precio(texto: str) -> str:
    """Lo que acompaña al número en una línea de precio: "unidad" en "$340
    unidad", "c/u" en "$99 c/u". Cadena vacía si no hay nada después del número."""
    m = _RE_NUMERO.search(texto or "")
    return (texto or "")[m.end():].strip() if m else ""


def _comparar_precio(campo: str, etiqueta: str, placa: str, esperado: str,
                     cola_dictada: bool = False) -> dict | None:
    """El precio contra una PLANILLA: vale lo que vale, no cómo está escrito.

    La planilla trae un número; el símbolo, el separador de miles y si los
    centavos van o no son decisiones del diseño, no de la planilla. Lo que sí
    se puede afirmar es el importe, y eso es lo que se compara. El texto que se
    muestra como referencia es el canónico (el mismo formato con el que se
    imprimen las cenefas).

    `cola_dictada`: la planilla escribió, en alguna fila de esa columna, lo que
    acompaña al precio ("$340 unidad"). Ahí la columna deja de ser un número y
    pasa a dictar también la cola: una fila que dice "$171" a secas está
    diciendo que NO va "unidad", igual que lo diría un mailing. Sin eso, la
    misma campaña validada contra el PDF y contra su planilla daba resultados
    distintos (22/09/2026: el "unidad" de la Stella salía solo en el PDF)."""
    if not placa and not esperado:
        return None
    if not esperado:
        return None  # la columna existe pero esta fila no trae precio: no hay qué exigir
    if not placa:
        return _fila(campo, etiqueta, "producto", "", esperado, "falta_en_placa", "error")
    if not misma_moneda(placa, esperado):
        # El importe puede coincidir y estar igual de mal: 149 pesos no son 149
        # dólares. La columna MONEDA de la planilla se leía desde el primer día,
        # pero solo para pintar el texto.
        return _fila(
            campo, etiqueta, "producto", placa, esperado, "diferente", "error",
            f"La planilla dice {nombre_moneda(moneda(esperado))} y la placa "
            f"{nombre_moneda(moneda(placa))}",
        )
    if not mismo_importe(placa, esperado):
        return _fila(
            campo, etiqueta, "producto", placa, esperado, "diferente", "error",
            "La planilla trae un número, no un texto: lo que se compara es el importe",
        )
    if cola_dictada and cola_del_precio(placa) != cola_del_precio(esperado):
        # Mismo importe, pero lo que lo acompaña no es lo que la planilla
        # escribió. Va como "diferente" y no como sobra/falta para que la
        # instrucción diga "Sobra «unidad»" y no "Sobra «$171 unidad»".
        return _fila(
            campo, etiqueta, "producto", placa, esperado, "diferente", "error",
            "El importe es el mismo; lo que cambia es lo que acompaña al precio",
        )
    return _fila(campo, etiqueta, "producto", placa, esperado, "ok", None)


def comparar_producto(placa: dict, item: dict, reglas: dict | None = None) -> list[dict]:
    """El producto de la placa contra el de la fuente, campo por campo.

    `reglas` dice qué campos dicta la fuente y cómo se comparan los precios
    (ver `reglas_de_la_fuente`). Sin reglas se compara todo y por texto, que es
    lo que hace un mailing."""
    reglas = reglas or {"campos": CAMPOS_TODOS, "precios": "texto"}
    campos = set(reglas["campos"])
    por_importe = reglas["precios"] == "importe"
    con_cola = set(reglas.get("colas") or ())
    filas = []
    for campo, etiqueta in CAMPOS_PRODUCTO:
        if campo not in campos:
            # La fuente no dice nada de este campo. No se compara y NO se
            # inventa: se lista aparte (planilla.campos_que_no_dicta) para que
            # se vea que quedó afuera en vez de dar por bueno lo que diga.
            continue
        if campo == "precio_anterior_tachado":
            # Tachado o no solo tiene sentido si hay un precio de los dos lados.
            if placa["precio_anterior"] and item["precio_anterior"]:
                p, m = placa[campo], item[campo]
                filas.append(_fila(
                    campo, etiqueta, "producto", texto_tachado(p), texto_tachado(m),
                    "ok" if p == m else "diferente", None if p == m else "error",
                ))
            continue
        if por_importe and campo in CAMPOS_DE_PRECIO:
            fila = _comparar_precio(campo, etiqueta, placa[campo], item[campo], cola_dictada=campo in con_cola)
        else:
            fila = _comparar_texto(campo, etiqueta, "producto", placa[campo], item[campo])
        if fila:
            filas.append(fila)
    return filas


def comparar_elementos(placa: dict, mailing: dict, config: dict, es_alcohol: bool) -> list[dict]:
    """Lo que no es el producto: fecha, logo, isotipo, foto, leyendas y CTA."""
    filas: list[dict] = []

    # Fecha: la que se escribió en la pantalla de carga si la hay, si no la que
    # dice la fuente. Mismo orden que la leyenda de alcohol, unas líneas más
    # abajo, y por el mismo motivo: una planilla no trae el texto de vigencia
    # como va impreso ("DEL JUEVES 17 AL DOMINGO 20 DE SETIEMBRE"), trae dos
    # fechas sueltas, y componerlo sería inventarle una forma. Sin ninguna de
    # las dos no hay contra qué comparar y no se marca nada.
    esperada = (config.get("fecha") or "").strip() or mailing.get("fecha", "")
    if esperada:
        fila = _comparar_texto("fecha", "Fecha de la campaña", "placa", placa["fecha"], esperada)
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


def _fila_de_duda(par: dict, item: dict, placa_desc: str) -> dict:
    """El aviso de "la emparejé, pero no estoy del todo seguro".

    Es la mitad que faltaba de la decisión de emparejar igual en vez de
    encogerse de hombros: si se empareja con duda y la duda no se ve, se pasó de
    no dar diagnóstico a dar uno falso con cara de certeza."""
    if par["motivo_duda"] == "otra_parecida":
        nota = (
            f"Hay otra fila que se le parece casi igual ({par['puntaje']:.1f} contra "
            f"{par['segundo']:.1f}): confirmá que sea esta."
        )
    else:
        nota = (
            f"Ninguna fila la calza del todo: esta es la que más se le parece "
            f"({par['puntaje']:.1f}). Confirmá que sea esta antes de corregir nada."
        )
    return _fila(
        "emparejamiento", "Con qué fila la emparejé", "producto",
        placa_desc, item["descripcion"], "revisar", "aviso", nota,
    )


def comparar_placa(placa: dict, mailing: dict, config: dict,
                   par: dict | None = None) -> tuple[int | None, float, list[dict]]:
    """Todo junto: empareja la placa con su producto y arma las filas.
    Devuelve (índice_en_mailing | None, puntaje, filas).

    `par` es el emparejamiento ya calculado (ver `emparejamiento`), para que el
    que necesita el detalle --con cuánta confianza fue, cuál era la segunda-- no
    tenga que puntuar todo el mailing dos veces."""
    par = par or emparejamiento(placa["producto"], mailing["productos"])
    idx, puntaje = par["indice"], par["puntaje"]
    filas: list[dict] = []
    es_alcohol = placa["producto"]["es_alcohol"]
    if idx is not None:
        item = mailing["productos"][idx]
        if par["duda"]:
            filas.append(_fila_de_duda(par, item, placa["producto"]["descripcion"]))
        filas += comparar_producto(placa["producto"], item, reglas_de_la_fuente(mailing))
        es_alcohol = es_alcohol or item["es_alcohol"]
    filas += comparar_elementos(placa, mailing, config, es_alcohol)
    return idx, puntaje, filas


def confirmar_con_segunda_lectura(filas: list[dict], segunda: dict) -> list[dict]:
    """Un error de texto solo se sostiene si una SEGUNDA lectura de la misma
    placa lee lo mismo. Si CatTi lee distinto la segunda vez, lo que se
    "encontró" pudo ser un error de lectura y no de la placa: se degrada a un
    aviso para que una persona lo mire, en vez de acusar a la placa.

    `segunda` es {campo: valor_leído} de la segunda lectura (ver `campos_leidos`)."""
    for fila in filas:
        if fila["severidad"] != "error" or fila["campo"] not in CAMPOS_CONFIRMABLES:
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


def confirmar_con_relectura_de_la_fuente(filas: list[dict], releido: dict, fuente: str = "el mailing") -> list[dict]:
    """El espejo de `confirmar_con_segunda_lectura`, del lado del MAILING.

    Hasta el 22/09/2026 la segunda lectura existía solo para la placa: el
    mailing se leía UNA vez, de la página entera, y nunca se confirmaba. Con
    la misma campaña leída tres veces, la Jarra INHAUS salió '$1090' / '$799',
    '$1.090' / '$799' y '$1090' / '$7799': dos de las tres corridas acusaron a
    las tres placas de la Jarra de un error de precio que la placa no tenía.
    Un error de lectura del mailing acusa igual que uno de la placa, y es peor,
    porque el diseñador va a "corregir" la placa hacia algo que el mailing no
    dice.

    `releido` es el producto leído POR SEGUNDA VEZ, del recorte ampliado del
    mailing (ver catti.leer_producto_del_mailing). Para cada fila en error de
    un campo de texto:
      - si la relectura dice lo mismo que la PLACA, el error cae: la placa se
        leyó dos veces igual y el recorte ampliado del mailing --que se lee
        mejor que la página entera-- coincide con ella. Son tres lecturas
        contra una. La fila queda en "ok" con la nota de lo que pasó.
      - si la relectura repite la primera lectura del mailing, el error se
        sostiene.
      - si dice una tercera cosa, no se sabe qué dice el mailing: baja a aviso
        para que lo mire una persona, igual que del lado de la placa."""
    for fila in filas:
        if fila["severidad"] != "error" or fila["campo"] not in CAMPOS_CONFIRMABLES or fila["campo"] not in releido:
            continue
        primera, segunda = fila["mailing"] or "", releido.get(fila["campo"]) or ""
        if segunda == primera:
            continue
        if segunda == (fila["placa"] or ""):
            fila["estado"] = "ok"
            fila["severidad"] = None
            fila["nota"] = (
                f"Leí {fuente} dos veces: la página entera decía {primera!r} y el recorte ampliado "
                f"dice {segunda!r}, igual que la placa. Me quedo con el recorte."
            )
            fila["mailing"] = segunda
            continue
        fila["estado"] = "revisar"
        fila["severidad"] = "aviso"
        fila["nota"] = (
            f"CatTi leyó distinto {fuente} en dos lecturas ({primera!r} y {segunda!r}): "
            f"confirmalo mirando {fuente}"
        )
    return filas


def campos_del_producto(producto: dict) -> dict:
    """Los campos confirmables de UN producto leído, como texto: el tachado va
    como "tachado" / "sin tachar", igual que en la fila que lo compara."""
    salida = {c: producto[c] for c in CAMPOS_DE_TEXTO if c in producto}
    if "precio_anterior_tachado" in producto:
        salida["precio_anterior_tachado"] = texto_tachado(bool(producto["precio_anterior_tachado"]))
    return salida


def campos_leidos(placa: dict) -> dict:
    """Los campos confirmables de una lectura de placa, aplanados: lo que se
    compara entre la primera y la segunda lectura."""
    salida = campos_del_producto(placa["producto"])
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

    # Las filas de la fuente que NINGUNA placa reclamó. Se venían contando
    # (productos_mailing contra productos_con_placa) pero no se decía CUÁLES, y
    # sin el nombre el número no sirve para nada. Con una planilla es un
    # hallazgo de primera: "falta la placa de este producto".
    con_placa = {g["match_indice"] for g in grupos if g["match_indice"] is not None}
    sin_placa = [
        {"indice": i, "descripcion": p["descripcion"], "fila": (p.get("fila") or {}).get("numero")}
        for i, p in enumerate(productos_mailing) if i not in con_placa
    ]

    return {
        "grupos": salida_grupos,
        "formatos_esperados": esperados,
        "cta": _chequeo_cta(imgs),
        "productos_mailing": len(productos_mailing),
        "productos_con_placa": len(con_placa),
        "productos_sin_placa": sin_placa,
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
