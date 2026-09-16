"""Convertidor de Excel — matchea el export crudo de gestión contra el
catálogo compartido de descripciones (sku_descripciones) y arma un Excel
limpio, listo para subir directo al generador de Cenefas existente.

Deliberadamente separado de data_engine.py: esta herramienta no interpreta
la mecánica de oferta/oferta det (eso sigue siendo trabajo exclusivo del
generador de Cenefas cuando el Excel de salida se vuelva a subir ahí) —
solo transporta esas columnas tal cual del input al output.
"""
import csv
import difflib
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cenefa_ofertadet_alias import CenefaOfertadetAlias
from app.models.convertidor_header_alias import ConvertidorHeaderAlias
from app.models.cenefa_grupo_unificado import CenefaGrupoUnificado
from app.models.sku_descripcion import SkuDescripcion
from app.services.cenefas.convertidor_ai import resolve_date_columns_with_ai
from app.services.cenefas.convertidor_variables import construir_variables
from app.services.cenefas.variables import (
    DECIMAL_OF,
    ORDEN_EXPORT,
    PRICE_VARS,
    resolve as resolve_variable,
)
from app.services.cenefas.formatters import parse_price_raw
from app.services.cenefas.validation_engine import DESCRIPTION_MAX_CHARS, DESCRIPTION_WARN_CHARS

# ---------------------------------------------------------------------------
# Normalización de headers del Excel de entrada
# ---------------------------------------------------------------------------

class ConvertidorParseError(ValueError):
    """El Excel no tiene una columna CODIGO reconocible."""


def _norm(name) -> str:
    """Copia intencional de data_engine._norm — no importamos ese símbolo
    privado entre módulos para no acoplar convertidor.py a los internos de
    data_engine.py; son 3 líneas, duplicarlas es más barato que el acople."""
    s = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", s).lower()


_INPUT_ALIASES: dict[str, str] = {
    "codigo":         "codigo",
    "nombrearticulo": "nombreArticulo",
    # Gestion exporta esta columna con y sin el "de" segun el listado
    # ("NOMBREARTICULO" en el mailing, "NOMBRE DE ARTICULO" en los de MRP).
    # Sin este alias la columna se ignora en silencio y las filas llegan sin
    # nombre: la generacion con IA las descarta antes de llamar a la API
    # --no tiene de donde redactar-- y salen todas como "completalas a mano".
    "nombredearticulo": "nombreArticulo",
    # La columna "Descripción" del Excel SÍ se lee, y gana sobre el catálogo:
    # si alguien se tomó el trabajo de escribirla, es la que quiere ver en el
    # cartel (decisión de 2026-08-24). Lo que NO cambia es que no se aprende
    # sola en el catálogo compartido -- ver match_rows().
    "descripcion":    "descripcionExcel",
    "moneda":         "moneda",
    "precioant":      "precioAnterior",
    "precioanterior": "precioAnterior",
    "pvpregular":     "precioAnterior",
    "pvpoferta":      "precio",
    "precio":         "precio",
    # Los nombres CANONICOS tambien entran. Desde 08/2026 la variable del
    # precio anterior se llama precioRegular y la del vigente precioOferta, y
    # es como salen del propio Convertidor -- si alguien renombra las columnas
    # de su Excel a los nombres del sistema (lo mas razonable) tienen que
    # matchear. Sin esto el archivo se leia sin precios y las cenefas salian
    # con el simbolo de moneda solo.
    "precioregular":  "precioAnterior",
    "preciooferta":   "precio",
    "oferta":         "oferta",
    "ofertadet":      "ofertaDet",
    "descripcionweb": "descripcionWeb",
    "descripcionesweb": "descripcionWeb",   # en plural en los listados de MRP
    "comprador":      "comprador",
    "descuentoprov":     "descuento",
    "descuentoprovdet":  "descuentoDet",
    # Fecha inicio/fin de vigencia -- ninguna de las dos es obligatoria en
    # gestión (muchos exports no las traen); si falta una o las dos, vigencia
    # simplemente queda como antes (ver _format_vigencia). Varios alias por
    # lado porque el nombre exacto de la columna varía según el export.
    "fechainicio":        "fechaInicio",
    "fechadeinicio":      "fechaInicio",
    "fechainicial":       "fechaInicio",
    "fechadesde":         "fechaInicio",
    "vigenciadesde":      "fechaInicio",
    "iniciovigencia":     "fechaInicio",
    "fechafin":           "fechaFin",
    "fechadefin":         "fechaFin",
    "fechafinal":         "fechaFin",
    "fechahasta":         "fechaFin",
    "vigenciahasta":      "fechaFin",
    "finvigencia":        "fechaFin",
    # El export con stock por sucursal (15/09/2026, el primero de verdad que
    # vimos) viene en FORMATO LARGO: una fila por producto y por sucursal, con
    # el nombre de la sucursal como VALOR de una columna y no como encabezado
    # (ver juntar_filas_por_producto). Nombra sus columnas distinto que los
    # listados de oferta, y esto es el mecanismo de siempre para eso.
    #
    # "idproducto" es el que NO se puede sacar: detectar_fila_headers busca una
    # columna que normalice a `codigo` para encontrar la fila de encabezados, y
    # sin este alias el archivo entero se rechaza con "No encontré una columna
    # 'CODIGO' reconocible" -- no es que saliera mal dividido, es que no se
    # podía ni abrir.
    "idproducto":     "codigo",
    "sucursal":       "sucursal",
    "stock":          "stock",
    # La categoría del producto la trae el propio export, en dsc_subfamilia
    # (AURICULARES, FREIDORA, MIXER, CAFETERA: 45 valores). Es exactamente el
    # nivel "por producto" que hace falta para partir la descarga, escrito por
    # gestión y no deducido por nosotros del texto del nombre (decisión de Ivan,
    # 15/09/2026). Los otros dos niveles que trae el archivo --dsc_categoria
    # (ELECTRO HOGAR / TECNOLOGIA) y dsc_subcategoria-- son demasiado gruesos
    # para una carpeta y no se leen.
    "dscsubfamilia":  "categoriaProducto",
    "subfamilia":     "categoriaProducto",
    # dsc_familia se lee SOLO como respaldo de las subfamilias que no dicen qué
    # es el producto -- ver _SUBFAMILIAS_SIN_PRODUCTO.
    "dscfamilia":     "familiaProducto",
    "familia":        "familiaProducto",
}


# Subfamilias que NO nombran al producto, y para las que manda dsc_familia.
#
# Gestión le pone "4K" de subfamilia a TODOS los televisores, chicos y grandes
# por igual: lo que los separa está un nivel más arriba, en dsc_familia
# ("TVS MENOS 65\"" y "TVS 65\" O MAS"). Con la subfamilia sola, un 32" y un 75"
# caían en el mismo "4K.xlsx", un nombre de archivo que no dice qué hay adentro.
# Ivan lo marcó el 16/09/2026 mirando la grilla: "lo que sea 4k en realidad son
# tvs, tenemos que tomar la columna porque ahí está el valor real".
#
# Es una lista y no un `if` para que agregar la próxima sea una línea: el resto
# de las 45 subfamilias (FREIDORA, CAFETERA, AURICULARES, LAVARROPA) se explican
# solas y NO hay que tocarlas.
_SUBFAMILIAS_SIN_PRODUCTO: frozenset[str] = frozenset(("4k",))


def categoria_del_listado(subfamilia: str, familia: str) -> str:
    """Qué categoría le corresponde a una fila según las columnas del listado.

    La subfamilia manda, salvo que sea una de las que no nombran al producto
    (ver _SUBFAMILIAS_SIN_PRODUCTO), donde manda la familia. Si la familia
    viniera vacía igual se devuelve la subfamilia: es preferible un "4K.xlsx"
    a una fila que cae en "Sin categoría" por un dato que sí estaba.
    """
    sub = _clean_str(subfamilia)
    fam = _clean_str(familia)
    if sub and _norm(sub) in _SUBFAMILIAS_SIN_PRODUCTO and fam:
        return fam
    return sub

_HEADER_SCAN_ROWS = 10
_DATE_SAMPLE_ROWS = 8  # filas de datos a mirar para juntar valores de muestra para la IA


# Espejo de SkuDescripcion.sku (String(600), migración 0049) y de
# SKU_COMBINADO_MAX_CHARS en ConvertidorGrid.tsx. Los tres tienen que moverse
# juntos: el frontend avisa antes de mandar, esto corta con un 400 con motivo y
# la columna es el límite real.
SKU_MAX_CHARS = 600


def normalize_sku(raw) -> str:
    """int/float/str crudo de la celda CODIGO -> string canónico ('17780.0' -> '17780')."""
    if raw is None:
        return ""
    if isinstance(raw, float):
        raw = int(raw) if raw.is_integer() else raw
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


# Clave que junta varios SKU numéricos ("63009-211797", "520221 - 512909",
# "594879/80/81"). Desde 2026-08-28 esas claves NO entran más al catálogo
# singular: lo grupal vive en cenefa_grupos_unificados. Solo se bloquean
# partes numéricas a propósito -- un código real con sufijo de variante
# ("12345-A") sigue siendo un SKU singular legítimo y pasa.
_RE_CLAVE_PLURAL = re.compile(r"^\d+(?:\s*[-/]\s*\d+)+$")


async def upsert_sku_descripcion(db: AsyncSession, sku: str, descripcion: str, user_id: int) -> str:
    """Upsert vía ON CONFLICT DO UPDATE — evita una condición de carrera real
    si dos personas completan el mismo SKU sin match al mismo tiempo.
    Compartido entre el PATCH manual del Convertidor y la tool de Tinín, para
    no duplicar el statement en dos lugares. No commitea — el caller decide
    cuándo (el PATCH lo hace solo, Tinín puede encadenar varias llamadas en
    un mismo turno de tool-use antes de commitear una vez)."""
    sku_norm = normalize_sku(sku)
    if not sku_norm:
        raise ValueError("SKU inválido")
    if _RE_CLAVE_PLURAL.match(sku_norm):
        raise ValueError(
            "Esa clave junta varios SKU. Las descripciones de grupo van en "
            "Grupos unificados (solapa Plurales del Diccionario), no en el "
            "catálogo singular: acá cada SKU lleva la descripción de ESE producto."
        )
    # Mismo largo que SkuDescripcion.sku (migración 0049). Se cierra acá para que
    # un grupo absurdamente grande devuelva un 400 con motivo en vez de un 500
    # de Postgres -- la clave entra además en un índice único y en el path de la
    # URL, así que no puede ser ilimitada.
    if len(sku_norm) > SKU_MAX_CHARS:
        raise ValueError(
            f"El código tiene {len(sku_norm)} caracteres y el máximo es {SKU_MAX_CHARS}. "
            "Si es un grupo unificado, son demasiados SKU para una sola clave."
        )
    descripcion = descripcion.strip()
    if not descripcion:
        raise ValueError("La descripción no puede quedar vacía")
    descripcion = descripcion[:300]

    stmt = pg_insert(SkuDescripcion).values(
        sku=sku_norm,
        descripcion=descripcion,
        updated_by_id=user_id,
    ).on_conflict_do_update(
        index_elements=["sku"],
        set_={
            "descripcion": descripcion,
            "updated_by_id": user_id,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    return sku_norm


# Copias intencionales de los regex de data_engine (mismo criterio que _norm:
# tres lineas duplicadas son mas baratas que acoplar los internos de los dos
# modulos): el precio con la unidad de venta pegada ("148 unidad", "31,2 la
# unidad", "1.919,20 c/u") y el separador de miles escrito como texto.
_RE_PRECIO_UNIDAD_PEGADA = re.compile(
    r"^\s*\$?\s*(\d[\d.,]*)\s+[a-zA-ZáéíóúñÁÉÍÓÚÑ/][a-zA-ZáéíóúñÁÉÍÓÚÑ/.\s]*$"
)
_RE_MILES_TEXTO = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def _parse_price_or_none(raw) -> float | None:
    """Precio crudo de gestión -> float, o None si la celda NO es un precio.

    La guarda del fullmatch es la parte que importa (2026-08-29): antes se
    descartaba todo lo no numérico DEL PRINCIPIO y se parseaba el resto, así
    que una celda con la mecánica escrita ("Comprando 2 $129 unidad") se
    convertía en 2.0 EN SILENCIO -- y ese 2 terminó impreso como $2 en una
    cenefa real de Mega Rompe Precios. Ahora: o la celda es un precio de
    punta a punta (tolerando el símbolo adelante y la unidad de venta atrás),
    o es None y la fila queda sin precio, roja, para que una persona decida.
    """
    if raw is None or str(raw).strip() == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    texto = str(raw).strip()
    # "148 unidad" -> "148": la unidad de venta pegada sí es un precio.
    con_unidad = _RE_PRECIO_UNIDAD_PEGADA.match(texto)
    if con_unidad:
        texto = con_unidad.group(1)
    # El símbolo de moneda adelante también se tolera ("$119", "U$S 45").
    texto = re.sub(r"^(?:U\$S|US\$|USD|\$)\s*", "", texto, flags=re.IGNORECASE).strip()
    if not re.fullmatch(r"\d[\d.,]*", texto):
        return None
    # "1.299" como texto es mil doscientos noventa y nueve, no 1,299.
    if _RE_MILES_TEXTO.fullmatch(texto):
        texto = texto.replace(".", "")
    return parse_price_raw(texto)


# La forma de una celda de stock: "12", "0", y el "12.0" / "12,0" que deja
# openpyxl cuando la columna del Excel está formateada como número. El decimal
# se tolera únicamente si es CERO -- ver el docstring de abajo.
#
# Este regex llegó a decidir además si una COLUMNA entera era de stock: primero
# por la forma de sus valores (parece_columna_de_stock) y después por el nombre
# del encabezado contra una lista fija de sucursales (SUCURSALES). Las dos cosas
# se borraron el 15/09/2026, cuando llegó el export real y resultó que no hay
# una columna por sucursal: hay UNA sola columna `stock` y una FILA por sucursal
# (ver juntar_filas_por_producto). Así que esto volvió a ser lo que dice el
# nombre -- la forma de UNA celda-- y nada más.
_RE_STOCK_ENTERO = re.compile(r"(\d+)(?:[.,]0+)?")


def _parse_stock_or_none(valor) -> int | None:
    """Celda de stock por sucursal -> int, o None si no hay dato legible.

    Misma doctrina que _parse_price_or_none, y por el mismo motivo: acá no se
    inventa nada. Lo que importa es la diferencia entre VACÍO y CERO. Una celda
    vacía es "esta sucursal no informó" y un 0 es "informó que no tiene": si el
    vacío se leyera como 0, una fila que quedó afuera por falta de dato tendría
    exactamente la misma cara que una que de verdad no tiene stock, y no habría
    forma de distinguir un listado incompleto de una góndola vacía. Las dos
    salen como None, sí, pero None significa "no hay dato" y nunca entra al
    "_stock" de la fila, mientras que el 0 sí entra y se ve.

    Tampoco se redondea: "12,5" no es una cantidad de unidades. Devolver 12
    sería inventar la mitad que falta, y devolver 13 peor. Ilegible es None.

    Un negativo también es None: no es un stock, y dejarlo pasar como -3
    obligaría a que todos los que lo comparan contra _STOCK_MINIMO se acuerden
    del caso. La forma de un stock es la misma acá y en la columna entera.
    """
    texto = _clean_str(valor)
    if not texto:
        return None
    m = _RE_STOCK_ENTERO.fullmatch(texto)
    return int(m.group(1)) if m else None


def _clean_str(raw) -> str:
    return str(raw).strip() if raw is not None else ""


_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y")


def _parse_date_or_none(raw) -> date | None:
    """xlsx con la celda formateada como fecha llega ya como date/datetime
    (openpyxl con data_only=True); CSV y celdas de texto llegan como string
    en alguno de los formatos regionales más comunes. Cualquier otra cosa
    (vacío, texto que no matchea ningún formato) es None -- fechaInicio/fin
    son opcionales, así que un valor no reconocible se ignora en vez de
    romper el import entero."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip() if raw is not None else ""
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _format_vigencia(fechaInicio: date | None, fechaFin: date | None) -> str:
    """"Desde el 10 al 16 de julio" (mismo mes/año -- el caso común de una
    promo semanal), con fallback a mencionar el mes de cada punta si difieren.
    Ninguna de las dos fechas es obligatoria: con una sola, frase abierta
    ("Desde"/"Hasta" nomás); con ninguna, "" (igual que antes de esta regla,
    completable a mano en la grilla)."""
    if fechaInicio and fechaFin:
        mes_inicio = _MESES[fechaInicio.month - 1]
        if fechaInicio.year != fechaFin.year:
            mes_fin = _MESES[fechaFin.month - 1]
            return (
                f"Desde el {fechaInicio.day} de {mes_inicio} de {fechaInicio.year} "
                f"hasta el {fechaFin.day} de {mes_fin} de {fechaFin.year}"
            )
        if fechaInicio.month != fechaFin.month:
            mes_fin = _MESES[fechaFin.month - 1]
            return f"Desde el {fechaInicio.day} de {mes_inicio} hasta el {fechaFin.day} de {mes_fin}"
        return f"Desde el {fechaInicio.day} al {fechaFin.day} de {mes_inicio}"
    if fechaInicio:
        return f"Desde el {fechaInicio.day} de {_MESES[fechaInicio.month - 1]}"
    if fechaFin:
        return f"Hasta el {fechaFin.day} de {_MESES[fechaFin.month - 1]}"
    return ""


# ---------------------------------------------------------------------------
# Validación por tipo esperado de columna
# ---------------------------------------------------------------------------
#
# Cada columna del Excel de gestión tiene un tipo de contenido esperado —
# precio es numérico, nombre/descripción son texto, moneda es un símbolo de
# un set chico conocido, oferta det es una categoría (nunca un número). Si
# el valor de una celda no matchea el tipo esperado de SU columna, eso es la
# señal real de columnas corridas para esa fila — no una heurística de
# "pinta" sobre la fila entera, sino una razón concreta y localizada: "acá
# esperaba X y encontré Y". OFERTA queda sin validar a propósito: en los
# datos reales es legítimamente polimórfica (texto "PVP OFERTA", un precio
# repetido, o una mecánica "2x599"), no hay un tipo único que reclamarle.

_VALID_MONEDAS = {"$", "u$s", "us$", "usd", "uyu"}
_NUMERIC_RE  = re.compile(r"^[\$\s]*-?\d[\d.,]*\s*$")
_LETTER_RE   = re.compile(r"[^\W\d_]")  # al menos una letra (unicode-aware)


def _is_numeric_like(raw: str) -> bool:
    return bool(_NUMERIC_RE.match(raw.strip()))


def _has_letters(raw: str) -> bool:
    return bool(_LETTER_RE.search(raw))


# ---------------------------------------------------------------------------
# Parseo del Excel de entrada
# ---------------------------------------------------------------------------

def _read_csv_rows(csv_bytes: bytes) -> list[tuple]:
    """Lee un CSV (algunos exports de gestión, sobre todo Rompe Precios,
    vienen así en vez de xlsx) tolerando las dos variantes regionales más
    comunes: separador coma o punto y coma (frecuente acá, porque la coma
    ya se usa como separador decimal), y encoding UTF-8 o Windows-1252
    (típico de sistemas de gestión viejos que no exportan UTF-8 nativo)."""
    text = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = csv_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = csv_bytes.decode("utf-8", errors="replace")

    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        # El sniffer necesita al menos un par de filas consistentes para
        # decidir — con muy pocas filas o un formato ambiguo, cae acá:
        # cuenta cuál separador aparece más seguido en la muestra.
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","

    return [tuple(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _parece_csv_en_una_columna(rows: list[tuple]) -> bool:
    """True si el .xlsx en realidad es un CSV metido en una sola columna.

    El export real de gestión sale así: una única columna por fila, con todo
    el contenido separado por comas adentro de la celda. openpyxl lo lee tal
    cual, así que el header queda como "CODIGO,SECCION,NRO_OFERTA,..." y no
    matchea con ninguna columna esperada -- el archivo se rechazaba con "no
    encontré una columna CODIGO" sin ninguna pista de por qué.
    """
    if not rows:
        return False
    con_datos = [r for r in rows[:5] if r and r[0] is not None]
    if not con_datos:
        return False
    if any(len(r) > 1 and any(c is not None for c in r[1:]) for r in con_datos):
        return False
    return all(str(r[0]).count(",") >= 3 or str(r[0]).count(";") >= 3 for r in con_datos)


def _mapear_columnas(row) -> tuple[dict[int, str], bool]:
    candidate: dict[int, str] = {}
    found_codigo = False
    for col_idx, cell in enumerate(row):
        if cell is None:
            continue
        var_name = _INPUT_ALIASES.get(_norm(cell))
        if var_name:
            candidate[col_idx] = var_name
            if var_name == "codigo":
                found_codigo = True
    return candidate, found_codigo


async def campos_reconocidos(header_row, db: AsyncSession | None = None) -> set[str]:
    """Qué campos de entrada resuelve el Convertidor SOLO en esta fila de headers.

    Existe para que la pantalla de mapeo no pida a mano algo que el archivo ya
    trae reconocido. El caso concreto es `tipoOferta`: el export de gestión trae
    una columna OFERTA y el motor ya saca el literal de ahí (leído junto con
    OFERTADET, ver construir_variables), así que pedir que alguien la mapee es
    trabajo al pedo -- y peor: lo mapeado a mano GANA sobre lo calculado, así que
    un mapeo hecho sin necesidad puede empeorar el resultado.

    Mira los dos pasos que no cuestan una llamada a IA: los alias fijos de
    _INPUT_ALIASES y el cache de alias aprendidos (mismo criterio que
    parse_input_excel, sin el tercer paso). Sin `db` se queda solo con los fijos.
    """
    col_map, _ = _mapear_columnas(header_row)
    campos = set(col_map.values())
    if db is None:
        return campos

    mapeadas = set(col_map.keys())
    sin_resolver = {
        _norm(cell): idx
        for idx, cell in enumerate(header_row)
        if cell is not None and idx not in mapeadas and _norm(cell)
    }
    if not sin_resolver:
        return campos

    result = await db.execute(
        select(ConvertidorHeaderAlias.header_norm, ConvertidorHeaderAlias.field_name)
        .where(ConvertidorHeaderAlias.header_norm.in_(sin_resolver.keys()))
    )
    for _header_norm, field_name in result.all():
        if field_name is not None:
            campos.add(field_name)
    return campos


# ---------------------------------------------------------------------------
# OFERTA con precios en vez de mecánicas (pedido de Ivan, 2026-08-27)
# ---------------------------------------------------------------------------
#
# La columna OFERTA del export de gestión trae el TITULAR de la mecánica: el
# literal "2x$299", "6x4", "2da unidad al 50%", solo o adentro de un texto más
# largo ("Coca Cola Zero 2.25 L 2x$299"). De ahí sale tipoOferta.
#
# Pero cuando alguien edita el Excel a mano, a veces escribe en esa columna los
# PRECIOS de oferta. El Convertidor la sigue leyendo como si fuera el titular:
# si OFERTADET dice "Combo", el regex del combo no encuentra el "NxM" y la fila
# queda con `combo_no_parseable`; y el precio real, que estaba ahí al lado, no lo
# usa nadie. El aviso decía que la mecánica no se pudo parsear, nunca que la
# columna entera venía con otra cosa.
#
# Esto NO se arregla solo, y a propósito: cuál es el precio de oferta cuando hay
# una columna PRECIO y además una OFERTA con números es una pregunta de negocio,
# no de código. Se detecta, se avisa en la pantalla de mapeo -- el único momento
# del flujo en que alguien está mirando las columnas -- y la persona decide.

# Un literal de mecánica adentro del texto: "2x$299", "6x4", "3 x 2",
# "2da unidad al 50%", "50% off". Si aparece cualquiera, el valor NO es un
# precio pelado, es un titular (o un titular con el nombre del producto adelante).
_RE_LITERAL_MECANICA = re.compile(
    r"\d\s*x\s*\$?\s*\d"          # 2x1, 6x4, 2x$299, 3 x 2
    r"|\d\s*(?:ra|da|ro|do|ta|va|ma)\b"   # 2da, 3ra, 4ta unidad...
    r"|\d\s*%"                     # 20%, 50% off
    r"|\bal\s+\d",                 # "al 50"
    re.IGNORECASE,
)

# Un precio de góndola de verdad. El piso de 10 es para no confundir un precio
# con un RATIO de descuento: gestión escribe "-0.253164556962025" en esa misma
# columna cuando el tipo es "% Descuentos", y eso no es un precio ni hay que
# proponer nada con él (ese caso ya está documentado arriba de resolver_mecanica
# en convertidor_variables.py).
_PRECIO_PELADO_MIN = 10


def _es_precio_pelado(valor: str) -> bool:
    """El valor es un precio y nada más -- ni literal de mecánica ni jerga."""
    v = (valor or "").strip()
    if not v or _RE_LITERAL_MECANICA.search(v):
        return False
    # Se le saca el símbolo de moneda de adelante, como hace _parse_price_or_none.
    limpio = re.sub(r"^\s*(?:\$u?|u\$s?|usd|\$)\s*", "", v, flags=re.IGNORECASE).strip()
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?", limpio):
        return False
    # "1.100" es mil cien, no 1,1: _parse_price_or_none toma el punto como
    # decimal, así que el separador de miles se resuelve aparte (mismo criterio
    # y mismo regex que _precio_es_de_kilo_en_100g más abajo).
    if _RE_SEPARADOR_MILES.match(limpio):
        numero = float(limpio.replace(".", ""))
    else:
        numero = _parse_price_or_none(limpio)
    return numero is not None and numero >= _PRECIO_PELADO_MIN


# Qué proporción de los valores no vacíos tiene que ser un precio pelado para
# decir que la columna entera viene con precios. No es 1.0 porque un listado real
# mezcla: unas pocas filas pueden traer el titular bien puesto. Tampoco 0.5,
# porque una columna mitad y mitad no es un caso claro y avisar de más en esta
# pantalla entrena a la gente a ignorar el aviso.
_PROPORCION_PRECIOS_PELADOS = 0.8


def oferta_trae_precios(valores: list[str]) -> bool:
    """La columna OFERTA parece traer precios en vez de titulares de mecánica.

    `valores` son los de muestra de esa columna (los mismos que la pantalla de
    mapeo ya muestra). Se piden al menos 3 no vacíos: con uno o dos, un número
    suelto es tan probablemente una casualidad como un patrón."""
    no_vacios = [v for v in (valores or []) if (v or "").strip()]
    if len(no_vacios) < 3:
        return False
    pelados = sum(1 for v in no_vacios if _es_precio_pelado(v))
    return pelados / len(no_vacios) >= _PROPORCION_PRECIOS_PELADOS


# ---------------------------------------------------------------------------
# Formato largo: una fila por producto y POR SUCURSAL (pedido de Ivan, 2026-09-15)
# ---------------------------------------------------------------------------
#
# Algunos listados traen, además de los datos del producto, cuántas unidades hay
# en cada sucursal. Con eso se puede partir la descarga: una carpeta por
# sucursal y adentro solo lo que esa sucursal tiene para vender (ver
# armar_zip_dividido).
#
# La forma de ese dato NO es la que habíamos supuesto, y conviene que quede
# escrito porque se implementaron las dos. Hasta el 15/09/2026 dimos por hecho
# que venía UNA COLUMNA POR SUCURSAL, con el nombre de la sucursal como
# encabezado: primero se reconocían por la forma de los valores
# (parece_columna_de_stock -- cualquier columna de enteros pasaba, y un precio
# redondo es un entero) y después por el nombre, contra una lista fija de
# sucursales (SUCURSALES, es_columna_de_sucursal, detectar_columnas_stock). Ese
# mismo día Ivan pasó el primer export de verdad y no era ninguna de las dos: es
# FORMATO LARGO.
#
#   id_producto | descripcion  | ... | sucursal | stock | ... | dsc_subfamilia
#   503996      | AURICULAR... | ... | Central  | 5     | ... | AURICULARES
#   503996      | AURICULAR... | ... | Arocena  | 0     | ... | AURICULARES
#   503996      | AURICULAR... | ... | Unión    | 0     | ... | AURICULARES
#
# Una fila por producto y por sucursal: ese archivo trae 4.773 filas para 271
# productos y 18 sucursales (no todos los productos traen las 18: el primero
# tiene 17). El nombre de la sucursal es un VALOR de la columna `sucursal`, no un
# encabezado, así que no hay ninguna columna que se llame como una sucursal ni
# lista de sucursales que mantener. Salen todas las que traiga el archivo
# --"Central", "Deposito A.Saravia" y "Propios" incluidas, sin lista blanca ni
# negra-- y el día que abra un local nuevo aparece solo, sin tocar código.
#
# OJO con contar productos por el número de arriba: ese export termina con tres
# filas de PIE DE PÁGINA ("Total", una en blanco, y "Filtros aplicados: ..."
# con todo el filtro escrito adentro de la celda del código). La vacía se
# descarta sola --no tiene código-- pero las otras dos entran como si fueran
# productos, así que el juntado devuelve 273 y no 271. No es algo que este
# módulo resuelva hoy: ninguna de las dos trae sucursal, así que quedan sin
# "_stock" y armar_zip_dividido las deja afuera y las cuenta en
# "filas_sin_stock", a la vista.
#
# Todo el bloque de detección por nombre se borró ese mismo día en vez de
# dejarlo apagado: código muerto en un módulo de 2.000 líneas es peor que nada,
# y lo único que sobreviviría de aquello es una lista de sucursales inventadas
# que alguien podría creerse.

# Cuántas unidades tiene que haber en una sucursal para que la fila entre en su
# carpeta. Ivan lo dijo primero como "mayor a 1" y lo corrigió a "mayor o igual
# a 1" el mismo 15/09/2026: con una sola unidad ya hay algo para vender y el
# cartel tiene que estar puesto. Si mañana cambia, se cambia acá y en ningún
# otro lado -- la UI no repite el número.
_STOCK_MINIMO = 1


def _sin_dato(valor) -> bool:
    """"No vino nada" para juntar_filas_por_producto: None y texto en blanco.

    Un 0 NO es "sin dato", y por eso no alcanza con preguntar si el valor es
    falsy. Es la misma distinción que cuida _parse_stock_or_none --vacío es "no
    informó", cero es "informó que no tiene"-- y acá además hay precios: un 0
    escrito en el listado es un valor que alguien puso, y si contara como vacío
    lo pisaría el de la fila siguiente.
    """
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    return False


def juntar_filas_por_producto(parsed: list[dict]) -> tuple[list[dict], dict]:
    """Formato largo -> una fila por producto, con el stock de cada sucursal.

    Por qué existe: el Convertidor hace UNA cenefa por producto. Sin juntar, el
    export de arriba llega a la grilla con 4.773 filas --la misma cenefa
    repetida una vez por sucursal, hasta 18 veces-- y el que la revisa tiene que
    corregir 18 veces la misma descripción para que salgan 18 carteles iguales.

    Es PURA y no toca `db` a propósito: es la pieza que hay que poder probar con
    filas escritas a mano, y conftest.py prohíbe base y red en los tests.

    Solo se aplica si la hoja trae la columna `sucursal`, o sea si ALGUNA fila la
    tiene con algo adentro (una columna con todas las celdas en blanco es lo
    mismo que no tenerla). Si no, devuelve `parsed` TAL CUAL --la misma lista,
    sin copiar ni tocar una clave-- y el resumen en cero: los listados de
    siempre, que son la enorme mayoría, se convierten exactamente igual que
    antes de que esto existiera.

    Se agrupa por `codigo` respetando el orden de aparición, y la fila que queda
    es la PRIMERA del grupo (así el orden de la grilla sigue siendo el del
    archivo), más:

    - `"_stock"` = {sucursal: unidades}, hermana de "_mapeado", con las filas del
      grupo cuyo stock es legible. Una celda vacía no deja rastro, porque "no
      informó" y "tiene cero" son dos cosas distintas (ver _parse_stock_or_none)
      y el que arma el ZIP tiene que poder verlas distinto. Si la MISMA sucursal
      aparece dos veces para un producto se SUMAN: un export puede traer el
      stock físico y el que está en tránsito en dos filas, y son unidades de la
      misma góndola. Una fila sin sucursal no tiene carpeta a la que ir, así que
      sus unidades no entran en ningún lado.
    - El resto de los campos: gana el PRIMER valor no vacío del grupo. Las
      filas de un producto traen los mismos datos repetidos, pero basta que la
      primera venga con la descripción en blanco para que, quedándose ciegamente
      con ella, el producto entero saliera sin descripción teniéndola 17 veces
      más abajo.

    `sucursal` y `stock` se SACAN de la fila resultante: ese dato ya vive adentro
    de "_stock", y dejarlos sueltos es una invitación a que alguien los lea como
    si fueran del producto ("este auricular es de Central") cuando en realidad
    son de una sola de las filas que se juntaron.

    El segundo valor es el resumen, para poder avisar en pantalla de dónde
    salieron las filas: {"filas", "productos", "sucursales", "con_diferencias"}.
    `sucursales` va en orden de aparición y sin repetir. `con_diferencias` es
    cuántos productos traían dos valores distintos no vacíos en algún campo entre
    sus filas; es un dato para mostrar y no frena nada: lo normal es 0, y si da
    alto quiere decir que el archivo no es lo que creemos que es.
    """
    if all(_sin_dato(r.get("sucursal")) for r in parsed):
        return parsed, {"filas": 0, "productos": 0, "sucursales": [], "con_diferencias": 0}

    # dict por código: conserva el orden de inserción, así que el primero que
    # aparece manda y las filas de un producto se juntan aunque vengan salteadas.
    grupos: dict[str, list[dict]] = {}
    sucursales: list[str] = []
    for r in parsed:
        grupos.setdefault(r.get("codigo") or "", []).append(r)
        sucursal = _clean_str(r.get("sucursal"))
        if sucursal and sucursal not in sucursales:
            sucursales.append(sucursal)

    salida: list[dict] = []
    con_diferencias = 0
    for grupo in grupos.values():
        fila = {k: v for k, v in grupo[0].items() if k not in ("sucursal", "stock")}
        stock: dict[str, int] = {}
        difiere = False
        for r in grupo:
            for clave, valor in r.items():
                if clave in ("sucursal", "stock"):
                    continue
                if _sin_dato(fila.get(clave)):
                    fila[clave] = valor
                elif not _sin_dato(valor) and valor != fila[clave]:
                    # Se cuenta el PRODUCTO una sola vez, no el campo ni la
                    # fila: lo que hay que poder decir en pantalla es "3
                    # productos vienen con datos distintos entre sus filas", no
                    # "51 diferencias", que no le dice nada a nadie.
                    difiere = True
            sucursal = _clean_str(r.get("sucursal"))
            unidades = r.get("stock")
            if sucursal and unidades is not None:
                stock[sucursal] = stock.get(sucursal, 0) + unidades
        fila["_stock"] = stock
        salida.append(fila)
        con_diferencias += 1 if difiere else 0

    return salida, {
        "filas":           len(parsed),
        "productos":       len(salida),
        "sucursales":      sucursales,
        "con_diferencias": con_diferencias,
    }


def detectar_fila_headers(rows: list[tuple]) -> int | None:
    """Indice (0-based) de la fila de encabezados, o None si no la hay.

    No se asume la fila 1: el export real trae una fila de titulo y una en
    blanco antes. La senal es una columna CODIGO reconocible."""
    for i, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        _, found_codigo = _mapear_columnas(row)
        if found_codigo:
            return i
    return None


def listar_hojas(file_bytes: bytes, filename: str = "") -> list[str]:
    """Nombres de las hojas del archivo, en orden. Un CSV tiene una sola.

    Los bocetos reales traen varias hojas con datos distintos: el export crudo
    de gestion, el "Frente" ya curado a mano (con los SKU combinables unidos y
    la mecanica en COMENTARIO) y el "Dorso". Cada una es un listado aparte y se
    convierte por separado.
    """
    if filename.lower().endswith(".csv"):
        return ["CSV"]
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    return list(wb.sheetnames)


def leer_filas(file_bytes: bytes, filename: str = "", hoja: str | int | None = None) -> list[tuple]:
    """Lee el archivo subido a filas, sea .csv, .xlsx o .xlsx-que-es-un-CSV.

    `hoja` es el nombre o el indice de la hoja a leer. None = la primera, que
    es el comportamiento historico. Hasta 08/2026 la primera era la unica que
    se leia, hardcodeada: en un boceto de tres hojas eso significaba convertir
    el export crudo de gestion y no el "Frente" curado, sin avisar a nadie.
    """
    if filename.lower().endswith(".csv"):
        return _read_csv_rows(file_bytes)

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    if hoja is None:
        nombre = wb.sheetnames[0]
    elif isinstance(hoja, int):
        if not 0 <= hoja < len(wb.sheetnames):
            raise ConvertidorParseError(
                f"El archivo no tiene una hoja numero {hoja + 1} (tiene {len(wb.sheetnames)})"
            )
        nombre = wb.sheetnames[hoja]
    else:
        if hoja not in wb.sheetnames:
            raise ConvertidorParseError(
                f"El archivo no tiene una hoja llamada {hoja!r}. "
                f"Tiene: {', '.join(wb.sheetnames)}"
            )
        nombre = hoja
    ws = wb[nombre]
    rows = list(ws.iter_rows(min_row=1, max_row=None, values_only=True))

    if _parece_csv_en_una_columna(rows):
        crudo = chr(10).join(str(r[0]) for r in rows if r and r[0] is not None)
        return _read_csv_rows(crudo.encode("utf-8"))
    return rows


async def parse_input_excel(
    file_bytes: bytes,
    filename: str = "",
    *,
    db: AsyncSession,
    current_user_id: int,
    allow_ai: bool = False,
    mapeo: dict[str, str] | None = None,
    valores: dict[str, str] | None = None,
    campos: dict[str, str] | None = None,
    hoja: str | int | None = None,
) -> tuple[list[dict], int, list[str], dict]:
    """Detecta la fila de headers real (puede no ser la fila 1 — el export
    real de gestión trae una fila de título + una fila en blanco antes),
    mapea columnas por nombre normalizado, y extrae por fila: codigo,
    nombreArticulo, moneda, precioAnterior, precio, oferta, ofertaDet,
    descripcionWeb, comprador, descuento, descuentoDet, fechaInicio,
    fechaFin (estas últimas dos opcionales -- ver _format_vigencia), y
    sucursal, stock y categoriaProducto, que solo traen los listados en formato
    largo (ver juntar_filas_por_producto).

    Columnas no reconocidas por _INPUT_ALIASES se resuelven en dos pasos más
    antes de darse por ignoradas -- para CUALQUIERA de los campos, no solo
    fechaInicio/fechaFin como fue al principio: primero
    contra ConvertidorHeaderAlias (headers que Tinín ya clasificó en un import
    anterior — nunca vuelve a gastar una llamada a IA en el mismo nombre de
    columna dos veces), y si sigue sin match y allow_ai=True (el caller decide
    esto según el permiso ai.tinin del usuario), se le pide a Tinín que
    clasifique las columnas no reconocidas cuyos valores de muestra ya
    parsean como fecha real (ver resolve_date_columns_with_ai en
    convertidor_ai.py) — nunca se le pregunta por columnas que no tienen
    pinta de fecha en los datos.

    Acepta .xlsx/.xlsm, .csv, y también el .xlsx que en realidad es un CSV
    metido en una sola columna, que es como sale el export real de gestión
    (ver leer_filas).

    Las variables que el Convertidor no puede deducir solo (ofertaUno..Cuatro,
    vigencia, aclaracionUno..Tres, legales) las resuelve la persona en la
    pantalla de mapeo, de una de dos formas:

    - `mapeo`   {variable: nombre_de_columna} -- se lee de esa columna, fila
      por fila.
    - `valores` {variable: texto_fijo} -- el mismo texto para todas las filas.
      Hace falta porque el export de gestión no trae nunca vigencia ni
      legales: esos textos los escribe una persona, no salen de ninguna
      columna.

    Las dos son excluyentes por variable; si igual llegaran las dos, gana el
    valor fijo (es lo que se escribió explícitamente para esta corrida).
    Ambas viajan resueltas en cada fila bajo la clave "_mapeado".

    Un listado en FORMATO LARGO --una fila por producto y por sucursal-- se
    junta acá adentro antes de devolverse: salen 274 filas de producto con su
    "_stock" por sucursal y no las 4.773 del archivo (ver
    juntar_filas_por_producto). No hay nada que prender ni confirmar; el formato
    se reconoce solo por la columna `sucursal`, y un listado que no la trae sale
    exactamente igual que siempre.

    Devuelve (filas, learned_aliases_count, headers, juntado) --
    learned_aliases_count es cuántos headers nuevos aprendió Tinín en esta
    llamada, para que el caller sepa si hace falta commitear; headers son los
    nombres crudos de la fila de encabezados, para poder re-abrir la pantalla de
    mapeo; juntado es el resumen del formato largo, todo en cero cuando no lo
    hubo, con `filas_sin_sucursal` = cuántas filas de pie de reporte se
    saltearon."""
    rows = leer_filas(file_bytes, filename, hoja)

    header_row_idx = detectar_fila_headers(rows)
    col_map: dict[int, str] = {}
    # Columnas cuyo campo lo decidió una persona en esta corrida. Se excluyen de
    # los pasos de resolución automática de más abajo: sin esto, desasignar una
    # columna (campo "") la dejaba como "no reconocida" y el cache de alias o la
    # IA se la volvían a asignar, deshaciendo justo lo que se pidió.
    forzadas: set[int] = set()
    if header_row_idx is not None:
        col_map, _ = _mapear_columnas(rows[header_row_idx])
        # Override de esta corrida: {nombre_de_columna: campo}. Pisa lo que dice
        # _INPUT_ALIASES para esa columna, y solo para este archivo -- NO se
        # aprende. Es deliberado: el caso que lo motiva es un Excel editado a
        # mano donde la columna OFERTA trae precios en vez del titular de la
        # mecánica (ver oferta_trae_precios), y eso es un accidente de ESE
        # archivo, no una convención de nombres que valga para siempre. Lo que sí
        # se aprende son los nombres de columna nuevos, y eso vive en
        # ConvertidorHeaderAlias.
        #
        # Un campo vacío ("") desasigna la columna: es como decirle "ignorá esta",
        # y hace falta para poder sacar OFERTA de `oferta` sin mandarla a otro
        # lado.
        if campos:
            por_norm = {_norm(c): campo for c, campo in campos.items() if _norm(c)}
            for idx, cell in enumerate(rows[header_row_idx]):
                campo = por_norm.get(_norm(cell)) if cell is not None else None
                if campo is None:
                    continue
                forzadas.add(idx)
                if campo:
                    # Se le saca ese campo a cualquier OTRA columna que lo
                    # tuviera. Pasa siempre en el caso que motiva esto: el
                    # archivo trae PRECIO y además OFERTA con precios, y al
                    # mandar OFERTA a `precio` quedaban dos columnas peleando
                    # por el mismo campo. Ganaba una por el orden en que
                    # `col_by_var` invierte el dict, que no es una regla que
                    # nadie eligió. Elegida a mano, gana la elegida.
                    for otro_idx in [i for i, c in col_map.items() if c == campo and i != idx]:
                        col_map.pop(otro_idx, None)
                    col_map[idx] = campo
                else:
                    col_map.pop(idx, None)

    if header_row_idx is None:
        raise ConvertidorParseError(
            "No encontré una columna 'CODIGO' reconocible en las primeras "
            f"{_HEADER_SCAN_ROWS} filas del Excel — verificá que sea el export crudo de gestión."
        )

    learned_aliases_count = 0
    header_row = rows[header_row_idx]
    mapped_cols = set(col_map.keys())

    # col_idx de cada celda con texto en la fila de headers que _INPUT_ALIASES
    # no supo mapear -- candidatas a resolverse por el cache aprendido o por IA.
    unresolved_by_norm: dict[str, int] = {}
    unresolved_display: dict[str, str] = {}
    for col_idx, cell_val in enumerate(header_row):
        # `sucursal` y `stock` no llegan acá porque _INPUT_ALIASES las
        # reconoce, y esa es media razón de ser de esos dos alias: una columna
        # que queda como "no reconocida" se lleva una llamada a Tinín al pedo y
        # --mucho peor-- lo que Tinín conteste se guarda en
        # ConvertidorHeaderAlias, que es un cache global y permanente. Un alias
        # falso ahí ("sucursal" -> fechaInicio) no se desaprende solo y se lo
        # come todo import futuro que traiga esa columna.
        if cell_val is None or col_idx in mapped_cols or col_idx in forzadas:
            continue
        norm = _norm(cell_val)
        if not norm:
            continue
        unresolved_by_norm[norm] = col_idx
        unresolved_display[norm] = str(cell_val).strip()

    if unresolved_by_norm:
        result = await db.execute(
            select(ConvertidorHeaderAlias.header_norm, ConvertidorHeaderAlias.field_name)
            .where(ConvertidorHeaderAlias.header_norm.in_(unresolved_by_norm.keys()))
        )
        for header_norm, field_name in result.all():
            # Se saca de unresolved pase lo que pase -- un cache negativo
            # (field_name None, "confirmado que no es de vigencia") también
            # evita volver a preguntarle a la IA por este mismo header.
            col_idx = unresolved_by_norm.pop(header_norm, None)
            if col_idx is not None and field_name is not None:
                col_map[col_idx] = field_name

    if unresolved_by_norm and allow_ai:
        sample_rows = rows[header_row_idx + 1: header_row_idx + 1 + _DATE_SAMPLE_ROWS]
        candidates = []
        for header_norm, col_idx in unresolved_by_norm.items():
            muestras = [
                str(r[col_idx]).strip()
                for r in sample_rows
                if col_idx < len(r) and r[col_idx] is not None and _parse_date_or_none(r[col_idx])
            ]
            # Al menos dos valores de muestra parseando como fecha real -- uno
            # solo puede ser casualidad (un texto que por azar matchea un
            # formato de fecha), dos ya es señal sólida de que la columna
            # entera es de fechas y vale la pena preguntarle a Tinín cuál es.
            if len(muestras) >= 2:
                candidates.append({
                    "header_norm": header_norm,
                    "header_display": unresolved_display[header_norm],
                    "muestras": muestras[:3],
                })

        if candidates:
            # {} significa que la llamada entera falló (red, JSON con forma
            # rara, etc.) -- no cachear nada en ese caso, se reintenta en el
            # próximo import. Un dict no vacío trae una entrada por candidato
            # (positiva o None), ver resolve_date_columns_with_ai.
            clasificaciones = await resolve_date_columns_with_ai(candidates, db, current_user_id)
            if clasificaciones:
                nuevas_aliases: list[tuple[str, str | None]] = []
                seen_fields: set[str] = set()
                for header_norm, field_name in clasificaciones.items():
                    if field_name is not None:
                        if field_name in seen_fields:
                            # Dos columnas distintas no pueden ser el mismo
                            # campo -- ante la duda no asignamos ninguna de
                            # las dos (mejor perder la detección que pisar
                            # una con la otra), y se cachea como "no es de
                            # vigencia" para no reabrir la duda en el
                            # próximo import con el mismo layout.
                            field_name = None
                        else:
                            seen_fields.add(field_name)
                            col_idx = unresolved_by_norm.get(header_norm)
                            if col_idx is not None:
                                col_map[col_idx] = field_name
                    nuevas_aliases.append((header_norm, field_name))

                stmt = pg_insert(ConvertidorHeaderAlias).values([
                    {"header_norm": h, "field_name": f} for h, f in nuevas_aliases
                ]).on_conflict_do_nothing(index_elements=["header_norm"])
                await db.execute(stmt)
                learned_aliases_count = len(nuevas_aliases)

    # col_map es col_idx -> var_name; invertido una sola vez, no por fila.
    col_by_var = {var: c for c, var in col_map.items()}
    codigo_col = col_by_var["codigo"]

    def cell(row: tuple, var: str):
        c = col_by_var.get(var)
        return row[c] if c is not None and c < len(row) else None

    # {variable: col_idx} para lo que eligió la persona en la pantalla de
    # mapeo. Se resuelve por nombre normalizado para que un espacio o una
    # mayúscula de más no rompa el match contra el header real.
    headers_crudos = [str(c).strip() if c is not None else "" for c in header_row]
    por_norm = {_norm(h): i for i, h in enumerate(headers_crudos) if h}
    mapeo_cols: dict[str, int] = {}
    for var, col_nombre in (mapeo or {}).items():
        idx = por_norm.get(_norm(col_nombre or ""))
        if idx is not None:
            mapeo_cols[var] = idx

    # Vuelta del propio Convertidor: una columna que YA se llama como una
    # variable final se toma tal cual, sin recalcular nada.
    #
    # El Convertidor está pensado para leer el export CRUDO de gestión y
    # calcular las variables. Pero su propia salida se vuelve a subir todo el
    # tiempo --se corrige una descripción, se unifican categorías, se guarda y
    # se sube de nuevo-- y ahí el archivo ya trae las variables resueltas. Sin
    # esto, de las 13 columnas de un archivo ya convertido matcheaban 4: los
    # decimales, `mecanica`, `unidadMoneda`, `precioBanco` y `banco` se perdían
    # en silencio, y los cuatro decimales ni siquiera se podían mapear a mano
    # porque no están en VARIABLES_MAPEABLES.
    #
    # Esto no es un camino nuevo: entra por el mismo `_mapeado` que ya usa la
    # pantalla de mapeo, donde "lo mapeado pisa lo calculado". Por eso lo
    # elegido a mano sigue ganando -- se agrega solo lo que nadie mapeó.
    #
    # `resolve` (variables.py) es el mismo que usan el encabezado del Excel del
    # generador y el placeholder del PPTX: tolera mayúsculas, separadores y el
    # alias corto. Un encabezado que NO es una variable no entra acá y sigue el
    # camino de siempre, así que los export crudos no cambian en nada.
    for i, h in enumerate(headers_crudos):
        canonica = resolve_variable(h) if h else None
        if canonica and canonica not in mapeo_cols:
            mapeo_cols[canonica] = i

    # Valores escritos a mano: el mismo texto en todas las filas. Se limpian
    # acá una sola vez en vez de por fila.
    fijos = {
        var: str(val).strip()
        for var, val in (valores or {}).items()
        if val is not None and str(val).strip()
    }

    parsed: list[dict] = []
    for row in rows[header_row_idx + 1:]:
        # "not row[...]" en vez de "is None": una celda vacía de CSV llega
        # como "" (nunca None, a diferencia de openpyxl) — este chequeo
        # cubre las dos fuentes por igual.
        if codigo_col >= len(row) or not row[codigo_col]:
            continue
        codigo = normalize_sku(row[codigo_col])
        if not codigo:
            continue

        precioRaw          = _clean_str(cell(row, "precio"))
        precioAnteriorRaw = _clean_str(cell(row, "precioAnterior"))
        parsed.append({
            "codigo":            codigo,
            "nombreArticulo":   _clean_str(cell(row, "nombreArticulo")),
            "moneda":            _clean_str(cell(row, "moneda")) or "$",
            "precioAnterior":   _parse_price_or_none(precioAnteriorRaw),
            "precioAnteriorRaw": precioAnteriorRaw,
            "precio":            _parse_price_or_none(precioRaw),
            "precioRaw":        precioRaw,
            "oferta":            _clean_str(cell(row, "oferta")),
            # None = el export NO trae la columna OFERTADET (los listados MRP,
            # por ejemplo). Es distinto de "" (la columna existe y la celda
            # vino vacía): sin columna, la familia de la mecánica se infiere
            # del literal de OFERTA (ver construir_variables); con columna,
            # OFERTADET decide y el texto de OFERTA nunca clasifica nada
            # (regla de Ivan del 2026-08-25, intacta).
            "ofertaDet":        (_clean_str(cell(row, "ofertaDet"))
                                 if "ofertaDet" in col_by_var else None),
            "descripcionWeb":   _clean_str(cell(row, "descripcionWeb")),
            "descripcionExcel": _clean_str(cell(row, "descripcionExcel")),
            "comprador":         _clean_str(cell(row, "comprador")),
            "descuento":         _clean_str(cell(row, "descuento")),
            "descuentoDet":     _clean_str(cell(row, "descuentoDet")),
            "fechaInicio":      _parse_date_or_none(cell(row, "fechaInicio")),
            "fechaFin":         _parse_date_or_none(cell(row, "fechaFin")),
            # Los tres del formato largo, vacíos en todos los demás listados.
            # `sucursal` y `stock` son datos de ESTA fila y no del producto:
            # viven sueltos acá nada más que hasta juntar_filas_por_producto,
            # que los mete adentro de "_stock" y los saca de la fila.
            "sucursal":          _clean_str(cell(row, "sucursal")),
            "stock":             _parse_stock_or_none(cell(row, "stock")),
            "categoriaProducto": _clean_str(cell(row, "categoriaProducto")),
            "familiaProducto":   _clean_str(cell(row, "familiaProducto")),
            "_mapeado": {
                **{var: _clean_str(row[i]) if i < len(row) else ""
                   for var, i in mapeo_cols.items()},
                **fijos,
            },
        })

    # Pie de reporte: en una hoja de formato largo, la fila SIN sucursal no es
    # un producto. El export de ejemplo termina con una fila "Total" y otra que
    # arranca "Filtros aplicados: ...", las dos con texto en la primera columna
    # y todo lo demás vacío, y sin esto llegan a la grilla como dos artículos
    # más. Se reconocen por la FORMA y no por el texto: toda fila de producto de
    # este formato trae sucursal --es la razón de ser del formato--, así que la
    # que no la trae no es una; el día que el reporte diga "Totales" el criterio
    # por texto se cae y este no. Ivan, 15/09/2026: "no siempre va a venir así
    # pero es una posibilidad, no lo hagas como fila obligatoria" -- si vienen se
    # saltean, si no vienen no pasa nada y el archivo NUNCA falla por esto.
    #
    # Y solo en las hojas que traen sucursal, que es el mismo criterio con el que
    # juntar_filas_por_producto reconoce el formato largo (alguna fila con algo
    # adentro). En un listado de los de siempre, una fila con código y nada más
    # ES un producto que la persona completa a mano --para eso está el warning
    # missing_description y el resaltado rojo--, y descartarla ahí sería hacerle
    # perder una cenefa sin decirle nada.
    filas_sin_sucursal = 0
    if any(not _sin_dato(r["sucursal"]) for r in parsed):
        con_sucursal = [r for r in parsed if not _sin_dato(r["sucursal"])]
        filas_sin_sucursal = len(parsed) - len(con_sucursal)
        parsed = con_sucursal

    # Última parada: si el archivo vino en formato largo, acá es donde las 4.773
    # filas se vuelven 274 productos y nadie más se entera. Va adentro del
    # parser y no en la ruta a propósito: si viviera afuera, cada caller nuevo
    # tendría que acordarse de juntar, y el que se olvidara generaría la misma
    # cenefa 18 veces sin un solo error a la vista.
    parsed, juntado = juntar_filas_por_producto(parsed)
    # Va siempre, 0 incluido, para que la pantalla pueda decir cuántas filas se
    # saltearon sin tener que preguntarse si la clave existe. Es para avisar, no
    # para frenar nada.
    juntado["filas_sin_sucursal"] = filas_sin_sucursal
    return parsed, learned_aliases_count, headers_crudos, juntado


# ---------------------------------------------------------------------------
# Fiambres por kg -> deben ir a 100g (descripción) y precio÷10
# ---------------------------------------------------------------------------
#
# Mismo criterio que ya usan dos reglas independientes del generador de
# Cenefas (data_engine.py): "fiambr" en COMPRADOR es la señal de categoría
# (ese precedente vive en process_row, líneas ~222-236), y "kg" como unidad
# suelta en el texto es la señal de que todavía está en kilogramo (ese
# criterio viene del precedente de subCategoria en _apply_legacy_compute).
# Acá se combinan: a diferencia de ambos precedentes, esto NO calcula el
# precio nuevo ni lo persiste en ningún lado — solo marca la fila para que
# el frontend decida qué mostrar/sugerir.
#
# Excepción confirmada con el equipo: chorizo, morcilla, frankfurters y panchos
# NUNCA pasan a 100g aunque el texto diga "Kg" -- chorizo y morcilla se venden
# por kilo por decisión comercial, y frankfurters/panchos mantienen el peso
# original del envase. Ninguno de los cuatro casos es "menos fiambre" que jamón
# cocido o salame (que sí convierten) -- es una excepción por línea de producto,
# no por categoría. (Morcilla se sumó el 2026-08-27, pedido de Ivan.)

_RE_FIAMBRE = re.compile(r"fiambr", re.IGNORECASE)
_RE_UNIDAD_KG = re.compile(r"(?:^|[\s.])kg\.?(?:$|[\s.,)])", re.IGNORECASE)
_RE_SIN_CONVERSION_100G = re.compile(
    r"\bchorizos?\b|\bmorcillas?\b|\bfrankfurters?\b|\bpanchos?\b", re.IGNORECASE)


def _tiene_unidad_kg(*textos: str) -> bool:
    return any(_RE_UNIDAD_KG.search(t) for t in textos if t)


def _tiene_producto_sin_conversion(*textos: str) -> bool:
    return any(_RE_SIN_CONVERSION_100G.search(t) for t in textos if t)


def _es_fiambre_por_kg(comprador: str, nombreArticulo: str, descripcion: str, descripcionWeb: str) -> bool:
    if not comprador or not _RE_FIAMBRE.search(comprador):
        return False
    if _tiene_producto_sin_conversion(nombreArticulo, descripcion, descripcionWeb):
        return False
    return _tiene_unidad_kg(nombreArticulo, descripcion, descripcionWeb)


# ---------------------------------------------------------------------------
# La unidad de cobro que el nombre de gestión NO dice (pedido de Ivan, 2026-08-27)
# ---------------------------------------------------------------------------
#
# "MORCILLA DULCE DON JOAQUIN", "MUZZA NATURALACT", "PANCETA AHUMADA VILLA
# MARGARITA": ninguno de los tres trae la unidad en el nombre. Tinín tiene
# PROHIBIDO inventar datos que no estén en la fuente (ver _STYLE_RULES en
# convertidor_ai.py), así que hacía lo correcto -- escribir la descripción sin
# gramaje -- y el cartel salía sin decir por cuánto se cobra. No era un problema
# del modelo: el dato no estaba en el prompt.
#
# Con qué unidad se cobra es conocimiento de góndola, no algo deducible del
# texto: la fiambrería y los quesos DE CORTE se cobran por 100 g, y morcilla y
# chorizo por kilo, aunque los cuatro estén en la misma vitrina. Por eso va como
# tabla explícita por línea de producto, igual que la excepción de arriba.
#
# Esto es SOLO para la unidad que FALTA. Si el texto ya dice "Kg" y el producto
# es de los que van por 100 g, no falta la unidad: está equivocada, y ese caso es
# el de _es_fiambre_por_kg (arriba), que además propone el precio÷10. Separarlos
# deja una sola vía para cada arreglo.

# Se cobran por kilo. Frankfurters y panchos NO están acá a propósito: van por
# envase, y el peso del envase no se puede adivinar -- para esos no hay unidad
# que sugerir, así que quedan como estaban (sin marca).
_RE_LINEA_KG = re.compile(r"\bchorizos?\b|\bmorcillas?\b", re.IGNORECASE)

# Se cobran por 100 g venga el comprador que venga. La fiambrería entra sola por
# COMPRADOR (más abajo), pero el queso de corte puede venir clasificado por
# LACTEOS y tiene la misma unidad -- ese agujero ya está documentado en el bloque
# de _precio_es_de_kilo_en_100g. Las variantes de escritura de muzzarella son las
# que aparecen en los exports reales ("MUZZA", "MUZZARELLA", "MOZARELLA").
_RE_LINEA_100G = re.compile(
    r"\bquesos?\b|\bmuzza\b|\bmu[sz]{1,2}arel+as?\b|\bmo[sz]{1,2}arel+as?\b"
    r"|\bpancetas?\b|\bjam[oó]n(?:es)?\b|\bsalames?\b|\bsalamin(?:es)?\b",
    re.IGNORECASE,
)

# El texto ya declara su propia cantidad ("500 g", "2 L", "x 12") o la unidad
# "Kg" suelta. Cuando eso pasa la tabla de arriba NO opina: "Muzzarella
# CONAPROLE 500 g" es un paquete que se vende por unidad, no queso de corte, y
# ponerle "100g" sería mentir en el cartel y encima disparar un precio÷10.
_RE_CANTIDAD_PROPIA = re.compile(
    r"\d\s*(?:kgs?|kilos?|kg|grs?|gramos?|g|mls?|cc|litros?|lts?|l|un|u)\b|\bx\s*\d+\b",
    re.IGNORECASE,
)


def _tiene_cantidad_propia(*textos: str) -> bool:
    return (any(_RE_CANTIDAD_PROPIA.search(t) for t in textos if t)
            or _tiene_unidad_kg(*textos))


def _unidad_de_venta(comprador: str, nombreArticulo: str, descripcion: str,
                     descripcionWeb: str) -> str:
    """Con qué unidad se cobra el producto, cuando el texto de origen no lo dice.

    Devuelve "100g", "kg" o "" (no se sabe, o el texto ya trae su cantidad). Es
    lo único que le faltaba a Tinín para escribir el gramaje sin inventar nada.
    No calcula ni toca precios: solo marca la fila."""
    textos = (nombreArticulo, descripcion, descripcionWeb)
    if _tiene_cantidad_propia(*textos):
        return ""
    if any(_RE_LINEA_KG.search(t) for t in textos if t):
        return "kg"
    # Antes de la lista de 100 g: un frankfurter de la fiambrería va por envase,
    # y sin este corte caería en la regla de comprador de más abajo.
    if _tiene_producto_sin_conversion(*textos):
        return ""
    if any(_RE_LINEA_100G.search(t) for t in textos if t):
        return "100g"
    if comprador and _RE_FIAMBRE.search(comprador):
        return "100g"
    return ""


# Acá vivían CATEGORIAS_PRODUCTO, _RE_CATEGORIAS_PRODUCTO y categoria_de_producto: se borraron el 15/09/2026 porque la categoría sale de la columna dsc_subfamilia del listado y de ningún otro lado (Ivan: "no hace falta tinín ni nada de detectar automáticamente").


# ---------------------------------------------------------------------------
# LEER ESTO ANTES DE TOCAR el chequeo de 100 g  (decisión de Ivan, 2026-08-26)
# ---------------------------------------------------------------------------
#
# La fiambrería de corte se vende por 100 g: el cartel muestra el precio de
# 100 g, no el del kilo. `_es_fiambre_por_kg` (arriba) cubre el caso en que la
# DESCRIPCIÓN todavía viene en kilo y hay que pasarla a 100 g.
#
# Esto cubre el caso INVERSO, que es el que se escapaba: la descripción ya dice
# "100 g" y el que quedó en kilo es el PRECIO. Pasó de verdad en el Rompe del
# Finde del 27 al 30/8 y se imprimió así:
#
#     Jamón Crudo TIENDA INGLESA 100 g          1.100  ->  110
#     Queso Colonia EL GAUCHO de Corte 100 g      590  ->   59
#     Jamón Cocido Extra TIENDA INGLESA 100 g     840  ->   84
#
# `_es_fiambre_por_kg` no lo veía porque exige que el texto diga "Kg", y estas
# filas ya decían "100 g". Tampoco se pide que el comprador sea FIAMBRERIA: el
# queso de corte puede venir por LACTEOS y tiene el mismo problema.
#
# La app NO divide sola. Marca la fila y propone el valor; una persona confirma
# (decisión de Ivan, explícita). Un falso positivo acá imprime un precio diez
# veces más barato en la góndola, así que no puede ser automático.

_RE_CIEN_GRAMOS = re.compile(r"(?:^|[^\d.,])100\s*(?:g|gr|grs|gramos)\b", re.IGNORECASE)

# Arriba de esto, un precio de "100 g" no existe en góndola: es el del kilo. No
# es una regla exacta, es un olor -- de ahí que dispare un aviso y no una
# división. Lo más caro de la fiambrería ronda los $135 los 100 g (jamón crudo
# a $1.350 el kilo), así que $400 deja casi 3x de margen antes de molestar.
_PRECIO_MAX_POR_100G = 400


def _es_por_100g(*textos: str) -> bool:
    return any(_RE_CIEN_GRAMOS.search(t) for t in textos if t)


# Un "1.100" escrito como TEXTO en el Excel: _parse_price_or_none lo lee como
# 1,1 porque toma el punto como decimal, y este chequeo se perdería justo el
# caso que más importa. Se normaliza el separador de miles solo acá y solo en un
# patrón inequívoco (grupos de exactamente tres dígitos), sin tocar el parser
# que usa todo el resto del archivo.
_RE_SEPARADOR_MILES = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def _precio_es_de_kilo_en_100g(precioRaw, *textos: str, unidadVenta: str = "") -> bool:
    """La fila se vende por 100 g pero el precio que vino parece el del kilo.

    `unidadVenta` ("100g" cuando lo sabemos por línea de producto, ver
    _unidad_de_venta) cuenta igual que si el texto lo dijera. Sin eso, la MUZZA
    y la PANCETA cuya descripción Tinín recién ahora escribe con "100g" pasarían
    de largo por este chequeo y saldrían con el precio del kilo -- exactamente el
    error que se imprimió en el Rompe del Finde y que el bloque de arriba cuenta.
    """
    if unidadVenta != "100g" and not _es_por_100g(*textos):
        return False
    crudo = str(precioRaw or "").strip().lstrip("$U S").strip()
    if _RE_SEPARADOR_MILES.match(crudo):
        precio = float(crudo.replace(".", ""))
    else:
        precio = _parse_price_or_none(precioRaw)
    return precio is not None and precio >= _PRECIO_MAX_POR_100G


# ---------------------------------------------------------------------------
# Matching contra el catálogo + warnings
# ---------------------------------------------------------------------------

def _compute_warnings(row: dict) -> list[str]:
    """Un warning por columna, cada uno con su propio motivo.

    Dos familias: "falta el dato" (missing_*) y "hay contenido pero no del
    tipo que esa columna espera" (*_invalido), que es la señal real de un
    Excel con las columnas corridas, localizada en la columna exacta que no
    cierra. Se suman los warnings de mecánica que ya calculó
    convertidor_variables (oferta_inesperada, combo_no_parseable...), que
    viajan en la fila bajo "warningsMecanica".
    """
    w = list(row.get("warningsMecanica") or [])

    descripcion = str(row.get("descripcion") or "").strip()
    if not descripcion:
        w.append("missing_description")
    elif not _has_letters(descripcion):
        w.append("descripcion_invalida")
    elif len(descripcion) > DESCRIPTION_MAX_CHARS:
        # Es para un cartel de precio, no un párrafo -- mismos umbrales que
        # validation_engine.py, así no hay que inventar un límite nuevo acá.
        # Ahora pesa más que antes: el motor ya no achica la descripción sola
        # para que entre (ver la nota en component_renderer.py).
        w.append("descripcion_larga")
    elif len(descripcion) > DESCRIPTION_WARN_CHARS:
        w.append("descripcion_algo_larga")

    precioRaw = str(row.get("precioRaw") or "").strip()
    if not precioRaw:
        w.append("missing_price")
    elif not _is_numeric_like(precioRaw):
        w.append("precio_invalido")

    precioAnteriorRaw = str(row.get("precioAnteriorRaw") or "").strip()
    if not precioAnteriorRaw:
        w.append("missing_precio_anterior")
    elif not _is_numeric_like(precioAnteriorRaw):
        w.append("precio_anterior_invalido")

    # Se vende por 100 g pero el precio vino del kilo. La fila ya trae el
    # chequeo hecho (ver el bloque de arriba); acá solo se convierte en aviso,
    # que es lo que la grilla sabe mostrar.
    if row.get("precioDeKiloEn100g"):
        w.append("precioDeKiloEn100g")

    ofertaDet = str(row.get("ofertaDet") or "").strip()
    if not ofertaDet:
        w.append("missing_oferta_det")
    elif _is_numeric_like(ofertaDet):
        w.append("oferta_det_invalido")  # es una categoría, nunca un número puro

    descripcionWeb = str(row.get("descripcionWeb") or "").strip()
    if not descripcionWeb:
        w.append("missing_descripcion_web")
    elif not _has_letters(descripcionWeb):
        w.append("descripcion_web_invalida")

    moneda = str(row.get("moneda") or "").strip()
    moneda_norm = moneda.lower()
    if moneda_norm and moneda_norm not in _VALID_MONEDAS:
        w.append("moneda_invalida")
    elif moneda_norm and moneda_norm not in ("$", "uyu"):
        # Desde 2026-08-29 el símbolo viaja en la variable unidadMoneda, así
        # que una fila en dólares SÍ sale con "U$S" solo. El aviso queda
        # igual: un precio en dólares en una góndola de pesos es algo que
        # una persona tiene que mirar, aunque el símbolo salga bien.
        w.append("moneda_no_pesos")

    nombreArticulo = str(row.get("nombreArticulo") or "").strip()
    if nombreArticulo and not _has_letters(nombreArticulo):
        w.append("nombre_articulo_invalido")

    return w


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ---------------------------------------------------------------------------
# Pares "mismo producto, dos SKUs" -- patrón real: sufijo suelto " M" / " A"
# al final del nombre (ej. "CUADRIL S/HUESO M" / "CUADRIL SIN HUESO A"), no
# exclusivo de una categoría -- confirmado también en NALGA con datos reales.
# ---------------------------------------------------------------------------

_MA_SIMILARITY_THRESHOLD = 0.6
# Sufijo M/A suelto al final del nombre, con o sin comillas -- "COCA COLA" NO
# matchea (la "A" es parte de la palabra, no un sufijo separado por espacio).
_RE_MA_SUFFIX = re.compile(r'(?:^|\s)["\']*([MA])["\']*\s*$', re.IGNORECASE)


def _ma_base_and_suffix(nombreArticulo: str) -> tuple[str, str] | None:
    s = nombreArticulo.strip()
    m = _RE_MA_SUFFIX.search(s)
    if not m:
        return None
    base = s[:m.start()].strip()
    return (base, m.group(1).upper()) if base else None


def detect_ma_pairs(rows: list[dict], catalogo: dict[str, str]) -> list[dict]:
    """Agrupa candidatos (nombre terminado en sufijo suelto M/A) por
    comprador, y empareja greedy por similarity ratio (difflib) sobre la base
    sin sufijo -- no exige igualdad exacta: "S/HUESO" vs "SIN HUESO" ~0.82.
    Un par necesita un M y un A (nunca dos del mismo sufijo) del mismo
    comprador. Saltea pares donde ambos SKUs ya resuelven a la misma
    descripción en el catálogo singular. Un par unificado ANTES (grupo en
    cenefa_grupos_unificados, sin entrada singular) sí se vuelve a proponer;
    no es grave: guardar_grupo_unificado upserta por conjunto de SKU, así
    que re-aprobarlo actualiza el grupo en vez de duplicarlo, y el aviso de
    "grupo completo" del frontend ya ofrece aplicarlo con un click."""
    candidatos: dict[str, list[dict]] = {}
    for r in rows:
        parsed = _ma_base_and_suffix(r["nombreArticulo"])
        if not parsed:
            continue
        base, suffix = parsed
        comprador = (r.get("comprador") or "").strip().lower()
        candidatos.setdefault(comprador, []).append({
            "codigo": r["codigo"],
            "nombreArticulo": r["nombreArticulo"],
            "base": base,
            "suffix": suffix,
        })

    pairs: list[dict] = []
    seen_skus: set[str] = set()
    for items in candidatos.values():
        used: set[int] = set()
        for i, a in enumerate(items):
            if i in used or a["codigo"] in seen_skus:
                continue
            best_j, best_ratio = None, 0.0
            for j in range(i + 1, len(items)):
                b = items[j]
                if j in used or b["suffix"] == a["suffix"] or b["codigo"] in seen_skus:
                    continue
                ratio = difflib.SequenceMatcher(None, a["base"].lower(), b["base"].lower()).ratio()
                if ratio > best_ratio:
                    best_ratio, best_j = ratio, j
            if best_j is None or best_ratio < _MA_SIMILARITY_THRESHOLD:
                continue
            b = items[best_j]
            if catalogo.get(a["codigo"]) and catalogo.get(a["codigo"]) == catalogo.get(b["codigo"]):
                continue  # ya unificados antes -- mismo SKU compuesto ya resuelve a ambos
            used.add(i)
            used.add(best_j)
            seen_skus.add(a["codigo"])
            seen_skus.add(b["codigo"])
            pairs.append({
                "sku1": a["codigo"],
                "sku2": b["codigo"],
                "nombre1": a["nombreArticulo"],
                "nombre2": b["nombreArticulo"],
                "base": a["base"] if len(a["base"]) >= len(b["base"]) else b["base"],
            })
    return pairs


async def match_rows(
    parsed: list[dict], db: AsyncSession,
    banco_multiplicador: float | None = None,
    banco_nombre: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Bulk lookup por SKU (un SELECT por cada 1000 códigos distintos, no
    N queries) + cómputo de warnings por fila.

    De dónde sale la descripción, en orden:

    1. **La columna "Descripción" del Excel**, si viene con algo. Si alguien
       la escribió, por algo la escribió: es la que quiere ver en el cartel y
       no se toca (decisión de 2026-08-24; antes se ignoraba siempre y el
       catálogo pisaba lo escrito -- en un listado real de 10 filas sobrevivía
       UNA, seis salían cambiadas y tres vacías).
    2. **El catálogo** (sku_descripciones), buscando por SKU.
    3. **Vacía**, con warning "missing_description" y fila roja, para
       resolverse por "Generar con IA" (usa nombreArticulo + descripcionWeb)
       o a mano.

    Lo que NO cambia: nunca se aprende nada en el catálogo compartido de forma
    automática. Una descripción escrita en el Excel vale para esa corrida; al
    catálogo se sube solo cuando alguien lo decide explícitamente.

    `banco_multiplicador`/`banco_nombre`: mismo valor para TODA la corrida
    (no varían por fila, a diferencia de `mapeo`/`valores`) -- ver
    ConvertidorBancoPreset y construir_variables().

    Devuelve (rows, ma_pairs) -- ma_pairs son los pares "mismo producto, dos
    SKUs" detectados (ver detect_ma_pairs) todavía sin unificar."""
    skus = sorted({r["codigo"] for r in parsed if r["codigo"]})
    catalogo: dict[str, str] = {}
    for chunk in _chunks(skus, 1000):
        result = await db.execute(
            select(SkuDescripcion.sku, SkuDescripcion.descripcion)
            .where(SkuDescripcion.sku.in_(chunk))
        )
        catalogo.update(dict(result.all()))

    # NO hay fallback por claves combinadas (eliminado 2026-08-28, decisión de
    # Ivan). Antes, un SKU suelto sin entrada propia recibía la descripción DEL
    # GRUPO si aparecía dentro de una clave compuesta ("SKU1-SKU2"), con
    # matched=true y sin warning -- o sea, texto de familia ("Todas las
    # variedades") presentado como si fuera la descripción de ese producto.
    # La regla ahora es estricta: el catálogo singular (sku_descripciones)
    # tiene UNA descripción de ESE producto por SKU, y lo grupal vive aparte
    # en cenefa_grupos_unificados (grupos_para_skus ya avisa cuando los SKU
    # del import tocan un grupo conocido). Un SKU sin descripción propia queda
    # vacío y en rojo, que es lo que obliga a escribir la de verdad.

    # Las familias de mecánica que alguien ya confirmó para un OFERTADET que el
    # motor no reconoce. Una sola consulta para todo el listado: son un puñado
    # de textos distintos aunque vengan mil filas.
    familias: dict[str, str] = {}
    dets = {_norm(r.get("ofertaDet") or "") for r in parsed}
    dets.discard("")
    if dets:
        familias = {
            a.ofertadet_norm: a.familia
            for a in (await db.execute(
                select(CenefaOfertadetAlias)
                .where(CenefaOfertadetAlias.ofertadet_norm.in_(dets))
            )).scalars().all()
        }

    rows = []
    for i, r in enumerate(parsed):
        del_excel = (r.get("descripcionExcel") or "").strip()
        descripcion = del_excel or catalogo.get(r["codigo"], "")
        origen = "excel" if del_excel else ("catalogo" if descripcion else "")

        # Las 26 variables ya resueltas: mecánica redactada, precios partidos
        # en entero + decimal, y lo que la persona mapeó pisando lo calculado.
        variables, warn_mecanica = construir_variables(
            r,
            descripcion,
            r.get("_mapeado") or {},
            vigencia_fallback=_format_vigencia(r.get("fechaInicio"), r.get("fechaFin")),
            familia_ofertadet=familias.get(_norm(r.get("ofertaDet") or "")),
            banco_multiplicador=banco_multiplicador,
            banco_nombre=banco_nombre,
        )

        # Contexto del export de gestión: no son variables y no se exportan,
        # pero se muestran en la grilla para que una persona pueda entender
        # de dónde salió cada valor calculado y corregirlo si algo no cierra.
        contexto = {
            "nombreArticulo":     r["nombreArticulo"],
            # De dónde salió la descripción: "excel" (la escribió una persona
            # en el listado), "catalogo" (la puso la plataforma) o "" (falta).
            "descripcionOrigen":  origen,
            "comprador":           r["comprador"],
            "moneda":              r["moneda"],
            "ofertaOrigen":       r["oferta"],
            "ofertaDet":          r["ofertaDet"] or "",
            "descripcionWeb":     r["descripcionWeb"],
            "precioRaw":          r["precioRaw"],
            "precioAnteriorRaw": r["precioAnteriorRaw"],
            # Stock por sucursal tal cual vino del listado: {sucursal: unidades}.
            # Vacío cuando el archivo no trae columnas de stock, que es el caso
            # normal -- y ese vacío es exactamente lo que hace que "dividir por
            # sucursales" no tenga nada para ofrecer. Va y vuelve por la grilla
            # (ver armar_zip_dividido), no sale en ninguna columna del Excel.
            "stockPorSucursal":   r.get("_stock") or {},
            # Qué tipo de producto es. Sale de las columnas del listado y de
            # ningún otro lado (Ivan, 15/09/2026): el export trae dsc_subfamilia
            # --AURICULARES, FREIDORA, MIXER, CAFETERA-- escrita por quien carga
            # el producto, en 271 de 273 filas, así que deducirla del texto sería
            # adivinar lo que el archivo ya dice. La excepción son los televisores,
            # que vienen todos como "4K" y se resuelven por dsc_familia (ver
            # categoria_del_listado). La fila que no traiga ninguna de las dos va
            # a "Sin categoría.xlsx" y se corrige a mano en la grilla, que para
            # eso tiene la columna editable.
            "categoriaProducto":  categoria_del_listado(
                r.get("categoriaProducto", ""), r.get("familiaProducto", "")),
        }

        # Con qué unidad se cobra el producto, cuando el texto de origen no lo
        # dice. Se calcula una vez porque la usan dos cosas distintas: la marca
        # que va al prompt de Tinín (para que escriba el gramaje) y el chequeo de
        # precio de acá abajo (para que ese gramaje no quede con el precio del
        # kilo).
        unidadVenta = _unidad_de_venta(
            r["comprador"], r["nombreArticulo"], descripcion, r["descripcionWeb"]
        )

        fila = {
            "row_id":  i,
            "matched": bool(descripcion),
            **contexto,
            **variables,
            "esFiambreKg": _es_fiambre_por_kg(
                r["comprador"], r["nombreArticulo"], descripcion, r["descripcionWeb"]
            ),
            "unidadVenta": unidadVenta,
            "precioDeKiloEn100g": _precio_es_de_kilo_en_100g(
                r["precioRaw"], r["nombreArticulo"], descripcion, r["descripcionWeb"],
                unidadVenta=unidadVenta,
            ),
            "warningsMecanica": warn_mecanica,
        }
        fila["warnings"] = _compute_warnings(fila)
        rows.append(fila)

    ma_pairs = detect_ma_pairs(rows, catalogo)

    return rows, ma_pairs


# ---------------------------------------------------------------------------
# Generación del Excel de salida
# ---------------------------------------------------------------------------

# El Excel de salida tiene UNA COLUMNA POR VARIABLE, con el nombre exacto de
# la variable como encabezado. No hay traducción ni nombres "bonitos": ese
# archivo se vuelve a subir al generador de cenefas, que matchea las columnas
# por nombre canónico y nada más. Antes la salida repetía las columnas de
# gestión (Oferta, Oferta Det, Descripción Web...) y el generador tenía que
# volver a interpretarlas; ahora los valores ya vienen resueltos.
_ANCHAS = {"descripcion", "mecanica", "vigencia", "legales",
           "aclaracionUno", "aclaracionDos", "aclaracionTres"}

# Columnas que salen SIEMPRE, tengan dato o no: son las que arman una cenefa
# mínima. Verlas vacías es justamente la señal de que falta completarlas, y
# los dos decimales acompañan a su precio porque el diseño de la cenefa tiene
# un cuadro aparte para ellos.
_COLUMNAS_FIJAS: frozenset[str] = frozenset((
    "codigo", "descripcion", "mecanica",
    "precioRegular", "decimalPrecioRegular",
    "precioOferta",  "decimalPrecioOferta",
))


def _columnas_de_salida(rows: list[dict]) -> list[str]:
    """Qué columnas lleva el Excel: las fijas más las que traen algún dato.

    Una columna que queda vacía en TODAS las filas no se crea. Antes salían
    las 26 siempre y un listado normal de gestión --que no trae vigencia, ni
    aclaraciones, ni niveles de oferta, ni banco-- se bajaba con 19 columnas
    vacías al lado de las que importan.

    No se pierde nada: el generador de cenefas no exige ninguna variable, y
    una que no está en el Excel simplemente no se sustituye en el diseño.

    Un precio y su decimal van SIEMPRE juntos, aunque el decimal quede vacío:
    son un par (precioOferta/decimalPrecioOferta, ofertaUno/decimalPrecioUno,
    y así) y el diseño de la cenefa tiene un cuadro separado para cada uno.
    Sacar el decimal porque en este listado todos los precios dieron redondos
    dejaría media pareja, y al listado siguiente --con un solo precio con
    centavos-- la columna aparecería de la nada.
    """
    con_dato = {
        var for var in ORDEN_EXPORT
        if any(str(r.get(var, "") or "").strip() for r in rows)
    }
    incluidas = con_dato | set(_COLUMNAS_FIJAS)
    incluidas |= {DECIMAL_OF[p] for p in PRICE_VARS if p in incluidas}
    return [v for v in ORDEN_EXPORT if v in incluidas]


# Warning -> variable cuya columna se resalta. Se guarda el NOMBRE y no el
# indice porque el Excel de salida ya no lleva siempre las mismas columnas
# (ver _columnas_de_salida): el indice se resuelve recien al armarlo.
#
# Los de mecanica apuntan a la columna mecanica, que es donde se ve el
# resultado de la interpretacion que hay que revisar.
_WARN_VAR = {
    "missing_description":      "descripcion",
    "descripcion_invalida":     "descripcion",
    "descripcion_larga":        "descripcion",
    "descripcion_algo_larga":   "descripcion",
    "missing_price":            "precioOferta",
    "precio_invalido":          "precioOferta",
    "missing_precio_anterior":  "precioRegular",
    "precio_anterior_invalido": "precioRegular",
    # Estos nacen de las columnas OFERTA/OFERTADET del listado de gestion. Se
    # marcaban sobre "mecanica" --donde se corrige-- y eso hacia imposible
    # entenderlos: dos filas con "Precio Final" identico, una marcada y la
    # otra no, y la diferencia tres columnas mas alla. Ahora se marca donde
    # esta el dato que no cierra. En el Excel de salida no hay columna OFERTA
    # (es contexto, no variable), asi que ahi caen sobre mecanica igual.
    "oferta_inesperada":        "mecanica",
    "combo_no_parseable":       "mecanica",
    "mxn_no_parseable":         "mecanica",
    "mxn_sin_precio":           "mecanica",
    "oferta_det_invalido":      "mecanica",
    "missing_oferta_det":       "mecanica",
    # Desde 2026-08-29 el simbolo es una variable propia: los problemas de
    # moneda se pintan sobre ella, no sobre el precio.
    "moneda_invalida":          "unidadMoneda",
    "moneda_no_pesos":          "unidadMoneda",
}

# Warnings que NO son "falta el dato" sino "hay contenido que no cierra":
# apuntan a un Excel con las columnas corridas o a un valor que una persona
# tiene que decidir. Se pintan distinto porque no se arreglan completando.
_INVALID_TYPE_CODES = {
    "nombre_articulo_invalido", "descripcion_invalida", "descripcion_larga",
    "moneda_invalida", "moneda_no_pesos",
    "precio_anterior_invalido", "precio_invalido", "oferta_det_invalido",
    "descripcion_web_invalida",
    "oferta_inesperada", "combo_no_parseable", "mxn_no_parseable", "mxn_sin_precio",
}


def build_output_workbook(rows: list[dict], columnas: list[str] | None = None) -> bytes:
    """El xlsx de salida. `columnas` fija cuáles lleva; None = las que
    _columnas_de_salida deduce de ESTAS filas, que es el comportamiento de
    siempre y el de todas las descargas de un solo archivo.

    El parámetro existe para la descarga dividida (ver armar_zip_dividido): ahí
    un mismo listado sale partido en varios Excel y las columnas se calculan una
    sola vez sobre TODAS las filas. Si cada libro dedujera las suyas, la sucursal
    que ese día no tuviera ninguna fila con banco saldría sin las columnas de
    banco y la de al lado con ellas -- y son archivos que se abren uno al lado
    del otro justamente para compararlos.

    Una lista vacía se trata igual que None a propósito: un Excel sin ninguna
    columna no le sirve a nadie y el error recién se vería al abrir el archivo.
    """
    fields = list(columnas) if columnas else _columnas_de_salida(rows)
    headers = fields
    col_widths = [34 if v in _ANCHAS else 18 for v in fields]
    # {codigo_de_warning: indice_de_columna} solo para las columnas que
    # realmente salieron.
    warn_col = {
        code: fields.index(var) + 1
        for code, var in _WARN_VAR.items() if var in fields
    }
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cenefas"

    header_fill    = PatternFill("solid", fgColor="1E3A5F")
    header_font    = Font(bold=True, color="FFFFFF", size=11)
    even_fill      = PatternFill("solid", fgColor="EEF2F7")
    warn_fill      = PatternFill("solid", fgColor="FDE68A")  # ámbar — falta el dato
    no_match_fill  = PatternFill("solid", fgColor="FCA5A5")  # rojo — sin descripción, acción obligatoria
    invalid_fill   = PatternFill("solid", fgColor="DDD6FE")  # violeta — hay dato, pero no del tipo que esa columna espera

    for col, name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, r in enumerate(rows, 2):
        # Recalculado server-side a partir de los mismos campos _raw que
        # ya viajaron en el preview — no confía en el array "warnings" que
        # mandó el cliente, única fuente de verdad para el coloreado.
        warnings = _compute_warnings(r)
        zebra = even_fill if row_idx % 2 == 0 else None
        for col_idx, field in enumerate(fields, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=r.get(field))
            cell.alignment = Alignment(vertical="center")
            warn_code = next((w for w, c in warn_col.items() if c == col_idx and w in warnings), None)
            if warn_code == "missing_description":
                cell.fill = no_match_fill
            elif warn_code in _INVALID_TYPE_CODES:
                cell.fill = invalid_fill
            elif warn_code:
                cell.fill = warn_fill
            elif zebra:
                cell.fill = zebra

    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Descarga dividida: una carpeta por sucursal, un Excel por categoría
# ---------------------------------------------------------------------------
#
# Ivan, 15/09/2026: "el resultado esperado es una carpeta mayor que tendrá sub
# carpetas por sucursales de tienda inglesa que tendrán adentro diferentes
# excels por cada categoría que correspondan a un stock mayor o igual a 1 para
# esa sucursal".
#
# La "carpeta mayor" no se arma acá: es la que crea el descompresor con el
# nombre del propio ZIP. Adentro van rutas y nada más -- "suc1/Heladeras.xlsx"
# ya crea la carpeta "suc1", así que no se escriben entradas de directorio.

# El nombre del Excel donde caen las filas que ninguna regla clasificó. No es un
# descarte: es un archivo visible, con las filas adentro, y además se cuenta en
# el resumen. Que se pierdan filas en silencio es lo que motivó todo el sistema
# de warnings de este módulo, y partir la descarga en N archivos es justo el
# momento en que nadie se daría cuenta.
_SIN_CATEGORIA = "Sin categoría"

# Lo que Windows no acepta en un nombre de archivo, más los caracteres de
# control (que ningún sistema acepta).
_RE_PROHIBIDO_EN_NOMBRE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')

# Los nombres que Windows tiene reservados desde el DOS: son dispositivos, no
# archivos, y no se puede crear ninguno ni como archivo ni como carpeta. Acá no
# hay ningún caracter prohibido que sacar --"CON" es un nombre perfectamente
# normal--, así que pasaban enteros y la extracción fallaba al llegar a ese
# archivo. Es un caso real y no teórico: una categoría "Aux", una sucursal
# escrita "Con" o un "PRN" de impresión alcanzan.
_NOMBRES_RESERVADOS_WINDOWS: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


def _nombre_para_zip(texto: str) -> str:
    """Deja un texto usable como nombre de archivo O DE CARPETA dentro del ZIP.

    Es una copia con cambios de _nombre_archivo (cenefas_v2.py), igual que _norm
    es copia de data_engine._norm y por la misma razón: importar un helper
    privado de una ruta desde un servicio acopla las dos cosas para siempre y
    son cuatro líneas. Pero además la de allá NO sirve tal cual, porque solo saca
    separadores y controles, y acá los nombres son encabezados de un Excel que
    sube cualquiera:

    - los PUNTOS del final ("Tienda Inglesa S.A.") hacen un nombre que Windows
      no puede escribir al descomprimir: en el mejor caso se come el punto en
      silencio, en el peor falla la extracción del ZIP entero.
    - ".." como nombre de carpeta no es un nombre, es una ruta relativa.
    - los ESPACIOS del final son el mismo problema que el punto y encima
      invisibles: nadie va a entender por qué ese archivo no se puede abrir.
    - los NOMBRES RESERVADOS de Windows ("CON", "AUX", "NUL", "PRN",
      "COM1".."COM9", "LPT1".."LPT9") no son archivos sino dispositivos: no se
      pueden crear, y el que descomprime se queda sin ESE archivo o sin el ZIP
      entero según con qué lo abra. Se les pega un "_" y dejan de serlo.

    Si no queda nada -> "SIN NOMBRE", en mayúsculas para que se note: una
    sucursal sin nombre igual tiene que poder bajarse. Perder el archivo es
    peor que un nombre feo.
    """
    limpio = _RE_PROHIBIDO_EN_NOMBRE.sub("", str(texto or ""))
    limpio = re.sub(r"\s+", " ", limpio)
    # Los puntos seguidos se colapsan en uno: así no sobrevive ningún ".." y un
    # "S.A." o un "2.5 L" quedan intactos.
    limpio = re.sub(r"\.{2,}", ".", limpio)
    # El corte va ANTES de sacar los puntos y espacios finales: cortar a 120
    # puede dejar justo un espacio o un punto colgando, que es lo que estamos
    # sacando.
    limpio = limpio.strip()[:120].rstrip(" .") or "SIN NOMBRE"
    # Windows mira el nombre ANTES del primer punto, así que "CON", "CON.xlsx" y
    # "CON.2.xlsx" son los tres el dispositivo de consola. Por eso el "_" va
    # pegado a ESA parte y no al final del nombre entero: un "NUL.xlsx" que
    # quedara como "NUL.xlsx_" sigue empezando con "NUL." y sigue sin poder
    # crearse. Con el "_" adelante del punto queda "NUL_.xlsx", que es un archivo
    # común. Acá la extensión .xlsx la pega el que llama, así que el nombre
    # reservado puede llegar pelado ("CON") o con puntos adentro ("CON.2").
    cabeza, punto, resto = limpio.partition(".")
    if cabeza.upper() in _NOMBRES_RESERVADOS_WINDOWS:
        limpio = f"{cabeza}_{punto}{resto}"
    return limpio


def armar_zip_dividido(
    rows: list[dict], *, por_categoria: bool, por_sucursal: bool, nombre_base: str,
) -> tuple[bytes, dict]:
    """El ZIP de la descarga dividida y su resumen: (bytes, dict).

    Pura y sin `db` a propósito: todo lo que necesita ya viaja en las filas que
    la grilla devuelve (`stockPorSucursal` y `categoriaProducto` son contexto
    que sale de match_rows, se ve y se corrige en pantalla). Así se puede testear
    de verdad -- conftest.py prohíbe base y red -- y así el trabajo pesado se
    puede tirar a un thread desde la ruta sin arrastrar una sesión de SQLAlchemy.

    Los dos interruptores son independientes y los tres modos existen:

    - `por_sucursal`: cada fila va a TODAS las sucursales donde tenga
      stockPorSucursal >= _STOCK_MINIMO. Una fila puede salir repetida en varias
      carpetas (está en varias góndolas, es correcto) y una fila sin stock en
      ninguna no sale en ningún archivo: esa se cuenta en "filas_sin_stock", que
      es el número que la pantalla muestra antes de descargar. En False no se
      filtra por stock: van todas.
    - `por_categoria`: adentro de cada grupo, un Excel por categoriaProducto.
      Las vacías caen en "Sin categoría.xlsx" y se cuentan.
    - Los dos en False es ValueError y no "bajá el Excel entero": para eso está
      /export, que devuelve un xlsx y no un zip, y confundir las dos cosas le
      rompe la descarga al cliente (que asume la extensión).

    Una sucursal sin ninguna fila simplemente no aparece en el ZIP. No hay nada
    que hacer al respecto ni forma de "crear la carpeta vacía": las entradas son
    rutas de archivo ("suc1/Heladeras.xlsx"), la carpeta la inventa el
    descompresor, y sin archivos adentro no hay carpeta. Queda documentado acá
    porque la pregunta va a volver.

    `nombre_base` NO entra en ninguna ruta de adentro del ZIP, y es a propósito:
    la "carpeta mayor" que pidió Ivan es la que crea el descompresor con el
    nombre del archivo .zip, así que ese nombre es cosa del Content-Disposition
    de la ruta. Queda en la firma porque es el dato que identifica la tanda y
    porque el día que haya que prefijar una carpeta de verdad adentro del ZIP ya
    está acá, sin cambiarle la firma a nadie.

    Si no queda ninguna fila el ZIP sale sin entradas y "archivos" es 0. Acá no
    se levanta un error por eso: la función arma lo que le piden y la ruta, que
    es la que habla con una persona, decide si eso es un 404 (mismo criterio que
    download_lote, que cuenta entradas y no bytes -- un ZIP vacío igual pesa 22).

    El resumen: {"archivos", "filas_sin_stock", "filas_sin_categoria",
    "sucursales", "categorias"}.
    """
    if not por_categoria and not por_sucursal:
        raise ValueError(
            "Elegí al menos una forma de dividir: por categorías, por sucursales o las dos"
        )

    # Las columnas, UNA sola vez y sobre TODAS las filas -- ver el docstring de
    # build_output_workbook. Es la razón por la que ese parámetro existe.
    columnas = _columnas_de_salida(rows)

    # Se agrupan ÍNDICES y no filas para poder contar sin repetir: con la
    # división por sucursal la misma fila entra en varias carpetas, y "3 filas
    # sin categoría" tiene que seguir diciendo 3 aunque esas 3 aparezcan en ocho
    # sucursales cada una. Un set de índices es la única forma barata de saber
    # "cuántas filas distintas", porque un dict no es hasheable.
    #
    # Sucursales y categorías se agrupan por su forma NORMALIZADA (_norm: sin
    # mayúsculas, sin acentos, sin espacios ni guiones) y se muestran con la
    # PRIMERA grafía que apareció. Es el arreglo del 15/09/2026: estas filas
    # vienen de la GRILLA, donde las dos cosas se ven y se corrigen a mano, así
    # que una fila arreglada como "heladeras" y otra como "Heladeras" son el
    # mismo tipo de producto -- pero agrupadas por el string exacto armaban DOS
    # archivos con el mismo nombre para Windows, uno pisando al otro al
    # descomprimir, y el set de colisiones de más abajo tampoco los veía porque
    # comparaba respetando las mayúsculas. Lo mismo entre "suc1" y "SUC1".
    filas_sin_stock = 0
    grupos: dict[str, list[int]] = {}
    # {clave normalizada: cómo se escribió la primera vez} de las sucursales.
    sucursal_visible: dict[str, str] = {}
    if por_sucursal:
        for i, r in enumerate(rows):
            # {clave: grafía} de ESTA fila, dict y no lista para que una fila que
            # trae "suc1" y "SUC1" a la vez --dos columnas del mismo listado-- no
            # se escriba dos veces adentro de la misma carpeta.
            donde: dict[str, str] = {}
            for sucursal, unidades in (r.get("stockPorSucursal") or {}).items():
                # Se vuelve a parsear en vez de confiar en el número: esto llega
                # de un request, y un "3" de string comparado contra un int
                # explota. _parse_stock_or_none es el mismo criterio con el que
                # se leyó el Excel, así que no hay dos formas de decir 3.
                cantidad = _parse_stock_or_none(unidades)
                if cantidad is None or cantidad < _STOCK_MINIMO:
                    continue
                nombre_suc = _clean_str(sucursal)
                donde.setdefault(_norm(nombre_suc), nombre_suc)
            if not donde:
                filas_sin_stock += 1
                continue
            for clave, nombre_suc in sorted(donde.items()):
                sucursal_visible.setdefault(clave, nombre_suc)
                grupos.setdefault(clave, []).append(i)
    else:
        # Un solo grupo sin eje de sucursal. La clave "" no se usa para nada más
        # que para no duplicar el bucle de abajo.
        grupos[""] = list(range(len(rows)))

    # Los nombres de CARPETA se sanean y se deduplican acá, UNA vez y ANTES del
    # bucle. Antes se saneaban al armar cada ruta, y entonces dos sucursales
    # distintas cuyos nombres sanean al mismo texto ("Suc/1" y "Suc1" quedan las
    # dos en "Suc1") terminaban compartiendo UNA carpeta con las filas de las dos
    # mezcladas: salía "Suc1/Heladeras.xlsx" y "Suc1/Heladeras (2).xlsx" y el que
    # repone góndola no tenía cómo saber cuál archivo era de cuál tienda --el
    # sufijo se lo comía el archivo en lugar de la carpeta--. Con el mapa armado
    # de antemano cada tienda tiene su carpeta y la segunda pasa a ser "Suc1 (2)".
    carpetas: dict[str, str] = {}
    if por_sucursal and por_categoria:
        usadas_carpetas: set[str] = set()
        for clave in sorted(grupos):
            base = _nombre_para_zip(sucursal_visible.get(clave, clave))
            carpeta_unica = base
            n = 2
            # La unicidad se mide por _norm y no por el string crudo, por lo
            # mismo que el agrupado: dos carpetas que se diferencian solo en las
            # mayúsculas son UNA sola carpeta cuando esto se descomprime.
            while _norm(carpeta_unica) in usadas_carpetas:
                carpeta_unica = f"{base} ({n})"
                n += 1
            usadas_carpetas.add(_norm(carpeta_unica))
            carpetas[clave] = carpeta_unica

    sin_categoria: set[int] = set()
    # {clave normalizada: primera grafía} de las categorías, compartido por TODAS
    # las sucursales a propósito: así el mismo tipo de producto se llama igual en
    # las ocho carpetas, aunque la fila que lo trajo primero en cada una esté
    # escrita distinto.
    categoria_visible: dict[str, str] = {}
    # El set lleva la RUTA COMPLETA y no el nombre suelto: ahora hay dos ejes, y
    # "Heladeras.xlsx" en suc1 y en suc2 no es una colisión sino lo esperable.
    usadas: set[str] = set()
    archivos = 0

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Ordenado para que la misma tanda dé siempre el mismo ZIP: el orden de
        # los dicts sale del orden de las filas del Excel, que cambia solo.
        for clave_suc in sorted(grupos):
            indices = grupos[clave_suc]
            if por_categoria:
                por_cat: dict[str, list[int]] = {}
                for i in indices:
                    cat = _clean_str(rows[i].get("categoriaProducto"))
                    if not cat:
                        cat = _SIN_CATEGORIA
                        sin_categoria.add(i)
                    clave_cat = _norm(cat)
                    categoria_visible.setdefault(clave_cat, cat)
                    por_cat.setdefault(clave_cat, []).append(i)
                bloques = [(categoria_visible[c], por_cat[c]) for c in sorted(por_cat)]
            else:
                # Sin eje de categoría el archivo se llama como la sucursal
                # (si llegamos acá, por_sucursal es True: el caso de los dos
                # apagados ya salió por el ValueError de arriba).
                bloques = [(sucursal_visible.get(clave_suc, clave_suc), indices)]

            # La carpeta existe solo cuando hay DOS ejes. Con uno solo el ZIP
            # queda plano: "suc1.xlsx" o "Heladeras.xlsx" sueltos, que es lo que
            # alguien espera cuando pidió una sola división.
            carpeta = (f"{carpetas[clave_suc]}/"
                       if por_sucursal and por_categoria else "")

            for nombre, idxs in bloques:
                base = f"{carpeta}{_nombre_para_zip(nombre)}"
                ruta = f"{base}.xlsx"
                # Dos nombres distintos pueden sanear al mismo ("Suc 1/2" y
                # "Suc 12"), y ahí uno se comía al otro dentro del ZIP sin que
                # nadie se enterara -- el mismo problema que ya tiene resuelto
                # download_lote con las plantillas repetidas. La comparación va
                # por _norm por lo mismo que la de las carpetas: "Heladeras.xlsx"
                # y "heladeras.xlsx" no pueden convivir en la misma carpeta.
                n = 2
                while _norm(ruta) in usadas:
                    ruta = f"{base} ({n}).xlsx"
                    n += 1
                usadas.add(_norm(ruta))
                zf.writestr(ruta, build_output_workbook([rows[i] for i in idxs], columnas))
                archivos += 1

    resumen = {
        "archivos":            archivos,
        "filas_sin_stock":     filas_sin_stock,
        # Cuenta filas DISTINTAS que cayeron en "Sin categoría.xlsx", no veces
        # que se escribieron: la misma fila sin categoría con stock en ocho
        # sucursales es una sola fila para clasificar, no ocho. Sin división por
        # categoría queda en 0, y está bien: no existe ningún "Sin categoría" al
        # que puedan estar cayendo.
        "filas_sin_categoria": len(sin_categoria),
        # Los nombres LÓGICOS, sin sanear y sin el sufijo de la carpeta: son los
        # que la persona ve en la grilla. De cada grupo sale la primera grafía
        # que apareció, que es la misma con la que se nombra el archivo.
        "sucursales":          ([sucursal_visible[c] for c in sorted(grupos)]
                                if por_sucursal else []),
        "categorias":          sorted(categoria_visible.values()),
    }
    return buf.getvalue(), resumen


# ---------------------------------------------------------------------------
# Grupos unificados: varios SKU, un solo cartel
# ---------------------------------------------------------------------------

async def guardar_grupo_unificado(
    db: AsyncSession, *, nombre: str, descripcion: str, skus: list[str], user_id: int | None,
) -> CenefaGrupoUnificado:
    """Guarda (o actualiza) un grupo por su CONJUNTO de SKU.

    La identidad del grupo es el conjunto, no el nombre ni el orden: el mismo
    listado subido dos veces con los codigos en otro orden es el mismo grupo, y
    no tiene que crear un duplicado.

    NO toca `sku_descripciones`. La descripcion individual de cada SKU es lo que
    permite rearmar el texto cuando manana venga solo una parte del grupo, asi
    que pisarla con el texto del grupo seria destruir justo el dato que hace
    falta.
    """
    normalizados = sorted({normalize_sku(s) for s in skus if normalize_sku(s)})
    if len(normalizados) < 2:
        raise ValueError("Un grupo unificado necesita al menos dos SKU distintos")

    existente = None
    for g in (await db.execute(
        select(CenefaGrupoUnificado)
        .where(CenefaGrupoUnificado.skus.overlap(normalizados))
    )).scalars().all():
        if sorted(g.skus) == normalizados:
            existente = g
            break

    if existente is not None:
        existente.nombre = nombre.strip()[:150]
        existente.descripcion = descripcion.strip()[:300]
        return existente

    grupo = CenefaGrupoUnificado(
        nombre=nombre.strip()[:150],
        descripcion=descripcion.strip()[:300],
        skus=normalizados,
        created_by=user_id,
    )
    db.add(grupo)
    return grupo


async def grupos_para_skus(db: AsyncSession, skus: list[str]) -> list[dict]:
    """Grupos guardados que tocan alguno de estos SKU, separando completos de
    parciales.

    Un grupo PARCIAL es el caso que importa: la promo de hoy trae 2 de los 3 SKU
    que el grupo conoce. La descripcion guardada NO se puede reusar tal cual --
    menciona un producto que hoy no esta en oferta, y un cartel de gondola no
    puede anunciar algo que no se vende a ese precio. Hay que reescribirla con
    los que si vinieron, a partir de sus descripciones individuales.
    """
    presentes = {normalize_sku(s) for s in skus if normalize_sku(s)}
    if not presentes:
        return []

    salida = []
    for g in (await db.execute(
        select(CenefaGrupoUnificado)
        .where(CenefaGrupoUnificado.skus.overlap(sorted(presentes)))
        .order_by(CenefaGrupoUnificado.nombre)
    )).scalars().all():
        del_grupo = set(g.skus)
        hay = sorted(del_grupo & presentes)
        faltan = sorted(del_grupo - presentes)
        salida.append({
            "id":          str(g.id),
            "nombre":      g.nombre,
            "descripcion": g.descripcion,
            "skus":        sorted(del_grupo),
            "presentes":   hay,
            "faltantes":   faltan,
            "completo":    not faltan,
        })
    return salida

