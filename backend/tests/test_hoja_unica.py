"""La red que evita que el PAPEL vuelva a decidirse en dos lugares.

QUE PASO (18/09/2026). Ivan exporto una 3xA4 SOLO X 25 y el texto salio
impreso fuera de la hoja mientras el preview se lo mostraba adentro. La cuarta
vez que se le decia "ahora si el preview es honesto" y encontraba que no.

No era un error de medicion: era el TAMANO DE LA HOJA. En Canvas.tsx habia un
``Math.max(ancho_de_la_hoja, ...borde_derecho_de_cada_cuadro)``. O sea: si un
cuadro se salia del papel, en vez de mostrarlo saliendo, SE AGRANDABA EL PAPEL
hasta que entrara. El editor le mostraba "A4 24.588x29.7 cm" -- 24,588 es
exactamente el borde derecho del cuadro que se iba 3,6 cm afuera. 11 de las 23
plantillas de produccion recibian una hoja inflada en silencio, y otras 3 ni
eso: lo que se salia quedaba fuera del lienzo, invisible.

Abajo de eso habia un problema mas viejo: el tamano de hoja estaba escrito a
mano en CINCO tablas (Canvas.FORMAT_DIMS, layout_engine.FORMATS,
component_renderer.FORMAT_SLIDES, pptx_importer._FORMATS_DIM y las etiquetas
del panel de importacion) y tres de los seis formatos tenian numeros DISTINTOS
segun a cual se le preguntara, porque unas decian el PAPEL que sale de la
impresora y otras la CELDA que ocupa una cenefa adentro de el, y las dos cosas
se llamaban igual. Y la orientacion tambien estaba mal: Ivan lo dijo el
22/09/2026 --"si te imaginas que la 6xA4 esta en vertical, nunca van a salir
bien"-- y de ahi salia que una A4 apaisada de 29,7x21 se detectara como "a5".

Ivan: "el archivo de reglas tiene que ser UNO SOLO, sino nos va a pasar de
poner una regla en algun lado y luego olvidarnos de cambiarla en el otro".

Ese archivo es ``backend/app/data/formatos_de_hoja.json``. Este test hace DOS
cosas, y las dos son barridos de CARPETA y no listas de archivos -- una lista
se desactualiza y el archivo nuevo que nadie sumo es justo por donde se cuela
el proximo bug (ya paso con ``pptx_importer`` y el tamano por defecto, ver
test_factor_voladita.py):

  1. PROHIBE QUE VUELVA A APARECER UN NUMERO DE HOJA ESCRITO A MANO en los dos
     motores (el exportador en Python, el preview en TypeScript).
  2. PROHIBE QUE EL TAMANO DE LA HOJA SE DERIVE DEL CONTENIDO -- o sea que
     vuelva a aparecer un maximo entre la hoja y los bordes de los cuadros.

SI UN TEST DE ACA FALLA no hay que "arreglar el test": hay que sacar el numero
del codigo y leerlo del archivo unico, o dejar de deducir el papel del diseno.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.services.cenefas.formatos_de_hoja import (
    CRUDO, FORMATOS, _RUTA, celda_cm, hoja_de_definicion, misma_hoja, papel_cm,
)

# backend/tests/ -> backend/ -> raiz del repo
_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _RAIZ / "backend"
_FRONTEND = _RAIZ / "frontend"

# Los dos modulos que LEEN el archivo unico y lo exponen: ahi los numeros (y la
# palabra "papel") aparecen legitimamente. Son los unicos dos excluidos, y son
# los canos, no la fuente -- de hecho el test de mas abajo comprueba que ni
# siquiera ellos tengan un valor propio.
_EXCLUIDOS = {"formatos_de_hoja.py", "formatosDeHoja.ts"}


def _barrer(*carpetas_y_sufijos):
    salida = []
    for carpeta, sufijos in carpetas_y_sufijos:
        if not carpeta.exists():
            continue
        for ruta in sorted(carpeta.rglob("*")):
            if ruta.suffix in sufijos and ruta.name not in _EXCLUIDOS:
                salida.append(ruta)
    return salida


_MOTOR_PYTHON = _barrer(
    (_BACKEND / "app" / "services" / "cenefas", {".py"}),
    (_BACKEND / "app" / "api" / "routes", {".py"}),
    (_BACKEND / "scripts", {".py"}),
)
_MOTOR_TS = _barrer(
    (_FRONTEND / "lib" / "cenefas", {".ts", ".tsx"}),
    (_FRONTEND / "components" / "cenefas", {".ts", ".tsx"}),
    (_FRONTEND / "app", {".ts", ".tsx"}),
    (_FRONTEND / "store", {".ts", ".tsx"}),
)
assert _MOTOR_PYTHON, "el barrido no encontro ningun .py: se movio la carpeta?"
assert _MOTOR_TS, "el barrido no encontro ningun .ts: se movio la carpeta?"


# ---------------------------------------------------------------------------
# 1. El archivo unico tiene todo lo que el codigo consume, y esta explicado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt_id", sorted(FORMATOS))
def test_cada_formato_declara_papel_celda_y_porque(fmt_id: str) -> None:
    fmt = FORMATOS[fmt_id]
    for clave in ("papel_cm", "celda_cm"):
        medida = fmt.get(clave)
        assert isinstance(medida, dict), (
            f"el formato '{fmt_id}' no declara '{clave}' en {_RUTA.name}."
        )
        for eje in ("ancho", "alto"):
            assert isinstance(medida.get(eje), (int, float)) and medida[eje] > 0, (
                f"{fmt_id}.{clave}.{eje} no es una medida."
            )
    # El PAPEL nunca puede ser mas chico que la CELDA que va adentro: si pasa,
    # una de las dos esta cargada como la otra -- que es exactamente la
    # confusion que teniamos cuando las dos se llamaban igual.
    assert fmt["papel_cm"]["ancho"] >= fmt["celda_cm"]["ancho"] - 1e-9, fmt_id
    assert fmt["papel_cm"]["alto"] >= fmt["celda_cm"]["alto"] - 1e-9, fmt_id
    # El porque va en el archivo y no en un comentario del codigo, por la misma
    # razon que el numero: si no, la explicacion queda duplicada igual.
    for campo in ("que_es", "porque"):
        texto = fmt.get(campo)
        assert isinstance(texto, str) and len(texto) > 40, (
            f"el formato '{fmt_id}' no explica '{campo}'. Ivan tiene que poder "
            f"leer que es y de donde salio sin ser programador."
        )


@pytest.mark.parametrize("fmt_id", sorted(FORMATOS))
def test_la_grilla_llena_el_papel(fmt_id: str) -> None:
    """slot_cols x slot_rows celdas tienen que dar el papel entero.

    Es la comprobacion que hubiera cazado el error de la 6xA4 sin que nadie
    tuviera que mirar un PPTX: la tabla vieja decia papel 21x29,7 (A4 parada)
    con celda de 7x14,85 en 3 columnas por 2 filas, y 3x7 = 21 pero 2x14,85 =
    29,7 -- cerraba de casualidad porque estaban MAL las dos cosas a la vez, la
    orientacion del papel y la de la grilla. Con la hoja acostada (29,7x21) y
    la grilla de 2x3 cierra igual, y ahora ademas coincide con lo que hay en
    produccion. Que cierre no prueba que este bien, pero que NO cierre prueba
    que esta mal, y eso es lo que hay que atajar.
    """
    fmt = FORMATOS[fmt_id]
    cols = int(fmt.get("slot_cols", 1))
    filas = int(fmt.get("slot_rows", 1))
    assert cols * filas == int(fmt["slots"]), (
        f"'{fmt_id}' dice {fmt['slots']} cenefas pero su grilla es "
        f"{cols}x{filas} = {cols * filas}."
    )
    ancho = fmt["celda_cm"]["ancho"] * cols
    alto = fmt["celda_cm"]["alto"] * filas
    assert misma_hoja((ancho, alto), (fmt["papel_cm"]["ancho"], fmt["papel_cm"]["alto"])), (
        f"'{fmt_id}': {cols} columnas x {filas} filas de celdas de "
        f"{fmt['celda_cm']['ancho']}x{fmt['celda_cm']['alto']} dan "
        f"{ancho}x{alto} cm, y el papel declarado es "
        f"{fmt['papel_cm']['ancho']}x{fmt['papel_cm']['alto']}. Una de las dos "
        f"medidas esta mal, o la orientacion del papel no es la que dice el "
        f"nombre del formato."
    )


def test_el_endpoint_devuelve_el_archivo_tal_cual() -> None:
    """CRUDO es literalmente el archivo, sin rearmar nada.

    Mismo criterio que reglas_de_medicion y font_metrics: si el endpoint
    reformateara, la FORMA seria un segundo lugar donde el backend y el preview
    se pueden desfasar.
    """
    assert CRUDO == json.loads(_RUTA.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 2. Nadie volvio a escribir un tamano de hoja a mano
# ---------------------------------------------------------------------------
#
# Las medidas que hoy existen en el archivo unico, en cm. Se arman DESDE el
# archivo: si manana se agrega un formato, sus numeros quedan prohibidos en el
# codigo el mismo dia, sin que nadie se acuerde de sumarlos aca.

def _medidas_prohibidas() -> set[str]:
    numeros: set[float] = set()
    for fmt in FORMATOS.values():
        for clave in ("papel_cm", "celda_cm"):
            numeros.add(fmt[clave]["ancho"])
            numeros.add(fmt[clave]["alto"])
    # 7.0 y 21.0 se escriben de las dos formas en el codigo real.
    formas: set[str] = set()
    for n in numeros:
        formas.add(f"{n:g}")
        if float(n).is_integer():
            formas.add(f"{int(n)}.0")
    return formas


_MEDIDAS = sorted(_medidas_prohibidas())
_MEDIDAS_CON_COMA = [m for m in _MEDIDAS if "." in m]


# SOLO SE MIRA EL CODIGO, nunca el texto. Los comentarios y los docstrings
# pueden (y deben) nombrar las medidas: ahi esta contada la historia -- "una
# hoja de 21 x 29,7", "detecto a5 (14,85 x 21, la mitad)". Prohibir la
# explicacion dejaria al proximo arreglo sin el porque, que es lo unico que
# hace entendible este. Lo prohibido es que el CODIGO tenga el numero.
def _solo_codigo(archivo: pathlib.Path) -> list[tuple[int, str]]:
    """Las lineas del archivo con los comentarios y los textos vaciados."""
    fuente = archivo.read_text(encoding="utf-8")
    if archivo.suffix == ".py":
        return _codigo_python(fuente)
    return _codigo_ts(fuente)


def _codigo_python(fuente: str) -> list[tuple[int, str]]:
    # Se BORRAN los textos y los comentarios de la linea original, en vez de
    # rearmar la linea juntando tokens. Rearmando quedaba `Cm ( 21.0 )` con
    # espacios en el medio y el barrido dejaba de reconocer `Cm(` -- o sea, la
    # tabla vieja de FORMAT_SLIDES pasaba limpia. Borrar sobre el texto
    # original no cambia ni una columna.
    import io
    import tokenize

    lineas = fuente.splitlines()
    ignorar = {tokenize.STRING, tokenize.COMMENT}
    for nombre in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        if hasattr(tokenize, nombre):
            ignorar.add(getattr(tokenize, nombre))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(fuente).readline):
            if tok.type not in ignorar:
                continue
            for fila in range(tok.start[0], tok.end[0] + 1):
                if fila > len(lineas):
                    break
                texto = lineas[fila - 1]
                desde = tok.start[1] if fila == tok.start[0] else 0
                hasta = tok.end[1] if fila == tok.end[0] else len(texto)
                lineas[fila - 1] = texto[:desde] + " " * (hasta - desde) + texto[hasta:]
    except Exception:  # pragma: no cover - un .py que no tokeniza ya no compila
        lineas = fuente.splitlines()
    return list(enumerate(lineas, 1))


def _codigo_ts(fuente: str) -> list[tuple[int, str]]:
    # Los bloques /* */ se reemplazan por espacios CONSERVANDO los saltos de
    # linea, para que el numero de linea del mensaje de error siga siendo el
    # de verdad.
    fuente = re.sub(
        r"/\*.*?\*/",
        lambda m: re.sub(r"[^\n]", " ", m.group(0)),
        fuente,
        flags=re.S,
    )
    salida = []
    for n, linea in enumerate(fuente.splitlines(), 1):
        linea = linea.split("//", 1)[0]
        # Comillas dobles, simples y template literals.
        linea = re.sub(r'"[^"]*"' + r"|'[^']*'" + r"|`[^`]*`", " ", linea)
        salida.append((n, linea))
    return salida


# Un "21" entero puede ser cualquier cosa (`column=7` de una planilla, un
# `:>7.2f` de formato). Para los enteros se exige que la linea hable de hoja
# con todas las letras; para las medidas con coma alcanza el contexto amplio,
# porque un 14.85 suelto no aparece por casualidad.
_HABLA_DE_HOJA = re.compile(
    r"(?i)hoja|papel|slide|page|pagina|format|celda|width_cm|height_cm|"
    r"ancho_cm|alto_cm|anchoCm|altoCm|\bdims?\b|Cm\("
)
_HABLA_DE_HOJA_FUERTE = re.compile(
    r"(?i)hoja|papel|celda|width_cm|height_cm|ancho_cm|alto_cm|anchoCm|altoCm|"
    r"slide_(width|height)|Cm\("
)


def _patron(medida: str) -> str:
    # El `(?![\d.])` del final es para que buscar "21" no enganche el "21" de
    # "21.0": si no, cada medida entera reportaba de prestado la de coma y el
    # mensaje de error nombraba dos veces la misma linea.
    return r"(?<![\d.])" + re.escape(medida) + r"(?![\d.])"


# Cuantas lineas alrededor cuentan como "la misma cosa". Una tabla de formatos
# se escribe asi:
#
#     const FORMAT_DIMS: Record<string, { w: number; h: number }> = {
#       a4:      { w: 21.0,  h: 29.7  },
#
# y la linea del numero NO dice "hoja" ni "formato" en ningun lado: lo dice el
# encabezado, tres lineas mas arriba. Mirando una sola linea, la tabla que
# arranco todo este problema pasaba limpia -- comprobado a mano contra el
# codigo viejo antes de subir esto.
_VENTANA = 4


def _lineas_con(archivo: pathlib.Path, medida: str) -> list[tuple[int, str]]:
    rx = re.compile(_patron(medida))
    contexto = _HABLA_DE_HOJA if "." in medida else _HABLA_DE_HOJA_FUERTE
    codigo = _solo_codigo(archivo)
    salida = []
    for i, (n, linea) in enumerate(codigo):
        if not rx.search(linea):
            continue
        # La ventana de vecinas vale para las medidas con coma. Para un entero
        # suelto se exige que la PROPIA linea hable de hoja: un `21` a cuatro
        # lineas de la palabra "papel" es casi siempre un indice de un texto
        # (`{c.texto[:21]}`) o una columna de una planilla, y un barrido que
        # grita por eso lo termina apagando alguien.
        if "." in medida:
            vecinas = "\n".join(l for _, l in codigo[max(0, i - _VENTANA): i + _VENTANA + 1])
            if not contexto.search(vecinas):
                continue
        elif not contexto.search(linea):
            continue
        salida.append((n, linea.strip()))
    return salida


_COMO_ARREGLARLO_PY = (
    "El tamano de hoja vive SOLO en app/data/formatos_de_hoja.json. Pone\n"
    "    from app.services.cenefas.formatos_de_hoja import papel_cm, celda_cm\n"
    "y usa papel_cm(formato) para el PAPEL que sale de la impresora o\n"
    "celda_cm(formato) para lo que ocupa UNA cenefa adentro. Y si lo que\n"
    "necesitas es el papel de una PLANTILLA, es hoja_de_definicion(definition):\n"
    "la medida del PPTX original le gana a cualquier tabla."
)

_COMO_ARREGLARLO_TS = (
    "No copies el numero: leelo de lib/cenefas/formatosDeHoja.ts, que lo pide al\n"
    "backend (papelDelFormato / celdaDelFormato / papelDeLaPlantilla). El valor\n"
    "vive SOLO en backend/app/data/formatos_de_hoja.json."
)


@pytest.mark.parametrize(
    "archivo, medida",
    [(a, m) for a in _MOTOR_PYTHON for m in _MEDIDAS],
    ids=lambda v: v.name if isinstance(v, pathlib.Path) else str(v),
)
def test_el_exportador_no_escribe_el_tamano_de_hoja_a_mano(
    archivo: pathlib.Path, medida: str
) -> None:
    encontradas = _lineas_con(archivo, medida)
    assert not encontradas, (
        f"VOLVIO LA COPIA: {archivo.name} escribe a mano la medida {medida} cm.\n"
        + "".join(f"  linea {n}: {t}\n" for n, t in encontradas)
        + "Consecuencia si se desfasa: el PPTX se arma sobre un papel y el "
        "preview dibuja otro, asi que en pantalla entra lo que impreso sale "
        "cortado -- que es el bug que Ivan encontro el 18/09/2026.\n"
        + _COMO_ARREGLARLO_PY
    )


@pytest.mark.parametrize(
    "archivo, medida",
    [(a, m) for a in _MOTOR_TS for m in _MEDIDAS],
    ids=lambda v: v.name if isinstance(v, pathlib.Path) else str(v),
)
def test_el_preview_no_escribe_el_tamano_de_hoja_a_mano(
    archivo: pathlib.Path, medida: str
) -> None:
    encontradas = _lineas_con(archivo, medida)
    assert not encontradas, (
        f"VOLVIO LA COPIA: {archivo.name} escribe a mano la medida {medida} cm.\n"
        + "".join(f"  linea {n}: {t}\n" for n, t in encontradas)
        + _COMO_ARREGLARLO_TS
    )


def test_el_preview_lee_el_tamano_de_hoja_del_backend() -> None:
    """El modulo puente existe y NO trae medidas propias.

    Un valor por defecto del lado del navegador es la duplicacion entrando por
    la ventana: dibujariamos una hoja que nadie comparo nunca con la que sale
    de la impresora.
    """
    puente = _FRONTEND / "lib" / "cenefas" / "formatosDeHoja.ts"
    assert puente.exists(), f"falta {puente}: el preview se quedo sin de donde leer."
    fuente = puente.read_text(encoding="utf-8")
    assert "/tools/cenefas/v2/formatos-de-hoja" in fuente or "getFormatosDeHoja" in fuente, (
        "formatosDeHoja.ts dejo de pedirle la tabla al backend."
    )
    codigo = "\n".join(l for _, l in _solo_codigo(puente))
    for medida in _MEDIDAS_CON_COMA:
        assert not re.search(_patron(medida), codigo), (
            f"formatosDeHoja.ts tiene la medida {medida} escrita adentro. Ese "
            f"archivo es el cano, no la fuente: no puede tener valores propios "
            f"ni de reserva."
        )


# ---------------------------------------------------------------------------
# 3. El papel NO se deriva del contenido
# ---------------------------------------------------------------------------

# LA FORMA EXACTA QUE TENIA EL BUG: se le ASIGNA a algo que ES la hoja el
# maximo (o el minimo) entre la hoja y algo sacado de los componentes.
#
# Se mira quien esta del lado IZQUIERDO, y eso es lo que separa el bug de lo
# legitimo: `dims = Math.max(hoja, ...bordes de los cuadros)` agranda el PAPEL
# para que entre el contenido, y esta prohibido; `newX = Math.min(x, dims.w -
# ancho)` acomoda un CUADRO para que no se pase de la hoja, y es lo que tiene
# que pasar cuando alguien arrastra una caja. Las dos nombran la hoja y los
# cuadros en la misma linea; lo que cambia es cual de los dos se calcula.
#
# Va sobre el archivo entero y no linea por linea porque el bug estaba escrito
# en cinco lineas (`const dims = slotBands ? { w: Math.max(...`).
# Como se llama LA HOJA en el codigo. Con `\w*` a los costados a proposito:
# `hojaDibujada`, `dimsReales`, `papelVisible` son la misma cosa con otro
# nombre, y un barrido que se esquiva renombrando la variable no barre nada.
_NOMBRE_DE_HOJA = (
    r"(?:\w*(?:dims|hoja|papel|paper|sheet)\w*|page_?[wh]\b|slide_width|slide_height|"
    r"width_cm|height_cm|ancho_cm|alto_cm|anchoCm|altoCm)"
)
# Como se llama EL CONTENIDO: los cuadros y sus bordes.
#
# OJO: el barrido mira el codigo con los TEXTOS BORRADOS (_solo_codigo), asi
# que en Python `c["base_bounds"]["width"]` llega como `c[  ][  ]` y no dice
# nada. Lo que queda en pie es el nombre de la lista que se recorre
# (`for c in componentes`), por eso estan los nombres de coleccion.
_CONTENIDO = (
    r"(?:base_bounds|computed_bounds|bounds\.|\.width|\.height|\w*comps?\b|"
    r"componentes?\b|components?\b|layoutComps|displayComps)"
)
# Un nombre de hoja con lo que le cuelgue (`papel.anchoCm`, `hoja["ancho_cm"]`).
_HOJA_CON_CAMPO = _NOMBRE_DE_HOJA + r"""[\w.\[\]"']*"""

_DERIVA_DEL_CONTENIDO = [
    # (a) LA FORMA ORIGINAL: a la hoja se le asigna un maximo/minimo que mira
    #     los cuadros. `dims = slotBands ? { w: Math.max(fmt.w, ...comps.map(
    #     c => c.base_bounds.x + c.base_bounds.width)) ...`.
    #     El hueco del medio no puede tener un `)`: sin eso, la ANOTACION DE
    #     TIPO de `def _ancho_seguro_cm(..., page_w: float) -> float:`
    #     enganchaba con el `max()` de adentro de la funcion y daba un falso
    #     positivo. Un parentesis cerrado ahi significa que el nombre de la
    #     hoja era un parametro, no el lado izquierdo de una cuenta.
    re.compile(
        r"\b" + _NOMBRE_DE_HOJA + r"\s*[:=][^;)]{0,400}?(?:Math\.)?\b(?:max|min)\s*\([^;]{0,300}?"
        + _CONTENIDO,
        re.S | re.I,
    ),
    # (b) LA HOJA COMO PRIMER ARGUMENTO de un max/min que ademas mira los
    #     cuadros, se asigne a quien se asigne: `Math.max(papel.anchoCm,
    #     ...layoutComps.map(c => c.base_bounds.x + c.base_bounds.width))`.
    #     Es la reescritura de "le pongo otro nombre a la variable": el
    #     maximo entre el papel y los bordes de los cuadros ES el bug, lo
    #     llame como lo llame.
    re.compile(
        r"\b(?:Math\.)?(?:max|min)\s*\(\s*" + _HOJA_CON_CAMPO + r"\s*,[^;]{0,300}?" + _CONTENIDO,
        re.S | re.I,
    ),
    # (c) LA HOJA COMO ULTIMO ARGUMENTO del mismo max/min: `max(*(c.x + c.w
    #     for c in comps), page_w)`. Lo que separa esto de lo legitimo --
    #     `min(x, dims.w - comp.base_bounds.width)` acomoda un CUADRO para que
    #     no se pase-- es que ahi la hoja entra RESTADA, no como candidata.
    #     En UNA linea: en Python no hay `;` que corte la ventana, y con
    #     saltos de linea el `max(0.0, min(x, page_w - MINIMO))` de una linea
    #     se pegaba con el `comp, ..., page_w)` de la siguiente.
    re.compile(
        r"\b(?:Math\.)?(?:max|min)\s*\([^;\n]{0,300}?" + _CONTENIDO + r"[^;\n]{0,200}?,\s*"
        + _HOJA_CON_CAMPO + r"\s*\)",
        re.I,
    ),
    # (d) EL MISMO MAXIMO ESCRITO COMO REDUCE, con la hoja de valor inicial:
    #     `comps.reduce((m, c) => Math.max(m, c.base_bounds.x + ...),
    #     papel.anchoCm)` o `functools.reduce(lambda m, c: max(m, ...),
    #     comps, page_w)`.
    re.compile(
        r"\breduce\s*\([^;]{0,300}?\b(?:max|min)\b[^;]{0,300}?" + _HOJA_CON_CAMPO,
        re.S | re.I,
    ),
    # (e) EL MAXIMO ESCRITO COMO ORDENAR Y TOMAR EL PRIMERO: `[papel.anchoCm,
    #     ...comps.map(c => c.base_bounds.x + c.base_bounds.width)].sort(
    #     (a, b) => b - a)[0]`.
    re.compile(
        r"\[[^\]]{0,300}?" + _HOJA_CON_CAMPO + r"[^\]]{0,300}?" + _CONTENIDO + r"[^\]]{0,200}?\]\s*\.sort\s*\(",
        re.S | re.I,
    ),
    re.compile(
        r"\[[^\]]{0,300}?" + _CONTENIDO + r"[^\]]{0,300}?" + _HOJA_CON_CAMPO + r"[^\]]{0,200}?\]\s*\.sort\s*\(",
        re.S | re.I,
    ),
]


def _culpables(codigo: str) -> list[str]:
    """Los pedazos de codigo que deducen la hoja del contenido, si los hay."""
    return [m.group(0)[:160] for rx in _DERIVA_DEL_CONTENIDO for m in rx.finditer(codigo)]


@pytest.mark.parametrize(
    "archivo",
    _MOTOR_PYTHON + _MOTOR_TS,
    ids=lambda v: v.name if isinstance(v, pathlib.Path) else str(v),
)
def test_nadie_deduce_el_tamano_de_hoja_del_contenido(archivo: pathlib.Path) -> None:
    """Prohibido agrandar (o achicar) la hoja para que entre el diseno.

    Esta es LA regla, y la que se violaba. El papel es un dato: lo trae el PPTX
    o lo dice el formato. Nunca sale de mirar donde quedaron los cuadros. Si el
    diseno no entra, el diseno no entra -- y hay que verlo.
    """
    codigo = "\n".join(l for _, l in _solo_codigo(archivo))
    culpables = _culpables(codigo)
    assert not culpables, (
        f"{archivo.name} vuelve a deducir el tamano de la hoja del contenido:\n"
        + "".join(f"  {t}\n" for t in culpables)
        + "\nEso es exactamente el bug del 18/09/2026: si un cuadro se salia del "
        "papel, el papel crecia hasta tragarlo y en pantalla todo entraba, "
        "mientras la impresora lo cortaba. El papel es un DATO -- sale del PPTX "
        "(definition.hoja) o del formato (formatos_de_hoja.papel_cm). Lo que se "
        "sale se tiene que VER saliendose; para avisarlo esta "
        "component_renderer.detectar_desbordes."
    )


# EL BARRIDO SE PRUEBA A SI MISMO. El 22/09/2026 se intento sabotear a mano
# y la regex original dejaba pasar CUATRO de siete reescrituras del mismo bug
# (el reduce, el nombre distinto, el nombre compuesto y el sort). Un barrido
# que solo atrapa la forma exacta en que se escribio la primera vez no protege
# de nada: la proxima vez se va a escribir distinto. Estas son las formas que
# se probaron; si aparece otra, se suma aca PRIMERO (en rojo) y despues se
# ensancha el barrido.
_REESCRITURAS_DEL_BUG = {
    "spread max": (
        "const dims = slotBands ? { w: Math.max(fmt.w, ...comps.map(c => "
        "c.base_bounds.x + c.base_bounds.width)), h: fmt.h } : fmt;"
    ),
    "reduce": (
        "const dims = { w: comps.reduce((m, c) => Math.max(m, c.base_bounds.x + "
        "c.base_bounds.width), papel.anchoCm), h: papel.altoCm };"
    ),
    "otro nombre": (
        "const lienzoW = Math.max(papel.anchoCm, ...layoutComps.map((c) => "
        "c.base_bounds.x + c.base_bounds.width));\n  const dims = { w: lienzoW, h: papel.altoCm };"
    ),
    "nombre compuesto": (
        "const hojaDibujada = { w: Math.max(papelReal.anchoCm, ...comps.map(c => "
        "c.base_bounds.x + c.base_bounds.width)), h: papelReal.altoCm };"
    ),
    "python": "page_w = max(page_w, *(c['base_bounds']['x'] + c['base_bounds']['width'] for c in comps))",
    "python ultimo": "ancho = max(*(c['computed_bounds']['x'] + c['computed_bounds']['width'] for c in comps), page_w)",
    "python reduce": "page_w = functools.reduce(lambda m, c: max(m, c['computed_bounds']['x']), comps, page_w)",
    "sort": (
        "const dims = { w: [papel.anchoCm, ...comps.map(c => c.base_bounds.x + "
        "c.base_bounds.width)].sort((a, b) => b - a)[0], h: papel.altoCm };"
    ),
}

# Lo que SI tiene que pasar limpio: acomodar un CUADRO contra la hoja, medir
# cuanto sobra, y la puerta unica. Si alguna de estas cae, el barrido se puso
# tan ancho que va a gritar por todo y alguien lo va a apagar.
_LEGITIMO = {
    "arrastre":  "const newX = +Math.max(0, Math.min((x - pageLeft) / PX_PER_CM, dims.w - comp.base_bounds.width)).toFixed(2);",
    "sobra":     "sobra.der = Math.max(sobra.der, b.x + b.width - dims.w);",
    "tope":      "const sobraDer = scalePx(Math.min(sobra.der, dims.w * TOPE_SOBRA));",
    "puerta":    "const dims = { w: papel?.anchoCm ?? 0, h: papel?.altoCm ?? 0 };",
    "peor lado": "const [lado, cm] = excesos.reduce((peor, e) => (e[1] > peor[1] ? e : peor));",
    "python ok": "ancho, alto = papel_cm(fmt_id or master)\nreturn {'ancho_cm': ancho, 'alto_cm': alto, 'origen': 'formato'}",
    "anotacion": "def _ancho_seguro_cm(comp: dict, page_w: float) -> float:\n    return max(0.0, min(comp['base_bounds']['width'], 3.0))",
}


def _como_lo_ve_el_barrido(forma: str, texto: str) -> str:
    """El texto con los strings y comentarios borrados, como en el barrido real.

    Sin esto la autoprueba mentiria: `c["base_bounds"]` en Python se borra
    entero antes de mirar, y una forma que "se atrapa" en el texto crudo puede
    pasar limpia en el archivo de verdad (paso el 22/09/2026 con jobs.py).
    """
    filas = _codigo_python(texto) if forma.startswith("python") else _codigo_ts(texto)
    return "\n".join(l for _, l in filas)


@pytest.mark.parametrize("forma", sorted(_REESCRITURAS_DEL_BUG))
def test_el_barrido_atrapa_el_bug_reescrito(forma: str) -> None:
    assert _culpables(_como_lo_ve_el_barrido(forma, _REESCRITURAS_DEL_BUG[forma])), (
        f"la forma '{forma}' del bug pasa limpia por el barrido:\n"
        f"  {_REESCRITURAS_DEL_BUG[forma]}\n"
        "Ensancha _DERIVA_DEL_CONTENIDO hasta que la atrape, y fijate que "
        "test_el_barrido_deja_pasar_lo_legitimo siga en verde."
    )


@pytest.mark.parametrize("forma", sorted(_LEGITIMO))
def test_el_barrido_deja_pasar_lo_legitimo(forma: str) -> None:
    assert not _culpables(_como_lo_ve_el_barrido(forma, _LEGITIMO[forma])), (
        f"el barrido marca como bug algo legitimo ('{forma}'):\n  {_LEGITIMO[forma]}"
    )


# ---------------------------------------------------------------------------
# 4. La puerta unica se comporta como dice
# ---------------------------------------------------------------------------

def test_la_hoja_de_la_plantilla_le_gana_a_la_tabla() -> None:
    """El caso de las cuatro apaisadas, que es el que justificaba el parche.

    Preciazos A5/6xA4 y Mega Rompe Precios A5/6xA4 tienen un PPTX de 29,7x21 cm
    (A4 apaisada) y master_format "a5", porque _detect_format comparaba contra
    medidas de CELDA y la tabla tenia la A5 parada y de una sola cenefa. Sin el
    dato medido, el preview las dibujaba a media hoja -- por eso existia el
    Math.max. Con el dato medido, se dibujan enteras sin inventar nada.
    """
    definicion = {
        "master_format": "a5",
        "hoja": {"ancho_cm": 29.699, "alto_cm": 20.999, "origen": "pptx"},
    }
    hoja = hoja_de_definicion(definicion)
    assert (hoja["ancho_cm"], hoja["alto_cm"]) == (29.699, 20.999)
    assert hoja["origen"] == "pptx"
    # Y la tabla sigue diciendo otra cosa, que es justamente el punto: la
    # etiqueta del formato no decide el tamano.
    assert papel_cm("a5") != (29.699, 20.999)


def test_sin_medida_se_usa_el_formato_y_se_dice() -> None:
    """Una plantilla armada a mano en el editor no tiene PPTX que medir.

    Ahi el papel es el del formato, y `origen` lo dice: el preview muestra
    "segun el formato" en vez de hacerlo pasar por medido.
    """
    hoja = hoja_de_definicion({"master_format": "3xa4"})
    assert hoja["origen"] == "formato"
    assert (hoja["ancho_cm"], hoja["alto_cm"]) == papel_cm("3xa4")
    # Y es el PAPEL, no la celda: un 3xa4 imprime una A4 entera con tres
    # franjas adentro. Confundirlos era lo que hacia que el preview de un
    # "3xa4" dibujara una franja de 9,9 cm de alto y la llamara "la hoja".
    assert (hoja["ancho_cm"], hoja["alto_cm"]) != celda_cm("3xa4")


def test_mirando_otro_formato_manda_el_papel_de_ese_formato() -> None:
    """El diseno escalado a otra hoja se dibuja sobre ESA hoja.

    Cuando se mira un formato que no es el master, lo que se ve es el diseno
    escalado, asi que la medida del PPTX original ya no aplica. Es el mismo
    criterio de los dos lados (papelDeLaPlantilla en el navegador).
    """
    definicion = {
        "master_format": "a4",
        "hoja": {"ancho_cm": 20.999, "alto_cm": 29.699, "origen": "pptx"},
    }
    hoja = hoja_de_definicion(definicion, "6xa4")
    assert hoja["origen"] == "formato"
    assert (hoja["ancho_cm"], hoja["alto_cm"]) == papel_cm("6xa4")


def test_el_ruido_de_emu_no_cuenta_como_otra_hoja() -> None:
    """20,999 x 29,699 ES una A4.

    PowerPoint guarda todo en EMU enteros y 21 cm no cae redondo: las 23
    plantillas de produccion declaran 20,999 x 29,699. Sin este piso, comparar
    el papel medido contra el de la tabla marcaria las 23 como distintas y
    cualquier aviso basado en eso seria ruido puro.
    """
    assert misma_hoja((20.999, 29.699), papel_cm("a4"))
    assert not misma_hoja((29.699, 20.999), papel_cm("a4"))


def test_una_a4_apaisada_ya_no_se_hace_pasar_por_a5() -> None:
    """El disparate que _detect_format aceptaba en silencio.

    Un slide de 29,699 x 20,999 no es la CELDA de ningun formato conocido: es
    una hoja ya armada. Antes se elegia el vecino mas cercano sin piso y salia
    "a5" con 14,85 cm de error. Ahora no llega a la tolerancia, se devuelve la
    etiqueta por defecto y `seguro` en False para que el import lo diga.
    """
    from app.services.cenefas.pptx_importer import _detect_format
    fmt, _slots, _cols, seguro = _detect_format(29.699, 20.999)
    assert seguro is False, "una A4 apaisada no es la celda de ningun formato"
    assert fmt == "a4", "sin reconocer, queda la etiqueta por defecto"
    # Y una A4 de verdad se sigue reconociendo, con el ruido de EMU incluido.
    fmt, _slots, _cols, seguro = _detect_format(20.999, 29.699)
    assert (fmt, seguro) == ("a4", True)


def test_lo_que_se_mide_es_lo_que_se_imprime() -> None:
    """El aviso de desborde mide los cuadros COMO VAN A SALIR, no los crudos.

    El render hace dos cosas distintas segun la plantilla: con bandas ignora
    el formato destino (las celdas ya estan en la hoja del master), y sin
    bandas escala el diseno a la celda del destino. La ruta del preview media
    siempre los base_bounds crudos del master contra el papel del destino: en
    una corrida de un diseno A4 pedido como 6xA4, comparaba centimetros de
    una hoja con el borde de otra. `como_se_imprimen` es la unica cuenta y
    tiene que decir lo mismo que el render.
    """
    from app.services.cenefas.component_renderer import como_se_imprimen
    comp = {"id": "d", "type": "text", "format_overrides": {},
            "base_bounds": {"x": 1.0, "y": 1.0, "width": 10.0, "height": 2.0}}

    # Sin bandas y mismo formato: los cuadros tal cual, papel del master.
    comps, fmt = como_se_imprimen([comp], "a4", "a4", None)
    assert fmt == "a4" and comps[0]["base_bounds"] == comp["base_bounds"]
    assert "computed_bounds" not in comps[0]

    # Sin bandas y otro formato: escalado a la celda del destino, papel del destino.
    comps, fmt = como_se_imprimen([comp], "a4", "6xa4", None)
    assert fmt == "6xa4"
    cx, cy = celda_cm("6xa4"); mx, my = celda_cm("a4")
    assert comps[0]["computed_bounds"]["width"] == pytest.approx(10.0 * cx / mx)
    assert comps[0]["computed_bounds"]["height"] == pytest.approx(2.0 * cy / my)

    # Con bandas: el destino no cambia nada, el papel es el del master.
    comps, fmt = como_se_imprimen([comp], "6xa4", "a4", [[comp]])
    assert fmt == "6xa4" and comps[0] is comp

    # Sin master ni destino: a4, como el resto del sistema.
    assert como_se_imprimen([comp], None, None, None)[1] == "a4"


# ---------------------------------------------------------------------------
# 5. El aviso de desborde: mide TINTA, no cajas
# ---------------------------------------------------------------------------

_HOJA_A4 = {"ancho_cm": 20.999, "alto_cm": 29.699, "origen": "pptx"}


def _caja_ancha(ancho=16.52, x=7.59, pt=27.0):
    """El cuadro de la descripcion de 3xA4 SOLO X 25, con sus medidas reales.

    x=7,59 y 16,52 cm de ancho sobre una A4 de 21: la CAJA termina en 24,11,
    o sea 3,1 cm afuera. Es el cuadro con el que Ivan encontro el bug.
    """
    return {
        "id": "descripcion", "type": "text", "variable": "descripcion",
        "base_bounds": {"x": x, "y": 5.0, "width": ancho, "height": 2.0},
        "style": {"font_size": pt, "align": "left", "font_family": "Aptos"},
    }


def test_una_caja_fuera_del_papel_con_el_texto_adentro_no_avisa():
    """La caja se sale 3,1 cm y no se avisa nada. Es correcto y es el punto.

    Los disenos reales usan cajas mucho mas anchas que la hoja a proposito. Si
    el aviso fuera por caja, saltarian 13 de las 23 plantillas de produccion
    --cuatro por 1,1 mm de sangrado del fondo-- y seria un aviso por cartel que
    nadie leeria. Es el mismo razonamiento que ya esta escrito en
    detectar_solapes.
    """
    from app.services.cenefas.component_renderer import detectar_desbordes
    comp = _caja_ancha()
    assert comp["base_bounds"]["x"] + comp["base_bounds"]["width"] > _HOJA_A4["ancho_cm"]
    assert detectar_desbordes([(comp, {"descripcion": "LECHE"})], _HOJA_A4) == []


def test_cuando_la_tinta_cruza_el_borde_si_avisa_con_nombre_y_centimetros():
    """Y el aviso tiene que servirle a una persona: cuanto y de que lado."""
    from app.services.cenefas.component_renderer import detectar_desbordes
    largo = "DETERGENTE LIQUIDO CONCENTRADO PARA ROPA BLANCA Y DE COLOR 3 LITROS"
    avisos = detectar_desbordes([(_caja_ancha(), {"descripcion": largo})], _HOJA_A4)
    assert len(avisos) == 1, "una descripcion larga en esa caja se imprime afuera"
    a = avisos[0]
    assert a["component_id"] == "descripcion"
    assert a["lado"] == "derecha" and a["corta_texto"] is True
    assert a["cm"] > 1, f"se pasa {a['cm']} cm: el numero tiene que ser util"
    assert largo[:10] in a["texto"], "el aviso dice QUE texto se sale"
    # El papel viaja redondeado a dos decimales A PROPOSITO: es lo que la
    # pantalla muestra entre parentesis ("hoja de 21 x 29,7 cm") y los 20,999
    # del EMU ahi son ruido. Las cuentas se hacen con el numero exacto; lo
    # redondeado es solo el que se lee.
    assert a["hoja_cm"] == [21.0, 29.7], "y contra que papel se midio"


def test_el_sangrado_de_una_imagen_de_fondo_no_es_un_desborde():
    """Una imagen que se pasa 1,1 mm del borde va asi a proposito.

    Cuatro plantillas de produccion tienen el fondo sangrado. Marcarlas seria
    exactamente el aviso-que-nadie-lee.
    """
    from app.services.cenefas.component_renderer import detectar_desbordes
    fondo = {
        "id": "fondo", "type": "image", "name": "fondo",
        "base_bounds": {"x": -0.11, "y": -0.07, "width": 21.22, "height": 29.84},
        "style": {},
    }
    assert detectar_desbordes([(fondo, {})], _HOJA_A4) == []


def test_sin_papel_no_se_inventa_ninguno():
    """Si no hay medida de hoja, no se avisa: no se compara contra un supuesto."""
    from app.services.cenefas.component_renderer import detectar_desbordes
    assert detectar_desbordes([(_caja_ancha(), {"descripcion": "X" * 80})], {}) == []


def test_el_desborde_se_mira_en_todas_las_filas_no_solo_en_la_primera():
    """La fila 1 entra y la 3 se sale: el aviso tiene que aparecer igual.

    Es el mismo agujero que se tapo en los solapes el 20/09/2026. Quien mira la
    pantalla ve la primera fila del Excel, y el texto que se imprime cortado es
    el mas largo del listado -- que casi nunca es el primero.
    """
    from app.services.cenefas.component_renderer import detectar_desbordes_del_lote
    productos = [
        {"descripcion": "LECHE"},
        {"descripcion": "YERBA"},
        {"descripcion": "DETERGENTE LIQUIDO CONCENTRADO PARA ROPA BLANCA 3 LITROS"},
    ]
    avisos = detectar_desbordes_del_lote([_caja_ancha()], [], productos, _HOJA_A4)
    assert len(avisos) == 1
    assert avisos[0]["fila"] == 3, "el peor caso es la tercera fila del Excel"
    assert avisos[0]["filas"] == 1, "y pasa en una sola de las tres"


def test_un_cuadro_oculto_no_tiene_tinta_y_no_avisa():
    """Un cuadro que no se dibuja no se sale de nada.

    Medido sobre las 23 plantillas el 22/09/2026: el "$" que una regla esconde
    cuando promoOferta es un "2x1" seguia apareciendo en la lista de desbordes.
    Es la misma condicion con la que _render_slide decide no escribirlo: el
    ojito del panel (`visible`) y la regla evaluada contra ESTE producto.
    """
    from app.services.cenefas.component_renderer import (
        detectar_desbordes, detectar_desbordes_del_lote,
    )
    largo = "DETERGENTE LIQUIDO CONCENTRADO PARA ROPA BLANCA Y DE COLOR 3 LITROS"
    prod = {"descripcion": largo}
    # Con el cuadro visible SI avisa (si no, este test no probaria nada).
    assert detectar_desbordes([(_caja_ancha(), prod)], _HOJA_A4)
    # El ojito del panel.
    apagado = {**_caja_ancha(), "visible": False}
    assert detectar_desbordes([(apagado, prod)], _HOJA_A4) == []
    # La regla de ocultar, por el camino real (preparar_componentes).
    regla = {
        "id": "r", "name": "ocultar", "action": {"type": "hide"},
        "condition": {"field": "descripcion", "operator": "contains", "value": "DETERGENTE"},
        "target_component_id": "descripcion",
    }
    assert detectar_desbordes_del_lote([_caja_ancha()], [regla], [prod], _HOJA_A4) == []


def test_un_texto_con_espacios_nunca_se_dibuja_mas_ancho_que_su_caja():
    """Si no entra, PowerPoint lo parte: no lo saca por el costado.

    Caso real (Fiesta Alemania A4, medido contra el PDF el 22/09/2026): la
    descripcion va en Franklin Gothic Heavy, que no esta en la tabla de
    metricas y se mide un 25% de mas. "DETERGENTE LIQUIDO CONCENTRADO" a 40 pt
    daba 23,6 cm de una sola linea en una caja de 19,83 centrada en la hoja,
    o sea 1,5 cm afuera por cada lado -- y en el papel esta partido en dos
    renglones, adentro. El exportador escribe todo con word_wrap, asi que un
    texto CON espacios jamas puede ser mas ancho que su caja; solo lo que no
    tiene por donde cortarse (un precio) sobresale.
    """
    from app.services.cenefas.component_renderer import _rect_texto_real, detectar_desbordes
    comp = {
        "id": "descripcion", "type": "text", "variable": "descripcion",
        "base_bounds": {"x": 0.78, "y": 9.39, "width": 19.83, "height": 5.39},
        "style": {"font_size": 40, "align": "center", "font_family": "Franklin Gothic Heavy"},
    }
    prod = {"descripcion": "DETERGENTE LÍQUIDO CONCENTRADO"}
    r = _rect_texto_real(comp, prod)
    assert r["width"] <= comp["base_bounds"]["width"] + 1e-9
    assert r["x"] >= comp["base_bounds"]["x"] - 1e-9
    assert detectar_desbordes([(comp, prod)], _HOJA_A4) == []
    # Y lo que NO tiene espacios sigue sobresaliendo, que es lo que pasa con
    # un precio mas ancho que su caja.
    precio = {**comp, "variable": "precio", "base_bounds": {**comp["base_bounds"], "width": 2.0}}
    assert _rect_texto_real(precio, {"precio": "199999"})["width"] > 2.0
